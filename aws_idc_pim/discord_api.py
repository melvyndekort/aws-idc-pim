"""Minimal Discord REST calls: interaction responses + followup webhooks.

No discord.py/py-cord dependency -- this bot only ever responds to
slash-command interactions, so the two REST calls below (immediate
response, deferred followup) are all it needs. Keeping the dependency
surface this small is deliberate: see
Tech/Homelab/planning/aws-idc-pim-2026-11-20.md on why a full gateway bot
library was rejected for this use case.
"""

import json
import os

import urllib3

DISCORD_API_BASE = "https://discord.com/api/v10"

_http = urllib3.PoolManager()


def followup_message(application_id: str, interaction_token: str, content: str) -> None:
    """Edit the original deferred response with the real result.

    https://discord.com/developers/docs/interactions/receiving-and-responding#followup-messages
    """
    url = f"{DISCORD_API_BASE}/webhooks/{application_id}/{interaction_token}/messages/@original"
    _http.request(
        "PATCH",
        url,
        body=json.dumps({"content": content}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )


def channel_message(channel_id: str, content: str) -> None:
    """Post a standalone message, used for the auto-revoke notification --
    there is no interaction token to follow up on by the time a scheduled
    revoke fires."""
    bot_token = os.environ["DISCORD_BOT_TOKEN"]
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
    _http.request(
        "POST",
        url,
        body=json.dumps({"content": content}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bot {bot_token}",
        },
    )
