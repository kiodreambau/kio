from kio.config import KioConfig
from kio.backends import _run_shell_command
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


def test_shell_backend_keeps_file_written_output_when_stdout_is_empty(tmp_path):
    output_file = tmp_path / "agent-output.md"

    _run_shell_command(
        f"printf 'review text' > {output_file}",
        cwd=tmp_path,
        output_file=output_file,
        env={},
    )

    assert output_file.read_text(encoding="utf-8") == "review text"
