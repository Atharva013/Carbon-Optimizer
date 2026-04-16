# 🌱 Automated Carbon Footprint Optimization on AWS

> An automated system to track, analyze, and optimize cloud infrastructure's environmental impact using AWS Cost Explorer, EventBridge, Lambda, DynamoDB, and a real-time Dashboard.

---

## 📋 Table of Contents

- [🚀 Quick Deploy (Terraform)](#-quick-deploy-terraform)
- [Project Overview](#project-overview)
- [Architecture](#architecture)
- [Team & Responsibilities](#team--responsibilities)
- [Prerequisites](#prerequisites)
- [Repository Structure](#repository-structure)
- [Getting Started](#getting-started)
- [Deployment Guide](#deployment-guide)
- [Validation & Testing](#validation--testing)
- [Cleanup](#cleanup)
- [Contributing](#contributing)
- [Resources](#resources)

---

## 🚀 Quick Deploy (Terraform)

**Want to skip the step-by-step sections?** Deploy the entire stack in under 5 minutes:

```bash
git clone https://github.com/Atharva013/Carbon-Optimizer.git
cd Carbon-Optimizer/terraform
cp terraform.tfvars.example terraform.tfvars   # edit with your region/email
terraform init && terraform apply
```

After deployment, open the **Dashboard URL** shown in the output. For details, see the [Terraform README](terraform/README.md).

> ⚠️ Requires [Terraform ≥ 1.3](https://terraform.io) and [AWS CLI v2](https://aws.amazon.com/cli/) with configured credentials.

---

## Project Overview

This project creates an **automated carbon footprint optimization system** by integrating AWS Cost Explorer insights with sustainability analysis through EventBridge and Lambda. The system:

- 📊 Analyzes monthly cost and usage patterns automatically
- ♻️ Applies industry-standard carbon emission factors
- 💡 Generates optimization recommendations to reduce environmental impact and costs
- 🔔 Sends real-time alerts when high-impact optimization opportunities are found
- 🗄️ Stores historical sustainability metrics for trend analysis
- 🖥️ Visualizes all data through a real-time web dashboard hosted on S3

**Estimated Monthly Cost:** $15–25 USD (Lambda, DynamoDB, S3, SNS, API Gateway)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         DATA SOURCES                            │
│   Cost Explorer API   │   CUR Reports   │  Carbon Footprint Tool│
└──────────┬────────────┴────────┬────────┴────────────┬──────────┘
           │                     │                     │
           ▼                     ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                       AUTOMATION LAYER                          │
│      EventBridge Scheduler  ──►  Lambda Function  ◄──  S3       │
└───────────────────────────────┬─────────────────────────────────┘
                                │
           ┌────────────────────┼────────────────────┐
           ▼                    ▼                    ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│   DynamoDB       │  │   SNS Topic      │  │ Systems Manager  │
│  (Metrics Store) │  │ (Notifications)  │  │  (Config Store)  │
└──────────────────┘  └──────────────────┘  └──────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     DASHBOARD LAYER (Section 5)                 │
│   S3 Static Site  ◄──  API Gateway  ──►  Lambda (Data API)     │
│   Real-time Charts │ Metrics Display │ Recommendations Panel   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Team & Responsibilities

| Section | Responsibility | Member |
|---------|---------------|--------|
| [Section 1](sections/section-1-iam-dynamodb.md) | IAM Roles & DynamoDB Setup | Kehan Shaikh |
| [Section 2](sections/section-2-lambda.md) | Lambda Function Development | Soham Kulkarni |
| [Section 3](sections/section-3-sns-eventbridge.md) | SNS Notifications & EventBridge Schedules | Atharva Jadhav |
| [Section 4](sections/section-4-cur-ssm.md) | Cost & Usage Reports + SSM Configuration | Priyank Adhav |
| [Section 5](sections/section-5-dashboard.md) | Real-Time Dashboard & GUI | Atharva Jadhav |
| [Section 6](sections/section-6-testing-cleanup.md) | Validation, Testing & Cleanup | Abhishek Abhang |

> ⚠️ Sections must be deployed in order (1 → 2 → 3 → 4 → 5 → 6). Each section depends on the previous.

---

## Prerequisites

Before starting, ensure all team members have:

- [ ] AWS account with billing/cost management permissions
- [ ] AWS CLI v2 installed and configured (`aws --version`)
- [ ] Python 3.11+ installed
- [ ] Git installed and configured
- [ ] GitHub account with repo access
- [ ] IAM permissions for: Lambda, EventBridge, Cost Explorer, S3, DynamoDB, SNS, SSM, CUR, API Gateway

---

## Repository Structure

```
carbon-optimizer/
├── README.md                        # This file
├── CONTRIBUTING.md                  # Contribution guidelines
├── CHANGELOG.md                     # Version history
├── .gitignore                       # Ignored files
│
├── terraform/                       # ⚡ One-command deploy (recommended)
│   ├── main.tf                      # All AWS resources
│   ├── variables.tf                 # User configuration
│   ├── outputs.tf                   # Dashboard URL & endpoints
│   ├── terraform.tfvars.example     # Example config (copy to .tfvars)
│   └── README.md                    # Terraform quick-start guide
│
├── sections/                        # Per-member task breakdowns
│   ├── section-1-iam-dynamodb.md
│   ├── section-2-lambda.md
│   ├── section-3-sns-eventbridge.md
│   ├── section-4-cur-ssm.md
│   ├── section-5-dashboard.md
│   └── section-6-testing-cleanup.md
│
├── docs/                            # Project documentation
│   └── github-project-setup.md
│
├── lambda-function/                 # Lambda source code
│   └── index.py                     # Carbon footprint analyzer
│
├── dashboard/                       # Dashboard source (Section 5)
│   ├── index.html                   # Main dashboard UI
│   └── dashboard-api/
│       └── index.py                 # API Gateway Lambda
│
├── iam/                             # IAM policy documents
│   ├── lambda-trust-policy.json
│   └── lambda-permissions-policy.json
│
├── cloudformation/                  # CloudFormation templates
│   └── sustainable-infrastructure.yaml
│
├── scripts/                         # Shell deploy scripts (manual path)
│   ├── setup.sh                     # Initial resource creation
│   ├── deploy.sh                    # SNS + EventBridge + CUR + SSM
│   ├── deploy-dashboard.sh          # Dashboard Lambda + API + S3
│   ├── deploy-cloudfront.sh         # Optional HTTPS via CloudFront
│   ├── validate.sh                  # End-to-end validation
│   └── cleanup.sh                   # Delete all resources
│
└── .github/
    ├── workflows/
    │   └── validate.yml
    └── ISSUE_TEMPLATE/
        └── bug_report.md
```

---

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/Atharva013/Carbon-Optimizer.git
cd Carbon-Optimizer
```

### 2. Configure Environment

```bash
# Set your AWS region and account
export AWS_REGION=$(aws configure get region)
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Set project name (use the same suffix across all sessions!)
export PROJECT_NAME="carbon-optimizer-cloud"
export S3_BUCKET="${PROJECT_NAME}-data"
export LAMBDA_FUNCTION="${PROJECT_NAME}-analyzer"
export DYNAMODB_TABLE="${PROJECT_NAME}-metrics"

echo "Project: ${PROJECT_NAME}"
```

### 3. Follow Section Guides in Order

- **Kehan** → [`sections/section-1-iam-dynamodb.md`](sections/section-1-iam-dynamodb.md)
- **Soham** → [`sections/section-2-lambda.md`](sections/section-2-lambda.md)
- **Atharva** → [`sections/section-3-sns-eventbridge.md`](sections/section-3-sns-eventbridge.md)
- **Priyank** → [`sections/section-4-cur-ssm.md`](sections/section-4-cur-ssm.md)
- **Atharva** → [`sections/section-5-dashboard.md`](sections/section-5-dashboard.md)
- **Abhishek** → [`sections/section-6-testing-cleanup.md`](sections/section-6-testing-cleanup.md)

---

## Deployment Guide

### Option A — Terraform (Recommended) ⚡

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # edit with your values
terraform init
terraform apply
```

See [terraform/README.md](terraform/README.md) for full details.

### Option B — Shell Scripts (Step-by-step)

Run sections **in order** (Sections 1–5 deploy; Section 6 validates):

```bash
# Source environment
source .env   # or set exports manually

# Full deployment
bash scripts/setup.sh              # IAM + DynamoDB + S3
bash scripts/deploy.sh             # SNS + EventBridge + CUR + SSM
bash scripts/deploy-dashboard.sh   # Dashboard Lambda + API Gateway + S3 upload

# Optional: HTTPS via CloudFront (takes 5-10 minutes)
bash scripts/deploy-cloudfront.sh
```

---

## Validation & Testing

```bash
# Test Lambda execution
aws lambda invoke \
    --function-name ${LAMBDA_FUNCTION} \
    --payload '{}' response.json && cat response.json

# Verify DynamoDB data
aws dynamodb scan --table-name ${DYNAMODB_TABLE} --max-items 5

# List EventBridge schedules
aws scheduler list-schedules --name-prefix ${PROJECT_NAME}

# Run full validation suite (Section 6)
bash scripts/validate.sh
```

---

## Cleanup

```bash
# If deployed with Terraform:
cd terraform && terraform destroy

# If deployed with shell scripts:
bash scripts/cleanup.sh
```

> ⚠️ This permanently deletes all AWS resources created by this project.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for branch naming, commit conventions, and PR process.

Branch naming for each section:
```
feature/section-1-iam-dynamodb
feature/section-2-lambda
feature/section-3-sns-eventbridge
feature/section-4-cur-ssm
feature/section-5-dashboard
feature/section-6-testing-cleanup
```

---

## Resources

- [AWS Well-Architected Sustainability Pillar](https://docs.aws.amazon.com/wellarchitected/latest/sustainability-pillar/sustainability-pillar.html)
- [AWS Customer Carbon Footprint Tool](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/ccft-overview.html)
- [Cost Explorer API Reference](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/Welcome.html)
- [AWS Lambda Developer Guide](https://docs.aws.amazon.com/lambda/latest/dg/)
- [AWS API Gateway Developer Guide](https://docs.aws.amazon.com/apigateway/latest/developerguide/)
- [Amazon DynamoDB Developer Guide](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/)