targetScope = 'resourceGroup'

@description('Deployment prefix. Use separate resource groups for development, staging and production.')
param prefix string
param location string = resourceGroup().location
@description('Existing Container Apps environment with VNet integration and Log Analytics configured.')
param environmentId string
@description('User-assigned identity with AcrPull and Key Vault Secrets User on the required resources.')
param identityId string
param registryServer string
@description('Immutable image reference, preferably registry/repository@sha256:digest.')
param image string
@description('Exact external HTTPS origin used by browsers. Configure DNS and TLS before rollout.')
param appOrigin string
@description('Container Apps Key Vault references: [{name, keyVaultUrl}]. No plaintext secrets.')
param secretReferences array
@description('Environment secret mappings: [{name: DATABASE_URL, secretRef: database-url}, ...].')
param secretEnvironment array
@description('Additional nonsecret runtime configuration, e.g. Google client ID, AI model, storage container.')
param runtimeEnvironment array = []

var identity = {
  type: 'UserAssigned'
  userAssignedIdentities: {
    '${identityId}': {}
  }
}
var baseEnvironment = [
  { name: 'APP_ENV', value: 'production' }
  { name: 'DEMO_MODE', value: 'false' }
  { name: 'COOKIE_SECURE', value: 'true' }
  { name: 'APP_ORIGIN', value: appOrigin }
  { name: 'API_ORIGIN', value: appOrigin }
  { name: 'STORAGE_BACKEND', value: 'azure' }
]
var secrets = [for secret in secretReferences: {
  name: secret.name
  keyVaultUrl: secret.keyVaultUrl
  identity: identityId
}]
var environment = concat(baseEnvironment, runtimeEnvironment, secretEnvironment)

resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${prefix}-app'
  location: location
  identity: identity
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      secrets: secrets
      registries: [{ server: registryServer, identity: identityId }]
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
      }
    }
    template: {
      containers: [{
        name: 'app'
        image: image
        env: environment
        resources: { cpu: 1, memory: '2Gi' }
        probes: [
          { type: 'Liveness', httpGet: { path: '/health/live', port: 8000 }, initialDelaySeconds: 15, periodSeconds: 30 }
          { type: 'Readiness', httpGet: { path: '/health/ready', port: 8000 }, initialDelaySeconds: 5, periodSeconds: 10 }
        ]
      }]
      scale: { minReplicas: 1, maxReplicas: 5 }
    }
  }
}
resource worker 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${prefix}-worker'
  location: location
  identity: identity
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      secrets: secrets
      registries: [{ server: registryServer, identity: identityId }]
    }
    template: {
      containers: [{
        name: 'worker'
        image: image
        command: ['python', '-m', 'realty.jobs']
        env: environment
        resources: { cpu: 1, memory: '2Gi' }
      }]
      // Start with one worker. Validate queue throughput and leases before increasing concurrency.
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
}
output appFqdn string = api.properties.configuration.ingress.fqdn
output workerName string = worker.name
