param name string
param tags object

resource communicationService 'Microsoft.Communication/communicationServices@2023-04-01' = {
  name: name
  location: 'global'
  tags: tags
  properties: {
    dataLocation: 'Japan'
  }
}

output name string = communicationService.name
output id string = communicationService.id
