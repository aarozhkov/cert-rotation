"""
Background scheduler for certificate synchronization tasks.
"""

import asyncio
import logging
import time
from typing import Dict, Any, Set
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .config import settings
from .secrets_client import SecretsManagerClient
from .cert_monitor import CertificateMonitor
from .haproxy_client import haproxy_client
from .metrics import metrics_collector


logger = logging.getLogger(__name__)


class CertificateScheduler:
    """Background scheduler for certificate operations."""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.secrets_client = SecretsManagerClient()
        self.cert_monitor = CertificateMonitor()
        self.is_running = False
        self.sync_in_progress = False
        self.last_sync_time = None
        self.sync_errors = []
        self.event_loop = None  # Store reference to the main event loop
    
    async def start(self):
        """Start the scheduler and monitoring."""
        if self.is_running:
            return

        logger.info("Starting certificate scheduler")

        # Store reference to the current event loop
        self.event_loop = asyncio.get_running_loop()

        # Start certificate monitoring
        self.cert_monitor.start_monitoring()
        self.cert_monitor.add_change_callback(self._on_certificate_file_changed)
        
        # Initial certificate scan
        await self._initial_scan()
        
        # Schedule periodic sync
        self.scheduler.add_job(
            self.sync_certificates,
            trigger=IntervalTrigger(minutes=settings.check_interval_minutes),
            id='cert_sync',
            name='Certificate Sync',
            max_instances=1,
            coalesce=True
        )
        
        # Start scheduler
        self.scheduler.start()
        self.is_running = True
        
        logger.info(f"Certificate scheduler started with {settings.check_interval_minutes}min interval")
    
    async def stop(self):
        """Stop the scheduler and monitoring."""
        if not self.is_running:
            return

        logger.info("Stopping certificate scheduler")

        # Stop scheduler
        self.scheduler.shutdown(wait=True)

        # Stop monitoring
        self.cert_monitor.stop_monitoring()

        self.is_running = False
        self.event_loop = None  # Clear event loop reference
        logger.info("Certificate scheduler stopped")
    
    async def _initial_scan(self):
        """Perform initial certificate scan and sync."""
        logger.info("Performing initial certificate scan")
        
        # Scan local certificates
        self.cert_monitor.scan_certificates()
        
        # Update metrics
        metrics_collector.update_certificate_metrics(self.cert_monitor.certificates)
        
        # Perform initial sync
        await self.sync_certificates()
    
    async def sync_certificates(self):
        """Synchronize certificates from ACM."""
        if self.sync_in_progress:
            logger.warning("Certificate sync already in progress, skipping")
            return
        
        self.sync_in_progress = True
        start_time = time.time()
        success = False
        
        try:
            logger.info("Starting certificate synchronization")

            # Get monitored certificates from Secrets Manager
            secrets_data = await self.secrets_client.get_monitored_secrets()
            metrics_collector.record_acm_request('get_monitored_secrets', True)

            certificates_updated = False

            for secret_name, secret_data in secrets_data.items():
                try:
                    updated = await self._sync_single_certificate(secret_name, secret_data)
                    if updated:
                        certificates_updated = True
                except Exception as e:
                    logger.error(f"Error syncing certificate from secret {secret_name}: {e}")
                    self.sync_errors.append(f"Sync error for {secret_name}: {str(e)}")
            
            # Rescan local certificates after sync
            self.cert_monitor.scan_certificates()
            
            # Update metrics
            metrics_collector.update_certificate_metrics(self.cert_monitor.certificates)
            
            # Reload HAProxy if certificates were updated
            if certificates_updated:
                logger.info("Certificates updated, reloading HAProxy")
                await haproxy_client.reload_certificates()
            
            success = True
            self.last_sync_time = datetime.now()
            logger.info("Certificate synchronization completed successfully")
            
        except Exception as e:
            logger.error(f"Certificate synchronization failed: {e}")
            self.sync_errors.append(f"Sync failed: {str(e)}")
            metrics_collector.record_acm_request('sync_certificates', False)
        
        finally:
            duration = time.time() - start_time
            metrics_collector.record_sync_operation(success, duration)
            self.sync_in_progress = False
    
    async def _sync_single_certificate(self, secret_name: str, secret_data: Dict) -> bool:
        """
        Sync a single certificate from Secrets Manager.

        Returns:
            True if certificate was updated, False otherwise
        """
        cert_name = self.secrets_client.get_certificate_name_from_secret(secret_data)

        # Check if we need to download this certificate
        needs_download = await self._certificate_needs_update(secret_name, secret_data, cert_name)

        if not needs_download:
            logger.debug(f"Certificate {cert_name} is up to date")
            return False

        # Extract certificate data from secret
        logger.info(f"Downloading certificate {cert_name} from Secrets Manager")
        cert_data = await self.secrets_client.extract_certificate_data(secret_data)

        if not cert_data:
            logger.warning(f"Could not extract certificate data from secret {secret_name}")
            metrics_collector.record_acm_request('extract_certificate', False)
            return False

        metrics_collector.record_acm_request('extract_certificate', True)

        certificate, private_key, certificate_chain = cert_data

        # Save certificate to filesystem
        try:
            self.cert_monitor.save_certificate(
                cert_name,
                certificate,
                private_key,
                certificate_chain
            )
            logger.info(f"Successfully saved certificate {cert_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to save certificate {cert_name}: {e}")
            return False
    
    async def _certificate_needs_update(self, secret_name: str, secret_data: Dict, cert_name: str) -> bool:
        """Check if a certificate needs to be downloaded/updated."""

        # Check if certificate file exists locally
        cert_file_path = self.cert_monitor.cert_path / f"{cert_name}.pem"

        if not cert_file_path.exists():
            logger.info(f"Certificate {cert_name} not found locally, will download")
            return True

        # Get local certificate info
        local_cert = self.cert_monitor.certificates.get(str(cert_file_path))

        if not local_cert:
            logger.info(f"Could not parse local certificate {cert_name}, will re-download")
            return True

        # Compare based on secret metadata (version changes)
        metadata = secret_data.get('_metadata', {})
        last_changed = metadata.get('last_changed_date')

        if last_changed:
            # If secret was changed recently, update the certificate
            # This is a simple approach - you could store last sync timestamps for more precision
            logger.info(f"Secret {secret_name} was recently changed, will update certificate")
            return True

        # For now, always check if the certificate content differs
        # Extract certificate from secret and compare with local
        try:
            cert_data = await self.secrets_client.extract_certificate_data(secret_data)
            if cert_data:
                secret_cert, _, _ = cert_data
                # Simple comparison - you could parse and compare serial numbers
                if secret_cert.strip() != local_cert.cert_data.strip():
                    logger.info(f"Certificate {cert_name} content changed, will update")
                    return True
        except Exception as e:
            logger.warning(f"Could not compare certificate content for {cert_name}: {e}")
            return True  # When in doubt, update

        return False
    
    def _on_certificate_file_changed(self, file_path: str):
        """Handle certificate file changes."""
        logger.info(f"Certificate file changed: {file_path}")
        metrics_collector.record_file_change('modified')

        # Schedule HAProxy reload using the stored event loop
        if self.is_running and self.event_loop and not self.event_loop.is_closed():
            try:
                # Schedule the coroutine in the main event loop from this thread
                asyncio.run_coroutine_threadsafe(
                    self._handle_certificate_change(),
                    self.event_loop
                )
            except Exception as e:
                logger.error(f"Error scheduling certificate change handler: {e}")
        else:
            logger.warning("Scheduler not running or event loop not available, cannot handle certificate change")
    
    async def _handle_certificate_change(self):
        """Handle certificate file changes by reloading HAProxy."""
        try:
            await haproxy_client.reload_certificates()
        except Exception as e:
            logger.error(f"Error handling certificate change: {e}")
    
    async def get_status(self) -> Dict[str, Any]:
        """Get scheduler status information."""
        return {
            'is_running': self.is_running,
            'sync_in_progress': self.sync_in_progress,
            'last_sync_time': self.last_sync_time.isoformat() if self.last_sync_time else None,
            'certificates_count': len(self.cert_monitor.certificates),
            'monitored_secrets': settings.secrets_names_list,
            'check_interval_minutes': settings.check_interval_minutes,
            'recent_errors': self.sync_errors[-5:],  # Last 5 errors
            'next_sync': self._get_next_sync_time()
        }
    
    def _get_next_sync_time(self) -> str:
        """Get next scheduled sync time."""
        job = self.scheduler.get_job('cert_sync')
        if job and job.next_run_time:
            return job.next_run_time.isoformat()
        return "Not scheduled"
