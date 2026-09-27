#!/usr/bin/env node
// Liquid Glass legibility proof (no browser, no data): for every theme × mode
// × glass tint, composite the tint over the WORST content that can scroll
// underneath (pure black and pure white — contrast depends only on luminance,
// and a composite's luminance is monotonic in the underlay, so these two are
// the exact extremes even after blur/saturation) and check every text colour
// that is drawn on glass against WCAG AA (4.5:1 text, 3:1 icons/large text).
//
//   node scripts/ui-audit/glass-contrast.mjs        exit 1 on any failure
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const palettes = JSON.parse(readFileSync(join(root, 'backend/apps/settings_app/theme_palettes.json'), 'utf8'))

// mirrors styles/liquid.css + index.css (not palette-driven)
const SURFACE_SOLID = { light: '#FFFFFF', dark: '#111827' }
const BAR = Number(process.env.LG_BAR || 0.90), STRONG = Number(process.env.LG_STRONG || 0.92)
const TINTS = { [`bar (full ${BAR * 100}%)`]: BAR, [`sheet/sidebar (full ${STRONG * 100}%)`]: STRONG, 'bar (lite 95%)': 0.95 }
// the active tab sits on a primary pill inside the bar
const PILL = 0.13
// --lg-active-fg (light): color-mix(in srgb, var(--c-primary-fg) 72%, var(--c-text))
const ACTIVE_MIX = 0.72
// ConfirmDialog text colours (components/ConfirmDialog.jsx CDLG_CSS)
const CDLG = { light: { title: '#0f172a', text: '#475569' }, dark: { title: '#f1f5f9', text: '#b6c0cf' } }
// sidebar link colour (--csp-text-2 fallbacks in index.css)
const TEXT2 = { light: '#1B2638', dark: '#D5DBE7' }

const hex = (h) => {
  const m = h.trim().match(/^#([0-9a-f]{6})$/i)
  if (!m) throw new Error('not a hex colour: ' + h)
  return [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16))
}
const mix = (a, b, wa) => a.map((v, i) => v * wa + b[i] * (1 - wa))          // sRGB mix like color-mix(in srgb)
const lum = (c) => {
  const [r, g, b] = c.map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4 })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05) }

let fails = 0, checks = 0
const rows = []
for (const [name, pal] of Object.entries(palettes)) {
  const modes = pal.base === 'light' ? ['light'] : pal.base === 'dark' ? ['dark'] : ['light', 'dark']
  for (const mode of modes) {
    const p = pal[mode]
    const text = hex(p.text), muted = hex(p.text_muted)
    const texts = {
      text: [text, 4.5],
      'text-muted': [muted, 4.5],
      'lg-label (muted 72% + text)': [mix(muted, text, 0.72), 4.5],
      'primary-fg (active tab / links)': [hex(p.primary_fg), 4.5],
      'success-fg': [hex(p.success_fg), 4.5],
      'danger-fg': [hex(p.danger_fg), 4.5],
      'warning-fg': [hex(p.warning_fg), 4.5],
      'sidebar link (--csp-text-2)': [hex(TEXT2[mode]), 4.5],
      'dialog text': [hex(CDLG[mode].text), 4.5],
      'dialog title': [hex(CDLG[mode].title), 4.5],
    }
    for (const [tintName, a] of Object.entries(TINTS)) {
      let worst = Infinity, worstWhat = ''
      for (const under of ['#000000', '#FFFFFF']) {
        const bg = mix(hex(SURFACE_SOLID[mode]), hex(under), a)
        const pill = mix(hex(p.primary), bg, PILL)
        for (const [tn, [fg, need]] of Object.entries({ ...texts, 'active tab label on its pill': [mode === 'light' ? mix(hex(p.primary_fg), text, ACTIVE_MIX) : hex(p.primary_fg), 4.5] })) {
          checks++
          const r = ratio(fg, tn.startsWith('active tab label') ? pill : bg)
          if (r < worst) { worst = r; worstWhat = `${tn} over ${under}` }
          if (r < need) { fails++; console.log(`FAIL ${name}/${mode} ${tintName}: ${tn} over ${under} = ${r.toFixed(2)} < ${need}`) }
        }
      }
      rows.push(`${name.padEnd(16)} ${mode.padEnd(5)} ${tintName.padEnd(26)} min ${worst.toFixed(2)}:1  (${worstWhat})`)
    }
  }
}
console.log(rows.join('\n'))
console.log(`\n${checks} checks, ${fails} below WCAG AA`)
process.exit(fails ? 1 : 0)
