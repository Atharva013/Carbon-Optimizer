# Section 5 — Real-Time Dashboard & GUI

**Estimated Time:** 3–4 hours  
**Branch:** `feature/section-5-dashboard`  
**Dependencies:** Sections 1–4 must be merged and all AWS resources active

---

## 🎯 Objective

Build a real-time web dashboard that visualizes all carbon footprint data from the system. The dashboard is hosted as a static website on S3 and fetches live data via API Gateway backed by a lightweight Lambda function that reads from DynamoDB.

---

## ✅ Prerequisites

- [ ] Sections 1–4 merged and all AWS resources active
- [ ] AWS CLI v2 installed and configured
- [ ] IAM permissions for: `apigateway:*`, `lambda:*`, `s3:PutBucketWebsite`, `s3:PutBucketPolicy`
- [ ] Environment variables exported:
  ```bash
  export AWS_REGION=<your-region>
  export AWS_ACCOUNT_ID=<your-account-id>
  export PROJECT_NAME=carbon-optimizer-cloud
  export DYNAMODB_TABLE=${PROJECT_NAME}-metrics
  export S3_BUCKET=${PROJECT_NAME}-data
  export LAMBDA_ROLE_ARN=$(aws iam get-role \
      --role-name ${PROJECT_NAME}-lambda-role \
      --query 'Role.Arn' --output text)
  ```
- [ ] Repository on branch `feature/section-5-dashboard`

---

## 📁 Files You Will Create

```
carbon-optimizer/
├── dashboard/
│   ├── index.html              ← Full dashboard UI (HTML + CSS + JS)
│   └── dashboard-api/
│       └── index.py            ← API Lambda: reads DynamoDB, returns JSON
└── scripts/
    └── deploy-dashboard.sh     ← Deploys API + uploads dashboard to S3
```

---

## 🔨 Tasks

### Task 5.1 — Create the Dashboard API Lambda

**Commit message:** `feat(dashboard): add API Lambda to serve DynamoDB metrics`

Create `dashboard/dashboard-api/index.py`:

```python
import json
import boto3
import os
import logging
from datetime import datetime, timedelta
from decimal import Decimal

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
TABLE_NAME = os.environ['DYNAMODB_TABLE']
table = dynamodb.Table(TABLE_NAME)


class DecimalEncoder(json.JSONEncoder):
    """Handle Decimal types from DynamoDB."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def lambda_handler(event, context):
    """Serve dashboard data from DynamoDB."""
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Allow-Methods': 'GET,OPTIONS',
        'Content-Type': 'application/json'
    }

    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': headers, 'body': ''}

    path = event.get('path', '/')

    try:
        if path == '/metrics':
            return get_metrics(headers)
        elif path == '/summary':
            return get_summary(headers)
        elif path == '/recommendations':
            return get_recommendations(headers)
        else:
            return {
                'statusCode': 404,
                'headers': headers,
                'body': json.dumps({'error': 'Route not found'})
            }
    except Exception as e:
        logger.error(f"Dashboard API error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': str(e)})
        }


def get_metrics(headers):
    """Return last 30 days of carbon metrics from DynamoDB."""
    response = table.scan(Limit=50)
    items = response.get('Items', [])
    items.sort(key=lambda x: x.get('analysis_date', ''), reverse=True)
    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({'metrics': items}, cls=DecimalEncoder)
    }


def get_summary(headers):
    """Return aggregated summary stats."""
    response = table.scan()
    items = response.get('Items', [])

    total_cost = sum(float(i.get('monthly_cost', 0)) for i in items)
    total_carbon = sum(float(i.get('carbon_kg_co2', 0)) for i in items)
    services = list(set(i.get('service_name', '') for i in items))

    summary = {
        'total_monthly_cost_usd': round(total_cost, 2),
        'total_carbon_kg_co2': round(total_carbon, 2),
        'services_tracked': len(services),
        'last_updated': items[0].get('analysis_date', 'N/A') if items else 'No data yet'
    }
    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({'summary': summary}, cls=DecimalEncoder)
    }


def get_recommendations(headers):
    """Return optimization recommendations from latest analysis."""
    response = table.scan(
        FilterExpression='attribute_exists(recommendations)'
    )
    items = response.get('Items', [])
    all_recs = []
    for item in items:
        recs = item.get('recommendations', [])
        if isinstance(recs, list):
            all_recs.extend(recs)

    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({'recommendations': all_recs[:10]}, cls=DecimalEncoder)
    }
```

