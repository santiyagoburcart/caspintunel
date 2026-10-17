import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n, enumLabel } from '../lib/i18n'
import { jalali, digits } from '../lib/format'
import { Alert, Spinner, Toggle } from '../components/ui'
import { useAuth } from '../lib/auth'
import { useUserActions } from '../lib/userActions'

const T = {
  fa: {
    subtitle: 'مشاهده، فیلتر و مدیریت کاربران ثبت‌شده از تلگرام و وب‌سایت',
    add_user: 'افزودن کاربر جدید',
    stat_total: 'کل کاربران ثبت‌شده', stat_active: 'حساب‌های فعال',
    stat_tg: 'کاربران تلگرام (ربات)', stat_web: 'کاربران وب‌سایت',
    search_ph: 'جستجو (نام، نام کاربری، ایمیل یا تلفن)...',
    f_source_all: 'منبع: همه', f_status_all: 'وضعیت: همه',
    only_active: 'فقط فعال', only_inactive: 'فقط غیرفعال', reset: 'بازنشانی فیلترها',
    filters: 'فیلترها', f_source: 'منبع', f_status: 'وضعیت', f_all: 'همه', f_active: 'فعال', f_inactive: 'غیرفعال',
    n_users: '{n} کاربر', n_user1: '1 کاربر', n_filters: '{n} فیلتر فعال', clear_search: 'پاک کردن جستجو',
    col_user: 'نام کاربری و مشخصات', col_services: 'کل سرویس‌ها', col_joined: 'تاریخ عضویت',
    col_actions: 'عملیات', uid: 'شناسه', legacy: 'قدیمی',
    rows_of: 'نمایش {a} از {b} کاربر', prev: 'قبلی', next: 'بعدی',
    none: 'کاربری یافت نشد',
    modal_add_title: 'افزودن کاربر جدید', modal_edit_title: 'ویرایش کاربر: {name}',
    modal_sub: 'مشخصات هویتی و تنظیمات دسترسی کاربر کاسپین تانل',
    fld_fullname: 'نام و نام خانوادگی', fld_username: 'نام کاربری (یوزرنیم)',
    fld_telegram: 'شناسه عددی تلگرام (Chat ID)', fld_tg_username: 'نام کاربری تلگرام',
    fld_phone: 'شماره موبایل', phone_hint: 'به ‎09xxxxxxxxx‎ تبدیل می‌شود؛ باید یکتا باشد', fld_email: 'پست الکترونیک (ایمیل)', fld_language: 'زبان',
    fld_password: 'رمز عبور', fld_password_new: 'رمز عبور جدید',
    fld_password_edit_hint: '(فقط برای تغییر وارد شود)',
    fld_status: 'وضعیت حساب کاربری',
    fld_status_hint: 'در حالت فعال، کاربر می‌تواند به تانل‌ها متصل شود و سفارش ثبت کند.',
    email_verified: 'ایمیل این کاربر تأیید شده است',
    this_week: 'این هفته',
    fld_note: 'یادداشت داخلی (فقط برای ادمین‌ها)',
    ph_note: 'توضیحات اختصاصی، شرایط ویژه یا بدهی این کاربر...',
    note_hint: 'این یادداشت هرگز به کاربر نمایش داده نمی‌شود.',
    ph_fullname: 'مثال: علی احمدی', ph_username: 'user_identifier',
    saving: 'در حال ثبت...', created_ok: 'کاربر جدید ساخته شد', updated_ok: 'تغییرات ذخیره شد',
    lang_fa: 'فارسی', lang_en: 'انگلیسی',
    purchase_history: 'سوابق خرید',
    deleted_users: 'کاربران حذف‌شده', delete_user: 'حذف کاربر',
  },
  en: {
    subtitle: 'View, filter and manage every user registered from Telegram and the website',
    add_user: 'Add new user',
    stat_total: 'Total registered users', stat_active: 'Active accounts',
    stat_tg: 'Telegram (bot) users', stat_web: 'Website users',
    search_ph: 'Search (name, username, email or phone)…',
    f_source_all: 'Source: all', f_status_all: 'Status: all',
    only_active: 'Active only', only_inactive: 'Inactive only', reset: 'Reset filters',
    filters: 'Filters', f_source: 'Source', f_status: 'Status', f_all: 'All', f_active: 'Active', f_inactive: 'Inactive',
    n_users: '{n} users', n_user1: '1 user', n_filters: '{n} filter(s) on', clear_search: 'Clear search',
    col_user: 'Username & details', col_services: 'Total services', col_joined: 'Joined',
    col_actions: 'Actions', uid: 'ID', legacy: 'Legacy',
    rows_of: 'Showing {a} of {b} users', prev: 'Prev', next: 'Next',
    none: 'No users found',
    modal_add_title: 'Add new user', modal_edit_title: 'Edit user: {name}',
    modal_sub: 'Identity details and access settings for the Caspian Tunnel user',
    fld_fullname: 'Full name', fld_username: 'Username',
    fld_telegram: 'Telegram numeric ID (Chat ID)', fld_tg_username: 'Telegram username',
    fld_phone: 'Mobile number', phone_hint: 'Stored as 09xxxxxxxxx; must be unique', fld_email: 'Email address', fld_language: 'Language',
    fld_password: 'Password', fld_password_new: 'New password',
    fld_password_edit_hint: '(fill only to change)',
    fld_status: 'Account status',
    fld_status_hint: 'When active, the user can connect to tunnels and place orders.',
    email_verified: "This user's email is verified",
    this_week: 'this week',
    fld_note: 'Internal note (admins only)',
    ph_note: "Notes specific to this user — special terms, debt, etc.",
    note_hint: 'This note is never shown to the user.',
    ph_fullname: 'e.g. Ali Ahmadi', ph_username: 'user_identifier',
    saving: 'Saving…', created_ok: 'New user created', updated_ok: 'Changes saved',
    lang_fa: 'Persian', lang_en: 'English',
    purchase_history: 'Purchase history',
    deleted_users: 'Deleted users', delete_user: 'Delete user',
  },
}

