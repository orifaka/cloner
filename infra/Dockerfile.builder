FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY packages /app/packages
COPY apps /app/apps
COPY template /app/template
COPY .env.example /app/.env.example

ENV PYTHONPATH=/app/packages/core:/app/packages/billing:/app/packages/deploy:/app/packages/monitoring:/app/apps/builder-bot

CMD ["python", "apps/builder-bot/main.py"]
