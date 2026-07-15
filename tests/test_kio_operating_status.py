import json

from kio.config import KioConfig
from kio.operating_status import bug_intake_status, record_delivery_state


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_bug_intake_status_returns_aggregate_secret_safe_counts(tmp_path):
    cfg = KioConfig(workspace=tmp_path)
    _write_json(
        cfg.slack_intake_dir / "accepted.json",
        {
            "text": "private Slack report",
            "issue_number": 12,
            "issue_url": "https://github.com/owner/repo/issues/12",
            "repair_queued": True,
            "delivery_state": "delivered",
        },
    )
    _write_json(
        cfg.slack_intake_dir / "blocked.json",
        {
            "text": "another private report",
            "delivery_state": "blocked",
            "blocked_at": 123,
        },
    )
    _write_json(cfg.repair_queue_dir / "repair-a.json", {"status": "queued"})
    _write_json(cfg.repair_queue_dir / "repair-b.json", {"status": "claimed"})
    _write_json(cfg.repair_queue_dir / "repair-c.json", {"status": "completed"})
    _write_json(cfg.repair_queue_dir / "repair-d.json", {"status": "failed"})
    _write_json(
        cfg.bug_artifact_dir / "accepted" / "artifact.json",
        {"expires_at": 999, "sha256": "private"},
    )

    status = bug_intake_status(cfg)

    assert status == {
        "state": "degraded",
        "intakes": {"total": 2, "blocked": 1, "issues_created": 1},
        "repairs": {"queued": 1, "claimed": 1, "completed": 1, "failed": 1},
        "artifacts": {"count": 1, "retention_days": 60},
    }
    serialized = json.dumps(status)
    assert "private Slack report" not in serialized
    assert "github.com" not in serialized
    assert str(tmp_path) not in serialized


def test_bug_intake_status_ignores_malformed_private_records(tmp_path):
    cfg = KioConfig(workspace=tmp_path)
    cfg.slack_intake_dir.mkdir(parents=True)
    (cfg.slack_intake_dir / "broken.json").write_text("not-json", encoding="utf-8")
    cfg.repair_queue_dir.mkdir(parents=True)
    (cfg.repair_queue_dir / "repair-broken.json").write_text("[]", encoding="utf-8")

    status = bug_intake_status(cfg)

    assert status["state"] == "healthy"
    assert status["intakes"]["total"] == 0
    assert status["repairs"]["queued"] == 0


def test_record_delivery_state_persists_only_safe_state_and_timestamp(tmp_path):
    record_path = tmp_path / "intake.json"
    _write_json(record_path, {"text": "private detail"})

    record_delivery_state(record_path, state="blocked", now=456)

    value = json.loads(record_path.read_text(encoding="utf-8"))
    assert value["delivery_state"] == "blocked"
    assert value["delivery_state_at"] == 456
    assert "error" not in value
