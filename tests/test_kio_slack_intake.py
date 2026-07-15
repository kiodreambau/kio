import hashlib
import hmac
import json

from kio.slack_intake import accept_slack_event


def _signed(body: bytes, timestamp: int, secret: str) -> str:
    value = f"v0:{timestamp}:".encode() + body
    return "v0=" + hmac.new(secret.encode(), value, hashlib.sha256).hexdigest()


def test_accepts_a_signed_top_level_bug_report_once(tmp_path):
    secret = "runtime-only-signing-secret"
    timestamp = 1_784_111_200
    body = json.dumps(
        {
            "event_id": "Ev-1",
            "event": {
                "type": "message",
                "channel": "C-BUGFIX",
                "user": "U-REPORTER",
                "ts": "1784111200.000100",
                "text": "The consultant login loops back to the form",
                "files": [],
            },
        },
        separators=(",", ":"),
    ).encode()

    result = accept_slack_event(
        raw_body=body,
        timestamp=str(timestamp),
        signature=_signed(body, timestamp, secret),
        signing_secret=secret,
        allowed_channel="C-BUGFIX",
        state_root=tmp_path,
        now=timestamp,
    )

    assert result == {
        "accepted": True,
        "duplicate": False,
        "intake_id": "C-BUGFIX-1784111200.000100",
        "trigger_fix": False,
    }
    record = json.loads((tmp_path / "C-BUGFIX-1784111200.000100.json").read_text())
    assert record["event_id"] == "Ev-1"
    assert record["reporter"] == "U-REPORTER"
    assert record["text"] == "The consultant login loops back to the form"
    assert secret not in str(record)


def test_replayed_event_id_does_not_create_a_second_intake(tmp_path):
    secret = "runtime-only-signing-secret"
    timestamp = 1_784_111_200

    def send(root_ts: str):
        body = json.dumps(
            {
                "event_id": "Ev-replayed",
                "event": {
                    "type": "message",
                    "channel": "C-BUGFIX",
                    "user": "U-REPORTER",
                    "ts": root_ts,
                    "text": "Broken login",
                },
            },
            separators=(",", ":"),
        ).encode()
        return accept_slack_event(
            raw_body=body,
            timestamp=str(timestamp),
            signature=_signed(body, timestamp, secret),
            signing_secret=secret,
            allowed_channel="C-BUGFIX",
            state_root=tmp_path,
            now=timestamp,
        )

    first = send("1784111200.000100")
    replay = send("1784111201.000200")

    assert first["duplicate"] is False
    assert replay == {**first, "duplicate": True}
    assert len(list(tmp_path.glob("C-BUGFIX-*.json"))) == 1


def test_explicit_kio_mention_marks_the_report_for_repair(tmp_path):
    secret = "runtime-only-signing-secret"
    timestamp = 1_784_111_200
    body = json.dumps(
        {
            "event_id": "Ev-fix",
            "event": {
                "type": "message",
                "channel": "C-BUGFIX",
                "user": "U-REPORTER",
                "ts": "1784111200.000300",
                "text": "<@U-KIO> fix the consultant login loop",
            },
        },
        separators=(",", ":"),
    ).encode()

    result = accept_slack_event(
        raw_body=body,
        timestamp=str(timestamp),
        signature=_signed(body, timestamp, secret),
        signing_secret=secret,
        allowed_channel="C-BUGFIX",
        bot_user_id="U-KIO",
        state_root=tmp_path,
        now=timestamp,
    )

    assert result["trigger_fix"] is True
