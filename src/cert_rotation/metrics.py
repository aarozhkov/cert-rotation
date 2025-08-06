"""
Prometheus metrics for certificate rotation service.
"""

import time
from typing import Dict, Any
from prometheus_client import (
    CollectorRegistry, 
    Gauge, 
    Counter, 
    Histogram,
    generate_latest
)

from .config import settings


# Create a custom registry
metrics_registry = CollectorRegistry()

# Certificate expiration metrics
cert_expiry_days = Gauge(
    'cert_expiry_days',
    'Days until certificate expires',
    ['cert_path', 'domain'],
    registry=metrics_registry
)

cert_expired = Gauge(
    'cert_expired',
    'Certificate is expired (1) or not (0)',
    ['cert_path', 'domain'],
    registry=metrics_registry
)

# Service operational metrics
sync_operations_total = Counter(
    'cert_sync_operations_total',
    'Total number of certificate sync operations',
    ['status'],
    registry=metrics_registry
)

sync_duration_seconds = Histogram(
    'cert_sync_duration_seconds',
    'Time spent syncing certificates',
    registry=metrics_registry
)

secrets_requests_total = Counter(
    'secrets_requests_total',
    'Total number of Secrets Manager API requests',
    ['operation', 'status'],
    registry=metrics_registry
)

haproxy_reload_total = Counter(
    'haproxy_reload_total',
    'Total number of HAProxy reload attempts',
    ['status'],
    registry=metrics_registry
)

certificates_managed = Gauge(
    'certificates_managed_total',
    'Total number of certificates being managed',
    registry=metrics_registry
)

last_sync_timestamp = Gauge(
    'last_sync_timestamp_seconds',
    'Timestamp of last successful sync',
    registry=metrics_registry
)

# File system monitoring metrics
file_changes_total = Counter(
    'cert_file_changes_total',
    'Total number of certificate file changes detected',
    ['change_type'],
    registry=metrics_registry
)


class MetricsCollector:
    """Collect and update metrics."""
    
    def __init__(self):
        self.start_time = time.time()
    
    def update_certificate_metrics(self, certificates: Dict[str, Any]):
        """Update certificate-related metrics."""
        # Clear existing metrics
        cert_expiry_days.clear()
        cert_expired.clear()
        
        cert_count = 0
        for cert_path, cert_info in certificates.items():
            cert_count += 1
            
            # Get primary domain for labeling
            primary_domain = cert_info.domain_names[0] if cert_info.domain_names else 'unknown'
            
            # Update expiry metrics
            if cert_info.days_until_expiry is not None:
                cert_expiry_days.labels(
                    cert_path=cert_path,
                    domain=primary_domain
                ).set(cert_info.days_until_expiry)
                
                cert_expired.labels(
                    cert_path=cert_path,
                    domain=primary_domain
                ).set(1 if cert_info.is_expired else 0)
        
        certificates_managed.set(cert_count)
    
    def record_sync_operation(self, success: bool, duration: float = None):
        """Record a sync operation."""
        status = 'success' if success else 'failure'
        sync_operations_total.labels(status=status).inc()
        
        if success:
            last_sync_timestamp.set(time.time())
        
        if duration is not None:
            sync_duration_seconds.observe(duration)
    
    def record_secrets_request(self, operation: str, success: bool):
        """Record a Secrets Manager API request."""
        status = 'success' if success else 'failure'
        secrets_requests_total.labels(operation=operation, status=status).inc()

    # Keep the old method name for backward compatibility during transition
    def record_acm_request(self, operation: str, success: bool):
        """Record a Secrets Manager API request (legacy method name)."""
        self.record_secrets_request(operation, success)
    
    def record_haproxy_reload(self, success: bool):
        """Record a HAProxy reload attempt."""
        status = 'success' if success else 'failure'
        haproxy_reload_total.labels(status=status).inc()
    
    def record_file_change(self, change_type: str):
        """Record a file system change."""
        file_changes_total.labels(change_type=change_type).inc()


# Global metrics collector instance
metrics_collector = MetricsCollector()


def generate_metrics() -> str:
    """Generate Prometheus metrics output."""
    return generate_latest(metrics_registry).decode('utf-8')


def get_metrics_summary() -> Dict[str, Any]:
    """Get a summary of current metrics for status endpoint."""
    return {
        'certificates_managed': certificates_managed._value._value,
        'last_sync_timestamp': last_sync_timestamp._value._value,
        'sync_operations_total': {
            family.name: {
                sample.labels['status']: sample.value 
                for sample in family.samples
            }
            for family in sync_operations_total.collect()
        },
        'service_uptime_seconds': time.time() - metrics_collector.start_time
    }
