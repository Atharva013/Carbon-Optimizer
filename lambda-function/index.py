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
ce_client  = boto3.client('ce')
dynamodb   = boto3.resource('dynamodb')
s3_client  = boto3.client('s3')
sns_client = boto3.client('sns')
ssm_client = boto3.client('ssm')

# Environment variables
TABLE_NAME    = os.environ['DYNAMODB_TABLE']
S3_BUCKET     = os.environ['S3_BUCKET']
SNS_TOPIC_ARN = os.environ['SNS_TOPIC_ARN']

table = dynamodb.Table(TABLE_NAME)


def lambda_handler(event, context):
    """Main handler for carbon footprint optimization analysis."""
    try:
        logger.info("Starting carbon footprint optimization analysis")

        end_date   = datetime.now().date()
        start_date = end_date - timedelta(days=30)

        cost_data       = get_cost_and_usage_data(start_date, end_date)
        carbon_analysis = analyze_carbon_footprint(cost_data)
        recommendations = generate_recommendations(carbon_analysis)
        store_metrics(carbon_analysis, recommendations)

        if recommendations['high_impact_actions']:
            send_optimization_notifications(recommendations)

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Carbon footprint analysis completed successfully',
                'total_cost_usd':       round(carbon_analysis['total_cost'], 4),
                'total_carbon_kg':      round(carbon_analysis['estimated_carbon_kg'], 4),
                'services_analyzed':    len(carbon_analysis['services']),
                'recommendations_count': len(recommendations['all_actions']),
                'high_impact_count':    len(recommendations['high_impact_actions'])
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
                'End':   end_date.strftime('%Y-%m-%d')
            },
            Granularity='DAILY',                          # DAILY for 30 granular data points
            Metrics=['BlendedCost', 'UsageQuantity'],
            GroupBy=[
                {'Type': 'DIMENSION', 'Key': 'SERVICE'},
                {'Type': 'DIMENSION', 'Key': 'REGION'}
            ]
        )
        logger.info(f"Retrieved cost data for {len(response['ResultsByTime'])} time periods")
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
        'Amazon Simple Storage Service':          0.000164,
        'Amazon Relational Database Service':     0.000688,
        'AWS Lambda':                             0.000025,
        'Amazon CloudFront':                      0.00004,
        'Amazon DynamoDB':                        0.000045,
        'Amazon Elastic Load Balancing':          0.000312,
        'Amazon Virtual Private Cloud':           0.000089,
        'AWS Key Management Service':             0.000020,
        'Amazon Simple Notification Service':     0.000018,
        'Amazon API Gateway':                     0.000035,
        'Amazon CloudWatch':                      0.000022
    }

    # Regional carbon intensity multipliers (lower = cleaner grid)
    regional_factors = {
        'us-east-1':      0.85,
        'us-east-2':      0.80,
        'us-west-1':      0.55,
        'us-west-2':      0.42,
        'eu-west-1':      0.65,
        'eu-west-2':      0.60,
        'eu-central-1':   0.70,
        'eu-north-1':     0.11,
        'ap-south-1':     0.95,   # India — coal-heavy grid (your region)
        'ap-southeast-1': 1.00,
        'ap-southeast-2': 1.20,
        'ap-northeast-1': 0.75,
        'ca-central-1':   0.23,
        'sa-east-1':      0.45,
        'global':         0.85
    }

    for time_period in cost_data:
        for group in time_period.get('Groups', []):
            service = group['Keys'][0] if len(group['Keys']) > 0 else 'Unknown'
            region  = group['Keys'][1] if len(group['Keys']) > 1 else 'global'

            cost = float(group['Metrics']['BlendedCost']['Amount'])

            # Skip zero-cost entries
            if cost <= 0:
                continue

            analysis['total_cost'] += cost

            service_factor   = carbon_factors.get(service, 0.0003)
            regional_factor  = regional_factors.get(region, 1.0)
            estimated_carbon = cost * service_factor * regional_factor
            analysis['estimated_carbon_kg'] += estimated_carbon

            # Accumulate per-service stats
            if service not in analysis['services']:
                analysis['services'][service] = {
                    'cost': 0.0,
                    'carbon_kg': 0.0,
                    'optimization_score': 0.0,
                    'primary_region': region
                }

            analysis['services'][service]['cost']      += cost
            analysis['services'][service]['carbon_kg'] += estimated_carbon

            # optimization_score = carbon per dollar × 1000 (higher = worse efficiency)
            svc = analysis['services'][service]
            if svc['cost'] > 0:
                svc['optimization_score'] = (svc['carbon_kg'] / svc['cost']) * 1000

            # Accumulate per-region stats
            if region not in analysis['regions']:
                analysis['regions'][region] = {'cost': 0.0, 'carbon_kg': 0.0}
            analysis['regions'][region]['cost']      += cost
            analysis['regions'][region]['carbon_kg'] += estimated_carbon

    # Overall optimization potential (%)
    if analysis['total_cost'] > 0:
        analysis['optimization_potential'] = min(
            round((analysis['estimated_carbon_kg'] / analysis['total_cost']) * 100, 2),
            100
        )

    logger.info(
        f"Analysis complete — cost: ${analysis['total_cost']:.4f}, "
        f"carbon: {analysis['estimated_carbon_kg']:.4f} kg CO2e, "
        f"services: {len(analysis['services'])}"
    )
    return analysis


