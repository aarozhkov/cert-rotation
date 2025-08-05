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
    
    async def get_certificate_details(self, cert_arn: str, include_tags: bool = False) -> Optional[Dict]:
        """Get certificate details from ACM."""
        try:
            response = self.client.describe_certificate(CertificateArn=cert_arn)
            cert_details = response.get('Certificate')

            # Add tags if requested
            if include_tags and cert_details:
                try:
                    tags_response = self.client.list_tags_for_certificate(CertificateArn=cert_arn)
                    cert_details['Tags'] = tags_response.get('Tags', [])
                except ClientError as e:
                    logger.warning(f"Could not fetch tags for certificate {cert_arn}: {e}")
                    cert_details['Tags'] = []

            return cert_details
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
            # First, try without passphrase (for AWS-issued certificates)
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
            elif error_code == 'ValidationException' and 'Passphrase' in str(e):
                # This is an imported certificate that requires a passphrase
                logger.warning(f"Certificate {cert_arn} requires passphrase for export (imported certificate)")
                return await self._try_export_with_passphrase(cert_arn)
            else:
                logger.error(f"Error exporting certificate {cert_arn}: {e}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error exporting certificate: {e}")
            raise

    async def _try_export_with_passphrase(self, cert_arn: str) -> Optional[Tuple[str, str, str]]:
        """
        Try to export certificate with configured or common passphrases.

        For imported certificates that require a passphrase.
        """
        # Passphrases to try
        passphrases_to_try = []

        # First try configured passphrase if available
        if settings.acm_passphrase:
            passphrases_to_try.append(settings.acm_passphrase)

        # Then try empty passphrase
        passphrases_to_try.append("")

        for passphrase in passphrases_to_try:
            try:
                logger.debug(f"Trying to export {cert_arn} with passphrase")
                response = self.client.export_certificate(
                    CertificateArn=cert_arn,
                    Passphrase=passphrase
                )

                certificate = response.get('Certificate', '')
                private_key = response.get('PrivateKey', '')
                certificate_chain = response.get('CertificateChain', '')

                if certificate and private_key:
                    logger.info(f"Successfully exported certificate with passphrase: {cert_arn}")
                    return certificate, private_key, certificate_chain

            except ClientError:
                # Continue trying other passphrases
                continue

        logger.error(f"Could not export certificate {cert_arn} - passphrase required but not configured")
        return None
    
    async def list_certificates(self, include_tags: bool = False) -> List[Dict]:
        """List all certificates in ACM."""
        try:
            certificates = []
            paginator = self.client.get_paginator('list_certificates')

            for page in paginator.paginate():
                cert_list = page.get('CertificateSummaryList', [])

                # Add tags if requested
                if include_tags:
                    for cert in cert_list:
                        cert_arn = cert.get('CertificateArn')
                        if cert_arn:
                            try:
                                tags_response = self.client.list_tags_for_certificate(CertificateArn=cert_arn)
                                cert['Tags'] = tags_response.get('Tags', [])
                            except ClientError as e:
                                logger.warning(f"Could not fetch tags for certificate {cert_arn}: {e}")
                                cert['Tags'] = []

                certificates.extend(cert_list)

            logger.debug(f"Found {len(certificates)} certificates in ACM")
            return certificates

        except Exception as e:
            logger.error(f"Error listing certificates: {e}")
            raise
    
    async def get_monitored_certificates(self, include_tags: bool = False) -> Dict[str, Dict]:
        """Get details for all monitored certificates."""
        monitored_certs = {}

        for cert_arn in settings.acm_cert_arns_list:
            cert_details = await self.get_certificate_details(cert_arn, include_tags=include_tags)
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
