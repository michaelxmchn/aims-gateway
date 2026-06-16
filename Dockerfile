FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/skills/uploaded /app/.aims /data && chown -R 1000:1000 /app/skills /app/.aims /data

EXPOSE 8000

CMD ["uvicorn", "src.gateway.server:app", "--host", "0.0.0.0", "--port", "8000"]
