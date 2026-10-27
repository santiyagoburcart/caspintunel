import { useEffect, useMemo, useState } from 'react'
import axios from 'axios'
import { Link } from 'react-router-dom'
import { clientId } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali, toman } from '../lib/format'
import { PORTAL_PATH } from '../lib/paths'
import { ACCENT_CSS, Ic } from '../components/AgencyIcons'
import { useToast } from '../components/Toast'
import { PORTAL_CSS } from './AgencyPortal'

// Group-manager portal (<portal>/manager). Own token ("Manager <token>") and HTTP
// client, like the reseller portal — never the customer or staff session. Every
// rule (own groups only, increase only, allowed inbounds, cap, approvals) is
// enforced by the server (apps/agency/managers.py); this page only lays it out.

const KEY = 'agency_mgr_token'
const store = {
  get: () => { try { return localStorage.getItem(KEY) } catch { return null } },
  set: (t) => { try { t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY) } catch { /* private mode */ } },
}
const http = axios.create({ baseURL: '/api/v1/agency/manager' })
http.interceptors.request.use((cfg) => {
  const t = store.get()
  if (t) cfg.headers.Authorization = `Manager ${t}`
  const cid = clientId()
  if (cid) cfg.headers['X-Client-Id'] = cid
  return cfg
})

const T = {
  fa: {
    title: 'پرتال مدیر گروه', sub: 'با نام کاربری و رمزی که پشتیبانی برای شما ساخته وارد شوید', username: 'نام کاربری', password: 'رمز عبور',
    login: 'ورود', logout: 'خروج', wrong: 'نام کاربری یا رمز عبور اشتباه است.', locked: 'به‌دلیل تلاش‌های ناموفق، ورود موقتاً بسته شده است.', error: 'خطا در ارتباط با سرور',
    net: 'ارتباط با سرور برقرار نشد — اینترنت را بررسی کنید.', expired: 'نشست شما تمام شده — دوباره وارد شوید.', welcome: 'خوش آمدید', bye: 'خارج شدید', reseller: 'ورود نمایندگان',
    t_admins: 'ادمین‌ها', t_acc: 'حسابداری', t_act: 'فعالیت', no_groups: 'هنوز گروهی به شما سپرده نشده است.',
    limit: 'سقف', used: 'مصرف', remaining: 'باقی‌مانده', users: 'کاربران', active_u: 'فعال', unl: 'نامحدود', inbounds: 'اینباندها', balance: 'بدهی', pend: 'در انتظار تأیید',
    st_active: 'فعال', st_panel_disabled: 'غیرفعال', st_pamp_limited: 'محدود‌شده', owner: 'مالک گروه', sudo: 'فقط پشتیبانی',
    add: 'افزودن حجم', pw: 'تغییر رمز', inb: 'تغییر اینباند', new_admin: 'ادمین جدید', group_debt: 'بدهی کل گروه',
    cap: 'حجم تأییدنشدهٔ شما', cap_of: 'از سقف', cap_reached: 'به سقف حجم تأییدنشده رسیده‌اید — تا تأیید پشتیبانی، حجم تازه نمی‌توانید بدهید.', no_cap: 'بدون سقف',
    gb_in: 'حجم (گیگابایت)', add_note: 'فقط افزایش. بلافاصله روی پنل اعمال می‌شود و تا تأیید پشتیبانی «در انتظار» می‌ماند.', confirm_add: 'تأیید و اعمال', new_limit: 'سقف جدید',
    cur: 'فعلی', pw_new: 'رمز جدید (حداقل ۸ نویسه)', gen: 'رمز تصادفی', save: 'ذخیره', cancel: 'انصراف', pick_inb: 'اینباندها را انتخاب کنید',
    n_user: 'نام کاربری ادمین', n_gb: 'حجم اولیه (گیگابایت)', create: 'ساخت ادمین', created: 'ادمین ساخته شد', cred: 'اطلاعات ورود ادمین (فقط همین یک بار)', copy: 'کپی', copied: 'کپی شد', close: 'بستن',
    added: 'حجم اضافه شد — در انتظار تأیید', pw_done: 'رمز ادمین تغییر کرد', inb_done: 'اینباند تغییر کرد', unl_no: 'این ادمین نامحدود است؛ فقط پشتیبانی آن را تغییر می‌دهد.',
    from: 'از تاریخ', to: 'تا تاریخ', apply: 'اعمال', clear: 'همهٔ زمان‌ها', csv: 'CSV', xlsx: 'Excel', print: 'چاپ', date_ph: '۱۴۰۵/۰۷/۰۱',
    date: 'تاریخ', type: 'نوع', amount: 'مبلغ', charges: 'شارژ', payments: 'پرداخت', admin: 'ادمین', statement: 'صورت‌حساب', group_st: 'صورت‌حساب گروه', hide: 'بستن', pending_sep: 'در انتظار تأیید (جدا از مانده)',
    opening: 'مانده از قبل', closing: 'مانده پایان بازه', none: 'گردشی نیست.', running: 'مانده', voided: 'باطل‌شده', no_price: 'بی‌قیمت', total: 'جمع',
    k_quota_charge: 'شارژ حجم', k_manual_charge: 'بدهکاری', k_adjustment: 'اصلاحیه', k_payment: 'پرداخت', act_none: 'فعالیتی نیست.',
    acts: { admin_created: 'ساخت ادمین', volume_added: 'افزودن حجم', password_changed: 'تغییر رمز ادمین', inbounds_changed: 'تغییر اینباند', login: 'ورود', approved: 'تأیید پشتیبانی', rejected: 'رد پشتیبانی' },
  },
  en: {
    title: 'Group manager portal', sub: 'Sign in with the username and password support made for you', username: 'Username', password: 'Password',
    login: 'Sign in', logout: 'Sign out', wrong: 'Wrong username or password.', locked: 'Too many failed attempts — sign-in is paused for a few minutes.', error: 'Could not reach the server',
    net: 'Could not reach the server — check your connection.', expired: 'Your session ended — please sign in again.', welcome: 'Welcome', bye: 'Signed out', reseller: 'Reseller sign-in',
    t_admins: 'Admins', t_acc: 'Accounting', t_act: 'Activity', no_groups: 'No group is assigned to you yet.',
    limit: 'Limit', used: 'Used', remaining: 'Remaining', users: 'Users', active_u: 'active', unl: 'Unlimited', inbounds: 'Inbounds', balance: 'Owes', pend: 'Pending approval',
    st_active: 'Active', st_panel_disabled: 'Disabled', st_pamp_limited: 'Limited', owner: 'Group owner', sudo: 'support only',
    add: 'Add volume', pw: 'Password', inb: 'Inbounds', new_admin: 'New admin', group_debt: 'Group total debt',
    cap: 'Your unapproved volume', cap_of: 'of', cap_reached: 'You reached your unapproved-volume cap — new volume is blocked until support approves.', no_cap: 'no cap',
    gb_in: 'Volume (GB)', add_note: 'Increase only. Applied on the panel at once; pending until support approves.', confirm_add: 'Confirm and apply', new_limit: 'New limit',
    cur: 'Current', pw_new: 'New password (8+ characters)', gen: 'Random', save: 'Save', cancel: 'Cancel', pick_inb: 'Pick the inbounds',
    n_user: 'Admin username', n_gb: 'Initial volume (GB)', create: 'Create admin', created: 'Admin created', cred: 'Admin sign-in (shown only once)', copy: 'Copy', copied: 'Copied', close: 'Close',
    added: 'Volume added — pending approval', pw_done: 'Admin password changed', inb_done: 'Inbounds changed', unl_no: 'This admin is unlimited; only support can change it.',
    from: 'From', to: 'To', apply: 'Apply', clear: 'All time', csv: 'CSV', xlsx: 'Excel', print: 'Print', date_ph: '1405/07/01',
    date: 'Date', type: 'Type', amount: 'Amount', charges: 'Charges', payments: 'Payments', admin: 'Admin', statement: 'Statement', group_st: 'Group statement', hide: 'Hide', pending_sep: 'Pending approval (not in the balance)',
    opening: 'Opening balance', closing: 'Closing balance', none: 'No entries.', running: 'Balance', voided: 'voided', no_price: 'no price', total: 'Total',
    k_quota_charge: 'Quota charge', k_manual_charge: 'Charge', k_adjustment: 'Adjustment', k_payment: 'Payment', act_none: 'No activity yet.',
    acts: { admin_created: 'Admin created', volume_added: 'Volume added', password_changed: 'Admin password changed', inbounds_changed: 'Inbounds changed', login: 'Signed in', approved: 'Approved by support', rejected: 'Rejected by support' },
  },
}
const GIB = 1024 ** 3
const N = ({ children }) => <bdi dir="ltr" className="ap-num">{children}</bdi>
const gbText = (v) => `${Number(v || 0).toLocaleString('en-US', { maximumFractionDigits: 2 })} GB`
const bText = (b) => gbText(Number(b || 0) / GIB)
const money = (v, lang) => (Number(v) < 0 ? '−' : '') + toman(Math.abs(Number(v || 0)), lang)
const errText = (e, s) => (!e?.response ? s.net : e.response.data?.detail || s.error)
const faDigits = (v) => String(v).replace(/[۰-۹]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d)).replace(/[٠-٩]/g, (d) => '٠١٢٣٤٥٦٧٨٩'.indexOf(d))
const roleLabel = (r, s) => (r ? (r.all_inbounds ? '*' : (r.inbounds || []).join(' · ') || r.name) : '—')