const PAGE = 20
const AV_TONES = ['#1464BA', '#11AB53', '#7C3AED', '#D97706', '#0891B2', '#DB2777']

const initials = (r) => {
  // NFKC folds fancy unicode (e.g. mathematical-italic) letters back to plain ASCII
  const name = String(r.name || '').normalize('NFKC').trim()
  if (name) {
    const parts = name.split(/\s+/).filter(Boolean)
    const a = [...parts[0]]
    const b = parts[1] ? [...parts[1]] : a
    return ((a[0] || '') + (parts[1] ? b[0] : a[1] || '')).toUpperCase()
  }
  if (r.source === 'bot') return 'TG'
  return (String(r.username || '?').replace(/[^a-zA-Z0-9]/g, '').slice(0, 2) || '?').toUpperCase()
}

function Ico({ d, w = 16 }) {
  return (
    <svg viewBox="0 0 24 24" width={w} height={w} fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{d}</svg>
  )
}
const I = {
  users: <><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75" /></>,
  check: <><path d="M22 11.08V12a10 10 0 11-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></>,
  bot: <><rect x="3" y="11" width="18" height="10" rx="2" /><circle cx="12" cy="5" r="2" /><path d="M12 7v4M8 16h.01M16 16h.01" /></>,
  globe: <><circle cx="12" cy="12" r="10" /><path d="M2 12h20M12 2a15.3 15.3 0 010 20 15.3 15.3 0 010-20z" /></>,
  search: <><circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" /></>,
  reset: <><path d="M23 4v6h-6M1 20v-6h6" /><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" /></>,
  edit: <path d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />,
  plus: <path d="M12 5v14M5 12h14" />,
  close: <path d="M18 6L6 18M6 6l12 12" />,
  eye: <><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z" /><circle cx="12" cy="12" r="3" /></>,
  eyeOff: <><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24" /><path d="M1 1l22 22" /></>,
  bag: <><path d="M6 2l1.5 5M18 2l-1.5 5M3.5 7h17l-1.2 12.2a2 2 0 01-2 1.8H6.7a2 2 0 01-2-1.8L3.5 7z" /><path d="M8 11a4 4 0 008 0" /></>,
  trash: <><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" /></>,
  archive: <><rect x="2" y="3" width="20" height="5" rx="1" /><path d="M4 8v11a2 2 0 002 2h12a2 2 0 002-2V8M10 12h4" /></>,
}

const GROWTH = {
  up: { tone: 'var(--c-success)', arrow: '↑' },
  down: { tone: 'var(--c-danger)', arrow: '↓' },
  flat: { tone: 'var(--c-text-muted)', arrow: '→' },
}

function GrowthBadge({ stat, s, lang }) {
  if (!stat || stat.growth_direction == null) return null
  const g = GROWTH[stat.growth_direction] || GROWTH.flat
  const pct = Math.abs(stat.growth_percent ?? 0)
  const pctStr = `${pct}%`
  return (
    <span className="usr-growth" style={{ background: `color-mix(in srgb, ${g.tone} 14%, transparent)`, color: g.tone }}>
      {g.arrow} {pctStr} {s.this_week}
    </span>
  )
}

function Stat({ label, stat, tone, icon, s, lang }) {
  return (
    <div className="card usr-stat">
      <div className="usr-stat-top">
        <span className="usr-stat-label">{label}</span>
        <span className="usr-stat-ico" style={{ background: `color-mix(in srgb, ${tone} 14%, transparent)`, color: tone }}>{icon}</span>
      </div>
      <div className="usr-stat-row">
        <span className="usr-stat-val">{stat?.count == null ? '—' : digits(stat.count, lang)}</span>
        <GrowthBadge stat={stat} s={s} lang={lang} />
      </div>
      <span className="usr-stat-accent" style={{ background: tone }} />
    </div>
  )
}

function Pw({ value, onChange, placeholder, t }) {
  const [show, setShow] = useState(false)
  return (
    <div className="usr-pw">
      <input className="input" type={show ? 'text' : 'password'} dir="ltr"
        value={value} onChange={onChange} placeholder={placeholder} />
      <button type="button" className="usr-pw-eye" onClick={() => setShow((s) => !s)}
        aria-label={t(show ? 'hide_password' : 'show_password')}>
        <Ico d={show ? I.eyeOff : I.eye} w={15} />
      </button>
    </div>
  )
}

const emptyForm = { name: '', username: '', telegram_id: '', telegram_username: '', phone: '', email: '', language: 'fa', password: '', is_active: true, email_verified: false, admin_note: '' }

