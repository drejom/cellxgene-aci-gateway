#!/usr/bin/env bash
# upload-dataset.sh — upload an h5ad file to Azure Files share
# Usage: ./upload-dataset.sh /path/to/dataset.h5ad
set -euo pipefail

: "${ACI_FILES_ACCOUNT:?required}"
: "${ACI_FILES_KEY:?required}"
: "${ACI_FILES_SHARE:=cellxgene-data}"

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
