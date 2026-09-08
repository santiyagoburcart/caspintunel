import { useEffect, useMemo, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { digits } from '../lib/format'
import { DataTable } from '../components/DataTable'
import { Alert, Spinner, Toggle } from '../components/ui'

function useList(url) {
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  const load = () => api.get(url)
    .then((r) => { setRows(r.data.results ?? r.data); setErr('') })
    .catch(() => { setRows([]); setErr('load') })
  useEffect(() => { load() }, [url])
  return { rows, err, load, setErr }
}

function Ico({ d, w = 16 }) {
  return (
    <svg viewBox="0 0 24 24" width={w} height={w} fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{d}</svg>
  )
}
const I = {
  check: <polyline points="20 6 9 17 4 12" />,
  plus: <path d="M12 5v14M5 12h14" />,
  close: <path d="M18 6L6 18M6 6l12 12" />,
  edit: <path d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />,
  trash: <><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" /></>,
  doc: <><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="9" y1="13" x2="15" y2="13" /><line x1="9" y1="17" x2="13" y2="17" /></>,
  shield: <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />,
  users: <><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75" /></>,
  key: <><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 11-7.78 7.78 5.5 5.5 0 017.78-7.78zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3" /></>,
  eye: <><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z" /><circle cx="12" cy="12" r="3" /></>,
  eyeOff: <><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24" /><path d="M1 1l22 22" /></>,
}

const SHARED_CSS = `
.sm-head { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-start; justify-content: space-between; }
.sm-title-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.sm-count-badge { font-size: 11px; font-weight: 600; padding: 2px 10px; border-radius: 999px; background: color-mix(in srgb, var(--c-text-muted) 14%, transparent); color: var(--c-text-muted); white-space: nowrap; }
.sm-add { display: inline-flex; align-items: center; gap: 6px; flex-shrink: 0; }

.sm-wrap { overflow-x: auto; }
.sm-table { width: 100%; min-width: 620px; border-collapse: collapse; font-size: 13px; }
.sm-table thead th {
  text-align: start; font-weight: 600; font-size: 11.5px; text-transform: uppercase; letter-spacing: .03em;
  color: var(--c-text-muted); padding: 13px 18px; white-space: nowrap; border-bottom: 1px solid var(--c-border);
}
.sm-table td { padding: 13px 18px; vertical-align: middle; border-bottom: 1px solid var(--c-border); }
.sm-row:hover > td { background: color-mix(in srgb, var(--c-primary) 5%, transparent); }
.sm-c { text-align: center; }
.sm-mono { font-family: 'JetBrains Mono', ui-monospace, monospace; }
.sm-slug { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 12px; font-weight: 600; }
.sm-ok { display: inline-grid; place-items: center; width: 26px; height: 26px; border-radius: 8px; background: color-mix(in srgb, var(--c-success) 15%, transparent); color: var(--c-success); }
.sm-off { color: var(--c-text-muted); }

.sm-acts { display: inline-flex; gap: 6px; }
.sm-btn { padding: 5px 12px; border-radius: 9px; font-size: 12px; font-weight: 600; border: 1px solid var(--c-border); background: transparent; transition: .15s; white-space: nowrap; }
.sm-btn:hover { border-color: var(--c-primary); color: var(--c-primary); }
.sm-btn--del:hover { border-color: var(--c-danger); color: var(--c-danger); }

.sm-cnt-pill { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 12px; font-weight: 700; font-family: 'JetBrains Mono', monospace; background: color-mix(in srgb, var(--c-primary) 12%, transparent); color: var(--c-primary); }

.sm-name-dot { display: inline-flex; align-items: center; gap: 8px; }
.sm-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.sm-role-badge { display: inline-flex; align-items: center; gap: 5px; padding: 3px 10px; border-radius: 8px; font-size: 11.5px; font-weight: 600; border: 1px solid var(--c-border); color: var(--c-text-muted); }
.sm-role-badge.super { background: color-mix(in srgb, #D97706 14%, transparent); color: #D97706; border-color: color-mix(in srgb, #D97706 26%, transparent); }
.sm-av { width: 32px; height: 32px; border-radius: 9px; display: grid; place-items: center; font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 12px; background: color-mix(in srgb, var(--c-text-muted) 16%, transparent); color: var(--c-text); flex-shrink: 0; }
.sm-uname { display: flex; align-items: center; gap: 10px; }

.sm-kpis { display: grid; grid-template-columns: 1fr; gap: 14px; }
@media (min-width: 640px) { .sm-kpis { grid-template-columns: repeat(3, 1fr); } }
.sm-kpi { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.sm-kpi-label { font-size: 12px; font-weight: 600; color: var(--c-text-muted); }
.sm-kpi-val { font-size: 22px; font-weight: 800; margin-top: 4px; font-family: 'JetBrains Mono', ui-monospace, monospace; }
.sm-kpi-unit { font-size: 11px; font-weight: 500; color: var(--c-text-muted); font-family: inherit; }
.sm-kpi-ico { width: 42px; height: 42px; border-radius: 12px; display: grid; place-items: center; flex-shrink: 0; }

/* modal */
.sm-backdrop { position: fixed; inset: 0; z-index: 60; background: color-mix(in srgb, #0b1220 62%, transparent); backdrop-filter: blur(3px); display: flex; align-items: flex-start; justify-content: center; padding: 24px 16px; overflow-y: auto; }
.sm-modal { width: 100%; max-width: 720px; padding: 0; overflow: hidden; }
.sm-modal--sm { max-width: 560px; }
.sm-modal-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 18px 20px; border-bottom: 1px solid var(--c-border); }
.sm-modal-head h2 { display: flex; align-items: center; gap: 8px; }
.sm-modal-body { padding: 20px; display: flex; flex-direction: column; gap: 16px; }
.sm-modal-foot { display: flex; justify-content: flex-end; gap: 10px; padding: 14px 20px; border-top: 1px solid var(--c-border); }
.sm-modal-foot .btn-primary { display: inline-flex; align-items: center; gap: 6px; }
.sm-icon-btn { padding: 6px; border-radius: 9px; color: var(--c-text-muted); }
.sm-icon-btn:hover { color: var(--c-text); background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); }
.sm-grid2 { display: grid; grid-template-columns: 1fr; gap: 14px; }
@media (min-width: 560px) { .sm-grid2 { grid-template-columns: 1fr 1fr; } }
.sm-fld { display: flex; flex-direction: column; gap: 6px; }
.sm-fld .label { font-size: 12px; }
.sm-hint { font-size: 11px; color: var(--c-text-muted); }

.sm-lang-tabs { display: inline-flex; gap: 4px; padding: 3px; border-radius: 10px; background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); }
.sm-lang-tabs button { padding: 5px 14px; border-radius: 8px; font-size: 12px; font-weight: 600; color: var(--c-text-muted); }
.sm-lang-tabs button.on { background: var(--c-primary); color: #fff; }
.sm-editor-bar { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.sm-preview { min-height: 180px; padding: 14px; border-radius: 12px; border: 1px solid var(--c-border); background: color-mix(in srgb, var(--c-text-muted) 5%, transparent); white-space: pre-wrap; line-height: 1.8; font-size: 13px; }
.sm-body-area { width: 100%; min-height: 200px; resize: vertical; line-height: 1.8; font-family: inherit; }

.sm-status-box { display: flex; align-items: center; gap: 10px; }
.sm-status-box .label { margin: 0; font-size: 12px; }

.sm-perm-grid { display: grid; grid-template-columns: 1fr; gap: 8px; padding: 14px; border-radius: 12px; border: 1px solid var(--c-border); background: color-mix(in srgb, var(--c-text-muted) 5%, transparent); max-height: 320px; overflow-y: auto; }
@media (min-width: 560px) { .sm-perm-grid { grid-template-columns: 1fr 1fr; } }
.sm-perm { display: flex; align-items: flex-start; gap: 8px; font-size: 12.5px; cursor: pointer; }
.sm-perm code { font-size: 10.5px; color: var(--c-text-muted); }

.sm-pw { position: relative; }
.sm-pw .input { width: 100%; padding-inline-end: 40px; }
.sm-pw-eye { position: absolute; inset-inline-end: 10px; top: 50%; transform: translateY(-50%); color: var(--c-text-muted); }
.sm-pw-eye:hover { color: var(--c-text); }
.sm-toggle-row { display: flex; align-items: center; gap: 8px; font-size: 13px; }
`

/* ============================ Themes (unchanged behaviour) ============================ */
export function Themes() {
  const { t } = useI18n()
  const { rows, err, load } = useList('/admin/themes/')
  const [e2, setE2] = useState('')
  const activate = async (id) => {
    setE2('')
    try { await api.post(`/admin/themes/${id}/activate/`); load() } catch (e) { setE2(apiError(e)) }
  }
  if (!rows) return <div className="grid place-items-center py-16"><Spinner /></div>
  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold">{t('themes')}</h1>
      <Alert>{err ? t('load_error') : e2}</Alert>
      <DataTable rows={rows} empty={t('none_found')} columns={[
        { key: 'name', label: t('name') },
        { key: 'is_active', label: t('active'), render: (r) => (r.is_active ? '✓' : '—') },
        {
          key: 'act', label: '', render: (r) => (!r.is_active && (
            <button className="btn-ghost text-xs" onClick={() => activate(r.id)}>{t('activate')}</button>
          )),
        },
      ]} />
    </div>
  )
}

