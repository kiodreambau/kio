"""Parse GitHub-facing kio triggers."""

from dataclasses import dataclass
import re
from typing import Iterable, Literal, Mapping

from .review_modes import normalize_review_mode, review_mode_from_labels

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
    trigger_handle: str | None = None,
    allow_thermonuclear: bool = False,
    comment_id: int | None = None,
    author: str | None = None,
) -> ReviewTrigger | None:
    """Return a review trigger for comments like '@kiocheck review 4'."""
    if not text:
        return None
    handle = re.escape((trigger_handle or bot_login).lstrip("@"))
    pattern = re.compile(rf"(?i)(?:^|[\s>])@{handle}\s+review(?:\s+(?:level\s*)?([a-z0-9_-]+))?\b")
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
    labels: Iterable[str] = (),
    review_level_labels: Mapping[str, str] | None = None,
    allow_thermonuclear: bool = False,
) -> ReviewTrigger | None:
    """Return a label-scoped trigger when the kio account is requested as reviewer."""
    labels = tuple(labels)
    normalized = {reviewer.lower().lstrip("@") for reviewer in requested_reviewers}
    if bot_login.lower().lstrip("@") not in normalized:
        return None
    mode = review_mode_from_labels(labels, level_labels=review_level_labels)
    return ReviewTrigger(
        source="reviewer_request",
        mode=normalize_review_mode(mode, allow_thermonuclear=allow_thermonuclear),
        raw_text="review request" + (f" ({', '.join(labels)})" if labels else ""),
    )
