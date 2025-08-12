# Certificate Rotation Service

A Python service for synchronizing certificates stored in AWS Secrets Manager with local filesystem for HAProxy certificate management on EC2 instances.

## Features

- **FastAPI HTTP Service**: RESTful API with health checks and manual triggers
- **Prometheus Metrics**: Certificate expiration monitoring and operational metrics
- **AWS Secrets Manager Integration**: Automatic certificate download and change detection
- **File System Monitoring**: Real-time detection of certificate changes
- **HAProxy Integration**: Automatic reload signals when certificates are updated
- **Container Ready**: Dockerized with UV package management
- **EC2 IAM Role Support**: Uses instance roles for AWS authentication

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   FastAPI App   │    │   Certificate    │    │   HAProxy       │
│                 │    │   Monitor        │    │   Server        │
│ /health         │    │                  │    │                 │
│ /metrics        │◄───┤ File Watcher     │───►│ Reload Signal   │
│ /reload         │    │ Expiry Calc      │    │                 │
│ /status         │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │
         │                       │
         ▼                       ▼
┌─────────────────┐    ┌──────────────────┐
│   Background    │    │   Local Cert     │
│   Scheduler     │    │   Storage        │
│                 │    │                  │
│ Periodic Sync   │◄───┤ /app/certs/      │
│ ACM Polling     │    │ *.pem, *.key     │
└─────────────────┘    └──────────────────┘
         │
         ▼
┌─────────────────┐
│   AWS ACM       │
│                 │
│ Certificate     │
│ Manager         │
└─────────────────┘
```

## Quick Start

### Using Docker (Recommended)

1. **Build the container:**
```bash
docker build -t cert-rotation .
```

**Docker Run Examples:**
- [Basic Secrets Manager setup](#basic-secrets-manager) - Simple development setup
- [Tag-based certificate discovery](#tag-based-discovery) - Automatic certificate discovery using tags
- [EC2 with IAM role](#ec2-iam-role) - Production EC2 deployment
- [Development with credentials](#development-credentials) - Local testing
- [Docker signal reload](#docker-signal-reload) - Container-based HAProxy reload via HUP signal
- [Complete production setup](#production-monitoring) - Full monitoring and health checks

2. **Basic Secrets Manager setup:** {#basic-secrets-manager}
```bash
docker run -d \
  --name cert-rotation \
  -p 8000:8000 \
  -v /path/to/certs:/app/certs \
  -e CERT_ROTATION_SECRETS_NAMES="my-web-cert,my-api-cert" \
  -e CERT_ROTATION_AWS_REGION="us-east-1" \
  -e CERT_ROTATION_HAPROXY_RELOAD_URL="http://haproxy:8404/reload" \
  -e CERT_ROTATION_CHECK_INTERVAL_MINUTES="30" \
  -e CERT_ROTATION_LOG_LEVEL="INFO" \
  cert-rotation
```

3. **Tag-based certificate discovery:** {#tag-based-discovery}
```bash
# Automatically discover certificates by tags
docker run -d \
  --name cert-rotation \
  -p 8000:8000 \
  -v /path/to/certs:/app/certs \
  -e CERT_ROTATION_TAG_KEY="Environment" \
  -e CERT_ROTATION_TAG_VALUE="production" \
  -e CERT_ROTATION_AWS_REGION="us-east-1" \
  -e CERT_ROTATION_HAPROXY_RELOAD_URL="http://haproxy:8404/reload" \
  -e CERT_ROTATION_CHECK_INTERVAL_MINUTES="30" \
  -e CERT_ROTATION_LOG_LEVEL="INFO" \
  cert-rotation
```

4. **EC2 with IAM role:** {#ec2-iam-role}
```bash
# When running on EC2 with IAM role attached
docker run -d \
  --name cert-rotation \
  -p 8000:8000 \
  -v /opt/haproxy/certs:/app/certs \
  -e CERT_ROTATION_SECRETS_NAMES="prod-web-cert,prod-api-cert" \
  -e CERT_ROTATION_AWS_REGION="us-west-2" \
  -e CERT_ROTATION_HAPROXY_STATS_SOCKET="/var/run/haproxy.sock" \
  -e CERT_ROTATION_CHECK_INTERVAL_MINUTES="60" \
  --restart unless-stopped \
  cert-rotation
