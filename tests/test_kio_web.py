from kio.config import KioConfig
from kio.run_store import RunSummary
from kio.web import public_config, render_dashboard


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
