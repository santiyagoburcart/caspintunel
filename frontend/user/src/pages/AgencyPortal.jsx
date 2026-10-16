import { useEffect, useState } from 'react'
import axios from 'axios'
import { useI18n } from '../lib/i18n'
import { jalali, toman } from '../lib/format'

// Reseller portal (PAMP's per-admin portal). Separate from the customer site:
// own token ("Agency <token>"), own HTTP client — the customer JWT, its 401
// handling and redirects are never involved. Numbers come from the server
// (PAMP's formulas); this page only formats them.

const KEY = 'agency_token'
const store = {
  get: () => { try { return localStorage.getItem(KEY) } catch { return null } },
  set: (t) => { try { t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY) } catch { /* private mode */ } },
}
const http = axios.create({ baseURL: '/api/v1/agency/portal' })
http.interceptors.request.use((cfg) => {
  const t = store.get()
  if (t) cfg.headers.Authorization = `Agency ${t}`
  return cfg
})
const errText = (e, fallback) => e?.response?.data?.detail || fallback

const T = {
  fa: {
    title: 'پرتال نمایندگان', sub: 'با نام کاربری و رمز پنل پاسارگاد خود وارد شوید',
    username: 'نام کاربری پنل', password: 'رمز عبور', login: 'ورود', logout: 'خروج', wrong: 'نام کاربری یا رمز عبور اشتباه است.',
    closed: 'پرتال نمایندگان هنوز فعال نشده است.', error: 'خطا در ارتباط با سرور', not_found: 'حساب نمایندگی برای این نام کاربری پیدا نشد.',
    limit: 'سقف ادمین', total_sold: 'حجم فروخته‌شده', used: 'مصرف‌شده', remaining: 'باقی‌مانده', deleted: 'از کاربران حذف‌شده',
    sold_limit: 'Sold Limit', hidden: 'ترافیک پنهان', usage: 'مصرف (حجم فروخته‌شده)', users: 'کاربران',
    st_active: 'فعال', st_panel_disabled: 'غیرفعال', st_pamp_limited: 'محدود‌شده', unl: 'نامحدود',
    warn: 'به {p}% سقف خود رسیده‌اید — برای افزایش سقف با پشتیبانی تماس بگیرید.',
    blocked_disabled: 'دسترسی شما روی پنل غیرفعال است.', blocked_limited: 'سقف حجم شما تمام شده و حساب محدود شده است.',
    support: 'پشتیبانی', balance: 'بدهی شما', statement: 'صورت‌حساب', none: 'هنوز گردشی ثبت نشده است.', show: 'نمایش صورت‌حساب', hide: 'بستن',
    k_quota_charge: 'شارژ حجم', k_manual_charge: 'بدهکاری', k_adjustment: 'اصلاحیه', k_payment: 'پرداخت', running: 'مانده', voided: 'باطل‌شده',
    group: 'حساب‌های گروه شما', last_sync: 'آخرین به‌روزرسانی',
  },
  en: {
    title: 'Reseller portal', sub: 'Sign in with your PasarGuard panel username and password',
    username: 'Panel username', password: 'Password', login: 'Sign in', logout: 'Sign out', wrong: 'Wrong username or password.',
    closed: 'The reseller portal is not open yet.', error: 'Could not reach the server', not_found: 'No reseller account was found for this username.',
    limit: 'Admin limit', total_sold: 'Total Sold', used: 'Used', remaining: 'Remaining', deleted: 'From deleted users',
    sold_limit: 'Sold Limit', hidden: 'Hidden traffic', usage: 'Usage (sold volume)', users: 'Users',
    st_active: 'Active', st_panel_disabled: 'Disabled', st_pamp_limited: 'Limited', unl: 'Unlimited',
    warn: 'You have used {p}% of your limit — contact support to raise it.',
    blocked_disabled: 'Your access is disabled on the panel.', blocked_limited: 'Your volume limit is used up and the account is limited.',
    support: 'Support', balance: 'You owe', statement: 'Statement', none: 'No entries yet.', show: 'Show statement', hide: 'Hide',
    k_quota_charge: 'Quota charge', k_manual_charge: 'Charge', k_adjustment: 'Adjustment', k_payment: 'Payment', running: 'Balance', voided: 'voided',
    group: 'Your group\'s accounts', last_sync: 'Last update',
  },
}
const fmt = (v, s) => (v === 'Unlimited' ? s.unl : v)
const B = ({ children }) => <bdi dir="ltr" className="ap-num">{children}</bdi>
const money = (n, lang) => (Number(n) < 0 ? '-' : '') + toman(Math.abs(Number(n || 0)), lang)

