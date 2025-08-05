"""
AWS Certificate Manager client for certificate operations.
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from .config import settings


logger = logging.getLogger(__name__)


class ACMClient:
    """AWS Certificate Manager client."""
    
    def __init__(self):
        """Initialize ACM client."""
        try:
            self.client = boto3.client('acm', region_name=settings.aws_region)
            logger.info(f"Initialized ACM client for region: {settings.aws_region}")
        except NoCredentialsError:
            logger.error("AWS credentials not found. Ensure EC2 instance has proper IAM role.")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize ACM client: {e}")
            raise
    
    async def get_certificate_details(self, cert_arn: str) -> Optional[Dict]:
        """Get certificate details from ACM."""
        try:
            response = self.client.describe_certificate(CertificateArn=cert_arn)
            return response.get('Certificate')
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ResourceNotFoundException':
                logger.warning(f"Certificate not found: {cert_arn}")
                return None
            else:
                logger.error(f"Error getting certificate details for {cert_arn}: {e}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error getting certificate details: {e}")
            raise
    
    async def export_certificate(self, cert_arn: str) -> Optional[Tuple[str, str, str]]:
        """
        Export certificate from ACM.
        
        Returns:
            Tuple of (certificate, private_key, certificate_chain) or None if failed
        """
        try:
            response = self.client.export_certificate(CertificateArn=cert_arn)
            
            certificate = response.get('Certificate', '')
            private_key = response.get('PrivateKey', '')
            certificate_chain = response.get('CertificateChain', '')
            
            if not certificate or not private_key:
                logger.error(f"Incomplete certificate data for {cert_arn}")
                return None
            
            logger.info(f"Successfully exported certificate: {cert_arn}")
            return certificate, private_key, certificate_chain
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ResourceNotFoundException':
                logger.warning(f"Certificate not found for export: {cert_arn}")
                return None
            elif error_code == 'InvalidStateException':
                logger.warning(f"Certificate not in exportable state: {cert_arn}")
                return None
            else:
                logger.error(f"Error exporting certificate {cert_arn}: {e}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error exporting certificate: {e}")
            raise
    
    async def list_certificates(self) -> List[Dict]:
        """List all certificates in ACM."""
        try:
            certificates = []
            paginator = self.client.get_paginator('list_certificates')
            
            for page in paginator.paginate():
                certificates.extend(page.get('CertificateSummaryList', []))
            
            logger.debug(f"Found {len(certificates)} certificates in ACM")
            return certificates
            
        except Exception as e:
            logger.error(f"Error listing certificates: {e}")
            raise
    
    async def get_monitored_certificates(self) -> Dict[str, Dict]:
        """Get details for all monitored certificates."""
        monitored_certs = {}
        
        for cert_arn in settings.acm_cert_arns:
            cert_details = await self.get_certificate_details(cert_arn)
            if cert_details:
                monitored_certs[cert_arn] = cert_details
            else:
                logger.warning(f"Could not get details for monitored certificate: {cert_arn}")
        
        return monitored_certs
    
    def get_certificate_name(self, cert_details: Dict) -> str:
        """Extract a suitable filename from certificate details."""
        # Try to get domain name from certificate
        domain_name = cert_details.get('DomainName', '')
        if domain_name:
            # Replace wildcards and special characters
            safe_name = domain_name.replace('*', 'wildcard').replace('.', '_')
            return safe_name
        
        # Fallback to subject alternative names
        san_list = cert_details.get('SubjectAlternativeNames', [])
        if san_list:
            primary_san = san_list[0].replace('*', 'wildcard').replace('.', '_')
            return primary_san
        
        # Last resort: use part of ARN
        cert_arn = cert_details.get('CertificateArn', '')
        if cert_arn:
            return cert_arn.split('/')[-1][:16]
        
        return 'unknown_cert'
