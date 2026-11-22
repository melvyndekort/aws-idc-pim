data "archive_file" "placeholder_lambda" {
  type        = "zip"
  output_path = "lambda.zip"

  source {
    filename = "handler.py"
    content  = <<EOF
def lambda_handler(event, context):
  raise NotImplementedError
EOF
  }
}

resource "aws_lambda_function" "aws_idc_pim" {
  function_name = "aws-idc-pim"
  role          = aws_iam_role.lambda.arn
  handler       = "aws_idc_pim.handler.lambda_handler"
  runtime       = "python3.12"
  timeout       = 30
  memory_size   = 256

  # CI deploys real code via `aws lambda update-function-code`, same
  # pattern as every other Lambda repo here -- see
  # Makefile's `deploy` target and .github/workflows/pipeline-apply.yml.
  filename         = data.archive_file.placeholder_lambda.output_path
  source_code_hash = data.archive_file.placeholder_lambda.output_base64sha256

  environment {
    variables = {
      LOG_LEVEL               = var.log_level
      MANAGEMENT_ACCOUNT_ID   = var.management_account_id
      ROOT_ELEVATION_ROLE_ARN = var.root_elevation_role_arn
      SCHEDULER_ROLE_ARN      = aws_iam_role.scheduler_invoke.arn
      # Deliberately a literal string, not aws_lambda_function.aws_idc_pim.arn
      # -- Terraform forbids a resource referencing its own computed attribute
      # from within its own config ("Self-referential block", confirmed live
      # on this PR's first real plan). The ARN is fully deterministic from
      # account id + region + the function_name set two lines above, so the
      # literal is exact, not a guess.
      SCHEDULER_TARGET_LAMBDA_ARN = "arn:aws:lambda:eu-west-1:397379012163:function:aws-idc-pim"
      ALLOWED_DISCORD_USERS       = jsonencode(var.allowed_discord_users)
      DEFAULT_DURATION_MINUTES    = tostring(var.default_duration_minutes)
      DISCORD_PUBLIC_KEY          = local.secrets.discord_public_key
      DISCORD_APPLICATION_ID      = local.secrets.discord_application_id
      DISCORD_BOT_TOKEN           = local.secrets.discord_bot_token
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic,
    aws_iam_role_policy.lambda_permissions,
  ]

  lifecycle {
    ignore_changes = [
      filename,
      source_code_hash,
    ]
  }
}

resource "aws_lambda_function_url" "aws_idc_pim" {
  function_name      = aws_lambda_function.aws_idc_pim.function_name
  authorization_type = "NONE" # Discord can't sign with IAM SigV4; signature verified in-app instead.
}

# Lambda needs permission to invoke itself asynchronously (the deferred
# ack -> real-work self-invoke pattern in handler.py).
resource "aws_iam_role_policy" "lambda_self_invoke" {
  name = "self-invoke"
  role = aws_iam_role.lambda.id

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

# EventBridge Scheduler also needs permission to invoke it.
resource "aws_lambda_permission" "allow_scheduler" {
  statement_id  = "AllowExecutionFromScheduler"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.aws_idc_pim.function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = "arn:aws:scheduler:eu-west-1:397379012163:schedule/default/*"
}
