"""Application service joining Slack evidence to bug delivery."""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any

from .bug_artifacts import store_bug_artifact
from .bug_delivery import _replace_private_json, deliver_bug_intake


def process_slack_bug(
    *,
    record_path: Path,
    artifact_root: Path,
    repo: str,
    slack: Any,
    github: Any,
    repair: Any,
    now: int | None = None,
) -> dict[str, Any]:
    """Persist private screenshots, erase Slack URLs, and deliver the intake."""
    current_time = int(time.time() if now is None else now)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if "files" in record:
        artifacts = list(record.get("artifacts") or [])
        for file_record in record.get("files") or []:
            url = str(file_record.get("url_private") or "")
            declared_type = str(file_record.get("mimetype") or "")
            content, response_type = slack.download_file(url, max_bytes=10 * 1024 * 1024)
            if response_type and response_type != declared_type:
                raise ValueError("Slack file response media type does not match the event")
            artifacts.append(
                store_bug_artifact(
                    content=content,
                    filename=str(file_record.get("name") or "attachment"),
                    media_type=declared_type,
                    intake_id=str(record["intake_id"]),
                    artifact_root=artifact_root,
                    now=current_time,
                )
            )
        record["artifacts"] = artifacts
        record.pop("files", None)
        _replace_private_json(record_path, record)
    return deliver_bug_intake(
        record_path=record_path,
        repo=repo,
        github=github,
        slack=slack,
        repair=repair,
    )