```

5. **Development with credentials:** {#development-credentials}
```bash
# For development/testing with AWS credentials
docker run -d \
  --name cert-rotation \
  -p 8000:8000 \
  -v $(pwd)/certs:/app/certs \
  -e AWS_ACCESS_KEY_ID="your-access-key" \
  -e AWS_SECRET_ACCESS_KEY="your-secret-key" \
  -e AWS_SESSION_TOKEN="your-session-token" \
  -e CERT_ROTATION_SECRETS_NAMES="dev-cert-1,dev-cert-2" \
  -e CERT_ROTATION_AWS_REGION="us-east-1" \
  -e CERT_ROTATION_LOG_LEVEL="DEBUG" \
  cert-rotation
```

5. **Docker signal reload (recommended for containers):** {#docker-signal-reload}
```bash
# Run with Docker socket access for HUP signal reload
docker run -d \
  --name cert-rotation \
  -p 8000:8000 \
  -v /opt/haproxy/certs:/app/certs \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e CERT_ROTATION_SECRETS_NAMES="prod-web-cert,prod-api-cert" \
  -e CERT_ROTATION_AWS_REGION="us-east-1" \
  -e CERT_ROTATION_HAPROXY_CONTAINER_NAME="haproxy" \
  -e CERT_ROTATION_CHECK_INTERVAL_MINUTES="30" \
  --restart unless-stopped \
  cert-rotation
```

6. **Complete production setup:** {#production-monitoring}
```bash
docker run -d \
  --name cert-rotation \
  -p 8000:8000 \
  -v /opt/haproxy/certs:/app/certs:rw \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e CERT_ROTATION_SECRETS_NAMES="prod-web-cert,prod-api-cert,prod-admin-cert" \
  -e CERT_ROTATION_AWS_REGION="us-east-1" \
  -e CERT_ROTATION_HAPROXY_CONTAINER_NAME="haproxy" \
  -e CERT_ROTATION_CHECK_INTERVAL_MINUTES="30" \
  -e CERT_ROTATION_METRICS_ENABLED="true" \
  -e CERT_ROTATION_LOG_LEVEL="INFO" \
  --restart unless-stopped \
  --health-cmd="curl -f http://localhost:8000/health || exit 1" \
  --health-interval=30s \
  --health-timeout=10s \
  --health-retries=3 \
  cert-rotation
```

### Using UV (Development)

1. **Install dependencies:**
```bash
uv pip install -e .
```

2. **Set environment variables:**
```bash
export CERT_ROTATION_CERT_PATH="/path/to/certs"
export CERT_ROTATION_ACM_CERT_ARNS="arn:aws:acm:us-east-1:123456789012:certificate/12345678-1234-1234-1234-123456789012"
```

3. **Run the service:**
```bash
python -m cert_rotation.main
```

## Configuration

All configuration is done via environment variables with the `CERT_ROTATION_` prefix:

### Required Configuration

| Variable | Description | Example |
|----------|-------------|---------|
| `CERT_ROTATION_CERT_PATH` | Path where certificates are stored | `/app/certs` |
| `CERT_ROTATION_SECRETS_NAMES` | Comma-separated list of Secrets Manager secret names | `my-cert-secret,another-cert` |
| `CERT_ROTATION_TAG_KEY` | Tag key to filter secrets by (alternative to SECRETS_NAMES) | `Environment` |
| `CERT_ROTATION_TAG_VALUE` | Tag value to filter secrets by (alternative to SECRETS_NAMES) | `production` |

### Certificate Discovery Methods

The service supports two methods for discovering certificates in AWS Secrets Manager:

1. **Explicit Secret Names** (traditional method):
   - Use `CERT_ROTATION_SECRETS_NAMES` to specify exact secret names
   - Example: `CERT_ROTATION_SECRETS_NAMES=my-cert-secret,another-cert`

2. **Tag-Based Discovery** (recommended for dynamic environments):
   - Use `CERT_ROTATION_TAG_KEY` and `CERT_ROTATION_TAG_VALUE` to filter secrets by tags
   - The service will automatically discover all secrets with the specified tag
   - Example: `CERT_ROTATION_TAG_KEY=Environment` and `CERT_ROTATION_TAG_VALUE=production`
   - This will fetch all secrets tagged with `Environment=production`

**Note**: If both methods are configured, tag-based discovery takes precedence for automatic synchronization, but explicit secret names can still be accessed via the API.

### Optional Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CERT_ROTATION_HOST` | `0.0.0.0` | Service bind host |
| `CERT_ROTATION_PORT` | `8000` | Service bind port |
| `CERT_ROTATION_LOG_LEVEL` | `INFO` | Logging level |
| `CERT_ROTATION_AWS_REGION` | `us-east-1` | AWS region |
| `CERT_ROTATION_CHECK_INTERVAL_MINUTES` | `60` | Sync interval |
| `CERT_ROTATION_HAPROXY_RELOAD_URL` | `None` | HAProxy HTTP reload endpoint |
| `CERT_ROTATION_HAPROXY_STATS_SOCKET` | `None` | HAProxy stats socket path |
| `CERT_ROTATION_HAPROXY_CONTAINER_NAME` | `None` | HAProxy container name for Docker signal reload |
| `CERT_ROTATION_METRICS_ENABLED` | `true` | Enable Prometheus metrics |

