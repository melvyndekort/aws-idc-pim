"""Module-level env vars elevation.py/handler.py read at import time."""

import json
import os

os.environ.setdefault("MANAGEMENT_ACCOUNT_ID", "075673041815")
os.environ.setdefault(
    "ROOT_ELEVATION_ROLE_ARN", "arn:aws:iam::075673041815:role/IdcPimRootElevationRole"
)
os.environ.setdefault(
    "SCHEDULER_ROLE_ARN",
    "arn:aws:iam::397379012163:role/aws-idc-pim-scheduler-invoke-role",
)
os.environ.setdefault(
    "SCHEDULER_TARGET_LAMBDA_ARN",
    "arn:aws:lambda:eu-west-1:397379012163:function:aws-idc-pim",
)
os.environ.setdefault(
    "TARGET_ACCOUNTS",
    json.dumps(
        {
            "management": "075673041815",
            "hermes-agent": "520519513359",
            "network-monitor": "844347863910",
        }
    ),
)
os.environ.setdefault("DISCORD_PUBLIC_KEY", "0" * 64)
os.environ.setdefault("DISCORD_APPLICATION_ID", "123456789")
os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token")
os.environ.setdefault("ALLOWED_DISCORD_USERS", '{"111222333": "melvyn@mdekort.nl"}')
