import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import axios from 'axios'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { clientId } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali, toman } from '../lib/format'
import { useTheme } from '../theme/ThemeProvider'
import { ACCENT_CSS, Ic } from '../components/AgencyIcons'
import { useToast } from '../components/Toast'
import { useConfirm } from '../components/ConfirmDialog'
import { PORTAL_PATH } from '../lib/paths'
import { PortalInvoices, PortalRequest, PortalRequests } from '../components/AgencyBilling'
import { AgencyBell, AgencyNotificationsPage } from '../components/AgencyBell'
import { InfoTip, ST, ST_CSS } from '../components/AgencyStats'
import { playChime, unlockSound } from '../lib/notifySound'
import { currentSubscription, needsHomeScreen, pushSupported, subscribePush, unsubscribePush } from '../lib/webPush'

// Reseller portal (PAMP's per-admin portal). Separate from the customer site:
// own token ("Agency <token>"), own HTTP client — the customer JWT, its 401
// handling and redirects are never involved. Numbers come from the server
// (PAMP's formulas); this page only formats them.
// v1.38.2: sections with a menu (desktop sidebar, phone ☰ drawer), header bell + notifications page
// (components/AgencyBell.jsx, shared with the group-manager panel), «پرداخت کل بدهی», settings, red «خروج» with a confirm,
// and a new-build check so a tab left open picks up a deploy.

const KEY = 'agency_token'
const SOUND_KEY = 'agency_notify'
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
const soundPrefs = () => { try { return { on: true, volume: 60, ...JSON.parse(localStorage.getItem(SOUND_KEY) || '{}') } } catch { return { on: true, volume: 60 } } }

