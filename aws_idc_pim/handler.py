"""Lambda entry point: dispatches on event shape.

Three distinct callers invoke this one function, kept to one Lambda to
minimize operational surface (see
Tech/Homelab/planning/aws-idc-pim-2026-11-20.md):

1. Discord's HTTP Interactions endpoint (Lambda Function URL, synchronous).
   Must ACK within Discord's ~3s budget, so it only verifies the signature
   and returns PONG / a deferred response, then re-invokes itself
   asynchronously (InvocationType=Event) to do the real work.
2. Its own async self-invocation (`action: process_command`) -- does the
   actual AWS calls and edits the deferred response with the real result.
3. EventBridge Scheduler's one-time auto-revoke invocation
   (`action: scheduled_revoke`) -- fires after the requested duration.
"""

import json
import logging
import os

import boto3

from aws_idc_pim import discord_api, elevation
from aws_idc_pim.discord_verify import verify_discord_signature

logger = logging.getLogger()
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

DISCORD_PUBLIC_KEY = os.environ["DISCORD_PUBLIC_KEY"]
DISCORD_APPLICATION_ID = os.environ["DISCORD_APPLICATION_ID"]
# Discord user ID -> email, Terraform-managed (terraform/variables.tf).
# The Lambda refuses any command from a Discord user not in this map before
# touching AWS at all -- see Tech/Homelab/planning/aws-idc-pim-2026-11-20.md.
ALLOWED_USERS = json.loads(os.environ["ALLOWED_DISCORD_USERS"])
DEFAULT_DURATION_MINUTES = int(os.environ.get("DEFAULT_DURATION_MINUTES", "15"))

PING = 1
APPLICATION_COMMAND = 2
PONG = 1
CHANNEL_MESSAGE_WITH_SOURCE = 4
DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE = 5


def lambda_handler(event, context):
    """Route to the right handler based on which caller invoked this Lambda."""
    if _is_discord_invocation(event):
        return _handle_discord_invocation(event, context)
    if event.get("action") == "process_command":
        _process_command(event)
        return {}
    if event.get("action") == "scheduled_revoke":
        _handle_scheduled_revoke(event)
        return {}
    raise ValueError(f"Unrecognized event shape: {list(event.keys())}")


def _is_discord_invocation(event) -> bool:
    """True iff this invocation came from Discord's Function URL, not Scheduler/self."""
    return "headers" in event and "body" in event


def _handle_discord_invocation(event, context):
    """Verify + ACK synchronously; hand the real work to an async self-invoke."""
    headers = {k.lower(): v for k, v in event.get("headers", {}).items()}
    signature = headers.get("x-signature-ed25519", "")
    timestamp = headers.get("x-signature-timestamp", "")
    body = event.get("body", "")

    if not verify_discord_signature(DISCORD_PUBLIC_KEY, signature, timestamp, body):
        logger.warning("Rejected interaction with invalid signature")
        return {"statusCode": 401, "body": "invalid request signature"}

    interaction = json.loads(body)

    if interaction["type"] == PING:
        return _json_response({"type": PONG})

    if interaction["type"] == APPLICATION_COMMAND:
        discord_user_id = interaction["member"]["user"]["id"]
        if discord_user_id not in ALLOWED_USERS:
            logger.warning(
                "Rejected command from non-allow-listed user %s", discord_user_id
            )
            return _json_response(
                {
                    "type": CHANNEL_MESSAGE_WITH_SOURCE,
                    "data": {"content": "You are not authorized to use this bot."},
                }
            )

        _invoke_async(
            context, {"action": "process_command", "interaction": interaction}
        )
        return _json_response({"type": DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE})

    return _json_response(
        {
            "type": CHANNEL_MESSAGE_WITH_SOURCE,
            "data": {"content": "Unsupported interaction"},
        }
    )


def _process_command(event) -> None:
    """Do the real AWS work for a command and post the Discord followup."""
    interaction = event["interaction"]
    discord_user_id = interaction["member"]["user"]["id"]
    email = ALLOWED_USERS[discord_user_id]
    token = interaction["token"]

    data = interaction["data"]
    command = data["name"]
    options = {o["name"]: o["value"] for o in data.get("options", [])}
    target_name = options["target"]

    try:
        if command == "elevate":
            duration = int(options.get("duration", DEFAULT_DURATION_MINUTES))
            result = elevation.elevate(email, target_name, duration)
        elif command == "revoke":
            result = elevation.revoke(email, target_name)
        else:
            result = f"Unknown command: {command}"
    except elevation.ElevationError as exc:
        logger.warning("Elevation error for %s: %s", email, exc)
        result = f"Error: {exc}"
    except Exception:  # pylint: disable=broad-except
        logger.exception("Unexpected error processing command for %s", email)
        result = "An unexpected error occurred. Check CloudWatch Logs."

    discord_api.followup_message(DISCORD_APPLICATION_ID, token, result)


def _handle_scheduled_revoke(event) -> None:
    """Auto-revoke callback fired by the EventBridge Scheduler one-time rule."""
    email = event["email"]
    target_name = event["target_name"]
    logger.info("Auto-revoke firing for %s on %s", email, target_name)
    try:
        elevation.revoke(email, target_name)
    except elevation.ElevationError:
        logger.exception("Auto-revoke failed for %s on %s", email, target_name)


def _invoke_async(context, payload: dict) -> None:
    """Re-invoke this same Lambda asynchronously to do the slow AWS work."""
    lambda_client = boto3.client("lambda")
    lambda_client.invoke(
        FunctionName=context.invoked_function_arn,
        InvocationType="Event",
        Payload=json.dumps(payload).encode("utf-8"),
    )


def _json_response(body: dict):
    """Wrap a Discord interaction response body as a Function URL response."""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
