import json

from kio.config import KioConfig
from kio.models import BackendResult, PullRequestContext, WorkItem
from kio.notifications import notify_review_completed, write_codex_handoff


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.login_args = None
        self.message = None
        self.quit_called = False
        self.__class__.instances.append(self)

    def starttls(self, *, context):
        self.started_tls = True

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, message):
        self.message = message

    def quit(self):
        self.quit_called = True


def _item():
    return WorkItem(
        pull_request=PullRequestContext(
            repo_full_name="owner/repo",
            number=7,
            head_sha="abc123",
            head_ref="feature",
            base_ref="main",
            clone_url="https://github.com/owner/repo.git",
            html_url="https://github.com/owner/repo/pull/7",
        ),
        source="reviewer_request",
        mode="level-4",
    )


def _result(tmp_path):
    return BackendResult(
        backend="local",
        returncode=0,
        command="local-review",
        output_file=tmp_path / "output.log",
        report_file=tmp_path / "review-comment.md",
    )


def test_email_notification_and_codex_handoff_are_written_without_secrets_in_files(
    tmp_path, mocker
):
    FakeSMTP.instances = []
    mocker.patch("kio.notifications.smtplib.SMTP", FakeSMTP)
    config = KioConfig(
        notification_email_to=("owner@dreambau.com",),
        notification_email_from="kiocheck@dreambau.com",
        smtp_host="mail.dreambau.com",
        smtp_port=587,
        smtp_username="kiocheck@dreambau.com",
        smtp_password="runtime-only",
    )
    handoff = write_codex_handoff(_item(), config=config, run_dir=tmp_path)

    deliveries = notify_review_completed(
        _item(),
        config=config,
        run_dir=tmp_path,
        result=_result(tmp_path),
        handoff_file=handoff,
    )

    assert "PR #7" in handoff.read_text(encoding="utf-8")
    assert deliveries == [{"channel": "email", "status": "sent", "detail": "1"}]
    assert FakeSMTP.instances[0].started_tls is True
    assert FakeSMTP.instances[0].login_args == ("kiocheck@dreambau.com", "runtime-only")
    assert "https://github.com/owner/repo/pull/7" in FakeSMTP.instances[0].message.get_content()
    assert FakeSMTP.instances[0].quit_called is True
    recorded = json.loads((tmp_path / "notifications.json").read_text(encoding="utf-8"))
    assert recorded["deliveries"] == deliveries


def test_notification_records_incomplete_email_configuration_as_skipped(tmp_path):
    handoff = write_codex_handoff(_item(), config=KioConfig(), run_dir=tmp_path)

    deliveries = notify_review_completed(
        _item(),
        config=KioConfig(notification_email_to=("owner@dreambau.com",)),
        run_dir=tmp_path,
        result=_result(tmp_path),
        handoff_file=handoff,
    )

    assert deliveries == [
        {
            "channel": "email",
            "status": "skipped",
            "detail": "missing notification_email_from, smtp_host, smtp_username, smtp_password",
        }
    ]


def test_notification_requires_runtime_smtp_credentials(tmp_path):
    config = KioConfig(
        notification_email_to=("owner@dreambau.com",),
        notification_email_from="kiocheck@dreambau.com",
        smtp_host="mail.dreambau.com",
    )
    handoff = write_codex_handoff(_item(), config=config, run_dir=tmp_path)

    deliveries = notify_review_completed(
        _item(),
        config=config,
        run_dir=tmp_path,
        result=_result(tmp_path),
        handoff_file=handoff,
    )

    assert deliveries == [
        {
            "channel": "email",
            "status": "skipped",
            "detail": "missing smtp_username, smtp_password",
        }
    ]


def test_slack_notification_uses_an_outgoing_webhook(tmp_path, mocker):
    response = mocker.Mock()
    response.raise_for_status.return_value = None
    post = mocker.patch("kio.notifications.requests.post", return_value=response)
    config = KioConfig(slack_webhook_url="https://hooks.slack.test/services/abc")
    handoff = write_codex_handoff(_item(), config=config, run_dir=tmp_path)

    deliveries = notify_review_completed(
        _item(),
        config=config,
        run_dir=tmp_path,
        result=_result(tmp_path),
        handoff_file=handoff,
    )

    assert deliveries == [{"channel": "slack", "status": "sent", "detail": "incoming webhook"}]
    assert post.call_args.kwargs["json"]["text"].startswith("*kiocheck review completed*")
