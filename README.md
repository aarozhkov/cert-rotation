# Certificate Rotation Service

A Python service for synchronizing AWS Certificate Manager (ACM) certificates with local filesystem for HAProxy certificate management on EC2 instances.

## Features

- **FastAPI HTTP Service**: RESTful API with health checks and manual triggers
- **Prometheus Metrics**: Certificate expiration monitoring and operational metrics
- **AWS ACM Integration**: Automatic certificate download and renewal detection
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

2. **Run with environment variables:**
```bash
docker run -d \
  --name cert-rotation \
  -p 8000:8000 \
  -v /path/to/certs:/app/certs \
  -e CERT_ROTATION_ACM_CERT_ARNS="arn:aws:acm:us-east-1:123456789012:certificate/12345678-1234-1234-1234-123456789012" \
  -e CERT_ROTATION_HAPROXY_RELOAD_URL="http://haproxy:8404/reload" \
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
| `CERT_ROTATION_ACM_CERT_ARNS` | Comma-separated list of ACM certificate ARNs | `arn:aws:acm:...` |

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

## AWS IAM Permissions

The EC2 instance needs the following IAM permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "acm:DescribeCertificate",
                "acm:ExportCertificate",
                "acm:ListCertificates"
            ],
            "Resource": "*"
        }
    ]
}
```

## HAProxy Integration

The service supports two methods for HAProxy certificate reloads:

1. **HTTP Endpoint**: Configure `CERT_ROTATION_HAPROXY_RELOAD_URL`
2. **Stats Socket**: Configure `CERT_ROTATION_HAPROXY_STATS_SOCKET`

Example HAProxy configuration for HTTP reload:
```
stats socket /var/run/haproxy.sock mode 600 level admin
stats bind-process all
```

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

1. **AWS Credentials**: Ensure EC2 instance has proper IAM role
2. **Certificate Path**: Verify path is writable by container user
3. **HAProxy Connection**: Check HAProxy reload endpoint accessibility
4. **Certificate Format**: Ensure ACM certificates are exportable

### Logs

Check service logs for detailed error information:
```bash
docker logs cert-rotation
```

## License

MIT License - see LICENSE file for details.
