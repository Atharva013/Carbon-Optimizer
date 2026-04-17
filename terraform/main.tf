# =============================================================================
# Carbon Optimizer — Terraform Quick Deploy
# =============================================================================
# This Terraform configuration deploys the ENTIRE Carbon Optimizer stack:
#   - IAM Role + Policies for Lambda
#   - DynamoDB Table with GSI
#   - S3 Bucket (static website + CUR storage)
#   - Lambda Functions (analyzer + dashboard API)
#   - API Gateway (REST → Lambda proxy)
#   - EventBridge Schedules (monthly + weekly analysis)
#   - SNS Topic for notifications
#   - SSM Parameter for sustainability config
#   - Dashboard HTML deployed to S3 (with live API endpoint)
#
# Usage:
#   cd terraform
#   cp terraform.tfvars.example terraform.tfvars   # edit with your values
#   terraform init
#   terraform apply
# =============================================================================

terraform {
  required_version = ">= 1.3.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      ManagedBy   = "terraform"
      Environment = "production"
    }
  }
}

# We need a us-east-1 provider for CUR (it only works in us-east-1)
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}

# =============================================================================
# DATA SOURCES
# =============================================================================

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# =============================================================================
# IAM — Lambda Execution Role
# =============================================================================

resource "aws_iam_role" "lambda_role" {
  name = "${var.project_name}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "lambda_policy" {
  name = "CarbonOptimizationPolicy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "ce:GetCostAndUsage",
          "ce:GetDimensions",
          "ce:GetUsageReport",
          "ce:ListCostCategoryDefinitions",
          "cur:DescribeReportDefinitions"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.data_bucket.arn,
          "${aws_s3_bucket.data_bucket.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:Query", "dynamodb:Scan"]
        Resource = [
          aws_dynamodb_table.metrics.arn,
          "${aws_dynamodb_table.metrics.arn}/index/*"
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = aws_sns_topic.notifications.arn
      },
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:PutParameter", "ssm:GetParameters"]
        Resource = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/${var.project_name}/*"
      }
    ]
  })
}

# =============================================================================
# DynamoDB Table
# =============================================================================

resource "aws_dynamodb_table" "metrics" {
  name           = "${var.project_name}-metrics"
  billing_mode   = "PROVISIONED"
  read_capacity  = 5
  write_capacity = 5
  hash_key       = "MetricType"
  range_key      = "Timestamp"

  attribute {
    name = "MetricType"
    type = "S"
  }
  attribute {
    name = "Timestamp"
    type = "S"
  }
  attribute {
    name = "ServiceName"
    type = "S"
  }
  attribute {
    name = "CarbonIntensity"
    type = "N"
  }

  global_secondary_index {
    name            = "ServiceCarbonIndex"
    hash_key        = "ServiceName"
    range_key       = "CarbonIntensity"
    projection_type = "ALL"
    read_capacity   = 3
    write_capacity  = 3
  }
}

# =============================================================================
# S3 Bucket — Data + Static Website
# =============================================================================

resource "aws_s3_bucket" "data_bucket" {
  bucket        = "${var.project_name}-data"
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "data_bucket" {
  bucket = aws_s3_bucket.data_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data_bucket" {
  bucket = aws_s3_bucket.data_bucket.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_website_configuration" "data_bucket" {
  bucket = aws_s3_bucket.data_bucket.id
  index_document { suffix = "index.html" }
  error_document { key = "index.html" }
}

resource "aws_s3_bucket_public_access_block" "data_bucket" {
  bucket                  = aws_s3_bucket.data_bucket.id
  block_public_acls       = false
  ignore_public_acls      = false
  block_public_policy     = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "data_bucket" {
  bucket     = aws_s3_bucket.data_bucket.id
  depends_on = [aws_s3_bucket_public_access_block.data_bucket]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "CURGetBucketPermissions"
        Effect    = "Allow"
        Principal = { Service = "billingreports.amazonaws.com" }
        Action    = ["s3:GetBucketAcl", "s3:GetBucketPolicy"]
        Resource  = aws_s3_bucket.data_bucket.arn
      },
      {
        Sid       = "CURPutObject"
        Effect    = "Allow"
        Principal = { Service = "billingreports.amazonaws.com" }
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.data_bucket.arn}/cost-usage-reports/*"
      },
      {
        Sid       = "PublicDashboardRead"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.data_bucket.arn}/dashboard/*"
      }
    ]
  })
}

# =============================================================================
# SNS Topic
# =============================================================================

resource "aws_sns_topic" "notifications" {
  name = "${var.project_name}-notifications"
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.notification_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.notifications.arn
  protocol  = "email"
  endpoint  = var.notification_email
}

# =============================================================================
# SSM Parameter — Sustainability Config
# =============================================================================

resource "aws_ssm_parameter" "sustainability_config" {
  name = "/${var.project_name}/sustainability-config"
  type = "String"
  value = jsonencode({
    carbon_thresholds = {
      high_impact              = 50
      optimization_threshold   = 0.1
    }
    regional_preferences = {
      preferred_regions = ["us-west-2", "eu-north-1", "ca-central-1"]
      current_region    = var.aws_region
      avoid_regions     = []
    }
    optimization_rules = {
      graviton_migration   = true
      intelligent_tiering  = true
      serverless_first     = true
      right_sizing         = true
    }
    notification_settings = {
      email_threshold = 10
      weekly_summary  = true
    }
  })
}

# =============================================================================
# Lambda — Analyzer Function
# =============================================================================

data "archive_file" "analyzer_zip" {
  type        = "zip"
  source_file = "${path.module}/../lambda-function/index.py"
  output_path = "${path.module}/.build/analyzer.zip"
}

resource "aws_lambda_function" "analyzer" {
  function_name    = "${var.project_name}-analyzer"
  filename         = data.archive_file.analyzer_zip.output_path
  source_code_hash = data.archive_file.analyzer_zip.output_base64sha256
  handler          = "index.lambda_handler"
  runtime          = "python3.11"
  timeout          = 60
  memory_size      = 256
  role             = aws_iam_role.lambda_role.arn

  environment {
    variables = {
      DYNAMODB_TABLE = aws_dynamodb_table.metrics.name
      S3_BUCKET      = aws_s3_bucket.data_bucket.id
      SNS_TOPIC_ARN  = aws_sns_topic.notifications.arn
    }
  }
}

# =============================================================================
# Lambda — Dashboard API Function
# =============================================================================

data "archive_file" "dashboard_api_zip" {
  type        = "zip"
  source_file = "${path.module}/../dashboard/dashboard-api/index.py"
  output_path = "${path.module}/.build/dashboard-api.zip"
}

resource "aws_lambda_function" "dashboard_api" {
  function_name    = "${var.project_name}-dashboard-api"
  filename         = data.archive_file.dashboard_api_zip.output_path
  source_code_hash = data.archive_file.dashboard_api_zip.output_base64sha256
  handler          = "index.lambda_handler"
  runtime          = "python3.11"
  timeout          = 30
  memory_size      = 256
  role             = aws_iam_role.lambda_role.arn

  environment {
    variables = {
      DYNAMODB_TABLE = aws_dynamodb_table.metrics.name
    }
  }
}

# =============================================================================
# API Gateway — Dashboard REST API
# =============================================================================

resource "aws_api_gateway_rest_api" "dashboard" {
  name        = "${var.project_name}-dashboard-api"
  description = "Carbon Optimizer Dashboard API"
}

resource "aws_api_gateway_resource" "proxy" {
  rest_api_id = aws_api_gateway_rest_api.dashboard.id
  parent_id   = aws_api_gateway_rest_api.dashboard.root_resource_id
  path_part   = "{proxy+}"
}

resource "aws_api_gateway_method" "proxy" {
  rest_api_id   = aws_api_gateway_rest_api.dashboard.id
  resource_id   = aws_api_gateway_resource.proxy.id
  http_method   = "ANY"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "proxy" {
  rest_api_id             = aws_api_gateway_rest_api.dashboard.id
  resource_id             = aws_api_gateway_resource.proxy.id
  http_method             = aws_api_gateway_method.proxy.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.dashboard_api.invoke_arn
}

resource "aws_api_gateway_deployment" "prod" {
  rest_api_id = aws_api_gateway_rest_api.dashboard.id

  depends_on = [aws_api_gateway_integration.proxy]

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.proxy.id,
      aws_api_gateway_method.proxy.id,
      aws_api_gateway_integration.proxy.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "prod" {
  deployment_id = aws_api_gateway_deployment.prod.id
  rest_api_id   = aws_api_gateway_rest_api.dashboard.id
  stage_name    = "prod"
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.dashboard_api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.dashboard.execution_arn}/*/*"
}

