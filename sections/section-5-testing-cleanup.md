# Section 5 — Validation, Testing & Cleanup

**Assigned To:** Team Member 5  
**Estimated Time:** 3–4 hours  
**Branch:** `feature/section-5-testing-cleanup`  
**Dependencies:** All previous sections (1–4) must be merged and deployed

---

## 🎯 Objective

Own the quality and reliability of the entire deployment. This section covers end-to-end validation of every component, integration testing, writing the cleanup scripts, and producing the final test report that confirms the system is production-ready.

---

## ✅ Prerequisites

- [ ] All sections 1–4 merged into `main` and deployed
- [ ] All AWS resources active (Lambda, DynamoDB, SNS, EventBridge schedules, SSM parameter)
- [ ] SNS email subscription confirmed by recipient
- [ ] AWS CLI v2 installed and configured
- [ ] Python 3.11+ installed
- [ ] `jq` installed for JSON parsing: `sudo apt-get install jq` or `brew install jq`
- [ ] Environment variables exported:
  ```bash
  export AWS_REGION=<your-region>
  export AWS_ACCOUNT_ID=<your-account-id>
  export PROJECT_NAME=carbon-optimizer-<suffix>
  export LAMBDA_FUNCTION=${PROJECT_NAME}-analyzer
  export DYNAMODB_TABLE=${PROJECT_NAME}-metrics
  export S3_BUCKET=${PROJECT_NAME}-data
  export SNS_TOPIC_ARN=$(aws sns list-topics \
      --query "Topics[?contains(TopicArn,'${PROJECT_NAME}-notifications')].TopicArn" \
      --output text)
  ```
- [ ] Repository on branch `feature/section-5-testing-cleanup`

---

## 📁 Files You Will Create

```
carbon-optimizer/
└── scripts/
    ├── validate.sh     (full test suite)
    └── cleanup.sh      (teardown all resources)
```

---

## 🔨 Tasks

### Task 5.1 — Verify All AWS Resources Exist

**Commit message:** `test(infra): add resource existence validation script`

Create `scripts/validate.sh` with the following content:

