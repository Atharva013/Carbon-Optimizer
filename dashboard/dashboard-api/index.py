import json
import boto3
import os
import logging
from decimal import Decimal
from boto3.dynamodb.conditions import Key, Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
TABLE_NAME = os.environ['DYNAMODB_TABLE']
table = dynamodb.Table(TABLE_NAME)


class DecimalEncoder(json.JSONEncoder):
    """Handle Decimal types returned from DynamoDB."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def cors_headers():
    return {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization',
        'Access-Control-Allow-Methods': 'GET,OPTIONS',
        'Content-Type': 'application/json'
    }


def ok(body):
    return {
        'statusCode': 200,
        'headers': cors_headers(),
        'body': json.dumps(body, cls=DecimalEncoder)
    }


def err(msg, code=500):
    return {
        'statusCode': code,
        'headers': cors_headers(),
        'body': json.dumps({'error': msg})
    }


def lambda_handler(event, context):
    """Route API requests to the correct handler."""
    headers = cors_headers()

    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': headers, 'body': ''}

    path = event.get('path', '/')
    logger.info(f"Dashboard API request: {path}")

    try:
        if path == '/summary' or path.endswith('/summary'):
            return get_summary()
        elif path == '/metrics' or path.endswith('/metrics'):
            return get_metrics()
        elif path == '/recommendations' or path.endswith('/recommendations'):
            return get_recommendations()
        elif path == '/services' or path.endswith('/services'):
            return get_services()
        elif path == '/health' or path.endswith('/health'):
            return ok({'status': 'healthy', 'table': TABLE_NAME})
        else:
            return err(f'Route not found: {path}', 404)
    except Exception as e:
        logger.error(f"Dashboard API error on {path}: {str(e)}")
        return err(str(e))


def get_summary():
    """
    Return aggregated summary from OVERALL_ANALYSIS rows.
    PK = 'OVERALL_ANALYSIS', SK = Timestamp (ISO string).
    """
    response = table.query(
        KeyConditionExpression=Key('MetricType').eq('OVERALL_ANALYSIS'),
        ScanIndexForward=False,   # newest first
        Limit=1
    )
    items = response.get('Items', [])

    if not items:
        # Fallback: scan for summary if no OVERALL_ANALYSIS rows yet
        scan = table.scan(
            FilterExpression=Attr('MetricType').eq('OVERALL_ANALYSIS'),
            Limit=5
        )
        items = scan.get('Items', [])

    if items:
        latest = items[0]
        summary = {
            'total_monthly_cost_usd': float(latest.get('TotalCost', 0)),
            'total_carbon_kg_co2':    float(latest.get('EstimatedCarbonKg', 0)),
            'services_tracked':       int(latest.get('ServiceCount', 0)),
            'optimization_potential': float(latest.get('OptimizationPotential', 0)),
            'high_impact_count':      int(latest.get('HighImpactCount', 0)),
            'estimated_cost_savings': float(latest.get('EstimatedCostSavings', 0)),
            'estimated_carbon_savings': float(latest.get('EstimatedCarbonSavings', 0)),
            'last_updated':           latest.get('AnalysisDate', latest.get('Timestamp', 'N/A')),
            'last_timestamp':         latest.get('Timestamp', 'N/A'),
            'top_recommendations':    latest.get('TopRecommendations', [])
        }
    else:
        summary = {
            'total_monthly_cost_usd': 0,
            'total_carbon_kg_co2': 0,
            'services_tracked': 0,
            'optimization_potential': 0,
            'high_impact_count': 0,
            'estimated_cost_savings': 0,
            'estimated_carbon_savings': 0,
            'last_updated': 'No data yet',
            'last_timestamp': 'N/A',
            'top_recommendations': []
        }

    return ok({'summary': summary})


def get_metrics():
    """
    Return per-service metrics. Uses GSI ServiceCarbonIndex
    or falls back to a filtered scan.
    PK pattern for service rows: 'SERVICE#<name>'
    """
    try:
        # Scan for all SERVICE# rows
        response = table.scan(
            FilterExpression=Attr('MetricType').begins_with('SERVICE#'),
            Limit=100
        )
        items = response.get('Items', [])

        # Normalize field names to what the dashboard JS expects
        normalized = []
        for item in items:
            svc_name = item.get('ServiceName', item.get('MetricType', '').replace('SERVICE#', ''))
            normalized.append({
                'service_name':       svc_name,
                'monthly_cost':       float(item.get('Cost', 0)),
                'carbon_kg_co2':      float(item.get('CarbonKg', 0)),
                'optimization_score': float(item.get('CarbonIntensity', 0)),
                'primary_region':     item.get('PrimaryRegion', 'global'),
                'analysis_date':      item.get('AnalysisDate', item.get('Timestamp', '')[:10]),
                'recommendations':    item.get('Recommendations', [])
            })

        # Sort by carbon descending
        normalized.sort(key=lambda x: x['carbon_kg_co2'], reverse=True)

        return ok({'metrics': normalized, 'count': len(normalized)})

    except Exception as e:
        logger.error(f"get_metrics error: {e}")
        return err(str(e))


def get_recommendations():
    """
    Return deduplicated recommendations from service rows and summary row.
    """
    try:
        # Get from OVERALL_ANALYSIS top recommendations
        summary_resp = table.query(
            KeyConditionExpression=Key('MetricType').eq('OVERALL_ANALYSIS'),
            ScanIndexForward=False,
            Limit=1
        )
        summary_items = summary_resp.get('Items', [])
        top_recs = []
        if summary_items:
            top_recs = summary_items[0].get('TopRecommendations', [])

        # Get per-service recommendations
        service_resp = table.scan(
            FilterExpression=Attr('MetricType').begins_with('SERVICE#') & Attr('Recommendations').exists(),
            Limit=100
        )

        all_recs = []
        seen = set()

        for item in service_resp.get('Items', []):
            recs = item.get('Recommendations', [])
            svc  = item.get('ServiceName', '')
            cost = float(item.get('Cost', 0))

            for action in recs:
                if action and action not in seen:
                    seen.add(action)
                    all_recs.append({
                        'service':  svc,
                        'action':   action,
                        'priority': 'HIGH' if cost > 50 else 'MEDIUM',
                        'cost':     cost,
                        'carbon':   float(item.get('CarbonKg', 0))
                    })

        # Sort HIGH first, then by cost desc
        all_recs.sort(key=lambda x: (0 if x['priority'] == 'HIGH' else 1, -x['cost']))

        return ok({
            'recommendations': all_recs[:10],
            'top_actions': top_recs[:5],
            'count': len(all_recs)
        })

    except Exception as e:
        logger.error(f"get_recommendations error: {e}")
        return err(str(e))


def get_services():
    """
    Return list of unique services with their latest metrics.
    Uses GSI ServiceCarbonIndex for efficient lookup.
    """
    try:
        response = table.scan(
            FilterExpression=Attr('MetricType').begins_with('SERVICE#'),
            ProjectionExpression='ServiceName, Cost, CarbonKg, CarbonIntensity, PrimaryRegion, AnalysisDate',
            Limit=50
        )
        items = response.get('Items', [])

        # Deduplicate by service name (keep highest cost entry)
        services = {}
        for item in items:
            name = item.get('ServiceName', '')
            if not name:
                continue
            existing = services.get(name)
            if not existing or float(item.get('Cost', 0)) > float(existing.get('Cost', 0)):
                services[name] = item

        result = [
            {
                'name':    v.get('ServiceName'),
                'cost':    float(v.get('Cost', 0)),
                'carbon':  float(v.get('CarbonKg', 0)),
                'score':   float(v.get('CarbonIntensity', 0)),
                'region':  v.get('PrimaryRegion', 'global'),
                'date':    v.get('AnalysisDate', '')
            }
            for v in services.values()
        ]
        result.sort(key=lambda x: x['carbon'], reverse=True)

        return ok({'services': result, 'count': len(result)})

    except Exception as e:
        logger.error(f"get_services error: {e}")
        return err(str(e))