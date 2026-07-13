"""Backend runners used by the local kio worker."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

from .config import KioConfig
from .models import BackendResult, WorkItem
from .review_modes import ReviewProfile, resolve_review_profiles, review_level
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
    profiles = resolve_review_profiles(
        item.mode,
        level_profiles=config.review_levels,
        profile_templates=config.review_templates,
    )
    _write_review_plan(item, run_dir=run_dir, profiles=profiles)
    if config.backend == "gito":
        return _run_gito(
            item,
            config=config,
            run_dir=run_dir,
            profiles=profiles,
            post_comment=post_comment,
        )
    return _run_external_agent(
        item,
        config=config,
        run_dir=run_dir,
        profiles=profiles,
        post_comment=post_comment,
    )


def _run_gito(
    item: WorkItem,
    *,
    config: KioConfig,
    run_dir: Path,
    profiles: tuple[ReviewProfile, ...],
    post_comment: bool,
) -> BackendResult:
    checkout_dir = _checkout_pull_request(item, run_dir)
    rules_file = write_rules_bundle(config, run_dir=run_dir, checkout_dir=checkout_dir)
    config_path = checkout_dir / ".gito" / "config.toml"
    original_config = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
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
    reports: list[tuple[ReviewProfile, Path]] = []
    commands: list[str] = []
    logs: list[str] = []
    for index, profile in enumerate(profiles, start=1):
        _write_gito_profile_config(
            config_path,
            original_config=original_config,
            profile=profile,
            rules_file=rules_file,
        )
        review_dir = run_dir / "reviews" / f"{index:02d}-{profile.name}"
        review_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            *executable,
            "review",
            f"HEAD..origin/{pr.base_ref}",
            "--pr",
            str(pr.number),
            "--out",
            str(review_dir),
        ]
        output_file = review_dir / "backend-output.log"
        _run_command(
            cmd,
            cwd=checkout_dir,
            output_file=output_file,
            env=_backend_env(config, rules_file=rules_file, profile=profile),
        )
        reports.append((profile, review_dir / "code-review-report.md"))
        commands.append(shlex.join(cmd))
        logs.append(output_file.read_text(encoding="utf-8"))
    output_file = run_dir / "backend-output.log"
    output_file.write_text("\n\n".join(logs), encoding="utf-8")
    report_file = _write_review_comment(
        item, run_dir=run_dir, reports=reports, rules_file=rules_file
    )
    if post_comment:
        _post_review_output(item, config=config, output_file=report_file)
    return BackendResult(
        backend="gito",
        returncode=0,
        command="\n".join(commands),
        output_file=output_file,
        report_file=report_file,
    )


def _run_external_agent(
    item: WorkItem,
    *,
    config: KioConfig,
    run_dir: Path,
    profiles: tuple[ReviewProfile, ...],
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
    reports: list[tuple[ReviewProfile, Path]] = []
    commands: list[str] = []
    for index, profile in enumerate(profiles, start=1):
        review_dir = run_dir / "reviews" / f"{index:02d}-{profile.name}"
        review_dir.mkdir(parents=True, exist_ok=True)
        profile_file = _write_profile_file(profile, review_dir=review_dir, rules_file=rules_file)
        output_file = review_dir / "agent-output.md"
        command = command_template.format(
            repo=pr.repo_full_name,
            pr=pr.number,
            mode=item.mode,
            review_level=review_level(item.mode) or "",
            mode_prompt=profile.instructions,
            profile=profile.name,
            profile_title=profile.title,
            profile_instructions=profile.instructions,
            profile_file=profile_file,
            output_file=output_file,
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
            env=_backend_env(config, rules_file=rules_file, profile=profile),
        )
        reports.append((profile, output_file))
        commands.append(command)
    output_file = run_dir / "backend-output.log"
    output_file.write_text("\n\n".join(commands), encoding="utf-8")
    report_file = _write_review_comment(
        item, run_dir=run_dir, reports=reports, rules_file=rules_file
    )
    if post_comment:
        _post_review_output(item, config=config, output_file=report_file)
    return BackendResult(
        backend=config.backend,
        returncode=0,
        command="\n".join(commands),
        output_file=output_file,
        report_file=report_file,
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


def _write_review_plan(
    item: WorkItem, *, run_dir: Path, profiles: tuple[ReviewProfile, ...]
) -> Path:
    out = run_dir / "review-plan.json"
    out.write_text(
        json.dumps(
            {
                "mode": item.mode,
                "level": review_level(item.mode),
                "profiles": [
                    {
                        "name": profile.name,
                        "title": profile.title,
                        "instructions": profile.instructions,
                    }
                    for profile in profiles
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return out


def _write_gito_profile_config(
    config_path: Path,
    *,
    original_config: str,
    profile: ReviewProfile,
    rules_file: Path | None,
) -> None:
    """Overlay a profile in the isolated PR checkout without touching the source repository."""
    import tomlkit

    document = tomlkit.parse(original_config) if original_config.strip() else tomlkit.document()
    prompt_vars = document.get("prompt_vars")
    if prompt_vars is None:
        prompt_vars = tomlkit.table()
        document["prompt_vars"] = prompt_vars
    existing = str(prompt_vars.get("requirements", "")).strip()
    additions = [
        "--- kio review pass ---",
        f"Profile: {profile.title}",
        profile.instructions,
        "For every finding, state the observable evidence, likely impact, and why the changed code causes it.",
    ]
    if rules_file and rules_file.exists():
        additions.extend(
            ["--- project review rules ---", rules_file.read_text(encoding="utf-8").strip()]
        )
    prompt_vars["requirements"] = "\n\n".join(part for part in [existing, *additions] if part)
    prompt_vars["kio_review_profile"] = profile.name
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(tomlkit.dumps(document), encoding="utf-8")


def _write_profile_file(
    profile: ReviewProfile, *, review_dir: Path, rules_file: Path | None
) -> Path:
    out = review_dir / "review-profile.md"
    lines = [f"# {profile.title}", "", profile.instructions, "", "## Required transparency", ""]
    lines.append("For each finding, include evidence, impact, and why this diff causes the issue.")
    if rules_file and rules_file.exists():
        lines.extend(["", "## Project rules", "", rules_file.read_text(encoding="utf-8").strip()])
    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return out


def _write_review_comment(
    item: WorkItem,
    *,
    run_dir: Path,
    reports: list[tuple[ReviewProfile, Path]],
    rules_file: Path | None,
) -> Path:
    level = review_level(item.mode)
    title = f"Level {level}" if level else item.mode.title()
    lines = [
        f"## kiocheck review: {title}",
        "",
        "### Scope",
        f"- PR: #{item.pull_request.number}",
        f"- Commit: `{item.pull_request.head_sha}`",
        f"- Trigger: `{item.raw_text or item.source}`",
        f"- Project rules: {'included' if rules_file else 'none found'}",
        "",
        "### Review passes",
    ]
    lines.extend(f"- {profile.title}" for profile, _report in reports)
    lines.extend(
        [
            "",
            "Each finding below should include the evidence in the diff, impact, and causal explanation. "
            "This report intentionally shows review evidence rather than hidden model reasoning.",
        ]
    )
    for profile, report_path in reports:
        body = report_path.read_text(encoding="utf-8").strip() if report_path.exists() else ""
        lines.extend(["", f"### {profile.title}", "", _strip_report_markers(body) or "No output."])
    out = run_dir / "review-comment.md"
    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return out


def _strip_report_markers(body: str) -> str:
    return re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL).strip()


def _post_review_output(item: WorkItem, *, config: KioConfig, output_file: Path) -> None:
    from .github import post_pull_request_review

    if not config.github_token:
        raise BackendError("Cannot submit a GitHub review without GITHUB_TOKEN or GH_TOKEN.")
    body = output_file.read_text(encoding="utf-8").strip()
    if not body:
        body = "## kiocheck review\n\nThe configured backend completed without text output."
    if len(body) > 60_000:
        body = (
            body[:59_800].rstrip() + "\n\n---\nThe full report is retained in the kio run artifact."
        )
    if not post_pull_request_review(
        item.pull_request.repo_full_name,
        item.pull_request.number,
        config.github_token,
        body,
    ):
        raise BackendError("Failed to submit GitHub review.")


def _split_comment(body: str, *, max_length: int = 60_000) -> list[str]:
    if len(body) <= max_length:
        return [body]
    sections = body.split("\n### ")
    chunks: list[str] = []
    current = sections[0]
    for section in sections[1:]:
        section = "### " + section
        if len(current) + len(section) + 2 > max_length and current:
            chunks.append(current)
            current = "## kiocheck review: continued\n\n" + section
        else:
            current += "\n\n" + section
    if current:
        chunks.append(current)
    return chunks


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
    if completed.stdout or not output_file.exists():
        output_file.write_text(completed.stdout, encoding="utf-8")
    if completed.returncode != 0:
        raise BackendError(f"Command failed with exit code {completed.returncode}: {command}")


def _backend_env(
    config: KioConfig,
    *,
    rules_file: Path | None = None,
    profile: ReviewProfile | None = None,
) -> dict[str, str]:
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
    if profile:
        env["KIO_REVIEW_PROFILE"] = profile.name
        env["KIO_REVIEW_PROFILE_TITLE"] = profile.title
        env["KIO_REVIEW_PROFILE_INSTRUCTIONS"] = profile.instructions
    return env
