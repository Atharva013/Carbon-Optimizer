import json
import logging
import os
from datetime import datetime
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr, Key


logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ["DYNAMODB_TABLE"]
table = dynamodb.Table(TABLE_NAME)

VALID_COST_TYPES = {"BlendedCost", "UnblendedCost", "NetUnblendedCost"}
COST_TYPE_LABELS = {
    "BlendedCost": "Blended",
    "UnblendedCost": "Unblended",
    "NetUnblendedCost": "Net Unblended (after credits)",
}

SNAPSHOT_CACHE = {"ts": 0.0, "data": None}


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization",
        "Access-Control-Allow-Methods": "GET,OPTIONS",
        "Content-Type": "application/json",
    }


def ok(body):
    return {
        "statusCode": 200,
        "headers": cors_headers(),
        "body": json.dumps(body, cls=DecimalEncoder),
    }


def err(msg, code=500):
    return {
        "statusCode": code,
        "headers": cors_headers(),
        "body": json.dumps({"error": msg}),
    }


def _parse_cost_type(event):
    params = event.get("queryStringParameters") or {}
    ct = params.get("cost_type", "UnblendedCost")
    shorthand = {
        "blended": "BlendedCost",
        "unblended": "UnblendedCost",
        "net_unblended": "NetUnblendedCost",
    }
    ct = shorthand.get(ct.lower(), ct)
    if ct not in VALID_COST_TYPES:
        ct = "UnblendedCost"
    return ct


def _now_ts():
    return datetime.now().timestamp()


def _to_float(value, default=0.0):
    if value is None:
        return default
    try:
        return float(value)
    except Exception:
        return default


def _pick_metric(item, map_field, legacy_field, cost_type, default=0.0):
    mapping = item.get(map_field)
    if isinstance(mapping, dict) and cost_type in mapping:
        return _to_float(mapping[cost_type], default)
    return _to_float(item.get(legacy_field), default)


def _load_latest_snapshot(force=False):
    if (
        not force
        and SNAPSHOT_CACHE["data"] is not None
        and (_now_ts() - SNAPSHOT_CACHE["ts"]) < 60
    ):
        return SNAPSHOT_CACHE["data"]

    overall_resp = table.query(
        KeyConditionExpression=Key("MetricType").eq("OVERALL_ANALYSIS"),
        ScanIndexForward=False,
        Limit=1,
    )
    if not overall_resp.get("Items"):
        raise RuntimeError("No OVERALL_ANALYSIS snapshot found. Run the analyzer Lambda first.")

    overall = overall_resp["Items"][0]
    snapshot_ts = overall["Timestamp"]
    service_rows = []
    scan_kwargs = {
        "FilterExpression": Attr("MetricType").begins_with("SERVICE#")
        & Attr("Timestamp").eq(snapshot_ts)
    }

    while True:
        response = table.scan(**scan_kwargs)
        service_rows.extend(response.get("Items", []))
        if "LastEvaluatedKey" not in response:
            break
        scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    snapshot = {"overall": overall, "services": service_rows}
    SNAPSHOT_CACHE["ts"] = _now_ts()
    SNAPSHOT_CACHE["data"] = snapshot
    return snapshot


