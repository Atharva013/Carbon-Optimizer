import json
import logging
import os
from datetime import datetime, timedelta
from decimal import Decimal

import boto3


logger = logging.getLogger()
logger.setLevel(logging.INFO)

ce_client = boto3.client("ce")
dynamodb = boto3.resource("dynamodb")
sns_client = boto3.client("sns")
ssm_client = boto3.client("ssm")

TABLE_NAME = os.environ["DYNAMODB_TABLE"]
S3_BUCKET = os.environ["S3_BUCKET"]
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]
PROJECT_NAME = os.environ.get("PROJECT_NAME") or (
    TABLE_NAME[:-8] if TABLE_NAME.endswith("-metrics") else TABLE_NAME
)

table = dynamodb.Table(TABLE_NAME)

COST_TYPES = ("UnblendedCost", "BlendedCost", "NetUnblendedCost")
COST_TYPE_LABELS = {
    "UnblendedCost": "Unblended",
    "BlendedCost": "Blended",
    "NetUnblendedCost": "Net Unblended",
}

CARBON_FACTORS = {
    "Amazon Elastic Compute Cloud - Compute": 0.000533,
    "Amazon Simple Storage Service": 0.000164,
    "Amazon Relational Database Service": 0.000688,
    "AWS Lambda": 0.000025,
    "Amazon CloudFront": 0.00004,
    "Amazon DynamoDB": 0.000045,
    "Amazon Elastic Load Balancing": 0.000312,
    "Amazon Virtual Private Cloud": 0.000089,
    "AWS Key Management Service": 0.000020,
    "Amazon Simple Notification Service": 0.000018,
    "Amazon API Gateway": 0.000035,
    "Amazon CloudWatch": 0.000022,
}

REGIONAL_FACTORS = {
    "us-east-1": 0.85,
    "us-east-2": 0.80,
    "us-west-1": 0.55,
    "us-west-2": 0.42,
    "eu-west-1": 0.65,
    "eu-west-2": 0.60,
    "eu-central-1": 0.70,
    "eu-north-1": 0.11,
    "ap-south-1": 0.95,
    "ap-southeast-1": 1.00,
    "ap-southeast-2": 1.20,
    "ap-northeast-1": 0.75,
    "ca-central-1": 0.23,
    "sa-east-1": 0.45,
    "global": 0.85,
}

DEFAULT_CONFIG = {
    "carbon_thresholds": {
        "high_impact": 50,
        "optimization_threshold": 0.1,
    },
    "regional_preferences": {
        "preferred_regions": ["us-west-2", "eu-north-1", "ca-central-1"],
        "current_region": os.environ.get("AWS_REGION", "ap-south-1"),
        "avoid_regions": [],
    },
    "optimization_rules": {
        "graviton_migration": True,
        "intelligent_tiering": True,
        "serverless_first": True,
        "right_sizing": True,
    },
    "notification_settings": {
        "email_threshold": 10,
        "weekly_summary": True,
    },
}


