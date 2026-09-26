import { createContext, useContext, useEffect, useState } from 'react'
import { api } from '../lib/api'
import { IS_PREVIEW } from '../lib/site'

// Preview builds bundle the palettes of the branch being previewed (copied by
// scripts/preview.sh from backend/apps/settings_app/theme_palettes.json — the
// file `seed` writes to the DB on deploy). Absent in production builds, so
// production always uses the palette the API returns.
const PREVIEW_PALETTES = IS_PREVIEW
  ? Object.values(import.meta.glob('./preview-palettes.json', { eager: true, import: 'default' }))[0] || null
  : null

const Ctx = createContext(null)

// Some browsers ignore a mutated <link rel=icon> href — remove + re-add a fresh
// element (with the right MIME type) so the tab icon actually updates. Works in
// every theme (Midnight Aurora / Royal Frost / Caspian) since it's theme-agnostic.
function setFavicon(url) {
  if (!url) return
  try {
    document.querySelectorAll("link[rel~='icon'], link#favicon").forEach((el) => el.remove())
    const link = document.createElement('link')
    link.id = 'favicon'
    link.rel = 'icon'
    const ext = String(url).split('?')[0].split('.').pop().toLowerCase()
    link.type = { png: 'image/png', svg: 'image/svg+xml', ico: 'image/x-icon',
      jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif', webp: 'image/webp' }[ext] || ''
    link.href = url
    document.head.appendChild(link)
  } catch { /* non-fatal */ }
}

// map API palette keys -> CSS variable names
const VARS = {
  background: '--c-bg', surface: '--c-surface', primary: '--c-primary',
  secondary: '--c-secondary', success: '--c-success', danger: '--c-danger',
  warning: '--c-warning', text: '--c-text', text_muted: '--c-text-muted', border: '--c-border',
  // text-safe variants of the role colours (≥4.5:1 on bg + surface)
  primary_fg: '--c-primary-fg', success_fg: '--c-success-fg', danger_fg: '--c-danger-fg', warning_fg: '--c-warning-fg',
}

// A theme carries more than colours now: `base` ("light" | "dark" | "auto")
// locks the whole site to one mode, and `style` ("aurora" | "frost") selects
// the component look via [data-theme-style] CSS. `vars` are extra raw CSS
// custom properties (e.g. a second gradient stop) applied alongside the
// semantic colour tokens above.
function applyPalette(palette, mode) {
  const root = document.documentElement
  const p = palette?.[mode] || palette?.light || palette?.dark
  if (p) for (const [k, v] of Object.entries(VARS)) if (p[k]) root.style.setProperty(v, p[k])
  if (palette?.vars) for (const [k, v] of Object.entries(palette.vars)) root.style.setProperty(k, v)
  root.setAttribute('data-theme-style', palette?.style || 'aurora')
}

export function ThemeProvider({ children }) {
  const [userMode, setUserMode] = useState(() => localStorage.getItem('ct_mode') || 'dark')
  const [config, setConfig] = useState(null)
  const [palette, setPalette] = useState(null)

  // an active theme can lock the site to one mode (e.g. Royal Frost is light-only)
  const base = palette?.base
  const locked = base === 'light' || base === 'dark'
  const mode = locked ? base : userMode

  useEffect(() => {
    document.documentElement.classList.toggle('dark', mode === 'dark')
    if (!locked) localStorage.setItem('ct_mode', userMode)
    if (palette) applyPalette(palette, mode)
  }, [mode, userMode, locked, palette])

  useEffect(() => {
    api.get('/theme/').then((r) => setPalette((PREVIEW_PALETTES && PREVIEW_PALETTES[r.data?.name]) || r.data?.palette || null)).catch(() => {})
    api.get('/config/').then((r) => {
      setConfig(r.data)
      if (r.data?.site_name_fa) document.title = r.data.site_name_fa
      setFavicon(r.data?.favicon)
    }).catch(() => {})
  }, [])

  const toggle = () => setUserMode((m) => (m === 'dark' ? 'light' : 'dark'))
  return (
    <Ctx.Provider value={{ mode, toggle, locked, styleKey: palette?.style || 'aurora', config }}>
      {children}
    </Ctx.Provider>
  )
}

export const useTheme = () => useContext(Ctx)
