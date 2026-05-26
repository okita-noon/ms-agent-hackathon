targetScope = 'resourceGroup'

@description('環境名 (dev, dev2, staging, prod)')
@allowed(['dev', 'dev2', 'staging', 'prod'])
param environment string = 'dev'

@description('プロジェクト名')
param projectName string = 'orderai'

@description('デプロイリージョン')
param location string = resourceGroup().location

@description('Azure SQL 管理者ユーザー名')
param sqlAdminLogin string

@secure()
@description('Azure SQL 管理者パスワード')
param sqlAdminPassword string

@description('Azure AI Foundry で使用する OpenAI モデルデプロイ名')
param openAiModelDeploymentName string = 'gpt-5.4-mini'

@description('Azure AI Foundry で使用する OpenAI モデル名')
param openAiModelName string = 'gpt-5.4-mini'

@description('Azure AI Foundry で使用する OpenAI モデルバージョン')
param openAiModelVersion string = '2026-03-17'

@description('Embedding モデルデプロイ名')
param embeddingModelDeploymentName string = 'text-embedding-3-small'

var suffix = '${projectName}-${environment}'
var tags = {
  project: projectName
  environment: environment
  hackathon: 'ms-agent-2026'
}

// ============================================================
// Key Vault
// ============================================================
module keyVault 'modules/key-vault.bicep' = {
  name: 'keyVault'
  params: {
    name: 'kv-${suffix}'
    location: location
    tags: tags
  }
}

// ============================================================
// Cosmos DB (受注・パターン学習・セッション)
// ============================================================
module cosmosDb 'modules/cosmos-db.bicep' = {
  name: 'cosmosDb'
  params: {
    name: 'cosmos-${suffix}'
    location: location
    tags: tags
    keyVaultName: keyVault.outputs.name
  }
}

// ============================================================
// Azure SQL Database (マスタ・在庫)
// ============================================================
module sqlDatabase 'modules/sql-database.bicep' = {
  name: 'sqlDatabase'
  params: {
    serverName: 'sql-${suffix}'
    databaseName: 'db-${suffix}'
    location: location
    tags: tags
    adminLogin: sqlAdminLogin
    adminPassword: sqlAdminPassword
    keyVaultName: keyVault.outputs.name
  }
}

// ============================================================
// Azure AI Services (OpenAI / Speech)
// NOTE: クォータ承認後に有効化する。ai-orderai-dev2 は手動作成済み。
// ============================================================
// module aiServices 'modules/ai-services.bicep' = {
//   name: 'aiServices'
//   params: {
//     name: 'ai-${suffix}'
//     location: location
//     tags: tags
//     openAiModelDeploymentName: openAiModelDeploymentName
//     openAiModelName: openAiModelName
//     openAiModelVersion: openAiModelVersion
//     embeddingModelDeploymentName: embeddingModelDeploymentName
//     keyVaultName: keyVault.outputs.name
//   }
// }

// ============================================================
// Azure AI Search (商品/顧客あいまい検索)
// ============================================================
module aiSearch 'modules/ai-search.bicep' = {
  name: 'aiSearch'
  params: {
    name: 'search-${suffix}'
    location: location
    tags: tags
    keyVaultName: keyVault.outputs.name
  }
}

// ============================================================
// Storage Account (Blob: 音声・メール原本バックアップ)
// ============================================================
module storage 'modules/storage.bicep' = {
  name: 'storage'
  params: {
    name: replace('st${suffix}', '-', '')
    location: location
    tags: tags
  }
}

// ============================================================
// Log Analytics + Application Insights
// ============================================================
module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  params: {
    name: suffix
    location: location
    tags: tags
  }
}

// ============================================================
// Azure Container Apps Environment + API
// ============================================================
module containerApps 'modules/container-apps.bicep' = {
  name: 'containerApps'
  params: {
    name: suffix
    location: location
    tags: tags
    logAnalyticsWorkspaceId: monitoring.outputs.logAnalyticsWorkspaceId
  }
}


// ============================================================
// Budget (コスト管理アラート)
// ============================================================
module budget 'modules/budget.bicep' = {
  name: 'budget'
  params: {
    budgetName: 'budget-${suffix}'
    amount: 30000
    contactEmails: [
      'yi.asdf761@gmail.com'
    ]
  }
}

// ============================================================
// Communication Services (メール送信・電話)
// ============================================================
module communicationServices 'modules/communication-services.bicep' = {
  name: 'communicationServices'
  params: {
    name: 'acs-${suffix}'
    tags: tags
  }
}

// ============================================================
// Outputs
// ============================================================
output keyVaultName string = keyVault.outputs.name
output cosmosDbEndpoint string = cosmosDb.outputs.endpoint
output sqlServerFqdn string = sqlDatabase.outputs.serverFqdn
// output aiServicesEndpoint string = aiServices.outputs.endpoint  // クォータ承認後に有効化
output aiSearchEndpoint string = aiSearch.outputs.endpoint
output containerAppsUrl string = containerApps.outputs.appUrl
output frontendUrl string = storage.outputs.webEndpoint
