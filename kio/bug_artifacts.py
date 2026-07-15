"""Private evidence storage for Slack bug reports."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
from typing import Any

RETENTION_SECONDS = 60 * 24 * 60 * 60
ALLOWED_MEDIA_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
SAFE_ID = re.compile(r"[^A-Za-z0-9._-]+")


class BugArtifactError(ValueError):
    """An attachment failed the private artifact contract."""


def store_bug_artifact(
    *,
    content: bytes,
    filename: str,
    media_type: str,
    intake_id: str,
    artifact_root: Path,
    now: int,
    max_bytes: int = 10 * 1024 * 1024,
) -> dict[str, Any]:
    """Store an already-downloaded Slack image outside the public web root."""
    del filename  # Original names are intentionally not used as filesystem paths.
    suffix = ALLOWED_MEDIA_TYPES.get(media_type)
    if suffix is None:
        raise BugArtifactError("unsupported bug artifact media type")
    if not content or len(content) > max_bytes:
        raise BugArtifactError("bug artifact size is outside the allowed range")
    if not _matches_media_type(content, media_type):
        raise BugArtifactError("bug artifact content does not match its media type")

    safe_intake_id = SAFE_ID.sub("-", intake_id).strip("-")
    if not safe_intake_id:
        raise BugArtifactError("invalid bug intake id")
    intake_root = artifact_root / safe_intake_id
    intake_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(intake_root, 0o700)

    artifact_id = secrets.token_hex(16)
    artifact_path = intake_root / f"{artifact_id}{suffix}"
    _write_private(artifact_path, content)
    expires_at = now + RETENTION_SECONDS
    metadata = {
        "artifact_id": artifact_id,
        "intake_id": intake_id,
        "media_type": media_type,
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "expires_at": expires_at,
        "pinned": False,
    }
    metadata_path = artifact_path.with_suffix(".json")
    _write_private(
        metadata_path,
        (json.dumps(metadata, separators=(",", ":"), sort_keys=True) + "\n").encode(),
    )
    return {
        **metadata,
        "relative_path": str(artifact_path.relative_to(artifact_root)),
    }


def _write_private(path: Path, content: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)


def _matches_media_type(content: bytes, media_type: str) -> bool:
    if media_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if media_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if media_type == "image/gif":
        return content.startswith((b"GIF87a", b"GIF89a"))
    if media_type == "image/webp":
        return len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    return False
