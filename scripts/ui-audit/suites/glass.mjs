// Suite 1 — Liquid Glass runtime: tier selection for every heuristic, material
// per tier, scroll states, reduced motion, logged-in chrome, frame smoke check.
import { HW, MM } from '../lib.mjs'

export const name = 'glass'

export async function run({ test, open, info }) {
  const tier = (p) => p.page.evaluate(() => document.documentElement.getAttribute('data-glass'))
  const expectTier = (title, opts, want) => test(title, async () => {
    const p = await open({ path: '/login', ...opts })
    const t = await tier(p); await p.ctx.close()
    if (t !== want) throw new Error(`data-glass=${t}, want ${want}`)
  })
  await expectTier('capable device (8 cores, 8 GB) → full', { init: HW(8, 8) }, 'full')
  await expectTier('4 cores → lite', { init: HW(4, 8) }, 'lite')
  await expectTier('4 GB RAM → lite', { init: HW(8, 4) }, 'lite')
  await expectTier('Save-Data → lite', { init: HW(8, 8) + "Object.defineProperty(navigator,'connection',{get:()=>({saveData:true})});" }, 'lite')
  await expectTier('prefers-reduced-transparency → solid', { init: HW(8, 8) + MM('prefers-reduced-transparency') }, 'solid')
  await expectTier('prefers-contrast: more → solid', { init: HW(8, 8) + MM('prefers-contrast') }, 'solid')
  await expectTier('no backdrop-filter support → lite', { init: HW(8, 8) + "(() => { const s = CSS.supports.bind(CSS); CSS.supports = (p, v) => /backdrop-filter/.test(p) ? false : s(p, v) })();" }, 'lite')
  await expectTier('remembered slow frames → lite', { init: HW(8, 8) + "localStorage.setItem('ct_glass_perf','slow');" }, 'lite')
  await test('?glass=solid override is remembered, ?glass=auto clears it', async () => {
    const p = await open({ path: '/login?glass=solid', init: HW(8, 8) })
    const a = await tier(p)
    await p.page.goto(p.page.url().replace('?glass=solid', '')); const b = await tier(p)
    await p.page.goto(p.page.url() + '?glass=auto'); const c = await tier(p)
    await p.ctx.close()
    if (a !== 'solid' || b !== 'solid' || c !== 'full') throw new Error(`${a} / ${b} / ${c}`)
  })
  await expectTier('admin app picks the tier too', { path: '/panel/login', init: HW(8, 8) }, 'full')

  for (const [t, wantBlur, wantOpaque] of [['full', true, false], ['lite', false, false], ['solid', false, true]]) {
    for (const mode of ['light', 'dark']) await test(`material ${t}/${mode}`, async () => {
      const p = await open({ path: `/login?glass=${t}`, mode, init: HW(8, 8) })
      const m = await p.page.evaluate(() => {
        const el = document.createElement('div'); el.className = 'lg-bar'; el.style.cssText = 'position:fixed;top:0;left:0;width:10px;height:10px'
        document.body.appendChild(el)
        const cs = getComputedStyle(el)
        return { bf: cs.backdropFilter || cs.webkitBackdropFilter, bg: cs.backgroundColor }
      })
      await p.page.goto(p.page.url().replace(/\?glass=\w+/, '?glass=auto')); await p.ctx.close()
      if (/blur/.test(m.bf || '') !== wantBlur) throw new Error(`backdrop-filter=${m.bf}`)
      const alpha = (m.bg.match(/\/\s*([\d.]+)\)$/) || m.bg.match(/rgba\([^)]*,\s*([\d.]+)\)/) || [])[1]
      const opaque = alpha === undefined || Number(alpha) >= 0.999
      if (wantOpaque !== opaque) throw new Error(`background ${m.bg}`)
      if (t === 'full' && Math.abs(Number(alpha) - 0.9) > 0.005) throw new Error(`bar tint ${alpha}, want 0.90`)
    })
  }

  await test('scroll: lg-scrolled past 4px, lg-min scrolling down, expands scrolling up and at top', async () => {
    const p = await open({ path: '/login', init: HW(8, 8) })
    const { page } = p
    await page.evaluate(() => { const d = document.createElement('div'); d.style.height = '4000px'; document.body.appendChild(d) })
    const cls = () => page.evaluate(() => document.documentElement.className)
    await page.mouse.wheel(0, 300); await page.waitForTimeout(250)
    let c = await cls(); if (!/lg-scrolled/.test(c) || !/lg-min/.test(c)) throw new Error('down: ' + c)
    await page.mouse.wheel(0, -120); await page.waitForTimeout(250)
    c = await cls(); if (/lg-min/.test(c)) throw new Error('up: ' + c)
    await page.evaluate(() => window.scrollTo(0, 0)); await page.waitForTimeout(250)
    c = await cls(); await p.ctx.close(); if (/lg-scrolled/.test(c)) throw new Error('top: ' + c)
  })

  await test('reduced motion: tab-bar transitions off', async () => {
    const p = await open({ path: '/login', init: HW(8, 8), wait: false })
    await p.page.emulateMedia({ reducedMotion: 'reduce' })
    await p.page.reload()
    const d = await p.page.evaluate(() => { const el = document.createElement('nav'); el.className = 'u-botnav'; document.body.appendChild(el); return getComputedStyle(el).transitionDuration })
    await p.ctx.close()
    if (!/^(0s|1e-05s|0\.00001s)/.test(d)) throw new Error('transition-duration ' + d)
  })

  // logged-in chrome on the real app (fake stack data)
  for (const [path, auth, bar, nav] of [['/', 'user', '.csp-topbar', '.u-botnav'], ['/panel/', 'staff', '.csp-mtop', '.csp-botnav']]) {
    await test(`${auth}: floating capsule tab bar + glass top bar (390px)`, async () => {
      const p = await open({ path, auth, init: HW(8, 8) })
      const m = await p.page.evaluate(([bar, nav]) => {
        const b = getComputedStyle(document.querySelector(bar)), n = document.querySelector(nav)
        const r = n.getBoundingClientRect(), ns = getComputedStyle(n)
        return { barBlur: b.backdropFilter, navBlur: ns.backdropFilter, left: r.left, bottomGap: innerHeight - r.bottom, radius: parseFloat(ns.borderTopLeftRadius),
          items: [...n.querySelectorAll('a')].map((a) => { const q = a.getBoundingClientRect(); return [Math.round(q.width), Math.round(q.height)] }) }
      }, [bar, nav])
      await p.ctx.close()
      if (!/blur/.test(m.barBlur) || !/blur/.test(m.navBlur)) throw new Error(`blur top=${m.barBlur} nav=${m.navBlur}`)
      if (m.left < 8 || m.bottomGap < 8 || m.radius < 20) throw new Error(`not floating: left ${m.left} gap ${m.bottomGap} radius ${m.radius}`)
      if (m.items.length !== 5 || m.items.some(([w, h]) => w < 44 || h < 44)) throw new Error('tabs ' + JSON.stringify(m.items))
    })
    await test(`${auth}: tab bar minimizes on scroll-down, tabs stay ≥44px`, async () => {
      const p = await open({ path, auth, init: HW(8, 8) })
      await p.page.evaluate(() => { const d = document.createElement('div'); d.style.height = '3000px'; document.querySelector('main').appendChild(d) })
      await p.page.mouse.wheel(0, 400); await p.page.waitForTimeout(600)
      const m = await p.page.evaluate((nav) => ({ min: document.documentElement.classList.contains('lg-min'),
        items: [...document.querySelectorAll(nav + ' a')].map((a) => { const q = a.getBoundingClientRect(); return [Math.round(q.width), Math.round(q.height)] }) }), nav)
      await p.ctx.close()
      if (!m.min) throw new Error('lg-min not set')
      if (m.items.some(([w, h]) => w < 44 || h < 44)) throw new Error('minimized tabs ' + JSON.stringify(m.items))
    })
  }
  await test('content cards never blur (dashboard, Aurora dark)', async () => {
    const p = await open({ path: '/', auth: 'user', theme: 'Midnight Aurora', mode: 'dark', init: HW(8, 8) })
    const n = await p.page.evaluate(() => [...document.querySelectorAll('.card, .glass:not(.lg-bar):not(.lg-drawer):not(.admin-side)')]
      .filter((e) => /blur/.test(getComputedStyle(e).backdropFilter)).length)
    await p.ctx.close()
    if (n) throw new Error(`${n} content cards with backdrop blur`)
  })
  await test('blur layers on a logged-in phone screen ≤ 2', async () => {
    const p = await open({ path: '/', auth: 'user', init: HW(8, 8) })
    const n = await p.page.evaluate(() => [...document.querySelectorAll('body *')].filter((e) => {
      const r = e.getBoundingClientRect(); return r.width && r.height && /blur/.test(getComputedStyle(e).backdropFilter)
    }).length)
    await p.ctx.close()
    if (n > 2) throw new Error(`${n} blurred layers`)
    info(`blurred layers on the user dashboard (phone): ${n}`)
  })
}
