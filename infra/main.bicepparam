using './main.bicep'

param environment = 'dev2'
param projectName = 'orderai'
param location = 'japaneast'
param sqlAdminLogin = 'sqladmin'
param sqlAdminPassword = readEnvironmentVariable('SQL_ADMIN_PASSWORD', '')
param openAiModelDeploymentName = 'gpt-5.4-mini'
param openAiModelName = 'gpt-5.4-mini'
param openAiModelVersion = '2026-03-17'
param embeddingModelDeploymentName = 'text-embedding-3-small'
