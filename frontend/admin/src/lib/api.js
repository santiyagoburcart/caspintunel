import axios from 'axios'

const ACCESS = 'cta_access'
const REFRESH = 'cta_refresh'

export const tokens = {
  get access() { return localStorage.getItem(ACCESS) },
  get refresh() { return localStorage.getItem(REFRESH) },
  set({ access, refresh }) {
    if (access) localStorage.setItem(ACCESS, access)
    if (refresh) localStorage.setItem(REFRESH, refresh)
  },
  clear() { localStorage.removeItem(ACCESS); localStorage.removeItem(REFRESH) },
}

export const api = axios.create({ baseURL: '/api/v1' })

api.interceptors.request.use((cfg) => {
  if (tokens.access) cfg.headers.Authorization = `Bearer ${tokens.access}`
  return cfg
})

let refreshing = null
api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const { response, config } = error
    if (response?.status === 401 && tokens.refresh && !config._retry) {
      config._retry = true
      try {
        refreshing = refreshing || axios.post('/api/v1/admin/auth/refresh/', { refresh: tokens.refresh })
        const { data } = await refreshing
        refreshing = null
        tokens.set({ access: data.access, refresh: data.refresh })
        config.headers.Authorization = `Bearer ${data.access}`
        return api(config)
      } catch (e) {
        refreshing = null
        tokens.clear()
        if (!location.pathname.endsWith('/login')) location.href = '/panel/login'
      }
    }
    return Promise.reject(error)
  },
)

export function apiError(e, fallback = 'خطایی رخ داد') {
  const d = e?.response?.data
  if (!d) return fallback
  if (typeof d === 'string') return d
  if (d.detail) return d.detail
  const first = Object.values(d)[0]
  return Array.isArray(first) ? first[0] : String(first || fallback)
}
