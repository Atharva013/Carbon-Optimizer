# =============================================================================
# Variables — User Configuration
# =============================================================================
# Copy terraform.tfvars.example → terraform.tfvars and edit to match your setup.
# NEVER commit terraform.tfvars — it's gitignored for your safety.
# =============================================================================

variable "aws_region" {
  description = "AWS region for deployment. Choose a region close to your users."
  type        = string
  default     = "ap-south-1"

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-\\d+$", var.aws_region))
    error_message = "Must be a valid AWS region code (e.g. us-east-1, ap-south-1)."
  }
}

variable "project_name" {
  description = "Project name used as prefix for all AWS resources. Must be lowercase with hyphens."
  type        = string
  default     = "carbon-optimizer-cloud"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]+$", var.project_name))
    error_message = "Project name must be lowercase letters, numbers, and hyphens."
  }
}

variable "notification_email" {
  description = "Email address for carbon optimization alert notifications. Leave empty to skip SNS subscription."
  type        = string
  default     = ""
}
