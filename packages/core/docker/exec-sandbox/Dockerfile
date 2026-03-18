FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash coreutils iptables procps \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    SQLAlchemy>=2.0.0 \
    PyYAML>=6.0.0 \
    trino>=0.330.0 \
    clickhouse-sqlalchemy>=0.3.0 \
    psycopg2-binary>=2.9.0 \
    pymysql>=1.1.0 \
    pymssql>=2.2.0 \
    duckdb>=1.0.0

WORKDIR /workspace
