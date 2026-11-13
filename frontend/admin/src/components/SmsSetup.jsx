// v1.60 the SMS auto-confirm tools, white-label (never our brand): «کد راه‌اندازی» for the Android app (one string = this
// store's address + a device token, pasted once in the app) and, on a store's panel, the whole «اپلیکیشن‌ها» page with a
// step-by-step guide to build the iPhone Shortcut themselves (our iCloud link points to our domain, so stores never get it).
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { digits } from '../lib/format'
import { copyToClipboard } from '../lib/clipboard'
import { useToast } from './Toast'
import { useAuth } from '../lib/auth'
import { Spinner } from './ui'

const T = {
  fa: {
    h1: 'اپلیکیشن‌ها', sub: 'ابزارهای گوشیِ دریافت‌کنندهٔ پیامک بانک برای تأیید خودکار پرداخت‌ها',
    app_name: 'تأیید پیامک خودکار',
    android_t: 'اپ اندروید «تأیید پیامک خودکار»',
    android_what: 'روی گوشی اندرویدی‌ای نصب می‌شود که پیامک واریز بانک به آن می‌رسد. هر پیامک بانکِ مجاز را فوراً به سایت شما می‌فرستد تا پرداخت مشتری خودکار تأیید شود.',
    a_steps: ['فایل را دانلود و روی گوشی نصب کنید (اجازهٔ «نصب از منابع ناشناس» را بدهید).', 'پایین همین کارت دستگاه را انتخاب کنید و «کد راه‌اندازی» را کپی کنید.',
      'در اپ «تنظیمات» ← «کد راه‌اندازی» را بچسبانید ← «اعمال و آزمایش اتصال».', 'اجازهٔ دریافت پیامک را بدهید و بهینه‌سازی باتری را برای اپ خاموش کنید.',
      'در «شماره‌های بانکی» شمارهٔ فرستندهٔ پیامک بانک را اضافه کنید.'],
    download: 'دانلود اپ', downloading: 'در حال دانلود…',
    not_ready: 'نسخهٔ جدید اپ در حال آماده‌سازی است و به‌زودی همین‌جا قابل دانلود می‌شود. کد راه‌اندازی را از همین حالا می‌توانید بسازید.',
    code_h: 'کد راه‌اندازی', device: 'دستگاه', pick: '— انتخاب دستگاه —', make: 'ساخت کد', copy: 'کپی', copied: 'کپی شد',
    code_hint: 'این کد شامل آدرس سایت و توکن دستگاه است — مثل رمز با آن رفتار کنید و برای کسی نفرستید.',
    no_dev: 'هنوز دستگاهی ثبت نشده.', add_dev: 'افزودن دستگاه', perm: 'برای ساخت کد، دسترسی «مدیریت دستگاه‌های پیامک» لازم است.',
    manual: 'ورود دستی (اگر کد کار نکرد)', server: 'آدرس سرور', token: 'توکن دستگاه', show_token: 'نمایش توکن',
    ios_t: 'آیفون: شورتکات تأیید پیامک', ios_what: 'آیفون اجازه نمی‌دهد اپ‌ها پیامک بخوانند؛ به‌جای اپ، با برنامهٔ Shortcuts (میانبرها) خود آیفون یک «اتوماسیون پیام» می‌سازید که هر پیامک بانک را به سایت شما می‌فرستد. ساختنش حدود ۵ دقیقه طول می‌کشد.',
    need: 'لازم: iOS 17 یا جدیدتر · یک دستگاه ثبت‌شده در پنل (برای توکن)', paste_h: 'این دو مقدار را در مرحلهٔ ۵ می‌چسبانید',
    endpoint: 'آدرس (URL)', test_h: 'آزمایش',
  },
  en: {
    h1: 'Apps', sub: 'Tools for the phone that receives the bank SMS, for automatic payment confirmation',
    app_name: 'SMS auto-confirm',
    android_t: 'Android app “SMS auto-confirm”',
    android_what: 'Install it on the Android phone that receives the bank deposit SMS. It forwards every allowed bank SMS to your site at once, so customer payments are confirmed automatically.',
    a_steps: ['Download the file and install it on the phone (allow “install unknown apps”).', 'Pick the device at the bottom of this card and copy the “setup code”.',
      'In the app: Settings → paste the setup code → “Apply and test”.', 'Grant the SMS permission and turn battery optimization off for the app.',
      'Add the bank’s SMS sender under “Bank numbers”.'],
    download: 'Download the app', downloading: 'Downloading…',
    not_ready: 'The new version of the app is being prepared and will be downloadable here soon. You can already create the setup code.',
    code_h: 'Setup code', device: 'Device', pick: '— pick a device —', make: 'Create code', copy: 'Copy', copied: 'Copied',
    code_hint: 'This code holds your site address and the device token — treat it like a password, never send it to anyone.',
    no_dev: 'No device yet.', add_dev: 'Add device', perm: 'Creating a code needs the “manage SMS devices” permission.',
    manual: 'Manual entry (if the code does not work)', server: 'Server address', token: 'Device token', show_token: 'Show token',
    ios_t: 'iPhone: SMS confirm shortcut', ios_what: 'iOS does not let apps read SMS. Instead you build a “Message automation” in the iPhone’s own Shortcuts app that forwards every bank SMS to your site. It takes about 5 minutes.',
    need: 'Needs: iOS 17 or later · a device registered in the panel (for its token)', paste_h: 'You paste these two values in step 5',
    endpoint: 'URL', test_h: 'Test',
  },
}

