# Section 4 — Cost & Usage Reports + Systems Manager Configuration

**Assigned To:** Team Member 4  
**Estimated Time:** 2–3 hours  
**Branch:** `feature/section-4-cur-ssm`  
**Dependencies:** Section 1 (S3 bucket must exist)

---

## 🎯 Objective

Configure the enhanced data pipeline and centralized configuration layer. This includes setting up AWS Cost and Usage Reports (CUR) for detailed carbon analysis data, storing sustainability best-practice configuration in AWS Systems Manager Parameter Store, and creating reusable CloudFormation templates for sustainable infrastructure.

---

## ✅ Prerequisites

- [ ] Section 1 merged (S3 bucket must exist)
- [ ] AWS CLI v2 installed and configured
- [ ] IAM permissions for: `cur:PutReportDefinition`, `ssm:PutParameter`, `s3:PutBucketPolicy`, `cloudformation:ValidateTemplate`
- [ ] Environment variables exported:
  ```bash
  export AWS_REGION=<your-region>
  export AWS_ACCOUNT_ID=<your-account-id>
  export PROJECT_NAME=carbon-optimizer-<suffix>
  export S3_BUCKET=${PROJECT_NAME}-data
  ```
- [ ] Repository on branch `feature/section-4-cur-ssm`

> ⚠️ **CUR API Note:** The `aws cur` commands must be run against `us-east-1` regardless of your deployment region. This is an AWS requirement.

---

## 📁 Files You Will Create

```
carbon-optimizer/
├── cloudformation/
│   └── sustainable-infrastructure.yaml
└── scripts/
    └── deploy.sh    (add CUR + SSM commands)
```

---

## 🔨 Tasks

### Task 4.1 — Add S3 Bucket Policy for CUR Delivery

**Commit message:** `feat(s3): add bucket policy to allow CUR delivery`

AWS requires an S3 bucket policy before it can deliver Cost and Usage Reports:

```bash
cat > /tmp/cur-bucket-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "billingreports.amazonaws.com"
      },
      "Action": [
        "s3:GetBucketAcl",
        "s3:GetBucketPolicy"
      ],
      "Resource": "arn:aws:s3:::${S3_BUCKET}"
    },
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "billingreports.amazonaws.com"
      },
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::${S3_BUCKET}/cost-usage-reports/*"
    }
  ]
}
EOF

aws s3api put-bucket-policy \
    --bucket ${S3_BUCKET} \
    --policy file:///tmp/cur-bucket-policy.json

echo "✅ S3 bucket policy updated for CUR delivery"
```

**Expected Output:**
```
✅ S3 bucket policy updated for CUR delivery
```

---

### Task 4.2 — Create Cost and Usage Report Definition

**Commit message:** `feat(cur): configure cost and usage report for carbon analysis`

```bash
cat > /tmp/cur-definition.json << EOF
{
    "ReportName": "carbon-optimization-detailed-report",
    "TimeUnit": "DAILY",
    "Format": "Parquet",
    "Compression": "GZIP",
    "AdditionalSchemaElements": ["RESOURCES", "SPLIT_COST_ALLOCATION_DATA"],
    "S3Bucket": "${S3_BUCKET}",
    "S3Prefix": "cost-usage-reports/",
    "S3Region": "${AWS_REGION}",
    "AdditionalArtifacts": ["ATHENA"],
    "RefreshClosedReports": true,
    "ReportVersioning": "OVERWRITE_REPORT"
}
EOF

# CUR must always be created in us-east-1
aws cur put-report-definition \
    --region us-east-1 \
    --report-definition file:///tmp/cur-definition.json

echo "✅ Cost and Usage Report definition created"
echo "ℹ️  Reports will appear in S3 within 24 hours of the first full day."
```

**Expected Output:**
```
✅ Cost and Usage Report definition created
ℹ️  Reports will appear in S3 within 24 hours of the first full day.
```

---

### Task 4.3 — Create Sustainability Configuration in SSM Parameter Store

**Commit message:** `feat(ssm): store sustainability optimization configuration`

```bash
aws ssm put-parameter \
    --name "/${PROJECT_NAME}/sustainability-config" \
    --value '{
        "carbon_thresholds": {
            "high_impact": 100,
            "optimization_threshold": 0.2
        },
        "regional_preferences": {
            "preferred_regions": ["us-west-2", "eu-north-1", "ca-central-1"],
            "avoid_regions": []
        },
        "optimization_rules": {
            "graviton_migration": true,
            "intelligent_tiering": true,
            "serverless_first": true,
            "right_sizing": true
        },
        "notification_settings": {
            "email_threshold": 50,
            "weekly_summary": true
        }
    }' \
    --type String \
    --description "Sustainability optimization configuration for ${PROJECT_NAME}"

echo "✅ SSM Parameter created: /${PROJECT_NAME}/sustainability-config"
```

**Expected Output:**
```json
{
    "Version": 1,
    "Tier": "Standard"
}
✅ SSM Parameter created: /carbon-optimizer-<suffix>/sustainability-config
```

---

### Task 4.4 — Create Sustainable Infrastructure CloudFormation Template

**Commit message:** `feat(cloudformation): add sustainable infrastructure template with Graviton support`

