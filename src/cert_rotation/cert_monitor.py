"""
Certificate monitoring and file system operations.
"""

import os
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .config import settings


logger = logging.getLogger(__name__)


class CertificateInfo:
    """Container for certificate information."""
    
    def __init__(self, path: str, cert_data: str, key_data: str = None):
        self.path = path
        self.cert_data = cert_data
        self.key_data = key_data
        self.expiration_date = None
        self.domain_names = []
        self.serial_number = None
        
        self._parse_certificate()
    
    def _parse_certificate(self):
        """Parse certificate to extract metadata."""
        try:
            cert = x509.load_pem_x509_certificate(
                self.cert_data.encode(), 
                default_backend()
            )
            
            self.expiration_date = cert.not_valid_after.replace(tzinfo=timezone.utc)
            self.serial_number = str(cert.serial_number)
            
            # Extract domain names
            try:
                # Get common name
                for attribute in cert.subject:
                    if attribute.oid == x509.NameOID.COMMON_NAME:
                        self.domain_names.append(attribute.value)
                        break
            except Exception:
                pass
            
            # Get SAN (Subject Alternative Names)
            try:
                san_ext = cert.extensions.get_extension_for_oid(
                    x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
                )
                for name in san_ext.value:
                    if isinstance(name, x509.DNSName):
                        self.domain_names.append(name.value)
            except x509.ExtensionNotFound:
                pass
            
            # Remove duplicates
            self.domain_names = list(set(self.domain_names))
            
        except Exception as e:
            logger.error(f"Error parsing certificate {self.path}: {e}")
    
    @property
    def days_until_expiry(self) -> Optional[int]:
        """Calculate days until certificate expires."""
        if not self.expiration_date:
            return None
        
        now = datetime.now(timezone.utc)
        delta = self.expiration_date - now
        return delta.days
    
    @property
    def is_expired(self) -> bool:
        """Check if certificate is expired."""
        days = self.days_until_expiry
        return days is not None and days < 0


class CertificateFileHandler(FileSystemEventHandler):
    """File system event handler for certificate changes."""
    
    def __init__(self, monitor: 'CertificateMonitor'):
        self.monitor = monitor
    
    def on_modified(self, event):
        """Handle file modification events."""
        if not event.is_directory and self._is_cert_file(event.src_path):
            logger.info(f"Certificate file modified: {event.src_path}")
            self.monitor.on_certificate_changed(event.src_path)
    
    def on_created(self, event):
        """Handle file creation events."""
        if not event.is_directory and self._is_cert_file(event.src_path):
            logger.info(f"Certificate file created: {event.src_path}")
            self.monitor.on_certificate_changed(event.src_path)
    
    def _is_cert_file(self, path: str) -> bool:
        """Check if file is a certificate file."""
        return path.endswith(('.pem', '.crt', '.cert'))


class CertificateMonitor:
    """Monitor local certificate files and manage certificate operations."""
    
    def __init__(self):
        self.cert_path = Path(settings.cert_path)
        self.certificates: Dict[str, CertificateInfo] = {}
        self.observer = None
        self.change_callbacks = []
    
    def start_monitoring(self):
        """Start file system monitoring."""
        if self.observer:
            return
        
        self.observer = Observer()
        handler = CertificateFileHandler(self)
        self.observer.schedule(handler, str(self.cert_path), recursive=True)
        self.observer.start()
        logger.info(f"Started monitoring certificate directory: {self.cert_path}")
    
    def stop_monitoring(self):
        """Stop file system monitoring."""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
            logger.info("Stopped certificate monitoring")
    
    def add_change_callback(self, callback):
        """Add callback for certificate changes."""
        self.change_callbacks.append(callback)
    
    def on_certificate_changed(self, file_path: str):
        """Handle certificate file changes."""
        # Reload certificates
        self.scan_certificates()
        
        # Notify callbacks
        for callback in self.change_callbacks:
            try:
                callback(file_path)
            except Exception as e:
                logger.error(f"Error in certificate change callback: {e}")
    
    def scan_certificates(self) -> Dict[str, CertificateInfo]:
        """Scan certificate directory and load all certificates."""
        self.certificates.clear()
        
        if not self.cert_path.exists():
            logger.warning(f"Certificate path does not exist: {self.cert_path}")
            return self.certificates
        
        for cert_file in self.cert_path.glob("**/*.pem"):
            try:
                self._load_certificate_file(cert_file)
            except Exception as e:
                logger.error(f"Error loading certificate {cert_file}: {e}")
        
        logger.info(f"Loaded {len(self.certificates)} certificates")
        return self.certificates
    
    def _load_certificate_file(self, cert_file: Path):
        """Load a single certificate file."""
        try:
            with open(cert_file, 'r') as f:
                content = f.read()
            
            # Try to find corresponding key file
            key_file = cert_file.with_suffix('.key')
            key_data = None
            
            if key_file.exists():
                with open(key_file, 'r') as f:
                    key_data = f.read()
            
            cert_info = CertificateInfo(str(cert_file), content, key_data)
            self.certificates[str(cert_file)] = cert_info
            
        except Exception as e:
            logger.error(f"Error loading certificate file {cert_file}: {e}")
    
    def save_certificate(self, name: str, cert_data: str, key_data: str, 
                        chain_data: str = None) -> str:
        """Save certificate and key to filesystem."""
        cert_file = self.cert_path / f"{name}.pem"
        key_file = self.cert_path / f"{name}.key"
        
        try:
            # Write certificate (with chain if provided)
            with open(cert_file, 'w') as f:
                f.write(cert_data)
                if chain_data:
                    f.write('\n')
                    f.write(chain_data)
            
            # Write private key
            with open(key_file, 'w') as f:
                f.write(key_data)
            
            # Set appropriate permissions
            os.chmod(cert_file, 0o644)
            os.chmod(key_file, 0o600)
            
            logger.info(f"Saved certificate: {cert_file}")
            return str(cert_file)
            
        except Exception as e:
            logger.error(f"Error saving certificate {name}: {e}")
            raise
    
    def get_certificate_by_domain(self, domain: str) -> Optional[CertificateInfo]:
        """Find certificate by domain name."""
        for cert_info in self.certificates.values():
            if domain in cert_info.domain_names:
                return cert_info
        return None
    
    def get_expiring_certificates(self, days_threshold: int = 30) -> List[CertificateInfo]:
        """Get certificates expiring within threshold days."""
        expiring = []
        for cert_info in self.certificates.values():
            days_left = cert_info.days_until_expiry
            if days_left is not None and days_left <= days_threshold:
                expiring.append(cert_info)
        return expiring