```bash
#!/bin/bash
set -e

echo "=================================================="
echo "  Carbon Optimizer — Validation Suite"
echo "=================================================="

PASS=0
FAIL=0

check() {
    local description=$1
    local command=$2
    local expected=$3

    result=$(eval "$command" 2>/dev/null)
    if echo "$result" | grep -q "$expected"; then
        echo "  ✅ PASS: $description"
        ((PASS++))
    else
        echo "  ❌ FAIL: $description"
        echo "     Expected: '$expected'"
        echo "     Got:      '$result'"
        ((FAIL++))
    fi
}

echo ""
echo "--- Section 1: IAM & S3 ---"
check "S3 bucket exists" \
    "aws s3api head-bucket --bucket ${S3_BUCKET} 2>&1 && echo ok" "ok"

check "IAM role exists" \
    "aws iam get-role --role-name ${PROJECT_NAME}-lambda-role --query 'Role.RoleName' --output text" \
    "${PROJECT_NAME}-lambda-role"

check "IAM inline policy exists" \
    "aws iam get-role-policy --role-name ${PROJECT_NAME}-lambda-role --policy-name CarbonOptimizationPolicy 2>&1 && echo ok" "ok"

echo ""
echo "--- Section 1: DynamoDB ---"
check "DynamoDB table is ACTIVE" \
    "aws dynamodb describe-table --table-name ${DYNAMODB_TABLE} --query 'Table.TableStatus' --output text" \
    "ACTIVE"

check "DynamoDB GSI exists" \
    "aws dynamodb describe-table --table-name ${DYNAMODB_TABLE} --query 'Table.GlobalSecondaryIndexes[0].IndexName' --output text" \
    "ServiceCarbonIndex"

echo ""
echo "--- Section 2: Lambda ---"
check "Lambda function is Active" \
    "aws lambda get-function --function-name ${LAMBDA_FUNCTION} --query 'Configuration.State' --output text" \
    "Active"

check "Lambda runtime is python3.11" \
    "aws lambda get-function-configuration --function-name ${LAMBDA_FUNCTION} --query 'Configuration.Runtime' --output text 2>/dev/null || aws lambda get-function --function-name ${LAMBDA_FUNCTION} --query 'Configuration.Runtime' --output text" \
    "python3.11"

check "Lambda has SNS_TOPIC_ARN env var" \
    "aws lambda get-function-configuration --function-name ${LAMBDA_FUNCTION} --query 'Environment.Variables.SNS_TOPIC_ARN' --output text" \
    "arn:aws:sns"

echo ""
echo "--- Section 3: SNS ---"
check "SNS topic exists" \
    "aws sns get-topic-attributes --topic-arn ${SNS_TOPIC_ARN} --query 'Attributes.TopicArn' --output text 2>/dev/null" \
    "${PROJECT_NAME}-notifications"

check "SNS has at least one subscription" \
    "aws sns list-subscriptions-by-topic --topic-arn ${SNS_TOPIC_ARN} --query 'length(Subscriptions)' --output text" \
    "1"

echo ""
echo "--- Section 3: EventBridge ---"
check "Monthly schedule exists" \
    "aws scheduler get-schedule --name ${PROJECT_NAME}-monthly-analysis --query 'Name' --output text 2>/dev/null" \
    "monthly-analysis"

check "Weekly schedule exists" \
    "aws scheduler get-schedule --name ${PROJECT_NAME}-weekly-trends --query 'Name' --output text 2>/dev/null" \
    "weekly-trends"

echo ""
echo "--- Section 4: SSM & CUR ---"
check "SSM parameter exists" \
    "aws ssm get-parameter --name '/${PROJECT_NAME}/sustainability-config' --query 'Parameter.Name' --output text" \
    "sustainability-config"

check "CloudFormation template in S3" \
    "aws s3 ls s3://${S3_BUCKET}/templates/sustainable-infrastructure.yaml 2>&1" \
    "sustainable-infrastructure.yaml"

check "CUR report definition exists" \
    "aws cur describe-report-definitions --region us-east-1 --query \"ReportDefinitions[?ReportName=='carbon-optimization-detailed-report'].ReportName\" --output text" \
    "carbon-optimization-detailed-report"

echo ""
echo "=================================================="
echo "  Results: ${PASS} passed, ${FAIL} failed"
echo "=================================================="
[ $FAIL -eq 0 ] && echo "  🎉 All checks passed!" || echo "  ⚠️  Some checks failed. Review output above."
```

```bash
chmod +x scripts/validate.sh
bash scripts/validate.sh
```

---

### Task 5.2 — Test Lambda Function End-to-End

**Commit message:** `test(lambda): add end-to-end invocation test`

```bash
echo "Testing Lambda function invocation..."

aws lambda invoke \
    --function-name ${LAMBDA_FUNCTION} \
    --payload '{}' \
    /tmp/lambda-response.json

echo "Lambda response:"
cat /tmp/lambda-response.json | python3 -m json.tool

STATUS=$(cat /tmp/lambda-response.json | python3 -c "import json,sys; print(json.load(sys.stdin).get('statusCode', 'missing'))")

if [ "$STATUS" == "200" ]; then
    echo "✅ Lambda returned statusCode 200"
else
    echo "❌ Lambda returned statusCode: ${STATUS}"
    echo "Check CloudWatch logs:"
    echo "aws logs tail /aws/lambda/${LAMBDA_FUNCTION} --follow"
fi
```

**Expected Output:**
```json
{
    "statusCode": 200,
    "body": "{\"message\": \"Carbon footprint analysis completed successfully\", \"recommendations_count\": 3, \"high_impact_count\": 1}"
}
✅ Lambda returned statusCode 200
```

---

### Task 5.3 — Verify DynamoDB Data Was Written

**Commit message:** `test(dynamodb): verify metrics written after lambda invocation`

