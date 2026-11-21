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
      "sso:ListInstances",
      "sso:ListPermissionSets",
      "sso:DescribePermissionSet",
    ]
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
