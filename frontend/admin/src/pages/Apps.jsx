// /panel/apps — the operator tools for the phone that receives the bank SMS:
// the Android "SMS Bridge" app and the iPhone Shortcut. Both are downloaded
// from OUR server (admin API), so this works on an offline / Iran-only host.
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { digits, jalali } from '../lib/format'
import { copyToClipboard } from '../lib/clipboard'
import { useToast } from '../components/Toast'
import { useAuth } from '../lib/auth'
import { Spinner } from '../components/ui'

const T = {
  fa: {
    h1: 'اپلیکیشن‌ها و ابزارها', sub: 'ابزارهای گوشیِ دریافت‌کنندهٔ پیامک بانک برای تأیید خودکار پرداخت‌ها — مستقیم از سرور خودتان دانلود کنید',
    android_t: 'اپلیکیشن اندروید SMS Bridge', ios_t: 'شورتکات آیفون (Shortcuts)',
    android_what: 'این اپ روی گوشی اندرویدی‌ای نصب می‌شود که پیامک‌های واریز بانک به آن می‌رسد. هر پیامکِ فرستندهٔ بانکی مجاز را فوراً به سرور می‌فرستد تا سامانه مبلغ را با سفارش‌ها تطبیق دهد و پرداخت را خودکار تأیید کند — بدون نیاز به تأیید دستی ادمین.',
    ios_what: 'آیفون اجازه نمی‌دهد اپ‌ها پیامک‌ها را بخوانند؛ به‌جای اپ، یک شورتکات (Shortcuts) با «اتوماسیون پیام» پیامک‌های بانک را به همان آدرس سرور می‌فرستد تا پرداخت‌ها مثل اپ اندروید خودکار تأیید شوند.',
    features: 'چه کاری انجام می‌دهد؟', setup: 'راه‌اندازی',
    a_f: ['فقط پیامک‌های شماره‌های بانکیِ تعریف‌شده ارسال می‌شود', 'اجرای دائمی در پس‌زمینه و شروع خودکار پس از روشن شدن گوشی', 'ارسال مجدد خودکار در صورت قطعی اینترنت (تا 3 بار)', 'نمایش وضعیت اتصال و 20 پیامک آخر در خود اپ'],
    a_s: ['فایل APK را دانلود و روی گوشی نصب کنید (اجازهٔ «نصب از منابع ناشناس» را بدهید).', 'در پنل: تنظیمات ← دستگاه‌های SMS ← «افزودن دستگاه» و توکن ساخته‌شده را کپی کنید.', 'در اپ آدرس سرور (پایین همین صفحه) و توکن را وارد و «تست اتصال» را بزنید.', 'مجوز دریافت پیامک را بدهید و بهینه‌سازی باتری را برای اپ خاموش کنید.', 'در تنظیمات ← شماره‌های بانکی، شمارهٔ فرستندهٔ پیامک بانک را اضافه کنید.'],
    i_f: ['اتوماسیون «وقتی پیامی از فرستندهٔ بانک رسید» روی خود آیفون', 'ارسال متن پیامک به سرور با توکن همان دستگاه', 'بدون نصب اپ و بدون نیاز به App Store'],
    i_s: ['در پنل: تنظیمات ← دستگاه‌های SMS ← «افزودن دستگاه» برای این آیفون.', 'همین‌جا دستگاه را انتخاب و شورتکات را دانلود کنید — آدرس سرور و توکن داخل فایل قرار می‌گیرد (بدون انتخاب دستگاه، توکن هنگام افزودن پرسیده می‌شود).', 'آیفون فقط شورتکات امضاشده را می‌پذیرد: روی یک مک ‎shortcuts sign --mode anyone -i CaspinSMS.shortcut -o CaspinSMS-signed.shortcut‎ را اجرا کنید (یا از لینک iCloud استفاده کنید).', 'فایل امضاشده را روی آیفون باز و «Add Shortcut» را بزنید.', 'Shortcuts ← Automation ← «Message»: فرستندهٔ بانک ← اجرای همین شورتکات با «Shortcut Input» ← «Run Immediately» را روشن کنید.'],
    server: 'آدرس دریافت پیامک در سرور', header: 'هدر احراز هویت', body: 'بدنهٔ درخواست (JSON)',
    copy: 'کپی', copied: 'کپی شد', download: 'دانلود از سرور', downloading: 'در حال دانلود…',
    none_file: 'هنوز فایلی بارگذاری نشده است', version: 'نسخه', size: 'حجم', updated: 'به‌روزرسانی', by: 'توسط',
    src_bundled: 'نسخهٔ همراه سامانه', src_upload: 'بارگذاری‌شده توسط ادمین', icloud: 'لینک iCloud (نیاز به اینترنت)',
    manage: 'بارگذاری نسخهٔ جدید', file: 'فایل', file_hint_android: 'فایل ‎.apk‎ — حداکثر 60 مگابایت', file_hint_ios: 'فایل ‎.shortcut‎',
    link: 'لینک خارجی (اختیاری)', notes: 'یادداشت / توضیحات نسخه', save: 'ذخیره', saved: 'ذخیره شد', clear: 'حذف فایل بارگذاری‌شده',
    devices_link: 'مدیریت دستگاه‌های SMS', notes_h: 'یادداشت نسخه', mb: 'مگابایت',
    src_repo: 'از مخزن کد (منبع واحد)', device: 'توکن کدام دستگاه داخل فایل قرار گیرد؟', device_none: 'هیچ — توکن هنگام افزودن پرسیده شود',
    manage_ios: 'ویرایش لینک iCloud و یادداشت', ios_single: 'شورتکات همیشه از فایل مخزن ساخته می‌شود و بارگذاری نمی‌شود؛ تغییر آن = ویرایش ‎mobile_shortcut/‎ و افزایش نسخه.',
  },
  en: {
    h1: 'Apps & tools', sub: 'Tools for the phone that receives the bank SMS, for automatic payment confirmation — downloaded straight from your own server',
    android_t: 'Android SMS Bridge app', ios_t: 'iPhone Shortcut',
    android_what: 'Install this on the Android phone that receives the bank deposit SMS. It instantly forwards every SMS from an allowed bank sender to the server, which matches the amount to an order and confirms the payment automatically — no manual approval.',
    ios_what: "iOS doesn't let apps read SMS, so instead a Shortcut with a Message automation forwards the bank SMS to the same server endpoint, so payments are auto-confirmed just like with the Android app.",
    features: 'What it does', setup: 'Setup',
    a_f: ['Only SMS from the configured bank numbers are forwarded', 'Runs permanently in the background and restarts after a reboot', 'Automatic retry when the connection drops (up to 3 times)', 'Shows the connection status and the last 20 SMS in the app'],
    a_s: ['Download the APK and install it on the phone (allow "install unknown apps").', 'In the panel: Settings → SMS devices → "Add device", copy the generated token.', 'In the app enter the server address (below) and the token, then tap "Test connection".', 'Grant the SMS permission and turn battery optimization off for the app.', 'In Settings → Bank numbers add the sender number of the bank SMS.'],
    i_f: ['A "when a message from the bank arrives" automation on the iPhone', 'Sends the SMS text to the server with that device\'s token', 'Nothing to install, no App Store needed'],
    i_s: ['In the panel: Settings → SMS devices → "Add device" for this iPhone.', 'Pick that device here and download — the server address and token are filled into the file (without a device, the token is asked when adding the shortcut).', 'iOS only imports signed shortcuts: on a Mac run `shortcuts sign --mode anyone -i CaspinSMS.shortcut -o CaspinSMS-signed.shortcut` (or use the iCloud link).', 'Open the signed file on the iPhone and tap "Add Shortcut".', 'Shortcuts → Automation → "Message": the bank sender → run this shortcut with "Shortcut Input" → turn "Run Immediately" on.'],
    server: 'SMS endpoint on the server', header: 'Auth header', body: 'Request body (JSON)',
    copy: 'Copy', copied: 'Copied', download: 'Download from server', downloading: 'Downloading…',
    none_file: 'No file uploaded yet', version: 'Version', size: 'Size', updated: 'Updated', by: 'by',
    src_bundled: 'Bundled with the system', src_upload: 'Uploaded by an admin', icloud: 'iCloud link (needs internet)',
    manage: 'Upload a new version', file: 'File', file_hint_android: '.apk file — max 60 MB', file_hint_ios: '.shortcut file',
    link: 'External link (optional)', notes: 'Notes / release notes', save: 'Save', saved: 'Saved', clear: 'Remove uploaded file',
    devices_link: 'Manage SMS devices', notes_h: 'Release notes', mb: 'MB',
    src_repo: 'From the repository (single source)', device: 'Put which device\'s token in the file?', device_none: 'None — ask for the token when adding',
    manage_ios: 'Edit iCloud link & notes', ios_single: 'The shortcut is always built from the repository file and is never uploaded; changing it = edit mobile_shortcut/ and bump its version.',
  },
}

