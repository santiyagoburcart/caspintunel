// /panel/settings/email — outgoing email (SMTP relay). Django sends straight to
// the relay saved here (apps/common/mail.py): changes apply on the next email,
// no restart. Order: this relay (if on) → .env SMTP → local mailserver.
import { useEffect, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useAuth } from '../lib/auth'
import { jalali, relTime } from '../lib/format'
import { useToast } from '../components/Toast'
import { Alert, Spinner, Toggle } from '../components/ui'

const PRESETS = [
  { key: 'brevo', name: 'Brevo', host: 'smtp-relay.brevo.com', port: 587, security: 'starttls' },
  { key: 'mailgun', name: 'Mailgun', host: 'smtp.mailgun.org', port: 587, security: 'starttls' },
  { key: 'sendgrid', name: 'SendGrid', host: 'smtp.sendgrid.net', port: 587, security: 'starttls', username: 'apikey' },
  { key: 'ses', name: 'Amazon SES', host: 'email-smtp.eu-central-1.amazonaws.com', port: 587, security: 'starttls' },
]

const T = {
  fa: {
    h1: 'تنظیمات ایمیل', sub: 'سرور SMTP برای ایمیل‌های خروجی (تأیید ایمیل، بازیابی رمز، اعلان‌ها) — تغییرات بلافاصله اعمال می‌شود',
    relay_h: 'رلهٔ SMTP', enable: 'ارسال از طریق این رله', enable_hint: 'خاموش = استفاده از تنظیمات ‎.env‎ یا میل‌سرور محلی',
    presets: 'تنظیم سریع', preset_ses: 'منطقهٔ SES را در نام میزبان درست کنید (مثلاً us-east-1).',
    host: 'میزبان SMTP', port: 'پورت', security: 'امنیت', sec_starttls: 'STARTTLS (پورت 587)', sec_ssl: 'SSL/TLS (پورت 465)', sec_none: 'بدون رمزنگاری',
    username: 'نام کاربری', password: 'رمز عبور / کلید SMTP', pw_saved: 'ذخیره شده ✓', pw_keep: 'خالی = همان رمز ذخیره‌شده',
    pw_clear: 'حذف رمز ذخیره‌شده', pw_will_clear: 'رمز با ذخیرهٔ بعدی حذف می‌شود', undo: 'انصراف',
    from_h: 'فرستنده', from_email: 'آدرس فرستنده', from_name: 'نام فرستنده', from_preview: 'نمایش در صندوق گیرنده',
    from_default: 'خالی = آدرس پیش‌فرض سامانه',
    save: 'ذخیره', saving: 'در حال ذخیره…', saved: 'تنظیمات ایمیل ذخیره شد', reset: 'بازنشانی',
    status_h: 'وضعیت', via: 'ایمیل‌ها الان از این مسیر ارسال می‌شوند',
    src_db: 'رلهٔ همین صفحه', src_env: 'تنظیمات SMTP در ‎.env‎', src_local: 'میل‌سرور محلی (بدون رله)', src_none: 'هیچ — ایمیلی ارسال نمی‌شود',
    last_ok: 'آخرین ارسال موفق', last_err: 'آخرین خطا', never: 'هنوز ثبت نشده',
    test_h: 'ارسال ایمیل آزمایشی', test_to: 'گیرنده', test_btn: 'ارسال ایمیل آزمایشی', testing: 'در حال ارسال…',
    test_note: 'با تنظیمات ذخیره‌شده ارسال می‌شود — اول تغییرات را ذخیره کنید.', unsaved: 'تغییرات ذخیره‌نشده دارید',
    ok: 'موفق', fail: 'ناموفق', raw: 'پاسخ سرور', through: 'از طریق',
    help_h: 'راهنما',
    help: [
      'پورت 25 روی این سرور بسته است؛ از پورت 587 با STARTTLS (یا 465 با SSL) استفاده کنید.',
      'دامنهٔ آدرس فرستنده باید نزد سرویس‌دهنده تأیید شده باشد (رکوردهای SPF و DKIM در DNS)؛ وگرنه ارسال رد می‌شود یا به اسپم می‌رود.',
      'رمز عبور رمزنگاری‌شده ذخیره می‌شود و هرگز نمایش داده نمی‌شود.',
    ],
    no_perm: 'دسترسی «مدیریت ایمیل خروجی» (settings.email) را ندارید.',
  },
  en: {
    h1: 'Email settings', sub: 'SMTP server for outgoing email (verification, password reset, notifications) — changes apply immediately',
    relay_h: 'SMTP relay', enable: 'Send through this relay', enable_hint: 'Off = use the .env settings or the local mail server',
    presets: 'Quick setup', preset_ses: 'Set your SES region in the host name (e.g. us-east-1).',
    host: 'SMTP host', port: 'Port', security: 'Security', sec_starttls: 'STARTTLS (port 587)', sec_ssl: 'SSL/TLS (port 465)', sec_none: 'None (unencrypted)',
    username: 'Username', password: 'Password / SMTP key', pw_saved: 'Saved ✓', pw_keep: 'Blank = keep the saved password',
    pw_clear: 'Remove saved password', pw_will_clear: 'Password will be removed on save', undo: 'Undo',
    from_h: 'Sender', from_email: 'From address', from_name: 'From name', from_preview: 'Shown to recipients as',
    from_default: 'Blank = the system default address',
    save: 'Save', saving: 'Saving…', saved: 'Email settings saved', reset: 'Reset',
    status_h: 'Status', via: 'Emails are currently sent via',
    src_db: 'the relay on this page', src_env: 'SMTP settings in .env', src_local: 'the local mail server (no relay)', src_none: 'nothing — no email is sent',
    last_ok: 'Last successful send', last_err: 'Last error', never: 'none yet',
    test_h: 'Send test email', test_to: 'Recipient', test_btn: 'Send test email', testing: 'Sending…',
    test_note: 'Uses the SAVED settings — save your changes first.', unsaved: 'You have unsaved changes',
    ok: 'Success', fail: 'Failed', raw: 'Server response', through: 'via',
    help_h: 'Help',
    help: [
      'Port 25 is blocked on this server; use port 587 with STARTTLS (or 465 with SSL).',
      'The sender domain must be verified at the provider (SPF and DKIM DNS records), otherwise mail is rejected or lands in spam.',
      'The password is stored encrypted and is never shown again.',
    ],
    no_perm: 'You need the "Manage outgoing email" permission (settings.email).',
  },
}

