#!/bin/bash
# =============================================================================
# Section 5b — CloudFront HTTPS Deploy (Idempotent)
# Deploys: CloudFront Distribution in front of S3 Static Website for HTTPS
# =============================================================================
set -euo pipefail

export AWS_REGION=${AWS_REGION:-ap-south-1}
export PROJECT_NAME=${PROJECT_NAME:-carbon-optimizer-cloud}
export S3_BUCKET=${S3_BUCKET:-${PROJECT_NAME}-data}
export AWS_PAGER=""

echo "=================================================="
echo "  Carbon Optimizer — CloudFront HTTPS Deploy"
echo "  Project : ${PROJECT_NAME}"
echo "=================================================="

S3_DOMAIN="${S3_BUCKET}.s3-website.${AWS_REGION}.amazonaws.com"
CF_CONFIG_FILE="/tmp/cf-config.json"
CF_OUTPUT_FILE="/tmp/cf-out.json"

echo "  Verifying S3 static website hosting on ${S3_BUCKET}..."
if ! aws s3api get-bucket-website --bucket "${S3_BUCKET}" >/dev/null; then
    echo "❌ S3 static website hosting is not enabled for ${S3_BUCKET}."
    echo "   Run bash scripts/deploy-dashboard.sh first, then retry."
    exit 1
fi
echo "✅ S3 website endpoint detected: ${S3_DOMAIN}"

# Check if distribution already exists using the exact DomainName
DIST_ID=$(aws cloudfront list-distributions \
    --query "DistributionList.Items[?Origins.Items[0].DomainName=='${S3_DOMAIN}'].Id" \
    --output text | head -1)

if [ -z "${DIST_ID}" ] || [ "${DIST_ID}" == "None" ]; then
    echo "  Creating CloudFront distribution..."
    echo "  The API call usually returns quickly; global HTTPS propagation takes 5-10 minutes."

    CALLER_REF=$(date +%s)

    cat > "${CF_CONFIG_FILE}" << EOF
{
    "CallerReference": "${CALLER_REF}",
    "Aliases": { "Quantity": 0 },
    "DefaultRootObject": "index.html",
    "Origins": {
        "Quantity": 1,
        "Items": [
            {
                "Id": "S3-Website-${S3_BUCKET}",
                "DomainName": "${S3_DOMAIN}",
                "CustomOriginConfig": {
                    "HTTPPort": 80,
                    "HTTPSPort": 443,
                    "OriginProtocolPolicy": "http-only",
                    "OriginSslProtocols": {
                        "Quantity": 1,
                        "Items": ["TLSv1.2"]
                    }
                }
            }
        ]
    },
    "DefaultCacheBehavior": {
        "TargetOriginId": "S3-Website-${S3_BUCKET}",
        "ViewerProtocolPolicy": "redirect-to-https",
        "AllowedMethods": {
            "Quantity": 2,
            "Items": ["GET", "HEAD"],
            "CachedMethods": {
                "Quantity": 2,
                "Items": ["GET", "HEAD"]
            }
        },
        "Compress": true,
        "ForwardedValues": {
            "QueryString": false,
            "Cookies": { "Forward": "none" },
            "Headers": { "Quantity": 0 },
            "QueryStringCacheKeys": { "Quantity": 0 }
        },
        "MinTTL": 0,
        "DefaultTTL": 86400,
        "MaxTTL": 31536000
    },
    "Comment": "Carbon Optimizer Dashboard — HTTPS",
    "PriceClass": "PriceClass_100",
    "Enabled": true,
    "ViewerCertificate": {
        "CloudFrontDefaultCertificate": true,
        "MinimumProtocolVersion": "TLSv1.2_2021"
    },
    "HttpVersion": "http2"
}
EOF

    aws cloudfront create-distribution \
        --distribution-config "file://${CF_CONFIG_FILE}" \
        --output json > "${CF_OUTPUT_FILE}"

    DIST_ID=$(python3 -c "import json; print(json.load(open('${CF_OUTPUT_FILE}'))['Distribution']['Id'])")
    DIST_DOMAIN=$(python3 -c "import json; print(json.load(open('${CF_OUTPUT_FILE}'))['Distribution']['DomainName'])")
    DIST_STATUS=$(python3 -c "import json; print(json.load(open('${CF_OUTPUT_FILE}'))['Distribution']['Status'])")

    echo "✅ Distribution created: ${DIST_ID}"
    echo "   Initial status: ${DIST_STATUS}"
else
    echo "✅ Distribution already exists: ${DIST_ID}"
    DIST_DOMAIN=$(aws cloudfront get-distribution --id "${DIST_ID}" --query 'Distribution.DomainName' --output text)
fi

echo ""
echo "=================================================="
echo "  Deploy Triggered ✅"
echo "  Secure HTTPS URL: https://${DIST_DOMAIN}/dashboard/index.html"
echo ""
echo "  ⚠️ IMPORTANT: AWS can take 5-10 minutes to finish"
echo "  propagating your CloudFront site globally."
echo "  If the link doesn't instantly work, grab a coffee and wait!"
echo "=================================================="