/* ================================ Pages — full CRUD ================================ */
const blankPage = { slug: '', title_fa: '', title_en: '', body_fa: '', body_en: '', is_active: true }

const P = {
  fa: {
    badge_active: '{n} صفحه فعال',
    subtitle: 'مدیریت قوانین، سؤالات متداول و محتوای راهنمای وب‌سایت و ربات تلگرام',
    c_slug: 'اسلاگ', c_title: 'عنوان', c_active: 'فعال', c_actions: 'عملیات',
    edit_title: 'ویرایش صفحه: {t}', new_title: 'ایجاد صفحهٔ جدید',
    modal_sub: 'تنظیم آدرس اسلاگ یکتا، عنوان‌ها و متن‌های چندزبانه',
    slug_hint: 'شناسهٔ URL اختصاصی صفحه (فقط حروف انگلیسی)',
    title_fa: 'عنوان (فارسی)', title_en: 'عنوان (انگلیسی)',
    body: 'متن محتوا', md_hint: 'پشتیبانی از متن ساده و Markdown',
    write: 'ویرایش', preview: 'پیش‌نمایش',
    apply_note: 'تغییرات بلافاصله روی ربات و صفحهٔ وب اعمال می‌شوند.',
    none: 'صفحه‌ای ثبت نشده', empty_preview: 'متنی برای پیش‌نمایش وارد نشده است.',
  },
  en: {
    badge_active: '{n} active pages',
    subtitle: 'Manage the rules, FAQ and help content shown on the website and the Telegram bot',
    c_slug: 'Slug', c_title: 'Title', c_active: 'Active', c_actions: 'Actions',
    edit_title: 'Edit page: {t}', new_title: 'Create new page',
    modal_sub: 'Set the unique slug, titles and multilingual content',
    slug_hint: "The page's unique URL identifier (latin letters only)",
    title_fa: 'Title (fa)', title_en: 'Title (en)',
    body: 'Content body', md_hint: 'Plain text and Markdown supported',
    write: 'Write', preview: 'Preview',
    apply_note: 'Changes apply to the bot and web page immediately.',
    none: 'No pages yet', empty_preview: 'Nothing to preview yet.',
  },
}

