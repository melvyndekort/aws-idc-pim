"""Tests for discord_api.py's two REST calls, mocking the urllib3 pool."""

# pylint: disable=missing-function-docstring

import json
from unittest.mock import patch

from aws_idc_pim import discord_api


@patch("aws_idc_pim.discord_api._http")
def test_followup_message_sends_patch(mock_http):
    discord_api.followup_message("app-id", "token-abc", "Granted.")

    mock_http.request.assert_called_once()
    args, kwargs = mock_http.request.call_args
    assert args[0] == "PATCH"
    assert "app-id" in args[1]
    assert "token-abc" in args[1]
    assert json.loads(kwargs["body"]) == {"content": "Granted."}


@patch("aws_idc_pim.discord_api._http")
def test_channel_message_sends_post_with_bot_token(mock_http):
    discord_api.channel_message("channel-123", "Auto-revoked.")

    mock_http.request.assert_called_once()
    args, kwargs = mock_http.request.call_args
    assert args[0] == "POST"
    assert "channel-123" in args[1]
    assert kwargs["headers"]["Authorization"].startswith("Bot ")
    assert json.loads(kwargs["body"]) == {"content": "Auto-revoked."}
