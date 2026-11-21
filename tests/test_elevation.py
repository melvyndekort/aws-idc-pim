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


def test_resolve_target_account_id_known():
    assert elevation.resolve_target_account_id("management") == "075673041815"


def test_resolve_target_account_id_unknown_raises():
    with pytest.raises(elevation.ElevationError, match="Unknown target"):
        elevation.resolve_target_account_id("not-a-real-account")


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
