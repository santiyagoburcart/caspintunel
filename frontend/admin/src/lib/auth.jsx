import { createContext, useContext, useEffect, useState } from 'react'
import { api, clearAuthState, SESSION_EXPIRED_KEY, tokens } from './api'

const Ctx = createContext(null)

export function AuthProvider({ children }) {
  const [staff, setStaff] = useState(null)
  const [loading, setLoading] = useState(true)

  // A deploy / network blip (no response, 5xx) is retried, never treated as a logout.
  // (v1.30.2: a failed /me/ during a deploy sent operators to the login page with their
  // old tokens still stored — and the login then failed until storage was cleared.)
  const refreshMe = async () => {
    if (!tokens.access) { setStaff(null); setLoading(false); return }
    for (let attempt = 0; ; attempt++) {
      try {
        const { data } = await api.get('/admin/auth/me/')
        setStaff(data)
        break
      } catch (e) {
        const st = e?.response?.status
        if ((!st || st >= 500) && attempt < 3) { await new Promise((r) => setTimeout(r, 1500 * (attempt + 1))); continue }
        if (st === 401 || st === 403) clearAuthState()
        setStaff(null)
        break
      }
    }
    setLoading(false)
  }
  useEffect(() => { refreshMe() }, [])

  // a sign-in always starts clean: an older session's tokens are dropped first and the
  // request itself never carries a token (lib/api.js isAuthCall)
  const login = async (username, password) => {
    clearAuthState()
    try { sessionStorage.removeItem(SESSION_EXPIRED_KEY) } catch { /* ignore */ }
    const { data } = await api.post('/admin/auth/login/', { username, password }, { quiet: true })
    tokens.set(data)
    setStaff(data.staff)
    return data.staff
  }
  // forget everything locally at once, then revoke the refresh token on the server
  const logout = () => {
    const refresh = tokens.refresh
    clearAuthState()
    setStaff(null)
    if (refresh) api.post('/admin/auth/logout/', { refresh }, { quiet: true }).catch(() => {})
  }

  // a list means "all of these" (a page whose API needs several, e.g. Analytics)
  const can = (code) => Array.isArray(code) ? code.every((c) => can(c))
    : !!staff && (staff.is_superadmin || staff.permissions?.includes('*') || staff.permissions?.includes(code))

  return <Ctx.Provider value={{ staff, loading, login, logout, refreshMe, can }}>{children}</Ctx.Provider>
}

export const useAuth = () => useContext(Ctx)
