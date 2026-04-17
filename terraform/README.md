# 🌱 Carbon Optimizer — Terraform Quick Deploy

Deploy the **entire Carbon Optimizer stack** to your AWS account in under 5 minutes.

## Prerequisites

| Tool | Version | Installation |
|------|---------|-------------|
| [Terraform](https://terraform.io) | ≥ 1.3.0 | `brew install terraform` or [download](https://developer.hashicorp.com/terraform/downloads) |
| [AWS CLI](https://aws.amazon.com/cli/) | v2 | `brew install awscli` or [download](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) |
| AWS Account | Free tier OK | [Sign up](https://aws.amazon.com/free/) |

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/Atharva013/Carbon-Optimizer.git
cd Carbon-Optimizer/terraform

# 2. Configure your deployment
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your preferred region and email

# 3. Configure AWS credentials (if not already done)
aws configure
# Enter your Access Key ID, Secret Access Key, and region

# 4. Deploy everything
terraform init
terraform plan          # Preview what will be created
terraform apply         # Type 'yes' to confirm

# 5. Open the dashboard URL from the output!
```

## What Gets Deployed

```
┌─────────────────────────────────────────────────────────┐
│                    AWS Account                          │
│                                                         │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────┐  │
│  │EventBridge│───▶│  Lambda   │───▶│    DynamoDB      │  │
│  │ Schedules │    │ Analyzer  │    │ (Carbon Metrics) │  │
│  └──────────┘    └──────────┘    └──────────────────┘  │
│                       │                    ▲             │
│                       ▼                    │             │
│                  ┌──────────┐    ┌──────────────────┐  │
│                  │   SNS    │    │   Lambda          │  │
│                  │  Alerts  │    │   Dashboard API   │  │
│                  └──────────┘    └────────▲─────────┘  │
│                                           │             │
│  ┌──────────────────┐          ┌──────────────────┐    │
│  │   S3 Bucket       │          │   API Gateway    │    │
│  │  (Dashboard HTML) │◀─────────│   (REST API)     │    │
│  └──────────────────┘          └──────────────────┘    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

| Resource | Purpose |
|----------|---------|
| **IAM Role** | Lambda execution permissions |
| **DynamoDB** | Stores carbon footprint metrics |
| **S3 Bucket** | Dashboard hosting + CUR data |
| **Lambda (Analyzer)** | Analyzes AWS costs → carbon emissions |
| **Lambda (Dashboard API)** | REST API serving live data |
| **API Gateway** | HTTPS endpoint for dashboard |
| **EventBridge** | Monthly + weekly automated analysis |
| **SNS Topic** | Email alerts for optimization opportunities |
| **SSM Parameter** | Sustainability configuration |

## Configuration

Edit `terraform.tfvars` before deploying:

| Variable | Default | Description |
|----------|---------|-------------|
| `aws_region` | `ap-south-1` | AWS region for all resources |
| `project_name` | `carbon-optimizer-cloud` | Prefix for all resource names |
| `notification_email` | `""` | Email for alerts (optional) |

## After Deployment

1. **Open the dashboard** — the URL is shown in the Terraform output
2. **Run the analyzer** to populate the cached billing snapshot:
   ```bash
   aws lambda invoke \
     --function-name carbon-optimizer-cloud-analyzer \
     --payload '{}' /tmp/response.json && cat /tmp/response.json
   ```
3. **Confirm SNS email** (if you provided one) by clicking the link in the AWS notification email
4. **Open the dashboard again** — it now reads the DynamoDB snapshot instead of querying Cost Explorer on every refresh

## Customization

### Change Region
```hcl
aws_region = "us-west-2"    # Oregon — lower carbon intensity!
```

### Multiple Environments
```hcl
project_name = "carbon-optimizer-staging"   # Creates separate resources
```

## Cleanup

Remove all AWS resources when done:

```bash
terraform destroy    # Type 'yes' to confirm
```

> ⚠️ This permanently deletes all resources including stored metrics data.

## Security Notes

- **No secrets in code** — all credentials come from your local AWS CLI config
- **`terraform.tfvars` is gitignored** — your configuration never gets committed
- **IAM follows least privilege** — Lambda role only has permissions it needs
- **S3 public access** is limited to the `/dashboard/` prefix only

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `AccessDenied` on `ce:GetCostAndUsage` | Your IAM user needs `ce:*` permissions |
| Dashboard shows no data | Run the analyzer Lambda manually (see step 2) |
| SNS email not received | Confirm the email subscription, then invoke the analyzer once. Alerts send when usage crosses the configured threshold or high-impact actions are found |
| `BucketAlreadyExists` | Change `project_name` in tfvars to a unique name |
