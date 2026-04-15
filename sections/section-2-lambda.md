# Section 2 — Lambda Function Development

**Assigned To:** Soham Kulkarni
**Estimated Time:** 3–4 hours  
**Branch:** `feature/section-2-lambda`  
**Dependencies:** Section 1 must be merged (IAM Role ARN required)

---

## 🎯 Objective

Develop and deploy the core Lambda function that serves as the intelligence engine for carbon footprint analysis. The function queries Cost Explorer, correlates costs with carbon emission factors, stores results in DynamoDB, and triggers SNS notifications for high-impact opportunities.

---

## ✅ Prerequisites

- [ ] Section 1 merged and all AWS resources confirmed active
- [ ] AWS CLI v2 installed and configured
- [ ] Python 3.11+ installed: `python3 --version`
- [ ] `zip` utility available: `zip --version`
- [ ] Environment variables exported:
  ```bash
  export AWS_REGION=<your-region>
  export AWS_ACCOUNT_ID=<your-account-id>
  export PROJECT_NAME=carbon-optimizer-<suffix>
  export LAMBDA_FUNCTION=${PROJECT_NAME}-analyzer
  export DYNAMODB_TABLE=${PROJECT_NAME}-metrics
  export S3_BUCKET=${PROJECT_NAME}-data

  # Get the IAM role ARN from Section 1 output
  export LAMBDA_ROLE_ARN=$(aws iam get-role \
      --role-name ${PROJECT_NAME}-lambda-role \
      --query 'Role.Arn' --output text)
  ```
- [ ] Repository on branch `feature/section-2-lambda`

---

## 📁 Files You Will Create

```
carbon-optimizer/
└── lambda-function/
    └── index.py
```

---

## 🔨 Tasks

### Task 2.1 — Create Lambda Function Directory

**Commit message:** `chore(lambda): initialize lambda function directory`

```bash
mkdir -p lambda-function
```

---

### Task 2.2 — Write the Lambda Handler

**Commit message:** `feat(lambda): implement main handler and cost explorer integration`

Create `lambda-function/index.py` with the following content:

