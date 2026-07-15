from pathlib import Path

import yaml


def test_kio_slack_ingress_routes_only_to_the_private_node_listener():
    manifest = Path("deploy/kubernetes/kio-slack-ingress.yaml").read_text()

    assert "kio.dreambau.com" in manifest
    assert "10.42.0.1" in manifest
    assert "port: 8876" in manifest
    assert "cert-manager.io/cluster-issuer: letsencrypt-prod" in manifest
    assert "type: ClusterIP" in manifest


def test_preview_service_uses_runtime_secrets_and_private_node_address():
    unit = Path("deploy/systemd/kio-slack-preview.service").read_text()

    assert "EnvironmentFile=/etc/kio/kio.env" in unit
    assert "--host 10.42.0.1" in unit
    assert "--port 8876" in unit
    assert "WorkingDirectory=/opt/kio-slack-preview" in unit
    assert "User=kio" in unit


def test_slack_app_manifest_requests_only_the_bug_intake_contract():
    manifest = yaml.safe_load(Path("deploy/slack/kio-bugfix-app.yaml").read_text())

    assert manifest["display_information"]["name"] == "Kio Bugfix"
    assert manifest["oauth_config"]["scopes"]["bot"] == [
        "channels:history",
        "chat:write",
        "files:read",
    ]
    assert manifest["settings"]["event_subscriptions"] == {
        "request_url": "https://kio.dreambau.com/webhooks/slack",
        "bot_events": ["message.channels"],
    }
    assert manifest["settings"]["socket_mode_enabled"] is False
