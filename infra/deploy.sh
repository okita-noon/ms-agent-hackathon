#!/usr/bin/env bash
set -euo pipefail

ENVIRONMENT="${1:-dev}"
LOCATION="${2:-japaneast}"
PROJECT_NAME="orderai"
RESOURCE_GROUP="rg-${PROJECT_NAME}-${ENVIRONMENT}"

echo "=== AI受発注自動一元管理システム - Azure デプロイ ==="
echo "環境: ${ENVIRONMENT}"
echo "リージョン: ${LOCATION}"
echo "リソースグループ: ${RESOURCE_GROUP}"
echo ""

if [ -z "${SQL_ADMIN_PASSWORD:-}" ]; then
  echo "ERROR: SQL_ADMIN_PASSWORD 環境変数を設定してください"
  echo "  export SQL_ADMIN_PASSWORD='YourSecurePassword123!'"
  exit 1
fi

echo ">>> リソースグループ作成..."
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --tags project="$PROJECT_NAME" environment="$ENVIRONMENT"

echo ">>> Bicep デプロイ開始..."
az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --template-file main.bicep \
  --parameters main.bicepparam \
  --parameters environment="$ENVIRONMENT" location="$LOCATION" \
  --name "deploy-${ENVIRONMENT}-$(date +%Y%m%d%H%M%S)"

echo ""
echo "=== デプロイ完了 ==="
az deployment group show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$(az deployment group list --resource-group "$RESOURCE_GROUP" --query '[0].name' -o tsv)" \
  --query properties.outputs \
  -o table
