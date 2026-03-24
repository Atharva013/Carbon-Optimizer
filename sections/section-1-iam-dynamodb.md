# Section 1 — IAM Roles & DynamoDB Setup

**Assigned To:** Team Member 1  
**Estimated Time:** 2–3 hours  
**Branch:** `feature/section-1-iam-dynamodb`  
**Dependencies:** None (this section must be completed first)

---

## 🎯 Objective

Set up the security foundation and data storage layer for the carbon footprint optimization project. This includes creating the IAM role for Lambda and provisioning the DynamoDB table with appropriate indexes.

---

## ✅ Prerequisites

Before starting, confirm you have:

- [ ] AWS CLI v2 installed: `aws --version`
- [ ] Valid AWS credentials configured: `aws sts get-caller-identity`
- [ ] IAM permissions to create roles, policies, and DynamoDB tables
- [ ] Project environment variables exported (see main README):
  ```bash
  export AWS_REGION=<your-region>
  export AWS_ACCOUNT_ID=<your-account-id>
  export PROJECT_NAME=carbon-optimizer-<suffix>
  export DYNAMODB_TABLE=${PROJECT_NAME}-metrics
  export S3_BUCKET=${PROJECT_NAME}-data
  ```
- [ ] Repository cloned locally and on branch `feature/section-1-iam-dynamodb`

---

## 📁 Files You Will Create

```
carbon-optimizer/
├── iam/
│   ├── lambda-trust-policy.json
│   └── lambda-permissions-policy.json
└── scripts/
    └── setup.sh   (partial — S3 bucket creation)
```

---

## 🔨 Tasks

### Task 1.1 — Create S3 Bucket for Data Storage

**Commit message:** `feat(s3): create encrypted versioned data bucket`

```bash
# Create S3 bucket
aws s3 mb s3://${S3_BUCKET} --region ${AWS_REGION}

# Enable versioning
aws s3api put-bucket-versioning \
    --bucket ${S3_BUCKET} \
    --versioning-configuration Status=Enabled

# Enable server-side encryption
aws s3api put-bucket-encryption \
    --bucket ${S3_BUCKET} \
    --server-side-encryption-configuration \
    'Rules=[{ApplyServerSideEncryptionByDefault:{SSEAlgorithm:AES256}}]'

echo "✅ S3 bucket created: ${S3_BUCKET}"
```

**Expected Output:**
```
make_bucket: carbon-optimizer-<suffix>-data
✅ S3 bucket created: carbon-optimizer-<suffix>-data
```

---

### Task 1.2 — Create IAM Trust Policy File

**Commit message:** `feat(iam): add lambda trust policy document`

Create the file `iam/lambda-trust-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

---

### Task 1.3 — Create IAM Permissions Policy File

**Commit message:** `feat(iam): add lambda permissions policy document`

Create `iam/lambda-permissions-policy.json` (substitute env vars before committing):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ce:GetCostAndUsage",
        "ce:GetDimensions",
        "ce:GetUsageReport",
        "ce:ListCostCategoryDefinitions",
        "cur:DescribeReportDefinitions"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::BUCKET_NAME_PLACEHOLDER",
        "arn:aws:s3:::BUCKET_NAME_PLACEHOLDER/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:GetItem",
        "dynamodb:UpdateItem",
        "dynamodb:Query",
        "dynamodb:Scan"
      ],
      "Resource": "arn:aws:dynamodb:*:*:table/TABLE_NAME_PLACEHOLDER"
    },
    {
      "Effect": "Allow",
      "Action": ["sns:Publish"],
      "Resource": "arn:aws:sns:*:*:PROJECT_NAME_PLACEHOLDER-notifications"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter",
        "ssm:PutParameter",
        "ssm:GetParameters"
      ],
      "Resource": "arn:aws:ssm:*:*:parameter/PROJECT_NAME_PLACEHOLDER/*"
    }
  ]
}
```

---

### Task 1.4 — Create IAM Role in AWS

**Commit message:** `feat(iam): provision lambda execution role`

```bash
# Create the IAM role
aws iam create-role \
    --role-name ${PROJECT_NAME}-lambda-role \
    --assume-role-policy-document file://iam/lambda-trust-policy.json

# Substitute env vars into policy file before attaching
sed -e "s/BUCKET_NAME_PLACEHOLDER/${S3_BUCKET}/g" \
    -e "s/TABLE_NAME_PLACEHOLDER/${DYNAMODB_TABLE}/g" \
    -e "s/PROJECT_NAME_PLACEHOLDER/${PROJECT_NAME}/g" \
    iam/lambda-permissions-policy.json > /tmp/resolved-policy.json

# Attach inline policy
aws iam put-role-policy \
    --role-name ${PROJECT_NAME}-lambda-role \
    --policy-name CarbonOptimizationPolicy \
    --policy-document file:///tmp/resolved-policy.json

# Export role ARN for use by Section 2 and 3
export LAMBDA_ROLE_ARN=$(aws iam get-role \
    --role-name ${PROJECT_NAME}-lambda-role \
    --query 'Role.Arn' --output text)

echo "✅ IAM Role ARN: ${LAMBDA_ROLE_ARN}"
```

