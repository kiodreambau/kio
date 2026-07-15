from pathlib import Path


def test_kio_slack_ingress_routes_only_to_the_private_node_listener():
    manifest = Path("deploy/kubernetes/kio-slack-ingress.yaml").read_text()

    assert "kio.dreambau.com" in manifest
    assert "10.42.0.1" in manifest
    assert "port: 8766" in manifest
    assert "cert-manager.io/cluster-issuer: letsencrypt-prod" in manifest
    assert "type: ClusterIP" in manifest


def test_preview_service_uses_runtime_secrets_and_private_node_address():
    unit = Path("deploy/systemd/kio-slack-preview.service").read_text()

    assert "EnvironmentFile=/etc/kio/kio.env" in unit
    assert "--host 10.42.0.1" in unit
    assert "--port 8766" in unit
    assert "WorkingDirectory=/opt/kio-slack-preview" in unit
    assert "User=kio" in unit
