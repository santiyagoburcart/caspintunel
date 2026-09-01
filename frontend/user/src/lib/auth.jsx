import { createContext, useContext, useEffect, useState } from 'react'
import { api, tokens } from './api'

const Ctx = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

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

  useEffect(() => { refreshMe() }, [])

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
    <Ctx.Provider value={{ user, loading, login, register, logout, refreshMe, setUser }}>
      {children}
    </Ctx.Provider>
  )
}

export const useAuth = () => useContext(Ctx)
