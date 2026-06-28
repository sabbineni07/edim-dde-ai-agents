# syntax=docker/dockerfile:1

# Multi-stage build: compile Python wheels in a builder image (gcc/g++/unixodbc-dev),
# then copy only site-packages into a slim runtime image. Keeps compilers, curl, and
# pip/setuptools out of production — smaller image, fewer OS CVEs, and no UI/node_modules.

FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade 'pip>=24' 'wheel>=0.46.2' && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --force-reinstall 'jaraco.context>=6.1.0' 'wheel>=0.46.2'

FROM python:3.11-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    unixodbc \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Drop pip/setuptools/wheel (build tooling; vendored copies trigger false-positive CVEs)
RUN rm -rf \
      /usr/local/lib/python3.11/site-packages/pip \
      /usr/local/lib/python3.11/site-packages/pip-*.dist-info \
      /usr/local/lib/python3.11/site-packages/setuptools \
      /usr/local/lib/python3.11/site-packages/setuptools-*.dist-info \
      /usr/local/lib/python3.11/site-packages/wheel \
      /usr/local/lib/python3.11/site-packages/wheel-*.dist-info \
    && rm -f /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/wheel

COPY API/ API/
COPY AI/ AI/
COPY DE/ DE/
COPY shared/ shared/
COPY config/ config/
COPY data/sample_job_metrics.csv data/sample_job_metrics.csv
COPY data/sample.csv data/sample.csv
COPY data/templates/ data/templates/

ENV PYTHONPATH=/app
# Prefer bundled CSV when compose/runtime env does not set USE_LOCAL_DATA
ENV USE_LOCAL_DATA=true

EXPOSE 8000

CMD ["uvicorn", "API.src.main:app", "--host", "0.0.0.0", "--port", "8000"]