function Ico({ d, w = 18 }) {
  return (
    <svg viewBox="0 0 24 24" width={w} height={w} fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}</svg>
  )
}
const I = {
  android: <><path d="M7 9h10v8a2 2 0 01-2 2H9a2 2 0 01-2-2V9z" /><path d="M7 9a5 5 0 0110 0M9 5.5 7.8 3.8M15 5.5l1.2-1.7M4 10v5M20 10v5" /><circle cx="10" cy="6.8" r=".5" /><circle cx="14" cy="6.8" r=".5" /></>,
  ios: <><rect x="6" y="2" width="12" height="20" rx="3" /><path d="M11 18h2" /></>,
  download: <><path d="M12 3v12m0 0l-4-4m4 4l4-4" /><path d="M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" /></>,
  check: <path d="M4.5 12.75l6 6 9-13.5" />,
  copy: <><rect x="9" y="9" width="12" height="12" rx="2" /><path d="M5 15H4a1 1 0 01-1-1V4a1 1 0 011-1h10a1 1 0 011 1v1" /></>,
  upload: <><path d="M12 21V9m0 0l-4 4m4-4l4 4" /><path d="M4 7V5a2 2 0 012-2h12a2 2 0 012 2v2" /></>,
  link: <path d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244" />,
}

const mb = (n) => (n ? Math.round((n / 1048576) * 10) / 10 : 0)

