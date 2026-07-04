"""GitHub webhook parsing for local kio review triggers."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from .config import KioConfig
from .github import GithubClient
from .models import PullRequestContext, WorkItem
from .triggers import parse_review_comment, trigger_from_reviewer_request


class SignatureError(ValueError):
    """Raised when a webhook signature is missing or invalid."""


def verify_signature(body: bytes, *, signature: str, secret: str) -> None:
    if not secret:
        return
    if not signature:
        raise SignatureError("Missing X-Hub-Signature-256 header.")
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise SignatureError("Invalid webhook signature.")


def webhook_work_item(
    payload: dict[str, Any],
    *,
    event: str,
    config: KioConfig,
    github: GithubClient | None = None,
) -> WorkItem | None:
    if event == "issue_comment":
        return _issue_comment_work_item(payload, config=config, github=github)
    if event == "pull_request":
        return _pull_request_work_item(payload, config=config)
    return None


def _issue_comment_work_item(
    payload: dict[str, Any],
    *,
    config: KioConfig,
    github: GithubClient | None = None,
) -> WorkItem | None:
    if payload.get("action") != "created":
        return None
    issue = payload.get("issue") or {}
    if "pull_request" not in issue:
        return None
    comment = payload.get("comment") or {}
    trigger = parse_review_comment(
        comment.get("body", ""),
        bot_login=config.bot_login,
        allow_thermonuclear=config.allow_thermonuclear,
        comment_id=comment.get("id"),
        author=(comment.get("user") or {}).get("login"),
    )
    if not trigger:
        return None
    repo = _repo_name(payload)
    if not repo:
        raise ValueError("Webhook payload is missing repository.full_name.")
    client = github or GithubClient(config.github_token)
    pr = client.get_pull_request(repo, int(issue["number"]))
    return WorkItem(
        pull_request=pr,
        source=trigger.source,
        mode=trigger.mode,
        comment_id=trigger.comment_id,
        author=trigger.author,
        raw_text=trigger.raw_text,
    )


def _pull_request_work_item(payload: dict[str, Any], *, config: KioConfig) -> WorkItem | None:
    action = payload.get("action")
    if action not in {"review_requested", "opened", "reopened", "synchronize"}:
        return None
    pr_payload = payload.get("pull_request") or {}
    if action == "review_requested":
        requested = payload.get("requested_reviewer")
        reviewers = [requested.get("login", "")] if isinstance(requested, dict) else []
    else:
        reviewers = [
            user.get("login", "")
            for user in pr_payload.get("requested_reviewers", [])
            if isinstance(user, dict)
        ]
    trigger = trigger_from_reviewer_request(
        reviewers,
        bot_login=config.bot_login,
        allow_thermonuclear=config.allow_thermonuclear,
    )
    if not trigger:
        return None
    return WorkItem(
        pull_request=_pull_request_context(payload),
        source=trigger.source,
        mode=trigger.mode,
    )


def _pull_request_context(payload: dict[str, Any]) -> PullRequestContext:
    repo_name = _repo_name(payload)
    pr = payload.get("pull_request") or {}
    head = pr.get("head") or {}
    base = pr.get("base") or {}
    base_repo = base.get("repo") or payload.get("repository") or {}
    return PullRequestContext(
        repo_full_name=repo_name,
        number=int(pr["number"]),
        head_sha=str(head["sha"]),
        head_ref=str(head["ref"]),
        base_ref=str(base["ref"]),
        clone_url=str(base_repo["clone_url"]),
        html_url=str(pr.get("html_url", "")),
    )


def _repo_name(payload: dict[str, Any]) -> str:
    return str((payload.get("repository") or {}).get("full_name") or "")


def signed_body(payload: dict[str, Any], *, secret: str) -> tuple[bytes, str]:
    """Test helper for constructing signed webhook bodies."""
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return body, signature
