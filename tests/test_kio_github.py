from kio.github import post_pull_request_review


class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code
        self.reason = "OK"
        self.text = ""


def test_post_pull_request_review_submits_one_native_comment_review(mocker):
    post = mocker.patch("kio.github.requests.post", return_value=FakeResponse(200))

    posted = post_pull_request_review("owner/repo", 12, "token", "review body")

    assert posted is True
    post.assert_called_once_with(
        "https://api.github.com/repos/owner/repo/pulls/12/reviews",
        headers={
            "Authorization": "Bearer token",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"body": "review body", "event": "COMMENT"},
        timeout=30,
    )


def test_post_pull_request_review_returns_false_for_github_error(mocker):
    post = mocker.patch("kio.github.requests.post", return_value=FakeResponse(422))

    assert post_pull_request_review("owner/repo", 12, "token", "review body") is False
    post.assert_called_once()
