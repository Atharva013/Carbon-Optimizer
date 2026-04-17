# Section 6 — Validation, Testing & Cleanup

**Estimated Time:** 3–4 hours  
**Branch:** `feature/section-6-testing-cleanup`  
**Dependencies:** All previous sections (1–5) must be merged and deployed

---

## 🎯 Objective

Own the quality and reliability of the entire deployment. This section covers end-to-end validation of every component including the Dashboard (Section 5), integration testing, writing the cleanup scripts, and producing the final test report that confirms the system is production-ready.

---

## ✅ Prerequisites

- [ ] All sections 1–5 merged into `main` and deployed
- [ ] All AWS resources active (Lambda, DynamoDB, SNS, EventBridge, API Gateway, Dashboard)
- [ ] SNS email subscription confirmed by recipient
- [ ] AWS CLI v2 installed and configured
- [ ] Python 3.11+ installed
- [ ] `jq` installed for JSON parsing: `sudo apt-get install jq` or `brew install jq`
- [ ] Environment variables exported:
  ```bash
  export AWS_REGION=<your-region>
  export AWS_ACCOUNT_ID=<your-account-id>
  export PROJECT_NAME=carbon-optimizer-cloud
  export LAMBDA_FUNCTION=${PROJECT_NAME}-analyzer
  export DYNAMODB_TABLE=${PROJECT_NAME}-metrics
  export S3_BUCKET=${PROJECT_NAME}-data
  export SNS_TOPIC_ARN=$(aws sns list-topics \
      --query "Topics[?contains(TopicArn,'${PROJECT_NAME}-notifications')].TopicArn" \
      --output text)
  export API_ID=$(aws apigateway get-rest-apis \
      --query "items[?name=='${PROJECT_NAME}-dashboard-api'].id" \
      --output text)
  export API_ENDPOINT="https://${API_ID}.execute-api.${AWS_REGION}.amazonaws.com/prod"
  ```
- [ ] Repository on branch `feature/section-6-testing-cleanup`

---

## 📁 Files You Will Create

```
carbon-optimizer/
└── scripts/
    ├── validate.sh     ← Full test suite (sections 1–5)
    └── cleanup.sh      ← Teardown all resources
```

---

## 🔨 Tasks

### Task 6.1 — Verify All AWS Resources Exist

**Commit message:** `test(infra): add resource existence validation script`

Create `scripts/validate.sh`:

```bash
#!/bin/bash
set -e

echo "=================================================="
echo "  Carbon Optimizer — Full Validation Suite"
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

echo ""
echo "--- Section 1: DynamoDB ---"
check "DynamoDB table is ACTIVE" \
    "aws dynamodb describe-table --table-name ${DYNAMODB_TABLE} --query 'Table.TableStatus' --output text" \
    "ACTIVE"

echo ""
echo "--- Section 2: Lambda ---"
check "Analyzer Lambda is Active" \
    "aws lambda get-function --function-name ${LAMBDA_FUNCTION} --query 'Configuration.State' --output text" \
    "Active"

check "Lambda runtime is python3.11" \
    "aws lambda get-function --function-name ${LAMBDA_FUNCTION} --query 'Configuration.Runtime' --output text" \
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

echo ""
echo "--- Section 5: Dashboard ---"
check "Dashboard Lambda is Active" \
    "aws lambda get-function --function-name ${PROJECT_NAME}-dashboard-api --query 'Configuration.State' --output text" \
    "Active"

check "API Gateway exists" \
    "aws apigateway get-rest-apis --query \"items[?name=='${PROJECT_NAME}-dashboard-api'].name\" --output text" \
    "dashboard-api"

check "Dashboard API /summary returns 200" \
    "curl -s -o /dev/null -w '%{http_code}' ${API_ENDPOINT}/summary" \
    "200"

check "Dashboard HTML in S3" \
    "aws s3 ls s3://${S3_BUCKET}/dashboard/index.html 2>&1" \
    "index.html"

echo ""
echo "=================================================="
echo "  Results: ${PASS} passed, ${FAIL} failed"
echo "=================================================="
[ $FAIL -eq 0 ] && echo "  🎉 All checks passed!" || echo "  ⚠️  Some checks failed. Review above."
```

```bash
chmod +x scripts/validate.sh
bash scripts/validate.sh
```

---

### Task 6.2 — Test Lambda Function End-to-End

**Commit message:** `test(lambda): add end-to-end invocation test`

```bash
echo "Testing Lambda function invocation..."

aws lambda invoke \
    --function-name ${LAMBDA_FUNCTION} \
    --payload '{}' \
    /tmp/lambda-response.json

echo "Lambda response:"
cat /tmp/lambda-response.json | python3 -m json.tool

STATUS=$(cat /tmp/lambda-response.json | python3 -c \
    "import json,sys; print(json.load(sys.stdin).get('statusCode', 'missing'))")

if [ "$STATUS" == "200" ]; then
    echo "✅ Lambda returned statusCode 200"
else
    echo "❌ Lambda returned statusCode: ${STATUS}"
    echo "Check CloudWatch logs:"
    echo "aws logs tail /aws/lambda/${LAMBDA_FUNCTION} --follow"
fi
```

---

### Task 6.3 — Verify DynamoDB Data Was Written

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
        --output table
else
    echo "❌ No items found. Check Lambda execution and CloudWatch logs."
fi
```

---

### Task 6.4 — Validate Dashboard API Endpoints

**Commit message:** `test(dashboard): validate all API routes return correct data`

```bash
echo "Testing Dashboard API endpoints..."

