import json
import boto3
import os
import logging
from decimal import Decimal
from datetime import datetime, timedelta
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb  = boto3.resource('dynamodb')
ce_client = boto3.client('ce')
TABLE_NAME = os.environ['DYNAMODB_TABLE']
table = dynamodb.Table(TABLE_NAME)

# Carbon intensity factors (kg CO2e per USD) — mirrors analyzer Lambda
CARBON_FACTORS = {
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
    'Amazon CloudWatch':                      0.000022,
}

REGIONAL_FACTORS = {
    'us-east-1': 0.85, 'us-east-2': 0.80, 'us-west-1': 0.55, 'us-west-2': 0.42,
    'eu-west-1': 0.65, 'eu-west-2': 0.60, 'eu-central-1': 0.70, 'eu-north-1': 0.11,
    'ap-south-1': 0.95, 'ap-southeast-1': 1.00, 'ap-southeast-2': 1.20,
    'ap-northeast-1': 0.75, 'ca-central-1': 0.23, 'sa-east-1': 0.45, 'global': 0.85,
}

# Simple in-memory cache for warm Lambda reuse (5 min TTL)
_ce_cache = {'data': None, 'ts': 0}


class DecimalEncoder(json.JSONEncoder):
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
    return {'statusCode': 200, 'headers': cors_headers(),
            'body': json.dumps(body, cls=DecimalEncoder)}


def err(msg, code=500):
    return {'statusCode': code, 'headers': cors_headers(),
            'body': json.dumps({'error': msg})}


def _get_ce_service_data(days=30):
    """Fetch per-service cost data from Cost Explorer with 5-min cache."""
    global _ce_cache
    now = datetime.now().timestamp()
    if _ce_cache['data'] and (now - _ce_cache['ts']) < 300:
        return _ce_cache['data']

    end   = datetime.now().date()
    start = end - timedelta(days=days)

    response = ce_client.get_cost_and_usage(
        TimePeriod={'Start': start.strftime('%Y-%m-%d'),
                    'End':   end.strftime('%Y-%m-%d')},
        Granularity='MONTHLY',
        Metrics=['BlendedCost', 'UsageQuantity'],
        GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'},
                 {'Type': 'DIMENSION', 'Key': 'REGION'}]
    )

    services = {}
    for period in response['ResultsByTime']:
        for group in period.get('Groups', []):
            svc    = group['Keys'][0]
            region = group['Keys'][1] if len(group['Keys']) > 1 else 'global'
            cost   = float(group['Metrics']['BlendedCost']['Amount'])
            usage  = float(group['Metrics']['UsageQuantity']['Amount'])

            if svc not in services:
                services[svc] = {'name': svc, 'cost': 0.0, 'carbon_kg': 0.0,
                                 'usage': 0.0, 'region': region, 'status': 'IDLE'}
            services[svc]['cost']  += cost
            services[svc]['usage'] += usage
            if cost > 0 or usage > 0:
                services[svc]['status'] = 'ACTIVE'

            cf = CARBON_FACTORS.get(svc, 0.0003)
            rf = REGIONAL_FACTORS.get(region, 1.0)
            services[svc]['carbon_kg'] += abs(cost) * cf * rf

    _ce_cache = {'data': services, 'ts': now}
    return services


def lambda_handler(event, context):
    headers = cors_headers()
    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': headers, 'body': ''}

    path = event.get('path', '/')
    logger.info(f"Dashboard API: {event.get('httpMethod','GET')} {path}")

    try:
        if path.endswith('/summary'):
            return get_summary()
        elif path.endswith('/metrics'):
            return get_metrics()
        elif path.endswith('/recommendations'):
            return get_recommendations()
        elif path.endswith('/services'):
            return get_services()
        elif path.endswith('/live-services'):
            return get_live_services()
        elif path.endswith('/health'):
            return ok({'status': 'healthy', 'table': TABLE_NAME,
                       'ts': datetime.now().isoformat()})
        else:
            return err(f'Route not found: {path}', 404)
    except Exception as e:
        logger.error(f"API error on {path}: {str(e)}")
        return err(str(e))


def get_summary():
    """Summary stats — Cost Explorer primary, DynamoDB for optimization metadata."""
    try:
        ce = _get_ce_service_data(30)
        total_cost   = sum(abs(s['cost'])      for s in ce.values())
        total_carbon = sum(s['carbon_kg'] for s in ce.values())
        active       = sum(1 for s in ce.values() if s['status'] == 'ACTIVE')

        opt_potential = est_cost_sav = est_carbon_sav = high_impact = 0
        last_analysis = 'Live'
        try:
            resp = table.query(
                KeyConditionExpression=Key('MetricType').eq('OVERALL_ANALYSIS'),
                ScanIndexForward=False, Limit=1)
            if resp.get('Items'):
                r = resp['Items'][0]
                opt_potential   = float(r.get('OptimizationPotential', 0))
                high_impact     = int(r.get('HighImpactCount', 0))
                est_cost_sav    = float(r.get('EstimatedCostSavings', 0))
                est_carbon_sav  = float(r.get('EstimatedCarbonSavings', 0))
                last_analysis   = r.get('AnalysisDate', 'Live')
        except Exception as e:
            logger.warning(f"DynamoDB query fallback: {e}")

        if opt_potential == 0 and total_cost > 0:
            opt_potential = min(round((total_carbon / total_cost) * 100, 2), 100)
        if est_cost_sav == 0 and total_cost > 0:
            est_cost_sav = round(total_cost * 0.15, 8)
        if est_carbon_sav == 0 and total_carbon > 0:
            est_carbon_sav = round(total_carbon * 0.25, 8)

        return ok({'summary': {
            'total_monthly_cost_usd':  total_cost,
            'total_carbon_kg_co2':     total_carbon,
            'services_tracked':        active,
            'optimization_potential':  round(opt_potential, 2),
            'high_impact_count':       high_impact,
            'estimated_cost_savings':  est_cost_sav,
            'estimated_carbon_savings': est_carbon_sav,
            'last_updated':            last_analysis,
            'last_timestamp':          datetime.now().isoformat(),
            'top_recommendations':     [],
            'data_source':             'cost-explorer'
        }})
    except Exception as e:
        logger.error(f"get_summary error: {e}")
        return err(str(e))


