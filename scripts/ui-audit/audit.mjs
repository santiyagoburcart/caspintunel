// UI audit of EVERY page (logged-out + logged-in, user + admin) and the phone
// density measurement. Runs against the isolated ui-audit stack (fake data);
// without API it audits only the logged-out pages from fixtures (offline).
//
//   scripts/ui-audit/run.sh audit | density      (builds, starts the stack, runs, tears down)
//   env: API USER_DIST ADMIN_DIST OUT  [MODE=audit|density] [SHOTS=1] [WORKERS=2] [PATHS=regex]
//
// Checks per render: horizontal overflow, text contrast (WCAG AA, composited
// backgrounds), text < 12px, tap targets < 44px on phones, Persian/Arabic
// digits, unnamed controls, page errors, and API calls that failed.
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { chromium, newPage, inPage, settle, apiGet, tokens, ORIGIN, API, THEMES, WIDTHS } from './lib.mjs'

const dists = { user: process.env.USER_DIST, admin: process.env.ADMIN_DIST }
const OUT = process.env.OUT || '/tmp/ui-audit'
const MODE = process.env.MODE || 'audit'
const SHOTS = process.env.SHOTS === '1'
const WORKERS = Number(process.env.WORKERS || 2)
mkdirSync(OUT, { recursive: true })

const PUBLIC = [['/login'], ['/register'], ['/reset'], ['/verify-email'], ['/terms'], ['/panel/login']].map(([p]) => [p, null])

async function appPages() {
  const t = await tokens()
  const mine = await (await fetch(API + '/api/v1/orders/', { headers: { Authorization: `Bearer ${t.user}` } })).json()
  const pendingOrder = (mine.results || mine).find((o) => o.status === 'pending_payment')
  const plans = await (await fetch(API + '/api/v1/plans/')).json()
  const users = await apiGet('/api/v1/admin/users/?search=audit-user&limit=1')
  const uid = (users.results || users)[0].id
  const pend = await apiGet('/api/v1/admin/payments/pending/')
  const pid = (pend.results || pend)[0].id
  const tx = await apiGet('/api/v1/admin/transactions/?status=approved&limit=1')
  const txid = (tx.results || tx)[0].id
  const svcs = await apiGet('/api/v1/admin/services/?search=pouya_main&limit=1')
  const sid = (svcs.results || svcs)[0].id
  const del = await apiGet('/api/v1/admin/deleted-users/?limit=1')
  const did = (del.results || del)[0]?.id
  return {
    ids: { pendingOrder: pendingOrder?.id, plan: (plans.results || plans)[0].id, uid, pid, txid, sid },
    user: ['/', '/store', `/checkout?plan=${(plans.results || plans)[0].id}`, `/checkout?order=${pendingOrder?.id}`,
      '/history', '/rules', '/profile', '/help'].map((p) => [p, 'user']),
    admin: ['/', '/users', '/users/deleted', ...(did ? [`/users/deleted/${did}`] : []), `/users/${uid}/orders`, '/plans', '/payments',
      `/payments/${pid}`, '/transactions', `/transactions/${txid}`, '/accounting', '/cards', '/monitoring', '/services',
      `/services/${sid}`, '/panel-link', '/bots', '/branding', '/settings', '/settings/email', '/settings/alerts',
      '/notifications', '/apps', '/pages', '/themes', '/roles'].map((p) => ['/panel' + (p === '/' ? '/' : p), 'staff']),
  }
}

const results = { renders: 0, findings: {}, apiFailures: {} }
const add = (k, v) => { (results.findings[k] ||= []).push(v) }

async function auditOne(browser, [path, auth], [tkey, tname, mode], lang, [w, h]) {
  const p = await newPage(browser, { w, h, theme: tname, mode, lang, auth, dists })
  const failed = []
  p.page.on('response', (r) => { if (r.url().includes('/api/') && r.status() >= 500) failed.push(`${r.status()} ${new URL(r.url()).pathname}`) })
  await p.page.goto(ORIGIN + path, { waitUntil: 'domcontentloaded' }).catch(() => {})
  await settle(p.page)
  const landed = new URL(p.page.url()).pathname
  const r = await p.page.evaluate(inPage, w < 768)
  const id = `${path} ${tkey} ${lang} ${w}`
  results.renders++
  if (auth && /\/login$/.test(landed)) add('bouncedToLogin', id)
  if (r.overflow) add('overflow', id)
  for (const k of ['lowContrast', 'tiny', 'smallTargets', 'unnamed', 'persianDigits', 'smallInputs']) for (const v of r[k]) add(k, `${id}: ${v}`)
  for (const e of p.errors) add('pageErrors', `${id}: ${e}`)
  for (const f of failed) (results.apiFailures[f] ||= 0, results.apiFailures[f]++)
  if (SHOTS && lang === 'fa' && (w === 390 || w === 1440) && (tkey === 'caspian-light' || tkey === 'caspian-dark')) {
    await p.page.screenshot({ path: join(OUT, `${path.replace(/[/?=&]/g, '_')}-${tkey}-${w}.png`), fullPage: w === 390 })
  }
  await p.ctx.close()
}

async function pool(jobs, n, fn) {
  let i = 0
  await Promise.all(Array.from({ length: n }, async () => { while (i < jobs.length) { const j = jobs[i++]; await fn(j) } }))
}

