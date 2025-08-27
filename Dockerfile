# ────────── build image ──────────
# 1) Force amd64 so Azure Web App (x86_64) can run it
FROM python:3.11-slim AS base
WORKDIR /src

# Install system dependencies that might be needed
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY csa_backend/requirements.txt app/
RUN pip install --no-cache-dir -r app/requirements.txt

# Copy the actual application code
COPY csa_backend/ app/

# Create a non-root user for security
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /src
USER appuser

# Health check
HEALTHCHECK --interval=120s --timeout=30s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8000/docs || exit 1

# gunicorn will listen on 8000 inside the container
EXPOSE 8000

# Simplified startup command with better error handling
# CMD ["gunicorn", "--workers", "2", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "--log-level", "info", "main:app"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--access-log", "--log-level", "info"]