function PageModal({ row, s, t, onClose, onSaved }) {
  const editing = !!row
  const [f, setF] = useState(() => (row ? { ...blankPage, ...row } : { ...blankPage }))
  const [tab, setTab] = useState('fa')
  const [preview, setPreview] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const bodyKey = tab === 'fa' ? 'body_fa' : 'body_en'

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr('')
    try {
      if (editing) await api.patch(`/admin/pages/${row.id}/`, f)
      else await api.post('/admin/pages/', f)
      onSaved()
    } catch (e2) { setErr(apiError(e2)) } finally { setBusy(false) }
  }

  return (
    <div className="sm-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form className="sm-modal card" onSubmit={submit} role="dialog" aria-modal="true">
        <div className="sm-modal-head">
          <div>
            <h2 className="font-bold"><span style={{ color: 'var(--c-primary)' }}><Ico d={I.doc} w={18} /></span>
              {editing ? s.edit_title.replace('{t}', row.title_fa || row.slug) : s.new_title}</h2>
            <p className="sm-hint mt-1">{s.modal_sub}</p>
          </div>
          <div className="flex items-center gap-3">
            <span className="sm-status-box"><span className="label">{t('active')}</span>
              <Toggle checked={f.is_active} onChange={(v) => setF({ ...f, is_active: v })} label={t('active')} /></span>
            <button type="button" className="sm-icon-btn" onClick={onClose} aria-label={t('cancel')}><Ico d={I.close} /></button>
          </div>
        </div>

        <div className="sm-modal-body">
          <Alert>{err}</Alert>
          <label className="sm-fld">
            <span className="label">{s.c_slug} <span className="sm-hint">— {s.slug_hint}</span></span>
            <input className="input sm-mono" dir="ltr" required disabled={editing} placeholder="e.g. faq"
              value={f.slug} onChange={(e) => setF({ ...f, slug: e.target.value })} />
          </label>

          <div className="sm-grid2">
            <label className="sm-fld">
              <span className="label">{s.title_fa}</span>
              <input className="input" value={f.title_fa} onChange={(e) => setF({ ...f, title_fa: e.target.value })} />
            </label>
            <label className="sm-fld">
              <span className="label">{s.title_en}</span>
              <input className="input" dir="ltr" value={f.title_en} onChange={(e) => setF({ ...f, title_en: e.target.value })} />
            </label>
          </div>

          <div className="sm-fld">
            <div className="sm-editor-bar">
              <span className="label">{s.body} <span className="sm-hint">— {s.md_hint}</span></span>
              <div className="flex items-center gap-2">
                <div className="sm-lang-tabs">
                  <button type="button" className={tab === 'fa' ? 'on' : ''} onClick={() => setTab('fa')}>فارسی</button>
                  <button type="button" className={tab === 'en' ? 'on' : ''} onClick={() => setTab('en')}>English</button>
                </div>
                <div className="sm-lang-tabs">
                  <button type="button" className={!preview ? 'on' : ''} onClick={() => setPreview(false)}>{s.write}</button>
                  <button type="button" className={preview ? 'on' : ''} onClick={() => setPreview(true)}>{s.preview}</button>
                </div>
              </div>
            </div>
            {preview ? (
              <div className="sm-preview" dir={tab === 'fa' ? 'rtl' : 'ltr'}>
                {f[bodyKey]?.trim() || <span className="sm-hint">{s.empty_preview}</span>}
              </div>
            ) : (
              <textarea className="input sm-body-area" dir={tab === 'fa' ? 'rtl' : 'ltr'} rows={9}
                value={f[bodyKey]} onChange={(e) => setF({ ...f, [bodyKey]: e.target.value })} />
            )}
          </div>

          <p className="sm-hint flex items-center gap-1.5">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" /><path d="M12 16v-4M12 8h.01" />
            </svg>{s.apply_note}
          </p>
        </div>

        <div className="sm-modal-foot">
          <button type="button" className="btn-ghost text-sm" onClick={onClose}>{t('cancel')}</button>
          <button type="submit" className="btn-primary text-sm" disabled={busy}>
            {busy ? '…' : <><Ico d={I.check} w={15} /> {t('save')}</>}
          </button>
        </div>
      </form>
    </div>
  )
}

