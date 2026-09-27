// UI audit of the LOGGED-OUT pages + the Liquid Glass runtime, fully offline.
//
// The built SPAs are served from disk through Playwright request routing
// (no web server); /api/v1 public reads (config, theme, pages) are answered
// from fixtures; every non-GET request is aborted; nothing leaves the
// container (run it with --network none). No credentials of any kind.
//
//   docker run --rm --network none -v <repo>:/w -v <dist+pw>:/s \
//     mcr.microsoft.com/playwright:v1.49.1-noble \
//     node /w/scripts/ui-audit/public-audit.mjs /s/dist-user /s/dist-admin /s/out
//
// Output: <out>/audit.json + a console summary; exit 1 on any finding.
import { readFileSync, existsSync, mkdirSync, writeFileSync } from 'node:fs'
import { join, extname, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'

const require = createRequire(process.env.PW_REQUIRE || import.meta.url)
const { chromium } = require('playwright')

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO = join(HERE, '..', '..')
const [USER_DIST, ADMIN_DIST, OUT] = process.argv.slice(2)
const ONLY = process.env.ONLY || ''          // "glass" | "audit" | ''
const SHOTS = process.env.SHOTS === '1'
mkdirSync(OUT, { recursive: true })

const PALETTES = JSON.parse(readFileSync(join(REPO, 'backend/apps/settings_app/theme_palettes.json'), 'utf8'))
const ORIGIN = 'http://audit.test'
const THEMES = [
  ['caspian-light', 'Caspian', 'light'], ['caspian-dark', 'Caspian', 'dark'],
  ['aurora-dark', 'Midnight Aurora', 'dark'], ['aurora-light', 'Midnight Aurora', 'light'],
  ['frost', 'Royal Frost', 'light'],
]
const WIDTHS = [[360, 780], [390, 844], [768, 1024], [1440, 900]]
const PAGES = [['user', '/login'], ['user', '/register'], ['user', '/reset'], ['user', '/verify-email'], ['user', '/terms'], ['admin', '/panel/login']]

const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.webp': 'image/webp', '.png': 'image/png',
  '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.woff': 'font/woff', '.ico': 'image/x-icon', '.json': 'application/json', '.apk': 'application/octet-stream' }

function fixture(path, themeName) {
  if (path.startsWith('/api/v1/theme/')) return { name: themeName, palette: PALETTES[themeName] }
  if (path.startsWith('/api/v1/config/')) return { site_name_fa: 'کسپین تانل', site_name_en: 'Caspian Tunnel', logo: null, favicon: null,
    product_display_mode: 'grouped', support_telegram: 'caspian_support', email_verification_required: false }
  if (path.startsWith('/api/v1/pages/')) {
    const page = { slug: 'rules', title_fa: 'قوانین و مقررات', title_en: 'Terms and rules', is_active: true,
      body_fa: 'استفاده از سرویس به معنی پذیرش این قوانین است.\n\n1. حساب شخصی است.\n2. بازپرداخت طبق شرایط انجام می‌شود.',
      body_en: 'Using the service means accepting these rules.\n\n1. Accounts are personal.\n2. Refunds follow the policy.' }
    return path === '/api/v1/pages/' ? { results: [page] } : page
  }
  return null
}

async function route(page, themeName) {
  await page.route('**/*', async (r) => {
    const req = r.request()
    const url = new URL(req.url())
    if (url.origin !== ORIGIN) return r.abort()                       // nothing external, ever
    if (req.method() !== 'GET') return r.abort()                      // writes blocked
    if (url.pathname.startsWith('/ws/')) return r.abort()
    if (url.pathname.startsWith('/api/')) {
      const body = fixture(url.pathname, themeName)
      return body ? r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
        : r.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not in fixtures"}' })
    }
    const admin = url.pathname.startsWith('/panel/')
    const dist = admin ? ADMIN_DIST : USER_DIST
    const rel = admin ? url.pathname.slice('/panel'.length) : url.pathname
    let file = join(dist, decodeURIComponent(rel))
    if (!extname(file) || !existsSync(file)) file = join(dist, 'index.html')
    return r.fulfill({ status: 200, contentType: MIME[extname(file)] || 'application/octet-stream', body: readFileSync(file) })
  })
}

