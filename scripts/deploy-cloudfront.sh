#!/bin/bash
# =============================================================================
# Section 5b — CloudFront HTTPS Deploy (Idempotent)
# Deploys: CloudFront Distribution in front of S3 Static Website for HTTPS
# =============================================================================
set -e

export AWS_REGION=${AWS_REGION:-ap-south-1}
export PROJECT_NAME=${PROJECT_NAME:-carbon-optimizer-cloud}
export S3_BUCKET=${S3_BUCKET:-${PROJECT_NAME}-data}

echo "=================================================="
echo "  Carbon Optimizer — CloudFront HTTPS Deploy"
echo "  Project : ${PROJECT_NAME}"
echo "=================================================="

S3_DOMAIN="${S3_BUCKET}.s3-website.${AWS_REGION}.amazonaws.com"

# Check if distribution already exists using the exact DomainName
DIST_ID=$(aws cloudfront list-distributions \
    --query "DistributionList.Items[?Origins.Items[0].DomainName=='${S3_DOMAIN}'].Id" \
    --output text 2>/dev/null | head -1)

if [ -z "${DIST_ID}" ] || [ "${DIST_ID}" == "None" ]; then
    echo "  Creating CloudFront Distribution. This will take multiple minutes..."

    CALLER_REF=$(date +%s)

    cat > /tmp/cf-config.json << EOF
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
        --distribution-config file:///tmp/cf-config.json \
        --tags "Items=[{Key=Project,Value=${PROJECT_NAME}}]" > /tmp/cf-out.json 2>/dev/null

    DIST_ID=$(cat /tmp/cf-out.json | python3 -c "import sys,json; print(json.load(sys.stdin)['Distribution']['Id'])")
    DIST_DOMAIN=$(cat /tmp/cf-out.json | python3 -c "import sys,json; print(json.load(sys.stdin)['Distribution']['DomainName'])")

    echo "✅ Distribution created: ${DIST_ID}"
    echo "   Status: IN_PROGRESS (propagation takes 5-10 minutes)"
else
    echo "✅ Distribution already exists: ${DIST_ID}"
    DIST_DOMAIN=$(aws cloudfront get-distribution --id ${DIST_ID} --query 'Distribution.DomainName' --output text 2>/dev/null)
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
