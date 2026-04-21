#!/usr/bin/env bash
# setup-azure.sh — provision Azure Files share + enable ACI subnet service endpoint
# Run once per environment. Idempotent.
set -euo pipefail

: "${AZURE_SUBSCRIPTION_ID:?required}"
: "${AZURE_RESOURCE_GROUP:?required}"
: "${STORAGE_ACCOUNT_NAME:?required}"      # e.g. kdlcellxgene
: "${VNET_NAME:?required}"                 # e.g. VNET-KDL-CORE
: "${SUBNET_NAME:=aci}"
: "${SHARE_NAME:=cellxgene-data}"
: "${SHARE_SIZE_GB:=100}"                  # Premium minimum = 100 GiB

echo "==> Creating storage account: $STORAGE_ACCOUNT_NAME"
az storage account create \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$STORAGE_ACCOUNT_NAME" \
  --sku Premium_LRS \
  --kind FileStorage \
  --location westus2 \
  --https-only true \
  --allow-shared-key-access true \
  --output none

echo "==> Creating file share: $SHARE_NAME (${SHARE_SIZE_GB}GiB)"
KEY=$(az storage account keys list \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --account-name "$STORAGE_ACCOUNT_NAME" \
  --query '[0].value' -o tsv)

az storage share create \
  --account-name "$STORAGE_ACCOUNT_NAME" \
  --account-key "$KEY" \
  --name "$SHARE_NAME" \
  --quota "$SHARE_SIZE_GB" \
  --output none

echo "==> Enabling Microsoft.Storage service endpoint on subnet $SUBNET_NAME"
az network vnet subnet update \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --vnet-name "$VNET_NAME" \
  --name "$SUBNET_NAME" \
  --service-endpoints Microsoft.Storage \
  --output none

echo ""
echo "==> Done. Storage account key (add to vault / env):"
echo "    ACI_FILES_KEY=$KEY"
