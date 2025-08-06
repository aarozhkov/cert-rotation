# AWS Secrets Manager Certificate Storage

This document explains how to store certificates in AWS Secrets Manager for use with the certificate rotation service.

## Secret Format

Certificates should be stored as JSON in AWS Secrets Manager with the following structure:

```json
{
  "certificate": "-----BEGIN CERTIFICATE-----\nMIIE...\n-----END CERTIFICATE-----",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----",
  "certificate_chain": "-----BEGIN CERTIFICATE-----\nMIIE...\n-----END CERTIFICATE-----",
  "domain_name": "example.com",
  "description": "Certificate for example.com"
}
```

### Required Fields

- **`certificate`**: The PEM-encoded certificate
- **`private_key`**: The PEM-encoded private key

### Optional Fields

- **`certificate_chain`**: The PEM-encoded certificate chain (intermediate certificates)
- **`domain_name`**: Primary domain name for the certificate (used for naming)
- **`description`**: Human-readable description

## Creating Secrets via AWS CLI

### Method 1: From Files

```bash
# Create the JSON structure
cat > cert-secret.json << EOF
{
  "certificate": "$(cat certificate.pem | sed ':a;N;$!ba;s/\n/\\n/g')",
  "private_key": "$(cat private-key.pem | sed ':a;N;$!ba;s/\n/\\n/g')",
  "certificate_chain": "$(cat ca-bundle.pem | sed ':a;N;$!ba;s/\n/\\n/g')",
  "domain_name": "example.com",
  "description": "Certificate for example.com"
}
EOF

# Create the secret
aws secretsmanager create-secret \
  --name "my-certificate" \
  --description "Certificate for example.com" \
  --secret-string file://cert-secret.json \
  --tags Key=Environment,Value=production Key=Application,Value=web-server
```

### Method 2: Direct Command

```bash
aws secretsmanager create-secret \
  --name "my-certificate" \
  --description "Certificate for example.com" \
  --secret-string '{
    "certificate": "-----BEGIN CERTIFICATE-----\nYOUR_CERT_HERE\n-----END CERTIFICATE-----",
    "private_key": "-----BEGIN PRIVATE KEY-----\nYOUR_KEY_HERE\n-----END PRIVATE KEY-----",
    "domain_name": "example.com"
  }'
```

## Updating Certificates

To update a certificate (for renewal):

```bash
aws secretsmanager update-secret \
  --secret-id "my-certificate" \
  --secret-string file://updated-cert-secret.json
```

## Environment Configuration

Set the secret names in your environment:

```bash
export CERT_ROTATION_SECRETS_NAMES="my-certificate,another-certificate"
```

## IAM Permissions

The EC2 instance needs the following IAM permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "secretsmanager:GetSecretValue",
                "secretsmanager:DescribeSecret",
                "secretsmanager:ListSecrets"
            ],
            "Resource": "*"
        }
    ]
}
```

For specific secrets only:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "secretsmanager:GetSecretValue",
                "secretsmanager:DescribeSecret"
            ],
            "Resource": [
                "arn:aws:secretsmanager:us-west-2:123456789012:secret:my-certificate-*",
                "arn:aws:secretsmanager:us-west-2:123456789012:secret:another-certificate-*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "secretsmanager:ListSecrets"
            ],
            "Resource": "*"
        }
    ]
}
```

## Benefits of Secrets Manager

1. **Full Access**: Unlike ACM, you can read certificate data
2. **Versioning**: Automatic versioning when secrets are updated
3. **Encryption**: Automatic encryption at rest
4. **Access Control**: Fine-grained IAM permissions
5. **Audit Trail**: CloudTrail logs all access
6. **Cross-Region**: Can replicate secrets across regions
7. **Rotation**: Built-in rotation capabilities (if needed)

## Migration from Files

If you have existing certificate files:

```bash
#!/bin/bash
CERT_FILE="certificate.pem"
KEY_FILE="private-key.pem"
CHAIN_FILE="ca-bundle.pem"
SECRET_NAME="my-certificate"
DOMAIN="example.com"

# Create JSON
jq -n \
  --arg cert "$(cat $CERT_FILE)" \
  --arg key "$(cat $KEY_FILE)" \
  --arg chain "$(cat $CHAIN_FILE)" \
  --arg domain "$DOMAIN" \
  '{
    certificate: $cert,
    private_key: $key,
    certificate_chain: $chain,
    domain_name: $domain,
    description: ("Certificate for " + $domain)
  }' > secret.json

# Create secret
aws secretsmanager create-secret \
  --name "$SECRET_NAME" \
  --secret-string file://secret.json

# Clean up
rm secret.json
```