def lambda_handler(event, context):
    """Main handler for carbon footprint optimization analysis."""
    try:
        logger.info("Starting carbon footprint optimization analysis")

        config = get_sustainability_config()
        end_date = datetime.now().date()
        start_30d = end_date - timedelta(days=30)
        start_7d = end_date - timedelta(days=7)

        analyses = {}
        recommendations_by_type = {}
        record_totals_by_type = {}
        live_services_by_type = {}

        for cost_type in COST_TYPES:
            cost_data = get_cost_and_usage_data(
                start_30d, end_date, cost_type=cost_type, record_type="Usage"
            )
            analysis = analyze_carbon_footprint(cost_data)
            analyses[cost_type] = analysis
            recommendations_by_type[cost_type] = generate_recommendations(
                analysis, config=config
            )
            record_totals_by_type[cost_type] = get_record_type_totals(
                start_30d, end_date, cost_type
            )

            live_cost_data = get_cost_and_usage_data(
                start_7d, end_date, cost_type=cost_type, record_type="Usage"
            )
            live_services_by_type[cost_type] = summarize_live_services(live_cost_data)

        snapshot = store_metrics(
            analyses=analyses,
            recommendations_by_type=recommendations_by_type,
            record_totals_by_type=record_totals_by_type,
            live_services_by_type=live_services_by_type,
            config=config,
        )

        summary = snapshot["overall"]
        if should_send_notification(summary, recommendations_by_type, config):
            send_optimization_notifications(summary, recommendations_by_type, config)

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "Carbon footprint analysis completed successfully",
                    "snapshot_timestamp": summary["snapshot_timestamp"],
                    "total_cost_usd": round(
                        summary["cost_by_type"]["UnblendedCost"], 4
                    ),
                    "credits_applied_usd": round(
                        summary["credits_by_type"]["UnblendedCost"], 4
                    ),
                    "total_carbon_kg": round(
                        summary["carbon_by_type"]["UnblendedCost"], 4
                    ),
                    "services_analyzed": summary["service_count"],
                    "recommendations_count": len(
                        recommendations_by_type["UnblendedCost"]["all_actions"]
                    ),
                    "high_impact_count": len(
                        recommendations_by_type["UnblendedCost"]["high_impact_actions"]
                    ),
                }
            ),
        }
    except Exception as exc:
        logger.error(f"Error in carbon footprint analysis: {str(exc)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(exc)}),
        }


def get_sustainability_config():
    """Load project config from SSM, with a safe local fallback."""
    parameter_name = f"/{PROJECT_NAME}/sustainability-config"
    try:
        response = ssm_client.get_parameter(Name=parameter_name)
        config = json.loads(response["Parameter"]["Value"])
        logger.info(f"Loaded sustainability config from {parameter_name}")
        return config
    except Exception as exc:
        logger.warning(
            f"Falling back to default sustainability config ({parameter_name}): {exc}"
        )
        return DEFAULT_CONFIG


def get_cost_and_usage_data(start_date, end_date, cost_type, record_type="Usage"):
    """Retrieve grouped cost and usage data from Cost Explorer."""
    response = ce_client.get_cost_and_usage(
        TimePeriod={
            "Start": start_date.strftime("%Y-%m-%d"),
            "End": end_date.strftime("%Y-%m-%d"),
        },
        Granularity="MONTHLY",
        Metrics=[cost_type, "UsageQuantity"],
        Filter={"Dimensions": {"Key": "RECORD_TYPE", "Values": [record_type]}},
        GroupBy=[
            {"Type": "DIMENSION", "Key": "SERVICE"},
            {"Type": "DIMENSION", "Key": "REGION"},
        ],
    )
    logger.info(
        "Retrieved %s grouped rows for %s (%s → %s, %s)",
        sum(len(period.get("Groups", [])) for period in response["ResultsByTime"]),
        cost_type,
        start_date,
        end_date,
        record_type,
    )
    return response["ResultsByTime"]


def get_record_type_totals(start_date, end_date, cost_type):
    """Fetch top-level charge categories like Usage and Credit."""
    response = ce_client.get_cost_and_usage(
        TimePeriod={
            "Start": start_date.strftime("%Y-%m-%d"),
            "End": end_date.strftime("%Y-%m-%d"),
        },
        Granularity="MONTHLY",
        Metrics=[cost_type],
        GroupBy=[{"Type": "DIMENSION", "Key": "RECORD_TYPE"}],
    )

    totals = {}
    for period in response["ResultsByTime"]:
        for group in period.get("Groups", []):
            key = group["Keys"][0]
            totals[key] = totals.get(key, 0.0) + float(group["Metrics"][cost_type]["Amount"])
    return totals