**Expected Output:**
```json
{
    "Role": {
        "RoleName": "carbon-optimizer-<suffix>-lambda-role",
        "Arn": "arn:aws:iam::<account-id>:role/carbon-optimizer-<suffix>-lambda-role"
    }
}
✅ IAM Role ARN: arn:aws:iam::<account-id>:role/carbon-optimizer-<suffix>-lambda-role
```

---

### Task 1.5 — Create DynamoDB Table

**Commit message:** `feat(dynamodb): create metrics table with primary key schema`

```bash
aws dynamodb create-table \
    --table-name ${DYNAMODB_TABLE} \
    --attribute-definitions \
        AttributeName=MetricType,AttributeType=S \
        AttributeName=Timestamp,AttributeType=S \
    --key-schema \
        AttributeName=MetricType,KeyType=HASH \
        AttributeName=Timestamp,KeyType=RANGE \
    --provisioned-throughput \
        ReadCapacityUnits=5,WriteCapacityUnits=5 \
    --tags Key=Project,Value=${PROJECT_NAME} \
           Key=Purpose,Value=CarbonFootprintOptimization

# Wait for table to become ACTIVE
aws dynamodb wait table-exists --table-name ${DYNAMODB_TABLE}

echo "✅ DynamoDB table created: ${DYNAMODB_TABLE}"
```

**Expected Output:**
```
✅ DynamoDB table created: carbon-optimizer-<suffix>-metrics
```

---

### Task 1.6 — Add Global Secondary Index

**Commit message:** `feat(dynamodb): add GSI for service-level carbon queries`

```bash
aws dynamodb update-table \
    --table-name ${DYNAMODB_TABLE} \
    --attribute-definitions \
        AttributeName=ServiceName,AttributeType=S \
        AttributeName=CarbonIntensity,AttributeType=N \
    --global-secondary-index-updates \
        'Create={
          IndexName=ServiceCarbonIndex,
          KeySchema=[
            {AttributeName=ServiceName,KeyType=HASH},
            {AttributeName=CarbonIntensity,KeyType=RANGE}
          ],
          Projection={ProjectionType=ALL},
          ProvisionedThroughput={ReadCapacityUnits=3,WriteCapacityUnits=3}
        }'

echo "✅ GSI ServiceCarbonIndex added to DynamoDB table"
```

**Expected Output:**
```
✅ GSI ServiceCarbonIndex added to DynamoDB table
```

---

## 🔍 Verification Checklist

Run these commands to confirm everything is working:

```bash
# 1. Verify S3 bucket exists
aws s3 ls | grep ${S3_BUCKET}

# 2. Verify IAM role exists
aws iam get-role --role-name ${PROJECT_NAME}-lambda-role --query 'Role.Arn'

# 3. Verify DynamoDB table is ACTIVE
aws dynamodb describe-table \
    --table-name ${DYNAMODB_TABLE} \
    --query 'Table.TableStatus'
# Expected: "ACTIVE"

# 4. Verify GSI exists
aws dynamodb describe-table \
    --table-name ${DYNAMODB_TABLE} \
    --query 'Table.GlobalSecondaryIndexes[*].IndexName'
# Expected: ["ServiceCarbonIndex"]
```

---

## 📝 Commit Summary

| # | Commit Message | Files Changed |
|---|---------------|---------------|
| 1 | `feat(s3): create encrypted versioned data bucket` | `scripts/setup.sh` |
| 2 | `feat(iam): add lambda trust policy document` | `iam/lambda-trust-policy.json` |
| 3 | `feat(iam): add lambda permissions policy document` | `iam/lambda-permissions-policy.json` |
| 4 | `feat(iam): provision lambda execution role` | `scripts/setup.sh` |
| 5 | `feat(dynamodb): create metrics table with primary key schema` | `scripts/setup.sh` |
| 6 | `feat(dynamodb): add GSI for service-level carbon queries` | `scripts/setup.sh` |

---

## 🚀 Pull Request Instructions

1. Push your branch: `git push origin feature/section-1-iam-dynamodb`
2. Open a PR to `main` titled: **"Section 1: IAM Roles & DynamoDB Setup"**
3. Add label: `infrastructure`
4. Request review from Team Member 5 (testing lead)
5. Paste verification output in the PR description

> ⚠️ **Sections 2, 3, and 4 depend on this section.** Do not merge until all verification checks pass.
