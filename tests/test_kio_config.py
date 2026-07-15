from kio import config as config_module


def test_sensitive_notification_values_are_runtime_only(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        "\n".join(
            [
                'smtp_username = "committed-user"',
                'smtp_password = "committed-password"',
                'slack_webhook_url = "https://hooks.slack.test/committed"',
                'slack_signing_secret = "committed-signing-secret"',
                'slack_bot_token = "committed-bot-token"',
                'repair_worker_token = "committed-worker-token"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "_candidate_files", lambda _config_file: [config_file])

    cfg = config_module.load_config()

    assert cfg.smtp_username == ""
    assert cfg.smtp_password == ""
    assert cfg.slack_webhook_url == ""
    assert cfg.slack_signing_secret == ""
    assert cfg.slack_bot_token == ""
    assert cfg.repair_worker_token == ""

    monkeypatch.setenv("KIO_SMTP_USERNAME", "runtime-user")
    monkeypatch.setenv("KIO_SMTP_PASSWORD", "runtime-password")
    monkeypatch.setenv("KIO_SLACK_WEBHOOK_URL", "https://hooks.slack.test/runtime")
    monkeypatch.setenv("KIO_SLACK_SIGNING_SECRET", "runtime-signing-secret")
    monkeypatch.setenv("KIO_SLACK_BOT_TOKEN", "runtime-bot-token")
    monkeypatch.setenv("KIO_REPAIR_WORKER_TOKEN", "runtime-worker-token")

    cfg = config_module.load_config()

    assert cfg.smtp_username == "runtime-user"
    assert cfg.smtp_password == "runtime-password"
    assert cfg.slack_webhook_url == "https://hooks.slack.test/runtime"
    assert cfg.slack_signing_secret == "runtime-signing-secret"
    assert cfg.slack_bot_token == "runtime-bot-token"
    assert cfg.repair_worker_token == "runtime-worker-token"


def test_repair_worker_nonsecret_routing_loads_from_toml(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        "\n".join(
            [
                'repair_api_url = "https://kio.dreambau.com"',
                'repair_worker_id = "kio-mac-mini"',
                "[repair_repos]",
                '"owner/repo" = "/Users/kio/Projects/repo"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "_candidate_files", lambda _config_file: [config_file])

    cfg = config_module.load_config()

    assert cfg.repair_api_url == "https://kio.dreambau.com"
    assert cfg.repair_worker_id == "kio-mac-mini"
    assert cfg.repair_repos == {"owner/repo": "/Users/kio/Projects/repo"}
