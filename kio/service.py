"""macOS self-host service helpers."""

from __future__ import annotations

import os
from pathlib import Path
import plistlib
import shutil
import sys

from .config import KioConfig


def default_launch_agent_path(config: KioConfig) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{config.launch_agent_label}.plist"


def render_launch_agent(config: KioConfig, *, config_file: Path | None = None) -> str:
    log_dir = config.workspace.expanduser() / "logs"
    args = _program_arguments(config)
    if config_file:
        args.extend(["--config", str(config_file.expanduser())])
    env = {
        "PATH": _service_path(),
        "KIO_WORKSPACE": str(config.workspace.expanduser()),
    }
    plist = {
        "Label": config.launch_agent_label,
        "ProgramArguments": args,
        "RunAtLoad": True,
        "KeepAlive": True,
        "WorkingDirectory": str(Path.cwd()),
        "EnvironmentVariables": env,
        "StandardOutPath": str(log_dir / "launch-agent.out.log"),
        "StandardErrorPath": str(log_dir / "launch-agent.err.log"),
    }
    return plistlib.dumps(plist, sort_keys=True).decode("utf-8")


def render_repair_launch_agent(config: KioConfig, *, config_file: Path | None = None) -> str:
    """Render the separate Mac repair poller without serializing its credential."""
    log_dir = config.workspace.expanduser() / "logs"
    args = _kio_program_arguments(["repair-poll"])
    if config_file:
        args.extend(["--config", str(config_file.expanduser())])
    plist = {
        "Label": f"{config.launch_agent_label}.repair",
        "ProgramArguments": args,
        "RunAtLoad": True,
        "KeepAlive": True,
        "WorkingDirectory": str(Path.cwd()),
        "EnvironmentVariables": {
            "PATH": _service_path(),
            "KIO_WORKSPACE": str(config.workspace.expanduser()),
        },
        "StandardOutPath": str(log_dir / "repair-agent.out.log"),
        "StandardErrorPath": str(log_dir / "repair-agent.err.log"),
    }
    return plistlib.dumps(plist, sort_keys=True).decode("utf-8")


def write_launch_agent(
    config: KioConfig,
    *,
    plist_text: str | None = None,
    output: Path | None = None,
) -> Path:
    path = (output or default_launch_agent_path(config)).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    config.workspace.expanduser().joinpath("logs").mkdir(parents=True, exist_ok=True)
    path.write_text(plist_text or render_launch_agent(config), encoding="utf-8")
    return path


def _program_arguments(config: KioConfig) -> list[str]:
    serve_args = [
        "serve",
        "--host",
        config.dashboard_host,
        "--port",
        str(config.dashboard_port),
    ]
    return _kio_program_arguments(serve_args, config=config)


def _kio_program_arguments(args: list[str], *, config: KioConfig | None = None) -> list[str]:
    runner = config.launch_agent_runner if config else "uv"
    if runner == "uv" and (uv := shutil.which("uv")):
        return [
            uv,
            "run",
            "--no-project",
            "--with-editable",
            str(Path.cwd()),
            "python",
            "-m",
            "kio",
            *args,
        ]
    return [sys.executable, "-m", "kio", *args]


def _service_path() -> str:
    home_local = str(Path.home() / ".local" / "bin")
    paths = [
        home_local,
        "/opt/homebrew/bin",
        "/opt/homebrew/sbin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
    ]
    return ":".join(paths)