## API Endpoints

### Health Check
```bash
GET /health
```
Returns service health status.

### Prometheus Metrics
```bash
GET /metrics
```
Returns Prometheus-formatted metrics including:
- Certificate expiration days
- Sync operation counters
- HAProxy reload status
- File change events

### Manual Reload
```bash
POST /reload
```
Manually trigger certificate synchronization.

### Service Status
```bash
GET /status
```
Returns detailed service status and statistics.

## Metrics

The service exposes the following Prometheus metrics:

- `cert_expiry_days` - Days until certificate expires
- `cert_expired` - Certificate expiration status (0/1)
- `cert_sync_operations_total` - Total sync operations by status
- `cert_sync_duration_seconds` - Sync operation duration
- `acm_requests_total` - ACM API requests by operation and status
- `haproxy_reload_total` - HAProxy reload attempts by status
- `certificates_managed_total` - Number of managed certificates
- `last_sync_timestamp_seconds` - Last successful sync timestamp
- `cert_file_changes_total` - File system change events

## AWS Secrets Manager Setup

### Certificate Storage Format

Certificates should be stored in AWS Secrets Manager as JSON with the following structure:

```json
{
  "certificate": "-----BEGIN CERTIFICATE-----\nMIIE...\n-----END CERTIFICATE-----",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----",
  "certificate_chain": "-----BEGIN CERTIFICATE-----\nMIIE...\n-----END CERTIFICATE-----",
  "domain_name": "example.com",
  "description": "Certificate for example.com"
}
```

### Creating Secrets

```bash
# Create a certificate secret
aws secretsmanager create-secret \
  --name "my-web-cert" \
  --description "Web server certificate" \
  --secret-string '{
    "certificate": "-----BEGIN CERTIFICATE-----\nYOUR_CERT_HERE\n-----END CERTIFICATE-----",
    "private_key": "-----BEGIN PRIVATE KEY-----\nYOUR_KEY_HERE\n-----END PRIVATE KEY-----",
    "certificate_chain": "-----BEGIN CERTIFICATE-----\nYOUR_CHAIN_HERE\n-----END CERTIFICATE-----",
    "domain_name": "example.com",
    "description": "Production web certificate"
  }'
```

### Updating Certificates

```bash
# Update certificate for renewal
aws secretsmanager update-secret \
  --secret-id "my-web-cert" \
  --secret-string file://updated-cert.json
```

## AWS IAM Permissions

The EC2 instance needs the following IAM permissions for Secrets Manager access:

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
            "Resource": [
                "arn:aws:secretsmanager:us-east-1:123456789012:secret:my-web-cert-*",
                "arn:aws:secretsmanager:us-east-1:123456789012:secret:my-api-cert-*"
            ]
        }
    ]
}
```

### Minimal IAM Policy (All Secrets)

For broader access to all secrets (less secure):

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

## HAProxy Integration

The service supports multiple methods for HAProxy certificate reloads:

1. **HTTP Endpoint**: Configure `CERT_ROTATION_HAPROXY_RELOAD_URL`
2. **Stats Socket**: Configure `CERT_ROTATION_HAPROXY_STATS_SOCKET`
3. **Docker Signal (HUP)**: Configure `CERT_ROTATION_HAPROXY_CONTAINER_NAME`

### Method 1: HTTP Endpoint Reload

Configure HAProxy with an HTTP stats interface that supports reload operations:

```bash
# Environment variable
CERT_ROTATION_HAPROXY_RELOAD_URL="http://haproxy:8404/reload"
```

Example HAProxy configuration:
```
frontend stats
    bind *:8404
    stats enable
    stats uri /stats
    stats refresh 30s
    stats admin if TRUE
