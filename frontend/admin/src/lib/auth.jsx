import { createContext, useContext, useEffect, useState } from 'react'
import { api, tokens } from './api'

const Ctx = createContext(null)

export function AuthProvider({ children }) {
  const [staff, setStaff] = useState(null)
  const [loading, setLoading] = useState(true)

  const refreshMe = async () => {
    if (!tokens.access) { setStaff(null); setLoading(false); return }
    try {
      const { data } = await api.get('/admin/auth/me/')
      setStaff(data)
    } catch { setStaff(null) } finally { setLoading(false) }
  }
  useEffect(() => { refreshMe() }, [])

  const login = async (username, password) => {
    const { data } = await api.post('/admin/auth/login/', { username, password })
    tokens.set(data)
    setStaff(data.staff)
    return data.staff
  }
  const logout = () => { tokens.clear(); setStaff(null) }

  const can = (code) =>
    !!staff && (staff.is_superadmin || staff.permissions?.includes('*') || staff.permissions?.includes(code))

  return <Ctx.Provider value={{ staff, loading, login, logout, refreshMe, can }}>{children}</Ctx.Provider>
}

export const useAuth = () => useContext(Ctx)
