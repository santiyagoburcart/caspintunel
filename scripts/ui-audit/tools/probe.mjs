// Debug helper: print text colour + background chain for selectors on a page.
//   PROBE='[["/panel/cards","staff","Caspian","light",".bankcard-num"], …]' node tools/probe.mjs
import { chromium, newPage, settle, ORIGIN } from '../lib.mjs'
const dists = { user: process.env.USER_DIST, admin: process.env.ADMIN_DIST }
const browser = await chromium.launch()
for (const [path, auth, theme, mode, sel, w = 1440] of JSON.parse(process.env.PROBE)) {
  const p = await newPage(browser, { w, h: 900, theme, mode, lang: 'en', auth, dists })
  await p.page.goto(ORIGIN + path); await settle(p.page)
  const r = await p.page.evaluate((sel) => {
    const el = sel.startsWith("text=") ? [...document.querySelectorAll("main *")].find((e) => [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.includes(sel.slice(5)))) : document.querySelector(sel); if (!el) return "not found"
    const chain = []
    for (let n = el; n && chain.length < 6; n = n.parentElement) {
      const cs = getComputedStyle(n)
      if ((cs.backgroundColor !== 'rgba(0, 0, 0, 0)') || cs.backgroundImage !== 'none')
        chain.push(`${n.className.toString().slice(0, 30)}: ${cs.backgroundColor} ${cs.backgroundImage.slice(0, 110)}`)
    }
    return { color: getComputedStyle(el).color, fs: getComputedStyle(el).fontSize, chain }
  }, sel)
  console.log(`${path} ${theme}/${mode} ${sel}\n  ${JSON.stringify(r)}`)
  await p.ctx.close()
}
await browser.close()