def generate_recommendations(analysis):
    """Generate carbon footprint optimization recommendations."""
    recommendations = {
        'all_actions': [],
        'high_impact_actions': [],
        'estimated_savings': {'cost': 0.0, 'carbon_kg': 0.0}
    }

    for service, metrics in analysis['services'].items():
        if metrics['cost'] > 1 and metrics['optimization_score'] > 0.1:
            rec = {
                'service':                    service,
                'priority':                   'HIGH' if metrics['cost'] > 50 else 'MEDIUM',
                'action':                     determine_optimization_action(service),
                'current_cost':               round(metrics['cost'], 4),
                'current_carbon_kg':          round(metrics['carbon_kg'], 6),
                'estimated_cost_savings':     round(metrics['cost'] * 0.15, 4),
                'estimated_carbon_reduction': round(metrics['carbon_kg'] * 0.25, 6)
            }
            recommendations['all_actions'].append(rec)

            if metrics['cost'] > 50:
                recommendations['high_impact_actions'].append(rec)
                recommendations['estimated_savings']['cost']      += rec['estimated_cost_savings']
                recommendations['estimated_savings']['carbon_kg'] += rec['estimated_carbon_reduction']

    logger.info(
        f"Generated {len(recommendations['all_actions'])} recommendations, "
        f"{len(recommendations['high_impact_actions'])} high-impact"
    )
    return recommendations


def determine_optimization_action(service):
    """Return a specific optimization action string for a given service."""
    action_map = {
        'Amazon Elastic Compute Cloud - Compute':
            'Rightsize instances or migrate to Graviton processors for 20% energy efficiency improvement',
        'Amazon Simple Storage Service':
            'Enable Intelligent Tiering and lifecycle policies to reduce storage carbon footprint',
        'Amazon Relational Database Service':
            'Evaluate Aurora Serverless v2 or rightsize DB instances for better resource utilization',
        'AWS Lambda':
            'Tune memory allocation and use ARM (Graviton2) architecture for improved efficiency',
        'Amazon CloudFront':
            'Review caching TTLs and enable Gzip/Brotli compression to reduce data transfer emissions',
        'Amazon DynamoDB':
            'Switch to on-demand billing for variable workloads to eliminate over-provisioned capacity',
        'Amazon Elastic Load Balancing':
            'Consolidate load balancers and enable connection multiplexing to reduce idle resource usage',
        'Amazon Virtual Private Cloud':
            'Audit NAT Gateway usage; use VPC endpoints to eliminate unnecessary data-transfer emissions',
        'Amazon API Gateway':
            'Enable caching on API stages to reduce Lambda invocations and downstream compute carbon',
        'Amazon CloudWatch':
            'Review log retention periods and metric filters to reduce unnecessary data storage'
    }
    return action_map.get(
        service,
        'Review resource utilization patterns and evaluate sustainable right-sizing alternatives'
    )


