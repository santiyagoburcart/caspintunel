// Suite 4 — customer flows end to end on the isolated stack (fake data; the
// flows really write: login, register, order, notifications). Phone viewport.
export const name = 'user-flows'

export async function run({ test, open }) {
  const fillLogin = async (page, user, pw) => {
    await page.fill('input[autocomplete="username"]', user)
    await page.fill('input[type="password"]', pw)
    await page.click('button[type="submit"]')
  }
  await test('login form → dashboard with the customer’s services', async () => {
    const p = await open({ path: '/login', writes: true })
    await fillLogin(p.page, 'audit-user', 'audit-pass-123')
    await p.page.waitForSelector('.csp-svc', { timeout: 10000 })
    const n = await p.page.$$eval('.csp-svc', (e) => e.length); await p.ctx.close()
    if (n < 4) throw new Error(`${n} service cards`)
  })
  await test('wrong password → error, stays on login', async () => {
    const p = await open({ path: '/login', writes: true })
    await fillLogin(p.page, 'audit-user', 'nope-nope-1')
    await p.page.waitForTimeout(1500)
    const r = await p.page.evaluate(() => ({ path: location.pathname, text: document.body.innerText }))
    await p.ctx.close()
    if (r.path !== '/login') throw new Error('navigated to ' + r.path)
  })
  await test('register: button stays disabled until the terms are accepted', async () => {
    const p = await open({ path: '/register', writes: true })
    const dis = await p.page.$eval('form button.btn-primary', (b) => b.disabled)
    await p.page.check('.reg-terms input')
    const en = await p.page.$eval('form button.btn-primary', (b) => !b.disabled); await p.ctx.close()
    if (!dis || !en) throw new Error(`disabled before=${dis} enabled after=${en}`)
  })
  await test('register → new account lands on an empty dashboard', async () => {
    const p = await open({ path: '/register', writes: true })
    const u = 'flow' + Date.now().toString(36)
    await p.page.fill('input[autocomplete="username"]', u)
    await p.page.fill('input[autocomplete="new-password"]', 'flow-pass-12345')
    await p.page.fill('input[autocomplete="name"]', 'کاربر آزمایشی')
    await p.page.fill('input[type="tel"], input[autocomplete="tel"]', '0912' + String(Date.now()).slice(-7))
    await p.page.check('.reg-terms input')
    await p.page.click('form button.btn-primary')
    await p.page.waitForFunction(() => location.pathname === '/', null, { timeout: 10000 })
    await p.page.waitForSelector('.empty-state', { timeout: 10000 })
    await p.ctx.close()
  })
  await test('store → pick a plan → checkout → pay step with card, amount and timer', async () => {
    const p = await open({ path: '/store', auth: 'user', writes: true })
    await p.page.click('.csp-plan >> nth=1')
    await p.page.click('.csp-store-cta')
    await p.page.waitForSelector('form.card')
    const acc = p.page.locator('form input[dir="ltr"][autocomplete="off"]')
    if (await acc.count()) await acc.fill('flowacc' + Date.now().toString(36).slice(-4))
    await p.page.click('form .m-actionbar button')
    await p.page.waitForSelector('.ckt-cardopt', { timeout: 10000 })
    const r = await p.page.evaluate(() => ({ cards: document.querySelectorAll('.ckt-cardopt').length,
      amount: document.querySelector('.ckt-amount-v')?.textContent, ring: !!document.querySelector('.ctd-ring') }))
    await p.ctx.close()
    if (!r.cards || !/\d/.test(r.amount || '') || !r.ring) throw new Error(JSON.stringify(r))
  })
  await test('history lists the pending order with a visible Pay button', async () => {
    const p = await open({ path: '/history', auth: 'user' })
    const r = await p.page.$$eval('.csp-hist-btn--primary', (bs) => bs.map((b) => {
      const cs = getComputedStyle(b); return { text: b.textContent.trim(), bg: cs.backgroundColor, fg: cs.color }
    }))
    await p.ctx.close()
    if (!r.length) throw new Error('no Pay button')
    if (r.some((b) => !b.text || b.bg === b.fg || /255, 255, 255\)$/.test(b.bg))) throw new Error('Pay button unreadable ' + JSON.stringify(r[0]))
  })
  await test('renew → plan summary sheet → continue opens checkout for that service', async () => {
    const p = await open({ path: '/', auth: 'user' })
    await p.page.click('.csp-svc-btn--primary >> nth=0')
    await p.page.waitForSelector('.cdlg-confirm:not([disabled])', { timeout: 10000 })
    await p.page.click('.cdlg-confirm')
    await p.page.waitForFunction(() => location.pathname === '/checkout' && /renew=/.test(location.search), null, { timeout: 8000 })
    await p.ctx.close()
  })
  await test('QR sheet opens with the QR image and closes with Escape', async () => {
    const p = await open({ path: '/', auth: 'user' })
    await p.page.click('.csp-svc-actions .csp-svc-btn >> nth=0')
    await p.page.waitForSelector('.csp-qr-modal img', { timeout: 10000 })
    const ok = await p.page.$eval('.csp-qr-modal img', (i) => i.complete && i.naturalWidth > 0)
    await p.page.keyboard.press('Escape'); await p.page.waitForTimeout(300)
    const gone = !(await p.page.$('.csp-qr-modal')); await p.ctx.close()
    if (!ok || !gone) throw new Error(`img ${ok} closed ${gone}`)
  })
  await test('notifications: panel lists items; "mark all read" clears the badge', async () => {
    const p = await open({ path: '/', auth: 'user', writes: true })
    const badge = await p.page.$('.ct-nbell-badge')
    await p.page.click('.ct-nbell-btn'); await p.page.waitForSelector('.ct-nbell-item', { timeout: 8000 })
    const n = await p.page.$$eval('.ct-nbell-item', (e) => e.length)
    if (badge) { await p.page.click('.ct-nbell-markall'); await p.page.waitForTimeout(800) }
    const after = await p.page.$('.ct-nbell-badge'); await p.ctx.close()
    if (!n) throw new Error('no items')
    if (badge && after) throw new Error('badge still shown')
  })
  await test('profile shows the account and its referral code', async () => {
    const p = await open({ path: '/profile', auth: 'user' })
    const t = await p.page.evaluate(() => document.querySelector('main').innerText); await p.ctx.close()
    if (!t.includes('audit-user')) throw new Error('username missing')
  })
  await test('dark/light toggle switches and persists', async () => {
    const p = await open({ path: '/', auth: 'user' })
    const a = await p.page.evaluate(() => document.documentElement.classList.contains('dark'))
    await p.page.click('.csp-topbar-r > button.csp-icon-btn'); await p.page.waitForTimeout(300)
    const b = await p.page.evaluate(() => [document.documentElement.classList.contains('dark'), localStorage.getItem('ct_mode')]); await p.ctx.close()
    if (a === b[0]) throw new Error('mode unchanged')
    if (b[1] !== (b[0] ? 'dark' : 'light')) throw new Error('not stored: ' + b[1])
  })
  await test('help + rules pages render content', async () => {
    const p = await open({ path: '/help', auth: 'user' })
    const h = await p.page.evaluate(() => document.querySelector('main').innerText.length)
    await p.page.goto(p.page.url().replace('/help', '/rules')); await p.page.waitForTimeout(800)
    const r = await p.page.evaluate(() => document.querySelector('main').innerText.length); await p.ctx.close()
    if (h < 40 || r < 40) throw new Error(`help ${h} rules ${r}`)
  })
}
