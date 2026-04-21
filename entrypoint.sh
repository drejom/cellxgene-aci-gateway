#!/bin/sh
set -e

if [ -z "$CELLXGENE_LOCATION" ]; then
  echo "ERROR: CELLXGENE_LOCATION not set"; exit 1
fi
if [ -z "$CELLXGENE_DATA" ]; then
  echo "ERROR: CELLXGENE_DATA not set"; exit 1
fi

echo "Starting cellxgene-gateway (backend=${CELLXGENE_BACKEND:-subprocess})"

exec python3 /app/launcher.py
