# Multi-purpose Dockerfile that can build both management platform and agent
# Use build argument to specify which component to build
ARG COMPONENT=management

# Frontend build stage (only for management platform)
FROM node:18-alpine AS frontend-builder
WORKDIR /app/frontend
COPY management_platform/web/package*.json ./
RUN npm ci --only=production
COPY management_platform/web/ ./
RUN npm run build

# Python dependencies build stage
FROM python:3.11-alpine AS python-builder
RUN apk add --no-cache \
    gcc \
    musl-dev \
    postgresql-dev \
    libffi-dev \
    openssl-dev \
    cargo \
    rust
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Management platform runtime stage
FROM python:3.11-alpine AS management
RUN apk add --no-cache \
    postgresql-client \
    libpq \
    libffi \
    openssl \
    && addgroup -g 1001 -S appgroup \
    && adduser -u 1001 -S appuser -G appgroup

COPY --from=python-builder /root/.local /home/appuser/.local
COPY --from=frontend-builder /app/frontend/dist /app/static

WORKDIR /app
COPY management_platform/ ./management_platform/
COPY shared/ ./shared/
COPY alembic.ini ./
COPY migrations/ ./migrations/

RUN mkdir -p /app/logs /app/uploads \
    && chown -R appuser:appgroup /app

USER appuser
ENV PATH="/home/appuser/.local/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "management_platform.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Agent runtime stage
FROM python:3.11-alpine AS agent
RUN apk add --no-cache \
    libffi \
    openssl \
    iputils \
    bind-tools \
    curl \
    && addgroup -g 1001 -S agentgroup \
    && adduser -u 1001 -S agentuser -G agentgroup

COPY --from=python-builder /root/.local /home/agentuser/.local

WORKDIR /app
COPY agent/ ./agent/
COPY shared/ ./shared/

RUN mkdir -p /app/logs /app/data \
    && chown -R agentuser:agentgroup /app

USER agentuser
ENV PATH="/home/agentuser/.local/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import psutil; exit(0 if psutil.cpu_percent() >= 0 else 1)" || exit 1

CMD ["python", "-m", "agent"]

# Final stage selection based on build argument
FROM ${COMPONENT} AS final