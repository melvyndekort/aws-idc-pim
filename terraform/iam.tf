# Lambda execution role. Named deterministically (aws-idc-pim-lambda-role)
# because tf-aws's management/identity-center-pim-root-role.tf trusts this
# exact name via a hardcoded ARN string -- see that file's comments for why
# a cross-repo Terraform reference isn't used.
resource "aws_iam_role" "lambda" {
  name = "aws-idc-pim-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
  role       = aws_iam_role.lambda.name
}

# IAM Identity Center delegated-administration grants most of this already
# (this account is registered as the delegated admin, tf-aws's
# management/identity_center.tf), but delegated admin status alone doesn't
# grant API permissions -- it only lifts the "must be the management
# account" restriction. The identity policy below is still required.
data "aws_ssoadmin_instances" "this" {}

locals {
  sso_instance_arn = tolist(data.aws_ssoadmin_instances.this.arns)[0]
}

data "aws_iam_policy_document" "lambda_permissions" {
  statement {
    # Account resource scoped to a wildcard, not an enumerated per-account
    # list: delegated administration already hard-blocks this identity
    # policy from reaching the management account regardless of what this
    # statement allows (AWS restricts management-account assignment
    # changes to the management account itself, confirmed live -- see
    # elevation.py's management-account-only ROOT_ELEVATION_ROLE_ARN path),
    # so a wildcard here only ever resolves to workload accounts in
    # practice. This is what lets a brand-new subaccount become a valid
    # /aws-elevate target with zero Terraform change in this repo.
    sid    = "ManageWorkloadAccountAssignments"
    effect = "Allow"
    actions = [
      "sso:CreateAccountAssignment",
      "sso:DeleteAccountAssignment",
      "sso:DescribeAccountAssignmentCreationStatus",
      "sso:DescribeAccountAssignmentDeletionStatus",
      "sso:ListAccountAssignments",
      "sso:ListPermissionSets",
      "sso:DescribePermissionSet",
    ]
    resources = [
      local.sso_instance_arn,
      "${replace(local.sso_instance_arn, "instance/", "permissionSet/")}/*",
      "arn:aws:sso:::account/*",
    ]
  }

  statement {
    sid       = "ListInstances"
    effect    = "Allow"
    actions   = ["sso:ListInstances"]
    resources = ["*"]
  }

  statement {
    sid       = "ResolveIdentityStorePrincipals"
    effect    = "Allow"
    actions   = ["identitystore:ListUsers"]
    resources = ["*"]
  }

  # organizations:ListAccounts resolves a Discord `target` name to an
  # account ID live (elevation.resolve_target_account_id) instead of a
  # Terraform-managed map. No resource-level restriction exists for this
  # action; the ability to call it at all is what matters, and it's
  # already an org-level read granted to any delegated-administrator
  # account (for any service), confirmed against AWS's own Organizations
  # docs on delegated-administrator permissions.
  statement {
    sid       = "ResolveTargetAccounts"
    effect    = "Allow"
    actions   = ["organizations:ListAccounts"]
    resources = ["*"]
  }

  statement {
    sid       = "AssumeRootElevationRole"
    effect    = "Allow"
    actions   = ["sts:AssumeRole"]
    resources = [var.root_elevation_role_arn]
  }

  statement {
    sid    = "ManageAutoRevokeSchedules"
    effect = "Allow"
    actions = [
      "scheduler:CreateSchedule",
      "scheduler:DeleteSchedule",
      "scheduler:GetSchedule",
    ]
    resources = ["arn:aws:scheduler:eu-west-1:397379012163:schedule/default/aws-idc-pim-revoke-*"]
  }

  statement {
    sid       = "PassSchedulerInvokeRole"
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.scheduler_invoke.arn]
  }
}

resource "aws_iam_role_policy" "lambda_permissions" {
  name   = "aws-idc-pim-permissions"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_permissions.json
}

# EventBridge Scheduler assumes this to invoke the Lambda target -- a
# distinct role from the Lambda's own, per AWS's standard Scheduler pattern
# (the scheduled event's "identity" is Scheduler itself, not the Lambda).
resource "aws_iam_role" "scheduler_invoke" {
  name = "aws-idc-pim-scheduler-invoke-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "scheduler.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "scheduler_invoke" {
  name = "invoke-lambda"
  role = aws_iam_role.scheduler_invoke.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "lambda:InvokeFunction"
        Resource = aws_lambda_function.aws_idc_pim.arn
      }
    ]
  })
}