function genPw() {
  const abc = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'
  const a = new Uint32Array(14); crypto.getRandomValues(a)
  return Array.from(a, (x) => abc[x % abc.length]).join('') + '7a'
}

async function download(url, params, name) {
  const r = await http.get(url, { params, responseType: 'blob' })
  const fn = (r.headers['content-disposition'] || '').match(/filename="([^"]+)"/)?.[1] || name
  const a = document.createElement('a')
  a.href = URL.createObjectURL(r.data); a.download = fn
  document.body.appendChild(a); a.click(); a.remove()
  setTimeout(() => URL.revokeObjectURL(a.href), 2000)
}

export default function AgencyManager() {
  const { lang, setLang } = useI18n()
  const s = T[lang] || T.fa
  const [token, setToken] = useState(store.get())
  const [me, setMe] = useState(null)
  const [err, setErr] = useState('')
  const [tab, setTab] = useState('admins')
  const toast = useToast()

  const load = () => http.get('/me/').then((r) => { setMe(r.data); setErr('') }).catch((e) => {
    if (e?.response?.status === 401) { store.set(null); setToken(null); setMe(null); toast.error(s.expired); return }
    const m = errText(e, s); setErr(m); toast.error(m)
  })
  useEffect(() => { if (token) load() }, [token])
  useEffect(() => { document.title = s.title }, [lang])
  const logout = async () => { try { await http.post('/logout/') } catch { /* gone */ } store.set(null); setToken(null); setMe(null); toast.success(s.bye) }

  return (
    <div className="ap" dir={lang === 'fa' ? 'rtl' : 'ltr'}>
      <style>{ACCENT_CSS + PORTAL_CSS + CSS}</style>
      <header className="ap-top am-noprint">
        <b>{s.title}{me && <small className="am-who"> · <bdi>{me.manager.display_name || me.manager.username}</bdi></small>}</b>
        <div className="ap-top-r">
          <button type="button" className="ap-lang" onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}><Ic n="globe" />{lang === 'fa' ? 'EN' : 'فا'}</button>
          {token && <button type="button" className="ap-lang" onClick={logout}><Ic n="logout" />{s.logout}</button>}
        </div>
      </header>
      <main className="ap-main am-main">
        {!token ? <LoginForm s={s} onDone={(t) => { store.set(t); setToken(t) }} /> : (
          <>
            {err && <div className="ap-alert" role="alert">{err}</div>}
            {!me && !err && <div className="ap-spin" aria-busy="true" />}
            {me && (
              <>
                <nav className="am-tabs am-noprint" role="tablist">
                  {[['admins', s.t_admins, 'users'], ['acc', s.t_acc, 'wallet'], ['act', s.t_act, 'clock']].map(([k, l, i]) => (
                    <button key={k} type="button" role="tab" aria-selected={tab === k} className={'am-tab' + (tab === k ? ' on' : '')} onClick={() => setTab(k)}><Ic n={i} size={15} />{l}</button>
                  ))}
                </nav>
                {me.groups.length === 0 && <div className="ap-card ap-empty">{s.no_groups}</div>}
                {tab === 'admins' && <Admins me={me} s={s} lang={lang} reload={load} />}
                {tab === 'acc' && <Accounting me={me} s={s} lang={lang} />}
                {tab === 'act' && <Activity s={s} lang={lang} />}
              </>
            )}
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
      toast.success(s.welcome); onDone(r.data.token)
    } catch (e2) {
      const st = e2?.response?.status
      const m = st === 400 ? s.wrong : st === 429 ? s.locked : errText(e2, s)
      setErr(m); toast.error(m)
    } finally { setBusy(false) }
  }
  return (
    <form className="ap-card ap-login" onSubmit={submit}>
      <h1>{s.title}</h1>
      <p>{s.sub}</p>
      {err && <div className="ap-alert" role="alert">{err}</div>}
      <label htmlFor="am-u">{s.username}</label>
      <input id="am-u" className="ap-input" dir="ltr" autoComplete="username" required value={u} onChange={(e) => setU(e.target.value)} />
      <label htmlFor="am-p">{s.password}</label>
      <input id="am-p" className="ap-input" dir="ltr" type="password" autoComplete="current-password" required value={p} onChange={(e) => setP(e.target.value)} />
      <button className="ap-btn" disabled={busy}>{busy ? <span className="ap-btn-spin" aria-hidden="true" /> : <Ic n="login" size={17} />}{s.login}</button>
      <Link className="ap-mgr-link" to={PORTAL_PATH}><Ic n="user" size={14} />{s.reseller}</Link>
    </form>
  )
}

