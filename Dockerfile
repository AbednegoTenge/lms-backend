# ==========================================
# STAGE 1: Build Dependencies & Assets
# ==========================================
FROM python:3.12-slim AS builder

WORKDIR /app

# Install system tools needed to compile Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Generate Python wheels in a local directory
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

# ==========================================
# STAGE 2: Final Production Image
# ==========================================
FROM python:3.12-slim

WORKDIR /app

# Install ONLY runtime libraries (no compilers allowed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-compiled wheels from Stage 1 and install them
COPY --from=builder /app/wheels /app/wheels
RUN pip install --no-cache-dir /app/wheels/* && rm -rf /app/wheels

# Copy application source code
COPY . .

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
