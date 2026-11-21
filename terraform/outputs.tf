output "lambda_function_arn" {
  description = "ARN of the aws-idc-pim Lambda function"
  value       = aws_lambda_function.aws_idc_pim.arn
}

output "function_url" {
  description = "Lambda Function URL -- register this as the Discord Application's Interactions Endpoint URL"
  value       = aws_lambda_function_url.aws_idc_pim.function_url
}
