import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { api, apiError, tokens } from './api'
import { isTelegramMiniApp, tgInitData, initTelegramUi } from './telegram'

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
    try {
      const { data } = await api.post('/auth/telegram/miniapp/', { init_data: tgInitData() })
      tokens.set(data)
      setUser(data.user)
    } catch (e) {
      tokens.clear()
      setUser(null)
      setTgError(apiError(e, 'Telegram session could not be verified.'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (booted.current) return   // StrictMode double-invoke guard
    booted.current = true
    if (isTelegramMiniApp()) bootstrapTelegram()
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
    <Ctx.Provider value={{ user, loading, tgError, login, register, logout, refreshMe, setUser }}>
      {children}
    </Ctx.Provider>
  )
}

export const useAuth = () => useContext(Ctx)
