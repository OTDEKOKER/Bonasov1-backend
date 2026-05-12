# syntax=docker/dockerfile:1.7

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=18000

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --upgrade pip && \
    pip install -r requirements.txt

COPY . .
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 18000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
