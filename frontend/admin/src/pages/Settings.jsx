import { useEffect, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali, relTime } from '../lib/format'
import { Alert, Field, Spinner, Toggle } from '../components/ui'

const T = {
  fa: {
    h1: 'تنظیمات عمومی',
    sub: 'پیکربندی پارامترهای پشتیبان‌گیری، قیمت‌گذاری، هشدارها و الزامات عضویت',
    card_h: 'مقادیر پایه', card_sub: 'تنظیم بازه‌های زمانی، آستانه‌ها و گزینه‌های ارتباطی',
    toggles_h: 'الزامات و محدودیت‌ها',
    reset: 'بازنشانی مقادیر', save: 'ذخیرهٔ تغییرات',
    note: 'تغییر فاصلهٔ پشتیبان‌گیری بلافاصله زمان‌بند را به‌روز می‌کند.',
    info_h: 'راهنمای مبلغ تصادفی یکتا',
    info: 'مبلغ افزوده به قیمت، به‌صورت تصادفی بین حداقل و حداکثر به فاکتورهای کارت‌به‌کارت اضافه می‌شود تا سیستم بتواند بدون تداخل، پرداخت هر کاربر را از روی شناسهٔ مبلغ به‌صورت خودکار تأیید کند.',
    lang_fa: 'فارسی', lang_en: 'English',

    dev_h: 'دستگاه‌های SMS', dev_sub: 'دستگاه‌های اندرویدی مجاز برای ارسال پیامک‌های واریزی به سرور',
    dev_add: 'افزودن دستگاه', dev_none: 'هنوز دستگاهی ثبت نشده است',
    dev_col_name: 'نام دستگاه', dev_col_token: 'توکن', dev_col_active: 'وضعیت',
    dev_col_seen: 'آخرین اتصال', dev_col_created: 'تاریخ ایجاد', dev_col_actions: 'عملیات',
    dev_reveal: 'نمایش توکن', dev_delete: 'حذف', dev_never: 'هرگز',
    dev_delete_confirm: 'این دستگاه حذف شود؟ اتصال آن به سرور بلافاصله قطع می‌شود.',
    dev_add_title: 'افزودن دستگاه جدید', dev_reveal_title: 'توکن دستگاه',
    dev_name_label: 'نام دستگاه (مثلاً گوشی اپراتور)', dev_name_placeholder: 'مثلاً Samsung A54 — اپراتور اصلی',
    dev_create_btn: 'ایجاد دستگاه', dev_done: 'متوجه شدم',
    dev_token_warn: 'این توکن دیگر نمایش داده نمی‌شود — همین حالا آن را کپی و در برنامهٔ اندروید وارد کنید.',
    dev_copy: 'کپی', dev_copied: 'کپی شد',
  },
  en: {
    h1: 'General settings',
    sub: 'Configure backup, pricing, alerts and membership requirement parameters',
    card_h: 'Base values', card_sub: 'Set the intervals, thresholds and communication options',
    toggles_h: 'Requirements & restrictions',
    reset: 'Reset values', save: 'Save changes',
    note: 'Changing the backup interval reschedules the backup task immediately.',
    info_h: 'About the unique random amount',
    info: 'A random amount between the min and max is added to each card-to-card invoice so the system can auto-verify every payment by its unique amount without clashing with other users’ bank transactions.',
    lang_fa: 'Persian', lang_en: 'English',

    dev_h: 'SMS Devices', dev_sub: 'Android devices authorized to forward deposit SMS to the server',
    dev_add: 'Add device', dev_none: 'No devices registered yet',
    dev_col_name: 'Device name', dev_col_token: 'Token', dev_col_active: 'Status',
    dev_col_seen: 'Last seen', dev_col_created: 'Created', dev_col_actions: 'Actions',
    dev_reveal: 'Reveal token', dev_delete: 'Delete', dev_never: 'Never',
    dev_delete_confirm: 'Delete this device? It will be disconnected from the server immediately.',
    dev_add_title: 'Add a new device', dev_reveal_title: 'Device token',
    dev_name_label: 'Device name (e.g. the operator\'s phone)', dev_name_placeholder: 'e.g. Samsung A54 — main operator',
    dev_create_btn: 'Create device', dev_done: 'Got it',
    dev_token_warn: 'This token will not be shown again — copy it now and paste it into the Android app.',
    dev_copy: 'Copy', dev_copied: 'Copied',
  },
}

