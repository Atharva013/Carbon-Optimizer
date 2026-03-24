# 🌱 Automated Carbon Footprint Optimization on AWS

> An automated system to track, analyze, and optimize cloud infrastructure's environmental impact using AWS Cost Explorer, EventBridge, Lambda, and DynamoDB.

---

## 📋 Table of Contents

- [Project Overview](#project-overview)
- [Architecture](#architecture)
- [Team & Responsibilities](#team--responsibilities)
- [Prerequisites](#prerequisites)
- [Repository Structure](#repository-structure)
- [Getting Started](#getting-started)
- [Environment Setup](#environment-setup)
- [Deployment Guide](#deployment-guide)
- [Validation & Testing](#validation--testing)
- [Cleanup](#cleanup)
- [Contributing](#contributing)
- [Resources](#resources)

---

## Project Overview

This project creates an **automated carbon footprint optimization system** by integrating AWS Cost Explorer insights with sustainability analysis through EventBridge and Lambda. The system:

- 📊 Analyzes monthly cost and usage patterns automatically
- ♻️ Applies industry-standard carbon emission factors
- 💡 Generates optimization recommendations to reduce environmental impact and costs
- 🔔 Sends real-time alerts when high-impact optimization opportunities are found
- 🗄️ Stores historical sustainability metrics for trend analysis

**Estimated Monthly Cost:** $15–25 USD (Lambda, DynamoDB, S3, SNS)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         DATA SOURCES                            │
│   Cost Explorer API   │   CUR Reports   │   Carbon Footprint Tool│
└──────────┬────────────┴────────┬────────┴────────────┬──────────┘
           │                    │                      │
           ▼                    ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                       AUTOMATION LAYER                           │
│      EventBridge Scheduler  ──►  Lambda Function  ◄──  S3       │
└───────────────────────────────┬─────────────────────────────────┘
                                │
           ┌────────────────────┼────────────────────┐
           ▼                    ▼                     ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│   DynamoDB       │  │   SNS Topic      │  │ Systems Manager  │
│  (Metrics Store) │  │ (Notifications)  │  │  (Config Store)  │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

---

## Team & Responsibilities

| Section | Responsibility | Member |
|---------|---------------|--------|
| [Section 1](sections/section-1-iam-dynamodb.md) | IAM Roles & DynamoDB Setup | Team Member 1 |
| [Section 2](sections/section-2-lambda.md) | Lambda Function Development | Team Member 2 |
| [Section 3](sections/section-3-sns-eventbridge.md) | SNS Notifications & EventBridge Schedules | Team Member 3 |
| [Section 4](sections/section-4-cur-ssm.md) | Cost & Usage Reports + SSM Configuration | Team Member 4 |
| [Section 5](sections/section-5-testing-cleanup.md) | Validation, Testing & Cleanup | Team Member 5 |

---

## Prerequisites

Before starting, ensure all team members have:

- [ ] AWS account with billing/cost management permissions
- [ ] AWS CLI v2 installed and configured (`aws --version`)
- [ ] Python 3.11+ installed
- [ ] Git installed and configured
- [ ] GitHub account with repo access
- [ ] IAM permissions for: Lambda, EventBridge, Cost Explorer, S3, DynamoDB, SNS, SSM, CUR

---

## Repository Structure

```
carbon-optimizer/
├── README.md                        # This file
├── CONTRIBUTING.md                  # Contribution guidelines
├── CHANGELOG.md                     # Version history
├── .gitignore                       # Ignored files
│
├── sections/                        # Per-member task breakdowns
│   ├── section-1-iam-dynamodb.md
│   ├── section-2-lambda.md
│   ├── section-3-sns-eventbridge.md
│   ├── section-4-cur-ssm.md
│   └── section-5-testing-cleanup.md
│
├── docs/                            # Project documentation
│   ├── architecture.md
│   ├── environment-setup.md
│   └── github-project-setup.md
│
├── lambda-function/                 # Lambda source code
│   └── index.py
│
├── iam/                             # IAM policy documents
│   ├── lambda-trust-policy.json
│   └── lambda-permissions-policy.json
│
├── cloudformation/                  # CloudFormation templates
│   └── sustainable-infrastructure.yaml
│
├── scripts/                         # Helper shell scripts
│   ├── setup.sh
│   ├── deploy.sh
│   └── cleanup.sh
│
└── .github/
    ├── workflows/
    │   └── validate.yml             # CI validation
    └── ISSUE_TEMPLATE/
        ├── bug_report.md
        └── feature_request.md
```

---

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/<your-org>/carbon-optimizer.git
cd carbon-optimizer
```

### 2. Configure Environment

```bash
# Set your AWS region and account
export AWS_REGION=$(aws configure get region)
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Generate unique project name
RANDOM_SUFFIX=$(cat /dev/urandom | tr -dc 'a-z0-9' | fold -w 6 | head -n 1)
export PROJECT_NAME="carbon-optimizer-${RANDOM_SUFFIX}"
export S3_BUCKET="${PROJECT_NAME}-data"
export LAMBDA_FUNCTION="${PROJECT_NAME}-analyzer"
export DYNAMODB_TABLE="${PROJECT_NAME}-metrics"

echo "Project: ${PROJECT_NAME}"
```

### 3. Follow Section Guides

Each team member should follow their assigned section guide:

- **Member 1** → [`sections/section-1-iam-dynamodb.md`](sections/section-1-iam-dynamodb.md)
- **Member 2** → [`sections/section-2-lambda.md`](sections/section-2-lambda.md)
- **Member 3** → [`sections/section-3-sns-eventbridge.md`](sections/section-3-sns-eventbridge.md)
- **Member 4** → [`sections/section-4-cur-ssm.md`](sections/section-4-cur-ssm.md)
- **Member 5** → [`sections/section-5-testing-cleanup.md`](sections/section-5-testing-cleanup.md)

---

## Deployment Guide

Run sections **in order** (Sections 1–4 deploy; Section 5 validates):

```bash
# Full deployment (run as team lead after all PRs merged)
bash scripts/setup.sh
bash scripts/deploy.sh
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
```

---

## Cleanup

```bash
# Remove all deployed resources
bash scripts/cleanup.sh
```

> ⚠️ This deletes all AWS resources created by this project. Confirm before running.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for branch naming, commit conventions, and PR process.

---

## Resources

- [AWS Well-Architected Sustainability Pillar](https://docs.aws.amazon.com/wellarchitected/latest/sustainability-pillar/sustainability-pillar.html)
- [AWS Customer Carbon Footprint Tool](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/ccft-overview.html)
- [Cost Explorer API Reference](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/Welcome.html)
- [AWS Lambda Developer Guide](https://docs.aws.amazon.com/lambda/latest/dg/)
