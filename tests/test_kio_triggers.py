import pytest

from kio.review_modes import ReviewModeError, normalize_review_mode
from kio.triggers import parse_review_comment, trigger_from_reviewer_request


def test_parse_standard_mention_review():
    trigger = parse_review_comment(
        "@kiodreambau review",
        bot_login="kiodreambau",
    )

    assert trigger is not None
    assert trigger.mode == "standard"
    assert trigger.source == "comment"


def test_parse_special_review_mode():
    trigger = parse_review_comment(
        "please @kiodreambau review stability",
        bot_login="kiodreambau",
        comment_id=42,
        author="dev",
    )

    assert trigger is not None
    assert trigger.mode == "stability"
    assert trigger.comment_id == 42
    assert trigger.author == "dev"


def test_parse_ignores_non_kio_review_text():
    assert parse_review_comment("@other review stability", bot_login="kiodreambau") is None


def test_reviewer_request_defaults_to_standard():
    trigger = trigger_from_reviewer_request(["alice", "kiodreambau"], bot_login="kiodreambau")

    assert trigger is not None
    assert trigger.mode == "standard"
    assert trigger.source == "reviewer_request"


def test_thermonuclear_requires_local_gate():
    with pytest.raises(ReviewModeError):
        normalize_review_mode("thermonuclear")

    assert normalize_review_mode("thermonuclear", allow_thermonuclear=True) == "thermonuclear"


def test_unknown_review_mode_is_rejected():
    with pytest.raises(ReviewModeError):
        normalize_review_mode("whatever")
