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
    acm_cert_arns: str = Field(
        default="",
        description="Comma-separated list of ACM certificate ARNs to monitor"
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
    
    # Metrics configuration
    metrics_enabled: bool = Field(default=True, description="Enable Prometheus metrics")
    
    @property
    def acm_cert_arns_list(self) -> List[str]:
        """Get ACM certificate ARNs as a list."""
        if not self.acm_cert_arns:
            return []
        return [arn.strip() for arn in self.acm_cert_arns.split(',') if arn.strip()]
    
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
