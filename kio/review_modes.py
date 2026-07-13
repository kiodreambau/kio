"""Review levels, specialist passes, and guarded legacy modes for kio."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Mapping

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

# A reviewer request is the only GitHub trigger. The PR author selects the
# depth before requesting the reviewer by applying exactly one of these labels.
DEFAULT_REVIEW_LEVEL_LABELS: dict[str, str] = {
    "kio:1": "level-1",
    "kio:2": "level-2",
    "kio:3": "level-3",
    "kio:4": "level-4",
}

DEFAULT_PROFILE_TEMPLATES: dict[str, str] = {
    "basic": (
        "Perform a concise, high-confidence review of the changed behavior and its surrounding "
        "contract. Report only concrete defects or regressions introduced by this diff, with file "
        "and line evidence. Do not block for style preferences, speculative refactors, or pre-existing "
        "issues. Prioritize findings that would materially reduce code health, and say explicitly when "
        "no high-confidence issue is found. Do not claim that code paths, tests, or runtime behavior "
        "were verified unless the supplied evidence proves it; label relevant unchecked areas as Not verified."
    ),
    "correctness": (
        "Review correctness and changed user-visible behavior. Trace control flow, data flow, "
        "error handling, and backward compatibility. If the diff affects UI, also assess keyboard "
        "use, semantic structure, labels, focus handling, responsive layout, and other accessibility "
        "regressions. For each issue, identify the changed path that makes the behavior fail; do not "
        "raise generic accessibility advice when no relevant UI changed. If an interaction or layout "
        "cannot be exercised from the available evidence, label it Not verified rather than guessing."
    ),
    "test-density": (
        "Review test density and verification. Identify changed behavior without a focused test, "
        "weak assertions, missing edge cases, and mismatches with lint, type-check, or test tooling. "
        "Check whether a test would fail if the production behavior regressed. Do not demand tests "
        "where the changed behavior is already covered with strong evidence or where a test adds no value. "
        "State which existing test or command provides the evidence; otherwise mark the coverage as Not verified."
    ),
    "stability": (
        "Review stability and operational safety. Focus on failure paths, retries, state transitions, "
        "concurrency, idempotency, data loss, migrations, compatibility, observability, and safe "
        "degradation. Tie every finding to a plausible production failure path caused by this diff. "
        "Distinguish an evidenced regression from an operational path that remains Not verified."
    ),
    "performance": (
        "Review performance and scalability. Focus on avoidable repeated work, unbounded queries or "
        "loops, excess network or disk I/O, memory growth, and latency regressions that the diff can cause. "
        "For user-facing changes also consider perceived responsiveness on narrow mobile viewports. Avoid "
        "micro-optimizations without a concrete affected path. Do not invent measurements; mark performance "
        "claims that need profiling or device testing as Not verified."
    ),
    "frontend": (
        "Review UI behavior, accessibility, responsive layout, keyboard interaction, and user-facing regressions."
    ),
    "security": (
        "Review authentication, authorization, secrets, injection, data exposure, dependency, and supply-chain risk."
    ),
    "thermonuclear": (
        "Perform the deepest practical review across correctness, testing, stability, security, accessibility, "
        "and performance. Treat it as a local-only, explicitly requested escalation. De-duplicate findings, "
        "prioritize material risk, and keep every finding concrete, evidence-backed, and actionable."
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


def review_mode_from_labels(
    labels: Iterable[str],
    *,
    level_labels: Mapping[str, str] | None = None,
) -> str:
    """Resolve one configured review-level label, defaulting to Level 1."""
    configured = {
        label.strip().lower(): normalize_review_mode(mode)
        for label, mode in (level_labels or DEFAULT_REVIEW_LEVEL_LABELS).items()
        if label.strip()
    }
    selected = {
        configured[label.strip().lower()] for label in labels if label.strip().lower() in configured
    }
    if not selected:
        return DEFAULT_MODE
    if len(selected) > 1:
        names = ", ".join(sorted(selected))
        raise ReviewModeError(
            f"A pull request may have only one kio review-level label; found {names}."
        )
    return selected.pop()


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