def lambda_handler(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": cors_headers(), "body": ""}

    path = event.get("path", "/")
    cost_type = _parse_cost_type(event)
    logger.info("Dashboard API: %s %s [%s]", event.get("httpMethod", "GET"), path, cost_type)

    try:
        if path.endswith("/summary"):
            return get_summary(cost_type)
        if path.endswith("/metrics"):
            return get_metrics(cost_type)
        if path.endswith("/recommendations"):
            return get_recommendations(cost_type)
        if path.endswith("/services"):
            return get_services(cost_type)
        if path.endswith("/live-services"):
            return get_live_services(cost_type)
        if path.endswith("/health"):
            snapshot = _load_latest_snapshot()
            return ok(
                {
                    "status": "healthy",
                    "table": TABLE_NAME,
                    "snapshot_timestamp": snapshot["overall"].get("SnapshotTimestamp"),
                    "service_count": len(snapshot["services"]),
                    "ts": datetime.now().isoformat(),
                }
            )
        return err(f"Route not found: {path}", 404)
    except Exception as exc:
        logger.error("API error on %s: %s", path, str(exc))
        return err(str(exc))


def get_summary(cost_type="UnblendedCost"):
    snapshot = _load_latest_snapshot()
    overall = snapshot["overall"]

    return ok(
        {
            "summary": {
                "total_monthly_cost_usd": _pick_metric(
                    overall, "CostByType", "TotalCost", cost_type
                ),
                "net_monthly_cost_usd": _pick_metric(
                    overall, "NetCostByType", "TotalCost", cost_type
                ),
                "credits_applied_usd": _pick_metric(
                    overall, "CreditsAppliedByType", None, cost_type
                ),
                "total_carbon_kg_co2": _pick_metric(
                    overall, "CarbonKgByType", "EstimatedCarbonKg", cost_type
                ),
                "services_tracked": int(overall.get("ServiceCount", len(snapshot["services"]))),
                "optimization_potential": _pick_metric(
                    overall, "OptimizationPotentialByType", "OptimizationPotential", cost_type
                ),
                "high_impact_count": int(
                    _pick_metric(overall, "HighImpactCountByType", "HighImpactCount", cost_type)
                ),
                "estimated_cost_savings": _pick_metric(
                    overall, "EstimatedCostSavingsByType", "EstimatedCostSavings", cost_type
                ),
                "estimated_carbon_savings": _pick_metric(
                    overall, "EstimatedCarbonSavingsByType", "EstimatedCarbonSavings", cost_type
                ),
                "last_updated": overall.get("AnalysisDate", "N/A"),
                "last_timestamp": overall.get("SnapshotTimestamp", overall.get("Timestamp")),
                "top_recommendations": overall.get("TopRecommendations", []),
                "data_source": overall.get("DataSource", "dynamodb-snapshot"),
                "cost_type": cost_type,
                "cost_type_label": COST_TYPE_LABELS.get(cost_type, cost_type),
                "table_name": TABLE_NAME,
            }
        }
    )


def get_metrics(cost_type="UnblendedCost"):
    snapshot = _load_latest_snapshot()
    metrics = []
    for item in snapshot["services"]:
        cost = _pick_metric(item, "CostByType", "Cost", cost_type)
        carbon = _pick_metric(item, "CarbonKgByType", "CarbonKg", cost_type)
        if cost == 0 and carbon == 0:
            continue
        metrics.append(
            {
                "service_name": item["ServiceName"],
                "monthly_cost": cost,
                "carbon_kg_co2": carbon,
                "optimization_score": _pick_metric(
                    item, "OptimizationScoreByType", "CarbonIntensity", cost_type
                ),
                "primary_region": item.get("PrimaryRegion", "global"),
                "analysis_date": item.get("AnalysisDate"),
                "recommendations": item.get("Recommendations", []),
            }
        )

    metrics.sort(key=lambda x: x["carbon_kg_co2"], reverse=True)
    return ok({"metrics": metrics, "count": len(metrics), "cost_type": cost_type})


def get_recommendations(cost_type="UnblendedCost"):
    snapshot = _load_latest_snapshot()
    recs = []
    for item in snapshot["services"]:
        cost = _pick_metric(item, "CostByType", "Cost", cost_type)
        carbon = _pick_metric(item, "CarbonKgByType", "CarbonKg", cost_type)
        action = item.get("Action") or (
            item.get("Recommendations", [""])[0] if item.get("Recommendations") else ""
        )
        if not action or (cost <= 0 and carbon <= 0):
            continue
        recs.append(
            {
                "service": item["ServiceName"],
                "action": action,
                "priority": item.get("Priority", "MEDIUM"),
                "cost": cost,
                "carbon": carbon,
            }
        )

    recs.sort(key=lambda x: x["cost"], reverse=True)
    return ok({"recommendations": recs[:10], "count": len(recs), "cost_type": cost_type})


def get_services(cost_type="UnblendedCost"):
    snapshot = _load_latest_snapshot()
    services = []
    for item in snapshot["services"]:
        cost = _pick_metric(item, "CostByType", "Cost", cost_type)
        carbon = _pick_metric(item, "CarbonKgByType", "CarbonKg", cost_type)
        usage_30d = _to_float(item.get("Usage30d"), 0.0)
        if cost == 0 and carbon == 0 and usage_30d == 0:
            continue
        services.append(
            {
                "name": item["ServiceName"],
                "cost": cost,
                "carbon": carbon,
                "region": item.get("PrimaryRegion", "global"),
                "date": item.get("AnalysisDate"),
                "score": _pick_metric(
                    item, "OptimizationScoreByType", "CarbonIntensity", cost_type
                ),
                "status": item.get("Status", "IDLE"),
            }
        )

    services.sort(key=lambda x: x["carbon"], reverse=True)
    return ok({"services": services, "count": len(services), "cost_type": cost_type})


def get_live_services(cost_type="UnblendedCost"):
    snapshot = _load_latest_snapshot()
    services = []
    for item in snapshot["services"]:
        cost_7d = _pick_metric(item, "LiveCost7dByType", None, cost_type)
        usage_7d = _to_float(item.get("LiveUsage7d"), 0.0)
        if cost_7d == 0 and usage_7d == 0:
            continue
        services.append(
            {
                "name": item["ServiceName"],
                "cost_7d": round(cost_7d, 8),
                "usage": round(usage_7d, 4),
                "region": item.get("PrimaryRegion", "global"),
                "status": item.get("Status", "IDLE"),
            }
        )

    services.sort(key=lambda x: x["cost_7d"], reverse=True)
    overall = snapshot["overall"]
    return ok(
        {
            "live_services": services,
            "count": len(services),
            "period_start": "Last 7 days (cached by analyzer)",
            "period_end": overall.get("SnapshotTimestamp"),
            "active_count": sum(1 for svc in services if svc["status"] == "ACTIVE"),
            "cost_type": cost_type,
        }
    )
