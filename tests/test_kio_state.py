from kio.state import ReviewState


def test_review_state_marks_completed(tmp_path):
    state = ReviewState(tmp_path / "reviews.json")

    assert not state.has_completed("repo#1@abc:standard")

    state.mark_completed(
        "repo#1@abc:standard",
        run_dir=tmp_path / "run",
        metadata={"backend": "gito"},
    )

    assert state.has_completed("repo#1@abc:standard")
