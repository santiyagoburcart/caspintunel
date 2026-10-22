import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { Spinner, Toggle } from '../components/ui'
import { useConfirm } from '../components/ConfirmDialog'
import { useToast } from '../components/Toast'
import { copyToClipboard } from '../lib/clipboard'
import { Ic } from '../components/AgencyIcons'

// Create / edit / delete PasarGuard admins (backend: apps/agency/admin_crud.py).
// The field list is the live panel's AdminCreate / AdminModify schema (PasarGuard 5.4):
// roles replaced "sudo"; allowed groups / templates come with the role.
const F = {
  fa: {
    new_title: 'ساخت ادمین جدید', new_sub: 'ادمین نماینده روی پنل پاسارگاد ساخته می‌شود و بلافاصله در پنل نمایندگی دیده می‌شود.',
    back: 'بازگشت به فهرست', panel: 'پنل', panel_hint: 'ادمین روی کدام پنل ساخته شود؟', not_tracked: 'این پنل در پنل نمایندگی همگام نمی‌شود — ادمین فقط روی آن پنل ساخته می‌شود.',
    sec_account: 'حساب', sec_role: 'نقش و دسترسی', sec_contact: 'ارتباط و اعلان‌ها', sec_sub: 'اشتراک', sec_limit: 'سقف و حسابداری',
    sec_adv: 'محدودیت‌های اختصاصی (اختیاری)', sec_vars: 'متغیرهای سفارشی', sec_note: 'یادداشت',
    username: 'نام کاربری', username_hint: '3 تا 32 حرف انگلیسی، عدد یا _ . @ -', password: 'رمز عبور', gen: 'ساخت رمز', show: 'نمایش', hide: 'پنهان',
    role: 'نقش', role_pick: '— یک نقش انتخاب کنید —', owner_role: 'مالک (دسترسی کامل، مثل sudo)', all_groups: 'همهٔ گروه‌ها',
    groups: 'گروه‌های مجاز', templates: 'قالب‌های مجاز', role_limits: 'محدودیت‌های نقش', status: 'وضعیت', st_active: 'فعال', st_disabled: 'غیرفعال',
    telegram_id: 'شناسهٔ عددی تلگرام', discord: 'Discord webhook', support_url: 'لینک پشتیبانی', notify: 'اعلان‌های پنل برای این ادمین',
    n_create: 'ساخت کاربر', n_modify: 'ویرایش کاربر', n_delete: 'حذف کاربر', n_status_change: 'تغییر وضعیت', n_reset_data_usage: 'ریست مصرف',
    n_data_reset_by_next: 'ریست با پلن بعدی', n_subscription_revoked: 'باطل شدن اشتراک',
    sub_domain: 'دامنهٔ اشتراک', profile_title: 'عنوان پروفایل', sub_template: 'قالب اشتراک',
    limit: 'سقف اولیه', limit_hint: 'خالی یا 0 = نامحدود', unit: 'واحد', price: 'قیمت هر گیگ (تومان)', price_hint: 'اختیاری — شارژ حساب = حجم × قیمت',
    charge: 'شارژ حساب', group: 'افزودن به گروه', no_group: '— بدون گروه —',
    l_max_users: 'حداکثر کاربر', l_data_limit_min: 'حداقل حجم کاربر (بایت)', l_data_limit_max: 'حداکثر حجم کاربر (بایت)', l_expire_min: 'حداقل مدت (ثانیه)',
    l_expire_max: 'حداکثر مدت (ثانیه)', l_min_hwid_per_user: 'حداقل دستگاه هر کاربر', l_max_hwid_per_user: 'حداکثر دستگاه هر کاربر',
    l_on_hold_timeout_min: 'حداقل زمان انتظار اتصال', l_on_hold_timeout_max: 'حداکثر زمان انتظار اتصال', adv_hint: 'خالی = همان محدودیت نقش',
    var_key: 'کلید', var_value: 'مقدار', var_add: 'افزودن متغیر', note: 'یادداشت داخلی', create: 'ساخت ادمین', creating: 'در حال ساخت…',
    done_title: 'ادمین ساخته شد', send_title: 'ارسال به نماینده', send_once: 'رمز فقط همین یک بار نمایش داده می‌شود — همین حالا کپی کنید.',
    portal: 'پرتال', copy: 'کپی', copy_all: 'کپی پیام کامل', copied: 'کپی شد', open_admin: 'مشاهدهٔ ادمین', another: 'ساخت ادمین دیگر',
    msg_tpl: 'پرتال نمایندگی:\n{url}\nنام کاربری: {u}\nرمز عبور: {p}', charged: 'شارژ ثبت‌شده', not_synced: 'تا همگام‌سازی بعدی، اعداد مصرف صفر نمایش داده می‌شوند.',
    // settings tab
    set_title: 'تنظیمات ادمین روی پنل', set_sub: 'فقط فیلدهای تغییرکرده به پنل فرستاده می‌شوند.', save: 'ذخیرهٔ تغییرات', saving: 'در حال ذخیره…', no_change: 'تغییری نداده‌اید',
    pw_reset: 'تغییر رمز عبور', pw_new: 'رمز جدید', pw_do: 'ثبت رمز جدید', pw_done: 'رمز جدید — آن را برای نماینده بفرستید',
    danger: 'منطقهٔ خطر', del: 'حذف ادمین از پنل', del_d: 'ادمین روی پنل پاسارگاد حذف می‌شود. صورت‌حساب و سوابق حسابداری او اینجا باقی می‌ماند.',
    del_type: 'برای تأیید، نام کاربری را دقیقاً بنویسید:', del_mismatch: 'نام کاربری درست وارد نشده است', not_on_panel: 'این ادمین روی پنل پیدا نشد.',
    usage_note: 'سقف و فعال/غیرفعال‌سازی در «محدودیت‌ها و عملیات» است.',
  },
  en: {
    new_title: 'New admin', new_sub: 'Creates a reseller admin on the PasarGuard panel; it shows up in the Agency panel right away.',
    back: 'Back to the list', panel: 'Panel', panel_hint: 'Which panel to create the admin on?', not_tracked: 'This panel is not synced by the Agency panel — the admin is only created on that panel.',
    sec_account: 'Account', sec_role: 'Role & access', sec_contact: 'Contact & notifications', sec_sub: 'Subscription', sec_limit: 'Limit & accounting',
    sec_adv: 'Own limits (optional)', sec_vars: 'Custom variables', sec_note: 'Note',
    username: 'Username', username_hint: '3–32 letters, digits or _ . @ -', password: 'Password', gen: 'Generate', show: 'Show', hide: 'Hide',
    role: 'Role', role_pick: '— pick a role —', owner_role: 'Owner (full access, like sudo)', all_groups: 'All groups',
    groups: 'Allowed groups', templates: 'Allowed templates', role_limits: 'Role limits', status: 'Status', st_active: 'Active', st_disabled: 'Disabled',
    telegram_id: 'Telegram numeric ID', discord: 'Discord webhook', support_url: 'Support URL', notify: 'Panel notifications for this admin',
    n_create: 'User created', n_modify: 'User modified', n_delete: 'User deleted', n_status_change: 'Status change', n_reset_data_usage: 'Usage reset',
    n_data_reset_by_next: 'Reset by next plan', n_subscription_revoked: 'Subscription revoked',
    sub_domain: 'Subscription domain', profile_title: 'Profile title', sub_template: 'Subscription template',
    limit: 'Initial limit', limit_hint: 'empty or 0 = unlimited', unit: 'Unit', price: 'Price per GB (Toman)', price_hint: 'optional — charge = volume × price',
    charge: 'Account charge', group: 'Add to group', no_group: '— no group —',
    l_max_users: 'Max users', l_data_limit_min: 'Min user data (bytes)', l_data_limit_max: 'Max user data (bytes)', l_expire_min: 'Min duration (s)',
    l_expire_max: 'Max duration (s)', l_min_hwid_per_user: 'Min devices per user', l_max_hwid_per_user: 'Max devices per user',
    l_on_hold_timeout_min: 'Min on-hold timeout', l_on_hold_timeout_max: 'Max on-hold timeout', adv_hint: 'empty = the role limit',
    var_key: 'Key', var_value: 'Value', var_add: 'Add variable', note: 'Internal note', create: 'Create admin', creating: 'Creating…',
    done_title: 'Admin created', send_title: 'Send to reseller', send_once: 'The password is shown only this once — copy it now.',
    portal: 'Portal', copy: 'Copy', copy_all: 'Copy full message', copied: 'Copied', open_admin: 'Open the admin', another: 'Create another',
    msg_tpl: 'Reseller portal:\n{url}\nUsername: {u}\nPassword: {p}', charged: 'Charge recorded', not_synced: 'Usage numbers show 0 until the next sync.',
    set_title: 'Admin settings on the panel', set_sub: 'Only changed fields are sent to the panel.', save: 'Save changes', saving: 'Saving…', no_change: 'Nothing changed',
    pw_reset: 'Change password', pw_new: 'New password', pw_do: 'Set new password', pw_done: 'New password — send it to the reseller',
    danger: 'Danger zone', del: 'Delete the admin from the panel', del_d: 'The admin is deleted on PasarGuard. Their statement and accounting history stay here.',
    del_type: 'To confirm, type the username exactly:', del_mismatch: 'The username does not match', not_on_panel: 'This admin was not found on the panel.',
    usage_note: 'Limit and enable / disable are under “Limits & actions”.',
  },
}
const GB = 1024 ** 3
const NOTIFY = ['create', 'modify', 'delete', 'status_change', 'reset_data_usage', 'data_reset_by_next', 'subscription_revoked']
const LIMITS = ['max_users', 'data_limit_min', 'data_limit_max', 'expire_min', 'expire_max', 'min_hwid_per_user', 'max_hwid_per_user', 'on_hold_timeout_min', 'on_hold_timeout_max']
const useF = () => { const { lang } = useI18n(); return [F[lang] || F.fa, lang] }

