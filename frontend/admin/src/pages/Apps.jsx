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
    ios_what: 'آیفون اجازه نمی‌دهد اپ‌ها پیامک‌ها را بخوانند؛ به‌جای اپ، یک شورتکات (Shortcuts) با «اتوماسیون پیام» پیامک‌های بانک را به همان آدرس سرور می‌فرستد تا پرداخت‌ها مثل اپ اندروید خودکار تأیید شوند. نصب رسمی از لینک iCloud است (آیفون فقط شورتکات امضاشده را می‌پذیرد).',
    features: 'چه کاری انجام می‌دهد؟', setup: 'راه‌اندازی',
    a_f: ['فقط پیامک‌های شماره‌های بانکیِ تعریف‌شده ارسال می‌شود', 'اجرای دائمی در پس‌زمینه و شروع خودکار پس از روشن شدن گوشی', 'ارسال مجدد خودکار در صورت قطعی اینترنت (تا 3 بار)', 'نمایش وضعیت اتصال و 20 پیامک آخر در خود اپ'],
    a_s: ['فایل APK را دانلود و روی گوشی نصب کنید (اجازهٔ «نصب از منابع ناشناس» را بدهید).', 'در پنل: تنظیمات ← دستگاه‌های SMS ← «افزودن دستگاه» و توکن ساخته‌شده را کپی کنید.', 'در اپ آدرس سرور (پایین همین صفحه) و توکن را وارد و «تست اتصال» را بزنید.', 'مجوز دریافت پیامک را بدهید و بهینه‌سازی باتری را برای اپ خاموش کنید.', 'در تنظیمات ← شماره‌های بانکی، شمارهٔ فرستندهٔ پیامک بانک را اضافه کنید.'],
    i_f: ['اتوماسیون «وقتی پیامی از فرستندهٔ بانک رسید» روی خود آیفون', 'ارسال متن پیامک به سرور با توکن همان دستگاه', 'بدون نصب اپ و بدون نیاز به App Store'],
    i_s: ['در پنل: تنظیمات ← دستگاه‌های SMS ← «افزودن دستگاه» برای این آیفون.', 'روی آیفون «نصب از iCloud» را بزنید (یا کد QR را با دوربین آیفون اسکن کنید) و «Add Shortcut» را بزنید.', 'هنگام نصب، آدرس سرور و توکن دستگاه (همین کارت) را در فیلدهای خواسته‌شده وارد کنید.', 'Shortcuts ← Automation ← «Message»: فرستندهٔ بانک ← اجرای همین شورتکات با «Shortcut Input» ← «Run Immediately» را روشن کنید.'],
    server: 'آدرس دریافت پیامک در سرور', header: 'هدر احراز هویت', body: 'بدنهٔ درخواست (JSON)',
    copy: 'کپی', copied: 'کپی شد', download: 'دانلود از سرور', downloading: 'در حال دانلود…',
    none_file: 'هنوز فایلی بارگذاری نشده است', version: 'نسخه', size: 'حجم', updated: 'به‌روزرسانی', by: 'توسط',
    src_bundled: 'نسخهٔ همراه سامانه', src_upload: 'بارگذاری‌شده توسط ادمین', icloud: 'لینک iCloud (نیاز به اینترنت)',
    manage: 'بارگذاری نسخهٔ جدید', file: 'فایل', file_hint_android: 'فایل ‎.apk‎ — حداکثر 60 مگابایت', file_hint_ios: 'فایل ‎.shortcut‎',
    link: 'لینک خارجی (اختیاری)', notes: 'یادداشت / توضیحات نسخه', save: 'ذخیره', saved: 'ذخیره شد', clear: 'حذف فایل بارگذاری‌شده',
    devices_link: 'مدیریت دستگاه‌های SMS', notes_h: 'یادداشت نسخه', mb: 'مگابایت',
    src_repo: 'از مخزن کد (منبع واحد)', device: 'توکن کدام دستگاه داخل فایل قرار گیرد؟', device_none: 'هیچ — توکن هنگام افزودن پرسیده شود',
    manage_ios: 'تنظیمات شورتکات (لینک iCloud و یادداشت)',
    ios_single: 'منبع شورتکات فایل ‎mobile_shortcut/‎ در مخزن است. با هر تغییر: آن را روی آیفون دوباره وارد کنید، از Share ← Copy iCloud Link لینک جدید بسازید، اینجا ذخیره کنید و نسخه و تغییرات را در ‎mobile_shortcut/‎ ثبت کنید.',
    icloud_install: 'نصب از iCloud', icloud_scan: 'برای نصب از روی صفحهٔ دسکتاپ، این کد را با دوربین آیفون اسکن کنید',
    icloud_missing: 'لینک iCloud شورتکات هنوز تنظیم نشده است: شورتکات را یک‌بار روی آیفون وارد کنید، از Share ← Copy iCloud Link لینک بگیرید و در «تنظیمات شورتکات» پایین همین کارت ذخیره کنید.',
    icloud_field: 'لینک iCloud شورتکات', icloud_field_hint: 'باید با https://www.icloud.com/shortcuts/ شروع شود. توکن را هرگز در لینک قرار ندهید.',
    icloud_bad: 'لینک باید با https://www.icloud.com/shortcuts/ شروع شود',
    token_h: 'اطلاعات نصب', token_hint: 'هنگام نصب، توکن را در فیلد خواسته‌شده وارد کنید',
    token_dev: 'دستگاه این آیفون', token_pick: '— انتخاب دستگاه —', token_show: 'نمایش توکن', token_l: 'توکن دستگاه',
    token_none: 'هنوز دستگاه SMS فعالی ثبت نشده است.', token_perm: 'برای دیدن توکن، مجوز «مدیریت دستگاه‌های SMS» لازم است.',
    endpoint_l: 'آدرس سرور',
    adv: 'پیشرفته: فایل امضانشده (نیاز به امضا روی macOS)',
    adv_why: 'آیفون (iOS 15 به بعد) فایل امضانشده را نمی‌پذیرد و خطای «Importing unsigned shortcut files is not supported» می‌دهد. این فایل را فقط اگر به مک دسترسی دارید دانلود کنید و روی مک امضا کنید:',
    adv_cmd: 'دستور امضا روی macOS', adv_inject: 'توکن دستگاه انتخاب‌شده داخل فایل قرار گیرد',
    adv_warn: 'فایل امضاشده‌ای را که توکن داخلش است با هیچ‌کس به اشتراک نگذارید و جایی بارگذاری نکنید — هر کس آن را داشته باشد می‌تواند به‌جای این دستگاه برای سرور پیامک بفرستد. برای اشتراک‌گذاری فقط از لینک iCloud (بدون توکن) استفاده کنید.',
    download_unsigned: 'دانلود فایل امضانشده',
  },
  en: {
    h1: 'Apps & tools', sub: 'Tools for the phone that receives the bank SMS, for automatic payment confirmation — downloaded straight from your own server',
    android_t: 'Android SMS Bridge app', ios_t: 'iPhone Shortcut',
    android_what: 'Install this on the Android phone that receives the bank deposit SMS. It instantly forwards every SMS from an allowed bank sender to the server, which matches the amount to an order and confirms the payment automatically — no manual approval.',
    ios_what: "iOS doesn't let apps read SMS, so instead a Shortcut with a Message automation forwards the bank SMS to the same server endpoint, so payments are auto-confirmed just like with the Android app. The official install is the iCloud link (iOS only imports signed shortcuts).",
    features: 'What it does', setup: 'Setup',
    a_f: ['Only SMS from the configured bank numbers are forwarded', 'Runs permanently in the background and restarts after a reboot', 'Automatic retry when the connection drops (up to 3 times)', 'Shows the connection status and the last 20 SMS in the app'],
    a_s: ['Download the APK and install it on the phone (allow "install unknown apps").', 'In the panel: Settings → SMS devices → "Add device", copy the generated token.', 'In the app enter the server address (below) and the token, then tap "Test connection".', 'Grant the SMS permission and turn battery optimization off for the app.', 'In Settings → Bank numbers add the sender number of the bank SMS.'],
    i_f: ['A "when a message from the bank arrives" automation on the iPhone', 'Sends the SMS text to the server with that device\'s token', 'Nothing to install, no App Store needed'],
    i_s: ['In the panel: Settings → SMS devices → "Add device" for this iPhone.', 'On the iPhone tap "Install via iCloud" (or scan the QR code with the iPhone camera) and tap "Add Shortcut".', 'While installing, enter the server address and the device token (on this card) in the fields it asks for.', 'Shortcuts → Automation → "Message": the bank sender → run this shortcut with "Shortcut Input" → turn "Run Immediately" on.'],
    server: 'SMS endpoint on the server', header: 'Auth header', body: 'Request body (JSON)',
    copy: 'Copy', copied: 'Copied', download: 'Download from server', downloading: 'Downloading…',
    none_file: 'No file uploaded yet', version: 'Version', size: 'Size', updated: 'Updated', by: 'by',
    src_bundled: 'Bundled with the system', src_upload: 'Uploaded by an admin', icloud: 'iCloud link (needs internet)',
    manage: 'Upload a new version', file: 'File', file_hint_android: '.apk file — max 60 MB', file_hint_ios: '.shortcut file',
    link: 'External link (optional)', notes: 'Notes / release notes', save: 'Save', saved: 'Saved', clear: 'Remove uploaded file',
    devices_link: 'Manage SMS devices', notes_h: 'Release notes', mb: 'MB',
    src_repo: 'From the repository (single source)', device: 'Put which device\'s token in the file?', device_none: 'None — ask for the token when adding',
    manage_ios: 'Shortcut settings (iCloud link & notes)',
    ios_single: 'The shortcut\'s source is mobile_shortcut/ in the repository. After every change: re-import it on an iPhone, create a new link with Share → Copy iCloud Link, save it here, and bump the version + changelog in mobile_shortcut/.',
    icloud_install: 'Install via iCloud', icloud_scan: 'Installing from a desktop screen? Scan this code with the iPhone camera',
    icloud_missing: 'The iCloud link is not set yet: import the shortcut on an iPhone once, use Share → Copy iCloud Link and save the link under "Shortcut settings" at the bottom of this card.',
    icloud_field: 'Shortcut iCloud link', icloud_field_hint: 'Must start with https://www.icloud.com/shortcuts/. Never put a token in the link.',
    icloud_bad: 'The link must start with https://www.icloud.com/shortcuts/',
    token_h: 'Install details', token_hint: 'When installing, enter the token in the field it asks for',
    token_dev: 'Device for this iPhone', token_pick: '— pick a device —', token_show: 'Show token', token_l: 'Device token',
    token_none: 'No active SMS device yet.', token_perm: 'Showing the token needs the "manage SMS devices" permission.',
    endpoint_l: 'Server address',
    adv: 'Advanced: unsigned file (needs signing on macOS)',
    adv_why: 'iOS 15+ rejects unsigned files ("Importing unsigned shortcut files is not supported"). Download this only if you have a Mac, and sign it there:',
    adv_cmd: 'Signing command (macOS)', adv_inject: "Put the selected device's token into the file",
    adv_warn: 'Never share or upload a signed file that contains a token — anyone who has it can send SMS to the server as this device. To share, use only the iCloud link (it has no token).',
    download_unsigned: 'Download unsigned file',
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
  cloud: <path d="M7 18a4.5 4.5 0 01-.6-8.96A6 6 0 0118 8.5a4 4 0 01-.5 9.5H7z" />,
  warn: <><path d="M12 9v4m0 4h.01" /><path d="M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z" /></>,
}