export default function AgencyPortal() {
  const { lang, setLang } = useI18n()
  const s = T[lang] || T.fa
  const [token, setToken] = useState(store.get())
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')

  const load = () => http.get('/me/').then((r) => { setData(r.data); setErr('') }).catch((e) => {
    if (e?.response?.status === 401) { store.set(null); setToken(null) }
    setErr(e?.response?.data?.code === 'portal_closed' ? s.closed : errText(e, s.error))
  })
  useEffect(() => { if (token) load() }, [token])
  useEffect(() => { document.title = s.title }, [lang])

  const logout = async () => { try { await http.post('/logout/') } catch { /* already gone */ } store.set(null); setToken(null); setData(null) }

  return (
    <div className="ap" dir={lang === 'fa' ? 'rtl' : 'ltr'}>
      <style>{CSS}</style>
      <header className="ap-top">
        <b>{s.title}</b>
        <div className="ap-top-r">
          <button type="button" className="ap-lang" onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}>{lang === 'fa' ? 'EN' : 'فا'}</button>
          {token && <button type="button" className="ap-lang" onClick={logout}>{s.logout}</button>}
        </div>
      </header>
      <main className="ap-main">
        {!token ? <LoginForm s={s} onDone={(t) => { store.set(t); setToken(t) }} /> : (
          <>
            {err && <div className="ap-alert" role="alert">{err}</div>}
            {!data && !err && <div className="ap-spin" aria-busy="true" />}
            {data?.mode === 'not_found' && <div className="ap-card ap-empty">{s.not_found}</div>}
            {data && data.mode === 'group' && <h2 className="ap-group">{s.group}</h2>}
            {data?.accounts.map((a) => <Account key={a.username} a={a} s={s} lang={lang} balance={data.balances[a.username]} />)}
          </>
        )}
      </main>
    </div>
  )
}

function LoginForm({ s, onDone }) {
  const [u, setU] = useState('')
  const [p, setP] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr('')
    try {
      const r = await http.post('/login/', { username: u.trim(), password: p })
      onDone(r.data.token)
    } catch (e2) {
      const st = e2?.response?.status
      setErr(e2?.response?.data?.code === 'portal_closed' ? s.closed : st === 400 ? s.wrong : errText(e2, s.error))
    } finally { setBusy(false) }
  }
  return (
    <form className="ap-card ap-login" onSubmit={submit}>
      <h1>{s.title}</h1>
      <p>{s.sub}</p>
      {err && <div className="ap-alert" role="alert">{err}</div>}
      <label htmlFor="ap-u">{s.username}</label>
      <input id="ap-u" className="ap-input" dir="ltr" autoComplete="username" required value={u} onChange={(e) => setU(e.target.value)} />
      <label htmlFor="ap-p">{s.password}</label>
      <input id="ap-p" className="ap-input" dir="ltr" type="password" autoComplete="current-password" required value={p} onChange={(e) => setP(e.target.value)} />
      <button className="ap-btn" disabled={busy}>{busy ? '…' : s.login}</button>
    </form>
  )
}

