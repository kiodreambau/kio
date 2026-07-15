"""Auditable delivery of normalized bug intake records."""

from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

import fcntl

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
        artifacts: tuple[dict[str, Any], ...] = (),
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
            "artifacts": [
                {
                    "artifact_id": str(artifact["artifact_id"]),
                    "media_type": str(artifact["media_type"]),
                    "relative_path": str(artifact["relative_path"]),
                }
                for artifact in artifacts
            ],
        }
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, separators=(",", ":"), sort_keys=True)
            handle.write("\n")
        return job_id

    def claim(self, *, worker_id: str) -> dict[str, Any] | None:
        """Atomically lease the oldest queued job to one named worker."""
        if not worker_id.strip():
            raise ValueError("worker_id is required")
        self.queue_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.queue_root, 0o700)
        with self._lock():
            for path in sorted(self.queue_root.glob("repair-*.json")):
                value = json.loads(path.read_text(encoding="utf-8"))
                if value.get("status") != "queued":
                    continue
                lease_token = str(uuid4())
                value["status"] = "claimed"
                value["worker_id"] = worker_id.strip()
                value["lease_hash"] = _lease_hash(lease_token)
                _replace_private_json(path, value)
                public_value = {
                    key: item
                    for key, item in value.items()
                    if key not in {"lease_hash", "artifacts"}
                }
                public_value["artifacts"] = [
                    {
                        "artifact_id": artifact["artifact_id"],
                        "media_type": artifact["media_type"],
                    }
                    for artifact in value.get("artifacts", [])
                ]
                return public_value | {"lease_token": lease_token}
        return None

    def complete(
        self,
        *,
        job_id: str,
        lease_token: str,
        status: str,
        result_url: str,
        summary: str,
    ) -> dict[str, Any]:
        """Finish a leased job without retaining the bearer lease."""
        if status not in {"completed", "failed"}:
            raise ValueError("repair job status must be completed or failed")
        safe_job_id = SAFE_ID.sub("-", job_id).strip("-")
        path = self.queue_root / f"{safe_job_id}.json"
        with self._lock():
            if not path.exists():
                raise ValueError("repair job not found")
            value = json.loads(path.read_text(encoding="utf-8"))
            expected = str(value.get("lease_hash") or "")
            if not expected or not _constant_time_equal(expected, _lease_hash(lease_token)):
                raise ValueError("invalid repair job lease")
            value.pop("lease_hash", None)
            value["status"] = status
            value["result_url"] = result_url
            value["summary"] = summary
            _replace_private_json(path, value)
            return value

    def artifact(
        self,
        *,
        job_id: str,
        artifact_id: str,
        lease_token: str,
        artifact_root: Path,
    ) -> tuple[Path, str]:
        """Resolve one leased private artifact without accepting filesystem input."""
        if not re.fullmatch(r"[a-f0-9]{32}", artifact_id):
            raise ValueError("invalid repair artifact id")
        safe_job_id = SAFE_ID.sub("-", job_id).strip("-")
        path = self.queue_root / f"{safe_job_id}.json"
        with self._lock():
            if not path.exists():
                raise ValueError("repair job not found")
            value = json.loads(path.read_text(encoding="utf-8"))
            expected = str(value.get("lease_hash") or "")
            if not expected or not _constant_time_equal(expected, _lease_hash(lease_token)):
                raise ValueError("invalid repair job lease")
            artifact = next(
                (
                    item
                    for item in value.get("artifacts", [])
                    if item.get("artifact_id") == artifact_id
                ),
                None,
            )
            if artifact is None:
                raise ValueError("repair artifact not found")
            root = artifact_root.resolve()
            artifact_path = (root / str(artifact["relative_path"])).resolve()
            if root not in artifact_path.parents or not artifact_path.is_file():
                raise ValueError("repair artifact path is invalid")
            return artifact_path, str(artifact["media_type"])

    def _lock(self):
        lock_path = self.queue_root / ".queue.lock"
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        handle = os.fdopen(descriptor, "r+")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return handle


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
            artifacts=tuple(record.get("artifacts") or ()),
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


def _lease_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _constant_time_equal(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left, right)
