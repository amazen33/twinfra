import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from './App'

const user = { username: 'vcloud-admin', roles: ['console.admin'], issuer: 'https://localhost:18443/realms/vcloud', client: 'vcloud-console', adminUrl: 'https://localhost:18443/admin/' }
beforeEach(() => {
  window.history.replaceState(null, '', '/console/overview')
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const view = url.split('/console/api/')[1]
    const data = view === 'identity' ? user : view === 'overview' ? { pods: 8, ready: 8, deployments: 6, healthyDeployments: 6, namespace: 'platform-services', checkedAt: '2026-10-08T12:00:00Z' } :
      view === 'gitops' ? [{ name: 'vcloud-wsl-platform', sync: 'Synced', health: 'Healthy', revision: 'cf1abfb123456789', message: '' }] :
      view.startsWith('storage?') ? { buckets: ['safe-bucket'], objects: ['file.txt'] } :
      view.startsWith('dynamodb?') ? { tables: ['users'], metadata: { TableName: 'users' } } :
      { services: { ec2: 'running' }, instances: [], ephemeral: true }
    return new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }))
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('console navigation and read-only state', () => {
  it('reads its environment badge and enabled emulators from configuration', async () => {
    vi.mocked(fetch).mockImplementation(async (url) => new Response(JSON.stringify(String(url).includes('/identity') ? { ...user, environment: 'dev', region: 'cairo-1', backends: ['ministack'] } : { services: {}, instances: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    window.history.replaceState(null, '', '/console/cloud')
    render(<App />)
    expect(await screen.findByText('Dev · cairo-1')).toBeTruthy()
    expect(screen.queryByRole('combobox')).toBeNull()
    expect(screen.queryByText('vcloud-wsl-local')).toBeNull()
  })
  it('shows live health and navigates to GitOps without leaving the shell', async () => {
    render(<App />)
    expect(await screen.findByText('Your control plane is ready.')).toBeTruthy()
    await userEvent.click(screen.getAllByRole('button', { name: /^GitOps$/ })[0])
    expect(await screen.findByText('vcloud-wsl-platform')).toBeTruthy()
    expect(window.location.pathname).toBe('/console/gitops')
    expect(screen.getByRole('navigation', { name: 'Platform navigation' })).toBeTruthy()
  })
  it('uses only MiniStack and browses object keys with a bounded query', async () => {
    window.history.replaceState(null, '', '/console/storage')
    render(<App />)
    await screen.findByText('safe-bucket')
    await waitFor(() => expect(fetch).toHaveBeenCalledWith('/console/api/storage?backend=ministack', expect.anything()))
    await userEvent.click(await screen.findByRole('button', { name: /safe-bucket/ }))
    expect(await screen.findByText('file.txt')).toBeTruthy()
    expect(fetch).toHaveBeenCalledWith('/console/api/storage?backend=ministack&bucket=safe-bucket', expect.anything())
  })
  it('handles denied access and never displays stale data', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response('{}', { status: 403, headers: { 'Content-Type': 'application/json' } }))
    render(<App />)
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.getByText('Your account does not have access to this view.')).toBeTruthy()
    expect(screen.queryByText('Your control plane is ready.')).toBeNull()
  })
  it('renders an empty EC2 state rather than a blank API page', async () => {
    window.history.replaceState(null, '', '/console/cloud')
    render(<App />)
    expect(await screen.findByText('No emulated EC2 instances.')).toBeTruthy()
    expect(screen.getByText('EC2')).toBeTruthy()
  })
  it('restricts the native IAM administration link to the admin role', async () => {
    window.history.replaceState(null, '', '/console/iam')
    render(<App />)
    const link = await screen.findByRole('link', { name: /Open Keycloak administration/ })
    expect(link.getAttribute('href')).toBe('https://localhost:18443/admin/')
    expect(link.getAttribute('rel')).toContain('noopener')
    expect(localStorage.length).toBe(0)
  })
})
