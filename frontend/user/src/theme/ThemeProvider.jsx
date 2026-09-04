import { createContext, useContext, useEffect, useState } from 'react'
import { api } from '../lib/api'

const Ctx = createContext(null)

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
    api.get('/theme/').then((r) => setPalette(r.data?.palette || null)).catch(() => {})
    api.get('/config/').then((r) => {
      setConfig(r.data)
      if (r.data?.site_name_fa) document.title = r.data.site_name_fa
      const fav = document.getElementById('favicon')
      if (fav && r.data?.favicon) fav.href = r.data.favicon
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