export function genPassword(n = 16) {
  const abc = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'
  for (;;) {
    const a = new Uint32Array(n)
    crypto.getRandomValues(a)
    const pw = Array.from(a, (x) => abc[x % abc.length]).join('')
    if (/\d/.test(pw) && /[A-Z]/.test(pw) && /[a-z]/.test(pw)) return pw
  }
}

function Sec({ icon, title, children, hint }) {
  return (
    <section className="card ag-card af-sec">
      <h3 className="af-sec-h"><Ic n={icon} size={15} />{title}</h3>
      {hint && <p className="af-hint">{hint}</p>}
      <div className="af-grid">{children}</div>
    </section>
  )
}
function Fld({ label, hint, wide, err, children }) {
  return (
    <label className={'af-fld' + (wide ? ' af-wide' : '') + (err ? ' af-err' : '')}>
      <span className="label">{label}</span>
      {children}
      {(err || hint) && <span className={err ? 'af-err-t' : 'af-hint'}>{err || hint}</span>}
    </label>
  )
}

export function PasswordInput({ value, onChange, s, autoFocus }) {
  const [show, setShow] = useState(false)
  return (
    <div className="af-pw">
      <input className="input" dir="ltr" type={show ? 'text' : 'password'} autoComplete="new-password" minLength={8}
        value={value} onChange={(e) => onChange(e.target.value)} autoFocus={autoFocus} />
      <button type="button" className="af-pw-b" onClick={() => setShow((v) => !v)}>{show ? s.hide : s.show}</button>
      <button type="button" className="af-pw-b" onClick={() => { onChange(genPassword()); setShow(true) }}><Ic n="reset" size={13} />{s.gen}</button>
    </div>
  )
}

