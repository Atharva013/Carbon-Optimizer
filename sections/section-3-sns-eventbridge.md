# Section 3 — SNS Notifications & EventBridge Schedules

**Assigned To:** Team Member 3  
**Estimated Time:** 2–3 hours  
**Branch:** `feature/section-3-sns-eventbridge`  
**Dependencies:** Section 1 (IAM Role ARN) and Section 2 (Lambda Function ARN) must be merged

---

## 🎯 Objective

Set up the notification and automation scheduling layer. This includes creating an SNS topic for stakeholder alerts and configuring EventBridge schedules for automated monthly and weekly carbon footprint analysis runs.

---

## ✅ Prerequisites

- [ ] Sections 1 and 2 merged and all resources confirmed active
- [ ] AWS CLI v2 installed and configured
- [ ] IAM permissions for SNS and EventBridge Scheduler
- [ ] Environment variables exported:
  ```bash
  export AWS_REGION=<your-region>
  export AWS_ACCOUNT_ID=<your-account-id>
  export PROJECT_NAME=carbon-optimizer-<suffix>
  export LAMBDA_FUNCTION=${PROJECT_NAME}-analyzer

  # Retrieve existing role ARN
  export LAMBDA_ROLE_ARN=$(aws iam get-role \
      --role-name ${PROJECT_NAME}-lambda-role \
      --query 'Role.Arn' --output text)
  ```
- [ ] Repository on branch `feature/section-3-sns-eventbridge`

---

## 📁 Files You Will Create / Modify

```
carbon-optimizer/
└── scripts/
    └── deploy.sh    (add SNS + EventBridge commands)
```

---

## 🔨 Tasks

### Task 3.1 — Create SNS Topic

**Commit message:** `feat(sns): create carbon optimization notifications topic`

```bash
aws sns create-topic \
    --name ${PROJECT_NAME}-notifications \
    --tags Key=Project,Value=${PROJECT_NAME} \
           Key=Purpose,Value=CarbonOptimizationAlerts

# Retrieve and export the topic ARN
export SNS_TOPIC_ARN=$(aws sns list-topics \
    --query "Topics[?contains(TopicArn, '${PROJECT_NAME}-notifications')].TopicArn" \
    --output text)

echo "✅ SNS Topic created: ${SNS_TOPIC_ARN}"
```

**Expected Output:**
```
✅ SNS Topic created: arn:aws:sns:<region>:<account>:carbon-optimizer-<suffix>-notifications
```

---

### Task 3.2 — Subscribe Email to SNS Topic

**Commit message:** `feat(sns): add email subscription for optimization alerts`

```bash
# Prompt for email address
read -p "Enter email address for carbon optimization notifications: " EMAIL_ADDRESS

aws sns subscribe \
    --topic-arn ${SNS_TOPIC_ARN} \
    --protocol email \
    --notification-endpoint ${EMAIL_ADDRESS}

echo "✅ Subscription request sent to: ${EMAIL_ADDRESS}"
echo "⚠️  Check your email and click 'Confirm subscription' before proceeding."
```

**Expected Output:**
```
✅ Subscription request sent to: team@example.com
⚠️  Check your email and click 'Confirm subscription' before proceeding.
```

> ⚠️ The SNS subscription must be confirmed via email before notifications will be delivered. Have the designated recipient confirm before you proceed to testing.

---

### Task 3.3 — Update Lambda Environment with SNS ARN

**Commit message:** `feat(lambda): update environment variables with confirmed SNS topic ARN`

Now that the SNS topic exists, update the Lambda function environment variable to the real ARN:

```bash
aws lambda update-function-configuration \
    --function-name ${LAMBDA_FUNCTION} \
    --environment Variables="{
        \"DYNAMODB_TABLE\":\"${DYNAMODB_TABLE:-${PROJECT_NAME}-metrics}\",
        \"S3_BUCKET\":\"${S3_BUCKET:-${PROJECT_NAME}-data}\",
        \"SNS_TOPIC_ARN\":\"${SNS_TOPIC_ARN}\"
    }"

echo "✅ Lambda environment updated with SNS topic ARN"
```

**Expected Output:**
```json
{
    "FunctionName": "carbon-optimizer-<suffix>-analyzer",
    "Environment": {
        "Variables": {
            "DYNAMODB_TABLE": "carbon-optimizer-<suffix>-metrics",
            "S3_BUCKET": "carbon-optimizer-<suffix>-data",
            "SNS_TOPIC_ARN": "arn:aws:sns:<region>:<account>:carbon-optimizer-<suffix>-notifications"
        }
    }
}
✅ Lambda environment updated with SNS topic ARN
```

---

### Task 3.4 — Create EventBridge Scheduler Role

**Commit message:** `feat(iam): add eventbridge scheduler execution role`

EventBridge Scheduler needs its own role to invoke Lambda:

