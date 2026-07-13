"""GitHub polling helpers for kio."""

import logging
from typing import Iterable, Iterator

from ghapi.all import GhApi
from ghapi.page import paged
import requests

from .models import PullRequestContext, WorkItem
from .triggers import trigger_from_reviewer_request


class GithubClient:
    def __init__(self, token: str):
        if not token:
            raise ValueError("A GitHub token is required. Set GITHUB_TOKEN or GH_TOKEN.")
        self.token = token

    def iter_work_items(
        self,
        repos: Iterable[str],
        *,
        bot_login: str,
        allow_thermonuclear: bool,
        review_level_labels: dict[str, str],
    ) -> Iterator[WorkItem]:
        for repo_full_name in repos:
            api = self._api(repo_full_name)
            for pull in paged(api.pulls.list, state="open"):
                pr_ctx = _pull_context(repo_full_name, pull)
                reviewer_names = _logins(_get(pull, "requested_reviewers", []))
                labels = _label_names(_get(pull, "labels", []))
                if trigger := trigger_from_reviewer_request(
                    reviewer_names,
                    bot_login=bot_login,
                    labels=labels,
                    review_level_labels=review_level_labels,
                    allow_thermonuclear=allow_thermonuclear,
                ):
                    yield WorkItem(
                        pull_request=pr_ctx,
                        source=trigger.source,
                        mode=trigger.mode,
                        raw_text=trigger.raw_text,
                    )

    def get_pull_request(self, repo_full_name: str, number: int) -> PullRequestContext:
        api = self._api(repo_full_name)
        return _pull_context(repo_full_name, api.pulls.get(number))

    def _api(self, repo_full_name: str) -> GhApi:
        owner, repo = repo_full_name.split("/", 1)
        return GhApi(owner=owner, repo=repo, token=self.token)


def _pull_context(repo_full_name: str, pull) -> PullRequestContext:
    head = _get(pull, "head", {})
    base = _get(pull, "base", {})
    return PullRequestContext(
        repo_full_name=repo_full_name,
        number=int(_get(pull, "number")),
        head_sha=str(_get(head, "sha")),
        head_ref=str(_get(head, "ref")),
        base_ref=str(_get(base, "ref")),
        clone_url=str(_get(_get(base, "repo", {}), "clone_url")),
        html_url=str(_get(pull, "html_url", "")),
    )


def _logins(users) -> list[str]:
    return [str(_get(user, "login", "")) for user in users if _get(user, "login", "")]


def _label_names(labels) -> list[str]:
    return [str(_get(label, "name", "")) for label in labels if _get(label, "name", "")]


def post_pull_request_review(
    repo_full_name: str,
    number: int,
    token: str,
    body: str,
) -> bool:
    """Submit one native GitHub PR review without reacting to PR comments."""
    response = requests.post(
        f"https://api.github.com/repos/{repo_full_name}/pulls/{number}/reviews",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"body": body, "event": "COMMENT"},
        timeout=30,
    )
    if 200 <= response.status_code < 300:
        logging.info("Submitted native kio review to #%s in %s", number, repo_full_name)
        return True
    logging.error(
        "Failed to submit native review: %s %s\\n%s",
        response.status_code,
        response.reason,
        response.text,
    )
    return False


def _get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
