#!/bin/bash
# =============================================================================
# Section 5 — Dashboard Deployment Script (Idempotent)
# Deploys: Dashboard API Lambda + API Gateway + S3 Static Website
# =============================================================================
set -e

export AWS_REGION=${AWS_REGION:-ap-south-1}
export AWS_ACCOUNT_ID=${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}
export PROJECT_NAME=${PROJECT_NAME:-carbon-optimizer-cloud}
export DYNAMODB_TABLE=${DYNAMODB_TABLE:-${PROJECT_NAME}-metrics}
export S3_BUCKET=${S3_BUCKET:-${PROJECT_NAME}-data}
export DASHBOARD_FUNCTION="${PROJECT_NAME}-dashboard-api"

echo "=================================================="
echo "  Carbon Optimizer — Section 5 Dashboard Deploy"
echo "  Project : ${PROJECT_NAME}"
echo "  Region  : ${AWS_REGION}"
echo "  Table   : ${DYNAMODB_TABLE}"
echo "=================================================="

# Get Lambda role ARN
export LAMBDA_ROLE_ARN=$(aws iam get-role \
    --role-name ${PROJECT_NAME}-lambda-role \
    --query 'Role.Arn' --output text --region ${AWS_REGION})
echo "✅ Lambda Role ARN: ${LAMBDA_ROLE_ARN}"

# ── Step 1: Package Dashboard API Lambda ─────────────────────────────────────
echo ""
echo "[ Step 1 ] Packaging Dashboard API Lambda..."
cd dashboard/dashboard-api
zip -r /tmp/dashboard-api.zip index.py > /dev/null
cd ../..
echo "✅ Packaged: /tmp/dashboard-api.zip"

# ── Step 2: Create or Update Dashboard Lambda ────────────────────────────────
echo ""
echo "[ Step 2 ] Deploying Dashboard Lambda function..."

FUNC_EXISTS=$(aws lambda get-function \
    --function-name ${DASHBOARD_FUNCTION} \
    --region ${AWS_REGION} \
    --query 'Configuration.FunctionName' \
    --output text 2>/dev/null || echo "")

if [ -z "${FUNC_EXISTS}" ] || [ "${FUNC_EXISTS}" == "None" ]; then
    echo "  Creating new function: ${DASHBOARD_FUNCTION}"
    aws lambda create-function \
        --function-name ${DASHBOARD_FUNCTION} \
        --runtime python3.11 \
        --handler index.lambda_handler \
        --role ${LAMBDA_ROLE_ARN} \
        --zip-file fileb:///tmp/dashboard-api.zip \
        --environment "Variables={DYNAMODB_TABLE=${DYNAMODB_TABLE}}" \
        --timeout 30 \
        --memory-size 256 \
        --tags Project=${PROJECT_NAME},Purpose=DashboardAPI \
        --region ${AWS_REGION} > /dev/null

    echo "  Waiting for Lambda to become Active..."
    aws lambda wait function-active \
        --function-name ${DASHBOARD_FUNCTION} \
        --region ${AWS_REGION}
    echo "✅ Dashboard Lambda created and active"
else
    echo "  Function exists — updating code..."
    aws lambda update-function-code \
        --function-name ${DASHBOARD_FUNCTION} \
        --zip-file fileb:///tmp/dashboard-api.zip \
        --region ${AWS_REGION} > /dev/null

    aws lambda wait function-updated \
        --function-name ${DASHBOARD_FUNCTION} \
        --region ${AWS_REGION}

    aws lambda update-function-configuration \
        --function-name ${DASHBOARD_FUNCTION} \
        --environment "Variables={DYNAMODB_TABLE=${DYNAMODB_TABLE}}" \
        --region ${AWS_REGION} > /dev/null

    echo "✅ Dashboard Lambda updated"
fi

export DASHBOARD_LAMBDA_ARN=$(aws lambda get-function \
    --function-name ${DASHBOARD_FUNCTION} \
    --query 'Configuration.FunctionArn' \
    --output text --region ${AWS_REGION})

# ── Step 3: Create or Reuse API Gateway ──────────────────────────────────────
echo ""
echo "[ Step 3 ] Setting up API Gateway..."

API_NAME="${PROJECT_NAME}-dashboard-api"

# Check if API already exists
EXISTING_API_ID=$(aws apigateway get-rest-apis \
    --region ${AWS_REGION} \
    --query "items[?name=='${API_NAME}'].id" \
    --output text 2>/dev/null | head -1)

