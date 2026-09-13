import axios from 'axios'

const ACCESS = 'cta_access'
const REFRESH = 'cta_refresh'
export const SESSION_EXPIRED_KEY = 'cta_session_expired'

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

// clear the stale session and bounce to login — never let the raw JWT error
// reach a page-level catch; the redirect is already underway when the caller
// would otherwise see this promise settle, so it deliberately never resolves
function sessionExpired() {
  tokens.clear()
  if (!location.pathname.endsWith('/login')) {
    try { sessionStorage.setItem(SESSION_EXPIRED_KEY, '1') } catch { /* private browsing */ }
    location.href = '/panel/login'
  }
  return new Promise(() => {})
}

let refreshing = null
api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const { response, config } = error
    if (response?.status === 401 && config && !config._retry) {
      config._retry = true
      if (tokens.refresh) {
        try {
          refreshing = refreshing || axios.post('/api/v1/admin/auth/refresh/', { refresh: tokens.refresh })
          const { data } = await refreshing
          refreshing = null
          tokens.set({ access: data.access, refresh: data.refresh })
          config.headers.Authorization = `Bearer ${data.access}`
          return api(config)
        } catch (e) {
          refreshing = null
          return sessionExpired()
        }
      }
      // no refresh token to try, but we did send an access token that was
      // just rejected — it's stale, not "logged out"; a page with no token
      // at all falls through to the plain reject below (normal logged-out 401)
      if (tokens.access) return sessionExpired()
    }
    return Promise.reject(error)
  },
)

export function apiError(e, fallback = 'خطایی رخ داد') {
  const d = e?.response?.data
  if (!d) return fallback
  // a stale/expired token slipping past the interceptor must never show its
  // technical detail — fall back to whatever generic message the caller gave
  if (d.code === 'token_not_valid' || d.code === 'token_expired') return fallback
  if (typeof d === 'string') return d
  if (d.detail) return d.detail
  const first = Object.values(d)[0]
  return Array.isArray(first) ? first[0] : String(first || fallback)
}
