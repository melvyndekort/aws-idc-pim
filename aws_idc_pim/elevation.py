"""IAM Identity Center JIT elevation: account assignments + auto-revoke.

Core AWS operations for the /elevate and /revoke commands. Deliberately
resolves the Identity Center instance ARN, the AdministratorAccessJIT
permission set ARN, and the requester's identitystore principal ID live on
every call rather than caching them in Terraform outputs or env vars --
these are cheap, infrequent calls, and resolving live means none of this
breaks if the permission set is ever recreated or the identity store user
is re-provisioned by Authentik's SCIM sync (see
Tech/Homelab/planning/aws-idc-pim-2026-11-20.md).

Uses a dedicated "AdministratorAccessJIT" permission set, never the
standing "AdministratorAccess" one the aws-users group has everyday access
through. Confirmed live: IAM Identity Center refuses to let a delegated
administrator manage ANY assignment for a permission set that has a
standing assignment to the management account, in ANY account -- not just
the management account itself. The standing permission set is tainted by
that management-account assignment; this bot's own permission set never
has one, so it's always manageable via delegated administration.
"""

import json
import logging
import os
import time
from datetime import UTC, datetime, timedelta

import boto3

logger = logging.getLogger()
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

PERMISSION_SET_NAME = "AdministratorAccessJIT"

MANAGEMENT_ACCOUNT_ID = os.environ["MANAGEMENT_ACCOUNT_ID"]
ROOT_ELEVATION_ROLE_ARN = os.environ["ROOT_ELEVATION_ROLE_ARN"]
SCHEDULER_ROLE_ARN = os.environ["SCHEDULER_ROLE_ARN"]
SCHEDULER_TARGET_LAMBDA_ARN = os.environ["SCHEDULER_TARGET_LAMBDA_ARN"]

# name -> account id, Terraform-managed (terraform/variables.tf), so a new
# workload account needs no code change here.
TARGET_ACCOUNTS = json.loads(os.environ["TARGET_ACCOUNTS"])


class ElevationError(Exception):
    """Raised for any user-facing failure in the elevate/revoke flow."""


def _sso_admin_client(target_account_id: str):
    """sso-admin client, assumed into the narrow root role for the
    management account, used directly (via delegated administration) for
    every other account."""
    if target_account_id == MANAGEMENT_ACCOUNT_ID:
        sts = boto3.client("sts")
        creds = sts.assume_role(
            RoleArn=ROOT_ELEVATION_ROLE_ARN,
            RoleSessionName="aws-idc-pim-elevation",
        )["Credentials"]
        return boto3.client(
            "sso-admin",
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        )
    return boto3.client("sso-admin")


def _instance_arn(sso_admin) -> str:
    instances = sso_admin.list_instances()["Instances"]
    if not instances:
        raise ElevationError("No IAM Identity Center instance found")
    return instances[0]["InstanceArn"]


def _administrator_permission_set_arn(sso_admin, instance_arn: str) -> str:
    paginator = sso_admin.get_paginator("list_permission_sets")
    for page in paginator.paginate(InstanceArn=instance_arn):
        for arn in page["PermissionSets"]:
            details = sso_admin.describe_permission_set(
                InstanceArn=instance_arn, PermissionSetArn=arn
            )["PermissionSet"]
            if details["Name"] == PERMISSION_SET_NAME:
                return arn
    raise ElevationError(f"Permission set {PERMISSION_SET_NAME} not found")


def resolve_principal_id(email: str) -> tuple[str, str, str]:
    """Look up the IAM Identity Center user ID for an email, live -- not
    cached, so an Authentik SCIM re-sync that recreates the user never goes
    stale here."""
    identitystore = boto3.client("identitystore")
    sso_admin = boto3.client("sso-admin")
    instance_arn = _instance_arn(sso_admin)
    identity_store_id = sso_admin.list_instances()["Instances"][0]["IdentityStoreId"]
    result = identitystore.list_users(
        IdentityStoreId=identity_store_id,
        Filters=[{"AttributePath": "UserName", "AttributeValue": email}],
    )
    users = result.get("Users", [])
    if not users:
        raise ElevationError(f"No Identity Center user found for {email}")
    return users[0]["UserId"], identity_store_id, instance_arn


def resolve_target_account_id(target_name: str) -> str:
    """Map a Discord command's `target` option to an AWS account ID."""
    account_id = TARGET_ACCOUNTS.get(target_name)
    if account_id is None:
        raise ElevationError(
            f"Unknown target '{target_name}'. Known: {', '.join(TARGET_ACCOUNTS)}"
        )
    return account_id


