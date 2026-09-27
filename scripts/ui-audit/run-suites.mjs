// Browser suites (regression checks) — run against the isolated ui-audit stack.
//
//   scripts/ui-audit/run.sh suites            (builds, starts the stack, runs, tears down)
//   env: API=http://web:8000  USER_DIST=…  ADMIN_DIST=…  OUT=…  SUITES=glass,shell,…
//
// Suites live in ./suites/*.mjs and export `name` + `run({ browser, test, open, info })`.
// `open(opts)` opens a page on the served build (theme/mode/lang/viewport/auth);
// `test(name, fn)` records one check. Exit 1 if any check fails.
import { writeFileSync, mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { chromium, newPage, settle, ORIGIN, HERE } from './lib.mjs'

const dists = { user: process.env.USER_DIST, admin: process.env.ADMIN_DIST }
const OUT = process.env.OUT || '/tmp/ui-suites'
mkdirSync(OUT, { recursive: true })
const wanted = (process.env.SUITES || 'glass,shell,invariants,user-flows,admin-flows').split(',')

const browser = await chromium.launch()
const all = []
for (const name of wanted) {
  const mod = await import(join(HERE, 'suites', `${name}.mjs`))
  const results = []
  const test = async (title, fn) => {
    const t0 = Date.now()
    try { await fn(); results.push(['PASS', title, Date.now() - t0]) } catch (e) {
      results.push(['FAIL', title, String(e?.message || e).split('\n')[0].slice(0, 240)])
    }
  }
  const info = (msg) => results.push(['INFO', msg])
  const open = async ({ path = '/', w = 390, h = 844, theme = 'Caspian', mode = 'light', lang = 'fa', auth, init, writes, touch, wait = true } = {}) => {
    const p = await newPage(browser, { w, h, theme, mode, lang, init, auth, dists, writes, touch })
    if (path) {
      await p.page.goto(ORIGIN + path, { waitUntil: 'domcontentloaded' })
      if (wait) await settle(p.page)
    }
    return p
  }
  try { await mod.run({ browser, test, open, info, OUT }) } catch (e) { results.push(['FAIL', `suite crashed: ${e.message}`]) }
  const pass = results.filter((r) => r[0] === 'PASS').length
  const fail = results.filter((r) => r[0] === 'FAIL').length
  console.log(`\n== suite ${mod.name || name}: ${pass} passed, ${fail} failed`)
  for (const r of results) if (r[0] !== 'PASS') console.log('  ' + r.slice(0, 3).join('  '))
  all.push({ suite: name, pass, fail, results })
}
await browser.close()
writeFileSync(join(OUT, 'suites.json'), JSON.stringify(all, null, 1))
const P = all.reduce((a, s) => a + s.pass, 0), F = all.reduce((a, s) => a + s.fail, 0)
console.log(`\nALL SUITES: ${P} passed, ${F} failed (${all.map((s) => `${s.suite} ${s.pass}/${s.pass + s.fail}`).join(', ')})`)
process.exit(F ? 1 : 0)
