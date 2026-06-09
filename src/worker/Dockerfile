FROM python:3.11-slim

# ── System dependencies for Playwright browsers ─────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    ca-certificates \
    libnss3 \
    libnspr4 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production

WORKDIR /app

# ── Install Python dependencies ─────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (Chromium for scraping tasks)
RUN pip install --no-cache-dir playwright && \
    python -m playwright install chromium && \
    python -m playwright install-deps chromium

# ── Copy worker code ────────────────────────────────────────────────────
COPY src/ ./src/
COPY tests/ ./tests/

# ── Default: run the worker loop ────────────────────────────────────────
CMD ["python", "-m", "src.worker.worker"]
