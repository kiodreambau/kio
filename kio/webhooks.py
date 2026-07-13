"""GitHub webhook parsing for local kio review triggers."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from .config import KioConfig
from .github import GithubClient
from .models import PullRequestContext, WorkItem
from .triggers import trigger_from_reviewer_request


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
    if event == "pull_request":
        return _pull_request_work_item(payload, config=config)
    return None


def _pull_request_work_item(payload: dict[str, Any], *, config: KioConfig) -> WorkItem | None:
    action = payload.get("action")
    if action != "review_requested":
        return None
    repo_name = _repo_name(payload)
    if not repo_name:
        raise ValueError("Webhook payload is missing repository.full_name.")
    if config.repos and repo_name not in config.repos:
        return None
    pr_payload = payload.get("pull_request") or {}
    requested = payload.get("requested_reviewer")
    reviewers = [requested.get("login", "")] if isinstance(requested, dict) else []
    labels = [
        label.get("name", "") for label in pr_payload.get("labels", []) if isinstance(label, dict)
    ]
    trigger = trigger_from_reviewer_request(
        reviewers,
        bot_login=config.bot_login,
        labels=labels,
        review_level_labels=config.review_level_labels,
        allow_thermonuclear=config.allow_thermonuclear,
    )
    if not trigger:
        return None
    return WorkItem(
        pull_request=_pull_request_context(payload),
        source=trigger.source,
        mode=trigger.mode,
        raw_text=trigger.raw_text,
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
