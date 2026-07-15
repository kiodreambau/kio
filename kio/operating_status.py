"""Secret-safe aggregate operating status for the bug intake pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .bug_artifacts import RETENTION_SECONDS
from .bug_delivery import _replace_private_json
from .config import KioConfig


def bug_intake_status(config: KioConfig) -> dict[str, Any]:
    intakes = _records(config.slack_intake_dir, "*.json")
    repairs = _records(config.repair_queue_dir, "repair-*.json")
    artifacts = _records(config.bug_artifact_dir, "**/*.json")
    repair_counts = {
        state: sum(record.get("status") == state for record in repairs)
        for state in ("queued", "claimed", "completed", "failed")
    }
    blocked = sum(record.get("delivery_state") == "blocked" for record in intakes)
    failed = repair_counts["failed"]
    return {
        "state": "degraded" if blocked or failed else "healthy",
        "intakes": {
            "total": len(intakes),
            "blocked": blocked,
            "issues_created": sum(bool(record.get("issue_number")) for record in intakes),
        },
        "repairs": repair_counts,
        "artifacts": {
            "count": len(artifacts),
            "retention_days": RETENTION_SECONDS // (24 * 60 * 60),
        },
    }


def record_delivery_state(record_path: Path, *, state: str, now: int) -> None:
    """Persist a bounded state marker without retaining exception details."""
    if state not in {"delivered", "blocked"}:
        raise ValueError("delivery state must be delivered or blocked")
    value = json.loads(record_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("bug intake record must be an object")
    value["delivery_state"] = state
    value["delivery_state_at"] = int(now)
    _replace_private_json(record_path, value)


def _records(root: Path, pattern: str) -> list[dict[str, Any]]:
    if not root.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for path in root.glob(pattern):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(value, dict):
            records.append(value)
    return records
