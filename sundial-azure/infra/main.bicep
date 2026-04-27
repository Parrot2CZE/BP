targetScope = 'resourceGroup'

@minLength(1)
param environmentName string

@minLength(1)
param location string = resourceGroup().location

var uniqueSuffix = uniqueString(resourceGroup().id)

resource storage 'Microsoft.Storage/storageAccounts@2022-09-01' = {
  name: 'st${uniqueSuffix}'
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
}

resource tableService 'Microsoft.Storage/storageAccounts/tableServices@2022-09-01' = {
  parent: storage
  name: 'default'
}

resource sundialTable 'Microsoft.Storage/storageAccounts/tableServices/tables@2022-09-01' = {
  parent: tableService
  name: 'sundial'
}

resource plan 'Microsoft.Web/serverfarms@2022-03-01' = {
  name: 'plan-${environmentName}'
  location: location
  sku: { name: 'Y1', tier: 'Dynamic' }
  kind: 'functionapp'
  properties: {
    reserved: true
  }
}

var connStr = 'DefaultEndpointsProtocol=https;AccountName=${storage.name};AccountKey=${storage.listKeys().keys[0].value};EndpointSuffix=core.windows.net'

resource functionApp 'Microsoft.Web/sites@2022-03-01' = {
  name: 'func-${environmentName}-${uniqueSuffix}'
  location: location
  kind: 'functionapp,linux'
  tags: { 'azd-service-name': 'api' }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'Python|3.11'
      appSettings: [
        { name: 'AzureWebJobsStorage',            value: connStr }
        { name: 'FUNCTIONS_EXTENSION_VERSION',    value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME',       value: 'python' }
        { name: 'STORAGE_CONNECTION_STRING',      value: connStr }
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'true' }
        { name: 'AzureWebJobsFeatureFlags',       value: 'EnableWorkerIndexing' }
      ]
      cors: { allowedOrigins: ['*'] }
    }
  }
}

resource staticSite 'Microsoft.Storage/storageAccounts@2022-09-01' = {
  name: 'stweb${uniqueSuffix}'
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: true
  }
}


output AZURE_FUNCTION_APP_NAME string = functionApp.name
output STATIC_WEB_STORAGE string = staticSite.name
output AZURE_FUNCTION_APP_URL string = 'https://${functionApp.properties.defaultHostName}'
