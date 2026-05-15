using './main.bicep'

param environment = 'dev'
param projectName = 'orderai'
param location = 'japaneast'
param sqlAdminLogin = 'sqladmin'
param sqlAdminPassword = readEnvironmentVariable('SQL_ADMIN_PASSWORD', '')
param openAiModelDeploymentName = 'gpt-4o'
param embeddingModelDeploymentName = 'text-embedding-3-small'
