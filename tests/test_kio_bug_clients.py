from unittest.mock import Mock

import pytest

from kio.bug_clients import SlackApiClient


def test_slack_file_download_rejects_non_slack_hosts_before_network_access():
    session = Mock()
    client = SlackApiClient("xoxb-runtime-token", session=session)

    with pytest.raises(ValueError, match="Slack file host"):
        client.download_file("https://attacker.example/screenshot.png", max_bytes=1024)

    session.get.assert_not_called()
