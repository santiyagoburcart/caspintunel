import { ADMIN_BASE } from './base'
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
  if (tokens.access) cfg.headers.Authorization = `Bearer ${tokens.access}`
  const cid = clientId()
  if (cid) cfg.headers['X-Client-Id'] = cid
  return cfg
})

// clear the stale session and bounce to login — never let the raw JWT error
// reach a page-level catch; the redirect is already underway when the caller
// would otherwise see this promise settle, so it deliberately never resolves
function sessionExpired() {
  tokens.clear()
  if (!location.pathname.endsWith('/login')) {
    try { sessionStorage.setItem(SESSION_EXPIRED_KEY, '1') } catch { /* private browsing */ }
    location.href = `${ADMIN_BASE}/login`
  }
  return new Promise(() => {})
}

let refreshing = null
api.interceptors.response.use(
  (r) => { report(r.config, { ok: true, data: r.data, status: r.status }); return r },
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
