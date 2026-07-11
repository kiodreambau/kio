"""Configuration loading for the local kio worker."""

from dataclasses import dataclass, field
import os
from pathlib import Path
import tomllib
from typing import Any

from .review_modes import DEFAULT_LEVEL_PROFILES, DEFAULT_PROFILE_TEMPLATES, resolve_review_profiles

SUPPORTED_BACKENDS = {"gito", "codex", "claude-code", "opencode", "local"}


@dataclass(frozen=True)
class KioConfig:
    bot_login: str = "kiodreambau"
    trigger_handle: str = "kiocheck"
    backend: str = "gito"
    workspace: Path = Path("~/kio")
    poll_interval_seconds: int = 60
    default_agents: int = 2
    max_agents: int = 5
    allow_thermonuclear: bool = False
    github_token: str = ""
    repos: tuple[str, ...] = ()
    backend_commands: dict[str, str] = field(default_factory=dict)
    gito_command: str = ""
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8765
    webhook_secret: str = ""
    webhook_dry_run: bool = False
    launch_agent_label: str = "io.kio.worker"
    launch_agent_runner: str = "uv"
    rules_files: tuple[str, ...] = ("AGENTS.md",)
    token_budget: int | None = None
    cost_budget_usd: float | None = None
    review_levels: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: dict(DEFAULT_LEVEL_PROFILES)
    )
    review_templates: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_PROFILE_TEMPLATES)
    )

    @property
    def runs_dir(self) -> Path:
        return self.workspace.expanduser() / "runs"

    @property
    def state_dir(self) -> Path:
        return self.workspace.expanduser() / "state"

    @property
    def state_file(self) -> Path:
        return self.state_dir / "reviews.json"

    def validate(self) -> None:
        if self.backend not in SUPPORTED_BACKENDS:
            allowed = ", ".join(sorted(SUPPORTED_BACKENDS))
            raise ValueError(f"Unsupported KIO_BACKEND '{self.backend}'. Allowed: {allowed}.")
        if self.default_agents < 1:
            raise ValueError("KIO_DEFAULT_AGENTS must be at least 1.")
        if self.max_agents < self.default_agents:
            raise ValueError("KIO_MAX_AGENTS must be greater than or equal to KIO_DEFAULT_AGENTS.")
        for level, profiles in self.review_levels.items():
            if str(level) not in {"1", "2", "3", "4"}:
                raise ValueError("review_levels may only define levels 1 through 4.")
            if not profiles:
                raise ValueError(f"review level {level} must contain at least one profile.")
            if len(profiles) > self.max_agents:
                raise ValueError(
                    f"review level {level} has {len(profiles)} passes, above max_agents={self.max_agents}."
                )
            resolve_review_profiles(
                f"level-{level}",
                level_profiles=self.review_levels,
                profile_templates=self.review_templates,
            )


def load_config(config_file: Path | None = None) -> KioConfig:
    """Load config from ~/.kio/config.toml, .kio/config.toml, an optional file, and env."""
    data: dict[str, Any] = {}
    for candidate in _candidate_files(config_file):
        if candidate.exists():
            data = _merge_config(data, _read_toml(candidate))
    data = _apply_env(data)

    cfg = KioConfig(
        bot_login=str(data.get("bot_login", KioConfig.bot_login)),
        trigger_handle=str(data.get("trigger_handle", KioConfig.trigger_handle)),
        backend=str(data.get("backend", KioConfig.backend)),
        workspace=Path(str(data.get("workspace", KioConfig.workspace))),
        poll_interval_seconds=int(
            data.get("poll_interval_seconds", KioConfig.poll_interval_seconds)
        ),
        default_agents=int(data.get("default_agents", KioConfig.default_agents)),
        max_agents=int(data.get("max_agents", KioConfig.max_agents)),
        allow_thermonuclear=bool(data.get("allow_thermonuclear", KioConfig.allow_thermonuclear)),
        github_token=str(data.get("github_token", "")),
        repos=tuple(data.get("repos", ())),
        backend_commands=dict(data.get("backend_commands", {})),
        gito_command=str(data.get("gito_command", "")),
        dashboard_host=str(data.get("dashboard_host", KioConfig.dashboard_host)),
        dashboard_port=int(data.get("dashboard_port", KioConfig.dashboard_port)),
        webhook_secret=str(data.get("webhook_secret", "")),
        webhook_dry_run=bool(data.get("webhook_dry_run", KioConfig.webhook_dry_run)),
        launch_agent_label=str(data.get("launch_agent_label", KioConfig.launch_agent_label)),
        launch_agent_runner=str(data.get("launch_agent_runner", KioConfig.launch_agent_runner)),
        rules_files=tuple(data.get("rules_files", KioConfig.rules_files)),
        token_budget=_optional_int(data.get("token_budget")),
        cost_budget_usd=_optional_float(data.get("cost_budget_usd")),
        review_levels=_review_levels(data.get("review_levels")),
        review_templates=_review_templates(data.get("review_templates")),
    )
    cfg.validate()
    return cfg