function CopyRow({ label, value, s }) {
  const [ok, setOk] = useState(false)
  return (
    <div className="ap-copy">
      <span className="ap-copy-l">{label}</span>
      <div className="ap-copy-v">
        <code dir="ltr">{value}</code>
        <button type="button" className="ap-copy-btn" onClick={async () => { if (await copyToClipboard(value)) { setOk(true); setTimeout(() => setOk(false), 1400) } }}>
          <Ico d={ok ? I.check : I.copy} w={15} />{ok ? s.copied : s.copy}
        </button>
      </div>
    </div>
  )
}

function AppCard({ info, s, lang, onSaved }) {
  const toast = useToast()
  const android = info.platform === 'android'
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState(false)
  const [f, setF] = useState({ version: info.version || '', link: info.link || '', notes: info.notes || '', file: null })
  const [saving, setSaving] = useState(false)
  const tone = android ? '#11AB53' : '#1464BA'
  const hasFile = !!info.source
  const { can } = useAuth()
  const [devices, setDevices] = useState([])
  const [deviceId, setDeviceId] = useState('')
  useEffect(() => {
    if (android || !can('sms.manage')) return
    api.get('/admin/sms-devices/?limit=100')
      .then((r) => setDevices((r.data.results || r.data || []).filter((d) => d.is_active !== false)))
      .catch(() => setDevices([]))
  }, [android])

  const download = async () => {
    setBusy(true)
    try {
      const q = !android && deviceId ? `?device=${deviceId}` : ''
      const r = await api.get(`/admin/apps/${info.platform}/download/${q}`, { responseType: 'blob' })
      const url = URL.createObjectURL(r.data)
      const a = document.createElement('a')
      a.href = url; a.download = info.file_name || (android ? 'app.apk' : 'shortcut.shortcut')
      document.body.appendChild(a); a.click(); a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 4000)
    } catch (e) { toast.error(apiError(e)) } finally { setBusy(false) }
  }

  const save = async (e, extra = {}) => {
    e?.preventDefault?.()
    setSaving(true)
    try {
      const fd = new FormData()
      if (android) fd.append('version', f.version)
      fd.append('notes', f.notes)
      if (!android) fd.append('link', f.link)
      if (f.file) fd.append('file', f.file)
      Object.entries(extra).forEach(([k, v]) => fd.append(k, v))
      const { data } = await api.post(`/admin/apps/${info.platform}/`, fd)
      toast.success(s.saved); setF((p) => ({ ...p, file: null })); onSaved(data)
    } catch (e2) { toast.error(apiError(e2)) } finally { setSaving(false) }
  }

  const features = android ? s.a_f : s.i_f
  const steps = android ? s.a_s : s.i_s

  return (
    <section className="card ap-card">
      <div className="ap-head">
        <span className="ap-ico" style={{ color: tone, background: `color-mix(in srgb, ${tone} 13%, transparent)` }}>
          <Ico d={android ? I.android : I.ios} w={26} />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="ap-title">{android ? s.android_t : s.ios_t}</h2>
          <div className="ap-meta">
            {info.version && <span className="ap-chip">{s.version} {digits(info.version, lang)}</span>}
            {info.size != null && <span className="ap-chip">{s.size}: {digits(mb(info.size), lang)} {s.mb}</span>}
            {info.source && <span className="ap-chip ap-chip--src">{info.source === 'bundled' ? s.src_bundled : info.source === 'repo' ? s.src_repo : s.src_upload}</span>}
            {info.updated_at && <span className="ap-chip">{s.updated}: {jalali(info.updated_at, false, lang)}{info.updated_by ? ` · ${s.by} ${info.updated_by}` : ''}</span>}
          </div>
        </div>
      </div>

      <p className="ap-what">{android ? s.android_what : s.ios_what}</p>

      <div className="ap-cols">
        <div>
          <h3 className="ap-h3">{s.features}</h3>
          <ul className="ap-list">{features.map((x) => <li key={x}><Ico d={I.check} w={14} />{x}</li>)}</ul>
        </div>
        <div>
          <h3 className="ap-h3">{s.setup}</h3>
          <ol className="ap-steps">{steps.map((x, i) => <li key={x}><b>{digits(i + 1, lang)}</b><span>{x}</span></li>)}</ol>
        </div>
      </div>

      {info.notes && <div className="ap-notes"><b>{s.notes_h}</b><p>{info.notes}</p></div>}

      {!android && devices.length > 0 && (
        <label className="ap-fld">
          <span className="label">{s.device}</span>
          <select className="input" value={deviceId} onChange={(e) => setDeviceId(e.target.value)}>
            <option value="">{s.device_none}</option>
            {devices.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </label>
      )}

      <div className="ap-actions">
        <button type="button" className="btn-primary ap-dl" onClick={download} disabled={!hasFile || busy}>
          {busy ? <><span className="ap-spin" />{s.downloading}</> : <><Ico d={I.download} />{s.download}</>}
        </button>
        {!hasFile && <span className="text-xs text-muted">{s.none_file}</span>}
        {info.link && (
          <a className="btn-ghost ap-link" href={info.link} target="_blank" rel="noreferrer"><Ico d={I.link} w={16} />{s.icloud}</a>
        )}
        <Link to="/settings/sms-devices" className="btn-ghost ap-link">{s.devices_link}</Link>
      </div>

      <details className="ap-manage" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
        <summary><Ico d={I.upload} w={16} />{android ? s.manage : s.manage_ios}</summary>
        <form className="ap-form" onSubmit={save}>
          {!android && <p className="text-xs text-muted leading-relaxed">{s.ios_single}</p>}
          {android && <label className="ap-fld">
            <span className="label">{s.file}</span>
            <input className="input" type="file" accept=".apk"
              onChange={(e) => setF((p) => ({ ...p, file: e.target.files?.[0] || null }))} />
            <span className="text-xs text-muted">{s.file_hint_android}</span>
          </label>}
          <div className="ap-grid2">
            {android && <label className="ap-fld">
              <span className="label">{s.version}</span>
              <input className="input" dir="ltr" value={f.version} onChange={(e) => setF((p) => ({ ...p, version: e.target.value }))} placeholder="1.0.0" />
            </label>}
            {!android && (
              <label className="ap-fld">
                <span className="label">{s.link}</span>
                <input className="input" dir="ltr" type="url" value={f.link} onChange={(e) => setF((p) => ({ ...p, link: e.target.value }))} placeholder="https://www.icloud.com/shortcuts/…" />
              </label>
            )}
          </div>
          <label className="ap-fld">
            <span className="label">{s.notes}</span>
            <textarea className="input" rows={3} value={f.notes} onChange={(e) => setF((p) => ({ ...p, notes: e.target.value }))} />
          </label>
          <div className="ap-form-foot">
            {info.source === 'upload' && (
              <button type="button" className="btn-ghost text-sm" disabled={saving} onClick={(e) => save(e, { clear_file: 'true' })}>{s.clear}</button>
            )}
            <button type="submit" className="btn-primary text-sm" disabled={saving}>{saving ? '…' : s.save}</button>
          </div>
        </form>
      </details>
    </section>
  )
}

