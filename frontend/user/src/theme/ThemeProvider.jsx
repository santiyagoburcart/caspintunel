import { createContext, useContext, useEffect, useState } from 'react'
import { api } from '../lib/api'

const Ctx = createContext(null)

function letterIcon(name) {
  const ch = String(name || '').trim().charAt(0).toUpperCase()
  if (!ch) return null
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#1464BA"/>`
    + `<text x="32" y="44" font-family="sans-serif" font-size="36" font-weight="700" fill="#fff" text-anchor="middle">${ch.replace(/[<&>"]/g, '')}</text></svg>`
  return `data:image/svg+xml,${encodeURIComponent(svg)}`
}

// Some browsers ignore a mutated <link rel=icon> href — remove + re-add a fresh
// element (with the right MIME type) so the tab icon actually updates, in every theme.
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
  root.setAttribute('data-theme-style', 'caspian')
}

// One customer design (Caspian) from the very first paint — before /theme/ answers, and
// even when it never does (slow Telegram in-app browsers used to get the old dark login).
if (typeof document !== 'undefined') document.documentElement.setAttribute('data-theme-style', 'caspian')

export function ThemeProvider({ children }) {
  const [userMode, setUserMode] = useState(() => { try { return localStorage.getItem('ct_mode') || 'light' } catch { return 'light' } })
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
    api.get('/theme/').then((r) => setPalette(r.data?.palette || null)).catch(() => {})
    api.get('/config/').then((r) => {
      setConfig(r.data)
      if (r.data?.site_name_fa) document.title = r.data.site_name_fa
      // v1.44: a store without its own favicon gets its initial, never our icon
      setFavicon(r.data?.favicon || letterIcon(r.data?.site_name_en || r.data?.site_name_fa))
    }).catch(() => {})
  }, [])

  const toggle = () => setUserMode((m) => (m === 'dark' ? 'light' : 'dark'))
  return (
    <Ctx.Provider value={{ mode, toggle, locked, styleKey: 'caspian', config }}>
      {children}
    </Ctx.Provider>
  )
}

export const useTheme = () => useContext(Ctx)