def store_metrics(analysis, recommendations):
    """
    Store analysis results in DynamoDB.

    Table schema (confirmed from describe-table):
      PK  (HASH):  MetricType     — String
      SK  (RANGE): Timestamp      — String
      GSI: ServiceCarbonIndex
           PK: ServiceName        — String
           SK: CarbonIntensity    — Number   ← must be Decimal/Number type

    Row types:
      MetricType = 'OVERALL_ANALYSIS'  → summary row
      MetricType = 'SERVICE#<name>'    → one row per service
    """
    timestamp     = datetime.now().isoformat()   # SK value
    analysis_date = datetime.now().strftime('%Y-%m-%d')

    # Build recommendation lookup: service → {action, priority}
    rec_lookup = {
        r['service']: {'action': r['action'], 'priority': r['priority']}
        for r in recommendations['all_actions']
    }

    # ── Per-service rows ──────────────────────────────────────────────────────
    for service, metrics in analysis['services'].items():
        rec_info = rec_lookup.get(service, {})

        item = {
            # Keys — must match table + GSI exactly
            'MetricType':      f'SERVICE#{service}',           # PK ✅
            'Timestamp':       timestamp,                       # SK ✅
            'ServiceName':     service,                         # GSI PK ✅
            'CarbonIntensity': Decimal(str(round(metrics['optimization_score'], 6))),  # GSI SK ✅ (Number)

            # Extra attributes for Section 5 Dashboard
            'AnalysisDate':    analysis_date,
            'Cost':            Decimal(str(round(metrics['cost'], 4))),
            'CarbonKg':        Decimal(str(round(metrics['carbon_kg'], 6))),
            'PrimaryRegion':   metrics.get('primary_region', 'global'),
            'Recommendations': [rec_info['action']] if rec_info else []
        }
        table.put_item(Item=item)
        logger.info(f"Stored metrics for service: {service}")

    # ── Summary row ───────────────────────────────────────────────────────────
    table.put_item(Item={
        'MetricType':  'OVERALL_ANALYSIS',                      # PK ✅
        'Timestamp':   timestamp,                               # SK ✅
        'ServiceName': 'SUMMARY',                               # GSI PK (queryable)
        'CarbonIntensity': Decimal(str(round(analysis['optimization_potential'], 6))),  # GSI SK ✅

        'AnalysisDate':           analysis_date,
        'TotalCost':              Decimal(str(round(analysis['total_cost'], 4))),
        'EstimatedCarbonKg':      Decimal(str(round(analysis['estimated_carbon_kg'], 4))),
        'ServiceCount':           len(analysis['services']),
        'OptimizationPotential':  Decimal(str(analysis['optimization_potential'])),
        'HighImpactCount':        len(recommendations['high_impact_actions']),
        'EstimatedCostSavings':   Decimal(
            str(round(recommendations['estimated_savings']['cost'], 4))
        ),
        'EstimatedCarbonSavings': Decimal(
            str(round(recommendations['estimated_savings']['carbon_kg'], 6))
        ),
        'TopRecommendations':     [r['action'] for r in recommendations['high_impact_actions']]
    })
    logger.info("Stored OVERALL_ANALYSIS summary row in DynamoDB")


def send_optimization_notifications(recommendations):
    """Send SNS notification about high-impact optimization opportunities."""
    savings = recommendations['estimated_savings']
    lines = [
        "╔══════════════════════════════════════════╗",
        "   Carbon Footprint Optimization Report     ",
        "╚══════════════════════════════════════════╝",
        "",
        f"High-Impact Opportunities: {len(recommendations['high_impact_actions'])}",
        "",
        "Estimated Monthly Savings:",
        f"  Cost:   ${savings['cost']:.4f} USD",
        f"  Carbon: {savings['carbon_kg']:.6f} kg CO2e",
        "",
        "Top Recommendations:"
    ]

    for i, rec in enumerate(recommendations['high_impact_actions'][:3], 1):
        lines += [
            "",
            f"{i}. [{rec['priority']}] {rec['service']}",
            f"   Cost:   ${rec['current_cost']:.4f}",
            f"   Carbon: {rec['current_carbon_kg']:.6f} kg CO2e",
            f"   Action: {rec['action']}"
        ]

    message = "\n".join(lines)

    try:
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject='Carbon Footprint Optimization Report',
            Message=message
        )
        logger.info("SNS notification sent successfully")
    except Exception as e:
        # Don't crash the whole function if SNS fails
        logger.error(f"Error sending SNS notification: {str(e)}")