export function Pages() {
  const { t, lang } = useI18n()
  const s = P[lang] || P.fa
  const { rows, err, load } = useList('/admin/pages/')
  const [modal, setModal] = useState(null) // { row } | { row:null }
  const [e2, setE2] = useState('')
  const [toast, setToast] = useState('')

  const del = async (r) => {
    if (!confirm(t('delete_confirm'))) return
    try { await api.delete(`/admin/pages/${r.id}/`); load() } catch (e) { setE2(apiError(e)) }
  }
  const onSaved = () => { setModal(null); load(); setToast(t('saved')); setTimeout(() => setToast(''), 2000) }
  const activeCount = useMemo(() => (rows || []).filter((r) => r.is_active).length, [rows])

  if (!rows) return <div className="grid place-items-center py-16"><Spinner /></div>
  return (
    <div className="space-y-5">
      <style>{SHARED_CSS}</style>

      <div className="sm-head">
        <div>
          <div className="sm-title-row">
            <h1 className="text-lg font-bold">{t('pages')}</h1>
            <span className="sm-count-badge">{s.badge_active.replace('{n}', digits(activeCount, lang))}</span>
          </div>
          <p className="text-sm text-muted mt-1">{s.subtitle}</p>
        </div>
        <button className="btn-primary text-sm sm-add" onClick={() => setModal({ row: null })}>
          <Ico d={I.plus} w={15} /> {t('create')}
        </button>
      </div>

      <Alert>{err ? t('load_error') : e2}</Alert>
      {toast && <Alert kind="success">{toast}</Alert>}

      {rows.length === 0 ? (
        <div className="card text-center text-muted">{s.none}</div>
      ) : (
        <div className="card p-0 sm-wrap">
          <table className="sm-table">
            <thead>
              <tr><th>{s.c_slug}</th><th>{s.c_title}</th><th className="sm-c">{s.c_active}</th><th className="sm-c">{s.c_actions}</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="sm-row">
                  <td><span className="sm-slug" dir="ltr">{r.slug}</span></td>
                  <td>{(lang === 'fa' ? r.title_fa : r.title_en) || r.title_fa || '—'}</td>
                  <td className="sm-c">{r.is_active ? <span className="sm-ok"><Ico d={I.check} w={14} /></span> : <span className="sm-off">—</span>}</td>
                  <td className="sm-c">
                    <div className="sm-acts">
                      <button className="sm-btn" onClick={() => setModal({ row: r })}>{t('edit')}</button>
                      <button className="sm-btn sm-btn--del" onClick={() => del(r)}>{t('delete')}</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modal && <PageModal row={modal.row} s={s} t={t} onClose={() => setModal(null)} onSaved={onSaved} />}
    </div>
  )
}

/* ================= Roles + Staff accounts — full CRUD, wired to RBAC ================= */
const blankRole = { name: '', description: '', permission_codes: [] }
const blankStaff = { username: '', password: '', role: '', is_active: true, is_superadmin: false }

const R = {
  fa: {
    kpi_roles: 'نقش‌های تعریف‌شده', kpi_roles_u: 'نقش',
    kpi_staff: 'حساب‌های فعال کارکنان', kpi_staff_u: 'کاربر',
    kpi_perms: 'مجموع دسترسی‌های سیستمی', kpi_perms_u: 'ماژول و متد',
    roles_h: 'نقش‌ها', staff_h: 'حساب‌های کارکنان',
    c_name: 'نام', c_desc: 'توضیح', c_perms: 'دسترسی‌ها', c_role: 'نقش', c_active: 'فعال', c_actions: 'عملیات', c_username: 'نام کاربری',
    role_modal_new: 'ایجاد نقش دسترسی جدید', role_modal_edit: 'ویرایش نقش: {n}',
    staff_modal_new: 'افزودن کارمند جدید', staff_modal_edit: 'ویرایش کارمند: {n}',
    pick_perms: 'انتخاب دسترسی‌های مجاز',
    pw_edit_hint: '(فقط برای تغییر وارد شود)',
    super: 'ابرمدیر', super_hint: 'دسترسی کامل به همهٔ بخش‌ها',
    none_roles: 'نقشی تعریف نشده', none_staff: 'کارمندی ثبت نشده',
  },
  en: {
    kpi_roles: 'Roles defined', kpi_roles_u: 'roles',
    kpi_staff: 'Active staff accounts', kpi_staff_u: 'users',
    kpi_perms: 'Total system permissions', kpi_perms_u: 'modules & methods',
    roles_h: 'Roles', staff_h: 'Staff accounts',
    c_name: 'Name', c_desc: 'Description', c_perms: 'Permissions', c_role: 'Role', c_active: 'Active', c_actions: 'Actions', c_username: 'Username',
    role_modal_new: 'Create a new access role', role_modal_edit: 'Edit role: {n}',
    staff_modal_new: 'Add a new staff member', staff_modal_edit: 'Edit staff: {n}',
    pick_perms: 'Select the allowed permissions',
    pw_edit_hint: '(fill only to change)',
    super: 'Superadmin', super_hint: 'Full access to every section',
    none_roles: 'No roles defined', none_staff: 'No staff accounts yet',
  },
}

const DOT = ['#11AB53', '#1464BA', '#0891B2', '#7C3AED', '#D97706', '#DB2777']
const initials = (u = '') => (String(u).replace(/[^a-zA-Z0-9]/g, '').slice(0, 2) || '?').toUpperCase()

function Kpi({ label, value, unit, tone, icon, lang }) {
  return (
    <div className="card sm-kpi">
      <div>
        <p className="sm-kpi-label">{label}</p>
        <p className="sm-kpi-val">{value == null ? '—' : digits(value, lang)}{unit ? <span className="sm-kpi-unit"> {unit}</span> : null}</p>
      </div>
      <span className="sm-kpi-ico" style={{ background: `color-mix(in srgb, ${tone} 13%, transparent)`, color: tone }}>{icon}</span>
    </div>
  )
}

function RoleModal({ row, perms, s, t, lang, onClose, onSaved }) {
  const editing = !!row
  const [f, setF] = useState(() => (row
    ? { ...row, permission_codes: [...(row.permission_codes || [])] }
    : { ...blankRole }))
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const toggle = (code) => setF((r) => ({
    ...r,
    permission_codes: r.permission_codes.includes(code)
      ? r.permission_codes.filter((c) => c !== code) : [...r.permission_codes, code],
  }))
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr('')
    try {
      if (editing) await api.patch(`/admin/roles/${row.id}/`, f)
      else await api.post('/admin/roles/', f)
      onSaved()
    } catch (e2) { setErr(apiError(e2)) } finally { setBusy(false) }
  }
  return (
    <div className="sm-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form className="sm-modal card" onSubmit={submit} role="dialog" aria-modal="true">
        <div className="sm-modal-head">
          <h2 className="font-bold"><span style={{ color: 'var(--c-primary)' }}><Ico d={I.shield} w={18} /></span>
            {editing ? s.role_modal_edit.replace('{n}', row.name) : s.role_modal_new}</h2>
          <button type="button" className="sm-icon-btn" onClick={onClose} aria-label={t('cancel')}><Ico d={I.close} /></button>
        </div>
        <div className="sm-modal-body">
          <Alert>{err}</Alert>
          <div className="sm-grid2">
            <label className="sm-fld">
              <span className="label">{s.c_name}</span>
              <input className="input" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
            </label>
            <label className="sm-fld">
              <span className="label">{s.c_desc}</span>
              <input className="input" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
            </label>
          </div>
          <div className="sm-fld">
            <span className="label">{s.pick_perms} <span className="sm-hint">({digits(f.permission_codes.length, lang)}/{digits(perms.length, lang)})</span></span>
            <div className="sm-perm-grid">
              {perms.map((p) => (
                <label key={p.code} className="sm-perm">
                  <input type="checkbox" checked={f.permission_codes.includes(p.code)} onChange={() => toggle(p.code)} />
                  <span>{p.name}<br /><code dir="ltr">{p.code}</code></span>
                </label>
              ))}
            </div>
          </div>
        </div>
        <div className="sm-modal-foot">
          <button type="button" className="btn-ghost text-sm" onClick={onClose}>{t('cancel')}</button>
          <button type="submit" className="btn-primary text-sm" disabled={busy}>{busy ? '…' : <><Ico d={I.check} w={15} /> {t('save')}</>}</button>
        </div>
      </form>
    </div>
  )
}

