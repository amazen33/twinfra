import { useEffect, useState } from 'react'
import { api, currentTab, tabs, type Tab, type Identity, type Overview, type Application, type Cloud, type Storage, type Dynamo } from './api'

function Badge({ value }: { value: string }) {
  const good = ['Ready', 'Healthy', 'Synced', 'running', 'Enabled'].includes(value)
  return <span className={`badge ${good ? 'badge-good' : 'badge-neutral'}`}><span className="status-dot" />{value || 'Unknown'}</span>
}
function Empty({ children }: { children: React.ReactNode }) { return <p className="empty">{children}</p> }
function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="panel"><h2>{title}</h2>{children}</section>
}

export function App() {
  const [tab, setTab] = useState<Tab>(currentTab)
  const [open, setOpen] = useState(false)
  const [identity, setIdentity] = useState<Identity | null>(null)
  const [backend, setBackend] = useState('localstack')
  const [selection, setSelection] = useState('')
  const [data, setData] = useState<unknown>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [refresh, setRefresh] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    api<Identity>('identity', controller.signal).then(setIdentity).catch(() => setIdentity(null))
    return () => controller.abort()
  }, [refresh])
  useEffect(() => {
    const onPop = () => { setData(null); setLoading(true); setTab(currentTab()); setSelection('') }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(''); setData(null)
    const query = new URLSearchParams({ backend })
    if (selection) query.set(tab === 'storage' ? 'bucket' : 'table', selection)
    const path = tab === 'iam' ? 'identity' : tab === 'localstack' ? 'cloud?' + query :
      ['storage', 'dynamodb'].includes(tab) ? tab + '?' + query : tab
    api(path, controller.signal).then(setData).catch(e => { if (!controller.signal.aborted) setError(e.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [tab, backend, selection, refresh])
  function navigate(next: Tab) {
    if (next !== tab) { setData(null); setLoading(true); setTab(next); setSelection(''); window.history.pushState(null, '', '/console/' + next) }
    setOpen(false)
  }
  const selected = tabs.find(t => t.id === tab)!
  const overview = data as Overview | null
  const storage = data as Storage | null
  const dynamo = data as Dynamo | null
  const cloud = data as Cloud | null
  const user = data as Identity | null
  return <div className="app-shell">
    <a className="skip-link" href="#content">Skip to content</a>
    {open && <button className="sidebar-scrim" aria-label="Close navigation" onClick={() => setOpen(false)} />}
    <aside className={`sidebar ${open ? 'is-open' : ''}`} aria-label="Platform navigation">
      <a className="brand" href="/console/overview"><span className="brand-symbol">T</span><span>Twinfra<small>CONTROL PLANE</small></span></a>
      <div className="environment"><span className="status-dot" /><span>WSL local lab<small>vcloud-wsl-local</small></span><span className="environment-tag">LOCAL</span></div>
      <p className="nav-label">WORKSPACE</p>
      <nav aria-label="Platform navigation">{tabs.map(t => <button key={t.id} className={`nav-item ${tab === t.id ? 'active' : ''}`} aria-current={tab === t.id ? 'page' : undefined} onClick={() => navigate(t.id)}>
        <span className="nav-icon" aria-hidden="true">{t.icon}</span><span>{t.label}<small>{t.description}</small></span>
      </button>)}</nav>
      <div className="sidebar-foot"><span className="shield" aria-hidden="true">◇</span><span>Zero-trust workspace<small>OIDC session · scoped access</small></span></div>
    </aside>
    <div className="workspace">
      <header className="topbar">
        <button className="mobile-menu" aria-label="Open navigation" aria-expanded={open} onClick={() => setOpen(!open)}>☰</button>
        <div className="breadcrumb">Platform <span>/</span> <strong>{selected.label}</strong></div>
        <div className="account"><span className="avatar">{identity?.username.slice(0, 1).toUpperCase() || '?'}</span><span>{identity?.username || 'Session'}<small>{identity?.roles.includes('console.admin') ? 'Console administrator' : 'Console viewer'}</small></span><a href="/console/logout">Sign out</a></div>
      </header>
      <main id="content" tabIndex={-1}>
        <div className="page-heading"><div><p className="eyebrow">TWINFRA WORKSPACE</p><h1>{selected.label === 'Identity' ? 'Identity & access' : selected.label}</h1><p className="subtitle">{selected.description} across your local platform.</p></div>
          <button className="button secondary" onClick={() => setRefresh(x => x + 1)} disabled={loading}><span aria-hidden="true">⟳</span> Refresh</button>
        </div>
        <nav className="tabs" aria-label="Workspace tabs">{tabs.map(t => <button key={t.id} className={tab === t.id ? 'selected' : ''} aria-current={tab === t.id ? 'page' : undefined} onClick={() => navigate(t.id)}>{t.label}</button>)}</nav>
        {['storage', 'localstack', 'dynamodb'].includes(tab) && <div className="toolbar"><label htmlFor="backend">Emulator</label><select id="backend" value={backend} onChange={e => { setBackend(e.target.value); setSelection('') }}><option value="localstack">LocalStack Community</option><option value="ministack">MiniStack</option></select><span className="read-only">Read-only</span></div>}
        {loading && <div className="loading" role="status"><span className="loader" />Loading {selected.label.toLowerCase()}…</div>}
        {error && <div className="error" role="alert"><h2>Unable to load this view</h2><p>{error}</p><a href={'/console/' + tab}>Reload this page</a></div>}
        {!loading && !error && data !== null && <>
          {tab === 'overview' && overview && <>
            <div className="hero"><div><span className="eyebrow">PLATFORM SERVICES</span><h2>{overview.ready === overview.pods && overview.healthyDeployments === overview.deployments ? 'Your control plane is ready.' : 'Some workloads need attention.'}</h2><p>Live status from {overview.namespace}. Heavy AI and HPC offloading remain disabled in this lab.</p></div><Badge value={overview.ready === overview.pods ? 'Ready' : 'Degraded'} /></div>
            <div className="metrics"><Card title="Ready pods"><strong className="metric">{overview.ready}<small> / {overview.pods}</small></strong><p>Running pods with all containers ready</p></Card><Card title="Healthy deployments"><strong className="metric">{overview.healthyDeployments}<small> / {overview.deployments}</small></strong><p>Available replicas meet desired replicas</p></Card><Card title="Access boundary"><strong className="metric metric-label">Restricted</strong><p>Namespace isolation & read-only portal access</p></Card></div>
            <Card title="Explore your workspace"><div className="shortcuts">{tabs.slice(1).map(t => <button key={t.id} onClick={() => navigate(t.id)}><span aria-hidden="true">{t.icon}</span><strong>{t.label}</strong><small>{t.description}</small><span className="arrow" aria-hidden="true">↗</span></button>)}</div></Card>
            <p className="timestamp">Last checked {new Date(overview.checkedAt).toLocaleTimeString()}</p>
          </>}
          {tab === 'gitops' && <Card title="Argo CD applications"><div className="table-scroll"><table><thead><tr><th>Application</th><th>Sync</th><th>Health</th><th>Revision</th></tr></thead><tbody>{(data as Application[]).map(a => <tr key={a.name}><td><strong>{a.name}</strong>{a.message && <small>{a.message}</small>}</td><td><Badge value={a.sync} /></td><td><Badge value={a.health} /></td><td><code title={a.revision}>{a.revision.slice(0, 12) || 'Pending'}</code></td></tr>)}</tbody></table></div>{!(data as Application[]).length && <Empty>No Applications are configured in this namespace.</Empty>}</Card>}
          {tab === 'storage' && storage && <Card title={selection ? `Objects in ${selection}` : 'S3 buckets'}>{selection && <button className="text-button" onClick={() => setSelection('')}>← All buckets</button>}{selection ? <ul className="resource-list">{storage.objects.map(key => <li key={key}><code>{key}</code></li>)}</ul> : <ul className="resource-list">{storage.buckets.map(bucket => <li key={bucket}><button onClick={() => setSelection(bucket)}><span aria-hidden="true">▦</span>{bucket}<span aria-hidden="true">→</span></button></li>)}</ul>}{!(selection ? storage.objects : storage.buckets).length && <Empty>{selection ? 'No objects in this bucket.' : 'No buckets found in this emulator.'}</Empty>}<p className="note">Preview is limited to 100 keys. Object contents and write operations are excluded.</p></Card>}
          {tab === 'dynamodb' && dynamo && <Card title={selection ? `Table: ${selection}` : 'DynamoDB tables'}>{selection ? <><button className="text-button" onClick={() => setSelection('')}>← All tables</button><pre>{JSON.stringify(dynamo.metadata, null, 2)}</pre></> : <ul className="resource-list">{dynamo.tables.map(table => <li key={table}><button onClick={() => setSelection(table)}>{table}<span aria-hidden="true">→</span></button></li>)}</ul>}{!selection && !dynamo.tables.length && <Empty>No tables found in this emulator.</Empty>}<p className="note">Table metadata only. Tenant rows are never scanned.</p></Card>}
          {tab === 'localstack' && cloud && <><Card title="AWS service health"><div className="service-grid">{Object.entries(cloud.services).map(([name, state]) => <div key={name}><strong>{name.toUpperCase()}</strong><Badge value={state} /></div>)}</div></Card><Card title="EC2 instances"><div className="table-scroll"><table><thead><tr><th>Instance</th><th>Type</th><th>State</th></tr></thead><tbody>{cloud.instances.map(i => <tr key={i.id}><td><code>{i.id}</code></td><td>{i.type}</td><td><Badge value={i.state} /></td></tr>)}</tbody></table></div>{!cloud.instances.length && <Empty>No emulated EC2 instances.</Empty>}<p className="note">API emulation uses ephemeral lab state. These instances do not launch real virtual machines.</p></Card></>}
          {tab === 'iam' && user && <><Card title="Your Keycloak session"><dl><dt>Signed in as</dt><dd>{user.username}</dd><dt>Console roles</dt><dd>{user.roles.map(role => <Badge key={role} value={role} />)}</dd><dt>Realm issuer</dt><dd><code>{user.issuer}</code></dd><dt>OIDC client</dt><dd><code>{user.client}</code></dd></dl></Card><Card title="Identity administration"><p>Portal roles grant access to these read-only views. They do not grant Kubernetes administration or Keycloak realm-management permissions.</p>{user.roles.includes('console.admin') ? <a className="button" href={user.adminUrl} target="_blank" rel="noopener noreferrer">Open Keycloak administration ↗</a> : <p className="note">A console administrator can open the dedicated Keycloak administration endpoint.</p>}</Card></>}
        </>}
        <footer>Twinfra <span>Local validation environment</span><span>Single origin · authenticated session</span></footer>
      </main>
    </div>
  </div>
}