function RoleInfo({ role, s }) {
  if (!role) return null
  const lim = Object.entries(role.limits || {})
  return (
    <div className="af-role af-wide">
      {role.is_owner && <span className="af-chip af-chip--owner">★ {s.owner_role}</span>}
      <span className="af-role-row"><b>{s.groups}:</b> {role.all_groups ? s.all_groups : (role.groups.length ? role.groups.join('، ') : '—')}</span>
      {role.templates.length > 0 && <span className="af-role-row"><b>{s.templates}:</b> {role.templates.join('، ')}</span>}
      {lim.length > 0 && <span className="af-role-row"><b>{s.role_limits}:</b> <bdi dir="ltr">{lim.map(([k, v]) => `${k}=${v}`).join(' · ')}</bdi></span>}
    </div>
  )
}

/** fields shared by create + settings (state object `f`, setter `set`) */
function AdminFields({ f, set, opts, s, errs }) {
  const role = opts?.roles?.find((r) => String(r.id) === String(f.role_id))
  return (
    <>
      <Sec icon="shield" title={s.sec_role}>
        <Fld label={s.role} err={errs.role_id}>
          <select className="input" value={f.role_id ?? ''} onChange={(e) => set('role_id', e.target.value)}>
            <option value="">{s.role_pick}</option>
            {(opts?.roles || []).map((r) => <option key={r.id} value={r.id}>{r.name}{r.is_owner ? ' ★' : ''}</option>)}
          </select>
        </Fld>
        <Fld label={s.status}>
          <select className="input" value={f.status || 'active'} onChange={(e) => set('status', e.target.value)}>
            <option value="active">{s.st_active}</option><option value="disabled">{s.st_disabled}</option>
          </select>
        </Fld>
        <RoleInfo role={role} s={s} />
      </Sec>
      <Sec icon="bell" title={s.sec_contact}>
        <Fld label={s.telegram_id} err={errs.telegram_id}><input className="input" dir="ltr" inputMode="numeric" value={f.telegram_id ?? ''} onChange={(e) => set('telegram_id', e.target.value.replace(/[^\d-]/g, ''))} /></Fld>
        <Fld label={s.discord} err={errs.discord_webhook}><input className="input" dir="ltr" type="url" placeholder="https://discord.com/api/webhooks/…" value={f.discord_webhook || ''} onChange={(e) => set('discord_webhook', e.target.value)} /></Fld>
        <Fld label={s.support_url} err={errs.support_url}><input className="input" dir="ltr" type="url" placeholder="https://t.me/…" value={f.support_url || ''} onChange={(e) => set('support_url', e.target.value)} /></Fld>
        <div className="af-wide">
          <span className="label">{s.notify}</span>
          <div className="af-toggles">
            {NOTIFY.map((k) => (
              <label key={k} className="af-toggle"><Toggle checked={f.notification_enable?.[k] !== false}
                onChange={(v) => set('notification_enable', { ...(f.notification_enable || {}), [k]: v })} label={s['n_' + k]} />{s['n_' + k]}</label>
            ))}
          </div>
        </div>
      </Sec>
      <Sec icon="link" title={s.sec_sub}>
        <Fld label={s.sub_domain} err={errs.sub_domain}><input className="input" dir="ltr" placeholder="sub.example.com" value={f.sub_domain || ''} onChange={(e) => set('sub_domain', e.target.value)} /></Fld>
        <Fld label={s.profile_title} err={errs.profile_title}><input className="input" value={f.profile_title || ''} onChange={(e) => set('profile_title', e.target.value)} /></Fld>
        <Fld label={s.sub_template} err={errs.sub_template}><input className="input" dir="ltr" value={f.sub_template || ''} onChange={(e) => set('sub_template', e.target.value)} /></Fld>
      </Sec>
      <details className="card ag-card af-sec af-details">
        <summary className="af-sec-h"><Ic n="gauge" size={15} />{s.sec_adv}</summary>
        <p className="af-hint">{s.adv_hint}</p>
        <div className="af-grid">
          {LIMITS.map((k) => (
            <Fld key={k} label={s['l_' + k]} err={errs[k]}>
              <input className="input" dir="ltr" inputMode="numeric" value={f.permission_overrides?.[k] ?? ''}
                onChange={(e) => set('permission_overrides', { ...(f.permission_overrides || {}), [k]: e.target.value.replace(/[^\d]/g, '') })} />
            </Fld>
          ))}
        </div>
      </details>
      <Sec icon="list" title={s.sec_vars}>
        <div className="af-wide af-vars">
          {(f.custom_variables || []).map((v, i) => (
            <div key={i} className="af-var">
              <input className="input" dir="ltr" placeholder={s.var_key} maxLength={64} value={v.key}
                onChange={(e) => set('custom_variables', f.custom_variables.map((x, j) => (j === i ? { ...x, key: e.target.value } : x)))} />
              <input className="input" dir="ltr" placeholder={s.var_value} maxLength={512} value={v.value}
                onChange={(e) => set('custom_variables', f.custom_variables.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))} />
              <button type="button" className="ag-act ag-act--sm" data-tone="danger" aria-label="remove"
                onClick={() => set('custom_variables', f.custom_variables.filter((_, j) => j !== i))}>✕</button>
            </div>
          ))}
          <button type="button" className="ag-act ag-act--sm" data-tone="neutral"
            onClick={() => set('custom_variables', [...(f.custom_variables || []), { key: '', value: '' }])}>+ {s.var_add}</button>
        </div>
      </Sec>
      <Sec icon="doc" title={s.sec_note}>
        <Fld label={s.note} wide err={errs.note}><textarea className="input" rows={3} maxLength={1000} value={f.note || ''} onChange={(e) => set('note', e.target.value)} /></Fld>
      </Sec>
    </>
  )
}

