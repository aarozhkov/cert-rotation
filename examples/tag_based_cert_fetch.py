#!/usr/bin/env python3
"""
Example script demonstrating how to fetch certificates by tag key/value pair.

This script shows how to use the new tag-based filtering functionality
to retrieve certificates from AWS Secrets Manager based on tags.
"""

import asyncio
import os
import sys
import logging
from pathlib import Path

# Add the src directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cert_rotation.secrets_client import SecretsManagerClient
from cert_rotation.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Main function to demonstrate tag-based certificate fetching."""
    
    # Check if tag environment variables are set
    if not settings.tag_key or not settings.tag_value:
        logger.error("Tag key and value must be set via environment variables:")
        logger.error("  CERT_ROTATION_TAG_KEY=<your_tag_key>")
        logger.error("  CERT_ROTATION_TAG_VALUE=<your_tag_value>")
        logger.error("")
        logger.error("Example:")
        logger.error("  export CERT_ROTATION_TAG_KEY=Environment")
        logger.error("  export CERT_ROTATION_TAG_VALUE=production")
        return 1
    
    logger.info(f"Fetching certificates with tag {settings.tag_key}={settings.tag_value}")
    
    try:
        # Initialize the secrets client
        client = SecretsManagerClient()
        
        # Method 1: Use environment variables (recommended)
        logger.info("Method 1: Using environment variables")
        secrets_by_env_tag = await client.get_secrets_by_env_tag()
        
        logger.info(f"Found {len(secrets_by_env_tag)} secrets using environment tag configuration")
        for secret_name, secret_data in secrets_by_env_tag.items():
            logger.info(f"  - {secret_name}")
            # Print some metadata (without sensitive data)
            metadata = secret_data.get('_metadata', {})
            if 'tags' in metadata:
                tags_str = ', '.join([f"{tag['Key']}={tag['Value']}" for tag in metadata['tags']])
                logger.info(f"    Tags: {tags_str}")
        
        # Method 2: Direct tag specification
        logger.info("\nMethod 2: Direct tag specification")
        secrets_by_direct_tag = await client.get_secrets_by_tag(
            tag_key="Environment", 
            tag_value="production"
        )
        
        logger.info(f"Found {len(secrets_by_direct_tag)} secrets with Environment=production")
        for secret_name in secrets_by_direct_tag.keys():
            logger.info(f"  - {secret_name}")
        
        # Method 3: List all secrets and show their tags
        logger.info("\nMethod 3: List all secrets with tags for reference")
        all_secrets = await client.list_secrets(include_tags=True)
        
        logger.info(f"Total secrets in Secrets Manager: {len(all_secrets)}")
        for secret in all_secrets:
            secret_name = secret.get('Name', 'Unknown')
            tags = secret.get('Tags', [])
            if tags:
                tags_str = ', '.join([f"{tag['Key']}={tag['Value']}" for tag in tags])
                logger.info(f"  - {secret_name}: {tags_str}")
            else:
                logger.info(f"  - {secret_name}: No tags")
        
        return 0
        
    except Exception as e:
        logger.error(f"Error fetching certificates: {e}")
        return 1


if __name__ == "__main__":
    # Set required environment variables if not already set
    if not os.getenv('CERT_ROTATION_CERT_PATH'):
        os.environ['CERT_ROTATION_CERT_PATH'] = '/tmp/certs'
    
    # Run the async main function
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
