# ==============================================================================
# Stage 1: Build dependencies
# ==============================================================================
FROM python:3.10-slim AS builder

WORKDIR /app

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install build dependencies if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy and install dependencies to user space
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ==============================================================================
# Stage 2: Final runner image
# ==============================================================================
FROM python:3.10-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH=/home/appuser/.local/bin:$PATH

# Create a secure non-root user and group
RUN groupadd -r -g 10001 appgroup && \
    useradd -r -u 10001 -g appgroup -m -d /home/appuser -s /bin/bash appuser

# Copy python packages from the builder stage
COPY --from=builder --chown=appuser:appgroup /root/.local /home/appuser/.local

# Copy application code with non-root ownership
COPY --chown=appuser:appgroup . .

# Use the secure non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check using python's built-in urllib (avoids installing curl/wget in slim image)
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live', timeout=3)" || exit 1

# Start the application with Uvicorn in production mode
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]