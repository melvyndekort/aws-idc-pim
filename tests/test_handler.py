"""Tests for handler.py's event dispatch and Discord interaction flow."""

# pylint: disable=missing-function-docstring,protected-access

import json
from unittest.mock import MagicMock, patch

from nacl.signing import SigningKey

from aws_idc_pim import handler


def _signed_request(signing_key, body_dict):
    body = json.dumps(body_dict)
    timestamp = "1700000000"
    signature = signing_key.sign((timestamp + body).encode("utf-8")).signature.hex()
    return {
        "headers": {
            "x-signature-ed25519": signature,
            "x-signature-timestamp": timestamp,
        },
        "body": body,
    }


def _keypair():
    signing_key = SigningKey.generate()
    return signing_key, signing_key.verify_key.encode().hex()


def test_rejects_invalid_signature():
    event = {
        "headers": {"x-signature-ed25519": "00", "x-signature-timestamp": "1700000000"},
        "body": "{}",
    }
    response = handler.lambda_handler(event, MagicMock())
    assert response["statusCode"] == 401


@patch("aws_idc_pim.handler.DISCORD_PUBLIC_KEY")
def test_ping_returns_pong(_unused_module_level_key):
    signing_key, public_key_hex = _keypair()
    with patch("aws_idc_pim.handler.DISCORD_PUBLIC_KEY", public_key_hex):
        event = _signed_request(signing_key, {"type": handler.PING})
        response = handler.lambda_handler(event, MagicMock())

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"type": handler.PONG}


def test_rejects_non_allowlisted_discord_user():
    signing_key, public_key_hex = _keypair()
    interaction = {
        "type": handler.APPLICATION_COMMAND,
        "member": {"user": {"id": "999999999"}},
        "data": {"name": "elevate", "options": []},
    }
    with patch("aws_idc_pim.handler.DISCORD_PUBLIC_KEY", public_key_hex):
        event = _signed_request(signing_key, interaction)
        response = handler.lambda_handler(event, MagicMock())

    body = json.loads(response["body"])
    assert "not authorized" in body["data"]["content"]


@patch("aws_idc_pim.handler.boto3")
def test_allowlisted_user_gets_deferred_ack_and_self_invoke(mock_boto3):
    signing_key, public_key_hex = _keypair()
    allowed_id = next(iter(handler.ALLOWED_USERS))
    interaction = {
        "type": handler.APPLICATION_COMMAND,
        "member": {"user": {"id": allowed_id}},
        "data": {
            "name": "elevate",
            "options": [{"name": "target", "value": "hermes-agent"}],
        },
    }
    mock_lambda_client = MagicMock()
    mock_boto3.client.return_value = mock_lambda_client

    with patch("aws_idc_pim.handler.DISCORD_PUBLIC_KEY", public_key_hex):
        event = _signed_request(signing_key, interaction)
        context = MagicMock(
            invoked_function_arn="arn:aws:lambda:eu-west-1:397379012163:function:aws-idc-pim"
        )
        response = handler.lambda_handler(event, context)

    assert json.loads(response["body"]) == {
        "type": handler.DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE
    }
    mock_lambda_client.invoke.assert_called_once()
    invoke_payload = json.loads(mock_lambda_client.invoke.call_args.kwargs["Payload"])
    assert invoke_payload["action"] == "process_command"


@patch("aws_idc_pim.handler.discord_api")
@patch("aws_idc_pim.handler.elevation")
def test_process_command_calls_elevate_and_posts_followup(
    mock_elevation, mock_discord_api
):
    mock_elevation.elevate.return_value = "Granted."
    allowed_id = next(iter(handler.ALLOWED_USERS))
    event = {
        "action": "process_command",
        "interaction": {
            "member": {"user": {"id": allowed_id}},
            "token": "interaction-token",
            "data": {
                "name": "elevate",
                "options": [
                    {"name": "target", "value": "hermes-agent"},
                    {"name": "duration", "value": 30},
                ],
            },
        },
    }

    handler._process_command(event)

    mock_elevation.elevate.assert_called_once_with(
        handler.ALLOWED_USERS[allowed_id], "hermes-agent", 30
    )
    mock_discord_api.followup_message.assert_called_once_with(
        handler.DISCORD_APPLICATION_ID, "interaction-token", "Granted."
    )


@patch("aws_idc_pim.handler.elevation")
def test_scheduled_revoke_calls_revoke(mock_elevation):
    event = {
        "action": "scheduled_revoke",
        "email": "melvyn@mdekort.nl",
        "target_name": "hermes-agent",
    }

    handler._handle_scheduled_revoke(event)

    mock_elevation.revoke.assert_called_once_with("melvyn@mdekort.nl", "hermes-agent")
