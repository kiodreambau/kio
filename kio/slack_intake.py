"""Signed, idempotent Slack bug intake."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import time
from typing import Any

MAX_REQUEST_AGE_SECONDS = 60 * 5
SAFE_ID = re.compile(r"[^A-Za-z0-9._-]+")


class SlackIntakeError(ValueError):
    """A Slack event failed the public intake contract."""


def accept_slack_event(
    *,
    raw_body: bytes,
    timestamp: str,
    signature: str,
    signing_secret: str,
    allowed_channel: str,
    bot_user_id: str = "",
    state_root: Path,
    now: int | None = None,
) -> dict[str, Any]:
    """Verify and persist one Slack message event without external delivery."""
    current_time = int(time.time() if now is None else now)
    _verify_signature(raw_body, timestamp, signature, signing_secret, current_time)
    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, TypeError) as exc:
        raise SlackIntakeError("invalid Slack event payload") from exc
    if payload.get("type") == "url_verification":
        challenge = str(payload.get("challenge") or "")
        if not challenge:
            raise SlackIntakeError("Slack verification challenge is missing")
        return {"challenge": challenge}
    try:
        event = payload["event"]
    except (KeyError, TypeError) as exc:
        raise SlackIntakeError("invalid Slack event payload") from exc
    if event.get("type") != "message" or event.get("subtype"):
        raise SlackIntakeError("unsupported Slack event")
    if event.get("channel") != allowed_channel:
        raise SlackIntakeError("Slack channel is not allowed")

    root_ts = str(event.get("thread_ts") or event.get("ts") or "")
    channel = str(event.get("channel") or "")
    if not root_ts or not channel:
        raise SlackIntakeError("Slack event is missing its root message")
    intake_id = _safe_id(f"{channel}-{root_ts}")
    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(state_root, 0o700)
    event_id = str(payload.get("event_id") or "")
    if not event_id:
        raise SlackIntakeError("Slack event is missing its event id")
    event_path = state_root / f".event-{_safe_id(event_id)}"
    try:
        event_descriptor = os.open(event_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        original_intake_id = event_path.read_text(encoding="utf-8").strip()
        return {
            "accepted": True,
            "duplicate": True,
            "intake_id": original_intake_id,
            "trigger_fix": False,
        }
    with os.fdopen(event_descriptor, "w", encoding="utf-8") as handle:
        handle.write(f"{intake_id}\n")
    record_path = state_root / f"{intake_id}.json"
    if record_path.exists():
        return {
            "accepted": True,
            "duplicate": True,
            "intake_id": intake_id,
            "trigger_fix": False,
        }

    record = {
        "event_id": event_id,
        "intake_id": intake_id,
        "channel": channel,
        "root_ts": root_ts,
        "reporter": str(event.get("user") or ""),
        "text": str(event.get("text") or ""),
        "files": list(event.get("files") or []),
        "received_at": current_time,
        "trigger_fix": _is_fix_trigger(str(event.get("text") or ""), bot_user_id),
    }
    descriptor = os.open(record_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(record, handle, separators=(",", ":"), sort_keys=True)
        handle.write("\n")
    return {
        "accepted": True,
        "duplicate": False,
        "intake_id": intake_id,
        "trigger_fix": record["trigger_fix"],
    }


def _verify_signature(
    raw_body: bytes,
    timestamp: str,
    signature: str,
    signing_secret: str,
    now: int,
) -> None:
    if not signing_secret:
        raise SlackIntakeError("Slack signing secret is not configured")
    try:
        request_time = int(timestamp)
    except ValueError as exc:
        raise SlackIntakeError("invalid Slack timestamp") from exc
    if abs(now - request_time) > MAX_REQUEST_AGE_SECONDS:
        raise SlackIntakeError("stale Slack request")
    base = f"v0:{timestamp}:".encode() + raw_body
    expected = "v0=" + hmac.new(signing_secret.encode(), base, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise SlackIntakeError("invalid Slack signature")


def _safe_id(value: str) -> str:
    result = SAFE_ID.sub("-", value).strip("-")
    if not result:
        raise SlackIntakeError("Slack event does not have a usable intake id")
    return result


def _is_fix_trigger(text: str, bot_user_id: str) -> bool:
    if not bot_user_id:
        return False
    return bool(re.search(rf"<@{re.escape(bot_user_id)}>\s+fix\b", text, re.IGNORECASE))
