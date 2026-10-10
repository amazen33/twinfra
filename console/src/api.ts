export type Identity = { environment?: string; region?: string; backends?: string[]; username: string; roles: string[]; issuer: string; client: string; adminUrl: string }
export type Overview = { pods: number; ready: number; deployments: number; healthyDeployments: number; namespace: string; checkedAt: string }
export type Application = { name: string; sync: string; health: string; revision: string; message: string }
export type Cloud = { backend: string; services: Record<string, string>; instances: { id: string; type: string; state: string }[]; ephemeral: boolean }
export type Storage = { backend: string; bucket: string; buckets: string[]; objects: string[] }
export type Dynamo = { backend: string; tables: string[]; metadata: unknown }
export type Tab = 'overview' | 'storage' | 'cloud' | 'dynamodb' | 'gitops' | 'iam'
export const tabs: { id: Tab; label: string; description: string; icon: string }[] = [
  { id: 'overview', label: 'Overview', description: 'Cluster health', icon: '◈' },
  { id: 'storage', label: 'Storage', description: 'S3 buckets & objects', icon: '▦' },
  { id: 'cloud', label: 'AWS emulation', description: 'AWS-compatible services', icon: '☁' },
  { id: 'dynamodb', label: 'DynamoDB', description: 'Tables & metadata', icon: '▤' },
  { id: 'gitops', label: 'GitOps', description: 'Argo CD reconciliation', icon: '⥁' },
  { id: 'iam', label: 'Identity', description: 'Keycloak & access', icon: '◇' }
]
export function currentTab(path = window.location.pathname): Tab {
  const value = path.split('/')[2]
  return tabs.some(t => t.id === value) ? value as Tab : 'overview'
}
export async function api<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch('/console/api/' + path, { credentials: 'same-origin', signal, headers: { Accept: 'application/json' } })
  if (response.status === 401 || response.redirected) throw new Error('Your session ended. Sign in again to continue.')
  if (response.status === 403) throw new Error('Your account does not have access to this view.')
  if (!response.ok) throw new Error('This service is unavailable. Try refreshing in a moment.')
  if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Your session ended. Sign in again to continue.')
  return response.json() as Promise<T>
}