// the guide: each step has its text and a small drawing of the iPhone screen (labels as iOS shows them, in English)
const STEPS = {
  fa: [
    { t: 'در پنل یک دستگاه برای این آیفون بسازید (پایین همین کارت «دستگاه» را انتخاب کنید) — آدرس و توکن آن را لازم دارید.', s: null },
    { t: 'برنامهٔ Shortcuts (میانبرها) را باز کنید ← زبانهٔ پایین «Automation» ← دکمهٔ «+» یا «New Automation».', s: 'auto' },
    { t: '«Message» را انتخاب کنید. «Sender» = فرستندهٔ پیامک بانک (یا «Message Contains» با یک کلمهٔ ثابت پیامک بانک مثل «واریز»). «Run Immediately» را انتخاب و «Notify When Run» را خاموش کنید ← Next.', s: 'message' },
    { t: '«New Blank Automation» ← «Add Action» ← در جستجو بنویسید Get Contents of URL و آن را انتخاب کنید.', s: 'action' },
    { t: 'در اکشن: جای «URL» آدرس پایین را بچسبانید. فلش «‹›» یا «Show More» را بزنید: Method = POST · Headers ← Add new header: کلید X-Device-Token و مقدار = توکن دستگاه · Request Body = JSON ← Add new field ← Text: کلید text و مقدار = «Shortcut Input» (روی آن بزنید و Content را انتخاب کنید) · یک فیلد Text دیگر: کلید sender و مقدار = Shortcut Input ← Sender.', s: 'url' },
    { t: '«Done» را بزنید. اتوماسیون آماده است؛ از این به بعد هر پیامک بانک خودکار به سایت شما می‌رود.', s: 'done' },
  ],
  en: [
    { t: 'Create a device for this iPhone in the panel (pick the “Device” at the bottom of this card) — you need its address and token.', s: null },
    { t: 'Open the Shortcuts app → bottom tab “Automation” → the “+” button or “New Automation”.', s: 'auto' },
    { t: 'Choose “Message”. “Sender” = the bank’s SMS sender (or “Message Contains” with a fixed word of the bank SMS). Choose “Run Immediately” and turn “Notify When Run” off → Next.', s: 'message' },
    { t: '“New Blank Automation” → “Add Action” → search Get Contents of URL and pick it.', s: 'action' },
    { t: 'In the action: paste the URL below. Tap the “‹›” arrow / “Show More”: Method = POST · Headers → Add new header: key X-Device-Token, value = the device token · Request Body = JSON → Add new field → Text: key text, value = “Shortcut Input” (tap it, choose Content) · another Text field: key sender, value = Shortcut Input → Sender.', s: 'url' },
    { t: 'Tap “Done”. The automation is ready — from now on every bank SMS goes to your site by itself.', s: 'done' },
  ],
}
const TEST = {
  fa: ['از یک گوشی دیگر به این آیفون پیامکی بفرستید که همان کلمهٔ مرحلهٔ ۳ را دارد (اگر «Sender» را انتخاب کرده‌اید، منتظر یک واریز واقعی بمانید).', 'در پنل ← «لاگ پیامک» باید همان پیامک دیده شود. اگر نیامد: توکن، آدرس و کلید X-Device-Token را دوباره بررسی کنید.'],
  en: ['From another phone send this iPhone an SMS that contains the word from step 3 (if you chose “Sender”, wait for a real deposit).', 'Panel → “SMS log” should show that SMS. If not: check the token, the URL and the X-Device-Token key again.'],
}

