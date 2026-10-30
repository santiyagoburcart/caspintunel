import axios from 'axios'

const ACCESS = 'ct_access'
const REFRESH = 'ct_refresh'
export const SESSION_EXPIRED_KEY = 'ct_session_expired'
// per-account things a logout / another login must not leave behind
const ACCOUNT_KEYS = ['ct_checkout_active']

const store = {
  get: (k) => { try { return localStorage.getItem(k) } catch { return null } },
  set: (k, v) => { try { localStorage.setItem(k, v) } catch { /* private mode */ } },
  del: (k) => { try { localStorage.removeItem(k) } catch { /* private mode */ } },
}

export const tokens = {
  get access() { return store.get(ACCESS) },
  get refresh() { return store.get(REFRESH) },
  set({ access, refresh }) {
    if (access) store.set(ACCESS, access)
    if (refresh) store.set(REFRESH, refresh)
  },
  clear() { store.del(ACCESS); store.del(REFRESH) },
}

/** Everything this site keeps for a signed-in account (tokens + per-account state). */
export function clearAuthState() {
  tokens.clear()
  ACCOUNT_KEYS.forEach(store.del)
}

// A JWT's payload, or null. Only read to drop tokens that can never work (wrong kind,
// e.g. a panel token, or an expired refresh token) — the server still verifies them.
function claims(t) {
  try {
    const p = t.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(atob(p + '='.repeat((4 - (p.length % 4)) % 4)))
  } catch { return null }
}
const alive = (c) => !!c && (!c.exp || c.exp * 1000 > Date.now() + 5000)

/** Tokens left by an older visit / older version that can't work any more are dropped
 * before the first request, so they are never sent (v1.30.2). */
export function pruneStoredTokens() {
  const a = tokens.access && claims(tokens.access)
  const r = tokens.refresh && claims(tokens.refresh)
  const accessOk = a && a.token_type === 'access'
  const refreshOk = r && r.token_type === 'refresh' && alive(r)
  if ((tokens.access && !accessOk) || (tokens.refresh && !refreshOk)) clearAuthState()
  else if (tokens.access && !alive(a) && !tokens.refresh) clearAuthState()
}
pruneStoredTokens()

export const api = axios.create({ baseURL: '/api/v1' })

// sign-in endpoints: never send a stored token and never try a refresh for them
const AUTH_CALL = /^\/?(api\/v1\/)?auth\/(login|register|token\/refresh|telegram\/miniapp|logout|password\/reset|email\/verify\/confirm)\//
export const isAuthCall = (url) => AUTH_CALL.test(url || '')
const AUTH_PAGES = ['/login', '/register', '/reset', '/verify-email']
const onAuthPage = () => AUTH_PAGES.some((p) => location.pathname.startsWith(p))

// a random id per browser: behind an Iran tunnel (no per-visitor IP) the server rate-limits by this instead
export function clientId() {
  try {
    let v = localStorage.getItem('ct_cid')
    if (!v || !/^[A-Za-z0-9_-]{8,64}$/.test(v)) {
      const b = new Uint8Array(16); crypto.getRandomValues(b)
      v = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('')
      localStorage.setItem('ct_cid', v)
    }
    return v
  } catch { return '' }
}

api.interceptors.request.use((cfg) => {
  if (tokens.access && !isAuthCall(cfg.url)) cfg.headers.Authorization = `Bearer ${tokens.access}`
  else delete cfg.headers.Authorization
  const cid = clientId()
  if (cid) cfg.headers['X-Client-Id'] = cid
  return cfg
})

// clear the stale session and bounce to login — never let the raw JWT error
// reach a page-level catch; the redirect is already underway when the caller
// would otherwise see this promise settle, so it deliberately never resolves.
// Already on a sign-in page there is nowhere to go: the error is returned so the
// form shows it (never a spinner that hangs forever).
function sessionExpired(error) {
  clearAuthState()
  // inside the Telegram Mini App the session comes from initData: start over
  // at the app root (it signs in again) instead of showing the login form
  if (window.Telegram?.WebApp?.initData || /tgWebAppData=/.test(window.location.hash)) {
    if (!sessionStorage.getItem('ct_tg_relaunch')) {
      try { sessionStorage.setItem('ct_tg_relaunch', '1') } catch { /* ignore */ }
      window.location.replace(import.meta.env.BASE_URL || '/')
      return new Promise(() => {})
    }
    return Promise.reject(error)
  }
  if (onAuthPage()) return Promise.reject(error)
  try { sessionStorage.setItem(SESSION_EXPIRED_KEY, '1') } catch { /* private browsing */ }
  location.href = '/login'
  return new Promise(() => {})
}

const isCsrfFailure = (r) => r?.status === 403 && /csrf/i.test(String(r?.data?.detail || ''))

let refreshing = null
api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const { response, config } = error
    if (!config || isAuthCall(config.url)) return Promise.reject(error)
    // a CSRF failure means an old cookie session got in the way: start clean
    if (isCsrfFailure(response)) return sessionExpired(error)
    if (response?.status === 401 && !config._retry) {
      config._retry = true
      if (tokens.refresh) {
        try {
          // bare axios: no stored (stale) access token rides along
          refreshing = refreshing || axios.post('/api/v1/auth/token/refresh/', { refresh: tokens.refresh })
          const { data } = await refreshing
          tokens.set({ access: data.access, refresh: data.refresh })
          config.headers.Authorization = `Bearer ${data.access}`
          return api(config)
        } catch (e) {
          // the refresh token itself was refused → signed out; a network / server
          // hiccup is not a logout — keep the session and report the failure
          if (!e?.response || e.response.status >= 500) return Promise.reject(error)
          return sessionExpired(error)
        } finally {
          refreshing = null
        }
      }
      // no refresh token to try, but we did send an access token that was
      // just rejected — it's stale, not "logged out"; a page with no token
      // at all falls through to the plain reject below (normal logged-out 401)
      if (tokens.access) return sessionExpired(error)
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