Create the file `cloudformation/sustainable-infrastructure.yaml`:

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: >
  Sustainable infrastructure template with carbon-optimized resources.
  Uses Graviton processors and S3 Intelligent Tiering for reduced carbon footprint.

Parameters:
  EnvironmentType:
    Type: String
    Default: production
    AllowedValues: [production, staging, development]
    Description: Deployment environment type
  
  ProjectName:
    Type: String
    Description: Name of the project for tagging and naming
    Default: carbon-optimizer

Mappings:
  SustainableInstanceTypes:
    production:
      InstanceType: m6g.large
    staging:
      InstanceType: t4g.medium
    development:
      InstanceType: t4g.small

Resources:

  EfficientStorageBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: !Sub "${ProjectName}-sustainable-${AWS::AccountId}"
      IntelligentTieringConfigurations:
        - Id: OptimizeStorage
          Status: Enabled
      LifecycleConfiguration:
        Rules:
          - Id: TransitionToIA
            Status: Enabled
            TransitionInDays: 30
            StorageClass: STANDARD_IA
          - Id: TransitionToGlacier
            Status: Enabled
            TransitionInDays: 90
            StorageClass: GLACIER
      BucketEncryption:
        ServerSideEncryptionConfiguration:
          - ServerSideEncryptionByDefault:
              SSEAlgorithm: AES256
      Tags:
        - Key: SustainabilityOptimized
          Value: "true"
        - Key: Project
          Value: !Ref ProjectName

  SustainableComputeSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Security group for sustainable compute instances
      Tags:
        - Key: Project
          Value: !Ref ProjectName

Outputs:
  StorageBucketName:
    Description: Name of the sustainable storage bucket
    Value: !Ref EfficientStorageBucket
    Export:
      Name: !Sub "${ProjectName}-StorageBucket"
  
  InstanceType:
    Description: Graviton instance type for this environment
    Value: !FindInMap [SustainableInstanceTypes, !Ref EnvironmentType, InstanceType]
```

---

### Task 4.5 — Upload CloudFormation Template to S3

**Commit message:** `feat(s3): upload sustainable infrastructure template to project bucket`

```bash
aws s3 cp cloudformation/sustainable-infrastructure.yaml \
    s3://${S3_BUCKET}/templates/sustainable-infrastructure.yaml

echo "✅ CloudFormation template uploaded to S3"
echo "Template URL: https://${S3_BUCKET}.s3.${AWS_REGION}.amazonaws.com/templates/sustainable-infrastructure.yaml"
```

---

### Task 4.6 — Validate CloudFormation Template

**Commit message:** `test(cloudformation): validate sustainable infrastructure template`

```bash
aws cloudformation validate-template \
    --template-url "https://${S3_BUCKET}.s3.${AWS_REGION}.amazonaws.com/templates/sustainable-infrastructure.yaml"

echo "✅ CloudFormation template is valid"
```

**Expected Output:**
```json
{
    "Parameters": [
        { "ParameterKey": "EnvironmentType", "DefaultValue": "production" },
        { "ParameterKey": "ProjectName", "DefaultValue": "carbon-optimizer" }
    ],
    "Description": "Sustainable infrastructure template..."
}
✅ CloudFormation template is valid
```

---

## 🔍 Verification Checklist

```bash
# 1. Confirm CUR report definition exists
aws cur describe-report-definitions \
    --region us-east-1 \
    --query 'ReportDefinitions[?ReportName==`carbon-optimization-detailed-report`].ReportName'
# Expected: ["carbon-optimization-detailed-report"]

# 2. Confirm SSM parameter exists
aws ssm get-parameter \
    --name "/${PROJECT_NAME}/sustainability-config" \
    --query 'Parameter.Name'
# Expected: "/carbon-optimizer-<suffix>/sustainability-config"

# 3. Confirm template uploaded to S3
aws s3 ls s3://${S3_BUCKET}/templates/
# Expected: sustainable-infrastructure.yaml listed

# 4. Confirm S3 bucket policy is in place
aws s3api get-bucket-policy --bucket ${S3_BUCKET} --query 'Policy' | python3 -m json.tool
```

---

## 📝 Commit Summary

| # | Commit Message | Files Changed |
|---|---------------|---------------|
| 1 | `feat(s3): add bucket policy to allow CUR delivery` | `scripts/deploy.sh` |
| 2 | `feat(cur): configure cost and usage report for carbon analysis` | `scripts/deploy.sh` |
| 3 | `feat(ssm): store sustainability optimization configuration` | `scripts/deploy.sh` |
| 4 | `feat(cloudformation): add sustainable infrastructure template with Graviton support` | `cloudformation/sustainable-infrastructure.yaml` |
| 5 | `feat(s3): upload sustainable infrastructure template to project bucket` | `scripts/deploy.sh` |
| 6 | `test(cloudformation): validate sustainable infrastructure template` | `scripts/deploy.sh` |

---

## 🚀 Pull Request Instructions

1. Push your branch: `git push origin feature/section-4-cur-ssm`
2. Open a PR to `main` titled: **"Section 4: Cost & Usage Reports + SSM Configuration"**
3. Add label: `configuration`
4. Paste CUR describe output and SSM get-parameter output in the PR description
5. Request review from Team Member 5 (testing lead)