export const ICLOUD_PREFIX = 'https://www.icloud.com/shortcuts/'
const SIGN_CMD = 'shortcuts sign --mode anyone -i CaspinSMS.shortcut -o CaspinSMS-signed.shortcut'

/** iPhone: the official install is the iCloud link (+ QR for a desktop screen).
 *  The device token is fetched through the authenticated API and shown here only —
 *  it never goes into the iCloud link or this page's URL. */
function IosInstall({ info, s, devices, canSms, endpoint, download, busy }) {
  const toast = useToast()
  const [qr, setQr] = useState(null)
  const [dev, setDev] = useState('')
  const [token, setToken] = useState('')
  const [loadingTok, setLoadingTok] = useState(false)
  const [inject, setInject] = useState(false)
  useEffect(() => {
    setQr(null)
    if (!info.icloud_url) return undefined
    let url
    api.get('/admin/apps/ios/qr/', { responseType: 'blob' })
      .then((r) => { url = URL.createObjectURL(r.data); setQr(url) })
      .catch(() => setQr(null))
    return () => { if (url) URL.revokeObjectURL(url) }
  }, [info.icloud_url])
  useEffect(() => { setToken('') }, [dev])

  const showToken = async () => {
    if (!dev) return
    setLoadingTok(true)
    try {
      const { data } = await api.get(`/admin/sms-devices/${dev}/token/`)
      setToken(data.api_token || '')
    } catch (e) { toast.error(apiError(e)) } finally { setLoadingTok(false) }
  }

  return (
    <div className="ap-ios">
      {info.icloud_url ? (
        <div className="ap-ios-install">
          <div className="ap-ios-cta">
            <a className="btn-primary ap-dl" href={info.icloud_url} target="_blank" rel="noreferrer noopener">
              <Ico d={I.cloud} />{s.icloud_install}
            </a>
            <code dir="ltr" className="ap-ios-url">{info.icloud_url}</code>
          </div>
          <figure className="ap-qr">
            {qr ? <img src={qr} alt={s.icloud_install} width="148" height="148" /> : <span className="ap-qr-ph"><Spinner /></span>}
            <figcaption>{s.icloud_scan}</figcaption>
          </figure>
        </div>
      ) : (
        <div className="ap-alert"><Ico d={I.warn} w={16} /><span>{s.icloud_missing}</span></div>
      )}

      <div className="ap-tok">
        <h3 className="ap-h3">{s.token_h}</h3>
        <CopyRow label={s.endpoint_l} value={endpoint} s={s} />
        {!canSms ? <p className="text-xs text-muted">{s.token_perm}</p>
          : devices.length === 0 ? <p className="text-xs text-muted">{s.token_none} <Link to="/settings/sms-devices" className="ap-inline-link">{s.devices_link}</Link></p>
          : (
            <>
              <div className="ap-tok-pick">
                <label className="ap-fld">
                  <span className="label">{s.token_dev}</span>
                  <select className="input" value={dev} onChange={(e) => setDev(e.target.value)}>
                    <option value="">{s.token_pick}</option>
                    {devices.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                  </select>
                </label>
                <button type="button" className="btn-ghost ap-link" onClick={showToken} disabled={!dev || loadingTok}>
                  {loadingTok ? <Spinner /> : s.token_show}
                </button>
              </div>
              {token && <CopyRow label={s.token_l} value={token} s={s} />}
            </>
          )}
        <p className="ap-tok-hint"><Ico d={I.check} w={14} />{s.token_hint}</p>
      </div>

      <details className="ap-adv">
        <summary><Ico d={I.download} w={16} />{s.adv}</summary>
        <div className="ap-adv-body">
          <p className="text-xs text-muted leading-relaxed">{s.adv_why}</p>
          <CopyRow label={s.adv_cmd} value={SIGN_CMD} s={s} />
          {canSms && dev && (
            <label className="ap-check">
              <input type="checkbox" checked={inject} onChange={(e) => setInject(e.target.checked)} />
              <span>{s.adv_inject}</span>
            </label>
          )}
          <div className="ap-alert ap-alert--danger"><Ico d={I.warn} w={16} /><span>{s.adv_warn}</span></div>
          <div className="ap-actions">
            <button type="button" className="btn-ghost ap-link" onClick={() => download(inject && dev ? dev : '')} disabled={!info.source || busy}>
              {busy ? <><Spinner />{s.downloading}</> : <><Ico d={I.download} w={16} />{s.download_unsigned}</>}
            </button>
          </div>
        </div>
      </details>
    </div>
  )
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

function AppCard({ info, s, lang, onSaved, endpoint }) {
  const toast = useToast()
  const android = info.platform === 'android'
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState(false)
  const [f, setF] = useState({ version: info.version || '', link: info.link || '', icloud_url: info.icloud_url || '', notes: info.notes || '', file: null })
  const [saving, setSaving] = useState(false)
  const tone = android ? '#11AB53' : '#1464BA'
  const hasFile = !!info.source
  const { can } = useAuth()
  const [devices, setDevices] = useState([])
  useEffect(() => {
    if (android || !can('sms.manage')) return
    api.get('/admin/sms-devices/?limit=100')
      .then((r) => setDevices((r.data.results || r.data || []).filter((d) => d.is_active !== false)))
      .catch(() => setDevices([]))
  }, [android])

  const download = async (deviceId = '') => {
    setBusy(true)
    try {
      const q = !android && deviceId ? `?device=${encodeURIComponent(deviceId)}` : ''
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
      if (!android) {
        const url = f.icloud_url.trim()
        if (url && !url.startsWith(ICLOUD_PREFIX)) { toast.error(s.icloud_bad); setSaving(false); return }
        fd.append('icloud_url', url)
      }
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

      {android ? (
        <div className="ap-actions">
          <button type="button" className="btn-primary ap-dl" onClick={() => download()} disabled={!hasFile || busy}>
            {busy ? <><span className="ap-spin" />{s.downloading}</> : <><Ico d={I.download} />{s.download}</>}
          </button>
          {!hasFile && <span className="text-xs text-muted">{s.none_file}</span>}
          {info.link && (
            <a className="btn-ghost ap-link" href={info.link} target="_blank" rel="noreferrer"><Ico d={I.link} w={16} />{info.link}</a>
          )}
          <Link to="/settings/sms-devices" className="btn-ghost ap-link">{s.devices_link}</Link>
        </div>
      ) : (
        <IosInstall info={info} s={s} devices={devices} canSms={can('sms.manage')} endpoint={info.endpoint || endpoint}
          download={download} busy={busy} />
      )}

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
              <label className="ap-fld ap-fld--wide">
                <span className="label">{s.icloud_field}</span>
                <input className="input" dir="ltr" type="url" inputMode="url" autoComplete="off" spellCheck={false}
                  value={f.icloud_url} onChange={(e) => setF((p) => ({ ...p, icloud_url: e.target.value }))}
                  placeholder={`${ICLOUD_PREFIX}…`} aria-invalid={!!f.icloud_url.trim() && !f.icloud_url.trim().startsWith(ICLOUD_PREFIX)} />
                <span className="text-xs text-muted">{s.icloud_field_hint}</span>
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
            {rows.map((r) => <AppCard key={r.platform} info={r} s={s} lang={lang} onSaved={replace} endpoint={endpoint} />)}
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
/* readable copy button (the brand fill as text is too light in some themes) */
.ap-copy-btn { color: var(--c-text) !important; }
.ap-copy-btn svg { color: var(--c-primary); }
/* phones + touch: every control on this page reaches 44px */
@media (max-width: 767px), (pointer: coarse) {
  .ap-copy-btn, .ap-dl, .ap-link, .ap-adv summary, .ap-manage summary { min-height: 44px !important; }
  .ap-copy-btn { min-width: 44px; justify-content: center; }
  .ap-check { min-height: 44px; }
  .ap-tok .input, .ap-form .input { font-size: 16px; }
}
.ap-fld--wide { grid-column: 1 / -1; }
.ap-ios { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.ap-ios-install { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 14px; align-items: center;
  padding: 14px; border-radius: 14px; border: 1px solid color-mix(in srgb, var(--c-primary) 28%, var(--c-border));
  background: color-mix(in srgb, var(--c-primary) 6%, transparent); }
.ap-ios-cta { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.ap-ios-url { font-size: 12px; color: var(--c-text-muted); overflow-wrap: anywhere; }
.ap-qr { display: flex; flex-direction: column; align-items: center; gap: 6px; margin: 0; max-width: 170px; }
.ap-qr img, .ap-qr-ph { width: 148px; height: 148px; border-radius: 12px; background: #fff; padding: 6px; display: grid; place-items: center; }
.ap-qr figcaption { font-size: 12px; line-height: 1.6; text-align: center; color: var(--c-text-muted); }
@media (max-width: 560px) {
  .ap-ios-install { grid-template-columns: 1fr; }
  .ap-qr { max-width: none; }
}
.ap-alert { display: flex; gap: 8px; align-items: flex-start; padding: 10px 12px; border-radius: 12px; font-size: 12.5px; line-height: 1.9;
  color: var(--c-text); background: color-mix(in srgb, var(--c-warning) 13%, transparent); border: 1px solid color-mix(in srgb, var(--c-warning) 35%, transparent); }
.ap-alert svg { flex-shrink: 0; margin-top: 4px; color: var(--c-warning); }
.ap-alert--danger { background: color-mix(in srgb, var(--c-danger) 10%, transparent); border-color: color-mix(in srgb, var(--c-danger) 32%, transparent); }
.ap-alert--danger svg { color: var(--c-danger); }
.ap-tok { display: flex; flex-direction: column; gap: 10px; padding: 12px; border-radius: 14px; border: 1px solid var(--c-border); }
.ap-tok .ap-h3 { margin-bottom: 0; }
.ap-tok-pick { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 8px; }
.ap-tok-pick .ap-fld { flex: 1 1 200px; }
.ap-tok-hint { display: flex; gap: 6px; align-items: flex-start; font-size: 12.5px; font-weight: 700; color: var(--c-text); line-height: 1.8; }
.ap-tok-hint svg { flex-shrink: 0; margin-top: 5px; color: var(--c-primary); }
.ap-inline-link { color: var(--c-text); font-weight: 700; text-decoration: underline; text-decoration-color: var(--c-primary); }
.ap-adv { border: 1px dashed var(--c-border); border-radius: 14px; padding: 10px 12px; }
.ap-adv summary { display: inline-flex; align-items: center; gap: 7px; cursor: pointer; font-size: 12.5px; font-weight: 700; color: var(--c-text-muted); list-style: none; min-height: 32px; }
.ap-adv summary::-webkit-details-marker { display: none; }
.ap-adv[open] summary { color: var(--c-text); }
.ap-adv-body { display: flex; flex-direction: column; gap: 10px; margin-top: 10px; }
.ap-check { display: flex; align-items: center; gap: 8px; font-size: 12.5px; cursor: pointer; }
.ap-check input { width: 18px; height: 18px; accent-color: var(--c-primary); }
`