const EDITABLE = ['enabled', 'host', 'port', 'security', 'username', 'from_email', 'from_name']

const CSS = `
.em { max-width: 60rem; }
.em-grid { display: grid; gap: 1rem; grid-template-columns: minmax(0, 1fr); }
@media (min-width: 1024px) { .em-grid { grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr); align-items: start; } }
.em-col { display: grid; gap: 1rem; min-width: 0; }
.em-card-h { font-weight: 700; font-size: .9rem; margin-bottom: .75rem; }
.em-row { display: grid; gap: .75rem; grid-template-columns: minmax(0, 1fr); }
@media (min-width: 640px) { .em-row-2 { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); } .em-row-hp { grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); } }
.em-fld { display: grid; gap: .3rem; min-width: 0; }
.em-hint { font-size: .72rem; color: var(--c-text-muted); line-height: 1.6; }
.em-toggle { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: .25rem 0 .9rem;
  border-bottom: 1px solid var(--c-border); margin-bottom: .9rem; }
.em-presets { display: flex; flex-wrap: wrap; gap: .4rem; }
.em-chip { border: 1px solid var(--c-border); background: var(--c-bg); color: var(--c-text); border-radius: 999px;
  padding: .3rem .8rem; font-size: .78rem; cursor: pointer; }
.em-chip:hover, .em-chip.on { border-color: var(--c-primary); color: var(--c-primary); }
.em-pw { position: relative; }
.em-pw .input { padding-inline-end: 2.4rem; }
.em-eye { position: absolute; inset-inline-end: .5rem; top: 50%; transform: translateY(-50%); background: none; border: 0;
  color: var(--c-text-muted); cursor: pointer; padding: .2rem; }
.em-badge { display: inline-flex; align-items: center; gap: .25rem; font-size: .72rem; font-weight: 600; border-radius: 999px;
  padding: .1rem .55rem; background: color-mix(in srgb, var(--c-success) 14%, transparent); color: var(--c-success); }
.em-link { background: none; border: 0; padding: 0; color: var(--c-danger); font-size: .75rem; cursor: pointer; text-decoration: underline; }
.em-status { display: grid; gap: .6rem; font-size: .82rem; }
.em-status-row { display: flex; align-items: flex-start; gap: .5rem; min-width: 0; }
.em-dot { width: .55rem; height: .55rem; border-radius: 999px; flex-shrink: 0; margin-top: .4rem; }
.em-code { display: block; margin-top: .3rem; font-size: .72rem; background: var(--c-bg); border: 1px solid var(--c-border);
  border-radius: .5rem; padding: .45rem .6rem; white-space: pre-wrap; word-break: break-word; color: var(--c-text-muted); }
.em-result { border-radius: .75rem; padding: .75rem .9rem; font-size: .84rem; border: 1px solid; }
.em-result.ok { border-color: color-mix(in srgb, var(--c-success) 40%, transparent); background: color-mix(in srgb, var(--c-success) 10%, transparent); }
.em-result.bad { border-color: color-mix(in srgb, var(--c-danger) 40%, transparent); background: color-mix(in srgb, var(--c-danger) 9%, transparent); }
.em-help li { font-size: .78rem; color: var(--c-text-muted); line-height: 1.7; padding-inline-start: .9rem; position: relative; }
.em-help li::before { content: ''; position: absolute; inset-inline-start: 0; top: .65rem; width: .3rem; height: .3rem; border-radius: 999px; background: var(--c-primary); }
.em-actions { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; justify-content: flex-end; }
@media (max-width: 767px) {
  .em-actions-bar { position: sticky; bottom: calc(4.25rem + env(safe-area-inset-bottom)); z-index: 5; background: var(--c-bg);
    padding: .6rem 0; border-top: 1px solid var(--c-border); }
  .em-actions-bar .btn-primary { flex: 1; }
}
`

