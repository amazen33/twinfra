// Real browser OIDC + first-login acceptance. Private inputs arrive through
// stdin only. Never emit credentials, URLs with queries, cookies, HAR or traces.
import { chromium } from 'playwright'
import { X509Certificate, createHash, createHmac } from 'node:crypto'
let raw = ''
for await (const chunk of process.stdin) raw += chunk
const input = JSON.parse(raw); raw = ''
if (input.origin !== 'http://localhost:18080' || !/^console-browser-[a-f0-9]{12}$/.test(input.username)) process.exit(1)
// Trust only the public key of the lab certificate already verified by the
// Python harness. This applies to this disposable browser, never OS trust.
const certificate = new X509Certificate(input.certificate)
if (!certificate.checkHost('localhost') || Date.now() < Date.parse(certificate.validFrom) || Date.now() > Date.parse(certificate.validTo)) process.exit(1)
const pin = createHash('sha256').update(certificate.publicKey.export({ type: 'spki', format: 'der' })).digest('base64')
const browser = await chromium.launch({ executablePath: input.browser, headless: true,
  args: ['--ignore-certificate-errors-spki-list=' + pin] })
let stage = 'initial redirect', seed, enrollmentPeriod, passwordChanged = false
const otp = () => {
  enrollmentPeriod = Math.floor(Date.now() / 30000)
  const count = Buffer.alloc(8); count.writeBigUInt64BE(BigInt(enrollmentPeriod))
  const digest = createHmac('sha1', seed).update(count).digest()
  return String((digest.readUInt32BE(digest.at(-1) & 15) & 0x7fffffff) % 1000000).padStart(6, '0')
}
const portal = 'http://localhost:18080/console/'
try {
  let context = await browser.newContext()
  let page = await context.newPage()
  const allowed = new Set([input.origin, 'https://localhost:18443'])
  await context.route('**/*', route => allowed.has(new URL(route.request().url()).origin) ? route.continue() : route.abort())
  await page.goto(portal)
  stage = 'credentials'
  await page.locator('#username').fill(input.username)
  await page.locator('#password').fill(input.password)
  await page.locator('#kc-login').click()
  // Required actions may be presented in either order by the realm.
  for (let i = 0; i < 3; i++) {
    await page.waitForLoadState('domcontentloaded')
    if (new URL(page.url()).origin === input.origin) break
    if (await page.locator('#password-new').count()) {
      stage = 'password change'
      await page.locator('#password-new').fill(input.newPassword)
      await page.locator('#password-confirm').fill(input.newPassword)
      await page.locator('input[type=submit],button[type=submit]').first().click()
      passwordChanged = true
    } else if (await page.locator('input[name=totpSecret]').count()) {
      stage = 'MFA enrollment'
      seed = Buffer.from(await page.locator('input[name=totpSecret]').inputValue(), 'utf8')
      await page.locator('#totp').fill(otp())
      await page.locator('#userLabel').fill('vcloud-browser-acceptance')
      await page.locator('input[type=submit],button[type=submit]').first().click()
    } else throw new Error('Unexpected required action')
  }
  stage = 'first callback'
  if (!passwordChanged || !seed) throw new Error('Required actions were skipped')
  await page.getByRole('navigation', { name: 'Workspace tabs' }).waitFor()
  const first = await page.request.get(input.origin + '/console/api/identity')
  if (first.status() !== 200) throw new Error('Identity response failed')
  console.log('PASS: browser starts at portal; temporary password change; TOTP enrollment; callback and identity HTTP 200')
  const cookies = await context.cookies(portal)
  stage = 'cookie attributes'
  const sessions = cookies.filter(c => c.name.startsWith('vcloud_portal'))
  if (!sessions.length || sessions.some(c => !c.httpOnly || c.path !== '/console' || c.sameSite !== 'Lax')) throw new Error('Session attributes failed')
  console.log('PASS: browser session cookie HttpOnly; SameSite Lax; path /console')
  await context.close()
  stage = 'returning MFA login'
  context = await browser.newContext()
  await context.route('**/*', route => allowed.has(new URL(route.request().url()).origin) ? route.continue() : route.abort())
  page = await context.newPage()
  await page.goto(portal)
  await page.locator('#username').fill(input.username)
  await page.locator('#password').fill(input.newPassword)
  await page.locator('#kc-login').click()
  stage = 'returning OTP form'
  await page.locator('input[name=otp]').waitFor()
  // Keycloak rejects reuse of an OTP already consumed during enrollment.
  if (Math.floor(Date.now() / 30000) === enrollmentPeriod)
    await page.waitForTimeout(30000 - Date.now() % 30000 + 1100)
  await page.locator('input[name=otp]').fill(otp())
  await page.locator('input[type=submit],button[type=submit]').first().click()
  stage = 'returning callback'
  await page.getByRole('navigation', { name: 'Workspace tabs' }).waitFor()
  console.log('PASS: returning browser login with enrolled TOTP -> portal HTTP 200')
  await context.close()
} catch (error) {
  console.log('FAIL: browser login stage ' + stage + '; ' + (error.message.match(/ERR_[A-Z_]+/)?.[0] || error.name))
  process.exitCode = 1
} finally {
  input.password = ''; input.newPassword = ''; seed?.fill(0)
  await browser.close()
}
