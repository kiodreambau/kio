import json
from unittest.mock import Mock

from kio.bug_delivery import FileRepairQueue, deliver_bug_intake


def test_normal_report_opens_one_issue_without_starting_a_repair(tmp_path):
    record_path = tmp_path / "C-BUGFIX-123.456.json"
    record_path.write_text(
        json.dumps(
            {
                "intake_id": "C-BUGFIX-123.456",
                "channel": "C-BUGFIX",
                "root_ts": "123.456",
                "reporter": "U-REPORTER",
                "text": "Consultant login loops back to the form",
                "files": [],
            }
        ),
        encoding="utf-8",
    )
    github = Mock()
    github.create_issue.return_value = {
        "number": 181,
        "url": "https://github.com/OpenResilienceInitiative/ORISO-Status/issues/181",
    }
    slack = Mock()
    repair = Mock()

    result = deliver_bug_intake(
        record_path=record_path,
        repo="OpenResilienceInitiative/ORISO-Status",
        github=github,
        slack=slack,
        repair=repair,
    )

    assert result["issue_number"] == 181
    github.create_issue.assert_called_once()
    assert github.create_issue.call_args.kwargs["title"] == (
        "Bug intake: Consultant login loops back to the form"
    )
    repair.queue.assert_not_called()
    slack.reply.assert_called_once_with(
        channel="C-BUGFIX",
        thread_ts="123.456",
        text="Bug accepted: https://github.com/OpenResilienceInitiative/ORISO-Status/issues/181",
    )

    deliver_bug_intake(
        record_path=record_path,
        repo="OpenResilienceInitiative/ORISO-Status",
        github=github,
        slack=slack,
        repair=repair,
    )
    github.create_issue.assert_called_once()


def test_explicit_fix_trigger_queues_one_bounded_repair(tmp_path):
    record_path = tmp_path / "C-BUGFIX-789.012.json"
    record_path.write_text(
        json.dumps(
            {
                "intake_id": "C-BUGFIX-789.012",
                "channel": "C-BUGFIX",
                "root_ts": "789.012",
                "reporter": "U-REPORTER",
                "text": "<@U-KIO> fix the consultant login loop",
                "files": [],
                "trigger_fix": True,
            }
        ),
        encoding="utf-8",
    )
    github = Mock()
    github.create_issue.return_value = {
        "number": 182,
        "url": "https://github.com/OpenResilienceInitiative/ORISO-Status/issues/182",
    }
    slack = Mock()
    repair = Mock()
    repair.queue.return_value = "repair-C-BUGFIX-789.012"

    result = deliver_bug_intake(
        record_path=record_path,
        repo="OpenResilienceInitiative/ORISO-Status",
        github=github,
        slack=slack,
        repair=repair,
    )

    assert result["repair_queued"] is True
    repair.queue.assert_called_once_with(
        intake_id="C-BUGFIX-789.012",
        repo="OpenResilienceInitiative/ORISO-Status",
        issue_number=182,
        issue_url="https://github.com/OpenResilienceInitiative/ORISO-Status/issues/182",
        instructions=(
            "Reproduce the reported behavior, add a failing regression test, "
            "implement the minimal fix, verify Pre-Dev, and open a human-reviewed PR. "
            "Do not force-push, merge, or promote to dev."
        ),
    )


def test_file_repair_queue_writes_a_private_idempotent_job(tmp_path):
    queue = FileRepairQueue(tmp_path)

    first = queue.queue(
        intake_id="C-BUGFIX-789.012",
        repo="OpenResilienceInitiative/ORISO-Status",
        issue_number=182,
        issue_url="https://github.com/OpenResilienceInitiative/ORISO-Status/issues/182",
        instructions="Write the failing regression test first.",
    )
    second = queue.queue(
        intake_id="C-BUGFIX-789.012",
        repo="OpenResilienceInitiative/ORISO-Status",
        issue_number=182,
        issue_url="https://github.com/OpenResilienceInitiative/ORISO-Status/issues/182",
        instructions="Write the failing regression test first.",
    )

    assert first == second == "repair-C-BUGFIX-789.012"
    job_path = tmp_path / "repair-C-BUGFIX-789.012.json"
    assert job_path.stat().st_mode & 0o777 == 0o600
    assert json.loads(job_path.read_text())["status"] == "queued"
    assert len(list(tmp_path.glob("*.json"))) == 1