```bash
# Create trust policy for EventBridge Scheduler
cat > /tmp/scheduler-trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "scheduler.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create scheduler role
aws iam create-role \
    --role-name ${PROJECT_NAME}-scheduler-role \
    --assume-role-policy-document file:///tmp/scheduler-trust-policy.json

# Attach Lambda invoke permission
cat > /tmp/scheduler-permissions.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "lambda:InvokeFunction",
      "Resource": "arn:aws:lambda:${AWS_REGION}:${AWS_ACCOUNT_ID}:function:${LAMBDA_FUNCTION}"
    }
  ]
}
EOF

aws iam put-role-policy \
    --role-name ${PROJECT_NAME}-scheduler-role \
    --policy-name InvokeLambdaPolicy \
    --policy-document file:///tmp/scheduler-permissions.json

export SCHEDULER_ROLE_ARN=$(aws iam get-role \
    --role-name ${PROJECT_NAME}-scheduler-role \
    --query 'Role.Arn' --output text)

echo "✅ Scheduler role created: ${SCHEDULER_ROLE_ARN}"
```

---

### Task 3.5 — Create Monthly Analysis Schedule

**Commit message:** `feat(eventbridge): create monthly carbon analysis schedule`

```bash
LAMBDA_ARN="arn:aws:lambda:${AWS_REGION}:${AWS_ACCOUNT_ID}:function:${LAMBDA_FUNCTION}"

aws scheduler create-schedule \
    --name ${PROJECT_NAME}-monthly-analysis \
    --schedule-expression "rate(30 days)" \
    --target "{
        \"RoleArn\": \"${SCHEDULER_ROLE_ARN}\",
        \"Arn\": \"${LAMBDA_ARN}\"
    }" \
    --flexible-time-window '{"Mode": "OFF"}' \
    --description "Monthly carbon footprint optimization analysis"

echo "✅ Monthly analysis schedule created"
```

**Expected Output:**
```json
{
    "ScheduleArn": "arn:aws:scheduler:<region>:<account>:schedule/default/carbon-optimizer-<suffix>-monthly-analysis"
}
✅ Monthly analysis schedule created
```

---

### Task 3.6 — Create Weekly Trend Schedule

**Commit message:** `feat(eventbridge): create weekly trend monitoring schedule`

```bash
aws scheduler create-schedule \
    --name ${PROJECT_NAME}-weekly-trends \
    --schedule-expression "rate(7 days)" \
    --target "{
        \"RoleArn\": \"${SCHEDULER_ROLE_ARN}\",
        \"Arn\": \"${LAMBDA_ARN}\"
    }" \
    --flexible-time-window '{"Mode": "OFF"}' \
    --description "Weekly carbon footprint trend monitoring"

echo "✅ Weekly trend monitoring schedule created"
```

---

## 🔍 Verification Checklist

```bash
# 1. Confirm SNS topic exists
aws sns get-topic-attributes \
    --topic-arn ${SNS_TOPIC_ARN} \
    --query 'Attributes.TopicArn'

# 2. Confirm email subscription status
aws sns list-subscriptions-by-topic \
    --topic-arn ${SNS_TOPIC_ARN} \
    --query 'Subscriptions[*].[Protocol,Endpoint,SubscriptionArn]'
# Expected: email subscription with status "PendingConfirmation" or "Confirmed"

# 3. Confirm both EventBridge schedules exist
aws scheduler list-schedules \
    --name-prefix ${PROJECT_NAME} \
    --query 'Schedules[*].[Name,State]'
# Expected: two schedules with State=ENABLED

# 4. Confirm Lambda env var has correct SNS ARN
aws lambda get-function-configuration \
    --function-name ${LAMBDA_FUNCTION} \
    --query 'Environment.Variables.SNS_TOPIC_ARN'
```

---

## 📝 Commit Summary

| # | Commit Message | Files Changed |
|---|---------------|---------------|
| 1 | `feat(sns): create carbon optimization notifications topic` | `scripts/deploy.sh` |
| 2 | `feat(sns): add email subscription for optimization alerts` | `scripts/deploy.sh` |
| 3 | `feat(lambda): update environment variables with confirmed SNS topic ARN` | `scripts/deploy.sh` |
| 4 | `feat(iam): add eventbridge scheduler execution role` | `scripts/deploy.sh` |
| 5 | `feat(eventbridge): create monthly carbon analysis schedule` | `scripts/deploy.sh` |
| 6 | `feat(eventbridge): create weekly trend monitoring schedule` | `scripts/deploy.sh` |

---

## 🚀 Pull Request Instructions

1. Push your branch: `git push origin feature/section-3-sns-eventbridge`
2. Open a PR to `main` titled: **"Section 3: SNS Notifications & EventBridge Schedules"**
3. Add label: `automation`
4. Paste the schedule list output and SNS subscription status in the PR description
5. Request review from Team Member 5 (testing lead)
