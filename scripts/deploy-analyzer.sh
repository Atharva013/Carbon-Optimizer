#!/bin/bash
# =============================================================================
# Section 2 — Analyzer Lambda Deployment Script (Idempotent)
# Deploys: Carbon Optimizer analyzer Lambda
# =============================================================================
set -euo pipefail

export AWS_REGION=${AWS_REGION:-ap-south-1}
export AWS_ACCOUNT_ID=${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}
export PROJECT_NAME=${PROJECT_NAME:-carbon-optimizer-cloud}
export LAMBDA_FUNCTION=${LAMBDA_FUNCTION:-${PROJECT_NAME}-analyzer}
export DYNAMODB_TABLE=${DYNAMODB_TABLE:-${PROJECT_NAME}-metrics}
export S3_BUCKET=${S3_BUCKET:-${PROJECT_NAME}-data}
export SNS_TOPIC_ARN=${SNS_TOPIC_ARN:-arn:aws:sns:${AWS_REGION}:${AWS_ACCOUNT_ID}:${PROJECT_NAME}-notifications}

echo "=================================================="
echo "  Carbon Optimizer — Analyzer Lambda Deploy"
echo "  Function : ${LAMBDA_FUNCTION}"
echo "  Region   : ${AWS_REGION}"
echo "=================================================="

export LAMBDA_ROLE_ARN=$(aws iam get-role \
    --role-name ${PROJECT_NAME}-lambda-role \
    --query 'Role.Arn' --output text --region ${AWS_REGION})
echo "✅ Lambda Role ARN: ${LAMBDA_ROLE_ARN}"

echo ""
echo "[ Step 1 ] Packaging analyzer Lambda..."
cd lambda-function
zip -r /tmp/analyzer.zip index.py > /dev/null
cd ..
echo "✅ Packaged: /tmp/analyzer.zip"

echo ""
echo "[ Step 2 ] Deploying analyzer Lambda..."
FUNC_EXISTS=$(aws lambda get-function \
    --function-name ${LAMBDA_FUNCTION} \
    --region ${AWS_REGION} \
    --query 'Configuration.FunctionName' \
    --output text 2>/dev/null || echo "")

if [ -z "${FUNC_EXISTS}" ] || [ "${FUNC_EXISTS}" == "None" ]; then
    echo "  Creating new function: ${LAMBDA_FUNCTION}"
    aws lambda create-function \
        --function-name ${LAMBDA_FUNCTION} \
        --runtime python3.11 \
        --handler index.lambda_handler \
        --role ${LAMBDA_ROLE_ARN} \
        --zip-file fileb:///tmp/analyzer.zip \
        --environment "Variables={DYNAMODB_TABLE=${DYNAMODB_TABLE},S3_BUCKET=${S3_BUCKET},SNS_TOPIC_ARN=${SNS_TOPIC_ARN},PROJECT_NAME=${PROJECT_NAME}}" \
        --timeout 60 \
        --memory-size 256 \
        --tags Project=${PROJECT_NAME},Purpose=Analyzer \
        --region ${AWS_REGION} > /dev/null

    aws lambda wait function-active \
        --function-name ${LAMBDA_FUNCTION} \
        --region ${AWS_REGION}
    echo "✅ Analyzer Lambda created and active"
else
    echo "  Function exists — updating code..."
    aws lambda update-function-code \
        --function-name ${LAMBDA_FUNCTION} \
        --zip-file fileb:///tmp/analyzer.zip \
        --region ${AWS_REGION} > /dev/null

    aws lambda wait function-updated \
        --function-name ${LAMBDA_FUNCTION} \
        --region ${AWS_REGION}

    aws lambda update-function-configuration \
        --function-name ${LAMBDA_FUNCTION} \
        --environment "Variables={DYNAMODB_TABLE=${DYNAMODB_TABLE},S3_BUCKET=${S3_BUCKET},SNS_TOPIC_ARN=${SNS_TOPIC_ARN},PROJECT_NAME=${PROJECT_NAME}}" \
        --timeout 60 \
        --memory-size 256 \
        --region ${AWS_REGION} > /dev/null

    aws lambda wait function-updated \
        --function-name ${LAMBDA_FUNCTION} \
        --region ${AWS_REGION}
    echo "✅ Analyzer Lambda updated"
fi

echo ""
echo "=================================================="
echo "  Verification"
echo "=================================================="
aws lambda get-function \
    --function-name ${LAMBDA_FUNCTION} \
    --query 'Configuration.[FunctionName,State,Runtime,LastModified]' \
    --output table \
    --region ${AWS_REGION}

echo ""
echo "To refresh the dashboard snapshot immediately, run:"
echo "aws lambda invoke --function-name ${LAMBDA_FUNCTION} --payload '{}' /tmp/analyzer-response.json && cat /tmp/analyzer-response.json"