// in-page audit (runs in the browser)
function inPage(isPhone) {
  // rgb()/rgba() and the color(srgb r g b / a) form Chromium uses for color-mix() results
  const parse = (c) => {
    let m = c.match(/color\(srgb ([^)]+)\)/)
    if (m) { const p = m[1].split(/[ /]+/).filter(Boolean).map(Number); return [p[0] * 255, p[1] * 255, p[2] * 255, p.length > 3 ? p[3] : 1] }
    m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null
    const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]
  }
  const lum = ([r, g, b]) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4 }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b) }
  const over = (top, under) => { const a = top[3]; return [0, 1, 2].map((i) => top[i] * a + under[i] * (1 - a)).concat(1) }
  const visible = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' && Number(cs.opacity) > 0.05 }
  function bgOf(el) {
    const layers = []
    for (let n = el; n; n = n.parentElement) {
      const cs = getComputedStyle(n)
      if (cs.backgroundImage && cs.backgroundImage !== 'none' && !cs.backgroundImage.startsWith('url')) return { skip: 'gradient' }
      const c = parse(cs.backgroundColor)
      if (c && c[3] > 0) { layers.push(c); if (c[3] >= 0.999) break }
    }
    let base = parse(getComputedStyle(document.body).backgroundColor) || [255, 255, 255, 1]
    if (base[3] < 1) base = over(base, [255, 255, 255, 1])
    for (let i = layers.length - 1; i >= 0; i--) base = over(layers[i], base)
    return { bg: base }
  }
  const out = { lowContrast: [], tiny: [], smallTargets: [], unnamed: [], persianDigits: [], overflow: false }
  out.overflow = document.documentElement.scrollWidth > window.innerWidth + 1
  const seen = new Set()
  for (const el of document.body.querySelectorAll('*')) {
    if (!visible(el)) continue
    const direct = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())
    const cs = getComputedStyle(el)
    if (direct) {
      const fs = parseFloat(cs.fontSize)
      if (fs < 12 && !el.closest('.preview-banner')) out.tiny.push(`${el.tagName}.${el.className}`.slice(0, 80) + ` ${fs}px`)
      const fg = parse(cs.color)
      const b = bgOf(el)
      if (fg && b.bg) {
        const fgc = fg[3] < 1 ? over(fg, b.bg) : fg
        const L1 = lum(fgc), L2 = lum(b.bg)
        const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05)
        const large = fs >= 24 || (fs >= 18.66 && Number(cs.fontWeight) >= 700)
        if (ratio < (large ? 3 : 4.5)) {
          const k = `${el.tagName}.${el.className}`.slice(0, 70)
          if (!seen.has(k)) { seen.add(k); out.lowContrast.push(`${k} "${el.textContent.trim().slice(0, 24)}" ${ratio.toFixed(2)}`) }
        }
      }
    }
    if (el.matches('a[href], button, [role="button"], input:not([type="hidden"]), select, textarea, summary, label.toggle')) {
      const name = (el.getAttribute('aria-label') || el.getAttribute('title') || el.textContent || el.getAttribute('placeholder') || el.value || '').trim()
        || [...el.querySelectorAll('img[alt]')].map((i) => i.alt).join('').trim()
        || (el.id && document.querySelector(`label[for="${el.id}"]`)?.textContent.trim()) || (el.closest('label')?.textContent.trim())
      if (!name && !el.matches('input[type="checkbox"], input[type="radio"]')) out.unnamed.push(`${el.tagName}.${el.className}`.slice(0, 80))
      if (isPhone) {
        const r = el.getBoundingClientRect()
        const inText = el.tagName === 'A' && el.closest('p, li') && !el.className
        const hidden = el.matches('input[type="file"][hidden], input[type="checkbox"], input[type="radio"]')
        const tgt = el.matches('input') && el.closest('label.toggle') ? el.closest('label.toggle').getBoundingClientRect() : r
        if (!inText && !hidden && (tgt.height < 43.5 || tgt.width < 43.5)) out.smallTargets.push(`${el.tagName}.${el.className}`.slice(0, 70) + ` ${Math.round(tgt.width)}x${Math.round(tgt.height)}`)
      }
    }
  }
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    if (/[۰-۹٠-٩]/.test(n.textContent) && n.parentElement && visible(n.parentElement)) out.persianDigits.push(n.textContent.trim().slice(0, 40))
  }
  out.glass = document.documentElement.getAttribute('data-glass')
  return out
}