```bash
echo "Checking DynamoDB for stored metrics..."

ITEM_COUNT=$(aws dynamodb scan \
    --table-name ${DYNAMODB_TABLE} \
    --select COUNT \
    --query 'Count' \
    --output text)

echo "Items in DynamoDB table: ${ITEM_COUNT}"

if [ "$ITEM_COUNT" -gt "0" ]; then
    echo "✅ DynamoDB has ${ITEM_COUNT} metric item(s)"
    
    echo ""
    echo "Sample items:"
    aws dynamodb scan \
        --table-name ${DYNAMODB_TABLE} \
        --max-items 3 \
        --query 'Items[*].[MetricType.S, Timestamp.S]' \
        --output table
else
    echo "❌ No items found in DynamoDB. Check Lambda execution and CloudWatch logs."
fi
```

---

### Task 5.4 — Test Cost Explorer API Access

**Commit message:** `test(cost-explorer): verify API access and data retrieval`

```bash
echo "Testing Cost Explorer API access..."

START=$(date -d '30 days ago' '+%Y-%m-%d' 2>/dev/null || date -v-30d '+%Y-%m-%d')
END=$(date '+%Y-%m-%d')

RESULT=$(aws ce get-cost-and-usage \
    --time-period Start=${START},End=${END} \
    --granularity MONTHLY \
    --metrics "BlendedCost" \
    --group-by Type=DIMENSION,Key=SERVICE \
    --max-items 3 2>&1)

if echo "$RESULT" | grep -q "ResultsByTime"; then
    echo "✅ Cost Explorer API accessible and returning data"
    echo "${RESULT}" | python3 -m json.tool | head -30
else
    echo "❌ Cost Explorer API error:"
    echo "${RESULT}"
fi
```

---

### Task 5.5 — Validate EventBridge Schedule Configuration

**Commit message:** `test(eventbridge): validate schedule targets and states`

```bash
echo "Validating EventBridge schedules..."

for SCHEDULE in "monthly-analysis" "weekly-trends"; do
    FULL_NAME="${PROJECT_NAME}-${SCHEDULE}"
    STATE=$(aws scheduler get-schedule \
        --name ${FULL_NAME} \
        --query 'State' \
        --output text 2>/dev/null)
    
    if [ "$STATE" == "ENABLED" ]; then
        echo "✅ Schedule ${FULL_NAME}: ENABLED"
    else
        echo "❌ Schedule ${FULL_NAME}: ${STATE:-NOT FOUND}"
    fi
done
```

---

### Task 5.6 — Write Cleanup Script

**Commit message:** `ops(cleanup): add full teardown script for all project resources`

Create `scripts/cleanup.sh`:

