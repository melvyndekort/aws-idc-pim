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
  # Account IDs this Lambda is allowed to manage assignments for directly
  # (via delegated admin). The management account is deliberately excluded
  # here -- delegated admin can never manage assignments to it regardless
  # of IAM policy (AWS hard restriction), that path goes through the
  # separate root_elevation_role instead.
  workload_account_ids = [for name, id in var.target_accounts : id if name != "management"]
}

data "aws_iam_policy_document" "lambda_permissions" {
  statement {
    sid    = "ManageWorkloadAccountAssignments"
    effect = "Allow"
    # Despite being called via the boto3 "sso-admin" client, every one of
    # these operations is authorized under the "sso:" IAM action prefix,
    # not "sso-admin:" -- confirmed live (AccessDeniedException naming
    # "sso:ListInstances" explicitly) and in AWS's Service Authorization
    # Reference for "AWS IAM Identity Center" (prefix sso). There is no
    # separate "sso-admin" IAM action namespace for these operations.
    actions = [
      "sso:CreateAccountAssignment",
      "sso:DeleteAccountAssignment",
      "sso:DescribeAccountAssignmentCreationStatus",
      "sso:DescribeAccountAssignmentDeletionStatus",
      "sso:ListAccountAssignments",
      "sso:ListPermissionSets",
      "sso:DescribePermissionSet",
    ]
    # IAM Identity Center's sso-admin API is a known exception to normal
    # IAM wildcard behavior: for multi-resource actions like
    # CreateAccountAssignment, a bare Resource "*" is NOT sufficient --
    # confirmed live (AccessDeniedException persisted even with Resource
    # "*" granting the action). AWS's own example policies (see "Delegating
    # permission set management and account assignment in AWS IAM Identity
    # Center" security blog) always list the Instance, PermissionSet, and
    # Account resource types explicitly, never as "*". Must do the same.
    resources = concat(
      [local.sso_instance_arn],
      ["${replace(local.sso_instance_arn, "instance/", "permissionSet/")}/*"],
      [for id in local.workload_account_ids : "arn:aws:sso:::account/${id}"],
    )
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
