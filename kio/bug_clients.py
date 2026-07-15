"""Narrow Slack and GitHub ports for bug intake delivery."""

from __future__ import annotations

from typing import Iterable
from urllib.parse import urlparse

import requests


class SlackApiClient:
    def __init__(self, token: str, *, session=requests):
        if not token:
            raise ValueError("A Slack bot token is required")
        self._token = token
        self._session = session

    def reply(self, *, channel: str, thread_ts: str, text: str) -> None:
        response = self._session.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {self._token}"},
            json={"channel": channel, "thread_ts": thread_ts, "text": text},
            timeout=20,
        )
        value = response.json()
        if not response.ok or not value.get("ok"):
            raise RuntimeError("Slack thread reply failed")

    def download_file(self, url: str, *, max_bytes: int) -> tuple[bytes, str]:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not _is_slack_host(parsed.hostname or ""):
            raise ValueError("Slack file host is not allowed")
        response = self._session.get(
            url,
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=30,
            stream=True,
            allow_redirects=False,
        )
        if not response.ok:
            raise RuntimeError("Slack file download failed")
        expected_size = int(response.headers.get("content-length") or 0)
        if expected_size > max_bytes:
            raise ValueError("Slack file exceeds the allowed size")
        content = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            content.extend(chunk)
            if len(content) > max_bytes:
                raise ValueError("Slack file exceeds the allowed size")
        return bytes(content), str(response.headers.get("content-type") or "").split(";", 1)[0]


class GithubIssueClient:
    def __init__(self, token: str, *, session=requests):
        if not token:
            raise ValueError("A GitHub token is required")
        self._token = token
        self._session = session

    def create_issue(
        self,
        *,
        repo: str,
        title: str,
        body: str,
        labels: Iterable[str] = (),
    ) -> dict[str, object]:
        response = self._session.post(
            f"https://api.github.com/repos/{repo}/issues",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={"title": title, "body": body, "labels": list(labels)},
            timeout=30,
        )
        if not response.ok:
            raise RuntimeError("GitHub issue creation failed")
        value = response.json()
        return {"number": int(value["number"]), "url": str(value["html_url"])}


def _is_slack_host(hostname: str) -> bool:
    hostname = hostname.lower().rstrip(".")
    return hostname == "slack.com" or hostname.endswith(".slack.com")
