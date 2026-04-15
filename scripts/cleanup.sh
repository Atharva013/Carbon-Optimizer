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
