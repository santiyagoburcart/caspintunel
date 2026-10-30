import { createContext, useContext, useEffect, useRef, useState } from 'react'
import axios from 'axios'
import { api, apiError, clearAuthState, SESSION_EXPIRED_KEY, tokens } from './api'
import { isTelegramMiniApp, tgInitData, initTelegramUi, isTelegramWebView } from './telegram'

const Ctx = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [tgError, setTgError] = useState('')
  const booted = useRef(false)

  // a deploy / network blip (no response, 5xx) is retried and never treated as a logout;
  // a refused token is handled by the api interceptor (refresh, else clean sign-out)
  const refreshMe = async () => {
    if (!tokens.access) { setUser(null); setLoading(false); return }
    for (let attempt = 0; ; attempt++) {
      try {
        const { data } = await api.get('/auth/me/')
        setUser(data)
        break
      } catch (e) {
        const st = e?.response?.status
        if ((!st || st >= 500) && attempt < 3) { await new Promise((r) => setTimeout(r, 1500 * (attempt + 1))); continue }
        if (st === 401 || st === 403) clearAuthState()
        setUser(null)
        break
      }
    }
    setLoading(false)
  }

  // In a Telegram Mini App the identity comes from the signed initData, which
  // the backend verifies against the sales-bot token. We re-do this on every
  // launch (initData is fresh each time) and never fall back to a possibly
  // stale stored token inside Telegram.
  const bootstrapTelegram = async () => {
    initTelegramUi()
    // a stale token from an earlier session must not ride along (it used to
    // turn this call into a 401 → "session expired" → login form)
    tokens.clear()
    try {
      const { data } = await axios.post('/api/v1/auth/telegram/miniapp/', { init_data: tgInitData() })
      tokens.set(data)
      setUser(data.user)
      setTgError('')
      try { sessionStorage.removeItem('ct_tg_relaunch') } catch { /* ignore */ }
    } catch (e) {
      tokens.clear()
      setUser(null)
      const code = e?.response?.data?.code
      setTgError(code === 'phone_required' ? 'phone_required'
        : apiError(e, 'Telegram session could not be verified.'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (booted.current) return   // StrictMode double-invoke guard
    booted.current = true
    if (isTelegramMiniApp()) bootstrapTelegram()
    else if (isTelegramWebView()) { setTgError('no_init_data'); setLoading(false) }
    else refreshMe()
  }, [])

  // a sign-in always starts clean: whatever an older session left is dropped first and
  // the request itself never carries a token (lib/api.js isAuthCall)
  const startClean = () => {
    clearAuthState()
    try { sessionStorage.removeItem(SESSION_EXPIRED_KEY) } catch { /* ignore */ }
  }
  const login = async (username, password) => {
    startClean()
    const { data } = await api.post('/auth/login/', { username, password })
    tokens.set(data)
    setUser(data.user)
    return data.user
  }
  const register = async (payload) => {
    startClean()
    const { data } = await api.post('/auth/register/', payload)
    tokens.set(data)
    setUser(data.user)
    return data
  }
  const logout = async () => {
    const refresh = tokens.refresh
    clearAuthState()
    setUser(null)
    if (refresh) { try { await api.post('/auth/logout/', { refresh }) } catch { /* already signed out locally */ } }
  }

  return (
    <Ctx.Provider value={{ user, loading, tgError, login, register, logout, refreshMe, setUser,
      retryTelegram: () => { setLoading(true); bootstrapTelegram() } }}>
      {children}
    </Ctx.Provider>
  )
}

export const useAuth = () => useContext(Ctx)
