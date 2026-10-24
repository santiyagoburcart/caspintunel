import { useEffect, useState } from 'react'
import axios from 'axios'
import { clientId } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali, toman } from '../lib/format'
import { ACCENT_CSS, Ic } from '../components/AgencyIcons'
import { useToast } from '../components/Toast'

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
  const cid = clientId()
  if (cid) cfg.headers['X-Client-Id'] = cid
  return cfg
})
const errText = (e, fallback) => e?.response?.data?.detail || fallback

const T = {
  fa: {
    title: 'پرتال نمایندگان', sub: 'با نام کاربری و رمز پنل پاسارگاد خود وارد شوید',
    username: 'نام کاربری پنل', password: 'رمز عبور', login: 'ورود', logout: 'خروج', wrong: 'نام کاربری یا رمز عبور اشتباه است.',
    closed: 'پرتال نمایندگان هنوز فعال نشده است.', error: 'خطا در ارتباط با سرور', not_found: 'حساب نمایندگی برای این نام کاربری پیدا نشد.',
    limit: 'سقف ادمین', total_sold: 'حجم فروخته‌شده', used: 'مصرف‌شده', remaining: 'باقی‌مانده', deleted: 'از کاربران حذف‌شده',
    sold_limit: 'Sold Limit', hidden: 'ترافیک پنهان', usage: 'مصرف از سقف', users: 'کاربران', used_of: '{u} از {l}',
    st_active: 'فعال', st_panel_disabled: 'غیرفعال', st_pamp_limited: 'محدود‌شده', unl: 'نامحدود',
    warn: 'به {p}% سقف خود رسیده‌اید — برای افزایش سقف با پشتیبانی تماس بگیرید.',
    blocked_disabled: 'دسترسی شما روی پنل غیرفعال است.', blocked_limited: 'سقف حجم شما تمام شده و حساب محدود شده است.',
    support: 'پشتیبانی', balance: 'بدهی شما', statement: 'صورت‌حساب', none: 'هنوز گردشی ثبت نشده است.', show: 'نمایش صورت‌حساب', hide: 'بستن',
    k_quota_charge: 'شارژ حجم', k_manual_charge: 'بدهکاری', k_adjustment: 'اصلاحیه', k_payment: 'پرداخت', running: 'مانده', voided: 'باطل‌شده',
    group: 'حساب‌های گروه شما', last_sync: 'آخرین به‌روزرسانی', welcome: 'خوش آمدید', bye: 'از پرتال خارج شدید', net: 'ارتباط با سرور برقرار نشد — اینترنت را بررسی کنید.', expired: 'نشست شما تمام شده — دوباره وارد شوید.', locked: 'به‌دلیل تلاش‌های ناموفق، ورود موقتاً بسته شده است — چند دقیقه بعد تلاش کنید.',
  },
  en: {
    title: 'Reseller portal', sub: 'Sign in with your PasarGuard panel username and password',
    username: 'Panel username', password: 'Password', login: 'Sign in', logout: 'Sign out', wrong: 'Wrong username or password.',
    closed: 'The reseller portal is not open yet.', error: 'Could not reach the server', not_found: 'No reseller account was found for this username.',
    limit: 'Admin limit', total_sold: 'Total Sold', used: 'Used', remaining: 'Remaining', deleted: 'From deleted users',
    sold_limit: 'Sold Limit', hidden: 'Hidden traffic', usage: 'Usage of limit', users: 'Users', used_of: '{u} of {l}',
    st_active: 'Active', st_panel_disabled: 'Disabled', st_pamp_limited: 'Limited', unl: 'Unlimited',
    warn: 'You have used {p}% of your limit — contact support to raise it.',
    blocked_disabled: 'Your access is disabled on the panel.', blocked_limited: 'Your volume limit is used up and the account is limited.',
    support: 'Support', balance: 'You owe', statement: 'Statement', none: 'No entries yet.', show: 'Show statement', hide: 'Hide',
    k_quota_charge: 'Quota charge', k_manual_charge: 'Charge', k_adjustment: 'Adjustment', k_payment: 'Payment', running: 'Balance', voided: 'voided',
    group: 'Your group\'s accounts', last_sync: 'Last update', welcome: 'Welcome', bye: 'You signed out of the portal', net: 'Could not reach the server — check your connection.', expired: 'Your session ended — please sign in again.', locked: 'Too many failed attempts — sign-in is paused for a few minutes.',
  },
}
const fmt = (v, s) => (v === 'Unlimited' ? s.unl : v)
const B = ({ children }) => <bdi dir="ltr" className="ap-num">{children}</bdi>
// GB figure next to a TB value (1 TB = 1024 GB), from the raw bytes; none under 1 TB
const GB = ({ b, signed }) => {
  if (b == null || Math.abs(Number(b)) < 1024 ** 4) return null
  const n = Math.round(Number(b) / 1024 ** 3)
  return <bdi dir="ltr" className="ap-gb">{`${signed && n > 0 ? '+' : ''}${n.toLocaleString('en-US')} GB`}</bdi>
}
// the admin limit reads in exact GB ("5,200 GB"); the server's TB figure is the small
// secondary text from 1 TB up. b = limit bytes (null/0 = Unlimited), tb = its *_fmt.
const Lim = ({ b, tb, s }) => {
  if (!(Number(b) > 0)) return <B>{s.unl}</B>
  return <><B>{`${(Number(b) / 1024 ** 3).toLocaleString('en-US', { maximumFractionDigits: 2 })} GB`}</B>{Number(b) >= 1024 ** 4 && tb && <bdi dir="ltr" className="ap-gb">{tb}</bdi>}</>
}
const money = (n, lang) => (Number(n) < 0 ? '-' : '') + toman(Math.abs(Number(n || 0)), lang)