```python
import json
import boto3
import os
from datetime import datetime, timedelta
from decimal import Decimal
import logging

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
ce_client = boto3.client('ce')
dynamodb = boto3.resource('dynamodb')
s3_client = boto3.client('s3')
sns_client = boto3.client('sns')
ssm_client = boto3.client('ssm')

# Environment variables
TABLE_NAME = os.environ['DYNAMODB_TABLE']
S3_BUCKET = os.environ['S3_BUCKET']
SNS_TOPIC_ARN = os.environ['SNS_TOPIC_ARN']

table = dynamodb.Table(TABLE_NAME)


def lambda_handler(event, context):
    """Main handler for carbon footprint optimization analysis."""
    try:
        logger.info("Starting carbon footprint optimization analysis")

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=30)

        cost_data = get_cost_and_usage_data(start_date, end_date)
        carbon_analysis = analyze_carbon_footprint(cost_data)
        store_metrics(carbon_analysis)
        recommendations = generate_recommendations(carbon_analysis)

        if recommendations['high_impact_actions']:
            send_optimization_notifications(recommendations)

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Carbon footprint analysis completed successfully',
                'recommendations_count': len(recommendations['all_actions']),
                'high_impact_count': len(recommendations['high_impact_actions'])
            })
        }

    except Exception as e:
        logger.error(f"Error in carbon footprint analysis: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def get_cost_and_usage_data(start_date, end_date):
    """Retrieve cost and usage data from Cost Explorer."""
    try:
        response = ce_client.get_cost_and_usage(
            TimePeriod={
                'Start': start_date.strftime('%Y-%m-%d'),
                'End': end_date.strftime('%Y-%m-%d')
            },
            Granularity='DAILY',
            Metrics=['BlendedCost', 'UsageQuantity'],
            GroupBy=[
                {'Type': 'DIMENSION', 'Key': 'SERVICE'},
                {'Type': 'DIMENSION', 'Key': 'REGION'}
            ]
        )
        return response['ResultsByTime']
    except Exception as e:
        logger.error(f"Error retrieving cost data: {str(e)}")
        raise


def analyze_carbon_footprint(cost_data):
    """Analyze carbon footprint patterns based on cost and usage data."""
    analysis = {
        'total_cost': 0,
        'estimated_carbon_kg': 0,
        'services': {},
        'regions': {},
        'optimization_potential': 0
    }

    # Carbon intensity factors (kg CO2e per USD) by service type
    carbon_factors = {
        'Amazon Elastic Compute Cloud - Compute': 0.000533,
        'Amazon Simple Storage Service': 0.000164,
        'Amazon Relational Database Service': 0.000688,
        'AWS Lambda': 0.000025,
        'Amazon CloudFront': 0.00004,
        'Amazon DynamoDB': 0.000045,
        'Amazon Elastic Load Balancing': 0.000312,
        'Amazon Virtual Private Cloud': 0.000089
    }

    # Regional carbon intensity factors (relative multipliers)
    regional_factors = {
        'us-east-1': 0.85,
        'us-west-2': 0.42,
        'eu-west-1': 0.65,
        'ap-southeast-2': 1.2,
        'ca-central-1': 0.23,
        'eu-north-1': 0.11
    }

    for time_period in cost_data:
        for group in time_period.get('Groups', []):
            service = group['Keys'][0] if len(group['Keys']) > 0 else 'Unknown'
            region = group['Keys'][1] if len(group['Keys']) > 1 else 'global'

            cost = float(group['Metrics']['BlendedCost']['Amount'])
            analysis['total_cost'] += cost

            service_factor = carbon_factors.get(service, 0.0003)
            regional_factor = regional_factors.get(region, 1.0)
            estimated_carbon = cost * service_factor * regional_factor
            analysis['estimated_carbon_kg'] += estimated_carbon

            if service not in analysis['services']:
                analysis['services'][service] = {
                    'cost': 0, 'carbon_kg': 0, 'optimization_score': 0
                }

            analysis['services'][service]['cost'] += cost
            analysis['services'][service]['carbon_kg'] += estimated_carbon

            if cost > 0:
                analysis['services'][service]['optimization_score'] = (
                    estimated_carbon / cost * 1000
                )

    return analysis


def generate_recommendations(analysis):
    """Generate carbon footprint optimization recommendations."""
    recommendations = {
        'all_actions': [],
        'high_impact_actions': [],
        'estimated_savings': {'cost': 0, 'carbon_kg': 0}
    }

    for service, metrics in analysis['services'].items():
        if metrics['cost'] > 10 and metrics['optimization_score'] > 0.2:
            recommendation = {
                'service': service,
                'current_cost': metrics['cost'],
                'current_carbon_kg': metrics['carbon_kg'],
                'action': determine_optimization_action(service, metrics),
                'estimated_cost_savings': metrics['cost'] * 0.15,
                'estimated_carbon_reduction': metrics['carbon_kg'] * 0.25
            }
            recommendations['all_actions'].append(recommendation)

            if metrics['cost'] > 100:
                recommendations['high_impact_actions'].append(recommendation)
                recommendations['estimated_savings']['cost'] += recommendation['estimated_cost_savings']
                recommendations['estimated_savings']['carbon_kg'] += recommendation['estimated_carbon_reduction']

    return recommendations


def determine_optimization_action(service, metrics):
    """Determine specific optimization action for a service."""
    action_map = {
        'Amazon Elastic Compute Cloud - Compute': 'Consider rightsizing instances or migrating to Graviton processors for up to 20% energy efficiency improvement',
        'Amazon Simple Storage Service': 'Implement Intelligent Tiering and lifecycle policies to reduce storage footprint',
        'Amazon Relational Database Service': 'Evaluate Aurora Serverless v2 or instance rightsizing for better resource utilization',
        'AWS Lambda': 'Optimize memory allocation and consider ARM-based architecture for improved efficiency',
        'Amazon CloudFront': 'Review caching strategies and enable compression to reduce data transfer',
        'Amazon DynamoDB': 'Consider on-demand billing for variable workloads to optimize resource usage'
    }
    return action_map.get(service, 'Review resource utilization and consider sustainable alternatives')


def store_metrics(analysis):
    """Store analysis results in DynamoDB."""
    timestamp = datetime.now().isoformat()

    table.put_item(Item={
        'MetricType': 'OVERALL_ANALYSIS',
        'Timestamp': timestamp,
        'TotalCost': Decimal(str(analysis['total_cost'])),
        'EstimatedCarbonKg': Decimal(str(analysis['estimated_carbon_kg'])),
        'ServiceCount': len(analysis['services'])
    })

    for service, metrics in analysis['services'].items():
        table.put_item(Item={
            'MetricType': f'SERVICE_{service.replace(" ", "_").replace("-", "_").upper()}',
            'Timestamp': timestamp,
            'ServiceName': service,
            'Cost': Decimal(str(metrics['cost'])),
            'CarbonKg': Decimal(str(metrics['carbon_kg'])),
            'CarbonIntensity': Decimal(str(metrics['optimization_score']))
        })


def send_optimization_notifications(recommendations):
    """Send notifications about optimization opportunities."""
    message = f"""
Carbon Footprint Optimization Report

High-Impact Opportunities Found: {len(recommendations['high_impact_actions'])}

Estimated Monthly Savings:
- Cost: ${recommendations['estimated_savings']['cost']:.2f}
- Carbon: {recommendations['estimated_savings']['carbon_kg']:.3f} kg CO2e

Top Recommendations:
"""
    for i, action in enumerate(recommendations['high_impact_actions'][:3], 1):
        message += f"""
{i}. {action['service']}
   Current Cost: ${action['current_cost']:.2f}
   Carbon Impact: {action['current_carbon_kg']:.3f} kg CO2e
   Action: {action['action']}
"""

    try:
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject='Carbon Footprint Optimization Report',
            Message=message
        )
    except Exception as e:
        logger.error(f"Error sending notification: {str(e)}")
```

