"""
Main FastAPI application for certificate rotation service.
"""

import logging
from contextlib import asynccontextmanager
from typing import Any, Dict

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

from .config import settings
from .metrics import generate_metrics
from .scheduler import CertificateScheduler

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: CertificateScheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global scheduler

    logger.info("Starting certificate rotation service")

    # Initialize and start the scheduler
    scheduler = CertificateScheduler()
    await scheduler.start()

    logger.info("Certificate rotation service started successfully")

    yield

    # Cleanup
    logger.info("Shutting down certificate rotation service")
    if scheduler:
        await scheduler.stop()
    logger.info("Certificate rotation service stopped")


# Create FastAPI application
app = FastAPI(
    title="Certificate Rotation Service",
    description="AWS ACM certificate synchronization service for HAProxy",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "cert-rotation", "version": "0.1.0"}


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> str:
    """Prometheus metrics endpoint."""
    if not settings.metrics_enabled:
        raise HTTPException(status_code=404, detail="Metrics disabled")

    return generate_metrics()


@app.post("/reload")
async def manual_reload() -> Dict[str, str]:
    """Manually trigger certificate reload."""
    global scheduler

    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    try:
        await scheduler.sync_certificates()
        return {"status": "success", "message": "Certificate sync triggered"}
    except Exception as e:
        logger.error(f"Manual reload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Reload failed: {str(e)}")


@app.get("/status")
async def service_status() -> Dict[str, Any]:
    """Get service status and statistics."""
    global scheduler

    if not scheduler:
        return {"status": "initializing"}

    return await scheduler.get_status()


@app.get("/status/list_secrets")
async def list_secrets(include_tags: bool = False) -> Dict[str, Any]:
    """List all certificate secrets from AWS Secrets Manager."""
    global scheduler

    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    try:
        # Get all secrets from Secrets Manager (metadata only)
        all_secrets = await scheduler.secrets_client.list_secrets(
            include_tags=include_tags
        )
        # TODO: rewrite this if. It should incopsulated into secrets client. Same for scheduler

        # Get monitored secrets based on current configuration
        if settings.tag_key and settings.tag_value:
            # Tag-based discovery
            tag_secrets_data = await scheduler.secrets_client.get_secrets_by_env_tag(
                include_tags=include_tags
            )
            monitored_secrets = {
                name: {"_metadata": data.get("_metadata", {})}
                for name, data in tag_secrets_data.items()
            }
            discovery_method = "tag-based"
            discovery_config = {
                "tag_key": settings.tag_key,
                "tag_value": settings.tag_value,
            }
        else:
            # Explicit secret names
            monitored_secrets = (
                await scheduler.secrets_client.get_monitored_secrets_metadata(
                    include_tags=include_tags
                )
            )
            discovery_method = "explicit"
            discovery_config = {"monitored_secret_names": settings.secrets_names_list}

        return {
            "all_secrets": all_secrets,
            "monitored_secrets": monitored_secrets,
            "discovery_method": discovery_method,
            "discovery_config": discovery_config,
            "total_secrets": len(all_secrets),
            "monitored_count": len(monitored_secrets),
            "include_tags": include_tags,
        }

    except Exception as e:
        logger.error(f"Error listing secrets: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list secrets: {str(e)}")


@app.get("/status/secrets_by_tag")
async def list_secrets_by_tag(
    tag_key: str, tag_value: str, include_tags: bool = True
) -> Dict[str, Any]:
    """List secrets filtered by a specific tag key/value pair."""
    global scheduler

    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    try:
        # Get secrets by the specified tag
        secrets_data = await scheduler.secrets_client.get_secrets_by_tag(
            tag_key, tag_value, include_tags=include_tags
        )

        # Convert to metadata-only format for the response
        secrets_metadata = {}
        for name, data in secrets_data.items():
            secrets_metadata[name] = {"_metadata": data.get("_metadata", {})}

        return {
            "tag_filter": {"key": tag_key, "value": tag_value},
            "secrets": secrets_metadata,
            "count": len(secrets_metadata),
            "include_tags": include_tags,
        }

    except Exception as e:
        logger.error(f"Error listing secrets by tag {tag_key}={tag_value}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to list secrets by tag: {str(e)}"
        )


@app.get("/debug/secret/{secret_name}")
async def get_secret_debug_info(
    secret_name: str, include_content: bool = False
) -> Dict[str, Any]:
    """
    Get detailed secret information for debugging.
    WARNING: Use include_content=true only for debugging - it exposes certificate data!
    """
    global scheduler

    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    try:
        if include_content:
            # Get full secret data (including sensitive content)
            logger.warning(f"DEBUG: Exposing secret content for {secret_name}")
            secret_data = await scheduler.secrets_client.get_secret_value(secret_name)

            if not secret_data:
                raise HTTPException(
                    status_code=404, detail=f"Secret {secret_name} not found"
                )

            # Mask sensitive data partially for logs
            masked_data = secret_data.copy()
            if "certificate" in masked_data:
                cert = masked_data["certificate"]
                masked_data["certificate"] = (
                    cert[:50] + "..." + cert[-50:] if len(cert) > 100 else cert
                )
            if "private_key" in masked_data:
                key = masked_data["private_key"]
                masked_data["private_key"] = (
                    key[:50] + "..." + key[-50:] if len(key) > 100 else key
                )

            return {
                "secret_name": secret_name,
                "content": secret_data,
                "warning": "This response contains sensitive certificate data!",
            }
        else:
            # Get only metadata
            metadata_response = (
                await scheduler.secrets_client.get_monitored_secrets_metadata(
                    include_tags=True
                )
            )
            secret_metadata = metadata_response.get(secret_name)

            if not secret_metadata:
                raise HTTPException(
                    status_code=404,
                    detail=f"Secret {secret_name} not found or not monitored",
                )

            return {
                "secret_name": secret_name,
                "metadata": secret_metadata,
                "note": "Use include_content=true to see certificate data (debugging only)",
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting secret debug info for {secret_name}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get secret info: {str(e)}"
        )


def main():
    """Main entry point."""
    logger.info(f"Starting server on {settings.host}:{settings.port}")
    uvicorn.run(
        "cert_rotation.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    main()
