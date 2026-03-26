#!/bin/bash
# Task 1.1 — Create S3 bucket for data storage

aws s3 mb s3://${S3_BUCKET} --region ${AWS_REGION}

aws s3api put-bucket-versioning \
    --bucket ${S3_BUCKET} \
    --versioning-configuration Status=Enabled

aws s3api put-bucket-encryption \
    --bucket ${S3_BUCKET} \
    --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

echo "✅ S3 bucket created: ${S3_BUCKET}"

# Task 1.4 — Create IAM role
aws iam create-role \
    --role-name ${PROJECT_NAME}-lambda-role \
    --assume-role-policy-document file://iam/lambda-trust-policy.json

sed -e "s/BUCKET_NAME_PLACEHOLDER/${S3_BUCKET}/g" \
    -e "s/TABLE_NAME_PLACEHOLDER/${DYNAMODB_TABLE}/g" \
    -e "s/PROJECT_NAME_PLACEHOLDER/${PROJECT_NAME}/g" \
    iam/lambda-permissions-policy.json > /tmp/resolved-policy.json

aws iam put-role-policy \
    --role-name ${PROJECT_NAME}-lambda-role \
    --policy-name CarbonOptimizationPolicy \
    --policy-document file:///tmp/resolved-policy.json

export LAMBDA_ROLE_ARN=$(aws iam get-role \
    --role-name ${PROJECT_NAME}-lambda-role \
    --query 'Role.Arn' --output text)

echo "✅ IAM Role ARN: ${LAMBDA_ROLE_ARN}"

# Task 1.5 — Create DynamoDB table
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

aws dynamodb wait table-exists --table-name ${DYNAMODB_TABLE}

echo "✅ DynamoDB table created: ${DYNAMODB_TABLE}"