function Account({ a, s, lang, balance }) {
  const p = a.portal
  const [open, setOpen] = useState(false)
  const w = Math.min(Number(a.usage_percent) || 0, 100)      // bar width only
  const tone = a.usage_percent >= 100 ? 'danger' : a.usage_percent >= 80 ? 'warning' : 'primary'
  const tg = (p.support_telegram || '').replace(/^@/, '')
  const nums = [[s.limit, fmt(a.admin_limit_fmt, s)], [s.total_sold, a.total_sold_fmt], [s.used, a.used_fmt],
    [s.remaining, fmt(a.remaining_fmt, s)], [s.sold_limit, a.sold_limit_fmt], [s.hidden, a.hidden_fmt], [s.deleted, a.deleted_used_fmt]]
  return (
    <section className="ap-card">
      <div className="ap-acc-h">
        <h2><bdi>{a.username}</bdi></h2>
        <span className="ap-pill" data-st={a.status_code}>{s['st_' + a.status_code] || a.status_code}</span>
      </div>
      {p.is_blocked && (
        <div className="ap-alert" role="alert">
          {p.block_reason === 'disabled' ? s.blocked_disabled : s.blocked_limited}
          {tg && <> · <a href={`https://t.me/${tg}`} target="_blank" rel="noreferrer">{s.support} <bdi dir="ltr">{p.support_telegram}</bdi></a></>}
        </div>
      )}
      {!p.is_blocked && p.show_warning && <div className="ap-warn" role="status">{s.warn.replace('{p}', p.warning_pct)}</div>}
      {!a.is_unlimited && (
        <div className="ap-usage">
          <div className="ap-usage-l"><span>{s.usage}</span><B>{a.usage_percent}%</B></div>
          <span className="ap-bar" data-tone={tone}><i style={{ width: `${w}%` }} /></span>
        </div>
      )}
      <dl className="ap-nums">
        {nums.map(([k, v]) => <div key={k}><dt>{k}</dt><dd><B>{v}</B></dd></div>)}
      </dl>
      <div className="ap-bal">
        <span>{s.balance}</span>
        <bdi dir="ltr" className="ap-num" data-sign={Number(balance) > 0 ? 'owes' : Number(balance) < 0 ? 'credit' : 'zero'}>{money(balance, lang)}</bdi>
        <button type="button" className="ap-link" onClick={() => setOpen((v) => !v)} aria-expanded={open}>{open ? s.hide : s.show}</button>
      </div>
      {open && <Statement username={a.username} s={s} lang={lang} />}
      {a.last_synced_at && <p className="ap-foot">{s.last_sync}: {jalali(a.last_synced_at, true, lang)}</p>}
    </section>
  )
}

function Statement({ username, s, lang }) {
  const [st, setSt] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { http.get('/statement/', { params: { admin: username } }).then((r) => setSt(r.data)).catch((e) => setErr(errText(e, s.error))) }, [username])
  if (err) return <div className="ap-alert">{err}</div>
  if (!st) return <div className="ap-spin" aria-busy="true" />
  if (!st.entries.length) return <p className="ap-foot">{s.none}</p>
  return (
    <ul className="ap-st">
      {[...st.entries].reverse().map((e) => (
        <li key={e.id} data-voided={e.voided || undefined}>
          <span className="ap-st-k" data-kind={e.kind}>{s['k_' + e.kind]}</span>
          <span className="ap-st-d">{jalali(e.date, false, lang)}</span>
          <span className="ap-st-a"><B>{e.kind === 'payment' || Number(e.signed) < 0 ? '−' : '+'}{toman(Math.abs(Number(e.amount)), lang)}</B></span>
          <span className="ap-st-r">{s.running}: <B>{money(e.balance, lang)}</B></span>
          {(e.note || e.voided || e.gb) && (
            <span className="ap-st-n">{e.gb && <bdi dir="ltr">{e.gb} GB</bdi>}{e.note && <> {e.note}</>}{e.voided && <> · {s.voided}</>}</span>
          )}
        </li>
      ))}
    </ul>
  )
}