def analyze_carbon_footprint(cost_data):
    """Analyze carbon footprint patterns from Cost Explorer service data."""
    analysis = {
        "total_cost": 0.0,
        "estimated_carbon_kg": 0.0,
        "services": {},
        "regions": {},
        "optimization_potential": 0.0,
    }

    for time_period in cost_data:
        for group in time_period.get("Groups", []):
            service = group["Keys"][0] if len(group["Keys"]) > 0 else "Unknown"
            region = group["Keys"][1] if len(group["Keys"]) > 1 else "global"
            metric_name = next(
                key for key in group["Metrics"].keys() if key != "UsageQuantity"
            )
            cost = float(group["Metrics"][metric_name]["Amount"])
            usage = float(group["Metrics"]["UsageQuantity"]["Amount"])

            if cost <= 0 and usage <= 0:
                continue

            analysis["total_cost"] += cost
            service_factor = CARBON_FACTORS.get(service, 0.0003)
            regional_factor = REGIONAL_FACTORS.get(region, 1.0)
            estimated_carbon = cost * service_factor * regional_factor
            analysis["estimated_carbon_kg"] += estimated_carbon

            if service not in analysis["services"]:
                analysis["services"][service] = {
                    "cost": 0.0,
                    "carbon_kg": 0.0,
                    "optimization_score": 0.0,
                    "primary_region": region,
                    "usage": 0.0,
                }

            svc = analysis["services"][service]
            svc["cost"] += cost
            svc["carbon_kg"] += estimated_carbon
            svc["usage"] += usage
            if svc["cost"] > 0:
                svc["optimization_score"] = (svc["carbon_kg"] / svc["cost"]) * 1000

            if region not in analysis["regions"]:
                analysis["regions"][region] = {"cost": 0.0, "carbon_kg": 0.0}
            analysis["regions"][region]["cost"] += cost
            analysis["regions"][region]["carbon_kg"] += estimated_carbon

    if analysis["total_cost"] > 0:
        analysis["optimization_potential"] = min(
            round((analysis["estimated_carbon_kg"] / analysis["total_cost"]) * 100, 2),
            100,
        )

    logger.info(
        "Analysis complete — cost: $%.4f, carbon: %.4f kg CO2e, services: %s",
        analysis["total_cost"],
        analysis["estimated_carbon_kg"],
        len(analysis["services"]),
    )
    return analysis


def summarize_live_services(cost_data):
    """Summarize the last 7 days of usage per service."""
    services = {}
    for time_period in cost_data:
        for group in time_period.get("Groups", []):
            service = group["Keys"][0] if len(group["Keys"]) > 0 else "Unknown"
            region = group["Keys"][1] if len(group["Keys"]) > 1 else "global"
            metric_name = next(
                key for key in group["Metrics"].keys() if key != "UsageQuantity"
            )
            cost = float(group["Metrics"][metric_name]["Amount"])
            usage = float(group["Metrics"]["UsageQuantity"]["Amount"])

            if service not in services:
                services[service] = {
                    "cost_7d": 0.0,
                    "usage_7d": 0.0,
                    "region": region,
                    "status": "IDLE",
                }

            services[service]["cost_7d"] += cost
            services[service]["usage_7d"] += usage
            if cost > 0 or usage > 0:
                services[service]["status"] = "ACTIVE"
    return services