function StaffModal({ row, roles, s, t, onClose, onSaved }) {
  const editing = !!row
  const [f, setF] = useState(() => (row
    ? { id: row.id, username: row.username, password: '', role: row.role || '', is_active: row.is_active, is_superadmin: row.is_superadmin }
    : { ...blankStaff }))
  const [showPw, setShowPw] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr('')
    const body = { ...f }
    if (editing && !body.password) delete body.password
    if (!body.role) body.role = null
    try {
      if (editing) await api.patch(`/admin/staff/${row.id}/`, body)
      else await api.post('/admin/staff/', body)
      onSaved()
    } catch (e2) { setErr(apiError(e2)) } finally { setBusy(false) }
  }
  return (
    <div className="sm-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form className="sm-modal sm-modal--sm card" onSubmit={submit} role="dialog" aria-modal="true">
        <div className="sm-modal-head">
          <h2 className="font-bold"><span style={{ color: 'var(--c-primary)' }}><Ico d={I.users} w={18} /></span>
            {editing ? s.staff_modal_edit.replace('{n}', row.username) : s.staff_modal_new}</h2>
          <button type="button" className="sm-icon-btn" onClick={onClose} aria-label={t('cancel')}><Ico d={I.close} /></button>
        </div>
        <div className="sm-modal-body">
          <Alert>{err}</Alert>
          <label className="sm-fld">
            <span className="label">{s.c_username}</span>
            <input className="input sm-mono" dir="ltr" required disabled={editing}
              value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} />
          </label>
          <div className="sm-fld">
            <span className="label">{t('password')} {editing && <span className="sm-hint">{s.pw_edit_hint}</span>}</span>
            <div className="sm-pw">
              <input className="input" type={showPw ? 'text' : 'password'} dir="ltr" minLength={8} required={!editing}
                value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
              <button type="button" className="sm-pw-eye" onClick={() => setShowPw((v) => !v)}
                aria-label={t(showPw ? 'hide_password' : 'show_password')}><Ico d={showPw ? I.eyeOff : I.eye} w={15} /></button>
            </div>
          </div>
          <label className="sm-fld">
            <span className="label">{s.c_role}</span>
            <select className="input" value={f.role || ''} onChange={(e) => setF({ ...f, role: e.target.value })} disabled={f.is_superadmin}>
              <option value="">— {t('select_role')} —</option>
              {roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select>
          </label>
          <div className="flex flex-col gap-2.5">
            <label className="sm-toggle-row">
              <Toggle checked={f.is_active} onChange={(v) => setF({ ...f, is_active: v })} label={t('active')} /> {t('active')}
            </label>
            <label className="sm-toggle-row">
              <Toggle checked={f.is_superadmin} onChange={(v) => setF({ ...f, is_superadmin: v })} label={s.super} />
              <span>{s.super} <span className="sm-hint">— {s.super_hint}</span></span>
            </label>
          </div>
        </div>
        <div className="sm-modal-foot">
          <button type="button" className="btn-ghost text-sm" onClick={onClose}>{t('cancel')}</button>
          <button type="submit" className="btn-primary text-sm" disabled={busy}>{busy ? '…' : <><Ico d={I.check} w={15} /> {t('save')}</>}</button>
        </div>
      </form>
    </div>
  )
}

