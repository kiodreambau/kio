"""Local kio worker orchestration."""

import json
import logging
import time

from .config import KioConfig
from .github import GithubClient
from .models import WorkItem
from .review_modes import normalize_review_mode
from .runs import prepare_run_dir
from .state import ReviewState


class KioWorker:
    def __init__(
        self,
        config: KioConfig,
        *,
        github: GithubClient | None = None,
        state: ReviewState | None = None,
    ):
        self.config = config
        self.github = github
        self.state = state or ReviewState(config.state_file)

    def run_once(self, *, repos: tuple[str, ...] | None = None, dry_run: bool = False) -> int:
        reviewed = 0
        target_repos = repos or self.config.repos
        if not target_repos:
            raise ValueError("No repositories configured. Use --repo or repos in .kio/config.toml.")
        for item in self._github().iter_work_items(
            target_repos,
            bot_login=self.config.bot_login,
            allow_thermonuclear=self.config.allow_thermonuclear,
            review_level_labels=self.config.review_level_labels,
        ):
            if self.process_item(item, dry_run=dry_run):
                reviewed += 1
        return reviewed

    def poll_forever(self, *, repos: tuple[str, ...] | None = None, dry_run: bool = False) -> None:
        while True:
            try:
                count = self.run_once(repos=repos, dry_run=dry_run)
                logging.info("kio worker pass complete: %s review(s) started", count)
            except Exception:
                logging.exception("kio worker pass failed")
            time.sleep(self.config.poll_interval_seconds)

    def review_pull_request(
        self,
        repo_full_name: str,
        number: int,
        *,
        mode: str,
        dry_run: bool = False,
    ) -> bool:
        pr = self._github().get_pull_request(repo_full_name, number)
        item = WorkItem(
            pull_request=pr,
            source="manual",
            mode=normalize_review_mode(
                mode,
                allow_thermonuclear=self.config.allow_thermonuclear,
            ),
        )
        return self.process_item(item, dry_run=dry_run)

    def process_item(self, item: WorkItem, *, dry_run: bool = False) -> bool:
        if self.state.has_completed(item.dedupe_key):
            logging.info("Skipping completed review %s", item.dedupe_key)
            return False
        run_dir = prepare_run_dir(self.config, item)
        if dry_run:
            logging.info("Dry run: would review %s in %s", item.dedupe_key, run_dir)
            return True
        from .backends import run_backend

        result = run_backend(
            item,
            config=self.config,
            run_dir=run_dir,
            post_comment=True,
        )
        with (run_dir / "backend-result.json").open("w", encoding="utf-8") as fh:
            json.dump(result.to_json(), fh, indent=2, sort_keys=True)
            fh.write("\n")
        from .notifications import notify_review_completed, write_codex_handoff

        handoff_file = write_codex_handoff(item, config=self.config, run_dir=run_dir)
        notify_review_completed(
            item,
            config=self.config,
            run_dir=run_dir,
            result=result,
            handoff_file=handoff_file,
        )
        self.state.mark_completed(
            item.dedupe_key,
            run_dir=run_dir,
            metadata={
                "backend": result.backend,
                "mode": item.mode,
                "repo": item.pull_request.repo_full_name,
                "pr": item.pull_request.number,
                "head_sha": item.pull_request.head_sha,
            },
        )
        return True

    def _github(self) -> GithubClient:
        if self.github is None:
            self.github = GithubClient(self.config.github_token)
        return self.github
