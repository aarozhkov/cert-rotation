"""
AWS Secrets Manager client for certificate operations.
"""

import json
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from .config import settings


logger = logging.getLogger(__name__)


class SecretsManagerClient:
    """AWS Secrets Manager client for certificate operations."""
    
    def __init__(self):
        """Initialize Secrets Manager client."""
        try:
            self.client = boto3.client('secretsmanager', region_name=settings.aws_region)
            logger.info(f"Initialized Secrets Manager client for region: {settings.aws_region}")
        except NoCredentialsError:
            logger.error("AWS credentials not found. Ensure EC2 instance has proper IAM role.")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize Secrets Manager client: {e}")
            raise
    
    async def get_secret_value(self, secret_name: str) -> Optional[Dict]:
        """Get secret value from Secrets Manager."""
        try:
            response = self.client.get_secret_value(SecretId=secret_name)
            
            # Parse the secret string as JSON
            secret_string = response.get('SecretString')
            if not secret_string:
                logger.error(f"Secret {secret_name} has no SecretString")
                return None
            
            try:
                secret_data = json.loads(secret_string)
                # Add metadata from the response
                secret_data['_metadata'] = {
                    'arn': response.get('ARN'),
                    'name': response.get('Name'),
                    'version_id': response.get('VersionId'),
                    'version_stages': response.get('VersionStages', []),
                    'created_date': response.get('CreatedDate'),
                    'last_accessed_date': response.get('LastAccessedDate'),
                    'last_changed_date': response.get('LastChangedDate')
                }
                return secret_data
            except json.JSONDecodeError as e:
                logger.error(f"Secret {secret_name} contains invalid JSON: {e}")
                return None
                
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ResourceNotFoundException':
                logger.warning(f"Secret not found: {secret_name}")
                return None
            elif error_code == 'InvalidRequestException':
                logger.error(f"Invalid request for secret {secret_name}: {e}")
                return None
            elif error_code == 'InvalidParameterException':
                logger.error(f"Invalid parameter for secret {secret_name}: {e}")
                return None
            else:
                logger.error(f"Error getting secret {secret_name}: {e}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error getting secret {secret_name}: {e}")
            raise
    
    async def list_secrets(self, include_tags: bool = False) -> List[Dict]:
        """List all secrets in Secrets Manager."""
        try:
            secrets = []
            paginator = self.client.get_paginator('list_secrets')
            
            for page in paginator.paginate():
                secret_list = page.get('SecretList', [])
                
                # Add tags if requested
                if include_tags:
                    for secret in secret_list:
                        secret_arn = secret.get('ARN')
                        if secret_arn:
                            try:
                                tags_response = self.client.describe_secret(SecretId=secret_arn)
                                secret['Tags'] = tags_response.get('Tags', [])
                            except ClientError as e:
                                logger.warning(f"Could not fetch tags for secret {secret_arn}: {e}")
                                secret['Tags'] = []
                
                secrets.extend(secret_list)
            
            logger.debug(f"Found {len(secrets)} secrets in Secrets Manager")
            return secrets
            
        except Exception as e:
            logger.error(f"Error listing secrets: {e}")
            raise
    
    async def get_monitored_secrets(self, include_tags: bool = False) -> Dict[str, Dict]:
        """Get details for all monitored secrets."""
        monitored_secrets = {}
        
        for secret_name in settings.secrets_names_list:
            secret_data = await self.get_secret_value(secret_name)
            if secret_data:
                # Add tags if requested
                if include_tags:
                    try:
                        tags_response = self.client.describe_secret(SecretId=secret_name)
                        secret_data['_metadata']['tags'] = tags_response.get('Tags', [])
                    except ClientError as e:
                        logger.warning(f"Could not fetch tags for secret {secret_name}: {e}")
                        secret_data['_metadata']['tags'] = []
                
                monitored_secrets[secret_name] = secret_data
            else:
                logger.warning(f"Could not get data for monitored secret: {secret_name}")
        
        return monitored_secrets

    async def get_monitored_secrets_metadata(self, include_tags: bool = False) -> Dict[str, Dict]:
        """Get metadata for all monitored secrets without sensitive data."""
        monitored_secrets = {}

        for secret_name in settings.secrets_names_list:
            try:
                # Get basic secret info without the actual secret value
                response = self.client.describe_secret(SecretId=secret_name)

                metadata = {
                    'arn': response.get('ARN'),
                    'name': response.get('Name'),
                    'description': response.get('Description'),
                    'created_date': response.get('CreatedDate'),
                    'last_accessed_date': response.get('LastAccessedDate'),
                    'last_changed_date': response.get('LastChangedDate'),
                    'last_rotated_date': response.get('LastRotatedDate'),
                    'version_ids_to_stages': response.get('VersionIdsToStages', {}),
                    'owning_service': response.get('OwningService'),
                    'primary_region': response.get('PrimaryRegion'),
                    'replication_status': response.get('ReplicationStatus', [])
                }

                if include_tags:
                    metadata['tags'] = response.get('Tags', [])

                monitored_secrets[secret_name] = {'_metadata': metadata}

            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code == 'ResourceNotFoundException':
                    logger.warning(f"Secret not found: {secret_name}")
                else:
                    logger.error(f"Error getting metadata for secret {secret_name}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error getting metadata for secret {secret_name}: {e}")

        return monitored_secrets

    async def get_secrets_by_tag(self, tag_key: str, tag_value: str, include_tags: bool = True) -> Dict[str, Dict]:
        """
        Get all secrets that have a specific tag key/value pair.

        Args:
            tag_key: The tag key to filter by
            tag_value: The tag value to filter by
            include_tags: Whether to include tags in the response

        Returns:
            Dictionary of secret names to secret data
        """
        try:
            secrets_with_tag = {}

            # First, list all secrets with tags
            all_secrets = await self.list_secrets(include_tags=True)

            # Filter secrets by tag
            for secret in all_secrets:
                secret_name = secret.get('Name')
                secret_tags = secret.get('Tags', [])

                # Check if the secret has the required tag
                has_matching_tag = False
                for tag in secret_tags:
                    if tag.get('Key') == tag_key and tag.get('Value') == tag_value:
                        has_matching_tag = True
                        break

                if has_matching_tag and secret_name:
                    logger.debug(f"Found secret with matching tag: {secret_name}")

                    # Get the full secret data
                    secret_data = await self.get_secret_value(secret_name)
                    if secret_data:
                        # Add tags to metadata if requested
                        if include_tags:
                            secret_data['_metadata']['tags'] = secret_tags

                        secrets_with_tag[secret_name] = secret_data
                    else:
                        logger.warning(f"Could not get data for secret with matching tag: {secret_name}")

            logger.info(f"Found {len(secrets_with_tag)} secrets with tag {tag_key}={tag_value}")
            return secrets_with_tag

        except Exception as e:
            logger.error(f"Error getting secrets by tag {tag_key}={tag_value}: {e}")
            raise

    async def get_secrets_by_env_tag(self, include_tags: bool = True) -> Dict[str, Dict]:
        """
        Get all secrets that match the tag key/value pair from environment variables.

        Args:
            include_tags: Whether to include tags in the response

        Returns:
            Dictionary of secret names to secret data, or empty dict if tag env vars not set
        """
        if not settings.tag_key or not settings.tag_value:
            logger.warning("Tag key or tag value not configured in environment variables")
            return {}

        logger.info(f"Fetching secrets with tag {settings.tag_key}={settings.tag_value}")
        return await self.get_secrets_by_tag(settings.tag_key, settings.tag_value, include_tags)
    
    def get_certificate_name_from_secret(self, secret_data: Dict) -> str:
        """Extract a suitable filename from secret data."""
        # Try to get name from metadata
        metadata = secret_data.get('_metadata', {})
        secret_name = metadata.get('name', '')
        
        if secret_name:
            # Clean up the secret name for use as filename
            safe_name = secret_name.replace('/', '_').replace(':', '_')
            return safe_name
        
        # Try to get domain name from certificate data
        domain_name = secret_data.get('domain_name', '')
        if domain_name:
            safe_name = domain_name.replace('*', 'wildcard').replace('.', '_')
            return safe_name
        
        # Fallback to a generic name
        return 'unknown_cert'
    
    def validate_certificate_secret(self, secret_data: Dict) -> bool:
        """Validate that secret contains required certificate data."""
        required_fields = ['certificate', 'private_key']
        
        for field in required_fields:
            if field not in secret_data:
                logger.error(f"Secret missing required field: {field}")
                return False
            
            if not secret_data[field]:
                logger.error(f"Secret field {field} is empty")
                return False
        
        return True
    
    async def extract_certificate_data(self, secret_data: Dict) -> Optional[Tuple[str, str, str]]:
        """
        Extract certificate data from secret.
        
        Expected secret format:
        {
            "certificate": "-----BEGIN CERTIFICATE-----...",
            "private_key": "-----BEGIN PRIVATE KEY-----...",
            "certificate_chain": "-----BEGIN CERTIFICATE-----..." (optional),
            "domain_name": "example.com" (optional),
            "description": "Certificate description" (optional)
        }
        
        Returns:
            Tuple of (certificate, private_key, certificate_chain) or None if invalid
        """
        if not self.validate_certificate_secret(secret_data):
            return None
        
        certificate = secret_data.get('certificate', '')
        private_key = secret_data.get('private_key', '')
        certificate_chain = secret_data.get('certificate_chain', '')
        
        return certificate, private_key, certificate_chain
