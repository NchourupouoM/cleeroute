# FROM python:3.12-slim
# WORKDIR /app
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt
# COPY . .
# EXPOSE 8000
# CMD ["uvicorn", "src.cleeroute.main:app", "--host", "0.0.0.0", "--port", "8000"]



# ===========================
#  STAGE 1 : build dependencies
# ===========================
FROM python:3.12-slim AS builder

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libssl-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt


# ===========================
#  STAGE 2 : final image
# ===========================
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Security: Install CA + supervisor
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed site-packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Add project files
COPY . .

# Create non-root user
RUN useradd -m celeryuser && chown -R celeryuser:celeryuser /app

# Supervisord config
COPY supervisord.conf /etc/supervisor/supervisord.conf

# Healthcheck (Uvicorn)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://localhost:8000/health || exit 1

EXPOSE 8000

USER celeryuser

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf"]
