#!/bin/bash
# =============================================================================
# Section 3 — SNS Notifications & EventBridge Schedules
# deploy.sh — Idempotent deployment script (safe to run multiple times)
# =============================================================================

set -e  # Exit immediately on any error

# -----------------------------------------------------------------------------
# Environment Variables
# -----------------------------------------------------------------------------
export AWS_REGION=ap-south-1
export AWS_ACCOUNT_ID=533389118899
export PROJECT_NAME=carbon-optimizer-cloud
export LAMBDA_FUNCTION=${PROJECT_NAME}-analyzer
export DYNAMODB_TABLE=${PROJECT_NAME}-metrics
export S3_BUCKET=${PROJECT_NAME}-data

echo "================================================"
echo "  Carbon Optimizer — Section 3 Deployment"
echo "  Project : ${PROJECT_NAME}"
echo "  Region  : ${AWS_REGION}"
echo "================================================"

# -----------------------------------------------------------------------------
# Retrieve existing role ARNs
# -----------------------------------------------------------------------------
export LAMBDA_ROLE_ARN=$(aws iam get-role \
    --role-name ${PROJECT_NAME}-lambda-role \
    --query 'Role.Arn' --output text --region ${AWS_REGION})

echo "✅ Lambda Role ARN : ${LAMBDA_ROLE_ARN}"

# -----------------------------------------------------------------------------
# Task 3.1 — Create SNS Topic (idempotent: create-topic is safe to re-run)
# -----------------------------------------------------------------------------
echo ""
echo "[ Task 3.1 ] Creating SNS Topic..."

aws sns create-topic \
    --name ${PROJECT_NAME}-notifications \
    --tags Key=Project,Value=${PROJECT_NAME} \
           Key=Purpose,Value=CarbonOptimizationAlerts \
    --region ${AWS_REGION} > /dev/null

export SNS_TOPIC_ARN=$(aws sns list-topics \
    --query "Topics[?contains(TopicArn, '${PROJECT_NAME}-notifications')].TopicArn" \
    --output text --region ${AWS_REGION})

echo "✅ SNS Topic : ${SNS_TOPIC_ARN}"

# -----------------------------------------------------------------------------
# Task 3.2 — Subscribe Email to SNS Topic
# -----------------------------------------------------------------------------
echo ""
echo "[ Task 3.2 ] Subscribing email to SNS Topic..."

# Check if subscription already exists
EXISTING_SUB=$(aws sns list-subscriptions-by-topic \
    --topic-arn ${SNS_TOPIC_ARN} \
    --query 'Subscriptions[?Protocol==`email`].Endpoint' \
    --output text --region ${AWS_REGION})

if [ -z "${EXISTING_SUB}" ]; then
    read -p "Enter email address for carbon optimization notifications: " EMAIL_ADDRESS
    aws sns subscribe \
        --topic-arn ${SNS_TOPIC_ARN} \
        --protocol email \
        --notification-endpoint ${EMAIL_ADDRESS} \
        --region ${AWS_REGION}
    echo "✅ Subscription request sent to: ${EMAIL_ADDRESS}"
    echo "⚠️  Check your email and click Confirm subscription before proceeding."
    read -p "Press ENTER once you have confirmed the subscription email..."
else
    echo "✅ Email already subscribed: ${EXISTING_SUB} — skipping"
fi

# -----------------------------------------------------------------------------
# Task 3.3 — Update Lambda Environment with real SNS ARN
# -----------------------------------------------------------------------------
echo ""
echo "[ Task 3.3 ] Updating Lambda environment variables..."

aws lambda update-function-configuration \
    --function-name ${LAMBDA_FUNCTION} \
    --environment Variables="{
        \"DYNAMODB_TABLE\":\"${DYNAMODB_TABLE}\",
        \"S3_BUCKET\":\"${S3_BUCKET}\",
        \"SNS_TOPIC_ARN\":\"${SNS_TOPIC_ARN}\"
    }" \
    --region ${AWS_REGION} > /dev/null

echo "✅ Lambda environment updated with SNS ARN"

# -----------------------------------------------------------------------------
# Task 3.4 — Create EventBridge Scheduler Role (idempotent)
# -----------------------------------------------------------------------------
echo ""
echo "[ Task 3.4 ] Creating EventBridge Scheduler IAM Role..."

# Trust policy
cat > /tmp/scheduler-trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "scheduler.amazonaws.com" },
    "Action": "sts:AssumeRole"
  }]
}
EOF

# Create role only if it doesn't exist
if ! aws iam get-role --role-name ${PROJECT_NAME}-scheduler-role \
    --query 'Role.RoleName' --output text 2>/dev/null | grep -q "scheduler-role"; then

    aws iam create-role \
        --role-name ${PROJECT_NAME}-scheduler-role \
        --assume-role-policy-document file:///tmp/scheduler-trust-policy.json > /dev/null
    echo "✅ Scheduler role created"
else
    echo "✅ Scheduler role already exists — skipping creation"
fi

# Permissions policy (always re-apply to ensure correctness)
cat > /tmp/scheduler-permissions.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": "lambda:InvokeFunction",
    "Resource": "arn:aws:lambda:${AWS_REGION}:${AWS_ACCOUNT_ID}:function:${LAMBDA_FUNCTION}"
  }]
}
EOF