function Phone({ kind }) {
  // tiny drawings of the iPhone screens (not screenshots): which button to look for
  const screens = {
    auto: <><div className="ip-nav">Automation <b>+</b></div><div className="ip-row ip-hl">New Automation</div><div className="ip-tabs"><span>Shortcuts</span><span className="on">Automation</span><span>Gallery</span></div></>,
    message: <><div className="ip-nav">New Automation</div><div className="ip-row">Email</div><div className="ip-row ip-hl">Message</div><div className="ip-row">Run Immediately ✓</div></>,
    action: <><div className="ip-nav">New Blank Automation</div><div className="ip-search">Get Contents of URL</div><div className="ip-row ip-hl">Get Contents of URL</div></>,
    url: <><div className="ip-nav">Get Contents of URL</div><div className="ip-row">URL: https://…/inbound/</div><div className="ip-row">Method: POST</div><div className="ip-row ip-hl">X-Device-Token</div><div className="ip-row">text · sender</div></>,
    done: <><div className="ip-nav">Automation</div><div className="ip-row ip-ok">When I get a message… ✓</div></>,
  }
  return <div className="ip" aria-hidden="true"><div className="ip-notch" />{screens[kind]}</div>
}

function CopyRow({ label, value, s, secret }) {
  const toast = useToast()
  return (
    <div className="sx-copy">
      <span className="sx-copy-l">{label}</span>
      <div className="sx-copy-v">
        <code dir="ltr" className={secret ? 'sx-secret' : ''}>{value}</code>
        <button type="button" className="sx-copy-btn" onClick={async () => { if (await copyToClipboard(value)) toast.success(s.copied) }}>{s.copy}</button>
      </div>
    </div>
  )
}