export default function Apps() {
  const { t, lang } = useI18n()
  const s = T[lang] || T.fa
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    api.get('/admin/apps/').then((r) => setRows(r.data.results)).catch((e) => { setRows([]); setErr(apiError(e, t('load_error'))) })
  }, [])

  const endpoint = `${window.location.origin}/api/v1/payments/sms/inbound/`
  const replace = (d) => setRows((cur) => cur.map((r) => (r.platform === d.platform ? d : r)))

  return (
    <div className="ap space-y-5">
      <style>{CSS}</style>
      <div>
        <h1 className="text-lg font-bold">{s.h1}</h1>
        <p className="text-sm text-muted mt-1">{s.sub}</p>
      </div>
      {err && <div className="card text-sm" style={{ color: 'var(--c-danger)' }}>{err}</div>}
      {rows === null ? <div className="grid place-items-center py-16"><Spinner /></div> : (
        <>
          <div className="ap-cards">
            {rows.map((r) => <AppCard key={r.platform} info={r} s={s} lang={lang} onSaved={replace} />)}
          </div>
          <section className="card ap-conn">
            <CopyRow label={s.server} value={endpoint} s={s} />
            <CopyRow label={s.header} value="X-Device-Token: <token>" s={s} />
            <CopyRow label={s.body} value={'{"text": "…", "sender": "…", "received_at": "ISO-8601 (optional)"}'} s={s} />
          </section>
        </>
      )}
    </div>
  )
}

