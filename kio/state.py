"""Persistent dedupe state for local kio review runs."""

import json
from pathlib import Path
from typing import Any


class ReviewState:
    def __init__(self, path: Path):
        self.path = path.expanduser()

    def has_completed(self, key: str) -> bool:
        return self._load().get(key, {}).get("status") == "completed"

    def mark_completed(self, key: str, *, run_dir: Path, metadata: dict[str, Any]) -> None:
        state = self._load()
        state[key] = {
            "status": "completed",
            "run_dir": str(run_dir),
            **metadata,
        }
        self._save(state)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        with self.path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
        tmp.replace(self.path)
