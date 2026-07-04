"""Parse GitHub-facing kio triggers."""

from dataclasses import dataclass
import re
from typing import Iterable, Literal

from .review_modes import normalize_review_mode

TriggerSource = Literal["comment", "reviewer_request", "manual"]


@dataclass(frozen=True)
class ReviewTrigger:
    source: TriggerSource
    mode: str
    raw_text: str = ""
    comment_id: int | None = None
    author: str | None = None


def parse_review_comment(
    text: str | None,
    *,
    bot_login: str,
    allow_thermonuclear: bool = False,
    comment_id: int | None = None,
    author: str | None = None,
) -> ReviewTrigger | None:
    """Return a review trigger for comments like '@kiodreambau review stability'."""
    if not text:
        return None
    login = re.escape(bot_login.lstrip("@"))
    pattern = re.compile(rf"(?i)(?:^|[\s>])@{login}\s+review(?:\s+([a-z0-9_-]+))?\b")
    match = pattern.search(text)
    if not match:
        return None
    mode = normalize_review_mode(
        match.group(1),
        allow_thermonuclear=allow_thermonuclear,
    )
    return ReviewTrigger(
        source="comment",
        mode=mode,
        raw_text=text,
        comment_id=comment_id,
        author=author,
    )


def trigger_from_reviewer_request(
    requested_reviewers: Iterable[str],
    *,
    bot_login: str,
    allow_thermonuclear: bool = False,
) -> ReviewTrigger | None:
    """Return the default review trigger if the kio account is requested as reviewer."""
    normalized = {reviewer.lower().lstrip("@") for reviewer in requested_reviewers}
    if bot_login.lower().lstrip("@") not in normalized:
        return None
    return ReviewTrigger(
        source="reviewer_request",
        mode=normalize_review_mode(None, allow_thermonuclear=allow_thermonuclear),
    )