// per-key advisory hints (mirrors backend EDITABLE_SETTINGS min/max)
const HINT = {
  fa: {
    backup_interval_minutes: 'پیش‌فرض: ۱۴۴۰ (۲۴ ساعت)',
    unique_amount_reservation_minutes: 'زمان انقضای فاکتور کارت‌به‌کارت',
    unique_amount_min: 'کف مبلغ افزوده — تومان',
    unique_amount_max: 'سقف مبلغ افزوده — تومان',
    alert_volume_percent: 'مثلاً ۸۰٪ مصرف',
    alert_expire_days: 'ارسال نوتیفیکیشن پیش از اتمام مهلت',
  },
  en: {
    backup_interval_minutes: 'default: 1440 (24h)',
    unique_amount_reservation_minutes: 'card-to-card invoice expiry',
    unique_amount_min: 'floor of the added amount — toman',
    unique_amount_max: 'ceiling of the added amount — toman',
    alert_volume_percent: 'e.g. at 80% usage',
    alert_expire_days: 'notify this many days before expiry',
  },
}
const RANGE = {
  backup_interval_minutes: [5, 43200], unique_amount_reservation_minutes: [5, 720],
  unique_amount_min: [1, 100000], unique_amount_max: [1, 100000],
  alert_volume_percent: [1, 100], alert_expire_days: [1, 60],
}