export function Roles() {
  const { t, lang } = useI18n()
  const s = R[lang] || R.fa
  const roles = useList('/admin/roles/?limit=200')
  const staff = useList('/admin/staff/?limit=200')
  const perms = useList('/admin/permissions/?limit=200')
  const [roleModal, setRoleModal] = useState(null)
  const [staffModal, setStaffModal] = useState(null)
  const [err, setErr] = useState('')
  const [toast, setToast] = useState('')

  const flash = () => { setToast(t('saved')); setTimeout(() => setToast(''), 2000) }
  const delRole = async (r) => {
    if (!confirm(t('delete_confirm'))) return
    try { await api.delete(`/admin/roles/${r.id}/`); roles.load() } catch (e) { setErr(apiError(e)) }
  }
  const delStaff = async (r) => {
    if (!confirm(t('delete_confirm'))) return
    try { await api.delete(`/admin/staff/${r.id}/`); staff.load() } catch (e) { setErr(apiError(e)) }
  }

  if (!roles.rows || !staff.rows || !perms.rows) return <div className="grid place-items-center py-16"><Spinner /></div>

  const activeStaff = staff.rows.filter((x) => x.is_active).length

  return (
    <div className="space-y-6">
      <style>{SHARED_CSS}</style>
      <Alert>{(roles.err || staff.err || perms.err) ? t('load_error') : err}</Alert>
      {toast && <Alert kind="success">{toast}</Alert>}

      <div className="sm-kpis">
        <Kpi label={s.kpi_roles} value={roles.rows.length} unit={s.kpi_roles_u} tone="#1464BA" icon={<Ico d={I.shield} w={22} />} lang={lang} />
        <Kpi label={s.kpi_staff} value={activeStaff} unit={s.kpi_staff_u} tone="#11AB53" icon={<Ico d={I.users} w={22} />} lang={lang} />
        <Kpi label={s.kpi_perms} value={perms.rows.length} unit={s.kpi_perms_u} tone="#7C3AED" icon={<Ico d={I.key} w={22} />} lang={lang} />
      </div>

      {/* ---- roles ---- */}
      <section className="space-y-3">
        <div className="sm-head">
          <h2 className="text-lg font-bold">{s.roles_h}</h2>
          <button className="btn-primary text-sm sm-add" onClick={() => setRoleModal({ row: null })}>
            <Ico d={I.plus} w={15} /> {t('new_role')}
          </button>
        </div>
        {roles.rows.length === 0 ? (
          <div className="card text-center text-muted">{s.none_roles}</div>
        ) : (
          <div className="card p-0 sm-wrap">
            <table className="sm-table">
              <thead><tr><th>{s.c_name}</th><th>{s.c_desc}</th><th className="sm-c">{s.c_perms}</th><th className="sm-c">{s.c_actions}</th></tr></thead>
              <tbody>
                {roles.rows.map((r, i) => (
                  <tr key={r.id} className="sm-row">
                    <td><span className="sm-name-dot"><span className="sm-dot" style={{ background: DOT[i % DOT.length] }} /><b>{r.name}</b></span></td>
                    <td className="text-muted">{r.description || '—'}</td>
                    <td className="sm-c"><span className="sm-cnt-pill">{digits((r.permission_codes || []).length, lang)}</span></td>
                    <td className="sm-c">
                      <div className="sm-acts">
                        <button className="sm-btn" onClick={() => setRoleModal({ row: r })}>{t('edit')}</button>
                        <button className="sm-btn sm-btn--del" onClick={() => delRole(r)}>{t('delete')}</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ---- staff ---- */}
      <section className="space-y-3">
        <div className="sm-head">
          <h2 className="text-lg font-bold">{s.staff_h}</h2>
          <button className="btn-primary text-sm sm-add" onClick={() => setStaffModal({ row: null })}>
            <Ico d={I.plus} w={15} /> {t('new_staff')}
          </button>
        </div>
        {staff.rows.length === 0 ? (
          <div className="card text-center text-muted">{s.none_staff}</div>
        ) : (
          <div className="card p-0 sm-wrap">
            <table className="sm-table">
              <thead><tr><th>{s.c_username}</th><th className="sm-c">{s.c_role}</th><th className="sm-c">{s.c_active}</th><th className="sm-c">{s.c_actions}</th></tr></thead>
              <tbody>
                {staff.rows.map((r) => (
                  <tr key={r.id} className="sm-row">
                    <td>
                      <span className="sm-uname">
                        <span className="sm-av">{initials(r.username)}</span>
                        <b className="sm-mono" dir="ltr">{r.username}</b>
                      </span>
                    </td>
                    <td className="sm-c">
                      {r.is_superadmin
                        ? <span className="sm-role-badge super">★ {s.super}</span>
                        : <span className="sm-role-badge">{r.role_name || '—'}</span>}
                    </td>
                    <td className="sm-c">{r.is_active ? <span className="sm-ok"><Ico d={I.check} w={14} /></span> : <span className="sm-off">—</span>}</td>
                    <td className="sm-c">
                      <div className="sm-acts">
                        <button className="sm-btn" onClick={() => setStaffModal({ row: r })}>{t('edit')}</button>
                        <button className="sm-btn sm-btn--del" onClick={() => delStaff(r)}>{t('delete')}</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {roleModal && <RoleModal row={roleModal.row} perms={perms.rows} s={s} t={t} lang={lang}
        onClose={() => setRoleModal(null)} onSaved={() => { setRoleModal(null); roles.load(); flash() }} />}
      {staffModal && <StaffModal row={staffModal.row} roles={roles.rows} s={s} t={t}
        onClose={() => setStaffModal(null)} onSaved={() => { setStaffModal(null); staff.load(); flash() }} />}
    </div>
  )
}
