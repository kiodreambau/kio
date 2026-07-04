"""Review mode validation for kio-triggered reviews."""

DEFAULT_MODE = "standard"

ALLOWED_MODES = {
    DEFAULT_MODE,
    "stability",
    "tests",
    "frontend",
    "security",
    "thermonuclear",
}


class ReviewModeError(ValueError):
    """Raised when a requested review mode is not allowed."""


def normalize_review_mode(raw_mode: str | None, *, allow_thermonuclear: bool = False) -> str:
    """Normalize and validate a review mode requested through GitHub."""
    mode = (raw_mode or DEFAULT_MODE).strip().lower().replace("_", "-")
    if not mode:
        mode = DEFAULT_MODE
    if mode not in ALLOWED_MODES:
        allowed = ", ".join(sorted(ALLOWED_MODES))
        raise ReviewModeError(f"Unsupported review mode '{mode}'. Allowed modes: {allowed}.")
    if mode == "thermonuclear" and not allow_thermonuclear:
        raise ReviewModeError("The thermonuclear review mode is disabled in local config.")
    return mode


def mode_prompt_hint(mode: str) -> str:
    """Return a short prompt hint for external agent backends."""
    hints = {
        "standard": "Review for high-confidence bugs, regressions, and maintainability issues.",
        "stability": "Focus on reliability, failure modes, data loss, retries, and race conditions.",
        "tests": "Focus on missing or weak tests for the behavior changed by this pull request.",
        "frontend": "Focus on UI behavior, accessibility, responsive layout, and user-facing regressions.",
        "security": "Focus on auth, authorization, secrets, injection, data exposure, and supply chain risk.",
        "thermonuclear": "Perform the deepest practical review. Be exhaustive, but keep findings actionable.",
    }
    return hints[mode]