const T = {
  fa: {
    title: 'پرتال نمایندگان', sub: 'با نام کاربری و رمز پنل پاسارگاد خود وارد شوید',
    username: 'نام کاربری پنل', password: 'رمز عبور', login: 'ورود', logout: 'خروج', wrong: 'نام کاربری یا رمز عبور اشتباه است.',
    closed: 'پرتال نمایندگان هنوز فعال نشده است.', error: 'خطا در ارتباط با سرور', not_found: 'حساب نمایندگی برای این نام کاربری پیدا نشد.',
    limit: 'سقف ادمین', total_sold: 'حجم فروخته‌شده', used: 'مصرف‌شده', remaining: 'باقی‌مانده', deleted: 'مصرف کاربران حذف‌شده',
    sold_limit: 'سقف فروش باقی‌مانده', hidden: 'ترافیک پنهان', usage: 'مصرف از سقف', users: 'کاربران', used_of: '{u} از {l}',
    st_active: 'فعال', st_panel_disabled: 'غیرفعال', st_pamp_limited: 'محدود‌شده', unl: 'نامحدود',
    warn: 'به {p}% سقف خود رسیده‌اید — برای افزایش سقف با پشتیبانی تماس بگیرید.',
    blocked_disabled: 'دسترسی شما روی پنل غیرفعال است.', blocked_limited: 'سقف حجم شما تمام شده و حساب محدود شده است.',
    support: 'پشتیبانی', balance: 'بدهی شما', statement: 'صورت‌حساب', none: 'هنوز گردشی ثبت نشده است.',
    k_quota_charge: 'شارژ حجم', k_manual_charge: 'بدهکاری', k_adjustment: 'اصلاحیه', k_payment: 'پرداخت', running: 'مانده', voided: 'باطل‌شده',
    mgr_link: 'مدیر گروه هستید؟ ورود مدیران گروه',
    use_panel: 'لطفاً از پنل مدیریت گروه وارد شوید', open_panel: 'ورود به پنل مدیریت گروه',
    readonly: 'حساب شما با مدیر گروه {m} است — درخواست شارژ و پرداخت از طریق ایشان انجام می‌شود؛ اینجا فقط مصرف خود را می‌بینید.', group: 'حساب‌های گروه شما', last_sync: 'آخرین به‌روزرسانی', welcome: 'خوش آمدید', bye: 'از پرتال خارج شدید', net: 'ارتباط با سرور برقرار نشد — اینترنت را بررسی کنید.', expired: 'نشست شما تمام شده — دوباره وارد شوید.', locked: 'به‌دلیل تلاش‌های ناموفق، ورود موقتاً بسته شده است — چند دقیقه بعد تلاش کنید.',
    n_dash: 'داشبورد', n_request: 'درخواست شارژ', n_requests: 'درخواست‌های من', n_invoices: 'فاکتورها و پرداخت', n_statement: 'صورت‌حساب', n_notifications: 'اعلان‌ها', n_settings: 'تنظیمات',
    menu: 'منو', close: 'بستن', logout_q: 'از پرتال خارج می‌شوید؟', logout_msg: 'برای ادامه باید دوباره با نام کاربری و رمز پنل وارد شوید.',
    owe_go: 'مشاهده و پرداخت', set_lang: 'زبان', set_theme: 'پوسته', light: 'روشن', dark: 'تاریک', set_prefs: 'نمایش', set_notify: 'اعلان‌ها',
    set_sound: 'صدای اعلان', set_sound_d: 'با رسیدن اعلان تازه (فاکتور، پرداخت، نتیجهٔ درخواست) یک صدای کوتاه پخش می‌شود.', set_volume: 'بلندی صدا', set_test: 'پخش آزمایشی',
    set_push: 'اعلان مرورگر', set_push_d: 'حتی وقتی پرتال بسته است، اعلان روی این دستگاه نشان داده می‌شود.', push_on: 'روشن کردن', push_off_btn: 'خاموش کردن', push_test: 'ارسال اعلان آزمایشی',
    push_off: 'اعلان مرورگر روی سرور فعال نیست.', push_ios: 'در آیفون اول پرتال را به صفحهٔ اصلی (Add to Home Screen) اضافه کنید.', push_unsupported: 'این مرورگر اعلان مرورگر را پشتیبانی نمی‌کند.', push_denied: 'اجازهٔ اعلان در مرورگر داده نشد.',
    account: 'حساب', new_build: 'نسخهٔ تازهٔ پرتال آماده است.', reload: 'بارگذاری دوباره', ro_short: 'فقط مشاهده (با مدیر گروه)',
  },
  en: {
    title: 'Reseller portal', sub: 'Sign in with your PasarGuard panel username and password',
    username: 'Panel username', password: 'Password', login: 'Sign in', logout: 'Sign out', wrong: 'Wrong username or password.',
    closed: 'The reseller portal is not open yet.', error: 'Could not reach the server', not_found: 'No reseller account was found for this username.',
    limit: 'Admin limit', total_sold: 'Total sold', used: 'Used', remaining: 'Remaining', deleted: 'Deleted users’ traffic',
    sold_limit: 'Sell limit left', hidden: 'Hidden traffic', usage: 'Usage of limit', users: 'Users', used_of: '{u} of {l}',
    st_active: 'Active', st_panel_disabled: 'Disabled', st_pamp_limited: 'Limited', unl: 'Unlimited',
    warn: 'You have used {p}% of your limit — contact support to raise it.',
    blocked_disabled: 'Your access is disabled on the panel.', blocked_limited: 'Your volume limit is used up and the account is limited.',
    support: 'Support', balance: 'You owe', statement: 'Statement', none: 'No entries yet.',
    k_quota_charge: 'Quota charge', k_manual_charge: 'Charge', k_adjustment: 'Adjustment', k_payment: 'Payment', running: 'Balance', voided: 'voided',
    mgr_link: 'Group manager? Sign in here',
    use_panel: 'Please sign in at the group-manager panel', open_panel: 'Open the group-manager panel',
    readonly: 'Your account is with your group manager {m} — volume requests and payments go through them; here you only see your usage.', group: 'Your group\'s accounts', last_sync: 'Last update', welcome: 'Welcome', bye: 'You signed out of the portal', net: 'Could not reach the server — check your connection.', expired: 'Your session ended — please sign in again.', locked: 'Too many failed attempts — sign-in is paused for a few minutes.',
    n_dash: 'Dashboard', n_request: 'Request volume', n_requests: 'My requests', n_invoices: 'Invoices & payments', n_statement: 'Statement', n_notifications: 'Notifications', n_settings: 'Settings',
    menu: 'Menu', close: 'Close', logout_q: 'Sign out of the portal?', logout_msg: 'You will need to sign in again with your panel username and password.',
    owe_go: 'View and pay', set_lang: 'Language', set_theme: 'Theme', light: 'Light', dark: 'Dark', set_prefs: 'Display', set_notify: 'Notifications',
    set_sound: 'Notification sound', set_sound_d: 'A short sound plays when a new notification arrives (invoice, payment, request result).', set_volume: 'Volume', set_test: 'Play a test',
    set_push: 'Browser notifications', set_push_d: 'Shown on this device even while the portal is closed.', push_on: 'Turn on', push_off_btn: 'Turn off', push_test: 'Send a test notification',
    push_off: 'Browser notifications are not configured on the server.', push_ios: 'On iPhone, add the portal to the Home Screen first.', push_unsupported: 'This browser does not support browser notifications.', push_denied: 'Notification permission was not given.',
    account: 'Account', new_build: 'A new version of the portal is ready.', reload: 'Reload', ro_short: 'View only (with your group manager)',
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

const NAV = [
  ['', 'n_dash', 'gauge'], ['request', 'n_request', 'plus', 'full'], ['requests', 'n_requests', 'clock', 'full'],
  ['invoices', 'n_invoices', 'money', 'full'], ['statement', 'n_statement', 'doc', 'full'], ['notifications', 'n_notifications', 'bell'],
  ['settings', 'n_settings', 'sliders'],
]
const to = (k) => `${PORTAL_PATH}${k ? '/' + k : ''}`

/** A tab left open across a deploy keeps its old code: compare the page's bundle with the current index.html. */
function useNewBuild() {
  const [fresh, setFresh] = useState(false)
  useEffect(() => {
    const mine = [...document.scripts].map((x) => x.src).find((x) => /\/assets\/index-[^/]+\.js/.test(x))
    if (!mine) return undefined
    const check = () => fetch(window.location.pathname, { cache: 'no-store', headers: { Accept: 'text/html' } })
      .then((r) => r.text()).then((h) => { const m = h.match(/\/assets\/index-[^"']+\.js/); if (m && !mine.endsWith(m[0])) setFresh(true) }).catch(() => {})
    const vis = () => { if (document.visibilityState === 'visible') check() }
    const t = setInterval(vis, 5 * 60 * 1000)
    document.addEventListener('visibilitychange', vis)
    return () => { clearInterval(t); document.removeEventListener('visibilitychange', vis) }
  }, [])
  return fresh
}

export default function AgencyPortal() {
  const { lang, setLang } = useI18n()
  const s = T[lang] || T.fa
  const [token, setToken] = useState(store.get())
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const toast = useToast()
  const fresh = useNewBuild()

  const load = () => http.get('/me/').then((r) => { setData(r.data); setErr('') }).catch((e) => {
    if (e?.response?.status === 401) { store.set(null); setToken(null); toast.error(s.expired); return }
    const m = e?.response?.data?.code === 'portal_closed' ? s.closed : !e?.response ? s.net : errText(e, s.error)
    setErr(m); toast.error(m)
  })
  useEffect(() => { if (token) load() }, [token])
  useEffect(() => { document.title = s.title }, [lang])

  const logout = async () => { try { await http.post('/logout/') } catch { /* already gone */ } store.set(null); setToken(null); setData(null); toast.success(s.bye) }
  const banner = fresh && <div className="ap-fresh" role="status" data-testid="ap-new-build">{s.new_build}<button type="button" className="ap-link" onClick={() => window.location.reload()}>{s.reload}</button></div>

  if (!token) {
    return (
      <div className="ap" dir={lang === 'fa' ? 'rtl' : 'ltr'}>
        <style>{ACCENT_CSS + CSS}</style>
        <header className="ap-top">
          <b>{s.title}</b>
          <div className="ap-top-r">
            <button type="button" className="ap-lang" onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}><Ic n="globe" />{lang === 'fa' ? 'EN' : 'فا'}</button>
          </div>
        </header>
        {banner}
        <main className="ap-main"><LoginForm s={s} onDone={(t) => { store.set(t); setToken(t) }} /></main>
      </div>
    )
  }
  return <Shell s={s} lang={lang} setLang={setLang} data={data} err={err} load={load} logout={logout} banner={banner} />
}

function NavList({ s, items, sec, onPick }) {
  return (
    <nav className="ap-nav" aria-label={s.menu}>
      {items.map(([k, key, icon]) => (
        <Link key={k || 'dash'} to={to(k)} className={'ap-nav-i' + (sec === k ? ' on' : '')} aria-current={sec === k ? 'page' : undefined}
          onClick={onPick} data-testid={`ap-nav-${k || 'dash'}`}><Ic n={icon} size={17} /><span>{s[key]}</span></Link>
      ))}
    </nav>
  )
}

function LogoutBtn({ s, onYes, testId }) {
  const confirm = useConfirm()
  const ask = async () => {
    if (await confirm({ tone: 'danger', icon: 'warning', title: s.logout_q, message: s.logout_msg, confirmLabel: s.logout })) onYes()
  }
  return <button type="button" className="ap-out" onClick={ask} data-testid={testId}><Ic n="logout" size={17} />{s.logout}</button>
}

function Shell({ s, lang, setLang, data, err, load, logout, banner }) {
  const { pathname } = useLocation()
  const go = useNavigate()
  const [drawer, setDrawer] = useState(false)
  const ro = data?.access?.mode === 'readonly' || data?.mode === 'not_found'
  const items = NAV.filter(([, , , need]) => !need || (data && !ro))
  const rest = pathname.slice(PORTAL_PATH.length).replace(/^\/+|\/+$/g, '')
  const sec = NAV.some(([k]) => k === rest) ? rest : ''
  useEffect(() => { if (data && ro && NAV.find(([k]) => k === sec)?.[3]) go(to(''), { replace: true }) }, [data, sec])
  useEffect(() => { setDrawer(false) }, [pathname])
  useEffect(() => {
    if (!drawer) return undefined
    const k = (e) => { if (e.key === 'Escape') setDrawer(false) }
    document.addEventListener('keydown', k)
    return () => document.removeEventListener('keydown', k)
  }, [drawer])
  const title = s[NAV.find(([k]) => k === sec)?.[1] || 'n_dash']
  const who = data?.username
  const side = (onPick) => (
    <>
      <div className="ap-side-who"><span className="ap-av">{(who || '?').charAt(0).toUpperCase()}</span>
        <span><b dir="ltr">{who || '…'}</b><small>{ro ? s.ro_short : s.title}</small></span></div>
      <NavList s={s} items={items} sec={sec} onPick={onPick} />
    </>
  )
  return (
    <div className="ap ap-shell" dir={lang === 'fa' ? 'rtl' : 'ltr'}>
      <style>{ACCENT_CSS + CSS + ST_CSS + SHELL_CSS}</style>
      <header className="ap-top">
        <div className="ap-top-s">
          <button type="button" className="ap-ico ap-burger" onClick={() => setDrawer(true)} aria-label={s.menu} aria-expanded={drawer} data-testid="ap-burger">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /></svg></button>
          <b className="ap-brand">{s.title}</b><span className="ap-crumb">{title}</span>
        </div>
        <div className="ap-top-r">
          {data && <AgencyBell http={http} url="/notices/" allTo={to('notifications')} lang={lang} sound={soundPrefs} evt="ct:ag-notices" tid="ap" />}
          <button type="button" className="ap-lang" onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}><Ic n="globe" />{lang === 'fa' ? 'EN' : 'فا'}</button>
        </div>
      </header>
      {banner}
      <div className="ap-body">
        <aside className="ap-side" data-testid="ap-side">
          {side()}
          <div className="ap-side-end"><LogoutBtn s={s} onYes={logout} testId="ap-side-logout" /></div>
        </aside>
        <main className="ap-main ap-main--wide">
          <h1 className="ap-h1">{title}</h1>
          {err && <div className="ap-alert" role="alert">{err}</div>}
          {!data && !err && <div className="ap-spin" aria-busy="true" />}
          {data && <Section sec={sec} s={s} lang={lang} setLang={setLang} data={data} load={load} ro={ro} />}
        </main>
      </div>
      {drawer && createPortal(
        <div className="ap-drw" dir={lang === 'fa' ? 'rtl' : 'ltr'}>
          <style>{ACCENT_CSS + SHELL_CSS}</style>
          <div className="ap-drw-scrim" onClick={() => setDrawer(false)} />
          <div className="ap-drw-p" role="dialog" aria-modal="true" aria-label={s.menu} data-testid="ap-drawer">
            <div className="ap-drw-h"><b>{s.title}</b><button type="button" className="ap-ico" onClick={() => setDrawer(false)} aria-label={s.close}>✕</button></div>
            {side(() => setDrawer(false))}
            <div className="ap-side-end"><LogoutBtn s={s} onYes={logout} testId="ap-drawer-logout" /></div>
          </div>
        </div>, document.body)}
    </div>
  )
}

function Section({ sec, s, lang, setLang, data, load, ro }) {
  if (sec === 'notifications') return <AgencyNotificationsPage http={http} url="/notices/" lang={lang} evt="ct:ag-notices" tid="ap" />
  if (sec === 'settings') return <Settings s={s} lang={lang} setLang={setLang} />
  if (data.mode === 'not_found') return <div className="ap-card ap-empty">{s.not_found}</div>
  if (ro || sec === '') return <Dashboard s={s} lang={lang} data={data} ro={ro} />
  if (sec === 'request') return <PortalRequest http={http} lang={lang} me={data.username} />
  if (sec === 'requests') return <PortalRequests http={http} lang={lang} />
  if (sec === 'invoices') return <PortalInvoices http={http} lang={lang} onChange={load} />
  if (sec === 'statement') return (
    <>{data.accounts.map((a) => <StatementCard key={a.username} a={a} s={s} lang={lang} balance={data.balances[a.username]} />)}</>
  )
  return null
}

function Dashboard({ s, lang, data, ro }) {
  return (
    <>
      {data.mode === 'group' && <h2 className="ap-group">{s.group}</h2>}
      {ro && <div className="ap-card ap-ro" role="note" data-testid="ap-readonly">{s.readonly.replace('{m}', data.access?.manager || '')}</div>}
      {data.accounts.map((a) => <Account key={a.username} a={a} s={s} lang={lang} balance={data.balances[a.username]} readonly={ro} />)}
    </>
  )
}

function LoginForm({ s, onDone }) {
  const [u, setU] = useState('')
  const [p, setP] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [blocked, setBlocked] = useState(null)       // v1.35: owner of a managed group → /panel/
  const toast = useToast()
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr('')
    try {
      const r = await http.post('/login/', { username: u.trim(), password: p })
      toast.success(s.welcome)
      onDone(r.data.token)
    } catch (e2) {
      const st = e2?.response?.status
      const code = e2?.response?.data?.code
      if (code === 'use_panel' || code === 'disabled') {
        const d = e2.response.data
        setBlocked({ msg: code === 'use_panel' ? s.use_panel : (d.detail_fa || d.detail), url: code === 'use_panel' ? d.panel_url : null })
        return
      }
      const m = code === 'portal_closed' ? s.closed : st === 400 ? s.wrong : st === 429 ? s.locked
        : !e2?.response ? s.net : errText(e2, s.error)
      setErr(m); toast.error(m)
    } finally { setBusy(false) }
  }
  return (
    <form className="ap-card ap-login" onSubmit={submit}>
      <h1>{s.title}</h1>
      <p>{s.sub}</p>
      {err && <div className="ap-alert" role="alert">{err}</div>}
      {blocked && (
        <div className="ap-warn ap-blocked" role="alert" data-testid="ap-use-panel">
          <b>{blocked.msg}</b>
          {blocked.url && <a className="ap-btn ap-panel-btn" href={blocked.url}>{s.open_panel}</a>}
        </div>
      )}
      <label htmlFor="ap-u">{s.username}</label>
      <input id="ap-u" className="ap-input" dir="ltr" autoComplete="username" required value={u} onChange={(e) => setU(e.target.value)} />
      <label htmlFor="ap-p">{s.password}</label>
      <input id="ap-p" className="ap-input" dir="ltr" type="password" autoComplete="current-password" required value={p} onChange={(e) => setP(e.target.value)} />
      <button className="ap-btn" disabled={busy}>{busy ? <span className="ap-btn-spin" aria-hidden="true" /> : <Ic n="login" size={17} />}{s.login}</button>
      <Link className="ap-mgr-link" to={`${PORTAL_PATH}/manager`}><Ic n="users" size={14} />{s.mgr_link}</Link>
    </form>
  )
}

function Account({ a, s, lang, balance, readonly }) {
  const st = ST[lang] || ST.fa
  const p = a.portal
  const w = Math.min(Number(a.usage_percent) || 0, 100)      // bar width only
  const tone = a.usage_percent >= 100 ? 'danger' : a.usage_percent >= 80 ? 'warning' : 'primary'
  const tg = (p.support_telegram || '').replace(/^@/, '')
  const by = a.bytes || {}
  // [label, value, accent, icon, bytes, signed, tooltip]
  const nums = [[s.limit, <Lim b={by.limit} tb={a.admin_limit_fmt} s={s} />, 'cyan', 'limit', null, false, st.t_limit],
    [s.total_sold, a.total_sold_fmt, 'blue', 'sold', by.total_sold, false, st.t_sold], [s.used, a.used_fmt, 'purple', 'used', by.used, false, st.t_used],
    [s.remaining, fmt(a.remaining_fmt, s), 'green', 'remaining', by.remaining, false, st.t_remaining],
    [s.sold_limit, a.sold_limit_fmt, 'cyan', 'limit', by.sold_limit, true, st.t_sold_limit], [s.hidden, a.hidden_fmt, 'orange', 'hidden', by.hidden, false, st.t_hidden],
    [s.deleted, a.deleted_used_fmt, 'gray', 'trash', by.deleted, false, st.t_deleted]]
  return (
    <section className="ap-card" data-testid="ap-account">
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
      <dl className="ap-nums ap-tiles">
        {nums.map(([k, v, ac, ic, b, signed, tip]) => (
          <div key={k} data-ac={ac}><dt><Ic n={ic} size={13} />{k}{tip && <InfoTip text={tip} label={`${st.info}: ${k}`} />}</dt>
            <dd>{typeof v === 'string' ? <><B>{v}</B><GB b={b} signed={signed} /></> : v}</dd></div>))}
      </dl>
      {!readonly && balance != null && <div className="ap-bal">
        <span>{s.balance}</span>
        <bdi dir="ltr" className="ap-num" data-sign={Number(balance) > 0 ? 'owes' : Number(balance) < 0 ? 'credit' : 'zero'}>{money(balance, lang)}</bdi>
        <Link className="ap-link" to={to('invoices')} data-testid="ap-owe-go"><Ic n="money" />{s.owe_go}</Link>
      </div>}
      {a.last_synced_at && <p className="ap-foot">{s.last_sync}: {jalali(a.last_synced_at, true, lang)}</p>}
    </section>
  )
}

function StatementCard({ a, s, lang, balance }) {
  return (
    <section className="ap-card" data-testid="ap-statement">
      <div className="ap-acc-h"><h2><bdi>{a.username}</bdi></h2></div>
      <div className="ap-bal ap-bal--top"><span>{s.balance}</span>
        <bdi dir="ltr" className="ap-num" data-sign={Number(balance) > 0 ? 'owes' : Number(balance) < 0 ? 'credit' : 'zero'}>{money(balance, lang)}</bdi></div>
      <Statement username={a.username} s={s} lang={lang} />
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

function Seg({ value, opts, onPick, label }) {
  return (
    <div className="ap-seg" role="radiogroup" aria-label={label}>
      {opts.map(([v, t]) => <button key={v} type="button" role="radio" aria-checked={value === v} className={value === v ? 'on' : ''} onClick={() => value !== v && onPick(v)}>{t}</button>)}
    </div>
  )
}

function Settings({ s, lang, setLang }) {
  const { mode, toggle, locked } = useTheme()
  const toast = useToast()
  const [snd, setSnd] = useState(soundPrefs)
  const [push, setPush] = useState(null)
  const [sub, setSub] = useState(false)
  const [busy, setBusy] = useState(false)
  const saveSnd = (v) => { setSnd(v); try { localStorage.setItem(SOUND_KEY, JSON.stringify(v)) } catch { /* private mode */ } }
  useEffect(() => {
    http.get('/push/').then((r) => setPush(r.data)).catch(() => setPush({ enabled: false }))
    currentSubscription('/').then((x) => setSub(!!x)).catch(() => {})
  }, [])
  const msg = (r) => (lang === 'fa' ? r.data.message_fa : r.data.message)
  const turn = async (on) => {
    setBusy(true)
    try {
      if (on) {
        const json = await subscribePush('/', push.public_key)
        toast.success(msg(await http.post('/push/subscribe/', { subscription: json }))); setSub(true)
      } else {
        const endpoint = await unsubscribePush('/')
        if (endpoint) toast.success(msg(await http.post('/push/unsubscribe/', { endpoint })))
        setSub(false)
      }
    } catch (e) {
      toast.error(e?.message === 'denied' ? s.push_denied : e?.message === 'unsupported' ? s.push_unsupported : errText(e, s.error))
    } finally { setBusy(false) }
  }
  const pushNote = !push ? null : !push.enabled ? s.push_off : !pushSupported() ? (needsHomeScreen() ? s.push_ios : s.push_unsupported) : null
  return (
    <div className="ap-set">
      <section className="ap-card ap-set-c">
        <h2>{s.set_prefs}</h2>
        <div className="ap-set-r"><span>{s.set_lang}</span><Seg label={s.set_lang} value={lang} onPick={setLang} opts={[['fa', 'فارسی'], ['en', 'English']]} /></div>
        {!locked && <div className="ap-set-r"><span>{s.set_theme}</span><Seg label={s.set_theme} value={mode} onPick={() => toggle()} opts={[['light', s.light], ['dark', s.dark]]} /></div>}
      </section>
      <section className="ap-card ap-set-c" data-testid="ap-notify">
        <h2>{s.set_notify}</h2>
        <div className="ap-set-r ap-set-r--top">
          <span><b>{s.set_sound}</b><small>{s.set_sound_d}</small></span>
          <button type="button" role="switch" aria-checked={snd.on} className="ap-switch" onClick={() => { unlockSound(); saveSnd({ ...snd, on: !snd.on }) }} aria-label={s.set_sound}><i /></button>
        </div>
        {snd.on && (
          <div className="ap-set-r">
            <label className="ap-vol"><span>{s.set_volume} <B>{snd.volume}%</B></span>
              <input type="range" min="10" max="100" step="10" value={snd.volume} onChange={(e) => saveSnd({ ...snd, volume: Number(e.target.value) })} /></label>
            <button type="button" className="ap-link" onClick={() => { unlockSound(); playChime(snd.volume, 'default') }}>{s.set_test}</button>
          </div>
        )}
        <div className="ap-set-r ap-set-r--top">
          <span><b>{s.set_push}</b><small>{pushNote || s.set_push_d}</small></span>
          {push?.enabled && pushSupported() && (
            <button type="button" className="ap-link" disabled={busy} onClick={() => turn(!sub)} data-testid="ap-push">{sub ? s.push_off_btn : s.push_on}</button>)}
        </div>
        {sub && push?.enabled && (
          <div className="ap-set-r"><span /><button type="button" className="ap-link" onClick={async () => { try { toast.success(msg(await http.post('/push/test/', {}))) } catch (e) { toast.error(errText(e, s.error)) } }}>{s.push_test}</button></div>
        )}
      </section>
    </div>
  )
}

const SHELL_CSS = `
.ap-shell { display: flex; flex-direction: column; }
.ap-top-s { display: flex; align-items: center; gap: 10px; min-width: 0; }
.ap-brand { white-space: nowrap; }
.ap-crumb { display: none; }
.ap-ico { width: 40px; height: 40px; display: inline-grid; place-items: center; border-radius: 10px; border: 0; color: var(--c-text);
  background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); cursor: pointer; flex-shrink: 0; }
.ap-burger { display: none; }
.ap-top-r { align-items: center; }
.ap-body { display: flex; align-items: flex-start; flex: 1; width: 100%; max-width: 1180px; margin: 0 auto; }
.ap-side { position: sticky; top: 61px; width: 240px; flex-shrink: 0; height: calc(100vh - 61px); display: flex; flex-direction: column; gap: 10px;
  padding: 16px 12px; border-inline-end: 1px solid var(--c-border); overflow-y: auto; }
.ap-side-who { display: flex; align-items: center; gap: 10px; padding: 4px 6px 10px; border-bottom: 1px solid var(--c-border); min-width: 0; }
.ap-side-who > span:last-child { display: flex; flex-direction: column; min-width: 0; }
.ap-side-who b { font-size: 13.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: start; }
.ap-side-who small { font-size: 11.5px; color: var(--c-muted-fg); }
.ap-av { width: 34px; height: 34px; border-radius: 999px; display: grid; place-items: center; flex-shrink: 0; font-weight: 800; color: #fff; background: var(--c-primary); }
.ap-nav { display: flex; flex-direction: column; gap: 2px; }
.ap-nav-i { display: flex; align-items: center; gap: 10px; min-height: 44px; padding: 0 12px; border-radius: 12px; color: var(--c-text); text-decoration: none; font-size: 14px; font-weight: 600; }
.ap-nav-i:hover { background: color-mix(in srgb, var(--c-primary) 8%, transparent); }
.ap-nav-i.on { color: #fff; background: var(--c-primary); font-weight: 800; }
.ap-nav-i .agi { flex-shrink: 0; }
.ap-side-end { margin-top: auto; padding-top: 12px; border-top: 1px solid var(--c-border); }
.ap-out { display: flex; align-items: center; justify-content: center; gap: 8px; width: 100%; min-height: 44px; border-radius: 12px; cursor: pointer;
  border: 1px solid color-mix(in srgb, var(--c-danger) 40%, transparent); background: color-mix(in srgb, var(--c-danger) 6%, transparent);
  color: var(--c-danger-fg, var(--c-danger)); font: inherit; font-size: 14px; font-weight: 800; }
.ap-out:hover { background: color-mix(in srgb, var(--c-danger) 13%, transparent); }
.ap-main--wide { flex: 1; min-width: 0; max-width: 820px; }
.ap-h1 { font-size: 19px; font-weight: 800; }
.ap-fresh { display: flex; align-items: center; justify-content: center; flex-wrap: wrap; gap: 8px 12px; padding: 8px 16px; font-size: 13px; font-weight: 700;
  color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 9%, var(--c-bg)); border-bottom: 1px solid var(--c-border); }
.ap-fresh .ap-link { margin: 0; }
/* dashboard tiles wrap and GROW: a short last row fills the width (no empty cell) */
.ap-tiles { display: flex !important; flex-wrap: wrap; }
.ap-tiles > div { flex: 1 1 160px; }
.ap-tiles dt { flex-wrap: wrap; }
.ap-bal .ap-link { text-decoration: none; }
.ap-bal--top { margin-top: 0; padding-top: 0; border-top: 0; }
.ap-set { display: flex; flex-direction: column; gap: 14px; }
.ap-set-c h2 { font-size: 15px; font-weight: 800; margin-bottom: 8px; }
.ap-set-r { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 0; border-top: 1px solid var(--c-border); font-size: 13.5px; font-weight: 600; }
.ap-set-c h2 + .ap-set-r { border-top: 0; }
.ap-set-r--top { align-items: flex-start; }
.ap-set-r > span:first-child { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.ap-set-r small { font-size: 12px; font-weight: 500; color: var(--c-muted-fg); line-height: 1.7; }
.ap-set-r .ap-link { margin: 0; flex-shrink: 0; }
.ap-seg { display: inline-flex; padding: 3px; border-radius: 12px; border: 1px solid var(--c-border); gap: 3px; }
.ap-seg button { min-height: 38px; padding: 0 14px; border-radius: 9px; border: 0; background: transparent; color: var(--c-text); font: inherit; font-size: 13px; font-weight: 700; cursor: pointer; }
.ap-seg button.on { background: var(--c-primary); color: #fff; }
/* 44px tall hit area; the 46×28 track is drawn inside it */
.ap-switch { position: relative; width: 52px; height: 44px; flex-shrink: 0; border: 0; cursor: pointer; background: transparent; padding: 0; }
.ap-switch::before { content: ''; position: absolute; top: 8px; inset-inline-start: 3px; width: 46px; height: 28px; border-radius: 999px; background: #3f4652; transition: background-color .15s; }
.ap-switch[aria-checked="true"]::before { background: #11AB53; }
.ap-switch i { position: absolute; top: 11px; inset-inline-start: 6px; width: 22px; height: 22px; border-radius: 999px; background: #fff; transition: inset-inline-start .15s; }
.ap-switch[aria-checked="true"] i { inset-inline-start: 24px; }
.ap-switch:focus-visible { outline: 2px solid var(--c-primary); outline-offset: 2px; border-radius: 12px; }
.ap-vol { display: flex; flex-direction: column; gap: 6px; flex: 1; }
.ap-vol input { width: 100%; max-width: 280px; }
.ap-drw { position: fixed; inset: 0; z-index: 80; }
.ap-drw-scrim { position: absolute; inset: 0; background: rgba(0,0,0,.45); }
.ap-drw-p { position: absolute; top: 0; bottom: 0; inset-inline-start: 0; width: min(300px, 86vw); display: flex; flex-direction: column; gap: 10px; padding: 12px 12px calc(12px + env(safe-area-inset-bottom, 0px));
  background: var(--c-bg); color: var(--c-text); border-inline-end: 1px solid var(--c-border); box-shadow: 0 0 40px rgba(0,0,0,.25); overflow-y: auto; font-family: Vazirmatn, Inter, sans-serif; }
.ap-drw[dir="ltr"] .ap-drw-p { font-family: Inter, Vazirmatn, sans-serif; }
.ap-drw-h { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 15px; }
@media (max-width: 767px) {
  .ap-side { display: none; }
  .ap-burger { display: inline-grid; }
  .ap-brand { font-size: 13px; color: var(--c-muted-fg); display: none; }
  .ap-crumb { display: inline; font-weight: 800; font-size: 15px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ap-top { padding: 8px 12px; }
  .ap-h1 { display: none; }
  .ap-lang, .ap-ico { min-height: 44px; height: 44px; }
  .ap-ico { width: 44px; }
  .ap-top .gmb-btn { width: 44px; height: 44px; }
  .ab-segb { min-height: 44px; }
  .ap-seg button { min-height: 44px; }
  .ap-set-r .ap-link { min-height: 44px; }
}
`

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
/* v1.38.1 compact sign-in card: ≤400px, centred, normal control heights (44px on phones) */
.ap-login { display: flex; flex-direction: column; gap: 6px; width: 100%; max-width: 400px; margin: 6vh auto 0; padding: 22px 22px 16px; border-radius: 18px;
  box-shadow: 0 10px 40px rgb(0 0 0 / .08); }
.ap-login h1 { font-size: 18px; font-weight: 800; line-height: 1.4; }
.ap-login p { font-size: 12.5px; line-height: 1.7; color: var(--c-muted-fg); margin-bottom: 8px; }
.ap-login label { font-size: 12.5px; font-weight: 700; margin-top: 6px; }
.ap-login .ap-input { height: 42px; border-radius: 10px; font-size: 15px; }
.ap-login > .ap-btn { margin-top: 14px; min-height: 42px; border-radius: 10px; font-size: 14.5px; }
.ap-login .ap-mgr-link { margin-top: 4px; font-size: 12.5px; }
@media (max-width: 767px) {
  .ap-login { margin-top: 3vh; padding: 18px 16px 12px; box-shadow: none; }
  .ap-login .ap-input { height: 44px; font-size: 16px; }
  .ap-login > .ap-btn { min-height: 44px; }
  .ap-login .ap-mgr-link { min-height: 44px; }
}
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
.ap-mgr-link { display: inline-flex; align-items: center; justify-content: center; gap: 6px; margin-top: 10px; font-size: 13px; font-weight: 700; color: var(--c-primary); min-height: 40px; }
.ap-ro { font-size: 13.5px; line-height: 1.9; font-weight: 600; border-color: color-mix(in srgb, var(--c-primary) 35%, var(--c-border)); }
.ap-blocked { display: flex; flex-direction: column; gap: 10px; }
.ap-panel-btn { text-decoration: none; margin-top: 0; }
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

export { CSS as PORTAL_CSS }
