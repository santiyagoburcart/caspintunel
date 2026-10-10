import { createContext, useContext, useEffect, useRef, useState } from 'react'
import axios from 'axios'
import { api, apiError, tokens } from './api'
import { isTelegramMiniApp, tgInitData, initTelegramUi, isTelegramWebView } from './telegram'

const Ctx = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [tgError, setTgError] = useState('')
  const booted = useRef(false)

  const refreshMe = async () => {
    if (!tokens.access) { setUser(null); setLoading(false); return }
    try {
      const { data } = await api.get('/auth/me/')
      setUser(data)
    } catch {
      setUser(null)
    } finally {
      setLoading(false)
    }
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

  const login = async (username, password) => {
    const { data } = await api.post('/auth/login/', { username, password })
    tokens.set(data)
    setUser(data.user)
    return data.user
  }
  const register = async (payload) => {
    const { data } = await api.post('/auth/register/', payload)
    tokens.set(data)
    setUser(data.user)
    return data
  }
  const logout = async () => {
    try { await api.post('/auth/logout/', { refresh: tokens.refresh }) } catch {}
    tokens.clear()
    setUser(null)
  }

  return (
    <Ctx.Provider value={{ user, loading, tgError, login, register, logout, refreshMe, setUser,
      retryTelegram: () => { setLoading(true); bootstrapTelegram() } }}>
      {children}
    </Ctx.Provider>
  )
}

export const useAuth = () => useContext(Ctx)
