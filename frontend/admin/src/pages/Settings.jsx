import { useEffect, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { Alert, Spinner, Toggle } from '../components/ui'

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
`
