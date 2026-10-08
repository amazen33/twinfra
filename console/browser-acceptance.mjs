// Cookies arrive only through stdin from the in-memory acceptance session.
// No storageState, trace, HAR, request headers or tokens are persisted/logged.
import { chromium } from 'playwright'
import fs from 'node:fs/promises'
let raw = ''
for await (const chunk of process.stdin) raw += chunk
const input = JSON.parse(raw); raw = ''
if (input.origin !== 'http://localhost:18080') throw new Error('Unexpected portal origin')
const browser = await chromium.launch({ executablePath: input.browser, headless: true })
let stage = 'overview'
const responses = []
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  await context.addCookies(input.cookies)
  input.cookies = []
  const page = await context.newPage()
  page.on('response', response => {
    const url = new URL(response.url())
    if (url.origin === input.origin && url.pathname.startsWith('/console/api/'))
      responses.push(url.pathname.split('/').pop() + '=' + response.status())
  })
  const failures = []
  page.on('pageerror', () => failures.push('JavaScript error'))
  await page.goto(input.origin + '/console/overview', { waitUntil: 'networkidle' })
  await page.getByText(/Your control plane is ready|Some workloads need attention/).waitFor()
  await fs.mkdir(input.output, { recursive: true })
  await page.screenshot({ path: input.output + '/overview-desktop.png', fullPage: true })
  for (const [tab, expected] of [
    ['Storage', 'S3 buckets'], ['AWS emulation', 'EC2 instances'], ['DynamoDB', 'DynamoDB tables'],
    ['GitOps', 'Argo CD applications'], ['Identity', 'Your Keycloak session']
  ]) {
    stage = tab
    await page.getByRole('navigation', { name: 'Workspace tabs' }).getByRole('button', { name: tab, exact: true }).click()
    await page.getByRole('heading', { name: expected, exact: true }).waitFor()
    if (await page.getByRole('alert').count()) failures.push('View error: ' + tab)
  }
  stage = 'reload'
  await page.reload({ waitUntil: 'networkidle' })
  await page.getByRole('heading', { name: 'Your Keycloak session' }).waitFor()
  stage = 'mobile'
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('navigation', { name: 'Platform navigation' }).getByRole('button', { name: /Overview/ }).click()
  await page.getByRole('heading', { name: /Your control plane|Some workloads/ }).waitFor()
  if (await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)) failures.push('Mobile horizontal overflow')
  await page.screenshot({ path: input.output + '/overview-mobile.png', fullPage: true })
  if (failures.length) throw new Error(failures.join('; '))
  console.log('PASS: six authenticated browser views, refresh, responsive navigation and desktop/mobile screenshots')
  await context.close()
} catch (error) {
  // Never print a browser error object: it may include OAuth redirect URLs.
  console.log('FAIL: browser stage ' + stage + '; ' + error.name)
  console.log('STATUS: ' + responses.join(' '))
  process.exitCode = 1
} finally { await browser.close() }
