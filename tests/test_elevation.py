"""Tests for elevation.py's business logic, mocking boto3 throughout.

Scope deliberately kept to pure logic (target resolution, schedule naming,
error paths) rather than re-testing boto3/AWS itself -- moto doesn't model
sso-admin or scheduler, so the AWS-call paths are covered by mocking the
boto3 clients directly instead.
"""

# pylint: disable=missing-function-docstring,protected-access

from unittest.mock import MagicMock, patch

import pytest

from aws_idc_pim import elevation


def _organizations_client(names_to_ids, inactive=None):
    """A mock organizations client's list_accounts paginator, wired to
    resolve_target_account_id's expectations."""
    accounts = [
        {"Name": name, "Id": account_id, "Status": "ACTIVE"}
        for name, account_id in names_to_ids.items()
    ]
    for name in inactive or []:
        accounts.append({"Name": name, "Id": "000000000000", "Status": "SUSPENDED"})
    mock_organizations = MagicMock()
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [{"Accounts": accounts}]
    mock_organizations.get_paginator.return_value = mock_paginator
    return mock_organizations


@patch("aws_idc_pim.elevation.boto3")
def test_resolve_target_account_id_known(mock_boto3):
    mock_boto3.client.return_value = _organizations_client(
        {"management": "075673041815"}
    )
    assert elevation.resolve_target_account_id("management") == "075673041815"


@patch("aws_idc_pim.elevation.boto3")
def test_resolve_target_account_id_unknown_raises(mock_boto3):
    mock_boto3.client.return_value = _organizations_client(
        {"management": "075673041815"}
    )
    with pytest.raises(elevation.ElevationError, match="Unknown target"):
        elevation.resolve_target_account_id("not-a-real-account")


@patch("aws_idc_pim.elevation.boto3")
def test_resolve_target_account_id_ignores_inactive_accounts(mock_boto3):
    mock_boto3.client.return_value = _organizations_client(
        {"management": "075673041815"}, inactive=["closed-account"]
    )
    with pytest.raises(elevation.ElevationError, match="Unknown target"):
        elevation.resolve_target_account_id("closed-account")


def test_schedule_name_is_stable_and_safe():
    name = elevation._schedule_name("melvyn@mdekort.nl", "hermes-agent")
    assert name == "aws-idc-pim-revoke-melvyn-at-mdekort-nl-hermes-agent"
    assert len(name) <= 64


@patch("aws_idc_pim.elevation.boto3")
def test_resolve_principal_id_raises_when_no_user_found(mock_boto3):
    mock_sso_admin = MagicMock()
    mock_sso_admin.list_instances.return_value = {
        "Instances": [
            {"InstanceArn": "arn:aws:sso:::instance/ssoins-1", "IdentityStoreId": "d-1"}
        ]
    }
    mock_identitystore = MagicMock()
    mock_identitystore.list_users.return_value = {"Users": []}

    def client(name, **_kwargs):
        return {"sso-admin": mock_sso_admin, "identitystore": mock_identitystore}[name]

    mock_boto3.client.side_effect = client

    with pytest.raises(elevation.ElevationError, match="No Identity Center user"):
        elevation.resolve_principal_id("nobody@mdekort.nl")


@patch("aws_idc_pim.elevation.boto3")
def test_sso_admin_client_assumes_role_for_management_account(mock_boto3):
    mock_sts = MagicMock()
    mock_sts.assume_role.return_value = {
        "Credentials": {
            "AccessKeyId": "AKIA...",
            "SecretAccessKey": "secret",
            "SessionToken": "token",
        }
    }
    mock_boto3.client.side_effect = lambda name, **_kwargs: (
        mock_sts if name == "sts" else MagicMock()
    )

    elevation._sso_admin_client(elevation.MANAGEMENT_ACCOUNT_ID)

    mock_sts.assume_role.assert_called_once()
    assert (
        mock_sts.assume_role.call_args.kwargs["RoleArn"]
        == elevation.ROOT_ELEVATION_ROLE_ARN
    )


@patch("aws_idc_pim.elevation.boto3")
def test_sso_admin_client_uses_delegated_admin_for_workload_account(mock_boto3):
    elevation._sso_admin_client("520519513359")

    mock_boto3.client.assert_called_once_with("sso-admin")


def _permission_set_paginator(mock_sso_admin):
    """Wire list_permission_sets/describe_permission_set to resolve exactly
    one AdministratorAccess permission set, as _administrator_permission_set_arn
    expects."""
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [
        {"PermissionSets": ["arn:aws:sso:::permissionSet/ssoins-1/ps-admin"]}
    ]
    mock_sso_admin.get_paginator.return_value = mock_paginator
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {"Name": "AdministratorAccessJIT"}
    }


