import json
from unittest.mock import Mock

from kio.bug_intake_service import process_slack_bug


def test_processes_screenshot_then_delivers_one_issue(tmp_path):
    state_root = tmp_path / "state"
    state_root.mkdir()
    record_path = state_root / "C-BUGFIX-123.456.json"
    record_path.write_text(
        json.dumps(
            {
                "intake_id": "C-BUGFIX-123.456",
                "channel": "C-BUGFIX",
                "root_ts": "123.456",
                "reporter": "U-REPORTER",
                "text": "The login loops",
                "files": [
                    {
                        "name": "screen.png",
                        "mimetype": "image/png",
                        "url_private": "https://files.slack.com/files-pri/T/F/screen.png",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    slack = Mock()
    slack.download_file.return_value = (b"\x89PNG\r\n\x1a\nimage", "image/png")
    github = Mock()
    github.create_issue.return_value = {
        "number": 183,
        "url": "https://github.com/OpenResilienceInitiative/ORISO-Status/issues/183",
    }
    repair = Mock()

    result = process_slack_bug(
        record_path=record_path,
        artifact_root=tmp_path / "artifacts",
        repo="OpenResilienceInitiative/ORISO-Status",
        slack=slack,
        github=github,
        repair=repair,
        now=1_784_111_200,
    )

    assert result["issue_number"] == 183
    record = json.loads(record_path.read_text())
    assert "files" not in record
    assert len(record["artifacts"]) == 1
    assert "url_private" not in str(record)
    assert (tmp_path / "artifacts" / record["artifacts"][0]["relative_path"]).exists()
