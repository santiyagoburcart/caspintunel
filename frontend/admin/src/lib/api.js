import { ADMIN_BASE } from './base'
import axios from 'axios'

const ACCESS = 'cta_access'
const REFRESH = 'cta_refresh'
export const SESSION_EXPIRED_KEY = 'cta_session_expired'
// per-operator page state that a logout / another login must not leave behind
const OPERATOR_SESSION_KEYS = ['ti_filters', 'an_period']

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

/** Everything the panel keeps for a signed-in operator (tokens + per-operator page state). */
export function clearAuthState() {
  tokens.clear()
  OPERATOR_SESSION_KEYS.forEach((k) => { try { sessionStorage.removeItem(k) } catch { /* ignore */ } })
}

// A JWT's payload, or null — only read to drop tokens that can never work (a customer
// token, an expired refresh token); the server still verifies everything.
function claims(t) {
  try {
    const p = t.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(atob(p + '='.repeat((4 - (p.length % 4)) % 4)))
  } catch { return null }
}
const alive = (c) => !!c && (!c.exp || c.exp * 1000 > Date.now() + 5000)

/** Panel tokens left by an older visit / version that can't work any more are dropped
 * before the first request, so they are never sent (v1.30.2). */
export function pruneStoredTokens() {
  const a = tokens.access && claims(tokens.access)
  const r = tokens.refresh && claims(tokens.refresh)
  const accessOk = a && a.type === 'staff_access'
  const refreshOk = r && r.type === 'staff_refresh' && alive(r)
  if ((tokens.access && !accessOk) || (tokens.refresh && !refreshOk)) clearAuthState()
  else if (tokens.access && !alive(a) && !tokens.refresh) clearAuthState()
}
pruneStoredTokens()

// sign-in endpoints: never send a stored token and never try a refresh for them
const AUTH_CALL = /^\/?(api\/v1\/)?admin\/auth\/(login|refresh|logout)\//
export const isAuthCall = (url) => AUTH_CALL.test(url || '')

export const api = axios.create({ baseURL: '/api/v1' })

// Feedback for every action: each POST/PUT/PATCH/DELETE through `api` reports its
// outcome to <FeedbackBridge> (a toast: success, or the real failure reason).
// Pass `{ quiet: true }` in the request config for calls that are not user
// actions (login, live previews). A page toast shown afterwards replaces it.
export const feedback = { emit: null }
const MUTATING = new Set(['post', 'put', 'patch', 'delete'])
const report = (cfg, payload) => {
  if (!cfg || cfg.quiet || !MUTATING.has((cfg.method || '').toLowerCase())) return
  try { feedback.emit?.({ method: cfg.method.toLowerCase(), url: cfg.url || '', ...payload }) } catch { /* never break a request */ }
}

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
// Already on the login page the error is returned instead (never a hanging spinner).
function sessionExpired(error) {
  clearAuthState()
  if (location.pathname.endsWith('/login')) return Promise.reject(error)
  try { sessionStorage.setItem(SESSION_EXPIRED_KEY, '1') } catch { /* private browsing */ }
  location.href = `${ADMIN_BASE}/login`
  return new Promise(() => {})
}

const isCsrfFailure = (r) => r?.status === 403 && /csrf/i.test(String(r?.data?.detail || ''))

let refreshing = null
api.interceptors.response.use(
  (r) => { report(r.config, { ok: true, data: r.data, status: r.status }); return r },
  async (error) => {
    const { response, config } = error
    const auth = config && isAuthCall(config.url)
    if (!auth && isCsrfFailure(response)) return sessionExpired(error)   // an old cookie session got in the way
    if (!auth && response?.status === 401 && config && !config._retry) {
      config._retry = true
      if (tokens.refresh) {
        try {
          // bare axios: no stored (stale) access token rides along
          refreshing = refreshing || axios.post('/api/v1/admin/auth/refresh/', { refresh: tokens.refresh })
          const { data } = await refreshing
          tokens.set({ access: data.access, refresh: data.refresh })
          config.headers.Authorization = `Bearer ${data.access}`
          return api(config)
        } catch (e) {
          // a refused refresh token = signed out; a network / server hiccup is not
          if (!e?.response || e.response.status >= 500) { report(config, { ok: false, error }); return Promise.reject(error) }
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
    report(config, { ok: false, error })
    return Promise.reject(error)
  },
)

/** The real reason of a failed request, for people: field errors with their field,
 * file-size / network / server failures in words (fa / en). */
export function failureReason(e, lang = 'fa') {
  const fa = lang !== 'en'
  const st = e?.response?.status
  const d = e?.response?.data
  if (!e?.response) return fa ? 'ارتباط با سرور برقرار نشد — اینترنت یا سرور را بررسی کنید.' : 'Could not reach the server — check the connection.'
  if (st === 413) return fa ? 'حجم فایل بیش از حد مجاز است (حداکثر 15 مگابایت).' : 'The file is too large (max 15 MB).'
  if (st === 415) return fa ? 'نوع فایل پشتیبانی نمی‌شود.' : 'Unsupported file type.'
  if (st === 403) return (d && typeof d.detail === 'string' && d.detail) || (fa ? 'اجازهٔ این کار را ندارید.' : 'You do not have permission for this.')
  if (d && typeof d === 'object' && !Array.isArray(d)) {
    if (fa && typeof d.detail_fa === 'string') return d.detail_fa   // a server reason written in Persian too
    if (typeof d.detail === 'string') return d.detail
    if (typeof d.message === 'string' && d.ok === false) return d.message
    const parts = Object.entries(d).filter(([k]) => k !== 'code').slice(0, 2).map(([k, v]) => {
      const msg = Array.isArray(v) ? v.map((x) => (typeof x === 'object' ? JSON.stringify(x) : x)).join(' ') : (typeof v === 'object' ? JSON.stringify(v) : String(v))
      return k === 'non_field_errors' ? msg : `${k}: ${msg}`
    })
    if (parts.length) return parts.join(' · ')
  }
  if (typeof d === 'string' && d.length < 200 && !d.trim().startsWith('<')) return d
  return fa ? `خطای سرور (${st}) — دوباره تلاش کنید.` : `Server error (${st}) — please try again.`
}

export function apiError(e, fallback = 'خطایی رخ داد') {
  const d = e?.response?.data
  if (!d) return fallback
  // a stale/expired token slipping past the interceptor must never show its
  // technical detail — fall back to whatever generic message the caller gave
  if (['token_not_valid', 'token_expired', 'token_revoked'].includes(d.code)) return fallback
  if (typeof d === 'string') return d
  if (d.detail) return d.detail
  const first = Object.values(d)[0]
  return Array.isArray(first) ? first[0] : String(first || fallback)
}
