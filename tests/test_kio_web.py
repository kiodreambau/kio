import hashlib
import hmac
import json
import time
from unittest.mock import Mock

from fastapi.testclient import TestClient

from kio.config import KioConfig
from kio.run_store import RunSummary
from kio.web import create_app, public_config, render_dashboard


def test_public_config_does_not_expose_runtime_secrets(tmp_path):
    cfg = KioConfig(
        workspace=tmp_path,
        github_token="secret",
        smtp_password="mail-secret",
        slack_webhook_url="https://hooks.slack.test/secret",
    )

    data = public_config(cfg)

    assert data["github_token_configured"] is True
    assert data["webhook_configured"] is False
    assert data["webhook_dry_run"] is False
    assert "secret" not in str(data)
    assert "mail-secret" not in str(data)
    assert "github_token" not in data
    assert "smtp_password" not in data
    assert "slack_webhook_url" not in data


def test_public_config_requires_smtp_credentials_for_email_status(tmp_path):
    cfg = KioConfig(
        workspace=tmp_path,
        notification_email_to=("owner@dreambau.com",),
        notification_email_from="kiocheck@dreambau.com",
        smtp_host="mail.dreambau.com",
    )

    assert public_config(cfg)["email_notifications_configured"] is False


def test_dashboard_renders_codex_like_controls(tmp_path):
    cfg = KioConfig(workspace=tmp_path, repos=("owner/repo",), backend="gito")
    html = render_dashboard(
        cfg,
        [
            RunSummary(
                repo="owner/repo",
                pr=7,
                head_sha="abcdef123456",
                mode="stability",
                source="comment",
                status="completed",
                run_dir=str(tmp_path / "runs" / "owner__repo" / "pr-7"),
                updated_at=1.0,
                backend="gito",
            )
        ],
    )

    assert "toolbar" in html
    assert "segmented" in html
    assert 'data-filter="completed"' in html
    assert 'data-status="completed"' in html
    assert "owner/repo" in html
    assert "stability" in html
    assert "abcdef12" in html
    assert "reviewer @kiodreambau" in html
    assert "label kio:1–4" in html


def test_slack_events_endpoint_verifies_and_accepts_a_bug_report(tmp_path):
    secret = "runtime-signing-secret"
    timestamp = str(int(time.time()))
    payload = {
        "event_id": "Ev-web-1",
        "event": {
            "type": "message",
            "channel": "C-BUGFIX",
            "user": "U-REPORTER",
            "ts": f"{timestamp}.000100",
            "text": "The login is broken",
        },
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = (
        "v0="
        + hmac.new(secret.encode(), f"v0:{timestamp}:".encode() + body, hashlib.sha256).hexdigest()
    )
    cfg = KioConfig(
        workspace=tmp_path,
        slack_signing_secret=secret,
        slack_bug_channel="C-BUGFIX",
    )

    response = TestClient(create_app(cfg)).post(
        "/webhooks/slack",
        content=body,
        headers={
            "x-slack-request-timestamp": timestamp,
            "x-slack-signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "accepted": True,
        "duplicate": False,
        "intake_id": f"C-BUGFIX-{timestamp}.000100",
        "trigger_fix": False,
    }


def test_slack_events_endpoint_completes_signed_url_verification(tmp_path):
    secret = "runtime-signing-secret"
    timestamp = str(int(time.time()))
    body = json.dumps(
        {"type": "url_verification", "challenge": "safe-challenge"},
        separators=(",", ":"),
    ).encode()
    signature = (
        "v0="
        + hmac.new(secret.encode(), f"v0:{timestamp}:".encode() + body, hashlib.sha256).hexdigest()
    )
    cfg = KioConfig(
        workspace=tmp_path,
        slack_signing_secret=secret,
        slack_bug_channel="C-BUGFIX",
    )

    response = TestClient(create_app(cfg)).post(
        "/webhooks/slack",
        content=body,
        headers={
            "x-slack-request-timestamp": timestamp,
            "x-slack-signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"challenge": "safe-challenge"}


def test_slack_bug_delivery_is_queued_only_when_runtime_config_is_complete(tmp_path):
    secret = "runtime-signing-secret"
    timestamp = str(int(time.time()))
    body = json.dumps(
        {
            "event_id": "Ev-delivery-1",
            "event": {
                "type": "message",
                "channel": "C-BUGFIX",
                "user": "U-REPORTER",
                "ts": f"{timestamp}.000200",
                "text": "The login is broken",
            },
        },
        separators=(",", ":"),
    ).encode()
    signature = (
        "v0="
        + hmac.new(secret.encode(), f"v0:{timestamp}:".encode() + body, hashlib.sha256).hexdigest()
    )
    processor = Mock()
    cfg = KioConfig(
        workspace=tmp_path,
        github_token="github-token",
        slack_signing_secret=secret,
        slack_bot_token="slack-token",
        slack_bot_user_id="U-KIO",
        slack_bug_channel="C-BUGFIX",
        slack_bug_repo="OpenResilienceInitiative/ORISO-Status",
    )

    response = TestClient(create_app(cfg, slack_processor=processor)).post(
        "/webhooks/slack",
        content=body,
        headers={
            "x-slack-request-timestamp": timestamp,
            "x-slack-signature": signature,
        },
    )

    assert response.status_code == 200
    processor.assert_called_once_with(cfg, f"C-BUGFIX-{timestamp}.000200")