def elevate(email: str, target_name: str, duration_minutes: int) -> str:
    """Grant AdministratorAccess on target_name to email for duration_minutes,
    scheduling an automatic revoke. Returns a human-readable confirmation."""
    target_account_id = resolve_target_account_id(target_name)
    principal_id, _, instance_arn = resolve_principal_id(email)

    sso_admin = _sso_admin_client(target_account_id)
    permission_set_arn = _administrator_permission_set_arn(sso_admin, instance_arn)

    existing = sso_admin.list_account_assignments(
        InstanceArn=instance_arn,
        AccountId=target_account_id,
        PermissionSetArn=permission_set_arn,
    )["AccountAssignments"]
    if any(a["PrincipalId"] == principal_id for a in existing):
        logger.info("Assignment already exists for %s on %s", email, target_name)
    else:
        result = sso_admin.create_account_assignment(
            InstanceArn=instance_arn,
            TargetId=target_account_id,
            TargetType="AWS_ACCOUNT",
            PermissionSetArn=permission_set_arn,
            PrincipalId=principal_id,
            PrincipalType="USER",
        )
        request_id = result["AccountAssignmentCreationStatus"]["RequestId"]
        _wait_for_status(
            sso_admin,
            "describe_account_assignment_creation_status",
            instance_arn,
            request_id,
        )

    _schedule_revoke(
        email=email,
        target_name=target_name,
        target_account_id=target_account_id,
        principal_id=principal_id,
        permission_set_arn=permission_set_arn,
        instance_arn=instance_arn,
        duration_minutes=duration_minutes,
    )

    return (
        f"Granted **AdministratorAccess** on **{target_name}** to {email} "
        f"for {duration_minutes} minute(s). Auto-revokes automatically."
    )


def revoke(email: str, target_name: str) -> str:
    """Revoke AdministratorAccess on target_name for email right now, and
    cancel any pending auto-revoke schedule for it."""
    target_account_id = resolve_target_account_id(target_name)
    principal_id, _, instance_arn = resolve_principal_id(email)

    sso_admin = _sso_admin_client(target_account_id)
    permission_set_arn = _administrator_permission_set_arn(sso_admin, instance_arn)

    existing = sso_admin.list_account_assignments(
        InstanceArn=instance_arn,
        AccountId=target_account_id,
        PermissionSetArn=permission_set_arn,
    )["AccountAssignments"]
    if not any(a["PrincipalId"] == principal_id for a in existing):
        _cancel_schedule(email, target_name)
        return f"No active elevation found for {email} on **{target_name}**."

    result = sso_admin.delete_account_assignment(
        InstanceArn=instance_arn,
        TargetId=target_account_id,
        TargetType="AWS_ACCOUNT",
        PermissionSetArn=permission_set_arn,
        PrincipalId=principal_id,
        PrincipalType="USER",
    )
    request_id = result["AccountAssignmentDeletionStatus"]["RequestId"]
    _wait_for_status(
        sso_admin,
        "describe_account_assignment_deletion_status",
        instance_arn,
        request_id,
    )
    _cancel_schedule(email, target_name)

    return f"Revoked **AdministratorAccess** on **{target_name}** for {email}."


def _wait_for_status(
    sso_admin, describe_method: str, instance_arn: str, request_id: str
) -> None:
    """create/delete-account-assignment are async; poll briefly so the
    Discord followup can report a real outcome instead of 'submitted'."""
    describe = getattr(sso_admin, describe_method)
    status_key = (
        "AccountAssignmentCreationStatus"
        if "creation" in describe_method
        else "AccountAssignmentDeletionStatus"
    )
    for _ in range(10):
        status = describe(InstanceArn=instance_arn, RequestId=request_id)[status_key][
            "Status"
        ]
        if status == "SUCCEEDED":
            return
        if status == "FAILED":
            raise ElevationError("The account assignment operation failed in AWS")
        time.sleep(1)
    logger.warning("Assignment request %s still IN_PROGRESS after polling", request_id)


def _schedule_name(email: str, target_name: str) -> str:
    """Deterministic, 64-char-safe EventBridge Scheduler schedule name."""
    safe_email = email.replace("@", "-at-").replace(".", "-")
    return f"aws-idc-pim-revoke-{safe_email}-{target_name}"[:64]


def _schedule_revoke(  # pylint: disable=too-many-arguments
    *,
    email,
    target_name,
    target_account_id,
    principal_id,
    permission_set_arn,
    instance_arn,
    duration_minutes,
) -> None:
    """Create (or replace) the one-time auto-revoke schedule for this grant."""
    scheduler = boto3.client("scheduler")
    name = _schedule_name(email, target_name)
    run_at = (datetime.now(UTC) + timedelta(minutes=duration_minutes)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    payload = {
        "action": "scheduled_revoke",
        "email": email,
        "target_name": target_name,
        "target_account_id": target_account_id,
        "principal_id": principal_id,
        "permission_set_arn": permission_set_arn,
        "instance_arn": instance_arn,
    }
    try:
        scheduler.delete_schedule(Name=name)
    except scheduler.exceptions.ResourceNotFoundException:
        pass
    scheduler.create_schedule(
        Name=name,
        ScheduleExpression=f"at({run_at})",
        FlexibleTimeWindow={"Mode": "OFF"},
        ActionAfterCompletion="DELETE",
        Target={
            "Arn": SCHEDULER_TARGET_LAMBDA_ARN,
            "RoleArn": SCHEDULER_ROLE_ARN,
            "Input": json.dumps(payload),
        },
    )


def _cancel_schedule(email: str, target_name: str) -> None:
    """Delete the pending auto-revoke schedule for this grant, if any."""
    scheduler = boto3.client("scheduler")
    try:
        scheduler.delete_schedule(Name=_schedule_name(email, target_name))
    except scheduler.exceptions.ResourceNotFoundException:
        pass
