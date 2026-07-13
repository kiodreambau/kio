from kio import config as config_module


def test_sensitive_notification_values_are_runtime_only(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        "\n".join(
            [
                'smtp_username = "committed-user"',
                'smtp_password = "committed-password"',
                'slack_webhook_url = "https://hooks.slack.test/committed"',
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

    monkeypatch.setenv("KIO_SMTP_USERNAME", "runtime-user")
    monkeypatch.setenv("KIO_SMTP_PASSWORD", "runtime-password")
    monkeypatch.setenv("KIO_SLACK_WEBHOOK_URL", "https://hooks.slack.test/runtime")

    cfg = config_module.load_config()

    assert cfg.smtp_username == "runtime-user"
    assert cfg.smtp_password == "runtime-password"
    assert cfg.slack_webhook_url == "https://hooks.slack.test/runtime"
