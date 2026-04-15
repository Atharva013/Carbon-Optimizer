#!/bin/bash

export AWS_REGION=${AWS_REGION:-ap-south-1}
export AWS_ACCOUNT_ID=${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text 2>/dev/null)}
export PROJECT_NAME=${PROJECT_NAME:-carbon-optimizer-cloud}
export LAMBDA_FUNCTION=${LAMBDA_FUNCTION:-${PROJECT_NAME}-analyzer}
export DYNAMODB_TABLE=${DYNAMODB_TABLE:-${PROJECT_NAME}-metrics}
export S3_BUCKET=${S3_BUCKET:-${PROJECT_NAME}-data}
export SNS_TOPIC_ARN=${SNS_TOPIC_ARN:-arn:aws:sns:${AWS_REGION}:${AWS_ACCOUNT_ID}:${PROJECT_NAME}-notifications}

echo "=================================================="
echo "  Carbon Optimizer — Full Validation Suite"
echo "=================================================="

PASS=0
FAIL=0

API_ID=$(aws apigateway get-rest-apis --region ${AWS_REGION:-ap-south-1} --query "items[?name=='${PROJECT_NAME}-dashboard-api'].id" --output text 2>/dev/null)
API_ENDPOINT="https://${API_ID}.execute-api.${AWS_REGION:-ap-south-1}.amazonaws.com/prod"

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

echo ""
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

echo ""
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

echo ""
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