def generate_recommendations(analysis, config):
    """Generate carbon footprint optimization recommendations."""
    thresholds = config.get("carbon_thresholds", {})
    high_impact_threshold = float(thresholds.get("high_impact", 50))
    optimization_threshold = float(thresholds.get("optimization_threshold", 0.1))

    recommendations = {
        "all_actions": [],
        "high_impact_actions": [],
        "estimated_savings": {"cost": 0.0, "carbon_kg": 0.0},
    }

    for service, metrics in analysis["services"].items():
        if metrics["cost"] > 1 and metrics["optimization_score"] > optimization_threshold:
            recommendation = {
                "service": service,
                "priority": "HIGH" if metrics["cost"] >= high_impact_threshold else "MEDIUM",
                "action": determine_optimization_action(service),
                "current_cost": round(metrics["cost"], 4),
                "current_carbon_kg": round(metrics["carbon_kg"], 6),
                "estimated_cost_savings": round(metrics["cost"] * 0.15, 4),
                "estimated_carbon_reduction": round(metrics["carbon_kg"] * 0.25, 6),
            }
            recommendations["all_actions"].append(recommendation)

            if metrics["cost"] >= high_impact_threshold:
                recommendations["high_impact_actions"].append(recommendation)
                recommendations["estimated_savings"]["cost"] += recommendation[
                    "estimated_cost_savings"
                ]
                recommendations["estimated_savings"]["carbon_kg"] += recommendation[
                    "estimated_carbon_reduction"
                ]

    logger.info(
        "Generated %s recommendations, %s high-impact",
        len(recommendations["all_actions"]),
        len(recommendations["high_impact_actions"]),
    )
    return recommendations


def determine_optimization_action(service):
    """Return a specific optimization action string for a given service."""
    action_map = {
        "Amazon Elastic Compute Cloud - Compute":
            "Rightsize instances or migrate to Graviton processors for 20% energy efficiency improvement",
        "Amazon Simple Storage Service":
            "Enable Intelligent Tiering and lifecycle policies to reduce storage carbon footprint",
        "Amazon Relational Database Service":
            "Evaluate Aurora Serverless v2 or rightsize DB instances for better resource utilization",
        "AWS Lambda":
            "Tune memory allocation and use ARM (Graviton2) architecture for improved efficiency",
        "Amazon CloudFront":
            "Review caching TTLs and enable Gzip/Brotli compression to reduce data transfer emissions",
        "Amazon DynamoDB":
            "Switch to on-demand billing for variable workloads to eliminate over-provisioned capacity",
        "Amazon Elastic Load Balancing":
            "Consolidate load balancers and enable connection multiplexing to reduce idle resource usage",
        "Amazon Virtual Private Cloud":
            "Audit NAT Gateway usage; use VPC endpoints to eliminate unnecessary data-transfer emissions",
        "Amazon API Gateway":
            "Enable caching on API stages to reduce Lambda invocations and downstream compute carbon",
        "Amazon CloudWatch":
            "Review log retention periods and metric filters to reduce unnecessary data storage",
    }
    return action_map.get(
        service,
        "Review resource utilization patterns and evaluate sustainable right-sizing alternatives",
    )