export default function AgencyPortal() {
  const { lang, setLang } = useI18n()
  const s = T[lang] || T.fa
  const [token, setToken] = useState(store.get())
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const toast = useToast()

  const load = () => http.get('/me/').then((r) => { setData(r.data); setErr('') }).catch((e) => {
    if (e?.response?.status === 401) { store.set(null); setToken(null); toast.error(s.expired); return }
    const m = e?.response?.data?.code === 'portal_closed' ? s.closed : !e?.response ? s.net : errText(e, s.error)
    setErr(m); toast.error(m)
  })
  useEffect(() => { if (token) load() }, [token])
  useEffect(() => { document.title = s.title }, [lang])

  const logout = async () => { try { await http.post('/logout/') } catch { /* already gone */ } store.set(null); setToken(null); setData(null); toast.success(s.bye) }

  return (
    <div className="ap" dir={lang === 'fa' ? 'rtl' : 'ltr'}>
      <style>{ACCENT_CSS + CSS}</style>
      <header className="ap-top">
        <b>{s.title}</b>
        <div className="ap-top-r">
          <button type="button" className="ap-lang" onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}><Ic n="globe" />{lang === 'fa' ? 'EN' : 'فا'}</button>
          {token && <button type="button" className="ap-lang" onClick={logout}><Ic n="logout" />{s.logout}</button>}
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
  const toast = useToast()
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr('')
    try {
      const r = await http.post('/login/', { username: u.trim(), password: p })
      toast.success(s.welcome)
      onDone(r.data.token)
    } catch (e2) {
      const st = e2?.response?.status
      const m = e2?.response?.data?.code === 'portal_closed' ? s.closed : st === 400 ? s.wrong : st === 429 ? s.locked
        : !e2?.response ? s.net : errText(e2, s.error)
      setErr(m); toast.error(m)
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
      <button className="ap-btn" disabled={busy}>{busy ? <span className="ap-btn-spin" aria-hidden="true" /> : <Ic n="login" size={17} />}{s.login}</button>
    </form>
  )
}