/** Pick an SMS device → its setup code (Android) or token (iPhone). Needs sms.manage. */
export function DeviceSecret({ mode = 'code', server }) {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const { can } = useAuth()
  const toast = useToast()
  const [devices, setDevices] = useState(null)
  const [dev, setDev] = useState('')
  const [out, setOut] = useState(null)
  const [busy, setBusy] = useState(false)
  const allowed = can('sms.manage')
  useEffect(() => {
    if (!allowed) return
    api.get('/admin/sms-devices/?limit=100').then((r) => setDevices((r.data.results || r.data || []).filter((d) => d.is_active !== false)))
      .catch(() => setDevices([]))
  }, [allowed])
  useEffect(() => { setOut(null) }, [dev])
  if (!allowed) return <p className="text-xs text-muted">{s.perm}</p>
  if (devices === null) return <Spinner />
  const make = async () => {
    setBusy(true)
    try {
      const { data } = await api.get(`/admin/sms-devices/${dev}/${mode === 'code' ? 'setup-code' : 'token'}/`)
      setOut(data)
    } catch (e) { toast.error(apiError(e)) } finally { setBusy(false) }
  }
  return (
    <div className="sx-dev" data-testid={`device-${mode}`}>
      {devices.length === 0 ? (
        <p className="text-xs text-muted">{s.no_dev} <Link className="sx-link" to="/settings/sms-devices">{s.add_dev}</Link></p>
      ) : (
        <div className="sx-pick">
          <label className="sx-fld"><span className="label">{s.device}</span>
            <select className="input" value={dev} onChange={(e) => setDev(e.target.value)}>
              <option value="">{s.pick}</option>
              {devices.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select></label>
          <button type="button" className="btn-primary text-sm sx-btn" disabled={!dev || busy} onClick={make}>
            {busy ? <Spinner /> : mode === 'code' ? s.make : s.show_token}</button>
        </div>
      )}
      {out?.code && <CopyRow label={s.code_h} value={out.code} s={s} secret />}
      {out?.api_token && <CopyRow label={s.token} value={out.api_token} s={s} secret />}
      {out && <p className="sx-warn">{s.code_hint}</p>}
      {mode === 'code' && server && (
        <details className="sx-manual"><summary>{s.manual}</summary>
          <CopyRow label={s.server} value={server} s={s} />
          {dev && <DeviceToken id={dev} s={s} />}
        </details>
      )}
    </div>
  )
}

function DeviceToken({ id, s }) {
  const [tok, setTok] = useState('')
  const toast = useToast()
  useEffect(() => { setTok('') }, [id])
  if (tok) return <CopyRow label={s.token} value={tok} s={s} secret />
  return <button type="button" className="sx-act" onClick={() => api.get(`/admin/sms-devices/${id}/token/`).then((r) => setTok(r.data.api_token)).catch((e) => toast.error(apiError(e)))}>{s.show_token}</button>
}

/** A store's whole «اپلیکیشن‌ها» page (white-label). */
export function StoreApps() {
  const { lang, t } = useI18n()
  const s = T[lang] || T.fa
  const toast = useToast()
  const [rows, setRows] = useState(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    api.get('/admin/apps/').then((r) => setRows(r.data.results)).catch((e) => { setRows([]); toast.error(apiError(e, t('load_error'))) })
  }, [])
  if (rows === null) return <div className="grid place-items-center py-16"><Spinner /></div>
  const android = rows.find((r) => r.platform === 'android') || {}
  const ios = rows.find((r) => r.platform === 'ios') || {}
  const download = async () => {
    setBusy(true)
    try {
      const r = await api.get('/admin/apps/android/download/', { responseType: 'blob' })
      const url = URL.createObjectURL(r.data)
      const a = document.createElement('a'); a.href = url; a.download = android.file_name || 'sms-confirm.apk'
      document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 4000)
    } catch (e) { toast.error(apiError(e)) } finally { setBusy(false) }
  }
  return (
    <div className="sx space-y-5" data-testid="store-apps">
      <style>{CSS}</style>
      <div>
        <h1 className="text-lg font-bold">{s.h1}</h1>
        <p className="text-sm text-muted mt-1">{s.sub}</p>
      </div>
      <div className="sx-cards">
        <section className="card sx-card" data-testid="store-apps-android">
          <div className="sx-head"><AppIcon /><div><h2 className="sx-title">{s.android_t}</h2>
            {android.version && <span className="sx-chip">{digits(android.version, lang)}</span>}</div></div>
          <p className="sx-what">{s.android_what}</p>
          <ol className="sx-steps">{s.a_steps.map((x, i) => <li key={x}><b>{digits(i + 1, lang)}</b><span>{x}</span></li>)}</ol>
          {android.source ? (
            <button type="button" className="btn-primary sx-dl" onClick={download} disabled={busy} data-testid="store-apk-download">
              {busy ? <><Spinner />{s.downloading}</> : s.download}</button>
          ) : <p className="sx-note" data-testid="store-apk-not-ready">{s.not_ready}</p>}
          <h3 className="sx-h3">{s.code_h}</h3>
          <DeviceSecret mode="code" server={android.server} />
        </section>
        <section className="card sx-card" data-testid="store-apps-ios">
          <div className="sx-head"><span className="sx-ico" aria-hidden="true"><svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="6" y="2" width="12" height="20" rx="3" /><path d="M11 18h2" /></svg></span>
            <div><h2 className="sx-title">{s.ios_t}</h2><span className="sx-chip">{s.need}</span></div></div>
          <p className="sx-what">{s.ios_what}</p>
          <ol className="sx-guide" data-testid="ios-guide">
            {(STEPS[lang] || STEPS.fa).map((x, i) => (
              <li key={i} className="sx-g">
                <div className="sx-g-t"><b>{digits(i + 1, lang)}</b><span>{x.t}</span></div>
                {x.s && <Phone kind={x.s} />}
                {i === 4 && (
                  <div className="sx-paste"><span className="sx-h3">{s.paste_h}</span>
                    <CopyRow label={s.endpoint} value={ios.endpoint || ''} s={s} />
                    <DeviceSecret mode="token" />
                  </div>
                )}
              </li>
            ))}
          </ol>
          <h3 className="sx-h3">{s.test_h}</h3>
          <ol className="sx-steps">{(TEST[lang] || TEST.fa).map((x, i) => <li key={x}><b>{digits(i + 1, lang)}</b><span>{x}</span></li>)}</ol>
        </section>
      </div>
    </div>
  )
}