def store_metrics(
    analyses,
    recommendations_by_type,
    record_totals_by_type,
    live_services_by_type,
    config,
):
    """Store a cached dashboard snapshot in DynamoDB."""
    timestamp = datetime.now().isoformat()
    analysis_date = datetime.now().strftime("%Y-%m-%d")

    all_services = set()
    for cost_type in COST_TYPES:
        all_services.update(analyses[cost_type]["services"].keys())
        all_services.update(live_services_by_type[cost_type].keys())

    primary_recommendations = recommendations_by_type["UnblendedCost"]
    rec_lookup = {
        rec["service"]: {"action": rec["action"], "priority": rec["priority"]}
        for rec in primary_recommendations["all_actions"]
    }

    for service in sorted(all_services):
        costs = {}
        carbons = {}
        scores = {}
        live_costs = {}
        region = "global"
        usage_30d = 0.0
        usage_7d = 0.0
        status = "IDLE"

        for cost_type in COST_TYPES:
            service_metrics = analyses[cost_type]["services"].get(service, {})
            live_metrics = live_services_by_type[cost_type].get(service, {})

            costs[cost_type] = service_metrics.get("cost", 0.0)
            carbons[cost_type] = service_metrics.get("carbon_kg", 0.0)
            scores[cost_type] = service_metrics.get("optimization_score", 0.0)
            live_costs[cost_type] = live_metrics.get("cost_7d", 0.0)

            if service_metrics.get("primary_region"):
                region = service_metrics["primary_region"]
            elif live_metrics.get("region"):
                region = live_metrics["region"]

            usage_30d = max(usage_30d, service_metrics.get("usage", 0.0))
            usage_7d = max(usage_7d, live_metrics.get("usage_7d", 0.0))
            if live_metrics.get("status") == "ACTIVE" or service_metrics.get("cost", 0.0) > 0:
                status = "ACTIVE"

        rec_info = rec_lookup.get(service, {})
        table.put_item(
            Item={
                "MetricType": f"SERVICE#{service}",
                "Timestamp": timestamp,
                "ServiceName": service,
                "CarbonIntensity": dec(scores["UnblendedCost"]),
                "AnalysisDate": analysis_date,
                "SnapshotTimestamp": timestamp,
                "PrimaryRegion": region,
                "Status": status,
                "CostByType": decimal_map(costs),
                "CarbonKgByType": decimal_map(carbons),
                "OptimizationScoreByType": decimal_map(scores),
                "LiveCost7dByType": decimal_map(live_costs),
                "Usage30d": dec(usage_30d),
                "LiveUsage7d": dec(usage_7d),
                "Recommendations": [rec_info["action"]] if rec_info else [],
                "Action": rec_info.get("action", ""),
                "Priority": rec_info.get("priority", "LOW"),
            }
        )

    overall = build_overall_snapshot(
        analyses, recommendations_by_type, record_totals_by_type, config, timestamp, analysis_date
    )
    table.put_item(Item=overall["ddb_item"])
    logger.info("Stored dashboard snapshot with %s services", len(all_services))
    return {"overall": overall["response"]}


def build_overall_snapshot(
    analyses, recommendations_by_type, record_totals_by_type, config, timestamp, analysis_date
):
    """Build the summary row shared by the dashboard and notifications."""
    cost_by_type = {}
    carbon_by_type = {}
    credits_by_type = {}
    net_cost_by_type = {}
    optimization_by_type = {}
    high_impact_by_type = {}
    estimated_savings_by_type = {}
    estimated_carbon_savings_by_type = {}

    for cost_type in COST_TYPES:
        analysis = analyses[cost_type]
        recommendations = recommendations_by_type[cost_type]
        record_totals = record_totals_by_type[cost_type]

        cost_by_type[cost_type] = analysis["total_cost"]
        carbon_by_type[cost_type] = analysis["estimated_carbon_kg"]
        credits_by_type[cost_type] = abs(record_totals.get("Credit", 0.0))
        net_cost_by_type[cost_type] = (
            analysis["total_cost"] - credits_by_type[cost_type]
        )
        optimization_by_type[cost_type] = analysis["optimization_potential"]
        high_impact_by_type[cost_type] = len(recommendations["high_impact_actions"])
        estimated_savings_by_type[cost_type] = recommendations["estimated_savings"]["cost"]
        estimated_carbon_savings_by_type[cost_type] = recommendations["estimated_savings"][
            "carbon_kg"
        ]

    ddb_item = {
        "MetricType": "OVERALL_ANALYSIS",
        "Timestamp": timestamp,
        "ServiceName": "SUMMARY",
        "CarbonIntensity": dec(optimization_by_type["UnblendedCost"]),
        "AnalysisDate": analysis_date,
        "SnapshotTimestamp": timestamp,
        "DataSource": "dynamodb-snapshot",
        "NotificationThreshold": dec(
            float(
                config.get("notification_settings", {}).get("email_threshold", 10)
            )
        ),
        "CostByType": decimal_map(cost_by_type),
        "NetCostByType": decimal_map(net_cost_by_type),
        "CreditsAppliedByType": decimal_map(credits_by_type),
        "CarbonKgByType": decimal_map(carbon_by_type),
        "OptimizationPotentialByType": decimal_map(optimization_by_type),
        "HighImpactCountByType": decimal_int_map(high_impact_by_type),
        "EstimatedCostSavingsByType": decimal_map(estimated_savings_by_type),
        "EstimatedCarbonSavingsByType": decimal_map(estimated_carbon_savings_by_type),
        "TopRecommendations": [
            rec["action"]
            for rec in recommendations_by_type["UnblendedCost"]["high_impact_actions"][:5]
        ],
        "ServiceCount": len(analyses["UnblendedCost"]["services"]),
        "TotalCost": dec(cost_by_type["UnblendedCost"]),
        "EstimatedCarbonKg": dec(carbon_by_type["UnblendedCost"]),
        "OptimizationPotential": dec(optimization_by_type["UnblendedCost"]),
        "HighImpactCount": high_impact_by_type["UnblendedCost"],
        "EstimatedCostSavings": dec(estimated_savings_by_type["UnblendedCost"]),
        "EstimatedCarbonSavings": dec(
            estimated_carbon_savings_by_type["UnblendedCost"]
        ),
    }

    response = {
        "snapshot_timestamp": timestamp,
        "analysis_date": analysis_date,
        "service_count": len(analyses["UnblendedCost"]["services"]),
        "cost_by_type": cost_by_type,
        "net_cost_by_type": net_cost_by_type,
        "credits_by_type": credits_by_type,
        "carbon_by_type": carbon_by_type,
        "notification_threshold": float(
            config.get("notification_settings", {}).get("email_threshold", 10)
        ),
    }
    return {"ddb_item": ddb_item, "response": response}


