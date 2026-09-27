// Suite 2 — navigation shell: tab bars, drawers, desktop rails, Settings hub
// reachability, inner-page back button, auth redirects (user + admin).
export const name = 'shell'

const eq = (a, b, what) => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${what}: ${JSON.stringify(a)} ≠ ${JSON.stringify(b)}`) }
const hrefs = (page, sel) => page.$$eval(sel, (as) => as.filter((a) => a.getAttribute('href') && a.getBoundingClientRect().width > 0)
  .map((a) => new URL(a.href).pathname.replace(/(.)\/$/, '$1')))

export async function run({ test, open }) {
  const USER_TABS = ['/', '/store', '/history', '/profile', '/help']   // DOM order (Layout.jsx links)
  for (const theme of ['Caspian', 'Midnight Aurora']) {
    await test(`user (${theme}): phone tab bar = 5 tabs`, async () => {
      const p = await open({ path: '/', auth: 'user', theme, mode: theme === 'Caspian' ? 'light' : 'dark' })
      const h = await hrefs(p.page, '.u-botnav a'); await p.ctx.close()
      eq(h, USER_TABS, 'tabs')
    })
    await test(`user (${theme}): desktop nav has all 6 pages, no tab bar`, async () => {
      const p = await open({ path: '/', auth: 'user', theme, w: 1440, h: 900, mode: theme === 'Caspian' ? 'light' : 'dark' })
      const nav = await hrefs(p.page, theme === 'Caspian' ? '.csp-nav a' : 'header nav a')
      const bar = await p.page.$eval('.u-botnav', (n) => getComputedStyle(n).display); await p.ctx.close()
      eq([...nav].sort(), ['/', '/help', '/history', '/profile', '/rules', '/store'], 'nav')
      if (bar !== 'none') throw new Error('tab bar visible on desktop')
    })
  }
  for (const to of USER_TABS) await test(`user: tab ${to} navigates and lights up`, async () => {
    const p = await open({ path: to === '/' ? '/store' : '/', auth: 'user' })
    await p.page.click(`.u-botnav a[href="${to}"]`); await p.page.waitForTimeout(400)
    const r = await p.page.evaluate((to) => ({ path: location.pathname, on: document.querySelector(`.u-botnav a[href="${to}"]`).classList.contains('on') }), to)
    await p.ctx.close()
    if (r.path !== to || !r.on) throw new Error(JSON.stringify(r))
  })
  await test('user: phone drawer lists all 6 pages incl. rules', async () => {
    const p = await open({ path: '/', auth: 'user' })
    await p.page.click('.csp-menu-btn'); await p.page.waitForSelector('.csp-drawer')
    const h = await hrefs(p.page, '.csp-drawer a'); await p.ctx.close()
    eq([...h].sort(), ['/', '/help', '/history', '/profile', '/rules', '/store'], 'drawer')
  })
  await test('user: language switch flips dir + lang and persists', async () => {
    const p = await open({ path: '/', auth: 'user' })
    const before = await p.page.evaluate(() => [document.documentElement.dir, document.documentElement.lang])
    await p.page.click('.csp-lang'); await p.page.waitForTimeout(300)
    // (a reload would re-run the harness init script that seeds the language)
    const after = await p.page.evaluate(() => [document.documentElement.dir, document.documentElement.lang, localStorage.getItem('ct_lang')])
    await p.ctx.close()
    eq(before, ['rtl', 'fa'], 'before'); eq(after, ['ltr', 'en', 'en'], 'after (dir, lang, stored)')
  })
  await test('user: logged-out visit to / lands on /login', async () => {
    const p = await open({ path: '/' })
    const path = await p.page.evaluate(() => location.pathname); await p.ctx.close()
    if (path !== '/login') throw new Error(path)
  })

  // ---- admin ----
  const ADMIN_TABS = ['/panel', '/panel/users', '/panel/payments', '/panel/services', '/panel/settings']
  await test('admin: phone tab bar = 5 tabs + live pending badge on payments', async () => {
    const p = await open({ path: '/panel/', auth: 'staff' })
    const h = await hrefs(p.page, '.csp-botnav a')
    const badge = await p.page.$eval('.csp-bn-centre', (a) => a.getAttribute('href') + '|' + (a.querySelector('.csp-bn-badge')?.textContent || ''))
    await p.ctx.close()
    eq(h, ADMIN_TABS, 'tabs')
    if (!/^\/panel\/payments\|\d+$/.test(badge)) throw new Error('badge ' + badge)
  })
  for (const to of ADMIN_TABS) await test(`admin: tab ${to} navigates and lights up`, async () => {
    const p = await open({ path: to === '/panel' ? '/panel/users' : '/panel/', auth: 'staff' })
    await p.page.click(`.csp-botnav a[href="${to}"]`); await p.page.waitForTimeout(500)
    const r = await p.page.evaluate((to) => ({ path: location.pathname, on: document.querySelector(`.csp-botnav a[href="${to}"]`).classList.contains('on') }), to)
    await p.ctx.close()
    if (r.path.replace(/\/$/, '') !== to.replace(/\/$/, '') || !r.on) throw new Error(JSON.stringify(r))
  })
  await test('admin: every desktop sidebar page is reachable on a phone (tab bar + Settings hub)', async () => {
    const d = await open({ path: '/panel/', auth: 'staff', w: 1440, h: 900 })
    const rail = await hrefs(d.page, '.csp-rail a.csp-link'); await d.ctx.close()
    const m = await open({ path: '/panel/settings', auth: 'staff' })
    const hub = await hrefs(m.page, '.st-hub-item'); await m.ctx.close()
    const reach = new Set([...ADMIN_TABS, ...hub])
    const missing = rail.filter((x) => !reach.has(x))
    if (rail.length < 16) throw new Error(`rail has only ${rail.length} links`)
    if (missing.length) throw new Error('not reachable on phone: ' + missing.join(', '))
  })
  await test('admin: inner page shows back + title; back returns', async () => {
    const p = await open({ path: '/panel/settings', auth: 'staff' })
    await p.page.click('.st-hub-item[href="/panel/transactions"]'); await p.page.waitForTimeout(500)
    const title = await p.page.$eval('.csp-mtop-title', (e) => e.textContent.trim())
    await p.page.click('.csp-mtop-back'); await p.page.waitForTimeout(400)
    const path = await p.page.evaluate(() => location.pathname); await p.ctx.close()
    if (!title) throw new Error('no title')
    if (path !== '/panel/settings') throw new Error('back → ' + path)
  })
  await test('admin: desktop shows rail + top bar, hides phone chrome', async () => {
    const p = await open({ path: '/panel/', auth: 'staff', w: 1440, h: 900 })
    const r = await p.page.evaluate(() => ['.csp-rail', '.csp-topbar', '.csp-mtop', '.csp-botnav'].map((s) => getComputedStyle(document.querySelector(s)).display))
    await p.ctx.close()
    if (r[0] === 'none' || r[1] === 'none' || r[2] !== 'none' || r[3] !== 'none') throw new Error(r.join(','))
  })
  await test('admin (Aurora): legacy sidebar on desktop, drawer on phone, same links', async () => {
    const d = await open({ path: '/panel/', auth: 'staff', theme: 'Midnight Aurora', mode: 'dark', w: 1440, h: 900 })
    const side = await hrefs(d.page, 'aside.admin-side a'); await d.ctx.close()
    const m = await open({ path: '/panel/', auth: 'staff', theme: 'Midnight Aurora', mode: 'dark' })
    await m.page.click('header button.md\\:hidden'); await m.page.waitForTimeout(300)
    const drawer = await hrefs(m.page, 'aside.admin-side a'); await m.ctx.close()
    if (side.length < 16) throw new Error(`sidebar ${side.length}`)
    eq([...drawer].sort(), [...side].sort(), 'drawer vs sidebar')
  })
  await test('admin: logged-out visit lands on /panel/login', async () => {
    const p = await open({ path: '/panel/users' })
    const path = await p.page.evaluate(() => location.pathname); await p.ctx.close()
    if (path !== '/panel/login') throw new Error(path)
  })
}
