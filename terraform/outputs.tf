# =============================================================================
# Outputs — Displayed after terraform apply
# =============================================================================

output "dashboard_url" {
  description = "Dashboard URL (S3 static website — HTTP)"
  value       = "http://${aws_s3_bucket_website_configuration.data_bucket.website_endpoint}/dashboard/index.html"
}

output "api_endpoint" {
  description = "API Gateway endpoint for the Dashboard API"
  value       = "https://${aws_api_gateway_rest_api.dashboard.id}.execute-api.${var.aws_region}.amazonaws.com/prod"
}

output "api_health_check" {
  description = "Quick health check URL — open in browser to verify API"
  value       = "https://${aws_api_gateway_rest_api.dashboard.id}.execute-api.${var.aws_region}.amazonaws.com/prod/health"
}

output "analyzer_lambda" {
  description = "Analyzer Lambda function name — invoke manually to populate data"
  value       = aws_lambda_function.analyzer.function_name
}

output "dashboard_lambda" {
  description = "Dashboard API Lambda function name"
  value       = aws_lambda_function.dashboard_api.function_name
}

output "dynamodb_table" {
  description = "DynamoDB table storing carbon metrics"
  value       = aws_dynamodb_table.metrics.name
}

output "s3_bucket" {
  description = "S3 bucket for data storage and dashboard hosting"
  value       = aws_s3_bucket.data_bucket.id
}

output "sns_topic_arn" {
  description = "SNS Topic ARN for notifications"
  value       = aws_sns_topic.notifications.arn
}

output "next_steps" {
  description = "What to do after deployment"
  value       = <<-EOT

    ╔══════════════════════════════════════════════════════════════╗
    ║          🌱 Carbon Optimizer — Deployed Successfully!       ║
    ╚══════════════════════════════════════════════════════════════╝

    1. Open the Dashboard:
       ${format("http://%s/dashboard/index.html", aws_s3_bucket_website_configuration.data_bucket.website_endpoint)}

    2. Run the analyzer to populate data:
       aws lambda invoke --function-name ${aws_lambda_function.analyzer.function_name} \
         --payload '{}' /tmp/response.json && cat /tmp/response.json

    3. Check API health:
       curl -s https://${aws_api_gateway_rest_api.dashboard.id}.execute-api.${var.aws_region}.amazonaws.com/prod/health | python3 -m json.tool

    ${var.notification_email != "" ? format("4. Check %s for SNS confirmation email", var.notification_email) : ""}
  EOT
}