// ---- density: what fits in the first 390×844 viewport ----
const DENSITY = [
  ['user dashboard', '/', 'user', '.csp-svc', 'service cards', '.csp-dash-hero'],
  ['user store', '/store', 'user', '.csp-plan', 'plan cards', '.csp-store-hero'],
  ['user history', '/history', 'user', '.csp-hist-row', 'order rows', '.csp-hist-head'],
  ['user checkout (pay step)', 'CHECKOUT', 'user', '.card.mx-auto > :not(style)', 'blocks', null],
  ['admin dashboard', '/panel/', 'staff', '.dash .kpi, .dash .card', 'KPI tiles + cards', null],
  ['admin users', '/panel/users', 'staff', '.usr-row', 'user rows', '.usr-stats'],
  ['admin payments', '/panel/payments', 'staff', '.grid > .card.space-y-2', 'payment cards', null],
  ['admin services', '/panel/services', 'staff', '.svc-row', 'service rows', null],
  ['admin settings hub', '/panel/settings', 'staff', '.st-hub-item', 'hub rows', null],
]
function measure([sel, heroSel]) {
  const vis = (e) => { const r = e.getBoundingClientRect(), cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden' }
  const top = Math.max(0, ...[...document.querySelectorAll('.csp-topbar, .csp-mtop, header.lg-bar, .csp-auth-top')].filter(vis)
    .map((e) => e.getBoundingClientRect().bottom))
  const docked = [...document.querySelectorAll('.u-botnav, .csp-botnav, .m-actionbar, .st-solo-bar, .sed-mbar')].filter(vis)
    .map((e) => e.getBoundingClientRect()).filter((r) => r.bottom >= innerHeight - 110 && r.top < innerHeight)
  const bottom = Math.min(innerHeight, ...docked.map((r) => r.top))
  const items = [...document.querySelectorAll(sel)].filter(vis).map((e) => e.getBoundingClientRect())
  const full = items.filter((r) => r.top >= top - 1 && r.bottom <= bottom + 1)
  const partial = items.filter((r) => r.bottom > top && r.top < bottom).length - full.length
  const hero = heroSel && document.querySelector(heroSel)
  const hr = hero && hero.getBoundingClientRect()
  const firstItem = items.length ? Math.round(items[0].top) : null
  const avg = items.length ? Math.round(items.slice(0, 6).reduce((a, r) => a + r.height, 0) / Math.min(6, items.length)) : null
  return { top: Math.round(top), bottom: Math.round(bottom), total: items.length, full: full.length, partial,
    lastBottom: full.length ? Math.round(Math.max(...full.map((r) => r.bottom))) : null,
    hero: hr ? Math.round(hr.height) : null, heroPct: hr ? Math.round((hr.height / innerHeight) * 100) : null, firstItem, avgHeight: avg }
}
async function density(browser, ids) {
  const rows = []
  for (const [label, path0, auth, sel, unit, hero] of DENSITY) {
    const path = path0 === 'CHECKOUT' ? `/checkout?order=${ids.pendingOrder}` : path0
    const p = await newPage(browser, { w: 390, h: 844, theme: 'Caspian', mode: 'light', lang: 'fa', auth, dists })
    await p.page.goto(ORIGIN + path, { waitUntil: 'domcontentloaded' }); await settle(p.page)
    const m = await p.page.evaluate(measure, [sel, hero])
    if (SHOTS) await p.page.screenshot({ path: join(OUT, `density-${label.replace(/\W+/g, '-')}.png`) })
    await p.ctx.close()
    rows.push({ label, unit, ...m })
  }
  return rows
}

const browser = await chromium.launch()
if (MODE === 'density') {
  const { ids } = await appPages()
  const rows = await density(browser, ids)
  writeFileSync(join(OUT, 'density.json'), JSON.stringify(rows, null, 1))
  for (const r of rows) console.log(`${r.label.padEnd(26)} ${String(r.full).padStart(2)} full + ${r.partial} partial ${r.unit} (of ${r.total}); first at ${r.firstItem}px, avg ${r.avgHeight}px${r.hero != null ? `; hero ${r.hero}px = ${r.heroPct}%` : ''}; view ${r.top}–${r.bottom}`)
} else {
  const pages = [...PUBLIC]
  if (API) { const a = await appPages(); pages.push(...a.user, ...a.admin); console.log('ids', JSON.stringify(a.ids)) }
  const only = process.env.PATHS ? new RegExp(process.env.PATHS) : null   // e.g. PATHS='^/panel/(cards|payments)'
  const jobs = []
  for (const pg of pages.filter(([p]) => !only || only.test(p))) for (const th of THEMES) for (const lang of ['fa', 'en']) for (const wh of WIDTHS) jobs.push([pg, th, lang, wh])
  console.log(`${pages.length} pages → ${jobs.length} renders`)
  let done = 0
  await pool(jobs, WORKERS, async (j) => {
    await auditOne(browser, ...j).catch((e) => add('auditErrors', `${j[0][0]} ${j[1][0]} ${j[2]} ${j[3][0]}: ${e.message.slice(0, 120)}`))
    if (++done % 100 === 0) console.log(`  ${done}/${jobs.length}`)
  })
  writeFileSync(join(OUT, 'audit.json'), JSON.stringify(results, null, 1))
  console.log(`renders: ${results.renders}`)
  for (const [k, v] of Object.entries(results.findings)) {
    console.log(`${k}: ${v.length}`)
    const uniq = [...new Set(v.map((x) => x.replace(/^\S+ \S+ \S+ \d+: /, '')))]
    for (const x of uniq.slice(0, 12)) console.log('   ' + x)
  }
  console.log('api 5xx:', JSON.stringify(results.apiFailures))
}
await browser.close()
const total = Object.values(results.findings).reduce((a, v) => a + v.length, 0)
process.exit(total ? 1 : 0)