---

### Task 5.2 — Deploy the Dashboard API Lambda + API Gateway

**Commit message:** `feat(dashboard): deploy API Gateway and dashboard Lambda`

Create `scripts/deploy-dashboard.sh`:

```bash
#!/bin/bash
set -e

echo "=================================================="
echo "  Deploying Carbon Optimizer Dashboard"
echo "=================================================="

# --- Step 1: Package Dashboard API Lambda ---
echo "Packaging Dashboard API Lambda..."
cd dashboard/dashboard-api
zip -r /tmp/dashboard-api.zip index.py
cd ../..

# --- Step 2: Create Dashboard Lambda Function ---
echo "Creating Dashboard Lambda function..."
DASHBOARD_FUNCTION="${PROJECT_NAME}-dashboard-api"

aws lambda create-function \
    --function-name ${DASHBOARD_FUNCTION} \
    --runtime python3.11 \
    --handler index.lambda_handler \
    --role ${LAMBDA_ROLE_ARN} \
    --zip-file fileb:///tmp/dashboard-api.zip \
    --environment "Variables={DYNAMODB_TABLE=${DYNAMODB_TABLE}}" \
    --timeout 15 \
    --region ${AWS_REGION}

echo "  Waiting for Lambda to become active..."
aws lambda wait function-active \
    --function-name ${DASHBOARD_FUNCTION} \
    --region ${AWS_REGION}
echo "  ✅ Dashboard Lambda active"

# --- Step 3: Create API Gateway ---
echo "Creating API Gateway..."
API_ID=$(aws apigateway create-rest-api \
    --name "${PROJECT_NAME}-dashboard-api" \
    --description "Carbon Optimizer Dashboard API" \
    --region ${AWS_REGION} \
    --query 'id' --output text)

echo "  API Gateway ID: ${API_ID}"

ROOT_ID=$(aws apigateway get-resources \
    --rest-api-id ${API_ID} \
    --region ${AWS_REGION} \
    --query 'items[0].id' --output text)

LAMBDA_ARN=$(aws lambda get-function \
    --function-name ${DASHBOARD_FUNCTION} \
    --query 'Configuration.FunctionArn' --output text)

# Create {proxy+} resource for all routes
RESOURCE_ID=$(aws apigateway create-resource \
    --rest-api-id ${API_ID} \
    --parent-id ${ROOT_ID} \
    --path-part '{proxy+}' \
    --region ${AWS_REGION} \
    --query 'id' --output text)

# Create ANY method on {proxy+}
aws apigateway put-method \
    --rest-api-id ${API_ID} \
    --resource-id ${RESOURCE_ID} \
    --http-method ANY \
    --authorization-type NONE \
    --region ${AWS_REGION}

# Set Lambda integration
aws apigateway put-integration \
    --rest-api-id ${API_ID} \
    --resource-id ${RESOURCE_ID} \
    --http-method ANY \
    --type AWS_PROXY \
    --integration-http-method POST \
    --uri "arn:aws:apigateway:${AWS_REGION}:lambda:path/2015-03-31/functions/${LAMBDA_ARN}/invocations" \
    --region ${AWS_REGION}

# Deploy the API
aws apigateway create-deployment \
    --rest-api-id ${API_ID} \
    --stage-name prod \
    --region ${AWS_REGION}

# Allow API Gateway to invoke Lambda
aws lambda add-permission \
    --function-name ${DASHBOARD_FUNCTION} \
    --statement-id apigateway-invoke \
    --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:${AWS_REGION}:${AWS_ACCOUNT_ID}:${API_ID}/*/*" \
    --region ${AWS_REGION}

export API_ENDPOINT="https://${API_ID}.execute-api.${AWS_REGION}.amazonaws.com/prod"
echo "  ✅ API Gateway deployed: ${API_ENDPOINT}"

# --- Step 4: Enable S3 Static Website Hosting ---
echo "Enabling S3 static website hosting..."
aws s3api put-bucket-website \
    --bucket ${S3_BUCKET} \
    --website-configuration '{
        "IndexDocument": {"Suffix": "index.html"},
        "ErrorDocument": {"Key": "index.html"}
    }'

# Public read policy for website
cat > /tmp/website-bucket-policy.json << POLICY
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": "*",
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::${S3_BUCKET}/dashboard/*"
  }]
}
POLICY

aws s3api put-bucket-policy \
    --bucket ${S3_BUCKET} \
    --policy file:///tmp/website-bucket-policy.json

# Inject API endpoint into dashboard HTML
sed -i "s|API_ENDPOINT_PLACEHOLDER|${API_ENDPOINT}|g" dashboard/index.html

# Upload dashboard to S3
aws s3 cp dashboard/index.html s3://${S3_BUCKET}/dashboard/index.html \
    --content-type text/html

DASHBOARD_URL="http://${S3_BUCKET}.s3-website.${AWS_REGION}.amazonaws.com/dashboard/index.html"
echo ""
echo "=================================================="
echo "  ✅ Dashboard deployed successfully!"
echo "  🌐 URL: ${DASHBOARD_URL}"
echo "  🔌 API: ${API_ENDPOINT}"
echo "=================================================="
```