def get_metrics():
    """Per-service carbon metrics from Cost Explorer."""
    try:
        ce = _get_ce_service_data(30)
        metrics = []
        for svc, d in ce.items():
            if d['cost'] == 0 and d['usage'] == 0:
                continue
            score = (d['carbon_kg'] / d['cost'] * 1000) if d['cost'] > 0 else 0
            metrics.append({
                'service_name':       svc,
                'monthly_cost':       d['cost'],
                'carbon_kg_co2':      d['carbon_kg'],
                'optimization_score': round(score, 4),
                'primary_region':     d['region'],
                'analysis_date':      datetime.now().isoformat(),
                'recommendations':    []
            })
        metrics.sort(key=lambda x: x['carbon_kg_co2'], reverse=True)
        return ok({'metrics': metrics, 'count': len(metrics)})
    except Exception as e:
        logger.error(f"get_metrics error: {e}")
        return err(str(e))


def get_recommendations():
    """Generate recommendations from Cost Explorer data."""
    try:
        ce = _get_ce_service_data(30)
        actions = {
            'Amazon Elastic Compute Cloud - Compute':
                'Rightsize instances or migrate to Graviton for 20% energy savings',
            'Amazon Simple Storage Service':
                'Enable Intelligent Tiering to reduce storage carbon footprint',
            'Amazon Relational Database Service':
                'Evaluate Aurora Serverless v2 for better resource utilization',
            'AWS Lambda':
                'Use ARM (Graviton2) architecture for improved efficiency',
            'Amazon DynamoDB':
                'Switch to on-demand billing to eliminate over-provisioned capacity',
            'Amazon Elastic Load Balancing':
                'Consolidate load balancers to reduce idle resource usage',
            'Amazon Virtual Private Cloud':
                'Use VPC endpoints to reduce data-transfer emissions',
            'EC2 - Other':
                'Review EBS volumes and Elastic IPs for unused resources',
        }
        recs = []
        for svc, d in ce.items():
            if d['cost'] > 0 or d['usage'] > 0:
                recs.append({
                    'service':  svc,
                    'action':   actions.get(svc, 'Review utilization and evaluate sustainable right-sizing'),
                    'priority': 'HIGH' if d['cost'] > 0.001 else 'MEDIUM',
                    'cost':     d['cost'],
                    'carbon':   d['carbon_kg'],
                })
        recs.sort(key=lambda x: x['cost'], reverse=True)
        return ok({'recommendations': recs[:10], 'count': len(recs)})
    except Exception as e:
        logger.error(f"get_recommendations error: {e}")
        return err(str(e))


def get_services():
    """All tracked services from Cost Explorer."""
    try:
        ce = _get_ce_service_data(30)
        services = []
        for svc, d in ce.items():
            if d['cost'] == 0 and d['usage'] == 0:
                continue
            score = (d['carbon_kg'] / d['cost'] * 1000) if d['cost'] > 0 else 0
            services.append({
                'name':   svc,
                'cost':   d['cost'],
                'carbon': d['carbon_kg'],
                'region': d['region'],
                'date':   datetime.now().strftime('%Y-%m-%d'),
                'score':  round(score, 4),
                'status': d['status']
            })
        services.sort(key=lambda x: x['carbon'], reverse=True)
        return ok({'services': services, 'count': len(services)})
    except Exception as e:
        logger.error(f"get_services error: {e}")
        return err(str(e))


def get_live_services():
    """Live services from Cost Explorer — last 7 days."""
    try:
        end   = datetime.now().date()
        start = end - timedelta(days=7)

        response = ce_client.get_cost_and_usage(
            TimePeriod={'Start': start.strftime('%Y-%m-%d'),
                        'End':   end.strftime('%Y-%m-%d')},
            Granularity='MONTHLY',
            Metrics=['BlendedCost', 'UsageQuantity'],
            GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'},
                     {'Type': 'DIMENSION', 'Key': 'REGION'}]
        )

        services = {}
        for period in response['ResultsByTime']:
            for group in period.get('Groups', []):
                svc    = group['Keys'][0]
                region = group['Keys'][1] if len(group['Keys']) > 1 else 'global'
                cost   = float(group['Metrics']['BlendedCost']['Amount'])
                usage  = float(group['Metrics']['UsageQuantity']['Amount'])

                if svc not in services:
                    services[svc] = {'name': svc, 'cost_7d': 0.0,
                                     'usage': 0.0, 'region': region, 'status': 'IDLE'}
                services[svc]['cost_7d'] += cost
                services[svc]['usage']   += usage
                if cost > 0 or usage > 0:
                    services[svc]['status'] = 'ACTIVE'

        result = sorted(services.values(), key=lambda x: x['cost_7d'], reverse=True)
        for s in result:
            s['cost_7d'] = round(s['cost_7d'], 8)
            s['usage']   = round(s['usage'], 4)

        return ok({
            'live_services': result,
            'count': len(result),
            'period_start': str(start),
            'period_end':   str(end),
            'active_count': sum(1 for s in result if s['status'] == 'ACTIVE')
        })
    except Exception as e:
        logger.error(f"get_live_services error: {e}")
        return err(str(e))