def should_send_notification(summary, recommendations_by_type, config):
    """Send alerts for meaningful usage or clear optimization wins."""
    threshold = float(config.get("notification_settings", {}).get("email_threshold", 10))
    unblended_usage = summary["cost_by_type"]["UnblendedCost"]
    high_impact = recommendations_by_type["UnblendedCost"]["high_impact_actions"]
    return bool(high_impact) or unblended_usage >= threshold


def send_optimization_notifications(summary, recommendations_by_type, config):
    """Send SNS notification about meaningful cost or optimization activity."""
    recommendations = recommendations_by_type["UnblendedCost"]
    threshold = float(config.get("notification_settings", {}).get("email_threshold", 10))
    gross_usage = summary["cost_by_type"]["UnblendedCost"]
    credits = summary["credits_by_type"]["UnblendedCost"]
    net_cost = summary["net_cost_by_type"]["UnblendedCost"]

    lines = [
        "Carbon Optimizer Billing Snapshot",
        "",
        f"Snapshot: {summary['snapshot_timestamp']}",
        f"Gross AWS usage (30d): ${gross_usage:.4f}",
        f"Credits applied (30d): ${credits:.4f}",
        f"Net billed after credits: ${net_cost:.4f}",
        f"Alert threshold: ${threshold:.2f}",
        "",
        f"High-impact opportunities: {len(recommendations['high_impact_actions'])}",
    ]

    if recommendations["high_impact_actions"]:
        lines.extend(["", "Top recommendations:"])
        for idx, rec in enumerate(recommendations["high_impact_actions"][:3], start=1):
            lines.extend(
                [
                    f"{idx}. [{rec['priority']}] {rec['service']}",
                    f"   Cost: ${rec['current_cost']:.4f}",
                    f"   Carbon: {rec['current_carbon_kg']:.6f} kg CO2e",
                    f"   Action: {rec['action']}",
                ]
            )
    else:
        lines.extend(
            [
                "",
                "No high-impact actions crossed the configured threshold yet.",
                "This alert was sent because your month-to-date AWS usage exceeded the notification threshold.",
            ]
        )

    sns_client.publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject="Carbon Optimizer Billing Snapshot",
        Message="\n".join(lines),
    )
    logger.info("SNS notification sent successfully")


def dec(value):
    return Decimal(str(round(float(value), 8)))


def decimal_map(values):
    return {key: dec(value) for key, value in values.items()}


def decimal_int_map(values):
    return {key: int(value) for key, value in values.items()}