// ------------------------------------------------------------------ dialogs
function Modal({ title, children, onClose }) {
  useEffect(() => {
    const k = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', k)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', k); document.body.style.overflow = prev }
  }, [])
  return (
    <div className="am-back" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="am-dlg" role="dialog" aria-modal="true" aria-label={title}>
        <div className="am-dlg-h"><b>{title}</b><button type="button" className="am-x" onClick={onClose} aria-label="×"><Ic n="x" /></button></div>
        {children}
      </div>
    </div>
  )
}

function useAction(s, done) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const toast = useToast()
  const run = async (fn, okMsg) => {
    setBusy(true); setErr('')
    try { const r = await fn(); if (okMsg) toast.success(okMsg); done(r); return r } catch (e) { const m = errText(e, s); setErr(m); toast.error(m); return null } finally { setBusy(false) }
  }
  return { busy, err, run }
}

function AddVolume({ a, s, cap, onClose, reload }) {
  const [gb, setGb] = useState('')
  const [step, setStep] = useState(1)
  const { busy, err, run } = useAction(s, () => { reload(); onClose() })
  const v = Number(faDigits(gb))
  const valid = v > 0
  const newB = Number(a.admin_limit_bytes) + v * GIB
  const over = cap.max_gb != null && Number(cap.pending_gb) + v > Number(cap.max_gb)
  return (
    <Modal title={`${s.add} — ${a.username}`} onClose={onClose}>
      {step === 1 ? (
        <form className="am-form" onSubmit={(e) => { e.preventDefault(); if (valid && !over) setStep(2) }}>
          <label>{s.gb_in}<input className="ap-input" dir="ltr" inputMode="decimal" autoFocus value={gb} onChange={(e) => setGb(e.target.value.replace(/[^\d.۰-۹]/g, ''))} /></label>
          <p className="am-hint">{s.add_note}</p>
          {over && <div className="ap-alert">{s.cap_reached}</div>}
          <div className="am-row"><button type="button" className="ap-link" onClick={onClose}>{s.cancel}</button><button className="ap-btn am-btn" disabled={!valid || over}><Ic n="plus" />{s.add}</button></div>
        </form>
      ) : (
        <div className="am-form">
          <dl className="am-cmp">
            <div><dt>{s.cur}</dt><dd><N>{bText(a.admin_limit_bytes)}</N></dd></div>
            <div><dt>+</dt><dd><N>{gbText(v)}</N></dd></div>
            <div data-strong><dt>{s.new_limit}</dt><dd><N>{bText(newB)}</N></dd></div>
          </dl>
          <p className="am-hint">{s.add_note}</p>
          {err && <div className="ap-alert">{err}</div>}
          <div className="am-row"><button type="button" className="ap-link" onClick={() => setStep(1)}>{s.cancel}</button>
            <button type="button" className="ap-btn am-btn" disabled={busy} onClick={() => run(() => http.post(`/admins/${encodeURIComponent(a.username)}/add-volume/`, { gb: v }), s.added)}>{busy ? <span className="ap-btn-spin" /> : <Ic n="check" />}{s.confirm_add}</button></div>
        </div>
      )}
    </Modal>
  )
}