function useOptions(panel) {
  const [opts, setOpts] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    setOpts(null)
    api.get(`/admin/agency/panel-admins/options/${panel ? `?panel=${panel}` : ''}`)
      .then((r) => { setOpts(r.data); setErr('') }).catch((e) => setErr(e?.response?.data?.detail || 'error'))
  }, [panel])
  return [opts, err]
}
const fieldErrs = (e) => { const d = e?.response?.data; return d?.field ? { [d.field]: d.detail } : {} }

export function CredentialsCard({ s, username, password, extra }) {
  const toast = useToast()
  const [link, setLink] = useState('')
  useEffect(() => { api.get('/admin/agency/portal-link/').then((r) => setLink(r.data.url)).catch(() => {}) }, [])
  const copy = async (t) => { if (await copyToClipboard(t)) toast.success(s.copied) }
  const rows = [[s.portal, link], [s.username, username], ...(password ? [[s.password, password]] : [])]
  return (
    <section className="card ag-card af-cred">
      <h3 className="af-sec-h"><Ic n="link" size={15} />{s.send_title}</h3>
      {password && <p className="af-warn">⚠️ {s.send_once}</p>}
      {extra}
      <dl className="af-cred-rows">
        {rows.map(([k, v]) => (
          <div key={k}><dt>{k}</dt><dd><code dir="ltr">{v || '…'}</code>
            <button type="button" className="ag-act ag-act--sm" data-tone="neutral" disabled={!v} onClick={() => copy(v)}><Ic n="copy" size={13} />{s.copy}</button></dd></div>
        ))}
      </dl>
      {password && <button type="button" className="ag-act" data-tone="primary" disabled={!link}
        onClick={() => copy(s.msg_tpl.replace('{url}', link).replace('{u}', username).replace('{p}', password))}><Ic n="copy" />{s.copy_all}</button>}
    </section>
  )
}