const CSS = `
.ap { min-height: 100vh; background: var(--c-bg); color: var(--c-text); font-family: Vazirmatn, Inter, sans-serif; }
.ap[dir="ltr"] { font-family: Inter, Vazirmatn, sans-serif; }
.ap-top { position: sticky; top: 0; z-index: 5; display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 10px 16px; background: color-mix(in srgb, var(--c-bg) 92%, transparent); backdrop-filter: blur(8px); border-bottom: 1px solid var(--c-border); }
.ap-top-r { display: flex; gap: 8px; }
.ap-lang { min-height: 40px; padding: 0 12px; border-radius: 10px; border: 1px solid var(--c-border); background: var(--c-surface); color: var(--c-text); font-weight: 700; font-size: 13px; }
.ap-main { max-width: 640px; margin: 0 auto; padding: 16px; display: flex; flex-direction: column; gap: 14px; }
.ap-card { background: linear-gradient(var(--c-surface), var(--c-surface)), var(--c-bg); border: 1px solid var(--c-border); border-radius: 16px; padding: 16px; }
.ap-login { display: flex; flex-direction: column; gap: 8px; margin-top: 8vh; }
.ap-login h1 { font-size: 20px; font-weight: 800; }
.ap-login p { font-size: 13px; color: var(--c-muted-fg); margin-bottom: 6px; }
.ap-login label { font-size: 12.5px; font-weight: 700; margin-top: 4px; }
.ap-input { height: 46px; border-radius: 12px; border: 1px solid var(--c-border); background: var(--c-surface); color: var(--c-text); padding: 0 12px; font-size: 16px; }
.ap-input:focus { outline: 2px solid color-mix(in srgb, var(--c-primary) 45%, transparent); }
.ap-btn { margin-top: 10px; min-height: 48px; border-radius: 12px; background: color-mix(in srgb, var(--c-primary) 82%, #000); color: #fff; font-weight: 800; font-size: 15px; border: 0; }
.ap-btn:disabled { opacity: .6; }
.ap-alert { padding: 10px 12px; border-radius: 12px; font-size: 13px; line-height: 1.7; color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 10%, transparent); margin: 6px 0; }
.ap-alert a { color: inherit; font-weight: 700; }
.ap-warn { padding: 10px 12px; border-radius: 12px; font-size: 13px; color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 12%, transparent); margin: 6px 0; }
.ap-empty { font-size: 14px; color: var(--c-muted-fg); }
.ap-group { font-size: 14px; font-weight: 800; color: var(--c-muted-fg); }
.ap-acc-h { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
.ap-acc-h h2 { font-size: 17px; font-weight: 800; overflow-wrap: anywhere; }
.ap-pill { font-size: 12px; font-weight: 700; padding: 3px 10px; border-radius: 999px; color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 14%, transparent); white-space: nowrap; }
.ap-pill[data-st="panel_disabled"] { color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 14%, transparent); }
.ap-pill[data-st="pamp_limited"] { color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 14%, transparent); }
.ap-num { font-family: 'JetBrains Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }
.ap-usage { margin: 10px 0; }
.ap-usage-l { display: flex; justify-content: space-between; font-size: 12.5px; font-weight: 700; color: var(--c-muted-fg); margin-bottom: 6px; }
.ap-bar { display: block; height: 10px; border-radius: 999px; background: color-mix(in srgb, var(--c-text-muted) 18%, transparent); overflow: hidden; }
.ap-bar i { display: block; height: 100%; border-radius: inherit; background: var(--c-primary); }
.ap-bar[data-tone="warning"] i { background: var(--c-warning); } .ap-bar[data-tone="danger"] i { background: var(--c-danger); }
.ap-nums { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 10px; }
.ap-nums > div { padding: 10px 12px; border-radius: 12px; border: 1px solid var(--c-border); min-width: 0; }
.ap-nums dt { font-size: 11.5px; font-weight: 600; color: var(--c-muted-fg); }
.ap-nums dd { font-size: 16px; font-weight: 800; margin-top: 2px; overflow-wrap: anywhere; }
.ap-bal { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--c-border); font-size: 13.5px; font-weight: 700; }
.ap-bal .ap-num { font-size: 16px; font-weight: 800; }
.ap-bal [data-sign="owes"] { color: var(--c-danger-fg); } .ap-bal [data-sign="credit"] { color: var(--c-success-fg); }
.ap-link { margin-inline-start: auto; min-height: 40px; padding: 0 12px; border-radius: 10px; color: var(--c-primary-fg); font-weight: 700; font-size: 13px; background: transparent; border: 1px solid var(--c-border); }
.ap-st { display: flex; flex-direction: column; margin-top: 8px; }
.ap-st li { display: grid; grid-template-columns: auto 1fr auto; gap: 2px 10px; align-items: center; padding: 9px 0; border-top: 1px solid var(--c-border); font-size: 13px; }
.ap-st li[data-voided] { opacity: .55; }
.ap-st-k { font-size: 11.5px; font-weight: 700; padding: 2px 9px; border-radius: 999px; color: var(--c-primary-fg); background: color-mix(in srgb, var(--c-primary) 12%, transparent); }
.ap-st-k[data-kind="payment"] { color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 14%, transparent); }
.ap-st-d { color: var(--c-muted-fg); font-size: 12.5px; }
.ap-st-a { font-weight: 800; }
.ap-st-r, .ap-st-n { grid-column: 1 / -1; font-size: 12px; color: var(--c-muted-fg); }
.ap-foot { font-size: 12px; color: var(--c-muted-fg); margin-top: 10px; }
.ap-spin { width: 28px; height: 28px; margin: 24px auto; border-radius: 50%; border: 3px solid var(--c-border); border-top-color: var(--c-primary); animation: ap-r 0.8s linear infinite; }
@keyframes ap-r { to { transform: rotate(360deg); } }
@media (min-width: 640px) { .ap-nums { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
`