function Account({ a, s, lang, balance }) {
  const p = a.portal
  const [open, setOpen] = useState(false)
  const w = Math.min(Number(a.usage_percent) || 0, 100)      // bar width only
  const tone = a.usage_percent >= 100 ? 'danger' : a.usage_percent >= 80 ? 'warning' : 'primary'
  const tg = (p.support_telegram || '').replace(/^@/, '')
  const by = a.bytes || {}
  const nums = [[s.limit, <Lim b={by.limit} tb={a.admin_limit_fmt} s={s} />, 'cyan', 'limit'], [s.total_sold, a.total_sold_fmt, 'blue', 'sold', by.total_sold], [s.used, a.used_fmt, 'purple', 'used', by.used],
    [s.remaining, fmt(a.remaining_fmt, s), 'green', 'remaining', by.remaining], [s.sold_limit, a.sold_limit_fmt, 'cyan', 'limit', by.sold_limit, true], [s.hidden, a.hidden_fmt, 'orange', 'hidden', by.hidden],
    [s.deleted, a.deleted_used_fmt, 'gray', 'trash', by.deleted]]
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
          <p className="ap-usage-s">{s.used_of.split('{u}')[0]}<B>{a.used_fmt}</B><GB b={by.used} />{s.used_of.split('{u}')[1].split('{l}')[0]}<Lim b={by.limit} tb={a.admin_limit_fmt} s={s} />{s.used_of.split('{l}')[1]}</p>
        </div>
      )}
      <dl className="ap-nums">
        {nums.map(([k, v, ac, ic, b, signed]) => <div key={k} data-ac={ac}><dt><Ic n={ic} size={13} />{k}</dt><dd>{typeof v === 'string' ? <><B>{v}</B><GB b={b} signed={signed} /></> : v}</dd></div>)}
      </dl>
      <div className="ap-bal">
        <span>{s.balance}</span>
        <bdi dir="ltr" className="ap-num" data-sign={Number(balance) > 0 ? 'owes' : Number(balance) < 0 ? 'credit' : 'zero'}>{money(balance, lang)}</bdi>
        <button type="button" className="ap-link" onClick={() => setOpen((v) => !v)} aria-expanded={open}><Ic n="doc" />{open ? s.hide : s.show}</button>
      </div>
      {open && <Statement username={a.username} s={s} lang={lang} />}
      {a.last_synced_at && <p className="ap-foot">{s.last_sync}: {jalali(a.last_synced_at, true, lang)}</p>}
    </section>
  )
}