function UserModal({ row, s, t, lang, onClose, onSaved }) {
  const editing = !!row
  const [f, setF] = useState(() => (row ? {
    name: row.name || '', username: row.username || '',
    telegram_id: row.telegram_id || '', telegram_username: row.telegram_username || '',
    phone: row.phone || '', email: row.email || '', language: row.language || 'fa',
    password: '', is_active: !!row.is_active, email_verified: !!row.email_verified,
    admin_note: row.admin_note || '',
  } : emptyForm))
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e?.target?.type === 'checkbox' ? e.target.checked : (e?.target ? e.target.value : e) }))

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setErr('')
    try {
      if (editing) {
        const patch = {
          name: f.name, username: f.username, email: f.email, phone: f.phone,
          telegram_id: f.telegram_id || null, telegram_username: f.telegram_username || null,
          language: f.language, is_active: f.is_active, email_verified: f.email_verified,
          admin_note: f.admin_note,
        }
        await api.patch(`/admin/users/${row.id}/`, patch)
        if (f.password) await api.post(`/admin/users/${row.id}/set-password/`, { password: f.password })
      } else {
        await api.post('/admin/users/', {
          username: f.username, password: f.password, email: f.email || '',
          name: f.name, phone: f.phone, language: f.language, is_active: f.is_active,
        })
      }
      onSaved(editing ? s.updated_ok : s.created_ok)
    } catch (e2) {
      // backend phone errors come as "fa / en" — show the UI language's half
      const msg = apiError(e2, t('load_error'))
      const parts = String(msg).split(' / ')
      setErr(parts.length === 2 ? parts[lang === 'en' ? 1 : 0] : msg)
    } finally { setBusy(false) }
  }

  return (
    <div className="usr-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="usr-modal card" role="dialog" aria-modal="true">
        <div className="usr-modal-head">
          <div className="flex items-center gap-3">
            <span className="usr-modal-ico"><Ico d={I.users} w={18} /></span>
            <div>
              <h2 className="font-bold">{editing ? s.modal_edit_title.replace('{name}', row.name || row.username) : s.modal_add_title}</h2>
              <p className="text-xs text-muted mt-0.5">{s.modal_sub}</p>
            </div>
          </div>
          <button type="button" className="usr-icon-btn" onClick={onClose} aria-label={t('cancel')}><Ico d={I.close} /></button>
        </div>

        <form className="usr-modal-body" onSubmit={submit}>
          <Alert>{err}</Alert>
          <div className="usr-grid2">
            <label className="usr-fld">
              <span className="label">{s.fld_fullname}</span>
              <input className="input" value={f.name} onChange={set('name')} placeholder={s.ph_fullname} />
            </label>
            <label className="usr-fld">
              <span className="label">{s.fld_username} <b className="usr-req">*</b></span>
              <input className="input" dir="ltr" required value={f.username} onChange={set('username')} placeholder={s.ph_username} />
            </label>
          </div>

          <div className="usr-grid2">
            <label className="usr-fld">
              <span className="label">{s.fld_telegram}</span>
              <input className="input" dir="ltr" inputMode="numeric" value={f.telegram_id} onChange={set('telegram_id')} placeholder="582194819" disabled={!editing} />
            </label>
            <label className="usr-fld">
              <span className="label">{s.fld_tg_username}</span>
              <input className="input" dir="ltr" value={f.telegram_username} onChange={set('telegram_username')} placeholder="@username" disabled={!editing} />
            </label>
          </div>

          <div className="usr-grid2">
            <label className="usr-fld">
              <span className="label">{s.fld_phone}</span>
              <input className="input" dir="ltr" type="tel" inputMode="tel" value={f.phone} onChange={set('phone')} placeholder="09121234567" />
              <span className="text-xs text-muted">{s.phone_hint}</span>
            </label>
            <label className="usr-fld">
              <span className="label">{s.fld_email}</span>
              <input className="input" dir="ltr" type="email" value={f.email} onChange={set('email')} placeholder="user@domain.com" />
            </label>
          </div>

          <div className="usr-grid2">
            <label className="usr-fld">
              <span className="label">{s.fld_language}</span>
              <select className="input" value={f.language} onChange={set('language')}>
                <option value="fa">{s.lang_fa}</option>
                <option value="en">{s.lang_en}</option>
              </select>
            </label>
            <div className="usr-fld">
              <span className="label">
                {editing ? s.fld_password_new : s.fld_password} {editing && <span className="text-muted font-normal">{s.fld_password_edit_hint}</span>}
                {!editing && <b className="usr-req"> *</b>}
              </span>
              <Pw value={f.password} onChange={set('password')} placeholder="••••••••" t={t} />
            </div>
          </div>

          <div className="usr-status-box">
            <div className="flex items-center gap-3">
              <span className={'usr-dot ' + (f.is_active ? 'on' : '')} />
              <div>
                <span className="text-sm font-semibold block">{s.fld_status}</span>
                <span className="text-xs text-muted">{s.fld_status_hint}</span>
              </div>
            </div>
            <Toggle checked={f.is_active} onChange={(v) => setF((p) => ({ ...p, is_active: v }))} label={s.fld_status} />
          </div>

          {editing && (
            <label className="usr-check">
              <input type="checkbox" checked={f.email_verified} onChange={set('email_verified')} />
              <span className="text-xs">{s.email_verified}</span>
            </label>
          )}

          {editing && (
            <label className="usr-fld">
              <span className="label">{s.fld_note}</span>
              <textarea className="input usr-note" rows={2} value={f.admin_note}
                onChange={set('admin_note')} placeholder={s.ph_note} />
              <span className="text-xs text-muted">{s.note_hint}</span>
            </label>
          )}

          <div className="usr-modal-foot">
            <button type="button" className="btn-ghost text-sm" onClick={onClose}>{t('cancel')}</button>
            <button type="submit" className="btn-primary text-sm" disabled={busy}>
              {busy ? s.saving : <><Ico d={I.check} w={15} /> {t('save')}</>}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function Users() {
  const { t, lang } = useI18n()
  const s = T[lang] || T.fa
  const [rows, setRows] = useState(null)
  const [count, setCount] = useState(0)
  const [offset, setOffset] = useState(0)
  const [q, setQ] = useState('')          // applied search
  const [qInput, setQInput] = useState('') // what is typed (debounced into q)
  const [source, setSource] = useState('')
  const [active, setActive] = useState('')
  const [err, setErr] = useState('')
  const [toast, setToast] = useState('')
  const [modal, setModal] = useState(null) // { row } | { row: null } | null
  const [stats, setStats] = useState({})
  const { can } = useAuth()
  const userActions = useUserActions()

  const params = useMemo(() => {
    const p = new URLSearchParams({ limit: PAGE, offset })
    if (q) p.set('search', q)
    if (source) p.set('source', source)
    if (active) p.set('is_active', active)
    return p
  }, [q, source, active, offset])

  const load = useCallback(() => {
    setRows(null); setErr('')
    api.get(`/admin/users/?${params}`)
      .then((r) => { setRows(r.data.results); setCount(r.data.count ?? r.data.results.length) })
      .catch(() => { setRows([]); setErr(t('load_error')) })
  }, [params, t])
  useEffect(load, [load])

  const loadStats = useCallback(() => {
    api.get('/admin/users/stats/').then((r) => setStats(r.data)).catch(() => setStats({}))
  }, [])
  useEffect(loadStats, [loadStats])

  const toggle = async (u) => {
    setErr('')
    try {
      await api.post(`/admin/users/${u.id}/${u.is_active ? 'disable' : 'enable'}/`)
      setRows((rs) => rs.map((r) => (r.id === u.id ? { ...r, is_active: !r.is_active } : r)))
      loadStats()
    } catch (e) { setErr(apiError(e)) }
  }

  const removeUser = async (u) => {
    if (await userActions.remove(u)) { load(); loadStats() }
  }

  // search as you type (debounced) — Enter applies at once
  useEffect(() => {
    const id = setTimeout(() => { if (qInput.trim() !== q) { setQ(qInput.trim()); setOffset(0) } }, 300)
    return () => clearTimeout(id)
  }, [qInput])
  const doSearch = () => { setQ(qInput.trim()); setOffset(0) }
  const resetFilters = () => { setQ(''); setQInput(''); setSource(''); setActive(''); setOffset(0) }
  const activeFilters = (q ? 1 : 0) + (source ? 1 : 0) + (active ? 1 : 0)
  const chip = (value, current, set, label) => (
    <button key={value || 'all'} type="button" className={'usr-chip' + (current === value ? ' on' : '')}
      aria-pressed={current === value} onClick={() => { set(value); setOffset(0) }}>{label}</button>
  )
  const onSaved = (msg) => { setModal(null); setToast(msg); load(); loadStats(); setTimeout(() => setToast(''), 2500) }

  const page = Math.floor(offset / PAGE) + 1
  const pages = Math.max(1, Math.ceil(count / PAGE))
  const shownFrom = count === 0 ? 0 : offset + 1
  const shownTo = Math.min(offset + PAGE, count)

  return (
    <div className="usr space-y-5">
      <style>{CSS}</style>

      <div className="usr-head">
        <div>
          <h1 className="text-lg font-bold">{t('users')}</h1>
          <p className="text-sm text-muted mt-1">{s.subtitle}</p>
        </div>
        <div className="usr-head-acts">
          <Link to="/users/deleted" className="usr-hist-btn usr-archive-link" aria-label={s.deleted_users} title={s.deleted_users}>
            <Ico d={I.archive} w={15} /> <span className="usr-archive-t">{s.deleted_users}</span>
          </Link>
          <button type="button" className="btn-primary text-sm" onClick={() => setModal({ row: null })}>
            <Ico d={I.plus} w={15} /> {s.add_user}
          </button>
        </div>
      </div>

      <div className="usr-stats">
        <Stat label={s.stat_total} stat={stats.total} tone="#1464BA" icon={<Ico d={I.users} />} s={s} lang={lang} />
        <Stat label={s.stat_active} stat={stats.active} tone="#11AB53" icon={<Ico d={I.check} />} s={s} lang={lang} />
        <Stat label={s.stat_tg} stat={stats.bot} tone="#0891B2" icon={<Ico d={I.bot} />} s={s} lang={lang} />
        <Stat label={s.stat_web} stat={stats.site} tone="#7C3AED" icon={<Ico d={I.globe} />} s={s} lang={lang} />
      </div>

      <Alert>{err}</Alert>
      {toast && <Alert kind="success">{toast}</Alert>}

      <div className="card usr-toolbar">
        <div className="usr-search">
          <span className="usr-search-ico"><Ico d={I.search} w={17} /></span>
          <input className="input" type="search" aria-label={s.search_ph} placeholder={s.search_ph} value={qInput}
            onChange={(e) => setQInput(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && doSearch()} enterKeyHint="search" />
          {qInput && (
            <button type="button" className="usr-search-clear" onClick={() => { setQInput(''); setQ(''); setOffset(0) }}
              aria-label={s.clear_search} title={s.clear_search}>×</button>
          )}
        </div>
        <div className="usr-filters" role="group" aria-label={s.filters}>
          <span className="usr-fgroup">
            <span className="usr-fgroup-l">{s.f_source}</span>
            {chip('', source, setSource, s.f_all)}{chip('bot', source, setSource, t('src_bot'))}{chip('site', source, setSource, t('src_site'))}
          </span>
          <span className="usr-fgroup">
            <span className="usr-fgroup-l">{s.f_status}</span>
            {chip('', active, setActive, s.f_all)}{chip('true', active, setActive, s.f_active)}{chip('false', active, setActive, s.f_inactive)}
          </span>
        </div>
        <div className="usr-tb-foot">
          <span className="usr-total" aria-live="polite">
            {count === 1 ? s.n_user1 : s.n_users.replace('{n}', digits(count, lang))}
            {activeFilters > 0 && <span className="usr-fbadge">{s.n_filters.replace('{n}', digits(activeFilters, lang))}</span>}
          </span>
          {activeFilters > 0 && (
            <button type="button" className="usr-reset" onClick={resetFilters}><Ico d={I.reset} w={14} />{s.reset}</button>
          )}
        </div>
      </div>

      {rows === null ? (
        <div className="grid place-items-center py-16"><Spinner /></div>
      ) : rows.length === 0 ? (
        <div className="card text-center text-muted">{s.none}</div>
      ) : (
        <div className="card p-0 usr-wrap">
          <table className="usr-table">
            <thead>
              <tr>
                <th>{s.col_user}</th><th>{t('name')}</th><th>{t('phone')}</th>
                <th>{t('source')}</th><th className="usr-c">{s.col_services}</th>
                <th>{s.col_joined}</th><th className="usr-c">{t('active')}</th>
                <th className="usr-c">{s.col_actions}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="usr-row">
                  <td>
                    <div className="usr-idcell">
                      <span className="usr-av" style={{ background: AV_TONES[r.id % AV_TONES.length] }}>{initials(r)}</span>
                      <div>
                        <div className="usr-uname">
                          <span dir="ltr">{r.username}</span>
                          <span className={'usr-src-tag ' + (r.source === 'bot' ? 'bot' : 'site')}>{enumLabel(t, 'src_', r.source)}</span>
                          {r.is_legacy && <span className="usr-src-tag legacy">{s.legacy}</span>}
                        </div>
                        <span className="usr-sub">{s.uid}: #{r.id}</span>
                        <span className="usr-sub usr-sub-m">{[r.name, r.phone].filter(Boolean).join(' · ') || '—'}</span>
                      </div>
                    </div>
                  </td>
                  <td data-label={t('name')}>{r.name || <span className="text-muted">—</span>}</td>
                  <td data-label={t('phone')} dir="ltr" className="usr-mono">{r.phone || <span className="text-muted">—</span>}</td>
                  <td data-label={t('source')}>
                    <span className={'usr-pill ' + (r.source === 'bot' ? 'bot' : 'site')}>
                      <Ico d={r.source === 'bot' ? I.bot : I.globe} w={13} />
                      {enumLabel(t, 'src_', r.source)}
                    </span>
                  </td>
                  <td data-label={s.col_services} className="usr-c"><span className="usr-count">{digits(r.service_count ?? 0, lang)}</span></td>
                  <td data-label={s.col_joined} className="usr-mono usr-date">{jalali(r.created_at, false, lang)}</td>
                  <td data-label={t('active')} className="usr-c"><Toggle checked={r.is_active} onChange={() => toggle(r)} label={t('active')} /></td>
                  <td data-label={s.col_actions} className="usr-c">
                    <div className="usr-actions">
                      <button type="button" className="usr-edit-btn" onClick={() => setModal({ row: r })} title={t('edit')} aria-label={t('edit')}>
                        <Ico d={I.edit} w={14} /> <span className="usr-act-l">{t('edit')}</span>
                      </button>
                      <Link to={`/users/${r.id}/orders`} className="usr-hist-btn" title={s.purchase_history} aria-label={s.purchase_history}>
                        <Ico d={I.bag} w={14} /> <span className="usr-act-l">{s.purchase_history}</span>
                      </Link>
                      {can('users.delete') && (
                        <button type="button" className="usr-del-btn" onClick={() => removeUser(r)} title={s.delete_user} aria-label={s.delete_user}>
                          <Ico d={I.trash} w={14} /> <span className="usr-act-l">{s.delete_user}</span>
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="usr-foot">
            <span className="text-xs text-muted">{s.rows_of.replace('{a}', `${digits(shownFrom, lang)}–${digits(shownTo, lang)}`).replace('{b}', digits(count, lang))}</span>
            <div className="usr-pager">
              <button className="usr-icon-btn" disabled={page <= 1} onClick={() => setOffset(Math.max(0, offset - PAGE))}>{s.prev}</button>
              <span className="text-xs usr-mono">{digits(page, lang)} / {digits(pages, lang)}</span>
              <button className="usr-icon-btn" disabled={page >= pages} onClick={() => setOffset(offset + PAGE)}>{s.next}</button>
            </div>
          </div>
        </div>
      )}

      {modal && (
        <UserModal row={modal.row} s={s} t={t} lang={lang}
          onClose={() => setModal(null)} onSaved={onSaved} />
      )}
    </div>
  )
}

const CSS = `
.usr-head { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-start; justify-content: space-between; }
.usr-head .btn-primary { display: inline-flex; align-items: center; gap: 6px; }
.usr-head-acts { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.usr-archive-link { padding: 8px 13px; border-radius: 10px; }

.usr-stats { display: grid; grid-template-columns: repeat(1, 1fr); gap: 14px; }
@media (min-width: 640px) { .usr-stats { grid-template-columns: repeat(2, 1fr); } }
@media (min-width: 1024px) { .usr-stats { grid-template-columns: repeat(4, 1fr); } }
.usr-stat { position: relative; overflow: hidden; display: flex; flex-direction: column; gap: 14px; }
.usr-stat-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.usr-stat-label { font-size: 12px; font-weight: 600; color: var(--c-text-muted); }
.usr-stat-ico { width: 38px; height: 38px; border-radius: 11px; display: grid; place-items: center; flex-shrink: 0; }
.usr-stat-row { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.usr-stat-val { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 26px; font-weight: 800; letter-spacing: -.02em; }
.usr-growth { display: inline-flex; align-items: center; gap: 3px; padding: 2px 8px; border-radius: 7px; font-size: 11px; font-weight: 700; white-space: nowrap; }
.usr-stat-accent { position: absolute; inset-inline: 0; bottom: 0; height: 3px; opacity: .85; }

/* search + filters: one row on desktop, wraps on tablet, stacked on phones.
   (.usr-search must not carry a flex-basis in a column layout — it became its
   HEIGHT and pushed the absolutely-centred icon far below the input.) */
.usr-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; padding: 10px 12px; }
.usr-search { position: relative; display: flex; align-items: center; flex: 1 1 260px; min-width: 200px; max-width: 420px; }
.usr-search .input { width: 100%; height: 40px; min-height: 0; padding-block: 0; padding-inline-start: 36px; padding-inline-end: 36px; }
.usr-search-ico { position: absolute; inset-inline-start: 11px; top: 50%; transform: translateY(-50%); display: flex;
  color: var(--c-text-muted); pointer-events: none; }
.usr-search-clear { position: absolute; inset-inline-end: 4px; top: 50%; transform: translateY(-50%); width: 32px; height: 32px;
  display: grid; place-items: center; border-radius: 999px; font-size: 20px; line-height: 1; color: var(--c-text-muted); }
.usr-search-clear:hover { background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); color: var(--c-text); }
.usr-search .input::-webkit-search-cancel-button { -webkit-appearance: none; appearance: none; }
.usr-filters { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 14px; }
.usr-fgroup { display: inline-flex; align-items: center; gap: 5px; }
.usr-fgroup-l { font-size: 12px; font-weight: 700; color: var(--c-text-muted); margin-inline-end: 2px; }
.usr-chip { height: 32px; padding: 0 12px; border-radius: 999px; font-size: 12.5px; font-weight: 600; white-space: nowrap;
  color: var(--c-text); border: 1px solid var(--c-border); background: transparent; transition: background .15s, border-color .15s; }
.usr-chip:hover { border-color: var(--c-primary); }
.usr-chip.on { background: var(--c-primary); border-color: var(--c-primary); color: #fff; }
.usr-tb-foot { display: flex; align-items: center; gap: 8px; margin-inline-start: auto; }
.usr-total { display: inline-flex; align-items: center; gap: 8px; font-size: 12.5px; font-weight: 600; color: var(--c-text-muted); white-space: nowrap; }
.usr-fbadge { padding: 1px 8px; border-radius: 999px; font-size: 12px; font-weight: 700; color: var(--c-primary-fg);
  background: color-mix(in srgb, var(--c-primary) 12%, transparent); }
.usr-reset { display: inline-flex; align-items: center; gap: 5px; font-size: 12.5px; font-weight: 700; color: var(--c-danger-fg);
  height: 32px; padding: 0 8px; border-radius: 8px; white-space: nowrap; }
.usr-reset:hover { background: color-mix(in srgb, var(--c-danger) 10%, transparent); }
@media (max-width: 1023px) {     /* tablet: search on top, both chip groups on one row */
  .usr-fgroup-l { display: none; }
  .usr-fgroup + .usr-fgroup { padding-inline-start: 8px; border-inline-start: 1px solid var(--c-border); }
}
@media (max-width: 767px) {
  .usr-toolbar { flex-direction: column; align-items: stretch; flex-wrap: nowrap; padding: 10px; gap: 8px; }
  .usr-search { flex: none; max-width: none; min-width: 0; }
  .usr-search .input { font-size: 16px; height: 44px; }
  .usr-search-clear { width: 40px; height: 40px; inset-inline-end: 2px; }
  .usr-filters { flex-wrap: nowrap; overflow-x: auto; scrollbar-width: none; gap: 6px; margin-inline: -10px; padding-inline: 10px; }
  .usr-filters::-webkit-scrollbar { display: none; }
  .usr-fgroup { flex-shrink: 0; }
  .usr-fgroup + .usr-fgroup { padding-inline-start: 6px; border-inline-start: 1px solid var(--c-border); }
  .usr-fgroup-l { display: none; }
  .usr-chip { height: 44px; padding: 0 14px; }
  .usr-tb-foot { margin-inline-start: 0; justify-content: space-between; }
  .usr-reset { height: 44px; }
}
.usr-sel { max-width: 170px; flex: 0 1 150px; }

.usr-icon-btn {
  display: inline-flex; align-items: center; gap: 5px; padding: 8px 12px; border-radius: 10px;
  font-size: 12px; font-weight: 600; color: var(--c-text-muted);
  border: 1px solid var(--c-border); background: transparent; transition: .15s;
}
.usr-icon-btn:hover:not(:disabled) { color: var(--c-text); border-color: var(--c-primary); }
.usr-icon-btn:disabled { opacity: .4; cursor: not-allowed; }

.usr-wrap { overflow-x: auto; }
@media (min-width: 768px) {
  .usr-table td { white-space: nowrap; }
  .usr-actions { flex-wrap: nowrap; gap: 4px; }
  .usr-actions .usr-act-l { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
  .usr-actions > :is(.usr-edit-btn, .usr-hist-btn, .usr-del-btn) { width: 32px; height: 32px; padding: 0; justify-content: center; gap: 0; }
}
.usr-table { width: 100%; min-width: 900px; border-collapse: collapse; font-size: 13px; }
.usr-table thead th {
  text-align: start; font-weight: 600; font-size: 11.5px; text-transform: uppercase; letter-spacing: .03em;
  color: var(--c-text-muted); padding: 13px 16px; white-space: nowrap; border-bottom: 1px solid var(--c-border);
}
.usr-table td { padding: 12px 16px; vertical-align: middle; border-bottom: 1px solid var(--c-border); }
.usr-row:hover > td { background: color-mix(in srgb, var(--c-primary) 5%, transparent); }
.usr-c { text-align: center; }
.usr-mono { font-family: 'JetBrains Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }
.usr-date { white-space: nowrap; color: var(--c-text-muted); font-size: 12px; }

.usr-idcell { display: flex; align-items: center; gap: 11px; }
.usr-av {
  width: 38px; height: 38px; border-radius: 11px; flex-shrink: 0; color: #fff;
  display: grid; place-items: center; font-weight: 700; font-size: 12px; letter-spacing: .02em;
}
.usr-uname { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-family: 'JetBrains Mono', ui-monospace, monospace; font-weight: 700; font-size: 12.5px; }
.usr-sub { display: block; font-size: 11px; color: var(--c-text-muted); margin-top: 2px; }
.usr-src-tag { font-family: var(--font-sans, inherit); font-size: 9.5px; font-weight: 600; padding: 1px 6px; border-radius: 5px; letter-spacing: 0; }
.usr-src-tag.bot { background: color-mix(in srgb, #0891B2 15%, transparent); color: #0891B2; }
.usr-src-tag.site { background: color-mix(in srgb, #7C3AED 15%, transparent); color: #7C3AED; }
.usr-src-tag.legacy { background: color-mix(in srgb, var(--c-text-muted) 18%, transparent); color: var(--c-text-muted); }

.usr-pill { display: inline-flex; align-items: center; gap: 5px; padding: 3px 10px; border-radius: 999px; font-size: 11.5px; font-weight: 600; white-space: nowrap; }
.usr-pill.bot { background: color-mix(in srgb, #0891B2 14%, transparent); color: #0891B2; }
.usr-pill.site { background: color-mix(in srgb, #7C3AED 14%, transparent); color: #7C3AED; }
.usr-count { display: inline-grid; place-items: center; min-width: 28px; height: 26px; padding: 0 8px; border-radius: 8px; font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 12px; background: color-mix(in srgb, var(--c-primary) 12%, transparent); color: var(--c-primary); }
.usr-edit-btn {
  display: inline-flex; align-items: center; gap: 5px; padding: 5px 11px; border-radius: 9px;
  font-size: 12px; font-weight: 600; white-space: nowrap;
  color: var(--c-primary); border: 1px solid color-mix(in srgb, var(--c-primary) 32%, transparent);
  background: color-mix(in srgb, var(--c-primary) 8%, transparent); transition: background .15s;
}
.usr-edit-btn:hover { background: color-mix(in srgb, var(--c-primary) 16%, transparent); }
.usr-actions { display: inline-flex; align-items: center; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
.usr-hist-btn {
  display: inline-flex; align-items: center; gap: 5px; padding: 5px 11px; border-radius: 9px;
  font-size: 12px; font-weight: 600; white-space: nowrap;
  color: var(--c-text-muted); border: 1px solid var(--c-border); background: transparent; transition: .15s;
}
.usr-hist-btn:hover { color: var(--c-primary); border-color: var(--c-primary); }
.usr-del-btn {
  display: inline-flex; align-items: center; gap: 5px; padding: 5px 11px; border-radius: 9px;
  font-size: 12px; font-weight: 600; white-space: nowrap;
  color: var(--c-danger); border: 1px solid color-mix(in srgb, var(--c-danger) 32%, transparent);
  background: color-mix(in srgb, var(--c-danger) 7%, transparent); transition: background .15s;
}
.usr-del-btn:hover { background: color-mix(in srgb, var(--c-danger) 15%, transparent); }

.usr-foot { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: space-between; padding: 13px 16px; border-top: 1px solid var(--c-border); }
.usr-pager { display: flex; align-items: center; gap: 8px; }

/* phones: compact records — [avatar · user / name · phone ······ active] then
   [services] [joined] and the actions in one row */
.usr-sub-m { display: none; }
@media (max-width: 767px) {
  .usr-head { flex-wrap: nowrap; align-items: center; }
  .usr-head-acts { flex-wrap: nowrap; }
  .usr-archive-t { display: none; }
  .usr-stats { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; gap: 8px; }
  .usr-stat { gap: 2px; padding: 9px 12px !important; }
  .usr-stat-ico { display: none; }
  .usr-stat-val { font-size: 19px; }
  .usr-stat-row { gap: 6px; }
  .usr-wrap { overflow-x: visible; }
  .usr-table, .usr-table tbody { display: block; width: 100%; }
  .usr-table { min-width: 0; }
  .usr-table thead { display: none; }
  .usr-table tr.usr-row {
    display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); align-items: center;
    border: 1px solid var(--c-border); border-radius: 12px; margin: 8px; padding: 4px 0;
  }
  .usr-table tr.usr-row:hover > td { background: none; }
  .usr-table td { border: 0 !important; padding: 4px 12px; display: flex; flex-direction: row; align-items: center; gap: 6px; min-width: 0; font-size: 13px; overflow-wrap: anywhere; }
  .usr-table td::before { content: attr(data-label) ":"; font-size: 12px; font-weight: 600; color: var(--c-text-muted); white-space: nowrap; }
  .usr-table td:nth-child(2), .usr-table td:nth-child(3), .usr-table td:nth-child(4) { display: none; }
  .usr-table td:nth-child(1) { grid-column: 1 / 6; grid-row: 1; padding-block: 6px; }
  .usr-table td:nth-child(1)::before { display: none; }
  .usr-table td:nth-child(7) { grid-column: 6; grid-row: 1; justify-content: flex-end; padding-inline: 8px; }
  .usr-table td:nth-child(7)::before { display: none; }
  .usr-table td:nth-child(5), .usr-table td:nth-child(6) { grid-column: span 3; }
  .usr-table td:nth-child(8) { grid-column: 1 / -1; padding-top: 4px; }
  .usr-table td:nth-child(8)::before { display: none; }
  .usr-table .usr-sub-m { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .usr-table td:nth-child(1) .usr-sub:not(.usr-sub-m) { display: none; }
  .usr-av { width: 32px; height: 32px; border-radius: 10px; }
  .usr-idcell { gap: 8px; min-width: 0; }
  .usr-idcell > div { min-width: 0; }
  .usr-actions { justify-content: flex-start; flex-wrap: nowrap; width: 100%; }
  .usr-actions > * { flex: 1 1 0; justify-content: center; min-width: 0; min-height: 44px; overflow: hidden; text-overflow: ellipsis; }
  .usr-date { font-size: 13px; }
  .usr-foot { padding: 10px 12px; }
}

/* modal */
.usr-backdrop { position: fixed; inset: 0; z-index: 60; background: color-mix(in srgb, #0b1220 62%, transparent); backdrop-filter: blur(3px); display: flex; align-items: flex-start; justify-content: center; padding: 24px 16px; overflow-y: auto; }
.usr-modal { width: 100%; max-width: 640px; padding: 0; overflow: hidden; }
.usr-modal-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 18px 20px; border-bottom: 1px solid var(--c-border); }
.usr-modal-ico { width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center; flex-shrink: 0; background: color-mix(in srgb, var(--c-primary) 12%, transparent); color: var(--c-primary); }
.usr-modal-body { padding: 20px; display: flex; flex-direction: column; gap: 16px; }
.usr-grid2 { display: grid; grid-template-columns: 1fr; gap: 14px; }
@media (min-width: 560px) { .usr-grid2 { grid-template-columns: 1fr 1fr; } }
.usr-fld { display: flex; flex-direction: column; gap: 6px; }
.usr-fld .label { font-size: 12px; }
.usr-req { color: var(--c-danger); }
.usr-pw { position: relative; }
.usr-pw .input { width: 100%; padding-inline-end: 40px; }
.usr-pw-eye { position: absolute; inset-inline-end: 10px; top: 50%; transform: translateY(-50%); color: var(--c-text-muted); }
.usr-pw-eye:hover { color: var(--c-text); }
.usr-note { width: 100%; resize: vertical; min-height: 58px; line-height: 1.6; font-family: inherit; }
.usr-status-box { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px; border-radius: 14px; border: 1px solid color-mix(in srgb, var(--c-primary) 22%, transparent); background: color-mix(in srgb, var(--c-primary) 6%, transparent); }
.usr-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--c-text-muted); flex-shrink: 0; }
.usr-dot.on { background: var(--c-success); }
.usr-check { display: flex; align-items: center; gap: 8px; cursor: pointer; }
.usr-modal-foot { display: flex; justify-content: flex-end; gap: 10px; padding-top: 4px; }
.usr-modal-foot .btn-primary { display: inline-flex; align-items: center; gap: 6px; }
.usr-icon-btn.usr-modal-x { padding: 6px; }
`
