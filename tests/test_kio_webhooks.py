import pytest

from kio.config import KioConfig
from kio.models import PullRequestContext
from kio.webhooks import SignatureError, signed_body, verify_signature, webhook_work_item


class FakeGithub:
    def get_pull_request(self, repo_full_name, number):
        return PullRequestContext(
            repo_full_name=repo_full_name,
            number=number,
            head_sha="abc123",
            head_ref="feature",
            base_ref="main",
            clone_url="https://github.com/owner/repo.git",
            html_url=f"https://github.com/{repo_full_name}/pull/{number}",
        )


def test_verify_signature_accepts_valid_signature():
    body, signature = signed_body({"ok": True}, secret="secret")

    verify_signature(body, signature=signature, secret="secret")


def test_verify_signature_rejects_invalid_signature():
    body, _signature = signed_body({"ok": True}, secret="secret")

    with pytest.raises(SignatureError):
        verify_signature(body, signature="sha256=bad", secret="secret")


def test_issue_comment_webhook_builds_work_item():
    payload = {
        "action": "created",
        "repository": {"full_name": "owner/repo"},
        "issue": {"number": 5, "pull_request": {"url": "https://api.github.com/pr"}},
        "comment": {
            "id": 99,
            "body": "@kiocheck review 4",
            "user": {"login": "dev"},
        },
    }

    item = webhook_work_item(
        payload,
        event="issue_comment",
        config=KioConfig(),
        github=FakeGithub(),
    )

    assert item is not None
    assert item.pull_request.repo_full_name == "owner/repo"
    assert item.pull_request.number == 5
    assert item.mode == "level-4"
    assert item.comment_id == 99


def test_pull_request_review_requested_webhook_builds_work_item():
    payload = {
        "action": "review_requested",
        "requested_reviewer": {"login": "kiodreambau"},
        "repository": {
            "full_name": "owner/repo",
            "clone_url": "https://github.com/owner/repo.git",
        },
        "pull_request": {
            "number": 7,
            "html_url": "https://github.com/owner/repo/pull/7",
            "head": {"sha": "def456", "ref": "feature"},
            "base": {
                "ref": "main",
                "repo": {"clone_url": "https://github.com/owner/repo.git"},
            },
        },
    }

    item = webhook_work_item(payload, event="pull_request", config=KioConfig())

    assert item is not None
    assert item.pull_request.head_sha == "def456"
    assert item.mode == "level-1"
    assert item.source == "reviewer_request"


def test_webhook_ignores_unrelated_comment():
    payload = {
        "action": "created",
        "repository": {"full_name": "owner/repo"},
        "issue": {"number": 5, "pull_request": {}},
        "comment": {"body": "@someone review"},
    }

    assert (
        webhook_work_item(
            payload,
            event="issue_comment",
            config=KioConfig(),
            github=FakeGithub(),
        )
        is None
    )