```bash
#!/bin/bash
set -e

echo "=================================================="
echo "  Carbon Optimizer — Cleanup Script"
echo "  This will DELETE all project resources!"
echo "=================================================="
echo ""
read -p "Are you sure you want to delete all resources for ${PROJECT_NAME}? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Cleanup cancelled."
    exit 0
fi

echo ""
echo "Starting cleanup..."

# Delete EventBridge schedules
echo "Deleting EventBridge schedules..."
aws scheduler delete-schedule --name ${PROJECT_NAME}-monthly-analysis 2>/dev/null && \
    echo "  ✅ Monthly schedule deleted" || echo "  ℹ️  Monthly schedule not found (skipping)"

aws scheduler delete-schedule --name ${PROJECT_NAME}-weekly-trends 2>/dev/null && \
    echo "  ✅ Weekly schedule deleted" || echo "  ℹ️  Weekly schedule not found (skipping)"

# Delete Lambda function
echo "Deleting Lambda function..."
aws lambda delete-function --function-name ${LAMBDA_FUNCTION} 2>/dev/null && \
    echo "  ✅ Lambda function deleted" || echo "  ℹ️  Lambda function not found (skipping)"

# Delete IAM roles and policies
echo "Deleting IAM roles..."
aws iam delete-role-policy \
    --role-name ${PROJECT_NAME}-lambda-role \
    --policy-name CarbonOptimizationPolicy 2>/dev/null || true

aws iam delete-role --role-name ${PROJECT_NAME}-lambda-role 2>/dev/null && \
    echo "  ✅ Lambda IAM role deleted" || echo "  ℹ️  Lambda role not found (skipping)"

aws iam delete-role-policy \
    --role-name ${PROJECT_NAME}-scheduler-role \
    --policy-name InvokeLambdaPolicy 2>/dev/null || true

aws iam delete-role --role-name ${PROJECT_NAME}-scheduler-role 2>/dev/null && \
    echo "  ✅ Scheduler IAM role deleted" || echo "  ℹ️  Scheduler role not found (skipping)"

# Delete DynamoDB table
echo "Deleting DynamoDB table..."
aws dynamodb delete-table --table-name ${DYNAMODB_TABLE} 2>/dev/null && \
    echo "  ✅ DynamoDB table deleted" || echo "  ℹ️  DynamoDB table not found (skipping)"

# Delete SNS topic
echo "Deleting SNS topic..."
SNS_ARN=$(aws sns list-topics \
    --query "Topics[?contains(TopicArn,'${PROJECT_NAME}-notifications')].TopicArn" \
    --output text 2>/dev/null)

if [ -n "$SNS_ARN" ]; then
    aws sns delete-topic --topic-arn ${SNS_ARN} && echo "  ✅ SNS topic deleted"
else
    echo "  ℹ️  SNS topic not found (skipping)"
fi

# Delete SSM parameter
echo "Deleting SSM parameters..."
aws ssm delete-parameter \
    --name "/${PROJECT_NAME}/sustainability-config" 2>/dev/null && \
    echo "  ✅ SSM parameter deleted" || echo "  ℹ️  SSM parameter not found (skipping)"

# Delete CUR report
echo "Deleting Cost and Usage Report..."
aws cur delete-report-definition \
    --region us-east-1 \
    --report-name carbon-optimization-detailed-report 2>/dev/null && \
    echo "  ✅ CUR report definition deleted" || echo "  ℹ️  CUR report not found (skipping)"

# Empty and delete S3 bucket
echo "Deleting S3 bucket..."
aws s3 rm s3://${S3_BUCKET} --recursive 2>/dev/null || true
aws s3 rb s3://${S3_BUCKET} 2>/dev/null && \
    echo "  ✅ S3 bucket deleted" || echo "  ℹ️  S3 bucket not found (skipping)"

# Clean up local temp files
echo "Cleaning up local files..."
rm -f /tmp/lambda-response.json /tmp/cur-bucket-policy.json \
      /tmp/resolved-policy.json /tmp/scheduler-trust-policy.json \
      /tmp/scheduler-permissions.json
echo "  ✅ Local temp files removed"

echo ""
echo "=================================================="
echo "  ✅ Cleanup complete for project: ${PROJECT_NAME}"
echo "=================================================="
```

```bash
chmod +x scripts/cleanup.sh
```

---

## 🔍 Final Verification Checklist

```bash
# Run the full validation suite
bash scripts/validate.sh

# Check CloudWatch logs for Lambda
aws logs tail /aws/lambda/${LAMBDA_FUNCTION} --since 1h

# Confirm DynamoDB has written data
aws dynamodb scan --table-name ${DYNAMODB_TABLE} --select COUNT
```

---

## 📝 Commit Summary

| # | Commit Message | Files Changed |
|---|---------------|---------------|
| 1 | `test(infra): add resource existence validation script` | `scripts/validate.sh` |
| 2 | `test(lambda): add end-to-end invocation test` | `scripts/validate.sh` |
| 3 | `test(dynamodb): verify metrics written after lambda invocation` | `scripts/validate.sh` |
| 4 | `test(cost-explorer): verify API access and data retrieval` | `scripts/validate.sh` |
| 5 | `test(eventbridge): validate schedule targets and states` | `scripts/validate.sh` |
| 6 | `ops(cleanup): add full teardown script for all project resources` | `scripts/cleanup.sh` |

---

## 🚀 Pull Request Instructions

1. Push your branch: `git push origin feature/section-5-testing-cleanup`
2. Open a PR to `main` titled: **"Section 5: Validation, Testing & Cleanup"**
3. Add label: `testing`
4. **Paste the full output of `bash scripts/validate.sh` in the PR description**
5. This section should be the final PR merged — act as reviewer for Sections 1–4

> 🏁 Once this PR is merged, the project is production-ready.