/** The new app's icon (same drawing as mobile_sms/…/ic_launcher_foreground.xml): a message bubble with a check. */
export function AppIcon({ size = 48 }) {
  return (
    <svg className="sx-appicon" viewBox="0 0 108 108" width={size} height={size} aria-hidden="true">
      <rect width="108" height="108" rx="24" fill="#0F766E" />
      <path d="M30 34h48a6 6 0 0 1 6 6v26a6 6 0 0 1-6 6H50l-12 10v-10h-8a6 6 0 0 1-6-6V40a6 6 0 0 1 6-6z" fill="#FFFFFF" />
      <path d="M41 53l9 9 17-17" fill="none" stroke="#0F766E" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export const SX_CSS = `
.sx-copy { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.sx-copy-l { font-size: 12px; font-weight: 700; color: var(--c-text-muted); }
.sx-copy-v { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 12px; border: 1px solid var(--c-border); min-width: 0; }
.sx-copy-v code { flex: 1; min-width: 0; font-size: 12.5px; overflow-wrap: anywhere; }
.sx-copy-btn, .sx-act { display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; font-size: 12.5px; font-weight: 700;
  padding: 0 12px; min-height: 44px; min-width: 44px; border-radius: 10px; color: var(--c-text); border: 1px solid var(--c-border); background: var(--c-bg); }
.sx-dev { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.sx-pick { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 8px; }
.sx-fld { display: flex; flex-direction: column; gap: 6px; flex: 1 1 200px; min-width: 0; }
.sx-fld .input { min-height: 44px; }
.sx-btn { min-height: 44px; display: inline-flex; align-items: center; gap: 6px; }
.sx-warn { font-size: 12px; line-height: 1.8; margin: 0; color: var(--c-warning-fg); }
.sx-link { font-weight: 700; text-decoration: underline; text-decoration-color: var(--c-primary); }
.sx-manual { border: 1px dashed var(--c-border); border-radius: 12px; padding: 0 12px; }
.sx-manual summary { min-height: 44px; display: flex; align-items: center; cursor: pointer; font-size: 12.5px; font-weight: 700; color: var(--c-text-muted); }
.sx-manual[open] { padding-bottom: 12px; }
.sx-manual[open] > * + * { margin-top: 8px; }
@media (max-width: 767px) { .sx-fld .input { font-size: 16px; } .sx-btn { flex: 1 1 100%; justify-content: center; } }
`

const CSS = SX_CSS + `
.sx-cards { display: grid; grid-template-columns: minmax(0, 1fr); gap: 16px; }
@media (min-width: 1100px) { .sx-cards { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); align-items: start; } }
.sx-card { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.sx-head { display: flex; gap: 12px; align-items: flex-start; }
.sx-head > div { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.sx-ico { width: 48px; height: 48px; border-radius: 14px; display: grid; place-items: center; flex: 0 0 auto; color: #1464BA;
  background: color-mix(in srgb, #1464BA 13%, transparent); }
.sx-appicon { flex: 0 0 auto; border-radius: 14px; }
.sx-title { font-size: 16px; font-weight: 800; }
.sx-chip { align-self: flex-start; font-size: 11.5px; padding: 2px 8px; border-radius: 999px; color: var(--c-muted-fg); background: color-mix(in srgb, var(--c-text-muted) 11%, transparent); }
.sx-what { font-size: 13.5px; line-height: 2; }
.sx-h3 { font-size: 13px; font-weight: 800; }
.sx-steps { display: flex; flex-direction: column; gap: 8px; font-size: 13px; line-height: 1.9; }
.sx-steps li, .sx-g-t { display: flex; gap: 9px; align-items: flex-start; }
.sx-steps b, .sx-g-t b { width: 24px; height: 24px; flex-shrink: 0; border-radius: 999px; display: grid; place-items: center; font-size: 12px; margin-top: 2px;
  color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 12%, transparent); }
.sx-dl { align-self: flex-start; min-height: 44px; display: inline-flex; align-items: center; gap: 8px; }
.sx-note { font-size: 12.5px; line-height: 1.9; padding: 10px 12px; border-radius: 12px; margin: 0;
  background: color-mix(in srgb, var(--c-warning) 12%, transparent); border: 1px solid color-mix(in srgb, var(--c-warning) 32%, transparent); }
.sx-guide { display: flex; flex-direction: column; gap: 12px; }
.sx-g { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px; align-items: start; padding: 12px; border-radius: 14px; border: 1px solid var(--c-border); font-size: 13px; line-height: 1.95; }
.sx-g > .sx-paste { grid-column: 1 / -1; display: flex; flex-direction: column; gap: 10px; }
.ip { width: 132px; border-radius: 22px; padding: 18px 8px 10px; background: #111827; display: flex; flex-direction: column; gap: 5px; position: relative; direction: ltr;
  font: 600 10.5px/1.35 Inter, system-ui, sans-serif; color: #e5e7eb; box-shadow: 0 0 0 2px color-mix(in srgb, var(--c-text-muted) 30%, transparent); }
.ip-notch { position: absolute; top: 6px; left: 50%; width: 40px; height: 6px; margin-left: -20px; border-radius: 6px; background: #374151; }
.ip-nav { display: flex; justify-content: space-between; font-weight: 800; font-size: 11px; color: #fff; padding: 2px 4px 4px; }
.ip-nav b { color: #60a5fa; }
.ip-row, .ip-search { padding: 6px; border-radius: 8px; background: #1f2937; overflow-wrap: anywhere; }
.ip-search { background: #374151; color: #cbd5e1; }
.ip-hl { background: #2563eb; color: #fff; }
.ip-ok { background: #166534; color: #fff; }
.ip-tabs { display: flex; justify-content: space-between; font-size: 9px; color: #9ca3af; padding-top: 4px; }
.ip-tabs .on { color: #60a5fa; }
@media (max-width: 560px) {
  .sx-g { grid-template-columns: minmax(0, 1fr); }
  .ip { justify-self: center; }
  .sx-dl { align-self: stretch; justify-content: center; }
}
`