def _mock_clients(*, existing_assignments=None):
    """A full sso-admin/identitystore/scheduler mock set wired for the
    happy-path elevate()/revoke() flow: one known user, no pre-existing
    assignment (or the caller's own list), successful async status, and a
    missing schedule to delete (ResourceNotFoundException)."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.list_instances.return_value = {
        "Instances": [
            {"InstanceArn": "arn:aws:sso:::instance/ssoins-1", "IdentityStoreId": "d-1"}
        ]
    }
    _permission_set_paginator(mock_sso_admin)
    mock_sso_admin.list_account_assignments.return_value = {
        "AccountAssignments": existing_assignments or []
    }
    mock_sso_admin.create_account_assignment.return_value = {
        "AccountAssignmentCreationStatus": {"RequestId": "req-create"}
    }
    mock_sso_admin.delete_account_assignment.return_value = {
        "AccountAssignmentDeletionStatus": {"RequestId": "req-delete"}
    }
    mock_sso_admin.describe_account_assignment_creation_status.return_value = {
        "AccountAssignmentCreationStatus": {"Status": "SUCCEEDED"}
    }
    mock_sso_admin.describe_account_assignment_deletion_status.return_value = {
        "AccountAssignmentDeletionStatus": {"Status": "SUCCEEDED"}
    }

    mock_identitystore = MagicMock()
    mock_identitystore.list_users.return_value = {"Users": [{"UserId": "user-1"}]}

    mock_scheduler = MagicMock()

    class _ResourceNotFoundException(Exception):
        pass

    mock_scheduler.exceptions.ResourceNotFoundException = _ResourceNotFoundException
    mock_scheduler.delete_schedule.side_effect = _ResourceNotFoundException

    mock_organizations = MagicMock()
    mock_org_paginator = MagicMock()
    mock_org_paginator.paginate.return_value = [
        {
            "Accounts": [
                {"Name": "hermes-agent", "Id": "520519513359", "Status": "ACTIVE"}
            ]
        }
    ]
    mock_organizations.get_paginator.return_value = mock_org_paginator

    clients = {
        "sso-admin": mock_sso_admin,
        "identitystore": mock_identitystore,
        "scheduler": mock_scheduler,
        "organizations": mock_organizations,
    }
    return clients, mock_sso_admin, mock_scheduler


@patch("aws_idc_pim.elevation.boto3")
def test_elevate_happy_path_grants_and_schedules_revoke(mock_boto3):
    clients, mock_sso_admin, mock_scheduler = _mock_clients()
    mock_boto3.client.side_effect = lambda name, **_kwargs: clients[name]

    result = elevation.elevate("melvyn@mdekort.nl", "hermes-agent", 15)

    assert "Granted" in result
    mock_sso_admin.create_account_assignment.assert_called_once()
    mock_scheduler.create_schedule.assert_called_once()
    schedule_kwargs = mock_scheduler.create_schedule.call_args.kwargs
    assert schedule_kwargs["ActionAfterCompletion"] == "DELETE"


@patch("aws_idc_pim.elevation.boto3")
def test_elevate_skips_create_when_assignment_already_exists(mock_boto3):
    clients, mock_sso_admin, _ = _mock_clients(
        existing_assignments=[{"PrincipalId": "user-1"}]
    )
    mock_boto3.client.side_effect = lambda name, **_kwargs: clients[name]

    elevation.elevate("melvyn@mdekort.nl", "hermes-agent", 15)

    mock_sso_admin.create_account_assignment.assert_not_called()


@patch("aws_idc_pim.elevation.boto3")
def test_revoke_happy_path_deletes_and_cancels_schedule(mock_boto3):
    clients, mock_sso_admin, mock_scheduler = _mock_clients(
        existing_assignments=[{"PrincipalId": "user-1"}]
    )
    mock_boto3.client.side_effect = lambda name, **_kwargs: clients[name]

    result = elevation.revoke("melvyn@mdekort.nl", "hermes-agent")

    assert "Revoked" in result
    mock_sso_admin.delete_account_assignment.assert_called_once()
    mock_scheduler.delete_schedule.assert_called()


@patch("aws_idc_pim.elevation.boto3")
def test_revoke_reports_no_active_elevation(mock_boto3):
    clients, mock_sso_admin, _ = _mock_clients(existing_assignments=[])
    mock_boto3.client.side_effect = lambda name, **_kwargs: clients[name]

    result = elevation.revoke("melvyn@mdekort.nl", "hermes-agent")

    assert "No active elevation" in result
    mock_sso_admin.delete_account_assignment.assert_not_called()


@patch("aws_idc_pim.elevation.time")
@patch("aws_idc_pim.elevation.boto3")
def test_wait_for_status_raises_on_failed(mock_boto3, mock_time):
    mock_sso_admin = MagicMock()
    mock_sso_admin.describe_account_assignment_creation_status.return_value = {
        "AccountAssignmentCreationStatus": {"Status": "FAILED"}
    }
    mock_boto3.client.return_value = mock_sso_admin

    with pytest.raises(elevation.ElevationError, match="failed in AWS"):
        elevation._wait_for_status(
            mock_sso_admin,
            "describe_account_assignment_creation_status",
            "arn:aws:sso:::instance/ssoins-1",
            "req-1",
        )
    mock_time.sleep.assert_not_called()
