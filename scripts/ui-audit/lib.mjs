// Shared helpers for the UI audits and browser suites (Playwright 1.49).
// Pages are served from the BUILT SPAs on disk through request routing; /api is
// either answered from fixtures (offline) or proxied to the isolated ui-audit
// stack (API = http://web:8000 — fake data, never the live API).
import { readFileSync, existsSync } from 'node:fs'
import { join, extname, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'

const require = createRequire(process.env.PW_REQUIRE || import.meta.url)
export const { chromium } = require('playwright')

export const HERE = dirname(fileURLToPath(import.meta.url))
export const REPO = join(HERE, '..', '..')
export const ORIGIN = 'http://audit.test'
export const API = process.env.API || ''            // '' → offline fixtures
export const PALETTES = JSON.parse(readFileSync(join(REPO, 'backend/apps/settings_app/theme_palettes.json'), 'utf8'))
export const THEMES = [
  ['caspian-light', 'Caspian', 'light'], ['caspian-dark', 'Caspian', 'dark'],
  ['aurora-dark', 'Midnight Aurora', 'dark'], ['aurora-light', 'Midnight Aurora', 'light'],
  ['frost', 'Royal Frost', 'light'],
]
export const WIDTHS = [[360, 780], [390, 844], [768, 1024], [1440, 900]]
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.webp': 'image/webp', '.png': 'image/png',
  '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.woff': 'font/woff', '.ico': 'image/x-icon', '.json': 'application/json' }

export const HW = (cores, mem) => `Object.defineProperty(navigator,'hardwareConcurrency',{get:()=>${cores}});Object.defineProperty(navigator,'deviceMemory',{get:()=>${mem}});`
export const MM = (q) => `(() => { const o = window.matchMedia.bind(window); window.matchMedia = (x) => x.includes(${JSON.stringify(q)}) ? { matches: true, media: x, addEventListener() {}, removeEventListener() {} } : o(x) })();`

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

/** Serve dists + answer /api. `writes`: let non-GET API calls through (stack only). */
export async function route(page, { theme, userDist, adminDist, writes = false, log }) {
  await page.route('**/*', async (r) => {
    const req = r.request()
    const url = new URL(req.url())
    if (url.origin !== ORIGIN) return r.abort()                       // nothing external, ever
    if (url.pathname.startsWith('/ws/')) return r.abort()
    if (url.pathname.startsWith('/api/')) {
      if (req.method() !== 'GET' && !(writes && API)) { log?.push(`blocked ${req.method()} ${url.pathname}`); return r.abort() }
      if (url.pathname.startsWith('/api/v1/theme/') || !API) {
        const body = fixture(url.pathname, theme)
        return body ? r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
          : r.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not in fixtures"}' })
      }
      try {
        const resp = await r.fetch({ url: API + url.pathname + url.search, timeout: 30000 })
        return r.fulfill({ response: resp })
      } catch (e) { log?.push(`api error ${url.pathname}: ${e.message}`); return r.abort() }
    }
    if (req.method() !== 'GET') return r.abort()
    const admin = url.pathname.startsWith('/panel/')
    const dist = admin ? adminDist : userDist
    const rel = admin ? url.pathname.slice('/panel'.length) : url.pathname
    let file = join(dist, decodeURIComponent(rel))
    if (!extname(file) || !existsSync(file)) file = join(dist, 'index.html')
    return r.fulfill({ status: 200, contentType: MIME[extname(file)] || 'application/octet-stream', body: readFileSync(file) })
  })
}

/** Fake-account logins on the isolated stack; tokens are re-issued every 8 minutes. */
const tok = { at: 0 }
export async function tokens() {
  if (!API) return null
  if (Date.now() - tok.at < 8 * 60 * 1000) return tok
  const post = async (path, body) => {
    const r = await fetch(API + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    if (!r.ok) throw new Error(`${path} → ${r.status}`)
    return r.json()
  }
  const u = await post('/api/v1/auth/login/', { username: 'audit-user', password: 'audit-pass-123' })
  const s = await post('/api/v1/admin/auth/login/', { username: 'audit-admin', password: 'audit-pass-123' })
  Object.assign(tok, { at: Date.now(), user: u.access, staff: s.access })
  return tok
}
export async function apiGet(path, who = 'staff') {
  const t = await tokens()
  const r = await fetch(API + path, { headers: { Authorization: `Bearer ${t[who]}` } })
  if (!r.ok) throw new Error(`${path} → ${r.status}`)
  return r.json()
}

export async function newPage(browser, { w, h, theme, mode, lang, init, auth, dists, writes, touch }) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, hasTouch: touch ?? w < 768 })
  const t = auth ? await tokens() : null
  await ctx.addInitScript(([mode, lang, t, auth]) => {
    try {
      localStorage.setItem('ct_mode', mode); localStorage.setItem('ct_lang', lang); localStorage.setItem('cta_lang', lang)
      if (t && auth === 'user') localStorage.setItem('ct_access', t.user)
      if (t && auth === 'staff') localStorage.setItem('cta_access', t.staff)
    } catch {}
  }, [mode, lang, t && { user: t.user, staff: t.staff }, auth])
  if (init) await ctx.addInitScript(init)
  const page = await ctx.newPage()
  const errors = [], log = []
  page.on('pageerror', (e) => errors.push(String(e.message || e).slice(0, 160)))
  await route(page, { theme, userDist: dists.user, adminDist: dists.admin, writes, log })
  return { ctx, page, errors, log }
}

