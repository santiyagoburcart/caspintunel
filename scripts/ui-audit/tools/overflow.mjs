// Debug helper: list elements wider than the viewport.  PAGE=/panel/payments AUTH=staff node tools/overflow.mjs
import { chromium, newPage, settle, ORIGIN } from '../lib.mjs'
const browser = await chromium.launch()
const p = await newPage(browser, { w: Number(process.env.W || 390), h: 844, theme: 'Caspian', mode: 'light', lang: 'fa', auth: process.env.AUTH, dists: { user: process.env.USER_DIST, admin: process.env.ADMIN_DIST } })
await p.page.goto(ORIGIN + process.env.PAGE); await settle(p.page)
console.log(await p.page.evaluate(() => [document.documentElement.scrollWidth, innerWidth, ...[...document.querySelectorAll('body *')]
  .filter((e) => { const r = e.getBoundingClientRect(); return r.width && (r.right > innerWidth + 1 || r.left < -1) })
  .slice(0, 8).map((e) => `${e.tagName}.${e.className.toString().slice(0, 50)} ${Math.round(e.getBoundingClientRect().left)}..${Math.round(e.getBoundingClientRect().right)}`)]))
await browser.close()
