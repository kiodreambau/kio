import json

import pytest

from kio.bug_artifacts import BugArtifactError, store_bug_artifact


def test_stores_an_allowed_png_privately_with_retention_metadata(tmp_path):
    result = store_bug_artifact(
        content=b"\x89PNG\r\n\x1a\nsynthetic",
        filename="screenshot.png",
        media_type="image/png",
        intake_id="C-BUGFIX-123.456",
        artifact_root=tmp_path,
        now=1_784_111_200,
    )

    artifact_path = tmp_path / result["relative_path"]
    assert artifact_path.exists()
    assert artifact_path.name != "screenshot.png"
    assert artifact_path.stat().st_mode & 0o777 == 0o600
    assert result["media_type"] == "image/png"
    assert result["size"] == len(b"\x89PNG\r\n\x1a\nsynthetic")
    assert result["expires_at"] == 1_789_295_200
    metadata = json.loads(artifact_path.with_suffix(".json").read_text())
    assert metadata["intake_id"] == "C-BUGFIX-123.456"
    assert "content" not in metadata


def test_rejects_a_spoofed_image_media_type(tmp_path):
    with pytest.raises(BugArtifactError, match="content does not match"):
        store_bug_artifact(
            content=b"<html>not an image</html>",
            filename="screenshot.png",
            media_type="image/png",
            intake_id="C-BUGFIX-123.456",
            artifact_root=tmp_path,
            now=1_784_111_200,
        )

    assert list(tmp_path.rglob("*")) == []
