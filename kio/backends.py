"""Backend runners used by the local kio worker."""

from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess
import sys

from .config import KioConfig
from .models import BackendResult, WorkItem
from .review_modes import mode_prompt_hint
from .rules import write_rules_bundle


class BackendError(RuntimeError):
    """Raised when a configured backend cannot run."""


def run_backend(
    item: WorkItem,
    *,
    config: KioConfig,
    run_dir: Path,
    post_comment: bool,
) -> BackendResult:
    if config.backend == "gito":
        return _run_gito(item, config=config, run_dir=run_dir, post_comment=post_comment)
    return _run_external_agent(item, config=config, run_dir=run_dir, post_comment=post_comment)


def _run_gito(
    item: WorkItem,
    *,
    config: KioConfig,
    run_dir: Path,
    post_comment: bool,
) -> BackendResult:
    checkout_dir = _checkout_pull_request(item, run_dir)
    rules_file = write_rules_bundle(config, run_dir=run_dir, checkout_dir=checkout_dir)
    review_dir = run_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    pr = item.pull_request
    executable = (
        shlex.split(config.gito_command)
        if config.gito_command
        else [
            sys.executable,
            "-m",
            "gito",
        ]
    )
    cmd = [
        *executable,
        "review",
        f"HEAD..origin/{pr.base_ref}",
        "--pr",
        str(pr.number),
        "--out",
        str(review_dir),
    ]
    if post_comment:
        cmd.append("--post-comment")
    output_file = run_dir / "backend-output.log"
    _run_command(
        cmd,
        cwd=checkout_dir,
        output_file=output_file,
        env=_backend_env(config, rules_file=rules_file),
    )
    return BackendResult(
        backend="gito",
        returncode=0,
        command=shlex.join(cmd),
        output_file=output_file,
        report_file=review_dir / "code-review-report.md",
    )


def _run_external_agent(
    item: WorkItem,
    *,
    config: KioConfig,
    run_dir: Path,
    post_comment: bool,
) -> BackendResult:
    command_template = config.backend_commands.get(config.backend)
    if not command_template:
        raise BackendError(
            f"Backend '{config.backend}' needs a command template. "
            f"Set KIO_{config.backend.upper().replace('-', '_')}_COMMAND or "
            "[backend_commands] in .kio/config.toml."
        )
    checkout_dir = _checkout_pull_request(item, run_dir)
    rules_file = write_rules_bundle(config, run_dir=run_dir, checkout_dir=checkout_dir)
    diff_file = run_dir / "diff.patch"
    pr = item.pull_request
    _run_command(
        ["git", "diff", f"origin/{pr.base_ref}...HEAD"],
        cwd=checkout_dir,
        output_file=diff_file,
    )
    output_file = run_dir / "agent-output.md"
    command = command_template.format(
        repo=pr.repo_full_name,
        pr=pr.number,
        mode=item.mode,
        mode_prompt=mode_prompt_hint(item.mode),
        run_dir=run_dir,
        checkout_dir=checkout_dir,
        diff_file=diff_file,
        rules_file=rules_file or "",
        base_ref=pr.base_ref,
        head_ref=pr.head_ref,
        head_sha=pr.head_sha,
        default_agents=config.default_agents,
        max_agents=config.max_agents,
        token_budget=config.token_budget or "",
        cost_budget_usd=config.cost_budget_usd or "",
    )
    _run_shell_command(
        command,
        cwd=checkout_dir,
        output_file=output_file,
        env=_backend_env(config, rules_file=rules_file),
    )
    if post_comment:
        _post_agent_output(item, config=config, output_file=output_file)
    return BackendResult(
        backend=config.backend,
        returncode=0,
        command=command,
        output_file=output_file,
        report_file=output_file,
    )


def _checkout_pull_request(item: WorkItem, run_dir: Path) -> Path:
    pr = item.pull_request
    checkout_dir = run_dir / "repo"
    if checkout_dir.exists():
        return checkout_dir
    _run_command(["git", "clone", "--no-tags", pr.clone_url, str(checkout_dir)], cwd=run_dir)
    _run_command(
        [
            "git",
            "fetch",
            "origin",
            f"refs/heads/{pr.base_ref}:refs/remotes/origin/{pr.base_ref}",
        ],
        cwd=checkout_dir,
    )
    _run_command(
        [
            "git",
            "fetch",
            "origin",
            f"refs/pull/{pr.number}/head:refs/heads/kio-pr-{pr.number}",
        ],
        cwd=checkout_dir,
    )
    _run_command(["git", "checkout", f"kio-pr-{pr.number}"], cwd=checkout_dir)
    actual_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=checkout_dir,
        text=True,
    ).strip()
    if actual_sha != pr.head_sha:
        raise BackendError(f"Checked out PR #{pr.number} at {actual_sha}, expected {pr.head_sha}.")
    return checkout_dir


def _post_agent_output(item: WorkItem, *, config: KioConfig, output_file: Path) -> None:
    from gito.gh_api import post_gh_comment

    if not config.github_token:
        raise BackendError("Cannot post GitHub comment without GITHUB_TOKEN or GH_TOKEN.")
    body = output_file.read_text(encoding="utf-8").strip()
    if not body:
        body = f"kio {config.backend} review completed without text output."
    header = f"## kio review: {item.mode}\n\n"
    if not post_gh_comment(
        item.pull_request.repo_full_name,
        item.pull_request.number,
        config.github_token,
        header + body,
    ):
        raise BackendError("Failed to post GitHub comment.")


def _run_command(
    cmd: list[str],
    *,
    cwd: Path,
    output_file: Path | None = None,
    env: dict[str, str] | None = None,
) -> None:
    completed = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        check=False,
    )
    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(completed.stdout, encoding="utf-8")
    if completed.returncode != 0:
        raise BackendError(
            f"Command failed with exit code {completed.returncode}: {shlex.join(cmd)}"
        )


def _run_shell_command(
    command: str,
    *,
    cwd: Path,
    output_file: Path,
    env: dict[str, str],
) -> None:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        shell=True,
        check=False,
    )
    output_file.write_text(completed.stdout, encoding="utf-8")
    if completed.returncode != 0:
        raise BackendError(f"Command failed with exit code {completed.returncode}: {command}")


def _backend_env(config: KioConfig, *, rules_file: Path | None = None) -> dict[str, str]:
    env = os.environ.copy()
    if config.github_token:
        env["GITHUB_TOKEN"] = config.github_token
    env["KIO_BACKEND"] = config.backend
    env["KIO_DEFAULT_AGENTS"] = str(config.default_agents)
    env["KIO_MAX_AGENTS"] = str(config.max_agents)
    if config.token_budget is not None:
        env["KIO_TOKEN_BUDGET"] = str(config.token_budget)
    if config.cost_budget_usd is not None:
        env["KIO_COST_BUDGET_USD"] = str(config.cost_budget_usd)
    if rules_file:
        env["KIO_RULES_FILE"] = str(rules_file)
    return env
