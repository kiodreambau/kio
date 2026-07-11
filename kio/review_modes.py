"""Review levels, specialist passes, and guarded legacy modes for kio."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

DEFAULT_MODE = "level-1"
THERMONUCLEAR_MODE = "thermonuclear"
LEVELS = (1, 2, 3, 4)
LEGACY_MODES = {"standard", "stability", "tests", "frontend", "security", THERMONUCLEAR_MODE}


@dataclass(frozen=True)
class ReviewProfile:
    """One independently scoped review pass within a kio review level."""

    name: str
    title: str
    instructions: str


DEFAULT_LEVEL_PROFILES: dict[str, tuple[str, ...]] = {
    "1": ("basic",),
    "2": ("basic", "test-density"),
    "3": ("basic", "test-density", "stability"),
    "4": ("correctness", "test-density", "stability", "performance"),
}

DEFAULT_PROFILE_TEMPLATES: dict[str, str] = {
    "basic": (
        "Perform a concise, high-confidence review of the changed behavior. "
        "Report only concrete defects or regressions, with file and line evidence."
    ),
    "correctness": (
        "Review correctness and changed user-visible behavior. Trace control flow, data flow, "
        "error handling, and backward compatibility. If the diff affects UI, also assess keyboard "
        "use, semantic structure, labels, focus handling, and other accessibility regressions."
    ),
    "test-density": (
        "Review test density and verification. Identify changed behavior without a focused test, "
        "weak assertions, missing edge cases, and mismatches with lint, type-check, or test tooling. "
        "Do not demand tests where the changed behavior is already covered with strong evidence."
    ),
    "stability": (
        "Review stability and operational safety. Focus on failure paths, retries, state transitions, "
        "concurrency, idempotency, data loss, migrations, and safe degradation."
    ),
    "performance": (
        "Review performance and scalability. Focus on avoidable repeated work, unbounded queries or "
        "loops, excess network or disk I/O, memory growth, and latency regressions that the diff can cause."
    ),
    "frontend": (
        "Review UI behavior, accessibility, responsive layout, keyboard interaction, and user-facing regressions."
    ),
    "security": (
        "Review authentication, authorization, secrets, injection, data exposure, dependency, and supply-chain risk."
    ),
    "thermonuclear": (
        "Perform the deepest practical review across correctness, testing, stability, security, accessibility, "
        "and performance. Keep every finding concrete and actionable."
    ),
}


class ReviewModeError(ValueError):
    """Raised when a requested review mode or level is not allowed."""


def normalize_review_mode(raw_mode: str | None, *, allow_thermonuclear: bool = False) -> str:
    """Normalize a review level, while accepting the earlier explicit mode names."""
    raw = (raw_mode or DEFAULT_MODE).strip().lower().replace("_", "-")
    if not raw:
        return DEFAULT_MODE
    if raw in {"basic", "standard"}:
        return DEFAULT_MODE
    if match := re.fullmatch(r"(?:level-?)?([1-4])", raw):
        return f"level-{match.group(1)}"
    if raw in LEGACY_MODES:
        if raw == THERMONUCLEAR_MODE and not allow_thermonuclear:
            raise ReviewModeError("The thermonuclear review mode is disabled in local config.")
        return raw
    allowed = "1, 2, 3, 4, standard, stability, tests, frontend, security, thermonuclear"
    raise ReviewModeError(f"Unsupported review mode '{raw_mode}'. Allowed values: {allowed}.")


def review_level(mode: str) -> int | None:
    """Return the numeric review level for canonical level modes."""
    if match := re.fullmatch(r"level-([1-4])", mode):
        return int(match.group(1))
    return None


def resolve_review_profiles(
    mode: str,
    *,
    level_profiles: Mapping[str, tuple[str, ...]] | None = None,
    profile_templates: Mapping[str, str] | None = None,
) -> tuple[ReviewProfile, ...]:
    """Resolve a mode into named review passes, applying local template overrides."""
    templates = dict(DEFAULT_PROFILE_TEMPLATES)
    templates.update(profile_templates or {})
    profiles_by_level = dict(DEFAULT_LEVEL_PROFILES)
    profiles_by_level.update(level_profiles or {})
    level = review_level(mode)
    names = profiles_by_level[str(level)] if level else (mode,)
    missing = [name for name in names if name not in templates]
    if missing:
        raise ReviewModeError(f"No review template configured for: {', '.join(missing)}.")
    return tuple(
        ReviewProfile(
            name=name,
            title=_profile_title(name),
            instructions=templates[name].strip(),
        )
        for name in names
    )


def mode_prompt_hint(mode: str) -> str:
    """Return the combined focus text used by external agent command templates."""
    return "\n\n".join(profile.instructions for profile in resolve_review_profiles(mode))


def _profile_title(name: str) -> str:
    return name.replace("-", " ").title()