```bash
chmod +x scripts/deploy-dashboard.sh
```

---

### Task 5.3 — Build the Dashboard HTML

**Commit message:** `feat(dashboard): add real-time carbon footprint dashboard UI`

Create `dashboard/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🌱 Carbon Optimizer Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Segoe UI', sans-serif; background: #0f1117; color: #e0e0e0; }

  header {
    background: linear-gradient(135deg, #1a2a1a, #0d1f0d);
    border-bottom: 1px solid #2d4a2d;
    padding: 18px 32px;
    display: flex; align-items: center; justify-content: space-between;
  }
  header h1 { font-size: 1.4rem; color: #4caf50; font-weight: 600; }
  header span { font-size: 0.8rem; color: #888; }

  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: 16px; padding: 24px 32px 0; }

  .card {
    background: #1a1f2e; border: 1px solid #2a3a4a;
    border-radius: 12px; padding: 20px;
  }
  .card .label { font-size: 0.75rem; color: #888; text-transform: uppercase; letter-spacing: 1px; }
  .card .value { font-size: 2rem; font-weight: 700; color: #4caf50; margin: 8px 0 4px; }
  .card .sub   { font-size: 0.8rem; color: #aaa; }

  .charts { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 16px 32px; }
  .chart-card { background: #1a1f2e; border: 1px solid #2a3a4a; border-radius: 12px; padding: 20px; }
  .chart-card h3 { font-size: 0.9rem; color: #ccc; margin-bottom: 16px; }

  .recs { padding: 0 32px 32px; }
  .recs h2 { font-size: 1rem; color: #ccc; margin-bottom: 12px; }
  .rec-item {
    background: #1a1f2e; border: 1px solid #2a3a4a; border-radius: 8px;
    padding: 14px 18px; margin-bottom: 10px;
    display: flex; align-items: center; gap: 12px;
  }
  .rec-item .badge {
    background: #4caf5020; color: #4caf50; border-radius: 6px;
    padding: 3px 10px; font-size: 0.75rem; white-space: nowrap;
  }
  .rec-item .badge.high { background: #f4433620; color: #f44336; }
  .rec-item p { font-size: 0.85rem; color: #bbb; }

  .status { padding: 0 32px; margin-bottom: 16px; font-size: 0.8rem; color: #666; }
  .loading { text-align: center; padding: 48px; color: #555; }

  @media (max-width: 768px) {
    .charts { grid-template-columns: 1fr; }
    .grid { grid-template-columns: 1fr 1fr; }
  }
</style>
</head>
<body>

<header>
  <h1>🌱 Carbon Footprint Optimizer</h1>
  <span id="last-updated">Loading...</span>
</header>

<div class="grid" id="summary-cards">
  <div class="card"><div class="label">Monthly Cost</div><div class="value" id="v-cost">—</div><div class="sub">USD tracked</div></div>
  <div class="card"><div class="label">Carbon Emissions</div><div class="value" id="v-carbon">—</div><div class="sub">kg CO₂ equivalent</div></div>
  <div class="card"><div class="label">Services Tracked</div><div class="value" id="v-services">—</div><div class="sub">AWS services</div></div>
  <div class="card"><div class="label">System Status</div><div class="value" id="v-status" style="font-size:1.2rem">—</div><div class="sub">EventBridge + Lambda</div></div>
</div>

<div class="charts">
  <div class="chart-card">
    <h3>📊 Carbon Emissions by Service</h3>
    <canvas id="carbonChart" height="200"></canvas>
  </div>
  <div class="chart-card">
    <h3>💰 Cost Distribution</h3>
    <canvas id="costChart" height="200"></canvas>
  </div>
</div>

<div class="recs">
  <h2>💡 Optimization Recommendations</h2>
  <div id="recs-list"><div class="loading">Loading recommendations...</div></div>
</div>

<div class="status" id="status-bar">Fetching live data from DynamoDB...</div>

<script>
  const API = 'API_ENDPOINT_PLACEHOLDER';

  let carbonChart, costChart;

  async function fetchData(path) {
    const res = await fetch(API + path);
    return res.json();
  }

  async function loadSummary() {
    try {
      const data = await fetchData('/summary');
      const s = data.summary;
      document.getElementById('v-cost').textContent = s.total_monthly_cost_usd > 0
        ? '$' + s.total_monthly_cost_usd.toFixed(2) : '$0.00';
      document.getElementById('v-carbon').textContent = s.total_carbon_kg_co2 > 0
        ? s.total_carbon_kg_co2.toFixed(1) : '0.0';
      document.getElementById('v-services').textContent = s.services_tracked || '0';
      document.getElementById('v-status').textContent = '🟢 Active';
      document.getElementById('last-updated').textContent = 'Last updated: ' + s.last_updated;
    } catch(e) {
      document.getElementById('v-status').textContent = '🔴 Error';
    }
  }

  async function loadCharts() {
    try {
      const data = await fetchData('/metrics');
      const items = data.metrics || [];

      const labels = items.map(i => i.service_name || 'Unknown').slice(0, 8);
      const carbonVals = items.map(i => parseFloat(i.carbon_kg_co2 || 0)).slice(0, 8);
      const costVals = items.map(i => parseFloat(i.monthly_cost || 0)).slice(0, 8);

      const COLORS = ['#4caf50','#2196f3','#ff9800','#9c27b0','#00bcd4','#f44336','#8bc34a','#ff5722'];

      if (carbonChart) carbonChart.destroy();
      carbonChart = new Chart(document.getElementById('carbonChart'), {
        type: 'bar',
        data: {
          labels,
          datasets: [{ label: 'kg CO₂', data: carbonVals, backgroundColor: COLORS, borderRadius: 6 }]
        },
        options: {
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { color: '#888' }, grid: { color: '#2a3a4a' } },
            y: { ticks: { color: '#888' }, grid: { color: '#2a3a4a' } }
          }
        }
      });

      if (costChart) costChart.destroy();
      costChart = new Chart(document.getElementById('costChart'), {
        type: 'doughnut',
        data: {
          labels,
          datasets: [{ data: costVals, backgroundColor: COLORS, borderWidth: 0 }]
        },
        options: {
          plugins: { legend: { position: 'bottom', labels: { color: '#888', boxWidth: 12 } } }
        }
      });
    } catch(e) {
      console.error('Chart error:', e);
    }
  }

  async function loadRecommendations() {
    try {
      const data = await fetchData('/recommendations');
      const recs = data.recommendations || [];
      const container = document.getElementById('recs-list');

      if (recs.length === 0) {
        container.innerHTML = '<div class="rec-item"><p>No recommendations yet. Run Lambda analysis first.</p></div>';
        return;
      }

      container.innerHTML = recs.map(r => `
        <div class="rec-item">
          <span class="badge ${r.priority === 'HIGH' ? 'high' : ''}">${r.priority || 'MEDIUM'}</span>
          <p>${r.action || r.description || JSON.stringify(r)}</p>
        </div>
      `).join('');
    } catch(e) {
      document.getElementById('recs-list').innerHTML = '<div class="rec-item"><p>Could not load recommendations.</p></div>';
    }
  }

  async function refreshAll() {
    document.getElementById('status-bar').textContent = 'Refreshing data...';
    await Promise.all([loadSummary(), loadCharts(), loadRecommendations()]);
    document.getElementById('status-bar').textContent =
      '✅ Live data — refreshes every 60 seconds | API: ' + API;
  }

  refreshAll();
  setInterval(refreshAll, 60000);
</script>
</body>
</html>
```

