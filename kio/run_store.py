"""Read local kio run artifacts for the dashboard and API."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from .config import KioConfig


@dataclass(frozen=True)
class RunSummary:
    repo: str
    pr: int
    head_sha: str
    mode: str
    source: str
    status: str
    run_dir: str
    updated_at: float
    backend: str = ""
    report_file: str = ""
    author: str = ""
    html_url: str = ""

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def list_runs(config: KioConfig, *, limit: int = 100) -> list[RunSummary]:
    runs_dir = config.runs_dir
    if not runs_dir.exists():
        return []
    records: list[RunSummary] = []
    for metadata_file in runs_dir.glob("**/metadata.json"):
        if summary := _load_run(metadata_file):
            records.append(summary)
    records.sort(key=lambda item: item.updated_at, reverse=True)
    return records[:limit]


def state_snapshot(config: KioConfig) -> dict[str, Any]:
    if not config.state_file.exists():
        return {}
    return _read_json(config.state_file)


def _load_run(metadata_file: Path) -> RunSummary | None:
    metadata = _read_json(metadata_file)
    if not metadata:
        return None
    run_dir = metadata_file.parent
    pr = metadata.get("pull_request", {})
    backend_result = _read_json(run_dir / "backend-result.json")
    backend = str(backend_result.get("backend", ""))
    report_file = str(backend_result.get("report_file") or "")
    status = "completed" if backend_result else "prepared"
    updated_at = max(
        metadata_file.stat().st_mtime,
        (
            (run_dir / "backend-result.json").stat().st_mtime
            if (run_dir / "backend-result.json").exists()
            else metadata_file.stat().st_mtime
        ),
    )
    return RunSummary(
        repo=str(pr.get("repo_full_name", "")),
        pr=int(pr.get("number", 0)),
        head_sha=str(pr.get("head_sha", "")),
        mode=str(metadata.get("mode", "")),
        source=str(metadata.get("source", "")),
        status=status,
        run_dir=str(run_dir),
        updated_at=updated_at,
        backend=backend,
        report_file=report_file,
        author=str(metadata.get("author") or ""),
        html_url=str(pr.get("html_url", "")),
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)
