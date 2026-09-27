// Suite 3 — design-system invariants from CLAUDE.md: toggles ON #11AB53 / OFF
// dark gray in every theme, one popup (ConfirmDialog, never window dialogs),
// Jalali dates + Latin digits, one font per language, one copy helper,
// sheets on phones / centred dialog on desktop, 16px inputs on phones.
import { THEMES } from '../lib.mjs'

export const name = 'invariants'
const NO_WINDOW_DIALOGS = `window.__winDialogs = 0; for (const k of ['alert','confirm','prompt']) window[k] = () => { window.__winDialogs++; return false };`

export async function run({ test, open }) {
  for (const [key, theme, mode] of THEMES) {
    await test(`toggles ON #11AB53 / OFF dark (${key}, admin users)`, async () => {
      const p = await open({ path: '/panel/users', auth: 'staff', theme, mode, w: 1440, h: 900 })
      const r = await p.page.$$eval('label.toggle', (ls) => ls.map((l) => [l.querySelector('input').checked, getComputedStyle(l.querySelector('.track')).backgroundColor]))
      await p.ctx.close()
      const on = r.filter(([c]) => c).map(([, b]) => b), off = r.filter(([c]) => !c).map(([, b]) => b)
      if (!on.length || !off.length) throw new Error(`need both states, got on=${on.length} off=${off.length}`)
      if (on.some((b) => b !== 'rgb(17, 171, 83)')) throw new Error('ON ' + [...new Set(on)])
      const dark = (b) => { const [r, g, bb] = b.match(/\d+/g).map(Number); return r < 80 && g < 80 && bb < 90 && Math.abs(r - bb) < 30 }
      if (off.some((b) => !dark(b))) throw new Error('OFF ' + [...new Set(off)])
    })
  }

  const dialogCase = (title, path, auth, act) => test(title, async () => {
    const p = await open({ path, auth, init: NO_WINDOW_DIALOGS })
    await act(p.page)
    await p.page.waitForSelector('.cdlg', { timeout: 5000 })
    const r = await p.page.evaluate(() => ({ win: window.__winDialogs, rect: document.querySelector('.cdlg').getBoundingClientRect().toJSON() }))
    await p.page.keyboard.press('Escape').catch(() => {})
    await p.ctx.close()
    if (r.win) throw new Error(`${r.win} window dialog(s)`)
    if (r.rect.bottom < 844 - 40) throw new Error(`phone dialog is not a bottom sheet (bottom ${r.rect.bottom})`)
  })
  await dialogCase('user: change-link confirm is the shared bottom sheet, no window dialog', '/', 'user', async (page) => {
    await page.click('.csp-svc-more'); await page.click('.csp-svc-extra .csp-svc-btn')
  })
  await dialogCase('admin: delete user confirm is the shared bottom sheet', '/panel/users', 'staff', async (page) => {
    await page.click('.usr-del-btn')
  })
  await dialogCase('admin: reject payment asks through the shared sheet', '/panel/payments', 'staff', async (page) => {
    await page.click('.pq-acts .btn-ghost')
  })
  await test('desktop: ConfirmDialog is centred', async () => {
    const p = await open({ path: '/panel/users', auth: 'staff', w: 1440, h: 900 })
    await p.page.click('.usr-del-btn'); await p.page.waitForSelector('.cdlg')
    const r = await p.page.$eval('.cdlg', (e) => e.getBoundingClientRect().toJSON()); await p.ctx.close()
    const cy = r.top + r.height / 2
    if (Math.abs(cy - 450) > 60) throw new Error(`centre y ${cy}`)
  })

  const JALALI = /\b14\d\d\/\d\d\/\d\d\b/
  for (const [path, auth] of [['/history', 'user'], ['/panel/users', 'staff'], ['/panel/transactions', 'staff']]) {
    await test(`fa dates are Jalali with Latin digits (${path})`, async () => {
      const p = await open({ path, auth, w: 1440, h: 900 })
      const txt = await p.page.evaluate(() => document.querySelector('main').innerText); await p.ctx.close()
      if (!JALALI.test(txt)) throw new Error('no Jalali date found')
      if (/\b20\d\d[/-]\d\d[/-]\d\d\b/.test(txt)) throw new Error('Gregorian date shown')
      if (/[۰-۹٠-٩]/.test(txt)) throw new Error('Persian digits shown')
    })
  }
  for (const [lang, font] of [['fa', 'Vazirmatn'], ['en', 'Inter']]) {
    for (const [path, auth] of [['/', 'user'], ['/panel/', 'staff']]) await test(`font ${lang} → ${font} (${path}), code → JetBrains Mono`, async () => {
      const p = await open({ path, auth, lang })
      const r = await p.page.evaluate(() => {
        const c = document.createElement('code'); c.textContent = 'x'; document.body.appendChild(c)
        return [getComputedStyle(document.querySelector('main')).fontFamily, getComputedStyle(c).fontFamily]
      })
      await p.ctx.close()
      if (!r[0].replace(/"/g, '').startsWith(font)) throw new Error('main: ' + r[0])
      if (!r[1].includes('JetBrains Mono')) throw new Error('code: ' + r[1])
    })
  }
  await test('copy helper copies the subscription link and confirms', async () => {
    // the audit origin is not a secure context, so lib/clipboard.js takes its execCommand path — capture it
    const CAPTURE = `document.execCommand = (cmd) => { if (cmd === 'copy') window.__copied = (document.activeElement && document.activeElement.value) || String(getSelection()); return true };`
    const p = await open({ path: '/', auth: 'user', init: CAPTURE })
    const before = await p.page.$eval('.csp-svc-copy .icon-btn', (b) => b.getAttribute('aria-label'))
    await p.page.click('.csp-svc-copy .icon-btn'); await p.page.waitForTimeout(300)
    const r = await p.page.evaluate(() => ({ clip: window.__copied || '', label: document.querySelector('.csp-svc-copy .icon-btn').getAttribute('aria-label') }))
    await p.ctx.close()
    if (!/^https:\/\/sub\./.test(r.clip)) throw new Error('clipboard: ' + r.clip)
    if (r.label === before) throw new Error('no copied feedback')
  })
  for (const [path, auth] of [['/panel/users', 'staff'], ['/panel/settings/alerts', 'staff'], ['/profile', 'user']]) {
    await test(`phone inputs are ≥16px (no iOS zoom) — ${path}`, async () => {
      const p = await open({ path, auth })
      const small = await p.page.$$eval('input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=hidden]), select, textarea',
        (els) => els.filter((e) => e.getBoundingClientRect().width > 0 && parseFloat(getComputedStyle(e).fontSize) < 16).map((e) => e.className || e.tagName))
      await p.ctx.close()
      if (small.length) throw new Error(small.join(', '))
    })
  }
}
