# HW8: one image for the Kafka worker and the FastAPI service (docker-compose.yml picks the command).
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# Container log timestamps in the same time zone as the Mac, so host and container lines line up.
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*
ENV TZ=America/Los_Angeles

COPY requirements.txt .
RUN pip install -r requirements.txt

# Only the root-level application code. .env is never copied; compose passes it in at run time.
COPY config.py AGENT.md ./
COPY backend ./backend
COPY kafka_service ./kafka_service
COPY domain_tools ./domain_tools
COPY bikeshare ./bikeshare
COPY agent_tools ./agent_tools