function Password({ a, s, onClose }) {
  const [pw, setPw] = useState('')
  const { busy, err, run } = useAction(s, () => {})
  const [done, setDone] = useState(false)
  return (
    <Modal title={`${s.pw} — ${a.username}`} onClose={onClose}>
      {done ? <Cred s={s} username={a.username} password={pw} onClose={onClose} /> : (
        <form className="am-form" onSubmit={async (e) => { e.preventDefault(); if (await run(() => http.post(`/admins/${encodeURIComponent(a.username)}/password/`, { password: pw }), s.pw_done)) setDone(true) }}>
          <label>{s.pw_new}<span className="am-pw"><input className="ap-input" dir="ltr" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} autoFocus />
            <button type="button" className="ap-link" onClick={() => setPw(genPw())}><Ic n="reset" />{s.gen}</button></span></label>
          {err && <div className="ap-alert">{err}</div>}
          <div className="am-row"><button type="button" className="ap-link" onClick={onClose}>{s.cancel}</button><button className="ap-btn am-btn" disabled={busy || pw.length < 8}>{s.save}</button></div>
        </form>
      )}
    </Modal>
  )
}

function RolePick({ roles, value, onChange, s }) {
  return (
    <div className="am-roles" role="radiogroup" aria-label={s.pick_inb}>
      {roles.map((r) => (
        <label key={r.id} className="am-rolei" data-on={value === r.id || undefined}>
          <input type="radio" name="role" checked={value === r.id} onChange={() => onChange(r.id)} />
          <span><b>{roleLabel(r, s)}</b><small>{r.name}</small></span>
        </label>
      ))}
    </div>
  )
}

function Inbounds({ a, roles, s, onClose, reload }) {
  const [rid, setRid] = useState(a.role?.id ?? null)
  const { busy, err, run } = useAction(s, () => { reload(); onClose() })
  return (
    <Modal title={`${s.inb} — ${a.username}`} onClose={onClose}>
      <form className="am-form" onSubmit={(e) => { e.preventDefault(); run(() => http.post(`/admins/${encodeURIComponent(a.username)}/inbounds/`, { role_id: rid }), s.inb_done) }}>
        <p className="am-hint">{s.cur}: <b>{roleLabel(a.role, s)}</b></p>
        <RolePick roles={roles} value={rid} onChange={setRid} s={s} />
        {err && <div className="ap-alert">{err}</div>}
        <div className="am-row"><button type="button" className="ap-link" onClick={onClose}>{s.cancel}</button><button className="ap-btn am-btn" disabled={busy || rid == null || rid === a.role?.id}>{s.save}</button></div>
      </form>
    </Modal>
  )
}

function NewAdmin({ g, s, cap, onClose, reload }) {
  const [v, setV] = useState({ username: '', password: genPw(), role_id: g.roles[0]?.id ?? null, gb: '' })
  const [made, setMade] = useState(null)
  const { busy, err, run } = useAction(s, () => reload())
  const gbv = Number(faDigits(v.gb))
  const over = cap.max_gb != null && Number(cap.pending_gb) + gbv > Number(cap.max_gb)
  const submit = async (e) => {
    e.preventDefault()
    const r = await run(() => http.post('/admins/', { group_id: g.id, username: v.username.trim(), password: v.password, role_id: v.role_id, initial_gb: gbv }), s.created)
    if (r) setMade(r.data)
  }
  return (
    <Modal title={`${s.new_admin} — ${g.name}`} onClose={onClose}>
      {made ? <Cred s={s} username={made.username} password={made.password} onClose={onClose} /> : (
        <form className="am-form" onSubmit={submit}>
          <label>{s.n_user}<input className="ap-input" dir="ltr" autoComplete="off" required minLength={3} maxLength={32} value={v.username} onChange={(e) => setV({ ...v, username: e.target.value })} autoFocus /></label>
          <label>{s.password}<span className="am-pw"><input className="ap-input" dir="ltr" autoComplete="new-password" required minLength={8} value={v.password} onChange={(e) => setV({ ...v, password: e.target.value })} />
            <button type="button" className="ap-link" onClick={() => setV({ ...v, password: genPw() })}><Ic n="reset" />{s.gen}</button></span></label>
          <span className="am-l">{s.inbounds}</span>
          <RolePick roles={g.roles} value={v.role_id} onChange={(id) => setV({ ...v, role_id: id })} s={s} />
          <label>{s.n_gb}<input className="ap-input" dir="ltr" inputMode="decimal" required value={v.gb} onChange={(e) => setV({ ...v, gb: e.target.value.replace(/[^\d.۰-۹]/g, '') })} /></label>
          <p className="am-hint">{s.add_note}</p>
          {over && <div className="ap-alert">{s.cap_reached}</div>}
          {err && <div className="ap-alert">{err}</div>}
          <div className="am-row"><button type="button" className="ap-link" onClick={onClose}>{s.cancel}</button><button className="ap-btn am-btn" disabled={busy || !(gbv > 0) || v.role_id == null || over}>{busy ? <span className="ap-btn-spin" /> : <Ic n="plus" />}{s.create}</button></div>
        </form>
      )}
    </Modal>
  )
}