---

### Task 2.3 — Package the Lambda Function

**Commit message:** `build(lambda): create deployment zip package`

```bash
cd lambda-function
zip -r ../lambda-function.zip .
cd ..
echo "✅ lambda-function.zip created ($(du -sh lambda-function.zip | cut -f1))"
```

**Expected Output:**
```
✅ lambda-function.zip created (5.2K)
```

---

### Task 2.4 — Deploy Lambda to AWS

**Commit message:** `feat(lambda): deploy analyzer function with environment variables`

```bash
# SNS ARN will be created in Section 3 — use placeholder format
SNS_TOPIC_ARN="arn:aws:sns:${AWS_REGION}:${AWS_ACCOUNT_ID}:${PROJECT_NAME}-notifications"

aws lambda create-function \
    --function-name ${LAMBDA_FUNCTION} \
    --runtime python3.11 \
    --role ${LAMBDA_ROLE_ARN} \
    --handler index.lambda_handler \
    --zip-file fileb://lambda-function.zip \
    --timeout 300 \
    --memory-size 512 \
    --environment Variables="{
        \"DYNAMODB_TABLE\":\"${DYNAMODB_TABLE}\",
        \"S3_BUCKET\":\"${S3_BUCKET}\",
        \"SNS_TOPIC_ARN\":\"${SNS_TOPIC_ARN}\"
    }" \
    --tags Project=${PROJECT_NAME},Purpose=CarbonFootprintOptimization

echo "✅ Lambda function deployed: ${LAMBDA_FUNCTION}"
```

**Expected Output:**
```json
{
    "FunctionName": "carbon-optimizer-<suffix>-analyzer",
    "FunctionArn": "arn:aws:lambda:<region>:<account>:function:carbon-optimizer-<suffix>-analyzer",
    "Runtime": "python3.11",
    "State": "Active"
}
✅ Lambda function deployed: carbon-optimizer-<suffix>-analyzer
```

---

### Task 2.5 — Update Lambda if Code Changes

**Commit message:** `fix(lambda): update function code after review`

Use this command if you need to redeploy after making code changes:

```bash
cd lambda-function && zip -r ../lambda-function.zip . && cd ..

aws lambda update-function-code \
    --function-name ${LAMBDA_FUNCTION} \
    --zip-file fileb://lambda-function.zip

echo "✅ Lambda function code updated"
```

---

## 🔍 Verification Checklist

```bash
# 1. Confirm function exists and is Active
aws lambda get-function \
    --function-name ${LAMBDA_FUNCTION} \
    --query 'Configuration.[FunctionName,State,Runtime]'
# Expected: ["carbon-optimizer-<suffix>-analyzer", "Active", "python3.11"]

# 2. Confirm environment variables are set
aws lambda get-function-configuration \
    --function-name ${LAMBDA_FUNCTION} \
    --query 'Environment.Variables'
# Expected: DYNAMODB_TABLE, S3_BUCKET, SNS_TOPIC_ARN all present

# 3. Test invocation (will fail on Cost Explorer if no billing data, but should return 200 or a known error)
aws lambda invoke \
    --function-name ${LAMBDA_FUNCTION} \
    --payload '{}' \
    response.json && cat response.json
```

---

## 📝 Commit Summary

| # | Commit Message | Files Changed |
|---|---------------|---------------|
| 1 | `chore(lambda): initialize lambda function directory` | `lambda-function/` |
| 2 | `feat(lambda): implement main handler and cost explorer integration` | `lambda-function/index.py` |
| 3 | `build(lambda): create deployment zip package` | `lambda-function.zip` (gitignored) |
| 4 | `feat(lambda): deploy analyzer function with environment variables` | `scripts/deploy.sh` |
| 5 | `fix(lambda): update function code after review` | `lambda-function/index.py` (if needed) |

---

## 🚀 Pull Request Instructions

1. Push your branch: `git push origin feature/section-2-lambda`
2. Open a PR to `main` titled: **"Section 2: Lambda Function Development"**
3. Add label: `backend`
4. Paste Lambda function ARN and test invocation output in the PR description
5. Request review from Team Member 5 (testing lead)

> ⚠️ **Section 3 (EventBridge)** depends on the Lambda function ARN from this section.