function EyeIco({ off }) {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {off ? <><path d="M3 3l18 18" /><path d="M10.6 10.6a2 2 0 002.8 2.8" /><path d="M9.9 5.1A9.8 9.8 0 0112 5c5 0 9 4.5 10 7-.4 1-1.2 2.3-2.4 3.5M6.2 6.2C4.2 7.5 2.7 9.5 2 12c1 2.5 5 7 10 7 1.7 0 3.3-.5 4.6-1.3" /></>
        : <><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></>}
    </svg>
  )
}

export default function EmailSettings() {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const { can } = useAuth()
  const toast = useToast()
  const [data, setData] = useState(null)
  const [form, setForm] = useState(null)
  const [pw, setPw] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [clearPw, setClearPw] = useState(false)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [to, setTo] = useState('')
  const [testing, setTesting] = useState(false)
  const [result, setResult] = useState(null)

  const apply = (d) => {
    setData(d)
    setForm(Object.fromEntries(EDITABLE.map((k) => [k, d[k] ?? ''])))
    setPw(''); setClearPw(false)
  }
  const load = () => api.get('/admin/email/').then((r) => apply(r.data)).catch((e) => setErr(apiError(e)))
  useEffect(() => { if (can('settings.email')) load() }, [])

  if (!can('settings.email')) return <div className="card"><Alert>{s.no_perm}</Alert></div>
  if (!form) return err ? <div className="card"><Alert>{err}</Alert></div> : <div className="grid place-items-center py-16"><Spinner /></div>

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))
  const dirty = EDITABLE.some((k) => String(form[k] ?? '') !== String(data[k] ?? '')) || !!pw || clearPw
  const preset = PRESETS.find((p) => p.host === form.host)

  const usePreset = (p) => setForm((f) => ({
    ...f, host: p.host, port: p.port, security: p.security,
    username: p.username && !f.username ? p.username : f.username,
  }))

  const save = async (e) => {
    e?.preventDefault(); setBusy(true); setErr('')
    try {
      const body = { ...form, port: Number(form.port) || 587 }
      if (pw) body.password = pw
      else if (clearPw) body.clear_password = true
      const r = await api.put('/admin/email/', body)
      apply(r.data)
      toast.success(s.saved)
    } catch (e2) {
      const d = e2?.response?.data
      const msg = d && typeof d === 'object' && !d.detail
        ? Object.entries(d).map(([k, v]) => `${s[k] || k}: ${Array.isArray(v) ? v[0] : v}`).join(' · ')
        : apiError(e2)
      setErr(msg); toast.error(msg)
    } finally { setBusy(false) }
  }

  const sendTest = async () => {
    setTesting(true); setResult(null)
    try {
      const r = await api.post('/admin/email/test/', { to })
      setResult(r.data)
      load()
    } catch (e) {
      setResult({ ok: false, fa: apiError(e), en: apiError(e), raw: '' })
    } finally { setTesting(false) }
  }

  const srcLabel = { db: s.src_db, env: s.src_env, local: s.src_local, none: s.src_none }
  const srcOk = data.effective_source === 'db' || data.effective_source === 'env'
  const fromPreview = form.from_email
    ? (form.from_name ? `${form.from_name} <${form.from_email}>` : form.from_email)
    : data.default_from
  const when = (v) => (v ? `${jalali(v, true, lang)} · ${relTime(v, lang)}` : s.never)

  return (
    <div className="em space-y-4">
      <style>{CSS}</style>
      <div>
        <h1 className="text-lg font-bold">{s.h1}</h1>
        <p className="mt-1 text-sm text-muted">{s.sub}</p>
      </div>

      {err && <Alert>{err}</Alert>}

      <div className="em-grid">
        <form className="em-col" onSubmit={save}>
          <div className="card">
            <div className="em-card-h">{s.relay_h}</div>
            <div className="em-toggle">
              <span className="min-w-0">
                <span className="block text-sm font-medium">{s.enable}</span>
                <span className="em-hint">{s.enable_hint}</span>
              </span>
              <Toggle checked={!!form.enabled} onChange={(v) => set('enabled', v)} label={s.enable} />
            </div>

            <div className="em-fld mb-3">
              <span className="label">{s.presets}</span>
              <div className="em-presets">
                {PRESETS.map((p) => (
                  <button key={p.key} type="button" className={'em-chip' + (preset?.key === p.key ? ' on' : '')} onClick={() => usePreset(p)}>
                    {p.name}
                  </button>
                ))}
              </div>
              {preset?.key === 'ses' && <span className="em-hint">{s.preset_ses}</span>}
            </div>

            <div className="em-row em-row-hp mb-3">
              <label className="em-fld">
                <span className="label">{s.host}</span>
                <input className="input" dir="ltr" placeholder="smtp-relay.brevo.com" autoComplete="off"
                  value={form.host} onChange={(e) => set('host', e.target.value.trim())} />
              </label>
              <label className="em-fld">
                <span className="label">{s.port}</span>
                <input className="input" dir="ltr" type="number" min="1" max="65535"
                  value={form.port} onChange={(e) => set('port', e.target.value)} />
              </label>
            </div>

            <label className="em-fld mb-3">
              <span className="label">{s.security}</span>
              <select className="input" value={form.security} onChange={(e) => {
                const v = e.target.value
                setForm((f) => ({ ...f, security: v, port: v === 'ssl' && Number(f.port) === 587 ? 465 : v === 'starttls' && Number(f.port) === 465 ? 587 : f.port }))
              }}>
                <option value="starttls">{s.sec_starttls}</option>
                <option value="ssl">{s.sec_ssl}</option>
                <option value="none">{s.sec_none}</option>
              </select>
            </label>

            <div className="em-row em-row-2">
              <label className="em-fld">
                <span className="label">{s.username}</span>
                <input className="input" dir="ltr" autoComplete="off" value={form.username} onChange={(e) => set('username', e.target.value)} />
              </label>
              <div className="em-fld">
                <span className="label flex items-center gap-2">
                  {s.password}
                  {data.password_set && !clearPw && <span className="em-badge">{s.pw_saved}</span>}
                </span>
                <div className="em-pw" dir="ltr">
                  <input className="input" dir="ltr" type={showPw ? 'text' : 'password'} autoComplete="new-password"
                    placeholder={data.password_set ? '••••••••' : ''} value={pw}
                    onChange={(e) => { setPw(e.target.value); if (e.target.value) setClearPw(false) }} />
                  <button type="button" className="em-eye" onClick={() => setShowPw((v) => !v)} aria-label={s.password}>
                    <EyeIco off={showPw} />
                  </button>
                </div>
                {data.password_set && (
                  <span className="em-hint">
                    {clearPw
                      ? <>{s.pw_will_clear} · <button type="button" className="em-link" onClick={() => setClearPw(false)}>{s.undo}</button></>
                      : <>{s.pw_keep} · <button type="button" className="em-link" onClick={() => { setClearPw(true); setPw('') }}>{s.pw_clear}</button></>}
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="card">
            <div className="em-card-h">{s.from_h}</div>
            <div className="em-row em-row-2">
              <label className="em-fld">
                <span className="label">{s.from_email}</span>
                <input className="input" dir="ltr" type="email" placeholder={data.default_from}
                  value={form.from_email} onChange={(e) => set('from_email', e.target.value.trim())} />
              </label>
              <label className="em-fld">
                <span className="label">{s.from_name}</span>
                <input className="input" placeholder="Caspin Tunnel" value={form.from_name} onChange={(e) => set('from_name', e.target.value)} />
              </label>
            </div>
            <p className="em-hint mt-2">
              {form.from_email ? s.from_preview : s.from_default}: <bdi dir="ltr" className="font-medium">{fromPreview}</bdi>
            </p>
          </div>

          <div className="em-actions em-actions-bar">
            {dirty && <span className="me-auto text-xs text-muted">{s.unsaved}</span>}
            <button type="button" className="btn-ghost text-sm" disabled={!dirty || busy} onClick={() => apply(data)}>{s.reset}</button>
            <button type="submit" className="btn-primary text-sm" disabled={!dirty || busy}>{busy ? s.saving : s.save}</button>
          </div>
        </form>

        <div className="em-col">
          <div className="card">
            <div className="em-card-h">{s.status_h}</div>
            <div className="em-status">
              <div className="em-status-row">
                <span className="em-dot" style={{ background: srcOk ? 'var(--c-success)' : 'var(--c-warning)' }} />
                <span className="min-w-0">
                  {s.via}: <b>{srcLabel[data.effective_source] || data.effective_source}</b>
                  {data.effective_host && <span className="block text-xs text-muted" dir="ltr">{data.effective_host}:{data.effective_port}</span>}
                </span>
              </div>
              <div className="em-status-row">
                <span className="em-dot" style={{ background: data.last_success_at ? 'var(--c-success)' : 'var(--c-border)' }} />
                <span className="min-w-0">{s.last_ok}: <span className="text-muted">{when(data.last_success_at)}</span></span>
              </div>
              <div className="em-status-row">
                <span className="em-dot" style={{ background: data.last_error_at ? 'var(--c-danger)' : 'var(--c-border)' }} />
                <span className="min-w-0 flex-1">
                  {s.last_err}: <span className="text-muted">{when(data.last_error_at)}</span>
                  {data.last_error && <code className="em-code" dir="ltr">{data.last_error}</code>}
                </span>
              </div>
            </div>
          </div>

          <div className="card space-y-3">
            <div className="em-card-h" style={{ marginBottom: 0 }}>{s.test_h}</div>
            <p className="em-hint">{s.test_note}{dirty ? ` — ${s.unsaved}` : ''}</p>
            <label className="em-fld">
              <span className="label">{s.test_to}</span>
              <input className="input" dir="ltr" type="email" placeholder="you@example.com" value={to} onChange={(e) => setTo(e.target.value.trim())} />
            </label>
            <button type="button" className="btn-primary w-full text-sm" disabled={testing || !to} onClick={sendTest}>
              {testing ? s.testing : s.test_btn}
            </button>
            {result && (
              <div className={'em-result ' + (result.ok ? 'ok' : 'bad')} role="status">
                <b>{result.ok ? s.ok : s.fail}</b>
                {result.source && <span className="text-xs text-muted"> · {s.through} {srcLabel[result.source] || result.source}{result.host ? <span dir="ltr"> ({result.host}:{result.port})</span> : null}</span>}
                <div className="mt-1">{lang === 'en' ? result.en : result.fa}</div>
                {result.raw && <code className="em-code" dir="ltr">{s.raw}: {result.raw}</code>}
              </div>
            )}
          </div>

          <div className="card">
            <div className="em-card-h">{s.help_h}</div>
            <ul className="em-help space-y-1">{s.help.map((h) => <li key={h}>{h}</li>)}</ul>
          </div>
        </div>
      </div>
    </div>
  )
}
