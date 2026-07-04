"""Shared data models for kio worker runs."""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PullRequestContext:
    repo_full_name: str
    number: int
    head_sha: str
    head_ref: str
    base_ref: str
    clone_url: str
    html_url: str = ""


@dataclass(frozen=True)
class WorkItem:
    pull_request: PullRequestContext
    source: str
    mode: str
    comment_id: int | None = None
    author: str | None = None
    raw_text: str = ""

    @property
    def dedupe_key(self) -> str:
        pr = self.pull_request
        return f"{pr.repo_full_name}#{pr.number}@{pr.head_sha}:{self.mode}"


@dataclass(frozen=True)
class BackendResult:
    backend: str
    returncode: int
    command: str
    output_file: Path
    report_file: Path | None = None

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["output_file"] = str(self.output_file)
        data["report_file"] = str(self.report_file) if self.report_file else None
        return data
