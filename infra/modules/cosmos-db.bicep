param name string
param location string
param tags object
param keyVaultName string

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-02-15-preview' = {
  name: name
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [
      {
        locationName: location
        failoverPriority: 0
      }
    ]
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    capabilities: [
      { name: 'EnableServerless' }
    ]
  }
}

resource ordersDb 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-02-15-preview' = {
  parent: cosmosAccount
  name: 'orders'
  properties: {
    resource: { id: 'orders' }
  }
}

resource ordersContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-02-15-preview' = {
  parent: ordersDb
  name: 'order-documents'
  properties: {
    resource: {
      id: 'order-documents'
      partitionKey: {
        paths: ['/tenant_id']
        kind: 'Hash'
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        includedPaths: [{ path: '/*' }]
        compositeIndexes: [
          [
            { path: '/delivery_date', order: 'ascending' }
            { path: '/status', order: 'ascending' }
          ]
          [
            { path: '/customer_id', order: 'ascending' }
            { path: '/order_date', order: 'descending' }
          ]
        ]
      }
    }
  }
}

resource pickingContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-02-15-preview' = {
  parent: ordersDb
  name: 'picking-lists'
  properties: {
    resource: {
      id: 'picking-lists'
      partitionKey: {
        paths: ['/tenant_id']
        kind: 'Hash'
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        includedPaths: [{ path: '/*' }]
        compositeIndexes: [
          [
            { path: '/delivery_date', order: 'ascending' }
            { path: '/delivery_carrier', order: 'ascending' }
          ]
        ]
      }
    }
  }
}

resource sessionsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-02-15-preview' = {
  parent: ordersDb
  name: 'order-sessions'
  properties: {
    resource: {
      id: 'order-sessions'
      partitionKey: {
        paths: ['/tenant_id']
        kind: 'Hash'
      }
      defaultTtl: 7200
    }
  }
}

resource intelligenceDb 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-02-15-preview' = {
  parent: cosmosAccount
  name: 'intelligence'
  properties: {
    resource: { id: 'intelligence' }
  }
}

resource patternsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-02-15-preview' = {
  parent: intelligenceDb
  name: 'order-patterns'
  properties: {
    resource: {
      id: 'order-patterns'
      partitionKey: {
        paths: ['/customer_id']
        kind: 'Hash'
      }
    }
  }
}

resource profilesContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-02-15-preview' = {
  parent: intelligenceDb
  name: 'customer-profiles'
  properties: {
    resource: {
      id: 'customer-profiles'
      partitionKey: {
        paths: ['/customer_id']
        kind: 'Hash'
      }
    }
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource cosmosConnectionStringSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'cosmos-connection-string'
  properties: {
    value: cosmosAccount.listConnectionStrings().connectionStrings[0].connectionString
  }
}

output endpoint string = cosmosAccount.properties.documentEndpoint
output name string = cosmosAccount.name