const blank = () => ({ panel: '', username: '', password: genPassword(), role_id: '', status: 'active', telegram_id: '', discord_webhook: '',
  support_url: '', sub_domain: '', profile_title: '', sub_template: '', note: '', custom_variables: [],
  notification_enable: Object.fromEntries(NOTIFY.map((k) => [k, true])), permission_overrides: {},
  limit_value: '', limit_unit: 'GB', price_per_gb: '', group_id: '' })

// ================================ create page ===================================
export function AgencyAdminCreate({ Header }) {
  const [s] = useF()
  const { can } = useAuth()
  const go = useNavigate()
  const [f, setF] = useState(blank)
  const [opts, optErr] = useOptions(f.panel)
  const [busy, setBusy] = useState(false)
  const [errs, setErrs] = useState({})
  const [done, setDone] = useState(null)
  const set = (k, v) => { setF((x) => ({ ...x, [k]: v })); setErrs((e) => ({ ...e, [k]: undefined })) }
  const limitGb = (Number(f.limit_value) || 0) * (f.limit_unit === 'TB' ? 1024 : 1)
  const charge = f.price_per_gb && limitGb ? Math.round(limitGb * Number(f.price_per_gb)) : null
  const tracked = opts ? (opts.panels.find((p) => p.id === opts.panel) || {}).agency : true

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setErrs({})
    try {
      const body = { ...f, panel: f.panel || opts?.panel }
      if (!can('agency.accounting')) delete body.price_per_gb
      const r = await api.post('/admin/agency/panel-admins/', body)
      setDone(r.data)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (e2) { setErrs(fieldErrs(e2)) } finally { setBusy(false) }
  }

  if (done) {
    return (
      <div className="ag space-y-4">
        {Header}<style>{CSS}</style>
        <div className="af-done card ag-card">
          <span className="af-done-ico"><Ic n="check" size={26} /></span>
          <div><h2 className="font-bold text-lg">{s.done_title}: <bdi dir="ltr">{done.username}</bdi></h2>
            <p className="text-sm text-muted">{done.panel}{done.charge ? ` · ${s.charged}: ${Number(done.charge.amount).toLocaleString('en-US')} T` : ''}</p>
            {done.tracked && <p className="text-xs text-muted mt-1">{s.not_synced}</p>}</div>
        </div>
        <CredentialsCard s={s} username={done.username} password={done.password} />
        <div className="af-actions">
          {done.tracked && <Link className="btn-primary text-sm" to={`/agency/admins/${encodeURIComponent(done.username)}`}>{s.open_admin}</Link>}
          <button type="button" className="btn-ghost text-sm" onClick={() => { setDone(null); setF(blank()) }}>{s.another}</button>
        </div>
      </div>
    )
  }
  return (
    <form className="ag space-y-4 af" onSubmit={submit}>
      {Header}<style>{CSS}</style>
      <Link to="/agency/admins" className="ag-back">← {s.back}</Link>
      <div><h2 className="text-lg font-bold">{s.new_title}</h2><p className="text-sm text-muted mt-1">{s.new_sub}</p></div>
      {opts && opts.panels.length > 1 && (
        <Sec icon="server" title={s.panel} hint={s.panel_hint}>
          <div className="af-wide af-panels">
            {opts.panels.map((p) => (
              <button key={p.id} type="button" className={'af-panel' + (opts.panel === p.id ? ' on' : '')} onClick={() => set('panel', p.id)}>
                <b>{p.name}</b>{p.agency && <span className="af-chip">✓ Agency</span>}
              </button>
            ))}
          </div>
          {!tracked && <p className="af-warn af-wide">{s.not_tracked}</p>}
        </Sec>
      )}
      {optErr && <p className="af-warn">{optErr}</p>}
      {!opts && !optErr ? <div className="grid place-items-center py-10"><Spinner /></div> : opts && (
        <>
          <Sec icon="user" title={s.sec_account}>
            <Fld label={s.username} hint={s.username_hint} err={errs.username}>
              <input className="input" dir="ltr" required autoFocus pattern="[A-Za-z0-9_.@\-]{3,32}" value={f.username} onChange={(e) => set('username', e.target.value.trim())} />
            </Fld>
            <Fld label={s.password} err={errs.password}><PasswordInput value={f.password} onChange={(v) => set('password', v)} s={s} /></Fld>
          </Sec>
          <AdminFields f={f} set={set} opts={opts} s={s} errs={errs} />
          {tracked && (
            <Sec icon="gauge" title={s.sec_limit}>
              <Fld label={s.limit} hint={s.limit_hint} err={errs.limit_value}>
                <div className="af-pw"><input className="input" dir="ltr" inputMode="decimal" value={f.limit_value} onChange={(e) => set('limit_value', e.target.value.replace(/[^\d.]/g, ''))} />
                  <select className="input af-unit" value={f.limit_unit} onChange={(e) => set('limit_unit', e.target.value)} aria-label={s.unit}><option>GB</option><option>TB</option></select></div>
              </Fld>
              {can('agency.accounting') && (
                <Fld label={s.price} hint={charge != null ? `${s.charge}: ${charge.toLocaleString('en-US')} T (${limitGb.toLocaleString('en-US')} GB)` : s.price_hint} err={errs.price_per_gb}>
                  <input className="input" dir="ltr" inputMode="numeric" value={f.price_per_gb} onChange={(e) => set('price_per_gb', e.target.value.replace(/[^\d]/g, ''))} />
                </Fld>
              )}
              <Fld label={s.group} err={errs.group_id}>
                <select className="input" value={f.group_id} onChange={(e) => set('group_id', e.target.value)}>
                  <option value="">{s.no_group}</option>
                  {opts.agency_groups.map((g) => <option key={g.id} value={g.id}>{g.name}{g.name !== g.owner ? ` (${g.owner})` : ''}</option>)}
                </select>
              </Fld>
            </Sec>
          )}
          <div className="af-actions af-sticky">
            <Link to="/agency/admins" className="btn-ghost text-sm">{s.back}</Link>
            <button type="submit" className="btn-primary text-sm" disabled={busy || !opts.writes_enabled}>{busy ? s.creating : <><Ic n="plus" size={14} /> {s.create}</>}</button>
          </div>
        </>
      )}
    </form>
  )
}

