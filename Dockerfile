FROM python:3.11-slim

WORKDIR /app

# System deps (none needed beyond base)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps — pinned
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Package — install as editable-style copy into site-packages
COPY cellxgene_gateway/ /usr/local/lib/python3.11/site-packages/cellxgene_gateway/
COPY templates/ /usr/local/lib/python3.11/site-packages/cellxgene_gateway/templates/

# App files
COPY launcher.py entrypoint.sh ./
RUN chmod +x entrypoint.sh

RUN mkdir -p /data /logs

ENV CELLXGENE_LOCATION=/usr/local/bin/cellxgene
ENV CELLXGENE_DATA=/data
ENV GATEWAY_PORT=5005
ENV GATEWAY_EXPIRE_SECONDS=3600
ENV EXTERNAL_PROTOCOL=https
ENV PROXY_FIX_FOR=1
ENV PROXY_FIX_PROTO=1
ENV PROXY_FIX_HOST=1
ENV CELLXGENE_BACKEND=aci

EXPOSE 5005

ENTRYPOINT ["/app/entrypoint.sh"]
