"""
Main FastAPI application for certificate rotation service.
"""

import logging
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
import uvicorn

from .config import settings
from .scheduler import CertificateScheduler
from .metrics import metrics_registry, generate_metrics


# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
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
    lifespan=lifespan
)


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "cert-rotation",
        "version": "0.1.0"
    }


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


@app.get("/status/list_acm")
async def list_acm_certificates() -> Dict[str, Any]:
    """List all certificates from AWS Certificate Manager."""
    global scheduler

    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    try:
        # Get all certificates from ACM
        all_certificates = await scheduler.acm_client.list_certificates()

        # Get monitored certificates with details
        monitored_certificates = await scheduler.acm_client.get_monitored_certificates()

        return {
            "all_certificates": all_certificates,
            "monitored_certificates": monitored_certificates,
            "monitored_arns": settings.acm_cert_arns_list,
            "total_certificates": len(all_certificates),
            "monitored_count": len(monitored_certificates)
        }

    except Exception as e:
        logger.error(f"Error listing ACM certificates: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list certificates: {str(e)}")


def main():
    """Main entry point."""
    logger.info(f"Starting server on {settings.host}:{settings.port}")
    uvicorn.run(
        "cert_rotation.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=False
    )


if __name__ == "__main__":
    main()