// ================================ settings tab ===================================
const EDIT_KEYS = ['role_id', 'status', 'telegram_id', 'discord_webhook', 'support_url', 'sub_domain', 'profile_title', 'sub_template', 'note',
  'custom_variables', 'notification_enable', 'permission_overrides']
const norm = (k, v) => (v == null ? '' : typeof v === 'object' ? JSON.stringify(v) : String(v))

export function AdminSettingsTab({ username, writable, onDeleted }) {
  const [s] = useF()
  const confirm = useConfirm()
  const [opts] = useOptions('')
  const [orig, setOrig] = useState(null)
  const [f, setF] = useState(null)
  const [err, setErr] = useState('')
  const [errs, setErrs] = useState({})
  const [busy, setBusy] = useState(false)
  const [pw, setPw] = useState('')
  const [newPw, setNewPw] = useState(null)
  const load = () => api.get(`/admin/agency/panel-admins/${encodeURIComponent(username)}/`)
    .then((r) => { const v = { ...r.data, permission_overrides: r.data.permission_overrides || {} }; setOrig(v); setF(v); setErr('') })
    .catch((e) => setErr(e?.response?.status === 404 ? s.not_on_panel : (e?.response?.data?.detail || 'error')))
  useEffect(() => { load() }, [username])
  const set = (k, v) => { setF((x) => ({ ...x, [k]: v })); setErrs((e) => ({ ...e, [k]: undefined })) }
  const changed = useMemo(() => (f && orig ? EDIT_KEYS.filter((k) => norm(k, f[k]) !== norm(k, orig[k])) : []), [f, orig])

  const save = async (e) => {
    e.preventDefault()
    if (!changed.length) return
    setBusy(true); setErrs({})
    try {
      const body = Object.fromEntries(changed.map((k) => [k, f[k]]))
      await api.patch(`/admin/agency/panel-admins/${encodeURIComponent(username)}/`, body)
      await load()
    } catch (e2) { setErrs(fieldErrs(e2)) } finally { setBusy(false) }
  }
  const setPassword = async () => {
    if (pw.length < 8) { setErrs({ password: '8+' }); return }
    await api.patch(`/admin/agency/panel-admins/${encodeURIComponent(username)}/`, { password: pw })
    setNewPw(pw); setPw('')
  }
  const del = () => {
    let typed = ''
    confirm({
      tone: 'danger', title: s.del, targetLabel: username, message: s.del_d, confirmLabel: s.del,
      content: (
        <label className="af-fld af-wide"><span className="label">{s.del_type} <bdi dir="ltr"><b>{username}</b></bdi></span>
          <input className="input" dir="ltr" autoComplete="off" onChange={(e) => { typed = e.target.value }} /></label>
      ),
      action: async () => {
        if (typed.trim() !== username) throw new Error(s.del_mismatch)
        await api.delete(`/admin/agency/panel-admins/${encodeURIComponent(username)}/`, { data: { confirm: typed.trim() } })
      },
    }).then((ok) => { if (ok) onDeleted() })
  }

  if (err) return <div className="card ag-card"><p className="af-warn">{err}</p></div>
  if (!f || !opts) return <div className="grid place-items-center py-10"><Spinner /></div>
  return (
    <div className="space-y-4 af">
      <style>{CSS}</style>
      <form className="space-y-4" onSubmit={save}>
        <div className="af-head"><div><h3 className="font-bold">{s.set_title}</h3><p className="text-sm text-muted">{s.set_sub} {s.usage_note}</p></div></div>
        <AdminFields f={f} set={set} opts={opts} s={s} errs={errs} />
        <div className="af-actions af-sticky">
          <span className="text-xs text-muted">{changed.length ? changed.join(' · ') : s.no_change}</span>
          <button type="submit" className="btn-primary text-sm" disabled={!writable || busy || !changed.length}>{busy ? s.saving : s.save}</button>
        </div>
      </form>
      <Sec icon="key" title={s.pw_reset}>
        <Fld label={s.pw_new} err={errs.password}><PasswordInput value={pw} onChange={setPw} s={s} /></Fld>
        <div className="af-fld af-end"><button type="button" className="ag-act" data-tone="primary" disabled={!writable || !pw} onClick={setPassword}>{s.pw_do}</button></div>
      </Sec>
      {newPw && <CredentialsCard s={s} username={username} password={newPw} extra={<p className="af-hint">{s.pw_done}</p>} />}
      <section className="card ag-card af-danger">
        <h3 className="af-sec-h"><Ic n="alert" size={15} />{s.danger}</h3>
        <p className="text-sm text-muted">{s.del_d}</p>
        <button type="button" className="ag-act" data-tone="danger" disabled={!writable} onClick={del}><Ic n="trash" />{s.del}</button>
      </section>
    </div>
  )
}

