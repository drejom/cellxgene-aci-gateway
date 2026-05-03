#!/usr/bin/env bash
# upload-dataset.sh — upload an h5ad file to Azure Files share, then invalidate
# any running ACI container for that dataset so the next browser access loads
# the new file instead of serving a stale in-memory copy.
#
# Required env vars:
#   ACI_FILES_ACCOUNT       Azure Files storage account name
#   ACI_FILES_KEY           Azure Files storage account key
#   ACI_FILES_SHARE         Azure Files share name (default: cellxgene-data)
#   AZURE_RESOURCE_GROUP    Resource group containing ACI containers (default: RG-KDL-CORE)
#
# Usage: ./upload-dataset.sh /path/to/dataset.h5ad
set -euo pipefail

: "${ACI_FILES_ACCOUNT:?required}"
: "${ACI_FILES_KEY:?required}"
: "${ACI_FILES_SHARE:=cellxgene-data}"
: "${AZURE_RESOURCE_GROUP:=RG-KDL-CORE}"

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
# Name derivation matches ACIBackend._container_group_name() in aci_backend.py:
#   stem = splitext(basename)[0], replace each non-alphanumeric with '-', lowercase, max 50 chars
STEM=$(printf '%s' "${BASENAME%.*}" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | cut -c1-50)
ACI_NAME="cellxgene-${STEM}"

echo "==> Checking for running ACI container: $ACI_NAME"
if az container show \
     --resource-group "$AZURE_RESOURCE_GROUP" \
     --name "$ACI_NAME" \
     --output none 2>/dev/null; then
  echo "==> Deleting $ACI_NAME ..."
  az container delete \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --name "$ACI_NAME" \
    --yes \
    --no-wait
  echo "==> ACI $ACI_NAME deleted (will reprovision on next access)"
else
  echo "==> ACI $ACI_NAME not running — nothing to invalidate"
fi