function Cred({ s, username, password, onClose }) {
  const toast = useToast()
  return (
    <div className="am-form">
      <p className="am-hint">{s.cred}</p>
      <dl className="am-cmp"><div><dt>{s.username}</dt><dd><N>{username}</N></dd></div><div><dt>{s.password}</dt><dd><N>{password}</N></dd></div></dl>
      <div className="am-row">
        <button type="button" className="ap-link" onClick={async () => { try { await navigator.clipboard.writeText(`${s.username}: ${username}\n${s.password}: ${password}`); toast.success(s.copied) } catch { /* no clipboard */ } }}><Ic n="copy" />{s.copy}</button>
        <button type="button" className="ap-btn am-btn" onClick={onClose}>{s.close}</button>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ admins tab
function Admins({ me, s, lang, reload }) {
  const [dlg, setDlg] = useState(null)
  const cap = me.cap
  const close = () => setDlg(null)
  return (
    <>
      {(cap.max_gb != null || Number(cap.pending_gb) > 0) && (
        <div className={cap.reached ? 'ap-alert' : 'ap-warn am-cap'} role="status">
          {s.cap}: <N>{gbText(cap.pending_gb)}</N> {cap.max_gb != null ? <>{s.cap_of} <N>{gbText(cap.max_gb)}</N></> : `(${s.no_cap})`}
          {cap.reached && <> — {s.cap_reached}</>}
        </div>
      )}
      {me.groups.map((g) => (
        <section key={g.id} className="am-group">
          <div className="am-gh">
            <h2><Ic n="users" size={16} /><bdi>{g.name}</bdi></h2>
            <span className="am-debt">{s.group_debt}: <N>{money(g.total_debt, lang)}</N></span>
            <button type="button" className="ap-btn am-btn am-new" disabled={!me.writes_enabled || cap.reached || !g.roles.length} onClick={() => setDlg({ k: 'new', g })}><Ic n="plus" />{s.new_admin}</button>
          </div>
          <div className="am-grid">
            {g.admins.map((a) => <AdminCard key={a.username} a={a} s={s} lang={lang} writable={me.writes_enabled} capReached={cap.reached} onAct={(k) => setDlg({ k, a, g })} />)}
          </div>
        </section>
      ))}
      {dlg?.k === 'add' && <AddVolume a={dlg.a} s={s} cap={cap} onClose={close} reload={reload} />}
      {dlg?.k === 'pw' && <Password a={dlg.a} s={s} onClose={close} />}
      {dlg?.k === 'inb' && <Inbounds a={dlg.a} roles={dlg.g.roles} s={s} onClose={close} reload={reload} />}
      {dlg?.k === 'new' && <NewAdmin g={dlg.g} s={s} cap={cap} onClose={close} reload={reload} />}
    </>
  )
}

function AdminCard({ a, s, lang, writable, capReached, onAct }) {
  const unl = !(Number(a.admin_limit_bytes) > 0)
  const pct = Math.min(Number(a.usage_percent) || 0, 100)
  const tone = a.usage_percent >= 100 ? 'danger' : a.usage_percent >= 80 ? 'warning' : 'primary'
  const locked = a.is_sudo
  return (
    <article className="ap-card am-card">
      <div className="ap-acc-h">
        <h3><bdi>{a.username}</bdi>{a.member_role === 'owner' && <small className="am-tag">{s.owner}</small>}</h3>
        <span className="ap-pill" data-st={a.status_code}>{s['st_' + a.status_code] || a.status_code}</span>
      </div>
      {!unl && <div className="ap-usage"><div className="ap-usage-l"><span>{s.used}</span><N>{a.usage_percent}%</N></div><span className="ap-bar" data-tone={tone}><i style={{ width: `${pct}%` }} /></span></div>}
      <dl className="am-nums">
        <div><dt>{s.limit}</dt><dd><N>{unl ? s.unl : bText(a.admin_limit_bytes)}</N></dd></div>
        <div><dt>{s.used}</dt><dd><N>{a.used_fmt}</N></dd></div>
        <div><dt>{s.remaining}</dt><dd><N>{unl ? s.unl : (a.remaining_fmt === 'Unlimited' ? s.unl : a.remaining_fmt)}</N></dd></div>
        <div><dt>{s.users}</dt><dd><N>{a.user_count}</N> <small>/ <N>{a.active_user_count}</N> {s.active_u}</small></dd></div>
        <div><dt>{s.balance}</dt><dd><span className="am-bal" data-sign={Number(a.balance) > 0 ? 'owes' : 'zero'}><N>{money(a.balance, lang)}</N></span></dd></div>
        <div><dt>{s.inbounds}</dt><dd className="am-inb">{roleLabel(a.role, s)}</dd></div>
      </dl>
      {Number(a.pending?.gb) > 0 && <p className="am-pend"><Ic n="clock" size={13} />{s.pend}: <N>{gbText(a.pending.gb)}</N></p>}
      {locked ? <p className="am-hint">{s.sudo}</p> : (
        <div className="am-acts">
          <button type="button" className="ap-link" disabled={!writable || unl || capReached} title={unl ? s.unl_no : undefined} onClick={() => onAct('add')}><Ic n="plus" />{s.add}</button>
          <button type="button" className="ap-link" disabled={!writable} onClick={() => onAct('pw')}><Ic n="edit" />{s.pw}</button>
          <button type="button" className="ap-link" disabled={!writable} onClick={() => onAct('inb')}><Ic n="sliders" />{s.inb}</button>
        </div>
      )}
      {unl && !locked && <p className="am-hint">{s.unl_no}</p>}
    </article>
  )
}

// ------------------------------------------------------------------ accounting tab
function RangeBar({ s, onApply }) {
  const [f, setF] = useState('')
  const [t, setT] = useState('')
  const norm = (v) => faDigits(v).replace(/-/g, '/').trim()
  return (
    <form className="am-range am-noprint" onSubmit={(e) => { e.preventDefault(); onApply({ from: norm(f), to: norm(t) }) }}>
      <label>{s.from}<input className="ap-input" dir="ltr" placeholder={s.date_ph} value={f} onChange={(e) => setF(e.target.value)} /></label>
      <label>{s.to}<input className="ap-input" dir="ltr" placeholder={s.date_ph} value={t} onChange={(e) => setT(e.target.value)} /></label>
      <button className="ap-link">{s.apply}</button>
      <button type="button" className="ap-link" onClick={() => { setF(''); setT(''); onApply({ from: '', to: '' }) }}>{s.clear}</button>
    </form>
  )
}

function Accounting({ me, s, lang }) {
  const [gid, setGid] = useState(me.groups[0]?.id)
  const [range, setRange] = useState({ from: '', to: '' })
  const [d, setD] = useState(null)
  const [open, setOpen] = useState(null)
  const toast = useToast()
  const params = useMemo(() => ({ ...(range.from ? { from: range.from } : {}), ...(range.to ? { to: range.to } : {}) }), [range])
  useEffect(() => { if (!gid) return; setD(null); http.get('/accounting/', { params: { group: gid, ...params } }).then((r) => setD(r.data.groups[0])).catch((e) => toast.error(errText(e, s))) }, [gid, params])
  const exp = (url, fmt, extra = {}) => download(url, { ...params, ...extra, export: fmt, lang }, `export.${fmt}`).catch((e) => toast.error(errText(e, s)))
  if (!gid) return null
  return (
    <>
      {me.groups.length > 1 && (
        <div className="am-seg am-noprint">{me.groups.map((g) => <button key={g.id} type="button" className={'am-tab' + (gid === g.id ? ' on' : '')} onClick={() => { setGid(g.id); setOpen(null) }}><bdi>{g.name}</bdi></button>)}</div>
      )}
      <RangeBar s={s} onApply={setRange} />
      {!d ? <div className="ap-spin" /> : (
        <section className="ap-card am-noprint">
          <dl className="am-nums am-sum">
            <div data-strong><dt>{s.group_debt}</dt><dd><span className="am-bal" data-sign={Number(d.total_debt) > 0 ? 'owes' : 'zero'}><N>{money(d.total_debt, lang)}</N></span></dd></div>
            <div><dt>{s.pending_sep}</dt><dd><N>{gbText(d.pending_gb)}</N> · <N>{toman(d.pending_amount, lang)}</N></dd></div>
          </dl>
          <div className="am-row am-exp">
            <button type="button" className="ap-link" onClick={() => exp('/accounting/', 'csv', { group: gid })}><Ic n="download" />{s.csv}</button>
            <button type="button" className="ap-link" onClick={() => exp('/accounting/', 'xlsx', { group: gid })}><Ic n="download" />{s.xlsx}</button>
          </div>
          <ul className="am-acc">
            {d.admins.map((r) => (
              <li key={r.username}>
                <div className="am-acc-r">
                  <b><bdi>{r.username}</bdi></b>
                  <span>{s.charges}: <N>{toman(r.charges, lang)}</N></span>
                  <span>{s.payments}: <N>{toman(r.payments, lang)}</N></span>
                  <span>{s.balance}: <span className="am-bal" data-sign={Number(r.balance) > 0 ? 'owes' : 'zero'}><N>{money(r.balance, lang)}</N></span></span>
                  {Number(r.pending.gb) > 0 && <span className="am-pend">{s.pend}: <N>{gbText(r.pending.gb)}</N> · <N>{toman(r.pending.amount, lang)}</N></span>}
                  <button type="button" className="ap-link" aria-expanded={open === r.username} onClick={() => setOpen(open === r.username ? null : r.username)}><Ic n="doc" />{open === r.username ? s.hide : s.statement}</button>
                </div>
                {open === r.username && <AdminStatement username={r.username} params={params} s={s} lang={lang} exp={exp} />}
              </li>
            ))}
          </ul>
        </section>
      )}
      <GroupStatement gid={gid} params={params} s={s} lang={lang} exp={exp} />
    </>
  )
}

const Kind = ({ k, s }) => <span className="ap-st-k" data-kind={k}>{s['k_' + k] || k}</span>

function AdminStatement({ username, params, s, lang, exp }) {
  const [st, setSt] = useState(null)
  const url = `/admins/${encodeURIComponent(username)}/statement/`
  useEffect(() => { http.get(url, { params }).then((r) => setSt(r.data)).catch(() => setSt(false)) }, [username, params])
  if (st === null) return <div className="ap-spin" />
  if (!st) return <div className="ap-alert">{s.error}</div>
  return (
    <div className="am-st">
      <div className="am-row am-exp">
        <button type="button" className="ap-link" onClick={() => exp(url, 'csv')}><Ic n="download" />{s.csv}</button>
        <button type="button" className="ap-link" onClick={() => exp(url, 'xlsx')}><Ic n="download" />{s.xlsx}</button>
      </div>
      {!st.entries.length ? <p className="ap-foot">{s.none}</p> : (
        <ul className="ap-st">
          {[...st.entries].reverse().map((e) => (
            <li key={e.id} data-voided={e.voided || undefined}>
              <Kind k={e.kind} s={s} />
              <span className="ap-st-d">{jalali(e.date, false, lang)}</span>
              <span className="ap-st-a" data-sign={e.voided ? 'zero' : Number(e.signed) < 0 ? 'credit' : 'owes'}><N>{Number(e.signed) < 0 ? '−' : '+'}{toman(Math.abs(Number(e.amount)), lang)}</N></span>
              <span className="ap-st-r">{s.running}: <N>{money(e.balance, lang)}</N>{e.gb && <> · <N>{gbText(e.gb)}</N></>}{e.voided && ` · ${s.voided}`}</span>
            </li>
          ))}
        </ul>
      )}
      {st.pending?.length > 0 && <Pending rows={st.pending} s={s} lang={lang} />}
    </div>
  )
}

function Pending({ rows, s, lang }) {
  return (
    <div className="am-pendbox">
      <h4>{s.pending_sep}</h4>
      <ul>{rows.map((p) => <li key={p.id}><span>{jalali(p.date, false, lang)}</span><bdi>{p.admin}</bdi><N>+{gbText(p.gb)}</N><N>{p.price_per_gb != null ? toman(p.amount, lang) : s.no_price}</N></li>)}</ul>
    </div>
  )
}

function GroupStatement({ gid, params, s, lang, exp }) {
  const [st, setSt] = useState(null)
  const url = `/groups/${gid}/statement/`
  useEffect(() => { setSt(null); http.get(url, { params }).then((r) => setSt(r.data)).catch(() => setSt(false)) }, [gid, params])
  return (
    <section className="ap-card am-gst">
      <div className="am-gst-h">
        <h2><Ic n="doc" size={16} />{s.group_st}{st && <> — <bdi>{st.group.name}</bdi></>}</h2>
        <div className="am-row am-exp am-noprint">
          <button type="button" className="ap-link" onClick={() => exp(url, 'csv')}><Ic n="download" />{s.csv}</button>
          <button type="button" className="ap-link" onClick={() => exp(url, 'xlsx')}><Ic n="download" />{s.xlsx}</button>
          <button type="button" className="ap-link" onClick={() => window.print()}><Ic n="doc" />{s.print}</button>
        </div>
      </div>
      {st === null ? <div className="ap-spin" /> : !st ? <div className="ap-alert">{s.error}</div> : (
        <>
          <dl className="am-nums am-sum">
            {st.from && <div><dt>{s.opening}</dt><dd><N>{money(st.opening, lang)}</N></dd></div>}
            <div><dt>{s.charges}</dt><dd><N>{toman(st.charges, lang)}</N></dd></div>
            <div><dt>{s.payments}</dt><dd><N>{toman(st.payments, lang)}</N></dd></div>
            <div><dt>{s.closing}</dt><dd><N>{money(st.closing, lang)}</N></dd></div>
            <div data-strong><dt>{s.group_debt}</dt><dd><span className="am-bal" data-sign={Number(st.total_debt) > 0 ? 'owes' : 'zero'}><N>{money(st.total_debt, lang)}</N></span></dd></div>
          </dl>
          {!st.entries.length ? <p className="ap-foot">{s.none}</p> : (
            <div className="am-tw">
              <table className="am-table">
                <thead><tr><th>{s.date}</th><th>{s.admin}</th><th>{s.type}</th><th>GB</th><th>{s.amount}</th><th>{s.running}</th></tr></thead>
                <tbody>
                  {st.entries.map((e) => (
                    <tr key={e.id} data-voided={e.voided || undefined}>
                      <td>{jalali(e.date, false, lang)}</td>
                      <td><bdi>{e.admin}</bdi></td>
                      <td><Kind k={e.kind} s={s} /></td>
                      <td>{e.gb ? <N>{Number(e.gb).toLocaleString('en-US', { maximumFractionDigits: 2 })}</N> : '—'}</td>
                      <td><span className="am-bal" data-sign={e.voided ? 'zero' : Number(e.signed) < 0 ? 'credit' : 'owes'}><N>{Number(e.signed) < 0 ? '−' : '+'}{toman(Math.abs(Number(e.amount)), lang)}</N></span></td>
                      <td><N>{money(e.balance, lang)}</N></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {st.pending.length > 0 && <Pending rows={st.pending} s={s} lang={lang} />}
        </>
      )}
    </section>
  )
}

// ------------------------------------------------------------------ activity tab
function Activity({ s, lang }) {
  const [d, setD] = useState(null)
  useEffect(() => { http.get('/activity/').then((r) => setD(r.data.results)).catch(() => setD([])) }, [])
  if (d === null) return <div className="ap-spin" />
  if (!d.length) return <div className="ap-card ap-empty">{s.act_none}</div>
  return (
    <ul className="ap-card am-act">
      {d.map((a) => {
        const k = a.action.split('.').pop()
        const det = a.detail || {}
        return (
          <li key={a.id}>
            <b>{s.acts[k] || k}</b>
            {a.admin && <bdi>{a.admin}</bdi>}
            {det.gb && <N>+{gbText(det.gb)}</N>}
            {det.inbounds && <span>{det.inbounds.join(' · ')}</span>}
            <span className="am-act-t"><bdi>{a.group}</bdi> · {jalali(a.at, true, lang)}</span>
          </li>
        )
      })}
    </ul>
  )
}

const CSS = `
.am-main { max-width: 1100px; }
.am-who { font-weight: 600; color: var(--c-muted-fg); }
.am-tabs, .am-seg { display: flex; gap: 6px; flex-wrap: wrap; }
.am-tab { display: inline-flex; align-items: center; gap: 6px; min-height: 42px; padding: 0 16px; border-radius: 12px; border: 1px solid var(--c-border); background: transparent; color: var(--c-text); font-weight: 800; font-size: 14px; }
.am-tab.on { background: color-mix(in srgb, var(--c-primary) 82%, #000); border-color: transparent; color: #fff; }
.am-tabs .am-tab { flex: 1 1 0; justify-content: center; }
.am-cap { margin: 0; }
.am-group { display: flex; flex-direction: column; gap: 10px; }
.am-gh { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; }
.am-gh h2 { display: inline-flex; align-items: center; gap: 6px; font-size: 17px; font-weight: 800; }
.am-debt { font-size: 13px; font-weight: 700; color: var(--c-muted-fg); }
.am-btn { margin-top: 0; min-height: 44px; padding: 0 16px; display: inline-flex; align-items: center; gap: 6px; }
.am-new { margin-inline-start: auto; }
.am-grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(min(100%, 320px), 1fr)); }
.am-card { display: flex; flex-direction: column; gap: 4px; }
.am-card h3 { font-size: 16px; font-weight: 800; overflow-wrap: anywhere; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.am-tag { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 999px; background: color-mix(in srgb, var(--c-primary) 12%, transparent); color: var(--c-primary-fg, var(--c-primary)); }
.am-nums { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 6px; }
.am-nums > div { padding: 8px 10px; border-radius: 12px; border: 1px solid var(--c-border); min-width: 0; }
.am-nums > div[data-strong] { border-color: color-mix(in srgb, var(--c-danger) 35%, var(--c-border)); }
.am-nums dt { font-size: 11.5px; font-weight: 600; color: var(--c-muted-fg); }
.am-nums dd { font-size: 14.5px; font-weight: 800; margin-top: 2px; overflow-wrap: anywhere; }
.am-nums dd small { font-weight: 600; color: var(--c-muted-fg); }
.am-sum { grid-template-columns: repeat(auto-fit, minmax(min(100%, 160px), 1fr)); }
.am-inb { font-size: 12.5px !important; }
.am-bal { font-weight: 800; }
.am-bal[data-sign="owes"] { color: var(--c-danger-fg); } .am-bal[data-sign="credit"] { color: var(--c-success-fg); } .am-bal[data-sign="zero"] { color: var(--c-muted-fg); }
.am-pend { display: inline-flex; align-items: center; gap: 5px; font-size: 12.5px; font-weight: 700; color: var(--c-warning-fg); }
.am-acts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.am-acts .ap-link { margin: 0; flex: 1 1 auto; }
.ap-link:disabled { opacity: .5; cursor: not-allowed; }
.am-hint { font-size: 12px; color: var(--c-muted-fg); line-height: 1.7; }
.am-back { position: fixed; inset: 0; z-index: 50; background: rgba(0,0,0,.45); display: grid; place-items: center; padding: 16px; }
.am-dlg { width: min(100%, 480px); max-height: 90vh; overflow: auto; background: var(--c-bg); border: 1px solid var(--c-border); border-radius: 18px; padding: 16px; }
.am-dlg-h { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 10px; font-size: 16px; }
.am-x { width: 40px; height: 40px; display: grid; place-items: center; border-radius: 10px; border: 0; background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); color: var(--c-text); }
.am-form { display: flex; flex-direction: column; gap: 10px; }
.am-form label { display: flex; flex-direction: column; gap: 5px; font-size: 12.5px; font-weight: 700; }
.am-l { font-size: 12.5px; font-weight: 700; }
.am-pw { display: flex; gap: 6px; align-items: center; }
.am-pw .ap-input { flex: 1; min-width: 0; }
.am-pw .ap-link { margin: 0; white-space: nowrap; }
.am-row { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; align-items: center; }
.am-row .ap-link { margin: 0; }
.am-exp { justify-content: flex-start; margin: 8px 0; }
.am-roles { display: flex; flex-direction: column; gap: 6px; }
.am-form .am-rolei { flex-direction: row; align-items: center; gap: 10px; padding: 9px 12px; border-radius: 12px; border: 1px solid var(--c-border); font-weight: 500; min-height: 44px; }
.am-rolei[data-on] { border-color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 8%, transparent); }
.am-rolei span { display: flex; flex-direction: column; }
.am-rolei small { color: var(--c-muted-fg); font-size: 11.5px; }
.am-cmp { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 8px; }
.am-cmp > div { padding: 10px; border-radius: 12px; border: 1px solid var(--c-border); }
.am-cmp > div[data-strong] { border-color: var(--c-primary); }
.am-cmp dt { font-size: 11.5px; color: var(--c-muted-fg); font-weight: 700; }
.am-cmp dd { font-size: 15px; font-weight: 800; overflow-wrap: anywhere; }
.am-range { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 8px; }
.am-range label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; font-weight: 700; flex: 1 1 calc(50% - 8px); min-width: 0; }
.am-range .ap-link { margin: 0; flex: 1 1 auto; }
.am-acc { display: flex; flex-direction: column; margin-top: 4px; }
.am-acc > li { border-top: 1px solid var(--c-border); padding: 10px 0; }
.am-acc-r { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 14px; font-size: 13px; }
.am-acc-r .ap-link { margin-inline-start: auto; }
.am-st { padding: 6px 0 0; }
.am-pendbox { margin-top: 10px; padding: 10px 12px; border-radius: 12px; background: color-mix(in srgb, var(--c-warning) 9%, transparent); }
.am-pendbox h4 { font-size: 13px; font-weight: 800; color: var(--c-warning-fg); margin-bottom: 4px; }
.am-pendbox li { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 12.5px; padding: 4px 0; }
.am-gst-h { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; }
.am-gst-h h2 { display: inline-flex; align-items: center; gap: 6px; font-size: 16px; font-weight: 800; }
.am-tw { overflow-x: auto; margin-top: 10px; }
.am-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.am-table th { text-align: start; font-size: 11.5px; color: var(--c-muted-fg); font-weight: 700; padding: 6px 8px; border-bottom: 1px solid var(--c-border); white-space: nowrap; }
.am-table td { padding: 8px; border-bottom: 1px solid var(--c-border); white-space: nowrap; }
.am-table tr[data-voided] { opacity: .5; }
.am-act { display: flex; flex-direction: column; }
.am-act li { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; padding: 9px 0; border-top: 1px solid var(--c-border); font-size: 13px; }
.am-act li:first-child { border-top: 0; }
.am-act-t { margin-inline-start: auto; font-size: 12px; color: var(--c-muted-fg); }
@media (max-width: 639px) {
  .am-table thead { display: none; }
  .am-table tr { display: grid; grid-template-columns: auto 1fr auto; gap: 2px 10px; padding: 8px 0; border-bottom: 1px solid var(--c-border); }
  .am-table td { padding: 0; border: 0; white-space: normal; }
  .am-new { margin-inline-start: 0; width: 100%; justify-content: center; }
  .am-acc-r .ap-link { margin-inline-start: 0; }
}
@media print {
  .am-noprint, .ap-top { display: none !important; }
  .am-gst { border: 0; }
}
`