if [ -z "${EXISTING_API_ID}" ] || [ "${EXISTING_API_ID}" == "None" ]; then
    echo "  Creating new API Gateway..."
    API_ID=$(aws apigateway create-rest-api \
        --name "${API_NAME}" \
        --description "Carbon Optimizer Dashboard API" \
        --region ${AWS_REGION} \
        --query 'id' --output text)
    echo "  API Gateway created: ${API_ID}"

    ROOT_ID=$(aws apigateway get-resources \
        --rest-api-id ${API_ID} \
        --region ${AWS_REGION} \
        --query 'items[0].id' --output text)

    # Create {proxy+} resource
    RESOURCE_ID=$(aws apigateway create-resource \
        --rest-api-id ${API_ID} \
        --parent-id ${ROOT_ID} \
        --path-part '{proxy+}' \
        --region ${AWS_REGION} \
        --query 'id' --output text)

    # ANY method on {proxy+}
    aws apigateway put-method \
        --rest-api-id ${API_ID} \
        --resource-id ${RESOURCE_ID} \
        --http-method ANY \
        --authorization-type NONE \
        --region ${AWS_REGION} > /dev/null

    # Lambda proxy integration
    aws apigateway put-integration \
        --rest-api-id ${API_ID} \
        --resource-id ${RESOURCE_ID} \
        --http-method ANY \
        --type AWS_PROXY \
        --integration-http-method POST \
        --uri "arn:aws:apigateway:${AWS_REGION}:lambda:path/2015-03-31/functions/${DASHBOARD_LAMBDA_ARN}/invocations" \
        --region ${AWS_REGION} > /dev/null

    # Deploy to prod stage
    aws apigateway create-deployment \
        --rest-api-id ${API_ID} \
        --stage-name prod \
        --region ${AWS_REGION} > /dev/null

    # Allow API Gateway to invoke Lambda
    aws lambda add-permission \
        --function-name ${DASHBOARD_FUNCTION} \
        --statement-id apigateway-dashboard-invoke \
        --action lambda:InvokeFunction \
        --principal apigateway.amazonaws.com \
        --source-arn "arn:aws:execute-api:${AWS_REGION}:${AWS_ACCOUNT_ID}:${API_ID}/*/*" \
        --region ${AWS_REGION} > /dev/null

    echo "✅ API Gateway deployed: ${API_ID}"
else
    API_ID="${EXISTING_API_ID}"
    echo "✅ API Gateway already exists: ${API_ID} — redeploying stage..."
    aws apigateway create-deployment \
        --rest-api-id ${API_ID} \
        --stage-name prod \
        --region ${AWS_REGION} > /dev/null
    echo "✅ Stage prod redeployed"
fi

export API_ENDPOINT="https://${API_ID}.execute-api.${AWS_REGION}.amazonaws.com/prod"
echo "  API Endpoint: ${API_ENDPOINT}"

# ── Step 4: Inject API endpoint into HTML ────────────────────────────────────
echo ""
echo "[ Step 4 ] Injecting API endpoint into dashboard HTML..."
sed -i "s|API_ENDPOINT_PLACEHOLDER|${API_ENDPOINT}|g" dashboard/index.html
echo "✅ API endpoint injected: ${API_ENDPOINT}"

# ── Step 5: Enable S3 Static Website Hosting ─────────────────────────────────
echo ""
echo "[ Step 5 ] Enabling S3 static website hosting..."

aws s3api put-bucket-website \
    --bucket ${S3_BUCKET} \
    --website-configuration '{
        "IndexDocument": {"Suffix": "index.html"},
        "ErrorDocument": {"Key": "index.html"}
    }' \
    --region ${AWS_REGION}

# Update bucket policy — merge with existing CUR policy
cat > /tmp/website-policy.json << POLICY
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CURGetBucketPermissions",
      "Effect": "Allow",
      "Principal": { "Service": "billingreports.amazonaws.com" },
      "Action": ["s3:GetBucketAcl", "s3:GetBucketPolicy"],
      "Resource": "arn:aws:s3:::${S3_BUCKET}"
    },
    {
      "Sid": "CURPutObject",
      "Effect": "Allow",
      "Principal": { "Service": "billingreports.amazonaws.com" },
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::${S3_BUCKET}/cost-usage-reports/*"
    },
    {
      "Sid": "PublicDashboardRead",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::${S3_BUCKET}/dashboard/*"
    }
  ]
}
POLICY

# Disable block public access first (required for static website)
aws s3api put-public-access-block \
    --bucket ${S3_BUCKET} \
    --public-access-block-configuration \
      "BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false" \
    --region ${AWS_REGION}

aws s3api put-bucket-policy \
    --bucket ${S3_BUCKET} \
    --policy file:///tmp/website-policy.json \
    --region ${AWS_REGION}

echo "✅ S3 static website configured"

# ── Step 6: Upload dashboard to S3 ───────────────────────────────────────────
echo ""
echo "[ Step 6 ] Uploading dashboard to S3..."
aws s3 cp dashboard/index.html \
    s3://${S3_BUCKET}/dashboard/index.html \
    --content-type "text/html" \
    --cache-control "no-cache, max-age=0" \
    --region ${AWS_REGION}

echo "✅ Dashboard uploaded"

export DASHBOARD_URL="http://${S3_BUCKET}.s3-website.${AWS_REGION}.amazonaws.com/dashboard/index.html"

# ── Verification ──────────────────────────────────────────────────────────────
echo ""
echo "=================================================="
echo "  Verification"
echo "=================================================="

echo ""
echo "[ Dashboard Lambda ]"
aws lambda get-function \
    --function-name ${DASHBOARD_FUNCTION} \
    --query 'Configuration.[FunctionName,State,Runtime]' \
    --region ${AWS_REGION}

echo ""
echo "[ API Gateway Health ]"
curl -s "${API_ENDPOINT}/health" || echo "(API may take a moment to propagate)"

echo ""
echo "[ API Summary Test ]"
curl -s "${API_ENDPOINT}/summary" | python3 -m json.tool 2>/dev/null | head -20

echo ""
echo "=================================================="
echo "  Section 5 Deployment Complete ✅"
echo ""
echo "  Dashboard URL : ${DASHBOARD_URL}"
echo "  API Endpoint  : ${API_ENDPOINT}"
echo "=================================================="
echo ""
echo "  If dashboard shows no data, run the analyzer Lambda first:"
echo "  aws lambda invoke --function-name ${PROJECT_NAME}-analyzer --payload '{}' /tmp/r.json && cat /tmp/r.json"