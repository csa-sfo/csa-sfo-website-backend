# ────────── build image ──────────
# 1) Force amd64 so Azure Web App (x86_64) can run it
FROM python:3.11-slim AS base
WORKDIR /app

# Install system dependencies that might be needed
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the actual application code
COPY . .

# Create a non-root user for security
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

# Health check - use /health endpoint instead of /docs
HEALTHCHECK --interval=120s --timeout=30s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# gunicorn will listen on 8000 inside the container
EXPOSE 8000

# Fixed startup command - removed invalid --access-log flag
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--log-level", "debug"]