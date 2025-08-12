"""
Configuration management for the certificate rotation service.
"""

import os
from typing import List, Optional
from pydantic import Field, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Service configuration
    host: str = Field(default="0.0.0.0", description="Host to bind the service")
    port: int = Field(default=8000, description="Port to bind the service")
    log_level: str = Field(default="INFO", description="Logging level")
    
    # Certificate management
    cert_path: str = Field(..., description="Path where certificates are stored")
    secrets_names: str = Field(
        default="",
        description="Comma-separated list of AWS Secrets Manager secret names to monitor"
    )

    # Tag-based secret filtering
    tag_key: Optional[str] = Field(
        default=None,
        description="Tag key to filter secrets by"
    )
    tag_value: Optional[str] = Field(
        default=None,
        description="Tag value to filter secrets by"
    )

    # AWS configuration
    aws_region: str = Field(default="us-east-1", description="AWS region")
    
    # Scheduling configuration
    check_interval_minutes: int = Field(
        default=60,
        description="Interval in minutes to check for certificate updates"
    )
    
    # HAProxy configuration
    haproxy_reload_url: Optional[str] = Field(
        default=None,
        description="HAProxy reload endpoint URL"
    )
    haproxy_stats_socket: Optional[str] = Field(
        default=None,
        description="HAProxy stats socket path"
    )
    haproxy_container_name: Optional[str] = Field(
        default=None,
        description="HAProxy container name for Docker signal reload"
    )
    
    # Metrics configuration
    metrics_enabled: bool = Field(default=True, description="Enable Prometheus metrics")
    
    @property
    def secrets_names_list(self) -> List[str]:
        """Get Secrets Manager secret names as a list."""
        if not self.secrets_names:
            return []
        return [name.strip() for name in self.secrets_names.split(',') if name.strip()]
    
    @validator('cert_path')
    def validate_cert_path(cls, v):
        """Ensure certificate path exists and is writable."""
        if not os.path.exists(v):
            try:
                os.makedirs(v, exist_ok=True)
            except Exception as e:
                raise ValueError(f"Cannot create certificate path {v}: {e}")
        
        if not os.access(v, os.W_OK):
            raise ValueError(f"Certificate path {v} is not writable")
        
        return v
    
    @validator('log_level')
    def validate_log_level(cls, v):
        """Validate log level."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level. Must be one of: {valid_levels}")
        return v.upper()
    
    class Config:
        env_prefix = "CERT_ROTATION_"
        case_sensitive = False


# Global settings instance
settings = Settings()