for ROUTE in "/summary" "/metrics" "/recommendations"; do
    STATUS=$(curl -s -o /tmp/api-response.json -w '%{http_code}' \
        "${API_ENDPOINT}${ROUTE}")

    if [ "$STATUS" == "200" ]; then
        echo "✅ ${ROUTE} → 200 OK"
        cat /tmp/api-response.json | python3 -m json.tool | head -10
    else
        echo "❌ ${ROUTE} → ${STATUS}"
    fi
    echo ""
done
```

---

### Task 6.5 — Test EventBridge Schedule Configuration

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

### Task 6.6 — Write Cleanup Script

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
read -p "Delete all resources for ${PROJECT_NAME}? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Cleanup cancelled."
    exit 0
fi

echo ""
echo "Starting cleanup..."

# EventBridge schedules
echo "Deleting EventBridge schedules..."
for SCHEDULE in "monthly-analysis" "weekly-trends"; do
    aws scheduler delete-schedule \
        --name ${PROJECT_NAME}-${SCHEDULE} 2>/dev/null \
        && echo "  ✅ ${SCHEDULE} deleted" \
        || echo "  ℹ️  ${SCHEDULE} not found"
done

# Lambda functions
echo "Deleting Lambda functions..."
for FN in "${PROJECT_NAME}-analyzer" "${PROJECT_NAME}-dashboard-api"; do
    aws lambda delete-function --function-name ${FN} 2>/dev/null \
        && echo "  ✅ ${FN} deleted" \
        || echo "  ℹ️  ${FN} not found"
done

# API Gateway
echo "Deleting API Gateway..."
API_ID=$(aws apigateway get-rest-apis \
    --query "items[?name=='${PROJECT_NAME}-dashboard-api'].id" \
    --output text 2>/dev/null)
if [ -n "$API_ID" ]; then
    aws apigateway delete-rest-api --rest-api-id ${API_ID} \
        && echo "  ✅ API Gateway deleted"
else
    echo "  ℹ️  API Gateway not found"
fi

# IAM cleanup
echo "Deleting IAM roles and policies..."
POLICY_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:policy/${PROJECT_NAME}-lambda-policy"
aws iam detach-role-policy \
    --role-name ${PROJECT_NAME}-lambda-role \
    --policy-arn ${POLICY_ARN} 2>/dev/null || true
aws iam delete-policy --policy-arn ${POLICY_ARN} 2>/dev/null || true
aws iam detach-role-policy \
    --role-name ${PROJECT_NAME}-lambda-role \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole 2>/dev/null || true
aws iam delete-role --role-name ${PROJECT_NAME}-lambda-role 2>/dev/null \
    && echo "  ✅ Lambda IAM role deleted" || echo "  ℹ️  Lambda role not found"

# DynamoDB
echo "Deleting DynamoDB table..."
aws dynamodb delete-table --table-name ${DYNAMODB_TABLE} 2>/dev/null \
    && echo "  ✅ DynamoDB table deleted" || echo "  ℹ️  Table not found"

# SNS
echo "Deleting SNS topic..."
SNS_ARN=$(aws sns list-topics \
    --query "Topics[?contains(TopicArn,'${PROJECT_NAME}-notifications')].TopicArn" \
    --output text 2>/dev/null)
if [ -n "$SNS_ARN" ]; then
    aws sns delete-topic --topic-arn ${SNS_ARN} && echo "  ✅ SNS topic deleted"
else
    echo "  ℹ️  SNS topic not found"
fi

# SSM
echo "Deleting SSM parameters..."
aws ssm delete-parameter \
    --name "/${PROJECT_NAME}/sustainability-config" 2>/dev/null \
    && echo "  ✅ SSM parameter deleted" || echo "  ℹ️  SSM parameter not found"

# CUR
echo "Deleting CUR report..."
aws cur delete-report-definition \
    --region us-east-1 \
    --report-name carbon-optimization-detailed-report 2>/dev/null \
    && echo "  ✅ CUR report deleted" || echo "  ℹ️  CUR report not found"

# S3
echo "Deleting S3 bucket..."
aws s3 rm s3://${S3_BUCKET} --recursive 2>/dev/null || true
aws s3 rb s3://${S3_BUCKET} 2>/dev/null \
    && echo "  ✅ S3 bucket deleted" || echo "  ℹ️  S3 bucket not found"

# Local temp files
rm -f /tmp/lambda-response.json /tmp/api-response.json \
      /tmp/cur-bucket-policy.json /tmp/dashboard-api.zip \
      /tmp/website-bucket-policy.json
echo "  ✅ Local temp files cleaned"

echo ""
echo "=================================================="
echo "  ✅ Cleanup complete for: ${PROJECT_NAME}"
echo "=================================================="
```

```bash
chmod +x scripts/cleanup.sh
```

---

## 📝 Commit Summary

| # | Commit Message | Files |
|---|----------------|-------|
| 1 | `test(infra): add resource existence validation script` | `scripts/validate.sh` |
| 2 | `test(lambda): add end-to-end invocation test` | `scripts/validate.sh` |
| 3 | `test(dynamodb): verify metrics written after lambda invocation` | `scripts/validate.sh` |
| 4 | `test(dashboard): validate all API routes return correct data` | `scripts/validate.sh` |
| 5 | `test(eventbridge): validate schedule targets and states` | `scripts/validate.sh` |
| 6 | `ops(cleanup): add full teardown script for all project resources` | `scripts/cleanup.sh` |

---

## 🚀 Pull Request Instructions

1. Push your branch: `git push origin feature/section-6-testing-cleanup`
2. Open PR to `main` titled: **"Section 6: Validation, Testing & Cleanup"**
3. Add label: `testing`
4. **Paste the full output of `bash scripts/validate.sh` in the PR description**
5. This is the final PR — merge only after all sections 1–5 are confirmed working

> 🏁 Once this PR is merged, the project is production-ready.
