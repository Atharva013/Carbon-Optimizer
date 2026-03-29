#!/bin/bash
# Section 4 — Cost & Usage Reports + Systems Manager Configuration
# Assigned To: Priyank Adhav

# Task 4.1 — Add S3 Bucket Policy for CUR Delivery
cat > /tmp/cur-bucket-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "billingreports.amazonaws.com"
      },
      "Action": [
        "s3:GetBucketAcl",
        "s3:GetBucketPolicy"
      ],
      "Resource": "arn:aws:s3:::${S3_BUCKET}",
      "Condition": {
        "StringEquals": {
          "aws:SourceAccount": "${AWS_ACCOUNT_ID}"
        }
      }
    },
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "billingreports.amazonaws.com"
      },
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::${S3_BUCKET}/cost-usage-reports/*",
      "Condition": {
        "StringEquals": {
          "aws:SourceAccount": "${AWS_ACCOUNT_ID}"
        }
      }
    },
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "bcm-data-exports.amazonaws.com"
      },
      "Action": [
        "s3:GetBucketAcl",
        "s3:GetBucketPolicy"
      ],
      "Resource": "arn:aws:s3:::${S3_BUCKET}",
      "Condition": {
        "StringEquals": {
          "aws:SourceAccount": "${AWS_ACCOUNT_ID}"
        }
      }
    },
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "bcm-data-exports.amazonaws.com"
      },
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::${S3_BUCKET}/cur2-exports/*",
      "Condition": {
        "StringEquals": {
          "aws:SourceAccount": "${AWS_ACCOUNT_ID}"
        }
      }
    }
  ]
}
EOF

aws s3api put-bucket-policy \
    --bucket ${S3_BUCKET} \
    --policy file:///tmp/cur-bucket-policy.json

echo "✅ S3 bucket policy updated for CUR delivery"

# Task 4.2 — Create Data Export (CUR 2.0)
# Note: Legacy aws cur put-report-definition requires root account billing access
# and is restricted to us-east-1 buckets. AWS now classifies legacy CUR as a
# legacy feature. We use aws bcm-data-exports with the CARBON_EMISSIONS table
# instead, which exports real Scope 1, 2, and 3 emissions data in MTCO2e directly.
aws bcm-data-exports create-export \
    --region us-east-1 \
    --export '{
        "Name": "carbon-optimization-export",
        "DataQuery": {
            "QueryStatement": "SELECT * FROM CARBON_EMISSIONS",
            "TableConfigurations": {
                "CARBON_EMISSIONS": {
                    "TIME_GRANULARITY": "DAILY"
                }
            }
        },
        "DestinationConfigurations": {
            "S3Destination": {
                "S3Bucket": "'"${S3_BUCKET}"'",
                "S3Prefix": "cur2-exports/",
                "S3Region": "'"${AWS_REGION}"'",
                "S3OutputConfigurations": {
                    "Compression": "GZIP",
                    "Format": "PARQUET",
                    "OutputType": "CUSTOM",
                    "Overwrite": "OVERWRITE_REPORT"
                }
            }
        },
        "RefreshCadence": {
            "Frequency": "SYNCHRONOUS"
        }
    }'

echo "✅ CUR 2.0 Data Export created for carbon emissions analysis"
echo "Reports will appear in S3 within 24 hours of the first full day."

# Task 4.3 — Create Sustainability Configuration in SSM Parameter Store
aws ssm put-parameter \
    --name "/${PROJECT_NAME}/sustainability-config" \
    --value '{
        "carbon_thresholds": {
            "high_impact": 100,
            "optimization_threshold": 0.2
        },
        "regional_preferences": {
            "preferred_regions": ["us-west-2", "eu-north-1", "ca-central-1"],
            "avoid_regions": []
        },
        "optimization_rules": {
            "graviton_migration": true,
            "intelligent_tiering": true,
            "serverless_first": true,
            "right_sizing": true
        },
        "notification_settings": {
            "email_threshold": 50,
            "weekly_summary": true
        }
    }' \
    --type String \
    --description "Sustainability optimization configuration for ${PROJECT_NAME}"

echo "✅ SSM Parameter created: /${PROJECT_NAME}/sustainability-config"