const CSS = `
.af-sec { display: flex; flex-direction: column; gap: 10px; }
.af-sec-h { display: flex; align-items: center; gap: 7px; margin: 0; font-size: 14px; font-weight: 800; cursor: default; }
.af-details summary { cursor: pointer; list-style: none; }
.af-details summary::-webkit-details-marker { display: none; }
.af-details summary::after { content: '▾'; margin-inline-start: auto; color: var(--c-text-muted); }
.af-details[open] summary::after { content: '▴'; }
.af-grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr)); }
.af-fld { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.af-wide { grid-column: 1 / -1; }
.af-end { justify-content: flex-end; }
.af-hint { font-size: 11.5px; color: var(--c-text-muted); margin: 0; }
.af-err .input { border-color: var(--c-danger); }
.af-err-t { font-size: 11.5px; color: var(--c-danger-fg, var(--c-danger)); }
.af-pw { display: flex; gap: 6px; }
.af-pw .input { flex: 1; min-width: 0; }
.af-pw-b { flex-shrink: 0; display: inline-flex; align-items: center; gap: 4px; padding: 0 10px; border-radius: 10px; font-size: 12px; font-weight: 700;
  border: 1px solid var(--c-border); background: none; color: var(--c-text); cursor: pointer; }
.af-unit { width: 84px !important; flex: 0 0 84px !important; }
.af-toggles { display: grid; gap: 8px; grid-template-columns: repeat(auto-fill, minmax(min(100%, 200px), 1fr)); margin-top: 6px; }
.af-toggle { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.af-role { display: flex; flex-direction: column; gap: 4px; padding: 10px 12px; border-radius: 12px; font-size: 12.5px;
  background: color-mix(in srgb, var(--c-primary) 6%, transparent); border: 1px dashed color-mix(in srgb, var(--c-primary) 30%, var(--c-border)); }
.af-chip { display: inline-flex; align-items: center; width: max-content; padding: 1px 8px; border-radius: 999px; font-size: 11px; font-weight: 700;
  color: var(--c-success-fg, var(--c-success)); background: color-mix(in srgb, var(--c-success) 14%, transparent); }
.af-chip--owner { color: var(--c-warning-fg, var(--c-warning)); background: color-mix(in srgb, var(--c-warning) 14%, transparent); }
.af-vars { display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
.af-var { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 2fr) auto; gap: 6px; width: 100%; }
.af-panels { display: flex; flex-wrap: wrap; gap: 8px; }
.af-panel { display: inline-flex; align-items: center; gap: 8px; padding: 10px 14px; border-radius: 12px; border: 1.5px solid var(--c-border); background: none; color: var(--c-text); cursor: pointer; }
.af-panel.on { border-color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 10%, transparent); }
.af-warn { margin: 0; padding: 9px 12px; border-radius: 10px; font-size: 13px; color: var(--c-warning-fg, var(--c-warning));
  background: color-mix(in srgb, var(--c-warning) 12%, transparent); border: 1px solid color-mix(in srgb, var(--c-warning) 30%, transparent); }
.af-actions { display: flex; align-items: center; justify-content: flex-end; gap: 10px; flex-wrap: wrap; }
.af-sticky { position: sticky; bottom: 0; z-index: 5; padding: 10px 12px; border-radius: 14px; border: 1px solid var(--c-border);
  background: color-mix(in srgb, var(--c-surface) 94%, transparent); -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px); }
.af-sticky > span { margin-inline-end: auto; }
@media (max-width: 767px) { .af-sticky { bottom: 84px; } }
.af-done { display: flex; align-items: center; gap: 14px; }
.af-done-ico { width: 52px; height: 52px; flex-shrink: 0; border-radius: 999px; display: grid; place-items: center; color: #fff; background: #11AB53; }
.af-cred { display: flex; flex-direction: column; gap: 10px; }
.af-cred-rows { margin: 0; display: flex; flex-direction: column; gap: 8px; }
.af-cred-rows > div { display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: 8px; align-items: center; }
.af-cred-rows dt { font-size: 12.5px; color: var(--c-text-muted); }
.af-cred-rows dd { margin: 0; display: flex; align-items: center; gap: 8px; min-width: 0; }
.af-cred-rows code { flex: 1; min-width: 0; overflow-wrap: anywhere; padding: 6px 10px; border-radius: 8px; font-size: 13px;
  background: color-mix(in srgb, var(--c-text-muted) 10%, transparent); }
@media (max-width: 480px) { .af-cred-rows > div { grid-template-columns: 1fr; } }
.af-danger { border-color: color-mix(in srgb, var(--c-danger) 40%, var(--c-border)) !important; display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
.af-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
`
