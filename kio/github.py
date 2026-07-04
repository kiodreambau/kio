"""GitHub polling helpers for kio."""

import logging
from typing import Iterable, Iterator

from ghapi.all import GhApi
from ghapi.page import paged

from .models import PullRequestContext, WorkItem
from .review_modes import ReviewModeError
from .triggers import parse_review_comment, trigger_from_reviewer_request


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
    ) -> Iterator[WorkItem]:
        for repo_full_name in repos:
            api = self._api(repo_full_name)
            for pull in paged(api.pulls.list, state="open"):
                pr_ctx = _pull_context(repo_full_name, pull)
                reviewer_names = _logins(_get(pull, "requested_reviewers", []))
                if trigger := trigger_from_reviewer_request(
                    reviewer_names,
                    bot_login=bot_login,
                    allow_thermonuclear=allow_thermonuclear,
                ):
                    yield WorkItem(
                        pull_request=pr_ctx,
                        source=trigger.source,
                        mode=trigger.mode,
                    )

                for comment in paged(api.issues.list_comments, _get(pull, "number")):
                    try:
                        trigger = parse_review_comment(
                            _get(comment, "body", ""),
                            bot_login=bot_login,
                            allow_thermonuclear=allow_thermonuclear,
                            comment_id=_get(comment, "id"),
                            author=_get(_get(comment, "user", {}), "login"),
                        )
                    except ReviewModeError as exc:
                        logging.warning("Ignoring unsupported kio trigger: %s", exc)
                        continue
                    if trigger:
                        yield WorkItem(
                            pull_request=pr_ctx,
                            source=trigger.source,
                            mode=trigger.mode,
                            comment_id=trigger.comment_id,
                            author=trigger.author,
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


def _get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
