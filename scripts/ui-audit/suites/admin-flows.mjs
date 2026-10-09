// Suite 5 — operator flows end to end on the isolated stack (fake data; the
// flows really write: login, user toggle, payment reject). Phone viewport
// unless noted.
export const name = 'admin-flows'

const text = (page) => page.evaluate(() => document.querySelector('main').innerText)

export async function run({ test, open }) {
  await test('staff login form → dashboard KPIs', async () => {
    const p = await open({ path: '/panel/login', writes: true })
    await p.page.fill('input[autocomplete="username"]', 'audit-admin')
    await p.page.fill('input[type="password"]', 'audit-pass-123')
    await p.page.click('button[type="submit"]')
    await p.page.waitForSelector('.dash .kpi', { timeout: 10000 })
    const n = await p.page.$$eval('.dash .kpi', (e) => e.length); await p.ctx.close()
    if (n !== 4) throw new Error(`${n} KPI tiles`)
  })
  await test('users: search narrows to the matching account', async () => {
    const p = await open({ path: '/panel/users', auth: 'staff' })
    await p.page.fill('.usr-search input', 'audit-user'); await p.page.press('.usr-search input', 'Enter')
    await p.page.waitForTimeout(1200)
    const rows = await p.page.$$eval('.usr-row', (r) => r.map((x) => x.innerText)); await p.ctx.close()
    if (rows.length !== 1 || !rows[0].includes('audit-user')) throw new Error(`${rows.length} rows`)
  })
  await test('users: source filter "bot" shows only bot accounts', async () => {
    const p = await open({ path: '/panel/users', auth: 'staff' })
    await p.page.selectOption('select.usr-sel >> nth=0', 'bot'); await p.page.waitForTimeout(1200)
    const names = await p.page.$$eval('.usr-row .usr-uname > span[dir="ltr"]', (s) => s.map((x) => x.textContent)); await p.ctx.close()
    if (!names.length || names.some((n) => !n.startsWith('tg_'))) throw new Error(names.join(','))
  })
  await test('users: edit opens a full-screen sheet on the phone and closes', async () => {
    const p = await open({ path: '/panel/users', auth: 'staff' })
    await p.page.click('.usr-edit-btn >> nth=0'); await p.page.waitForSelector('.usr-modal')
    const r = await p.page.$eval('.usr-modal', (m) => m.getBoundingClientRect().toJSON())
    await p.page.click('.usr-modal-head .usr-icon-btn'); await p.page.waitForTimeout(300)
    const gone = !(await p.page.$('.usr-modal')); await p.ctx.close()
    if (r.width < 380 || r.height < 780) throw new Error(`sheet ${r.width}x${r.height}`)
    if (!gone) throw new Error('did not close')
  })
  await test('users: the active toggle saves (and flips back)', async () => {
    const p = await open({ path: '/panel/users', auth: 'staff', writes: true })
    const sel = '.usr-row >> nth=3 >> label.toggle input'
    const before = await p.page.isChecked(sel)
    await p.page.click('.usr-row >> nth=3 >> label.toggle')
    if (await p.page.$('.cdlg-confirm')) await p.page.click('.cdlg-confirm')
    await p.page.waitForTimeout(1200)
    const mid = await p.page.isChecked(sel)
    await p.page.click('.usr-row >> nth=3 >> label.toggle')
    if (await p.page.$('.cdlg-confirm')) await p.page.click('.cdlg-confirm')
    await p.page.waitForTimeout(1200)
    const after = await p.page.isChecked(sel); await p.ctx.close()
    if (mid === before || after !== before) throw new Error(`${before} → ${mid} → ${after}`)
  })
  await test('payments: reject with a reason removes the card from the queue', async () => {
    const p = await open({ path: '/panel/payments', auth: 'staff', writes: true })
    const n0 = await p.page.$$eval('.pq-acts', (e) => e.length)
    await p.page.click('.pq-acts .btn-ghost >> nth=0'); await p.page.waitForSelector('.cdlg textarea')
    await p.page.fill('.cdlg textarea', 'رسید ناخوانا (آزمون)'); await p.page.click('.cdlg-confirm')
    await p.page.waitForTimeout(1500)
    const n1 = await p.page.$$eval('.pq-acts', (e) => e.length); await p.ctx.close()
    if (n1 !== n0 - 1) throw new Error(`${n0} → ${n1}`)
  })
  await test('payments: receipt thumbnail loads through the authenticated API', async () => {
    const p = await open({ path: '/panel/payments', auth: 'staff' })
    await p.page.waitForSelector('.pq-rcpt img', { timeout: 10000 })
    const ok = await p.page.$eval('.pq-rcpt img', (i) => i.complete && i.naturalWidth > 100); await p.ctx.close()
    if (!ok) throw new Error('receipt image did not load')
  })
  await test('transactions: status filter + detail page', async () => {
    const p = await open({ path: '/panel/transactions', auth: 'staff', w: 1440, h: 900 })
    await p.page.click('.tx-filter-row .btn-ghost >> nth=2'); await p.page.waitForTimeout(1000)
    const rows = await p.page.$$eval('.tx-row', (r) => r.length)
    await p.page.click('.tx-row >> nth=0 >> .tx-detail-btn')
    await p.page.waitForTimeout(1200)
    const path = await p.page.evaluate(() => location.pathname); await p.ctx.close()
    if (!rows) throw new Error('no rows after filter')
    if (!/\/panel\/transactions\/\d+/.test(path)) throw new Error('detail not opened: ' + path)
  })
  await test('services: filter "active" shows only active services', async () => {
    const p = await open({ path: '/panel/services', auth: 'staff' })
    await p.page.click('.svc-filter-btn >> nth=1'); await p.page.waitForTimeout(1200)
    const st = await p.page.$$eval('.svc-row td:nth-child(5)', (t) => t.map((x) => x.innerText.trim())); await p.ctx.close()
    if (!st.length || new Set(st).size !== 1) throw new Error([...new Set(st)].join(','))
  })
  await test('settings section on the phone: only that card + a save bar clear of the tab bar', async () => {
    const p = await open({ path: '/panel/settings/alerts', auth: 'staff' })
    const r = await p.page.evaluate(() => {
      const cards = [...document.querySelectorAll('.st-card, .sms-dev-card')].filter((c) => c.getBoundingClientRect().height > 0).length
      const bar = document.querySelector('.st-solo-bar')?.getBoundingClientRect(), nav = document.querySelector('.csp-botnav').getBoundingClientRect()
      return { cards, barBottom: bar?.bottom, navTop: nav.top }
    })
    await p.ctx.close()
    if (r.cards !== 1) throw new Error(`${r.cards} cards`)
    if (!r.barBottom || r.barBottom > r.navTop) throw new Error(`save bar ${r.barBottom} overlaps tab bar ${r.navTop}`)
  })
  await test('plans: add-plan form opens', async () => {
    const p = await open({ path: '/panel/plans', auth: 'staff' })
    await p.page.click('.pl-add'); await p.page.waitForTimeout(500)
    const n = await p.page.$$eval('input, select, textarea', (e) => e.filter((x) => x.getBoundingClientRect().height > 0).length); await p.ctx.close()
    if (n < 5) throw new Error(`${n} fields`)
  })
  await test('deleted users: archive lists the soft-deleted customer', async () => {
    const p = await open({ path: '/panel/users/deleted', auth: 'staff' })
    const t = await text(p.page); await p.ctx.close()
    if (!t.includes('left_user')) throw new Error('archived user missing')
  })
  await test('cards: every bank card is drawn as a card visual', async () => {
    const p = await open({ path: '/panel/cards', auth: 'staff', w: 1440, h: 900 })
    const t = await text(p.page); await p.ctx.close()
    for (const d of ['6037', '6219', '5022']) if (!t.replace(/\s/g, '').includes(d)) throw new Error('missing card ' + d)
  })
  await test('monitoring renders health rows from the stack', async () => {
    const p = await open({ path: '/panel/monitoring', auth: 'staff', w: 1440, h: 900 })
    const len = (await text(p.page)).length; await p.ctx.close()
    if (len < 200) throw new Error(`only ${len} chars`)
  })
  await test('apps: iPhone card installs via iCloud (button + QR); token shown on demand, never in a URL', async () => {
    const p = await open({ path: '/panel/apps', auth: 'staff' })
    const card = p.page.locator('.ap-ios')
    const href = await card.locator('a.ap-dl').getAttribute('href')
    const qr = await card.locator('.ap-qr img').evaluate((i) => i.complete && i.naturalWidth > 100)
    await card.locator('.ap-tok select').selectOption({ index: 1 })
    await card.locator('.ap-tok button.ap-link').click(); await p.page.waitForTimeout(800)
    const token = (await card.locator('.ap-tok .ap-copy-v code').last().textContent()).trim()
    const url = p.page.url()
    await card.locator('.ap-adv summary').click()
    const dl = await card.locator('.ap-adv .ap-actions button').isEnabled()
    await p.ctx.close()
    if (!/^https:\/\/www\.icloud\.com\/shortcuts\/[A-Za-z0-9]+\/?$/.test(href || '')) throw new Error('href ' + href)
    if (!qr) throw new Error('QR did not load')
    if (token.length < 20) throw new Error('token not shown')
    if (url.includes(token) || href.includes(token)) throw new Error('token leaked into a URL')
    if (!dl) throw new Error('advanced unsigned download disabled')
  })
  await test('logout from the Settings hub → login page', async () => {
    const p = await open({ path: '/panel/settings', auth: 'staff', writes: true })
    await p.page.click('.st-hub-item--danger'); await p.page.waitForTimeout(800)
    const path = await p.page.evaluate(() => location.pathname); await p.ctx.close()
    if (path !== '/panel/login') throw new Error(path)
  })
}