---

### Task 5.4 — Deploy the Dashboard

**Commit message:** `ops(dashboard): deploy dashboard to S3 and configure API Gateway`

```bash
bash scripts/deploy-dashboard.sh
```

Paste the output — you should see your Dashboard URL at the end.

---

### Task 5.5 — Verify Dashboard is Live

```bash
# Get your dashboard URL
DASHBOARD_URL="http://${S3_BUCKET}.s3-website.${AWS_REGION}.amazonaws.com/dashboard/index.html"
echo "Dashboard URL: ${DASHBOARD_URL}"

# Test API endpoints directly
curl -s "${API_ENDPOINT}/summary" | python3 -m json.tool
curl -s "${API_ENDPOINT}/metrics" | python3 -m json.tool | head -30
```

Open `${DASHBOARD_URL}` in your browser. You should see:
- ✅ All 4 summary cards with real values (or $0.00 if Lambda hasn't run yet)
- ✅ Bar chart for carbon emissions
- ✅ Doughnut chart for cost distribution
- ✅ Recommendations panel

> 💡 **Tip:** If cards show $0.00, manually invoke the main Lambda first:
> ```bash
> aws lambda invoke --function-name ${PROJECT_NAME}-analyzer --payload '{}' /tmp/r.json
> ```
> Then refresh the dashboard.

---

## 📝 Commit Summary

| # | Commit Message | Files |
|---|----------------|-------|
| 1 | `feat(dashboard): add API Lambda to serve DynamoDB metrics` | `dashboard/dashboard-api/index.py` |
| 2 | `feat(dashboard): deploy API Gateway and dashboard Lambda` | `scripts/deploy-dashboard.sh` |
| 3 | `feat(dashboard): add real-time carbon footprint dashboard UI` | `dashboard/index.html` |
| 4 | `ops(dashboard): deploy dashboard to S3 and configure API Gateway` | deployment output |

---

## 🚀 Pull Request Instructions

1. Push your branch: `git push origin feature/section-5-dashboard`
2. Open PR to `main` titled: **"Section 5: Real-Time Carbon Footprint Dashboard"**
3. Add label: `dashboard`
4. **Paste the Dashboard URL and a screenshot in the PR description**
5. Paste output of `curl -s "${API_ENDPOINT}/summary"`
