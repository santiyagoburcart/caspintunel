import { createContext, useContext, useEffect, useState } from 'react'
import { api } from '../lib/api'

const Ctx = createContext(null)

// map API palette keys -> CSS variable names
const VARS = {
  background: '--c-bg', surface: '--c-surface', primary: '--c-primary',
  secondary: '--c-secondary', success: '--c-success', danger: '--c-danger',
  warning: '--c-warning', text: '--c-text', text_muted: '--c-text-muted', border: '--c-border',
}

function applyPalette(palette, mode) {
  const p = palette?.[mode]
  if (!p) return
  const root = document.documentElement
  for (const [k, v] of Object.entries(VARS)) if (p[k]) root.style.setProperty(v, p[k])
}

export function ThemeProvider({ children }) {
  const [mode, setMode] = useState(() => localStorage.getItem('ct_mode') || 'dark')
  const [config, setConfig] = useState(null)
  const [palette, setPalette] = useState(null)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', mode === 'dark')
    localStorage.setItem('ct_mode', mode)
    if (palette) applyPalette(palette, mode)
  }, [mode, palette])

  useEffect(() => {
    api.get('/theme/').then((r) => setPalette(r.data?.palette || null)).catch(() => {})
    api.get('/config/').then((r) => {
      setConfig(r.data)
      if (r.data?.site_name_fa) document.title = r.data.site_name_fa
      const fav = document.getElementById('favicon')
      if (fav && r.data?.favicon) fav.href = r.data.favicon
    }).catch(() => {})
  }, [])

  const toggle = () => setMode((m) => (m === 'dark' ? 'light' : 'dark'))
  return <Ctx.Provider value={{ mode, toggle, config }}>{children}</Ctx.Provider>
}

export const useTheme = () => useContext(Ctx)
