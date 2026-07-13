"""Run directory helpers for kio."""

from dataclasses import asdict
import json
from pathlib import Path
import re

from .config import KioConfig
from .models import WorkItem


def run_dir_for(config: KioConfig, item: WorkItem) -> Path:
    pr = item.pull_request
    repo_slug = _safe_slug(pr.repo_full_name)
    return config.runs_dir / repo_slug / f"pr-{pr.number}" / pr.head_sha / item.mode


def prepare_run_dir(config: KioConfig, item: WorkItem) -> Path:
    run_dir = run_dir_for(config, item)
    run_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "pull_request": asdict(item.pull_request),
        "source": item.source,
        "mode": item.mode,
        "comment_id": item.comment_id,
        "author": item.author,
        "raw_text": item.raw_text,
        "dedupe_key": item.dedupe_key,
    }
    with (run_dir / "metadata.json").open("w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return run_dir


def _safe_slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "__", value).strip("_")