aws iam put-role-policy \
    --role-name ${PROJECT_NAME}-scheduler-role \
    --policy-name InvokeLambdaPolicy \
    --policy-document file:///tmp/scheduler-permissions.json

export SCHEDULER_ROLE_ARN=$(aws iam get-role \
    --role-name ${PROJECT_NAME}-scheduler-role \
    --query 'Role.Arn' --output text)

echo "✅ Scheduler Role ARN : ${SCHEDULER_ROLE_ARN}"

# -----------------------------------------------------------------------------
# Task 3.5 — Create or Enable Monthly Analysis Schedule
# -----------------------------------------------------------------------------
echo ""
echo "[ Task 3.5 ] Setting up Monthly Analysis Schedule..."

LAMBDA_ARN="arn:aws:lambda:${AWS_REGION}:${AWS_ACCOUNT_ID}:function:${LAMBDA_FUNCTION}"

# Check if schedule exists
MONTHLY_EXISTS=$(aws scheduler list-schedules \
    --name-prefix ${PROJECT_NAME}-monthly-analysis \
    --query 'Schedules[0].Name' --output text 2>/dev/null || echo "")

if [ -z "${MONTHLY_EXISTS}" ] || [ "${MONTHLY_EXISTS}" == "None" ]; then
    aws scheduler create-schedule \
        --name ${PROJECT_NAME}-monthly-analysis \
        --schedule-expression "rate(30 days)" \
        --target "{\"RoleArn\":\"${SCHEDULER_ROLE_ARN}\",\"Arn\":\"${LAMBDA_ARN}\"}" \
        --flexible-time-window '{"Mode": "OFF"}' \
        --description "Monthly carbon footprint optimization analysis" \
        --region ${AWS_REGION} > /dev/null
    echo "✅ Monthly schedule created"
else
    # Re-enable if it was disabled
    aws scheduler update-schedule \
        --name ${PROJECT_NAME}-monthly-analysis \
        --schedule-expression "rate(30 days)" \
        --target "{\"RoleArn\":\"${SCHEDULER_ROLE_ARN}\",\"Arn\":\"${LAMBDA_ARN}\"}" \
        --flexible-time-window '{"Mode": "OFF"}' \
        --state ENABLED \
        --region ${AWS_REGION} > /dev/null
    echo "✅ Monthly schedule already exists — re-enabled"
fi

# -----------------------------------------------------------------------------
# Task 3.6 — Create or Enable Weekly Trend Schedule
# -----------------------------------------------------------------------------
echo ""
echo "[ Task 3.6 ] Setting up Weekly Trend Schedule..."

WEEKLY_EXISTS=$(aws scheduler list-schedules \
    --name-prefix ${PROJECT_NAME}-weekly-trends \
    --query 'Schedules[0].Name' --output text 2>/dev/null || echo "")

if [ -z "${WEEKLY_EXISTS}" ] || [ "${WEEKLY_EXISTS}" == "None" ]; then
    aws scheduler create-schedule \
        --name ${PROJECT_NAME}-weekly-trends \
        --schedule-expression "rate(7 days)" \
        --target "{\"RoleArn\":\"${SCHEDULER_ROLE_ARN}\",\"Arn\":\"${LAMBDA_ARN}\"}" \
        --flexible-time-window '{"Mode": "OFF"}' \
        --description "Weekly carbon footprint trend monitoring" \
        --region ${AWS_REGION} > /dev/null
    echo "✅ Weekly schedule created"
else
    aws scheduler update-schedule \
        --name ${PROJECT_NAME}-weekly-trends \
        --schedule-expression "rate(7 days)" \
        --target "{\"RoleArn\":\"${SCHEDULER_ROLE_ARN}\",\"Arn\":\"${LAMBDA_ARN}\"}" \
        --flexible-time-window '{"Mode": "OFF"}' \
        --state ENABLED \
        --region ${AWS_REGION} > /dev/null
    echo "✅ Weekly schedule already exists — re-enabled"
fi

# -----------------------------------------------------------------------------
# Verification
# -----------------------------------------------------------------------------
echo ""
echo "================================================"
echo "  Verification"
echo "================================================"

echo ""
echo "[ SNS Topic ]"
aws sns get-topic-attributes \
    --topic-arn ${SNS_TOPIC_ARN} \
    --query 'Attributes.TopicArn' --region ${AWS_REGION}

echo ""
echo "[ Email Subscription ]"
aws sns list-subscriptions-by-topic \
    --topic-arn ${SNS_TOPIC_ARN} \
    --query 'Subscriptions[*].[Protocol,Endpoint,SubscriptionArn]' \
    --output table --region ${AWS_REGION}

echo ""
echo "[ EventBridge Schedules ]"
aws scheduler list-schedules \
    --name-prefix ${PROJECT_NAME} \
    --query 'Schedules[*].[Name,State]' \
    --output table --region ${AWS_REGION}

echo ""
echo "[ Lambda Environment ]"
aws lambda get-function-configuration \
    --function-name ${LAMBDA_FUNCTION} \
    --query 'Environment.Variables' --region ${AWS_REGION}

echo ""
echo "================================================"
echo "  Section 3 Deployment Complete ✅"
echo "================================================"