/** In-page audit (runs in the browser). */
export function inPage(isPhone) {
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
      // paint order inside one element: background-color at the bottom, then the
      // image layers from last to first; each gradient layer is judged by its
      // first colour stop (a glow / sheen starts at its strongest colour)
      const own = []
      const c = parse(cs.backgroundColor)
      if (c && c[3] > 0) own.push(c)
      if (cs.backgroundImage && cs.backgroundImage !== 'none' && !cs.backgroundImage.includes('url(')) {
        const imgLayers = []; let depth = 0, cur = ''
        for (const ch of cs.backgroundImage) {
          if (ch === '(') depth++
          if (ch === ')') depth--
          if (ch === ',' && depth === 0) { imgLayers.push(cur); cur = '' } else cur += ch
        }
        imgLayers.push(cur)
        for (const layer of imgLayers.reverse()) { const stop = parse(layer); if (stop && stop[3] > 0) own.push(stop) }
      }
      for (const l of own.reverse()) layers.push(l)       // topmost first, like the outer loop
      if (own.some((l) => l[3] >= 0.999)) break
    }
    let base = parse(getComputedStyle(document.body).backgroundColor) || [255, 255, 255, 1]
    if (base[3] < 1) base = over(base, [255, 255, 255, 1])
    for (let i = layers.length - 1; i >= 0; i--) base = over(layers[i], base)
    return { bg: base }
  }
  const out = { lowContrast: [], tiny: [], smallTargets: [], unnamed: [], persianDigits: [], smallInputs: [], overflow: false }
  out.overflow = document.documentElement.scrollWidth > window.innerWidth + 1
  const seen = new Set()
  for (const el of document.body.querySelectorAll('*')) {
    if (!visible(el)) continue
    if (el.closest('svg, .preview-banner, [aria-hidden="true"]')) continue
    const direct = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())
    const cs = getComputedStyle(el)
    if (direct) {
      const fs = parseFloat(cs.fontSize)
      if (fs < 12) out.tiny.push(`${el.tagName}.${el.className}`.slice(0, 80) + ` ${fs}px`)
      const fg = parse(cs.color)
      const b = bgOf(el)
      if (fg && b.bg && !el.closest('input, textarea, select, img')) {
        const fgc = fg[3] < 1 ? over(fg, b.bg) : fg
        const L1 = lum(fgc), L2 = lum(b.bg)
        const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05)
        const large = fs >= 24 || (fs >= 18.66 && Number(cs.fontWeight) >= 700)
        const disabled = el.closest('button:disabled, [aria-disabled="true"], fieldset:disabled')
        if (!disabled && ratio < (large ? 3 : 4.5)) {
          const k = `${el.tagName}.${el.className}`.slice(0, 70)
          if (!seen.has(k)) { seen.add(k); out.lowContrast.push(`${k} "${el.textContent.trim().slice(0, 24)}" ${ratio.toFixed(2)}`) }
        }
      }
    }
    if (el.matches('a[href], button, [role="button"], input:not([type="hidden"]), select, textarea, summary, label.toggle')) {
      const name = (el.getAttribute('aria-label') || el.getAttribute('title') || el.textContent || el.getAttribute('placeholder') || el.value || '').trim()
        || [...el.querySelectorAll('img[alt]')].map((i) => i.alt).join('').trim()
        || (el.id && document.querySelector(`label[for="${el.id}"]`)?.textContent.trim()) || (el.closest('label')?.textContent.trim())
        || (el.getAttribute('aria-labelledby') && document.getElementById(el.getAttribute('aria-labelledby'))?.textContent.trim())
      if (!name && !el.matches('input[type="checkbox"], input[type="radio"], input[type="file"]')) out.unnamed.push(`${el.tagName}.${el.className}`.slice(0, 80))
      if (isPhone && el.matches('input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=file]), select, textarea') && parseFloat(cs.fontSize) < 16)
        out.smallInputs.push(`${el.tagName}.${el.className}`.slice(0, 70) + ` ${cs.fontSize}`)
      if (isPhone) {
        const r = el.getBoundingClientRect()
        const inText = el.tagName === 'A' && el.closest('p, li') && !el.className
        const hidden = el.matches('input[type="file"], input[type="checkbox"], input[type="radio"]')
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

/** Wait until the SPA has rendered real content (spinners gone, network quiet). */
export async function settle(page) {
  await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {})
  await page.waitForFunction(() => !document.querySelector('.animate-spin, .skeleton, .btn-spin') ||
    document.readyState === 'complete', null, { timeout: 8000 }).catch(() => {})
  await page.waitForTimeout(300)
}