const CSS = `
.ap-cards { display: grid; grid-template-columns: 1fr; gap: 16px; }
@media (min-width: 1100px) { .ap-cards { grid-template-columns: 1fr 1fr; } }
.ap-card { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.ap-head { display: flex; align-items: flex-start; gap: 14px; }
.ap-ico { width: 54px; height: 54px; border-radius: 16px; flex-shrink: 0; display: grid; place-items: center; }
.ap-title { font-size: 16px; font-weight: 800; }
.ap-meta { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.ap-chip { font-size: 11px; padding: 2px 8px; border-radius: 999px; color: var(--c-text-muted); background: color-mix(in srgb, var(--c-text-muted) 11%, transparent); }
.ap-chip--src { color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 11%, transparent); }
.ap-what { font-size: 13.5px; line-height: 2; color: var(--c-text); }
.ap-cols { display: grid; grid-template-columns: 1fr; gap: 16px; }
@media (min-width: 640px) { .ap-cols { grid-template-columns: 1fr 1fr; } }
.ap-h3 { font-size: 12.5px; font-weight: 800; margin-bottom: 8px; }
.ap-list { display: flex; flex-direction: column; gap: 7px; font-size: 12.5px; line-height: 1.8; }
.ap-list li { display: flex; gap: 7px; align-items: flex-start; }
.ap-list svg { color: var(--c-success); flex-shrink: 0; margin-top: 5px; }
.ap-steps { display: flex; flex-direction: column; gap: 8px; font-size: 12.5px; line-height: 1.8; }
.ap-steps li { display: flex; gap: 9px; align-items: flex-start; }
.ap-steps b { width: 22px; height: 22px; flex-shrink: 0; border-radius: 999px; display: grid; place-items: center; font-size: 11px; margin-top: 2px;
  color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 12%, transparent); }
.ap-notes { padding: 10px 12px; border-radius: 12px; font-size: 12.5px; background: color-mix(in srgb, var(--c-text-muted) 8%, transparent); }
.ap-notes p { margin-top: 4px; white-space: pre-wrap; line-height: 1.8; }
.ap-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.ap-dl, .ap-link { display: inline-flex; align-items: center; gap: 7px; min-height: 42px; }
.ap-spin { width: 16px; height: 16px; border-radius: 50%; border: 2px solid rgba(255,255,255,.4); border-top-color: #fff; animation: ap-spin .7s linear infinite; }
@keyframes ap-spin { to { transform: rotate(360deg); } }
.ap-manage { border-top: 1px solid var(--c-border); padding-top: 12px; }
.ap-manage summary { display: inline-flex; align-items: center; gap: 7px; cursor: pointer; font-size: 13px; font-weight: 700; color: var(--c-text-muted); list-style: none; }
.ap-manage summary::-webkit-details-marker { display: none; }
.ap-manage[open] summary { color: var(--c-primary); }
.ap-form { display: flex; flex-direction: column; gap: 12px; margin-top: 12px; }
.ap-grid2 { display: grid; grid-template-columns: 1fr; gap: 12px; }
@media (min-width: 640px) { .ap-grid2 { grid-template-columns: 1fr 1fr; } }
.ap-fld { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.ap-form-foot { display: flex; justify-content: flex-end; gap: 8px; }
.ap-conn { display: flex; flex-direction: column; gap: 12px; }
.ap-copy { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.ap-copy-l { font-size: 12px; font-weight: 700; color: var(--c-text-muted); }
.ap-copy-v { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 12px; border: 1px solid var(--c-border); min-width: 0; }
.ap-copy-v code { flex: 1; min-width: 0; font-size: 12.5px; overflow-wrap: anywhere; }
.ap-copy-btn { display: inline-flex; align-items: center; gap: 5px; flex-shrink: 0; font-size: 12px; font-weight: 700; padding: 6px 10px; border-radius: 9px;
  color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 10%, transparent); min-height: 34px; }
@media (max-width: 767px) { .ap-dl { flex: 1 1 100%; justify-content: center; } }
`
