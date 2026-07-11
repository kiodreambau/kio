import pytest

from kio.review_modes import ReviewModeError, normalize_review_mode
from kio.triggers import parse_review_comment, trigger_from_reviewer_request


def test_parse_level_one_kiocheck_review():
    trigger = parse_review_comment(
        "@kiocheck review 1",
        bot_login="kiodreambau",
        trigger_handle="kiocheck",
    )

    assert trigger is not None
    assert trigger.mode == "level-1"
    assert trigger.source == "comment"


def test_parse_special_review_mode():
    trigger = parse_review_comment(
        "please @kiocheck review 4",
        bot_login="kiodreambau",
        trigger_handle="kiocheck",
        comment_id=42,
        author="dev",
    )

    assert trigger is not None
    assert trigger.mode == "level-4"
    assert trigger.comment_id == 42
    assert trigger.author == "dev"


def test_parse_ignores_other_review_handles():
    assert (
        parse_review_comment(
            "@kiodreambau review 1",
            bot_login="kiodreambau",
            trigger_handle="kiocheck",
        )
        is None
    )


def test_reviewer_request_defaults_to_level_one():
    trigger = trigger_from_reviewer_request(["alice", "kiodreambau"], bot_login="kiodreambau")

    assert trigger is not None
    assert trigger.mode == "level-1"
    assert trigger.source == "reviewer_request"


def test_thermonuclear_requires_local_gate():
    with pytest.raises(ReviewModeError):
        normalize_review_mode("thermonuclear")

    assert normalize_review_mode("thermonuclear", allow_thermonuclear=True) == "thermonuclear"


def test_unknown_review_mode_is_rejected():
    with pytest.raises(ReviewModeError):
        normalize_review_mode("whatever")


def test_explicit_legacy_mode_remains_available():
    trigger = parse_review_comment(
        "@kiocheck review tests",
        bot_login="kiodreambau",
        trigger_handle="kiocheck",
    )

    assert trigger is not None
    assert trigger.mode == "tests"