async function newPage(browser, { w, h, theme, mode, lang, init }) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, hasTouch: w < 768, isMobile: false })
  await ctx.addInitScript(([mode, lang]) => {
    try { localStorage.setItem('ct_mode', mode); localStorage.setItem('ct_lang', lang); localStorage.setItem('cta_lang', lang) } catch {}
  }, [mode, lang])
  if (init) await ctx.addInitScript(init)
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e.message || e).slice(0, 160)))
  await route(page, theme)
  return { ctx, page, errors }
}

const results = { renders: 0, findings: {}, glass: [] }
const add = (k, v) => { (results.findings[k] ||= []).push(v) }

async function audit(browser) {
  for (const [app, path] of PAGES) for (const [tkey, tname, mode] of THEMES) for (const lang of ['fa', 'en']) for (const [w, h] of WIDTHS) {
    const { ctx, page, errors } = await newPage(browser, { w, h, theme: tname, mode, lang })
    await page.goto(ORIGIN + path, { waitUntil: 'networkidle' }).catch(() => {})
    await page.waitForTimeout(250)
    const r = await page.evaluate(inPage, w < 768)
    const id = `${app}${path} ${tkey} ${lang} ${w}`
    results.renders++
    if (r.overflow) add('overflow', id)
    for (const k of ['lowContrast', 'tiny', 'smallTargets', 'unnamed', 'persianDigits']) for (const v of r[k]) add(k, `${id}: ${v}`)
    for (const e of errors) add('pageErrors', `${id}: ${e}`)
    if (SHOTS && (w === 390 || w === 1440) && lang === 'fa') await page.screenshot({ path: join(OUT, `${app}${path.replace(/\//g, '_')}-${tkey}-${w}.png`) })
    await ctx.close()
  }
}

