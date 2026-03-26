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