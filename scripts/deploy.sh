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