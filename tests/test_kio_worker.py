from kio.config import KioConfig
from kio.models import PullRequestContext, WorkItem
from kio.worker import KioWorker


def test_process_item_dry_run_does_not_require_github_token(tmp_path):
    item = WorkItem(
        pull_request=PullRequestContext(
            repo_full_name="owner/repo",
            number=1,
            head_sha="abc123",
            head_ref="feature",
            base_ref="main",
            clone_url="https://github.com/owner/repo.git",
        ),
        source="manual",
        mode="standard",
    )

    started = KioWorker(KioConfig(workspace=tmp_path)).process_item(item, dry_run=True)

    assert started is True
    assert (tmp_path / "runs" / "owner__repo" / "pr-1" / "abc123" / "standard").exists()
