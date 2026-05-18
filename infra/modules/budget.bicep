@description('バジェット名')
param budgetName string

@description('月額バジェット金額（JPY）')
param amount int

@description('アラート通知先メールアドレス')
param contactEmails array

@description('バジェット開始日（YYYY-MM-01 形式）')
param startDate string = '${utcNow('yyyy-MM')}-01'

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: budgetName
  properties: {
    timePeriod: {
      startDate: startDate
    }
    timeGrain: 'Monthly'
    amount: amount
    category: 'Cost'
    notifications: {
      actual_30_percent: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 30
        thresholdType: 'Actual'
        contactEmails: contactEmails
      }
      actual_50_percent: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 50
        thresholdType: 'Actual'
        contactEmails: contactEmails
      }
      actual_65_percent: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 65
        thresholdType: 'Actual'
        contactEmails: contactEmails
      }
      actual_80_percent: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 80
        thresholdType: 'Actual'
        contactEmails: contactEmails
      }
      actual_90_percent: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 90
        thresholdType: 'Actual'
        contactEmails: contactEmails
      }
    }
  }
}

output budgetName string = budget.name
