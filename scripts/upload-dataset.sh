#!/usr/bin/env bash
# upload-dataset.sh — upload an h5ad file to Azure Files share, then invalidate
# any running ACI container for that dataset so the next browser access loads
# the new file instead of serving a stale in-memory copy.
#
# Usage: ./upload-dataset.sh /path/to/dataset.h5ad
set -euo pipefail

: "${ACI_FILES_ACCOUNT:?required}"
: "${ACI_FILES_KEY:?required}"
: "${ACI_FILES_SHARE:=cellxgene-data}"
: "${AZURE_RESOURCE_GROUP:?required}"

FILE="${1:?Usage: $0 /path/to/dataset.h5ad}"
BASENAME=$(basename "$FILE")

echo "==> Uploading $BASENAME to $ACI_FILES_ACCOUNT/$ACI_FILES_SHARE"
az storage file upload \
  --account-name "$ACI_FILES_ACCOUNT" \
  --account-key "$ACI_FILES_KEY" \
  --share-name "$ACI_FILES_SHARE" \
  --source "$FILE" \
  --path "$BASENAME"

echo "==> Done: https://${ACI_FILES_ACCOUNT}.file.core.windows.net/${ACI_FILES_SHARE}/${BASENAME}"

# Invalidate any running ACI for this dataset so the next access provisions
# a fresh container that mounts the new file.
# Name derivation must match ACIBackend._container_group_name() in aci_backend.py:
#   stem = splitext(basename)[0], lowercase alphanumeric+hyphens, max 50 chars
STEM=$(basename "$BASENAME" .h5ad | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/-$//' | cut -c1-50)
ACI_NAME="cellxgene-${STEM}"

echo "==> Invalidating ACI container: $ACI_NAME (if running)"
az container delete \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$ACI_NAME" \
  --yes \
  --no-wait 2>/dev/null && echo "==> ACI $ACI_NAME deleted (will reprovision on next access)" \
  || echo "==> ACI $ACI_NAME not found or already stopped — nothing to invalidate"
