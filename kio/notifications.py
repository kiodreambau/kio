"""Best-effort outbound notifications for completed kio reviews."""

from __future__ import annotations

from email.message import EmailMessage
import json
import logging
from pathlib import Path
import smtplib
import ssl
import requests

from .config import KioConfig
from .models import BackendResult, WorkItem

DEFAULT_EMAIL_TEMPLATE = """# kiocheck review completed

Repository: {repo}
PR: #{pr} ({pr_url})
Commit: {head_sha}
Review level: {mode}

The native GitHub review has been submitted. The review body contains concrete evidence, impact, and recommended next actions.

## Codex handoff

{handoff}
"""

DEFAULT_CODEX_HANDOFF_TEMPLATE = """Review GitHub PR #{pr} in {repo} at commit {head_sha} using KIO {mode}.

Read the existing native kiocheck review and run artifacts first. Then inspect the actual changed behavior, exercise relevant browser or mobile flows where applicable, and report only evidence-backed findings. Do not push, merge, or create a fix PR. If a correction is appropriate, prepare the patch and explain it for the author to review.

PR: {pr_url}
Run artifact: {run_dir}
"""


def write_codex_handoff(
    item: WorkItem,
    *,
    config: KioConfig,
    run_dir: Path,
) -> Path:
    """Persist a concise, reusable handoff for the local Codex review session."""
    content = _render_template(
        config.codex_handoff_template_file,
        DEFAULT_CODEX_HANDOFF_TEMPLATE,
        _template_values(item, run_dir=run_dir),
    )
    path = run_dir / "codex-handoff.md"
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return path


def notify_review_completed(
    item: WorkItem,
    *,
    config: KioConfig,
    run_dir: Path,
    result: BackendResult,
    handoff_file: Path,
) -> list[dict[str, str]]:
    """Send configured outbound notifications without changing review completion semantics."""
    handoff = handoff_file.read_text(encoding="utf-8").strip()
    values = _template_values(item, run_dir=run_dir) | {"handoff": handoff}
    deliveries: list[dict[str, str]] = []
    if config.notification_email_to or config.smtp_host:
        deliveries.append(_send_email(config, values))
    if config.slack_webhook_url:
        deliveries.append(_send_slack(config, values))
    path = run_dir / "notifications.json"
    path.write_text(
        json.dumps({"deliveries": deliveries}, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return deliveries


def _send_email(config: KioConfig, values: dict[str, str]) -> dict[str, str]:
    required = {
        "notification_email_to": config.notification_email_to,
        "notification_email_from": config.notification_email_from,
        "smtp_host": config.smtp_host,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        return {"channel": "email", "status": "skipped", "detail": f"missing {', '.join(missing)}"}
    try:
        message = EmailMessage()
        message["Subject"] = (
            f"[kiocheck] {values['repo']} PR #{values['pr']} {values['mode']} complete"
        )
        message["From"] = config.notification_email_from
        message["To"] = ", ".join(config.notification_email_to)
        message.set_content(
            _render_template(
                config.notification_email_template_file, DEFAULT_EMAIL_TEMPLATE, values
            )
        )
        _deliver_email(config, message)
        return {
            "channel": "email",
            "status": "sent",
            "detail": str(len(config.notification_email_to)),
        }
    except Exception as exc:  # Best effort: a mail outage must not rerun a completed review.
        logging.exception("kio email notification failed")
        return {"channel": "email", "status": "failed", "detail": str(exc)}


def _deliver_email(config: KioConfig, message: EmailMessage) -> None:
    if config.smtp_security == "ssl":
        client: smtplib.SMTP = smtplib.SMTP_SSL(
            config.smtp_host,
            config.smtp_port,
            context=ssl.create_default_context(),
            timeout=30,
        )
    else:
        client = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30)
    try:
        if config.smtp_security == "starttls":
            client.starttls(context=ssl.create_default_context())
        if config.smtp_username:
            client.login(config.smtp_username, config.smtp_password)
        client.send_message(message)
    finally:
        client.quit()


def _send_slack(config: KioConfig, values: dict[str, str]) -> dict[str, str]:
    text = (
        f"*kiocheck review completed*\n"
        f"<{values['pr_url']}|{values['repo']} PR #{values['pr']}> · {values['mode']} · `{values['head_sha']}`"
    )
    try:
        response = requests.post(config.slack_webhook_url, json={"text": text}, timeout=15)
        response.raise_for_status()
        return {"channel": "slack", "status": "sent", "detail": "incoming webhook"}
    except requests.RequestException as exc:
        logging.exception("kio Slack notification failed")
        return {"channel": "slack", "status": "failed", "detail": str(exc)}


def _template_values(item: WorkItem, *, run_dir: Path) -> dict[str, str]:
    pr = item.pull_request
    return {
        "repo": pr.repo_full_name,
        "pr": str(pr.number),
        "pr_url": pr.html_url or f"https://github.com/{pr.repo_full_name}/pull/{pr.number}",
        "head_sha": pr.head_sha,
        "mode": item.mode.replace("level-", "Level "),
        "run_dir": str(run_dir),
    }


def _render_template(path: Path, fallback: str, values: dict[str, str]) -> str:
    template = fallback
    if path.exists():
        template = path.read_text(encoding="utf-8")
    try:
        return template.format(**values)
    except KeyError as exc:
        raise ValueError(f"Template {path} contains an unknown placeholder: {exc.args[0]}") from exc