function Statement({ username, s, lang }) {
  const [st, setSt] = useState(null)
  const [err, setErr] = useState('')
  const toast = useToast()
  useEffect(() => { http.get('/statement/', { params: { admin: username } }).then((r) => setSt(r.data)).catch((e) => { const m = errText(e, s.error); setErr(m); toast.error(m) }) }, [username])
  if (err) return <div className="ap-alert">{err}</div>
  if (!st) return <div className="ap-spin" aria-busy="true" />
  if (!st.entries.length) return <p className="ap-foot">{s.none}</p>
  return (
    <ul className="ap-st">
      {[...st.entries].reverse().map((e) => (
        <li key={e.id} data-voided={e.voided || undefined}>
          <span className="ap-st-k" data-kind={e.kind}>{s['k_' + e.kind]}</span>
          <span className="ap-st-d">{jalali(e.date, false, lang)}</span>
          <span className="ap-st-a" data-sign={e.voided ? 'zero' : e.kind === 'payment' || Number(e.signed) < 0 ? 'credit' : 'owes'}><B>{e.kind === 'payment' || Number(e.signed) < 0 ? '−' : '+'}{toman(Math.abs(Number(e.amount)), lang)}</B></span>
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
.ap-lang { min-height: 40px; padding: 0 12px; border-radius: 10px; border: 1px solid transparent; background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); color: var(--c-text); font-weight: 700; font-size: 13px; }
.ap-lang:hover { background: color-mix(in srgb, var(--c-text-muted) 20%, transparent); }
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
.ap-pill { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; font-weight: 700; padding: 3px 10px; border-radius: 999px; color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 14%, transparent); white-space: nowrap; }
.ap-pill[data-st="panel_disabled"] { color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 14%, transparent); }
.ap-pill[data-st="pamp_limited"] { color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 14%, transparent); }
.ap-num { font-family: 'JetBrains Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }
.ap-usage { margin: 10px 0; }
.ap-usage-l { display: flex; justify-content: space-between; font-size: 12.5px; font-weight: 700; color: var(--c-muted-fg); margin-bottom: 6px; }
.ap-bar { display: block; height: 10px; border-radius: 999px; background: color-mix(in srgb, var(--c-text-muted) 18%, transparent); overflow: hidden; }
.ap-usage-s { font-size: 12px; color: var(--c-muted-fg); margin-top: 6px; }
.ap-bar i { display: block; height: 100%; border-radius: inherit; background: var(--c-primary); }
.ap-bar[data-tone="warning"] i { background: var(--c-warning); } .ap-bar[data-tone="danger"] i { background: var(--c-danger); }
.ap-nums { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 10px; }
.ap-nums > div { padding: 10px 12px; border-radius: 12px; border: 1px solid var(--c-border); min-width: 0; border-top: 3px solid var(--ac, var(--c-border)); }
.ap-nums dt { font-size: 11.5px; font-weight: 600; color: var(--c-muted-fg); display: flex; align-items: center; gap: 5px; }
.ap-nums dt .agi { color: var(--ac); }
.ap-nums dd { font-size: 16px; font-weight: 800; margin-top: 2px; overflow-wrap: anywhere; }
.ap-bal { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--c-border); font-size: 13.5px; font-weight: 700; }
.ap-bal .ap-num { font-size: 16px; font-weight: 800; }
.ap-bal [data-sign="owes"] { color: var(--c-danger-fg); } .ap-bal [data-sign="credit"] { color: var(--c-success-fg); } .ap-bal [data-sign="zero"] { color: var(--c-muted-fg); }
.ap-link { margin-inline-start: auto; min-height: 40px; padding: 0 12px; border-radius: 10px; color: var(--c-text); font-weight: 700; font-size: 13px; background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); border: 1px solid transparent; }
.ap-link:hover { background: color-mix(in srgb, var(--c-text-muted) 20%, transparent); }
.ap-st { display: flex; flex-direction: column; margin-top: 8px; }
.ap-st li { display: grid; grid-template-columns: auto 1fr auto; gap: 2px 10px; align-items: center; padding: 9px 0; border-top: 1px solid var(--c-border); font-size: 13px; }
.ap-st li[data-voided] { opacity: .55; }
.ap-st-k { font-size: 11.5px; font-weight: 700; padding: 2px 9px; border-radius: 999px; color: var(--c-primary-fg); background: color-mix(in srgb, var(--c-primary) 12%, transparent); }
.ap-st-k[data-kind="payment"] { color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 14%, transparent); }
.ap-st-d { color: var(--c-muted-fg); font-size: 12.5px; }
.ap-st-a { font-weight: 800; }
.ap-st-a[data-sign="owes"] { color: var(--c-danger-fg); } .ap-st-a[data-sign="credit"] { color: var(--c-success-fg); } .ap-st-a[data-sign="zero"] { color: var(--c-muted-fg); }
.ap-st-r, .ap-st-n { grid-column: 1 / -1; font-size: 12px; color: var(--c-muted-fg); }
.ap-foot { font-size: 12px; color: var(--c-muted-fg); margin-top: 10px; }
.ap-spin { width: 28px; height: 28px; margin: 24px auto; border-radius: 50%; border: 3px solid var(--c-border); border-top-color: var(--c-primary); animation: ap-r 0.8s linear infinite; }
@keyframes ap-r { to { transform: rotate(360deg); } }
@media (min-width: 640px) { .ap-nums { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
.ap-pill::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.ap-lang, .ap-link, .ap-btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; transition: background-color .15s, transform .08s; }
.ap-lang:active, .ap-link:active, .ap-btn:active:not(:disabled) { transform: translateY(1px) scale(.98); }
.ap-btn:hover:not(:disabled) { background: color-mix(in srgb, var(--c-primary) 70%, #000); }
.ap-btn:active:not(:disabled) { background: color-mix(in srgb, var(--c-primary) 60%, #000); }
.ap-btn:focus-visible, .ap-lang:focus-visible, .ap-link:focus-visible { outline: 2px solid var(--c-primary); outline-offset: 2px; }
.ap-btn-spin { width: 16px; height: 16px; border-radius: 50%; border: 2px solid currentColor; border-inline-end-color: transparent; animation: ap-r .7s linear infinite; }
.ap-st li:hover { background: color-mix(in srgb, var(--c-primary) 4%, transparent); }
.ap-gb { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: .74em; font-weight: 500; color: var(--c-muted-fg); margin: 0 6px; white-space: nowrap; }
.ap-nums dd .ap-gb { display: block; margin: 0; font-size: 11.5px; margin-top: 1px; }
`