// ---- Liquid Glass runtime suite ----
const HW = (cores, mem) => `Object.defineProperty(navigator,'hardwareConcurrency',{get:()=>${cores}});Object.defineProperty(navigator,'deviceMemory',{get:()=>${mem}});`
const MM = (q) => `(() => { const o = window.matchMedia.bind(window); window.matchMedia = (x) => x.includes(${JSON.stringify(q)}) ? { matches: true, media: x, addEventListener() {}, removeEventListener() {} } : o(x) })();`
async function glassSuite(browser) {
  const T = async (name, fn) => {
    try { await fn(); results.glass.push(['PASS', name]) } catch (e) { results.glass.push(['FAIL', name, String(e.message || e).slice(0, 200)]) }
  }
  const tierOf = async (opts, url = '/login') => {
    const { ctx, page } = await newPage(browser, { w: 390, h: 844, theme: 'Caspian', mode: 'light', lang: 'fa', ...opts })
    await page.goto(ORIGIN + url, { waitUntil: 'networkidle' })
    const tier = await page.evaluate(() => document.documentElement.getAttribute('data-glass'))
    return { ctx, page, tier }
  }
  const expectTier = async (name, opts, want, url) => T(name, async () => {
    const { ctx, tier } = await tierOf(opts, url); await ctx.close()
    if (tier !== want) throw new Error(`data-glass=${tier}, want ${want}`)
  })
  await expectTier('capable device (8 cores, 8 GB) → full', { init: HW(8, 8) }, 'full')
  await expectTier('4 cores → lite', { init: HW(4, 8) }, 'lite')
  await expectTier('4 GB RAM → lite', { init: HW(8, 4) }, 'lite')
  await expectTier('Save-Data → lite', { init: HW(8, 8) + "Object.defineProperty(navigator,'connection',{get:()=>({saveData:true})});" }, 'lite')
  await expectTier('prefers-reduced-transparency → solid', { init: HW(8, 8) + MM('prefers-reduced-transparency') }, 'solid')
  await expectTier('prefers-contrast: more → solid', { init: HW(8, 8) + MM('prefers-contrast') }, 'solid')
  await expectTier('no backdrop-filter support → lite', { init: HW(8, 8) + "(() => { const s = CSS.supports.bind(CSS); CSS.supports = (p, v) => /backdrop-filter/.test(p) ? false : s(p, v) })();" }, 'lite')
  await expectTier('remembered slow frames → lite', { init: HW(8, 8) + "localStorage.setItem('ct_glass_perf','slow');" }, 'lite')
  await expectTier('?glass=solid override', { init: HW(8, 8) }, 'solid', '/login?glass=solid')
  await expectTier('admin app picks the tier too', { init: HW(8, 8) }, 'full', '/panel/login')

  // computed material per tier (probe element carries the shared .lg class)
  for (const [tier, wantBlur, wantOpaque] of [['full', true, false], ['lite', false, false], ['solid', false, true]]) {
    for (const mode of ['light', 'dark']) await T(`material ${tier}/${mode}: blur=${wantBlur} opaque=${wantOpaque}`, async () => {
      const { ctx, page } = await tierOf({ mode, init: HW(8, 8) }, `/login?glass=${tier}`)
      const m = await page.evaluate(() => {
        const el = document.createElement('div'); el.className = 'lg-bar'; el.style.cssText = 'position:fixed;top:0;left:0;width:10px;height:10px'
        document.body.appendChild(el)
        const cs = getComputedStyle(el)
        return { bf: cs.backdropFilter || cs.webkitBackdropFilter, bg: cs.backgroundColor, img: cs.backgroundImage }
      })
      await ctx.close()
      const blur = /blur/.test(m.bf || '')
      if (blur !== wantBlur) throw new Error(`backdrop-filter=${m.bf}`)
      const alpha = (m.bg.match(/\/\s*([\d.]+)\)$/) || m.bg.match(/rgba\([^)]*,\s*([\d.]+)\)/) || [])[1]
      const opaque = alpha === undefined || Number(alpha) >= 0.999
      results.glass.push(['INFO', `material ${tier}: ${m.bg}${m.bf && m.bf !== 'none' ? ' + ' + m.bf : ''}`])
      if (tier === 'full' && Math.abs(Number(alpha) - 0.9) > 0.005) throw new Error(`bar tint alpha ${alpha}, want 0.90 (glass-contrast.mjs proves AA at 90%)`)
      if (wantOpaque && !opaque) throw new Error(`background ${m.bg} not opaque`)
      if (tier === 'full' && opaque) throw new Error(`full glass should be translucent, got ${m.bg}`)
    })
  }

  await T('scroll: lg-scrolled at >4px, lg-min scrolling down, expands scrolling up', async () => {
    const { ctx, page } = await tierOf({ init: HW(8, 8) })
    await page.evaluate(() => { const d = document.createElement('div'); d.style.height = '4000px'; document.body.appendChild(d) })
    const cls = () => page.evaluate(() => document.documentElement.className)
    await page.mouse.wheel(0, 300); await page.waitForTimeout(200)
    let c = await cls(); if (!/lg-scrolled/.test(c) || !/lg-min/.test(c)) throw new Error('after scroll down: ' + c)
    await page.mouse.wheel(0, -120); await page.waitForTimeout(200)
    c = await cls(); if (/lg-min/.test(c)) throw new Error('after scroll up: ' + c)
    await page.evaluate(() => window.scrollTo(0, 0)); await page.waitForTimeout(200)
    c = await cls(); if (/lg-scrolled/.test(c)) throw new Error('at top: ' + c)
    await ctx.close()
  })

  await T('reduced motion: glass transitions off', async () => {
    const { ctx, page } = await newPage(browser, { w: 390, h: 844, theme: 'Caspian', mode: 'light', lang: 'fa', init: HW(8, 8) })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.goto(ORIGIN + '/login', { waitUntil: 'networkidle' })
    const d = await page.evaluate(() => { const el = document.createElement('nav'); el.className = 'u-botnav'; document.body.appendChild(el); return getComputedStyle(el).transitionDuration })
    await ctx.close()
    if (!/^0s|^1e-05s|0\.00001s/.test(d)) throw new Error('transition-duration ' + d)
  })

  // smoke check only: headless Chromium paces rAF at a fixed 16.7 ms and has no
  // GPU, so it cannot show real blur cost — on devices lib/glass.js measures
  // frame times itself and drops to lite. This catches gross regressions.
  for (const tier of ['full', 'lite']) await T(`scroll smoothness (${tier}, 6× CPU throttle)`, async () => {
    const { ctx, page } = await tierOf({ init: HW(8, 8) }, `/login?glass=${tier}`)
    await page.evaluate(() => {
      const bar = document.createElement('header'); bar.className = 'csp-topbar'; bar.style.cssText = 'top:0;height:64px;z-index:50;position:sticky'
      document.body.prepend(bar)
      const long = document.createElement('div')
      long.innerHTML = Array.from({ length: 120 }, (_, i) => `<div class="card" style="margin:12px;height:80px">row ${i}</div>`).join('')
      document.body.appendChild(long)
    })
    const cdp = await ctx.newCDPSession(page)
    await cdp.send('Emulation.setCPUThrottlingRate', { rate: 6 })
    const stats = await page.evaluate(() => new Promise((res) => {
      const d = []; let last = 0, y = 0
      const step = (t) => { if (last) d.push(t - last); last = t; y += 24; window.scrollTo(0, y); if (d.length < 150) requestAnimationFrame(step); else res(d) }
      requestAnimationFrame(step)
    }))
    await ctx.close()
    const sorted = [...stats].sort((a, b) => a - b)
    const p50 = sorted[Math.floor(sorted.length * 0.5)], p95 = sorted[Math.floor(sorted.length * 0.95)]
    const long = stats.filter((x) => x > 34).length
    results.glass.push(['INFO', `frames ${tier}: p50 ${p50.toFixed(1)} ms, p95 ${p95.toFixed(1)} ms, >34ms ${long}/${stats.length}`])
  })
}

const browser = await chromium.launch()
if (ONLY !== 'audit') await glassSuite(browser)
if (ONLY !== 'glass') await audit(browser)
await browser.close()

writeFileSync(join(OUT, 'audit.json'), JSON.stringify(results, null, 1))
console.log(`renders: ${results.renders}`)
for (const [k, v] of Object.entries(results.findings)) {
  console.log(`${k}: ${v.length}`)
  for (const x of v.slice(0, 8)) console.log('   ' + x)
}
const gf = results.glass.filter((g) => g[0] === 'FAIL')
for (const g of results.glass) console.log(g.join('  '))
console.log(`glass suite: ${results.glass.filter((g) => g[0] === 'PASS').length} passed, ${gf.length} failed`)
const total = Object.values(results.findings).reduce((a, v) => a + v.length, 0)
process.exit(total || gf.length ? 1 : 0)
