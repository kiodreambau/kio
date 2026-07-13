import json

from kio.config import KioConfig
from kio.run_store import list_runs


def test_list_runs_reads_metadata_and_backend_result(tmp_path):
    run_dir = tmp_path / "runs" / "owner__repo" / "pr-4" / "abc123" / "standard"
    run_dir.mkdir(parents=True)
    (run_dir / "metadata.json").write_text(
        json.dumps(
            {
                "mode": "standard",
                "source": "comment",
                "author": "dev",
                "pull_request": {
                    "repo_full_name": "owner/repo",
                    "number": 4,
                    "head_sha": "abc123",
                    "html_url": "https://github.com/owner/repo/pull/4",
                },
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "backend-result.json").write_text(
        json.dumps(
            {
                "backend": "gito",
                "report_file": str(run_dir / "review" / "code-review-report.md"),
            }
        ),
        encoding="utf-8",
    )

    runs = list_runs(KioConfig(workspace=tmp_path))

    assert len(runs) == 1
    assert runs[0].repo == "owner/repo"
    assert runs[0].pr == 4
    assert runs[0].status == "completed"
    assert runs[0].backend == "gito"


def test_list_runs_returns_empty_when_workspace_is_new(tmp_path):
    assert list_runs(KioConfig(workspace=tmp_path)) == []