# =============================================================================
# EventBridge Schedules
# =============================================================================

resource "aws_iam_role" "scheduler_role" {
  name = "${var.project_name}-scheduler-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "scheduler_invoke" {
  name = "InvokeLambdaPolicy"
  role = aws_iam_role.scheduler_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.analyzer.arn
    }]
  })
}

resource "aws_scheduler_schedule" "monthly" {
  name                         = "${var.project_name}-monthly-analysis"
  description                  = "Monthly carbon footprint optimization analysis"
  schedule_expression          = "rate(30 days)"
  schedule_expression_timezone = "UTC"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.analyzer.arn
    role_arn = aws_iam_role.scheduler_role.arn
  }
}

resource "aws_scheduler_schedule" "weekly" {
  name                         = "${var.project_name}-weekly-trends"
  description                  = "Weekly carbon footprint trend monitoring"
  schedule_expression          = "rate(7 days)"
  schedule_expression_timezone = "UTC"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.analyzer.arn
    role_arn = aws_iam_role.scheduler_role.arn
  }
}

# =============================================================================
# Dashboard HTML — Inject API endpoint & upload to S3
# =============================================================================

locals {
  api_endpoint = "https://${aws_api_gateway_rest_api.dashboard.id}.execute-api.${var.aws_region}.amazonaws.com/prod"

  dashboard_html = replace(
    file("${path.module}/../dashboard/index.html"),
    "API_ENDPOINT_PLACEHOLDER",
    local.api_endpoint
  )
}

resource "aws_s3_object" "dashboard_html" {
  bucket        = aws_s3_bucket.data_bucket.id
  key           = "dashboard/index.html"
  content       = local.dashboard_html
  content_type  = "text/html"
  cache_control = "no-cache, max-age=0"
  etag          = md5(local.dashboard_html)
}

# =============================================================================
# CloudFormation Template upload (reference only)
# =============================================================================

resource "aws_s3_object" "cfn_template" {
  bucket = aws_s3_bucket.data_bucket.id
  key    = "templates/sustainable-infrastructure.yaml"
  source = "${path.module}/../cloudformation/sustainable-infrastructure.yaml"
  etag   = filemd5("${path.module}/../cloudformation/sustainable-infrastructure.yaml")
}