```

### Method 2: Stats Socket Reload

Configure HAProxy with a Unix socket for administrative commands:

```bash
# Environment variable
CERT_ROTATION_HAPROXY_STATS_SOCKET="/var/run/haproxy.sock"
```

Example HAProxy configuration:
```
global
    stats socket /var/run/haproxy.sock mode 600 level admin
    stats timeout 30s
```

Docker volume mount example:
```bash
docker run -d \
  --name cert-rotation \
  -v /var/run/haproxy.sock:/var/run/haproxy.sock \
  cert-rotation
```

### Method 3: Docker Signal (HUP) - Recommended for Containers

Send a HUP signal to the HAProxy container via Docker API to trigger a graceful reload:

```bash
# Environment variables
CERT_ROTATION_HAPROXY_CONTAINER_NAME="haproxy"
```

**Requirements:**
- Docker socket access: `-v /var/run/docker.sock:/var/run/docker.sock`
- HAProxy container configured for graceful reload on HUP signal

**Docker Compose Example:**
```yaml
version: '3.8'
services:
  cert-rotation:
    build: .
    volumes:
      - ./certs:/app/certs
      - /var/run/docker.sock:/var/run/docker.sock  # Required for Docker API access
    environment:
      - CERT_ROTATION_HAPROXY_CONTAINER_NAME=haproxy

  haproxy:
    image: haproxy:2.8
    container_name: haproxy  # Must match HAPROXY_CONTAINER_NAME
    volumes:
      - ./certs:/etc/ssl/certs:ro
```

**Docker Run Example:**
```bash
# Run cert-rotation with Docker socket access
docker run -d \
  --name cert-rotation \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /opt/haproxy/certs:/app/certs \
  -e CERT_ROTATION_HAPROXY_CONTAINER_NAME="haproxy" \
  cert-rotation

# Run HAProxy container
docker run -d \
  --name haproxy \
  -p 80:80 -p 443:443 \
  -v /opt/haproxy/certs:/etc/ssl/certs:ro \
  haproxy:2.8
```

**How HUP Signal Works:**
- The service sends a `SIGHUP` to the HAProxy container via Docker API
- HAProxy performs a graceful reload without dropping connections
- New certificates are loaded without service interruption
- This method works reliably across different HAProxy versions

**Security Considerations:**
- Docker socket access grants significant privileges
- Consider using Docker socket proxy in production
- Ensure proper container isolation and security policies

## Development

### Running Tests
```bash
uv pip install -e ".[dev]"
pytest
```

### Code Formatting
```bash
black src/
isort src/
```

### Type Checking
```bash
mypy src/
```

## Troubleshooting

### Common Issues

1. **AWS Credentials**: Ensure EC2 instance has proper IAM role with Secrets Manager permissions
2. **Certificate Path**: Verify path is writable by container user
3. **HAProxy Connection**: Check HAProxy reload endpoint accessibility
4. **Secret Format**: Ensure secrets contain valid JSON with required certificate fields
5. **Secret Names**: Verify secret names in `CERT_ROTATION_SECRETS_NAMES` exist in Secrets Manager
6. **AWS Region**: Ensure `CERT_ROTATION_AWS_REGION` matches where secrets are stored
7. **IAM Permissions**: Verify the service can access the specific secrets (check CloudTrail logs)
8. **Docker Socket Access**: Ensure `/var/run/docker.sock` is mounted when using Docker signal reload
9. **Container Name**: Verify `CERT_ROTATION_HAPROXY_CONTAINER_NAME` matches the actual HAProxy container name
10. **HAProxy HUP Signal**: Ensure HAProxy is configured to handle SIGHUP for graceful reloads

### Logs

Check service logs for detailed error information:
```bash
docker logs cert-rotation
```

## License

MIT License - see LICENSE file for details.
