"""Auditable delivery of normalized bug intake records."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any

REPAIR_INSTRUCTIONS = (
    "Reproduce the reported behavior, add a failing regression test, "
    "implement the minimal fix, verify Pre-Dev, and open a human-reviewed PR. "
    "Do not force-push, merge, or promote to dev."
)
SAFE_ID = re.compile(r"[^A-Za-z0-9._-]+")


class FileRepairQueue:
    """Private, idempotent handoff boundary for the repair worker."""

    def __init__(self, queue_root: Path):
        self.queue_root = queue_root

    def queue(
        self,
        *,
        intake_id: str,
        repo: str,
        issue_number: int,
        issue_url: str,
        instructions: str,
    ) -> str:
        safe_intake_id = SAFE_ID.sub("-", intake_id).strip("-")
        if not safe_intake_id:
            raise ValueError("invalid bug intake id")
        job_id = f"repair-{safe_intake_id}"
        self.queue_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.queue_root, 0o700)
        path = self.queue_root / f"{job_id}.json"
        if path.exists():
            return job_id
        value = {
            "job_id": job_id,
            "intake_id": intake_id,
            "repo": repo,
            "issue_number": issue_number,
            "issue_url": issue_url,
            "instructions": instructions,
            "status": "queued",
        }
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, separators=(",", ":"), sort_keys=True)
            handle.write("\n")
        return job_id


def deliver_bug_intake(
    *,
    record_path: Path,
    repo: str,
    github: Any,
    slack: Any,
    repair: Any,
) -> dict[str, Any]:
    """Open/link one issue and optionally queue an explicitly requested repair."""
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if not (record.get("issue_number") and record.get("issue_url")):
        text = " ".join(str(record.get("text") or "Bug report").split())
        title = f"Bug intake: {text[:100]}"
        issue = github.create_issue(
            repo=repo,
            title=title,
            body=_issue_body(record),
            labels=("bug", "needs-triage", "source:slack"),
        )
        record["repo"] = repo
        record["issue_number"] = int(issue["number"])
        record["issue_url"] = str(issue["url"])
        record["repair_queued"] = False
        _replace_private_json(record_path, record)
        slack.reply(
            channel=str(record["channel"]),
            thread_ts=str(record["root_ts"]),
            text=f"Bug accepted: {record['issue_url']}",
        )

    if record.get("trigger_fix") and not record.get("repair_queued"):
        repair.queue(
            intake_id=str(record["intake_id"]),
            repo=repo,
            issue_number=int(record["issue_number"]),
            issue_url=str(record["issue_url"]),
            instructions=REPAIR_INSTRUCTIONS,
        )
        record["repair_queued"] = True
        _replace_private_json(record_path, record)
        slack.reply(
            channel=str(record["channel"]),
            thread_ts=str(record["root_ts"]),
            text="Kio repair queued. The result will stop at a human-reviewed PR.",
        )
    return {
        "issue_number": record["issue_number"],
        "issue_url": record["issue_url"],
        "repair_queued": bool(record.get("repair_queued")),
    }


def _issue_body(record: dict[str, Any]) -> str:
    return "\n".join(
        [
            "## Report",
            str(record.get("text") or "No description supplied."),
            "",
            "## Intake",
            f"- Slack channel: `{record.get('channel', '')}`",
            f"- Root message: `{record.get('root_ts', '')}`",
            f"- Reporter: `{record.get('reporter', '')}`",
            f"- Private artifacts: {len(record.get('artifacts') or record.get('files') or [])}",
            "",
            "Private screenshots remain in the Dreambau artifact store.",
        ]
    )


def _replace_private_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(value, handle, separators=(",", ":"), sort_keys=True)
        handle.write("\n")
    os.replace(temporary, path)
    os.chmod(path, 0o600)
