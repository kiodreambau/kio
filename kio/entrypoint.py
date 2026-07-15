"""CLI entrypoint for the local kio worker."""

import logging
from pathlib import Path
from typing import Annotated

import typer

from .config import load_config
from .models import PullRequestContext, WorkItem
from .review_modes import normalize_review_mode
from .runs import prepare_run_dir
from .service import render_launch_agent, write_launch_agent

app = typer.Typer(
    help="kio local PR review worker. GitHub is the interface; reviews run on this machine.",
    pretty_exceptions_show_locals=False,
)


@app.callback()
def callback(verbose: bool = typer.Option(False, "--verbose", "-v")):
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s %(message)s",
    )


@app.command("once")
def once(
    repo: Annotated[
        list[str] | None,
        typer.Option("--repo", "-r", help="GitHub repo, e.g. kiodreambau/sandbox"),
    ] = None,
    config_file: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Additional kio TOML config file"),
    ] = None,
    dry_run: bool = typer.Option(False, "--dry-run", help="Do not run backends or post comments"),
):
    """Poll configured repos once and process matching kio triggers."""
    from .worker import KioWorker

    cfg = load_config(config_file)
    count = KioWorker(cfg).run_once(repos=tuple(repo or ()), dry_run=dry_run)
    typer.echo(f"kio processed {count} review trigger(s).")


@app.command("poll")
def poll(
    repo: Annotated[
        list[str] | None,
        typer.Option("--repo", "-r", help="GitHub repo, e.g. kiodreambau/sandbox"),
    ] = None,
    config_file: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Additional kio TOML config file"),
    ] = None,
    dry_run: bool = typer.Option(False, "--dry-run", help="Do not run backends or post comments"),
):
    """Run the local worker continuously."""
    from .worker import KioWorker

    cfg = load_config(config_file)
    KioWorker(cfg).poll_forever(repos=tuple(repo or ()), dry_run=dry_run)


@app.command("review-pr")
def review_pr(
    repo: Annotated[str, typer.Argument(help="GitHub repo, e.g. kiodreambau/sandbox")],
    number: Annotated[int, typer.Argument(help="Pull request number")],
    mode: str = typer.Option("standard", "--mode", "-m"),
    config_file: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Additional kio TOML config file"),
    ] = None,
    dry_run: bool = typer.Option(False, "--dry-run", help="Do not run backends or post comments"),
):
    """Run one PR review manually through the configured backend."""
    from .worker import KioWorker

    cfg = load_config(config_file)
    started = KioWorker(cfg).review_pull_request(repo, number, mode=mode, dry_run=dry_run)
    typer.echo("kio review started." if started else "kio review was already completed.")


@app.command("prepare-run")
def prepare_run(
    repo: Annotated[str, typer.Argument(help="GitHub repo, e.g. kiodreambau/sandbox")],
    number: Annotated[int, typer.Argument(help="Pull request number")],
    head_sha: Annotated[str, typer.Option("--head-sha")],
    head_ref: Annotated[str, typer.Option("--head-ref")],
    base_ref: Annotated[str, typer.Option("--base-ref")],
    clone_url: Annotated[str, typer.Option("--clone-url")],
    mode: str = typer.Option("standard", "--mode", "-m"),
    config_file: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Additional kio TOML config file"),
    ] = None,
):
    """Create the local run folder and metadata without contacting GitHub."""
    cfg = load_config(config_file)
    item = WorkItem(
        pull_request=PullRequestContext(
            repo_full_name=repo,
            number=number,
            head_sha=head_sha,
            head_ref=head_ref,
            base_ref=base_ref,
            clone_url=clone_url,
        ),
        source="manual",
        mode=normalize_review_mode(mode, allow_thermonuclear=cfg.allow_thermonuclear),
    )
    run_dir = prepare_run_dir(cfg, item)
    typer.echo(str(run_dir))


@app.command("serve")
def serve(
    host: str | None = typer.Option(None, "--host"),
    port: int | None = typer.Option(None, "--port", "-p"),
    config_file: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Additional kio TOML config file"),
    ] = None,
):
    """Serve the self-hosted local kio dashboard."""
    import uvicorn

    from .web import create_app

    cfg = load_config(config_file)
    uvicorn.run(create_app(cfg), host=host or cfg.dashboard_host, port=port or cfg.dashboard_port)


@app.command("launch-agent")
def launch_agent(
    config_file: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Additional kio TOML config file"),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Write plist to this path"),
    ] = None,
    print_only: bool = typer.Option(
        False,
        "--print",
        help="Print the plist instead of writing it",
    ),
):
    """Create a macOS LaunchAgent plist for running kio serve at login."""
    cfg = load_config(config_file)
    plist_text = render_launch_agent(cfg, config_file=config_file)
    if print_only:
        typer.echo(plist_text)
        return
    path = write_launch_agent(cfg, plist_text=plist_text, output=output)
    typer.echo(str(path))


@app.command("repair-once")
def repair_once(
    config_file: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Additional kio TOML config file"),
    ] = None,
):
    """Claim and process at most one human-gated repair job."""
    from .repair_worker import run_repair_once

    processed = run_repair_once(load_config(config_file))
    typer.echo("kio repair processed." if processed else "kio repair queue is empty.")


@app.command("repair-poll")
def repair_poll(
    config_file: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Additional kio TOML config file"),
    ] = None,
):
    """Continuously process human-gated repairs on this Mac."""
    from .repair_worker import poll_repairs_forever

    poll_repairs_forever(load_config(config_file))


def main():
    app()