def _candidate_files(config_file: Path | None) -> list[Path]:
    candidates = [
        Path("~/.kio/config.toml").expanduser(),
        Path(".kio/config.toml"),
    ]
    if config_file:
        candidates.append(config_file.expanduser())
    return candidates


def _read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _merge_config(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = dict(merged[key]) | value
        else:
            merged[key] = value
    return merged


def _apply_env(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    env_map = {
        "KIO_BOT_LOGIN": "bot_login",
        "KIO_TRIGGER_HANDLE": "trigger_handle",
        "KIO_BACKEND": "backend",
        "KIO_WORKSPACE": "workspace",
        "KIO_POLL_INTERVAL_SECONDS": "poll_interval_seconds",
        "KIO_DEFAULT_AGENTS": "default_agents",
        "KIO_MAX_AGENTS": "max_agents",
        "KIO_ALLOW_THERMONUCLEAR": "allow_thermonuclear",
        "KIO_GITO_COMMAND": "gito_command",
        "KIO_DASHBOARD_HOST": "dashboard_host",
        "KIO_DASHBOARD_PORT": "dashboard_port",
        "KIO_WEBHOOK_SECRET": "webhook_secret",
        "KIO_WEBHOOK_DRY_RUN": "webhook_dry_run",
        "KIO_LAUNCH_AGENT_LABEL": "launch_agent_label",
        "KIO_LAUNCH_AGENT_RUNNER": "launch_agent_runner",
        "KIO_RULES_FILES": "rules_files",
        "KIO_TOKEN_BUDGET": "token_budget",
        "KIO_COST_BUDGET_USD": "cost_budget_usd",
        "GITHUB_TOKEN": "github_token",
        "GH_TOKEN": "github_token",
    }
    for env_key, cfg_key in env_map.items():
        if env_key in os.environ and os.environ[env_key] != "":
            out[cfg_key] = _coerce_env_value(cfg_key, os.environ[env_key])

    backend_commands = dict(out.get("backend_commands", {}))
    if command := os.getenv("KIO_BACKEND_COMMAND"):
        backend = str(out.get("backend", KioConfig.backend))
        backend_commands[backend] = command
    for backend in SUPPORTED_BACKENDS:
        env_key = f"KIO_{backend.upper().replace('-', '_')}_COMMAND"
        if command := os.getenv(env_key):
            backend_commands[backend] = command
    if backend_commands:
        out["backend_commands"] = backend_commands
    return out


def _coerce_env_value(key: str, value: str) -> Any:
    if key in {"poll_interval_seconds", "default_agents", "max_agents", "dashboard_port"}:
        return int(value)
    if key == "rules_files":
        return tuple(item.strip() for item in value.split(",") if item.strip())
    if key == "token_budget":
        return _optional_int(value)
    if key == "cost_budget_usd":
        return _optional_float(value)
    if key in {"allow_thermonuclear", "webhook_dry_run"}:
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return value


def _review_levels(value: Any) -> dict[str, tuple[str, ...]]:
    levels = dict(DEFAULT_LEVEL_PROFILES)
    if not value:
        return levels
    if not isinstance(value, dict):
        raise ValueError("review_levels must be a TOML table of level to profile names.")
    for raw_level, raw_profiles in value.items():
        if not isinstance(raw_profiles, list):
            raise ValueError(f"review_levels.{raw_level} must be an array of template names.")
        levels[str(raw_level)] = tuple(str(profile) for profile in raw_profiles)
    return levels


def _review_templates(value: Any) -> dict[str, str]:
    templates = dict(DEFAULT_PROFILE_TEMPLATES)
    if not value:
        return templates
    if not isinstance(value, dict):
        raise ValueError("review_templates must be a TOML table of template text.")
    templates.update({str(name): str(text) for name, text in value.items()})
    return templates


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)
