"""
Tests for the SecretsManagerClient tag-based filtering functionality.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from cert_rotation.secrets_client import SecretsManagerClient
from cert_rotation.config import Settings


@pytest.fixture
def mock_settings():
    """Mock settings with tag configuration."""
    with patch('cert_rotation.secrets_client.settings') as mock_settings:
        mock_settings.aws_region = 'us-east-1'
        mock_settings.tag_key = 'Environment'
        mock_settings.tag_value = 'production'
        yield mock_settings


@pytest.fixture
def secrets_client(mock_settings):
    """Create a SecretsManagerClient instance with mocked boto3."""
    with patch('cert_rotation.secrets_client.boto3.client') as mock_boto3:
        mock_client = Mock()
        mock_boto3.return_value = mock_client
        client = SecretsManagerClient()
        client.client = mock_client
        return client


@pytest.fixture
def sample_secrets_list():
    """Sample secrets list with tags."""
    return [
        {
            'Name': 'prod-web-cert',
            'ARN': 'arn:aws:secretsmanager:us-east-1:123456789012:secret:prod-web-cert-AbCdEf',
            'Tags': [
                {'Key': 'Environment', 'Value': 'production'},
                {'Key': 'Service', 'Value': 'web'}
            ]
        },
        {
            'Name': 'dev-web-cert',
            'ARN': 'arn:aws:secretsmanager:us-east-1:123456789012:secret:dev-web-cert-GhIjKl',
            'Tags': [
                {'Key': 'Environment', 'Value': 'development'},
                {'Key': 'Service', 'Value': 'web'}
            ]
        },
        {
            'Name': 'prod-api-cert',
            'ARN': 'arn:aws:secretsmanager:us-east-1:123456789012:secret:prod-api-cert-MnOpQr',
            'Tags': [
                {'Key': 'Environment', 'Value': 'production'},
                {'Key': 'Service', 'Value': 'api'}
            ]
        }
    ]


@pytest.fixture
def sample_secret_value():
    """Sample secret value response."""
    return {
        'SecretString': '{"certificate": "-----BEGIN CERTIFICATE-----\\nMIIC...\\n-----END CERTIFICATE-----", "private_key": "-----BEGIN PRIVATE KEY-----\\nMIIE...\\n-----END PRIVATE KEY-----", "domain_name": "example.com"}',
        'ARN': 'arn:aws:secretsmanager:us-east-1:123456789012:secret:prod-web-cert-AbCdEf',
        'Name': 'prod-web-cert',
        'VersionId': 'EXAMPLE1-90ab-cdef-fedc-ba987EXAMPLE',
        'VersionStages': ['AWSCURRENT'],
        'CreatedDate': '2023-01-01T00:00:00Z',
        'LastAccessedDate': '2023-01-02T00:00:00Z',
        'LastChangedDate': '2023-01-01T00:00:00Z'
    }


class TestSecretsClientTagFiltering:
    """Test tag-based filtering functionality."""

    @pytest.mark.asyncio
    async def test_get_secrets_by_tag_success(self, secrets_client, sample_secrets_list, sample_secret_value):
        """Test successful filtering of secrets by tag."""
        # Mock list_secrets to return our sample data
        secrets_client.list_secrets = AsyncMock(return_value=sample_secrets_list)
        
        # Mock get_secret_value to return sample secret data
        secrets_client.get_secret_value = AsyncMock(return_value={
            'certificate': '-----BEGIN CERTIFICATE-----\nMIIC...\n-----END CERTIFICATE-----',
            'private_key': '-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----',
            'domain_name': 'example.com',
            '_metadata': {
                'arn': 'arn:aws:secretsmanager:us-east-1:123456789012:secret:prod-web-cert-AbCdEf',
                'name': 'prod-web-cert'
            }
        })

        # Test filtering by Environment=production
        result = await secrets_client.get_secrets_by_tag('Environment', 'production')

        # Should return 2 secrets (prod-web-cert and prod-api-cert)
        assert len(result) == 2
        assert 'prod-web-cert' in result
        assert 'prod-api-cert' in result
        assert 'dev-web-cert' not in result

        # Verify get_secret_value was called for each matching secret
        assert secrets_client.get_secret_value.call_count == 2

    @pytest.mark.asyncio
    async def test_get_secrets_by_tag_no_matches(self, secrets_client, sample_secrets_list):
        """Test filtering when no secrets match the tag."""
        secrets_client.list_secrets = AsyncMock(return_value=sample_secrets_list)

        # Test filtering by non-existent tag
        result = await secrets_client.get_secrets_by_tag('NonExistent', 'value')

        # Should return empty dict
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_secrets_by_env_tag_success(self, secrets_client, mock_settings, sample_secrets_list):
        """Test get_secrets_by_env_tag with configured environment variables."""
        # Mock the get_secrets_by_tag method
        expected_result = {'prod-web-cert': {'certificate': 'test'}}
        secrets_client.get_secrets_by_tag = AsyncMock(return_value=expected_result)

        result = await secrets_client.get_secrets_by_env_tag()

        # Verify it called get_secrets_by_tag with the right parameters
        secrets_client.get_secrets_by_tag.assert_called_once_with('Environment', 'production', True)
        assert result == expected_result

    @pytest.mark.asyncio
    async def test_get_secrets_by_env_tag_no_config(self, secrets_client, mock_settings):
        """Test get_secrets_by_env_tag when tag environment variables are not set."""
        # Clear the tag configuration
        mock_settings.tag_key = None
        mock_settings.tag_value = None

        result = await secrets_client.get_secrets_by_env_tag()

        # Should return empty dict
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_secrets_by_env_tag_partial_config(self, secrets_client, mock_settings):
        """Test get_secrets_by_env_tag when only one tag environment variable is set."""
        # Set only tag_key
        mock_settings.tag_key = 'Environment'
        mock_settings.tag_value = None

        result = await secrets_client.get_secrets_by_env_tag()

        # Should return empty dict
        assert result == {}


class TestSchedulerIntegration:
    """Test scheduler integration with tag-based discovery."""

    @pytest.mark.asyncio
    async def test_scheduler_uses_tag_discovery(self, mock_settings):
        """Test that scheduler uses tag-based discovery when configured."""
        from cert_rotation.scheduler import CertificateScheduler

        # Mock the secrets client methods
        with patch('cert_rotation.scheduler.SecretsManagerClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client

            # Mock tag-based discovery
            mock_client.get_secrets_by_env_tag = AsyncMock(return_value={
                'prod-cert-1': {'certificate': 'cert1', '_metadata': {'name': 'prod-cert-1'}},
                'prod-cert-2': {'certificate': 'cert2', '_metadata': {'name': 'prod-cert-2'}}
            })

            # Mock other required methods
            mock_client.get_monitored_secrets = AsyncMock(return_value={})

            scheduler = CertificateScheduler()

            # Test _get_secrets_data method
            secrets_data = await scheduler._get_secrets_data()

            # Should use tag-based discovery
            mock_client.get_secrets_by_env_tag.assert_called_once()
            mock_client.get_monitored_secrets.assert_not_called()

            assert len(secrets_data) == 2
            assert 'prod-cert-1' in secrets_data
            assert 'prod-cert-2' in secrets_data

    @pytest.mark.asyncio
    async def test_scheduler_fallback_to_explicit_names(self, mock_settings):
        """Test scheduler falls back to explicit names when tag discovery fails."""
        from cert_rotation.scheduler import CertificateScheduler

        # Configure both tag and explicit names
        mock_settings.secrets_names_list = ['explicit-cert-1', 'explicit-cert-2']

        with patch('cert_rotation.scheduler.SecretsManagerClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client

            # Mock tag-based discovery to fail
            mock_client.get_secrets_by_env_tag = AsyncMock(side_effect=Exception("Tag discovery failed"))

            # Mock explicit discovery to succeed
            mock_client.get_monitored_secrets = AsyncMock(return_value={
                'explicit-cert-1': {'certificate': 'cert1', '_metadata': {'name': 'explicit-cert-1'}}
            })

            scheduler = CertificateScheduler()

            # Test _get_secrets_data method
            secrets_data = await scheduler._get_secrets_data()

            # Should try tag-based first, then fall back to explicit
            mock_client.get_secrets_by_env_tag.assert_called_once()
            mock_client.get_monitored_secrets.assert_called_once()

            assert len(secrets_data) == 1
            assert 'explicit-cert-1' in secrets_data

    @pytest.mark.asyncio
    async def test_scheduler_no_configuration(self, mock_settings):
        """Test scheduler behavior when no discovery method is configured."""
        from cert_rotation.scheduler import CertificateScheduler

        # Clear all configuration
        mock_settings.tag_key = None
        mock_settings.tag_value = None
        mock_settings.secrets_names_list = []

        with patch('cert_rotation.scheduler.SecretsManagerClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client

            scheduler = CertificateScheduler()

            # Test _get_secrets_data method
            secrets_data = await scheduler._get_secrets_data()

            # Should return empty dict
            assert secrets_data == {}

            # Should not call any discovery methods
            mock_client.get_secrets_by_env_tag.assert_not_called()
            mock_client.get_monitored_secrets.assert_not_called()
