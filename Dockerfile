# Use Python 3.11 slim image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install UV
RUN pip install uv

# Create app user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set work directory
WORKDIR /app

# Copy project files
COPY pyproject.toml ./
COPY src/ ./src/

# Install dependencies using UV
RUN uv pip install --system -e .

# Create certificate directory
RUN mkdir -p /app/certs && chown appuser:appuser /app/certs

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default environment variables
ENV CERT_ROTATION_CERT_PATH=/app/certs \
    CERT_ROTATION_HOST=0.0.0.0 \
    CERT_ROTATION_PORT=8000 \
    CERT_ROTATION_LOG_LEVEL=INFO

# Run the application
CMD ["python", "-m", "cert_rotation.main"]