// mode: 'add' (name form -> shows the new token once) | 'reveal' (fetches an
// existing device's token on open). Either way, once a token is in hand it's
// shown the same way — copy button + "won't be shown again" style warning.
function SmsDeviceModal({ mode, device, s, t, onClose, onCreated }) {
  const [name, setName] = useState('')
  const [token, setToken] = useState(null)
  const [busy, setBusy] = useState(mode === 'reveal')
  const [err, setErr] = useState('')
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (mode !== 'reveal') return
    api.get(`/admin/sms-devices/${device.id}/token/`)
      .then((r) => setToken(r.data.api_token))
      .catch((e) => setErr(apiError(e)))
      .finally(() => setBusy(false))
  }, [])

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr('')
    try {
      const { data } = await api.post('/admin/sms-devices/', { name })
      setToken(data.api_token)
      onCreated()
    } catch (e2) { setErr(apiError(e2)) } finally { setBusy(false) }
  }

  const copy = () => {
    navigator.clipboard?.writeText(token || '')
    setCopied(true); setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="sdm-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="sdm-modal card" role="dialog" aria-modal="true">
        <div className="sdm-modal-head">
          <h2 className="font-bold">{mode === 'add' ? s.dev_add_title : s.dev_reveal_title}</h2>
          <button type="button" className="sdm-icon-btn" onClick={onClose} aria-label={t('cancel')}>✕</button>
        </div>

        <div className="sdm-modal-body">
          <Alert>{err}</Alert>

          {mode === 'add' && !token && (
            <form id="sms-dev-form" onSubmit={submit}>
              <Field label={s.dev_name_label}>
                <input className="input" required autoFocus placeholder={s.dev_name_placeholder}
                  value={name} onChange={(e) => setName(e.target.value)} />
              </Field>
            </form>
          )}

          {mode === 'reveal' && busy && <div className="grid place-items-center py-6"><Spinner /></div>}

          {token && (
            <div className="sms-token-box">
              <p className="sms-token-warn">{s.dev_token_warn}</p>
              <div className="sms-token-row">
                <code className="mono-num" dir="ltr">{token}</code>
                <button type="button" className="btn-ghost text-xs" onClick={copy}>
                  {copied ? s.dev_copied : s.dev_copy}
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="sdm-modal-foot">
          {token ? (
            <button type="button" className="btn-primary text-sm" onClick={onClose}>{s.dev_done}</button>
          ) : mode === 'add' ? (
            <>
              <button type="button" className="btn-ghost text-sm" onClick={onClose}>{t('cancel')}</button>
              <button type="submit" form="sms-dev-form" className="btn-primary text-sm" disabled={busy}>
                {busy ? '…' : s.dev_create_btn}
              </button>
            </>
          ) : (
            <button type="button" className="btn-ghost text-sm" onClick={onClose}>{t('cancel')}</button>
          )}
        </div>
      </div>
    </div>
  )
}

function SmsDevicesSection({ t, s, lang }) {
  const [devices, setDevices] = useState(null)
  const [err, setErr] = useState('')
  const [modal, setModal] = useState(null) // { mode: 'add' } | { mode: 'reveal', device }

  const load = () =>
    api.get('/admin/sms-devices/')
      .then((r) => { setDevices(r.data.results ?? r.data); setErr('') })
      .catch((e) => { setDevices([]); setErr(apiError(e, t('load_error'))) })
  useEffect(() => { load() }, [])

  const toggle = async (d) => {
    setErr('')
    try {
      await api.patch(`/admin/sms-devices/${d.id}/`, { is_active: !d.is_active })
      setDevices((cur) => cur.map((x) => (x.id === d.id ? { ...x, is_active: !x.is_active } : x)))
    } catch (e2) { setErr(apiError(e2)) }
  }
  const del = async (d) => {
    if (!confirm(s.dev_delete_confirm)) return
    try { await api.delete(`/admin/sms-devices/${d.id}/`); load() } catch (e2) { setErr(apiError(e2)) }
  }

  return (
    <div className="card sms-dev-card">
      <div className="sms-dev-head">
        <div>
          <h3 className="font-bold text-sm">{s.dev_h}</h3>
          <p className="text-xs text-muted mt-0.5">{s.dev_sub}</p>
        </div>
        <button type="button" className="btn-primary text-sm" onClick={() => setModal({ mode: 'add' })}>
          {s.dev_add}
        </button>
      </div>

      <Alert>{err}</Alert>

      {devices === null ? (
        <div className="grid place-items-center py-10"><Spinner /></div>
      ) : devices.length === 0 ? (
        <div className="sms-dev-empty">{s.dev_none}</div>
      ) : (
        <div className="sms-dev-table-wrap">
          <table className="sms-dev-table">
            <thead>
              <tr>
                <th>{s.dev_col_name}</th>
                <th>{s.dev_col_token}</th>
                <th>{s.dev_col_active}</th>
                <th>{s.dev_col_seen}</th>
                <th>{s.dev_col_created}</th>
                <th>{s.dev_col_actions}</th>
              </tr>
            </thead>
            <tbody>
              {devices.map((d) => (
                <tr key={d.id}>
                  <td data-label={s.dev_col_name}><span className="font-semibold">{d.name}</span></td>
                  <td data-label={s.dev_col_token}><code className="mono-num sms-dev-masked" dir="ltr">{d.token_masked}</code></td>
                  <td data-label={s.dev_col_active}>
                    <Toggle checked={d.is_active} onChange={() => toggle(d)} label={s.dev_col_active} />
                  </td>
                  <td data-label={s.dev_col_seen}>{d.last_seen_at ? relTime(d.last_seen_at, lang) : s.dev_never}</td>
                  <td data-label={s.dev_col_created}>{jalali(d.created_at, false, lang)}</td>
                  <td data-label={s.dev_col_actions}>
                    <div className="sms-dev-actions">
                      <button type="button" className="btn-ghost text-xs" onClick={() => setModal({ mode: 'reveal', device: d })}>
                        {s.dev_reveal}
                      </button>
                      <button type="button" className="btn-ghost text-xs sms-dev-del" onClick={() => del(d)}>
                        {s.dev_delete}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modal && (
        <SmsDeviceModal
          mode={modal.mode}
          device={modal.device}
          s={s}
          t={t}
          onClose={() => setModal(null)}
          onCreated={load}
        />
      )}
    </div>
  )
}

export default function Settings() {
  const { t, lang } = useI18n()
  const s = T[lang] || T.fa
  const h = HINT[lang] || HINT.fa
  const [rows, setRows] = useState(null)
  const [form, setForm] = useState({})
  const [initial, setInitial] = useState({})
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  const load = () =>
    api.get('/admin/settings/')
      .then((r) => {
        const f = Object.fromEntries(r.data.settings.map((x) => [x.key, x.value]))
        setRows(r.data.settings); setForm(f); setInitial(f); setErr('')
      })
      .catch(() => { setRows([]); setErr(t('load_error')) })
  useEffect(() => { load() }, [])

  const save = async (e) => {
    e.preventDefault(); setBusy(true); setErr(''); setMsg('')
    try {
      await api.put('/admin/settings/', form)
      setMsg(t('saved')); setTimeout(() => setMsg(''), 2500); load()
    } catch (e2) { setErr(apiError(e2)) } finally { setBusy(false) }
  }
  const reset = () => setForm(initial)

  if (!rows) return <div className="grid place-items-center py-16"><Spinner /></div>

  const nums = rows.filter((x) => x.type === 'int')
  const bools = rows.filter((x) => x.type === 'bool')
  const strs = rows.filter((x) => x.type === 'str')

  return (
    <div className="st space-y-5">
      <style>{CSS}</style>

      <div className="st-head">
        <div>
          <h1 className="text-lg font-bold">{s.h1}</h1>
          <p className="text-sm text-muted mt-1">{s.sub}</p>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" className="btn-ghost text-sm" onClick={reset}>{s.reset}</button>
          <button type="submit" form="settings-form" className="btn-primary text-sm" disabled={busy}>
            {busy ? '…' : s.save}
          </button>
        </div>
      </div>

      <Alert>{err}</Alert>
      {msg && <Alert kind="success">{msg}</Alert>}

      <form id="settings-form" onSubmit={save} className="card st-card">
        <div className="st-card-head">
          <h3 className="font-bold text-sm">{s.card_h}</h3>
          <p className="text-xs text-muted mt-0.5">{s.card_sub}</p>
        </div>

        <div className="st-fields">
          {nums.map((x) => (
            <label key={x.key} className="st-fld">
              <span className="st-fld-top">
                <span className="label">{t('set_' + x.key)}</span>
                {h[x.key] && <span className="st-hint">{h[x.key]}</span>}
              </span>
              <input className="input" dir="ltr" type="number"
                min={RANGE[x.key]?.[0]} max={RANGE[x.key]?.[1]}
                value={form[x.key] ?? ''} onChange={(e) => setForm({ ...form, [x.key]: e.target.value })} />
            </label>
          ))}
        </div>

        {bools.length > 0 && (
          <div className="st-toggles">
            <span className="label st-toggles-h">{s.toggles_h}</span>
            {bools.map((x, i) => (
              <div key={x.key} className={'st-toggle-row' + (i ? ' st-div' : '')}>
                <span className="text-sm">{t('set_' + x.key)}</span>
                <Toggle checked={!!form[x.key]} onChange={(v) => setForm({ ...form, [x.key]: v })} label={t('set_' + x.key)} />
              </div>
            ))}
          </div>
        )}

        <div className="st-selects">
          {strs.map((x) => (
            <label key={x.key} className="st-fld">
              <span className="label">{t('set_' + x.key)}</span>
              <select className="input" value={form[x.key] ?? ''} onChange={(e) => setForm({ ...form, [x.key]: e.target.value })}>
                {x.key === 'default_language' && <>
                  <option value="fa">{s.lang_fa}</option>
                  <option value="en">{s.lang_en}</option>
                </>}
                {x.key === 'product_display_mode' && <>
                  <option value="grouped">{t('display_grouped')}</option>
                  <option value="flat">{t('display_flat')}</option>
                </>}
              </select>
            </label>
          ))}
        </div>

        <div className="st-foot">
          <button className="btn-primary text-sm" disabled={busy}>{busy ? '…' : t('save')}</button>
          <p className="text-xs text-muted">{s.note}</p>
        </div>
      </form>

      <div className="card st-info">
        <span className="st-info-ico">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" /><path d="M12 16v-4M12 8h.01" />
          </svg>
        </span>
        <div>
          <span className="font-bold text-sm block">{s.info_h}</span>
          <p className="text-xs text-muted leading-6 mt-1">{s.info}</p>
        </div>
      </div>

      <SmsDevicesSection t={t} s={s} lang={lang} />
    </div>
  )
}

const CSS = `
.st-head { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-start; justify-content: space-between; }
.st-card { padding: 0; overflow: hidden; }
.st-card-head { padding: 18px 20px; border-bottom: 1px solid var(--c-border); }
.st-fields { padding: 20px; display: grid; grid-template-columns: 1fr; gap: 16px; }
@media (min-width: 640px) { .st-fields { grid-template-columns: 1fr 1fr; } }
.st-fld { display: flex; flex-direction: column; gap: 6px; }
.st-fld .label { font-size: 12px; }
.st-fld-top { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.st-hint { font-size: 11px; color: var(--c-text-muted); }

.st-toggles { padding: 4px 20px 20px; }
.st-toggles-h { display: block; margin-bottom: 4px; }
.st-toggle-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 13px 0; }
.st-div { border-top: 1px solid var(--c-border); }

.st-selects { padding: 0 20px 20px; display: grid; grid-template-columns: 1fr; gap: 16px; }
@media (min-width: 640px) { .st-selects { grid-template-columns: 1fr 1fr; } }

.st-foot { padding: 16px 20px; border-top: 1px solid var(--c-border); display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }

.st-info { display: flex; gap: 14px; align-items: flex-start; }
.st-info-ico { width: 38px; height: 38px; border-radius: 11px; flex-shrink: 0; display: grid; place-items: center;
  background: color-mix(in srgb, var(--c-primary) 13%, transparent); color: var(--c-primary); }

/* ---- SMS devices section ---- */
.sms-dev-card { padding: 0; overflow: hidden; }
.sms-dev-head { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-start; justify-content: space-between;
  padding: 18px 20px; border-bottom: 1px solid var(--c-border); }
.sms-dev-empty { padding: 32px 20px; text-align: center; color: var(--c-text-muted); font-size: 13px; }

.sms-dev-table-wrap { overflow-x: auto; }
.sms-dev-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.sms-dev-table th { text-align: start; padding: 10px 20px; font-size: 11px; font-weight: 600; color: var(--c-text-muted);
  border-bottom: 1px solid var(--c-border); white-space: nowrap; }
.sms-dev-table td { padding: 12px 20px; border-bottom: 1px solid var(--c-border); vertical-align: middle; }
.sms-dev-table tr:last-child td { border-bottom: 0; }
.sms-dev-masked { color: var(--c-text-muted); }
.sms-dev-actions { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.sms-dev-del:hover { color: var(--c-danger); border-color: var(--c-danger); }

/* stack into cards below ~640px */
@media (max-width: 640px) {
  .sms-dev-table thead { display: none; }
  .sms-dev-table, .sms-dev-table tbody, .sms-dev-table tr, .sms-dev-table td { display: block; width: 100%; }
  .sms-dev-table tr { padding: 12px 16px; border-bottom: 1px solid var(--c-border); }
  .sms-dev-table td { display: flex; align-items: center; justify-content: space-between; gap: 12px;
    padding: 6px 0; border-bottom: 0; }
  .sms-dev-table td::before { content: attr(data-label); font-size: 11px; font-weight: 600; color: var(--c-text-muted); }
}

/* modal (local to this page — do not confuse with Cards.jsx's cd-* classes) */
.sdm-backdrop { position: fixed; inset: 0; z-index: 60; background: color-mix(in srgb, #0b1220 62%, transparent);
  backdrop-filter: blur(3px); display: flex; align-items: flex-start; justify-content: center; padding: 24px 16px; overflow-y: auto; }
.sdm-modal { width: 100%; max-width: 440px; padding: 0; overflow: hidden; }
.sdm-modal-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
  padding: 18px 20px; border-bottom: 1px solid var(--c-border); }
.sdm-modal-body { padding: 20px; display: flex; flex-direction: column; gap: 14px; }
.sdm-modal-foot { display: flex; justify-content: flex-end; gap: 10px; padding: 14px 20px; border-top: 1px solid var(--c-border); }
.sdm-icon-btn { padding: 6px; border-radius: 9px; color: var(--c-text-muted); }
.sdm-icon-btn:hover { color: var(--c-text); background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); }

.sms-token-box { padding: 13px 14px; border-radius: 14px;
  border: 1px solid color-mix(in srgb, var(--c-warning) 30%, transparent);
  background: color-mix(in srgb, var(--c-warning) 8%, transparent); }
.sms-token-warn { font-size: 12px; line-height: 1.7; color: color-mix(in srgb, var(--c-warning) 85%, var(--c-text)); margin: 0 0 10px; }
.sms-token-row { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 10px;
  background: var(--c-surface); border: 1px solid var(--c-border); }
.sms-token-row code { flex: 1; min-width: 0; overflow-wrap: anywhere; font-size: 12px; }
`
