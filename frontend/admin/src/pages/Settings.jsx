import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useAuth } from '../lib/auth'
import { jalali, relTime } from '../lib/format'
import { Alert, Field, Spinner, Toggle } from '../components/ui'
import { useToast } from '../components/Toast'

function HubIco({ d, w = 18 }) {
  return (
    <svg viewBox="0 0 24 24" width={w} height={w} fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{d}</svg>
  )
}
const HUB_ICONS = {
  panel: <><path d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244" /></>,
  bots: <><rect x="3" y="11" width="18" height="10" rx="2" /><circle cx="12" cy="5" r="2" /><path d="M12 7v4M8 16h.01M16 16h.01" /></>,
  roles: <path d="M9 12.75L11.25 15 15 9.75M21 12c0 5.591-3.824 10.29-9 11.622C6.824 22.29 3 17.591 3 12c0-1.933.204-3.44.596-4.996A11.943 11.943 0 0112 3c2.998 0 5.74 1.1 7.843 2.918A11.94 11.94 0 0121 12z" />,
  branding: <path d="M4.098 19.902a3.75 3.75 0 005.304 0l6.401-6.402M6.75 21A3.75 3.75 0 013 17.25V4.125C3 3.504 3.504 3 4.125 3h5.25c.621 0 1.125.504 1.125 1.125v4.072M6.75 21a3.75 3.75 0 003.75-3.75V8.197M6.75 21h13.125c.621 0 1.125-.504 1.125-1.125v-5.25c0-.621-.504-1.125-1.125-1.125h-4.072M10.5 8.197l2.88-2.88c.438-.439 1.15-.439 1.59 0l3.712 3.713c.44.44.44 1.152 0 1.59l-2.879 2.88M6.75 17.25h.008v.008H6.75v-.008z" />,
  themes: <path d="M9.53 16.122a3 3 0 00-5.78 1.128 2.25 2.25 0 01-2.4 2.245 4.5 4.5 0 008.4-2.245c0-.399-.078-.78-.22-1.128zm0 0a15.998 15.998 0 003.388-1.62m-5.043-.025a15.994 15.994 0 011.622-3.395m3.42 3.42a15.995 15.995 0 004.764-4.648l3.876-5.814a1.151 1.151 0 00-1.597-1.597L14.146 6.32a15.996 15.996 0 00-4.649 4.763m3.42 3.42a6.776 6.776 0 00-3.42-3.42" />,
  pages: <path d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />,
  sms_devices: <><path d="M7 4h10a1 1 0 011 1v14a1 1 0 01-1 1H7a1 1 0 01-1-1V5a1 1 0 011-1z" /><line x1="11" y1="18" x2="13" y2="18" /></>,
  sms_sources: <><path d="M3 21h18M4 10h16M6 21V10M18 21V10M12 3l9 5H3l9-5z" /></>,
  alerts: <><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></>,
  unique_amount: <><line x1="12" y1="1" x2="12" y2="23" /><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" /></>,
  requirements: <><path d="M5 11h14v10H5z" /><path d="M8 11V7a4 4 0 018 0v4" /></>,
  backup: <><path d="M21 12a9 9 0 11-3-6.7" /><path d="M21 3v5h-5" /></>,
  chevron: <polyline points="9 18 15 12 9 6" />,
  logout: <><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" /></>,
}

const HUB = {
  fa: {
    h: 'مرکز تنظیمات و دسترسی‌ها', sub: 'میانبر سریع به بخش‌های پیکربندی سامانه',
    themes: { t: 'پوسته و استایل', d: 'انتخاب پوستهٔ رنگی فعال سامانه' },
    panel: { t: 'اتصال پنل پاسارگارد', d: 'مدیریت سرورها و گروه‌های نود' },
    bots: { t: 'ربات‌های تلگرام', d: 'ربات فروش، بک‌آپ و عضویت اجباری' },
    sms_devices: { t: 'دستگاه‌های SMS', d: 'دستگاه‌های مجاز ارسال پیامک واریزی' },
    sms_sources: { t: 'شماره‌های بانکی', d: 'شماره‌های فرستندهٔ مجاز پیامک بانک' },
    alerts: { t: 'هشدارها', d: 'آستانهٔ هشدار حجم و انقضا' },
    unique_amount: { t: 'مبلغ تصادفی', d: 'بازهٔ مبلغ افزودهٔ خودکار کارت‌به‌کارت' },
    requirements: { t: 'الزامات', d: 'تأیید ایمیل، کد معرف و عضویت اجباری' },
    backup: { t: 'بک‌آپ و پشتیبان‌گیری', d: 'فاصلهٔ زمانی پشتیبان‌گیری خودکار' },
    branding: { t: 'برندینگ', d: 'لوگو، فاویکون، نام و دامنهٔ سامانه' },
    roles: { t: 'نقش‌ها', d: 'تعریف سطوح دسترسی و حساب‌های ادمین' },
    pages: { t: 'صفحات', d: 'سوالات متداول و شرایط استفاده' },
    logout: 'خروج از حساب مدیریت',
  },
  en: {
    h: 'Settings & access hub', sub: 'Quick shortcuts to every configuration area',
    themes: { t: 'Theme & style', d: "Pick the system's active colour theme" },
    panel: { t: 'Pasargad panel connection', d: 'Manage servers and node groups' },
    bots: { t: 'Telegram bots', d: 'Sales bot, backup bot, forced join' },
    sms_devices: { t: 'SMS devices', d: 'Devices authorized to forward deposit SMS' },
    sms_sources: { t: 'Bank numbers', d: 'Authorized sender numbers for bank SMS' },
    alerts: { t: 'Alerts', d: 'Volume and expiry warning thresholds' },
    unique_amount: { t: 'Unique amount', d: 'Auto-added card-to-card amount range' },
    requirements: { t: 'Requirements', d: 'Email verification, referral, forced join' },
    backup: { t: 'Backup & scheduling', d: 'Automatic backup interval' },
    branding: { t: 'Branding', d: 'Logo, favicon, name and domain' },
    roles: { t: 'Roles', d: 'Define access levels and admin accounts' },
    pages: { t: 'Pages', d: 'FAQ and terms of use' },
    logout: 'Log out of the admin account',
  },
}

// icon tint by section category — network blue, bots violet, finance green,
// security orange, appearance pink, everything else neutral gray
const HUB_COLOR = {
  themes: '#DB2777', branding: '#DB2777',
  panel: '#1464BA',
  bots: '#7C3AED',
  sms_devices: '#11AB53', sms_sources: '#11AB53', unique_amount: '#11AB53',
  alerts: 'var(--c-warning)',
  requirements: '#D97706', roles: '#D97706',
  backup: '#1464BA',
  pages: '#64748B',
}

// [route-or-hash, i18n-key, permission]
const HUB_ITEMS = [
  ['/themes', 'themes', 'themes.manage'],
  ['/panel-link', 'panel', 'settings.manage'],
  ['/bots', 'bots', 'bots.manage'],
  ['/settings#sms-devices', 'sms_devices', 'settings.manage'],
  ['/settings#sms-sources', 'sms_sources', 'settings.manage'],
  ['/settings#alerts', 'alerts', 'settings.manage'],
  ['/settings#unique-amount', 'unique_amount', 'settings.manage'],
  ['/settings#requirements', 'requirements', 'settings.manage'],
  ['/settings#backup', 'backup', 'settings.manage'],
  ['/branding', 'branding', 'settings.manage'],
  ['/roles', 'roles', 'roles.manage'],
  ['/pages', 'pages', 'pages.manage'],
]

function SettingsHub() {
  const { lang } = useI18n()
  const { logout, can } = useAuth()
  const go = useNavigate()
  const h = HUB[lang] || HUB.fa
  const items = HUB_ITEMS.filter(([, , p]) => !p || can(p))

  return (
    <div className="st-hub set-mobile-only">
      <div className="mb-1">
        <h2 className="font-bold text-sm">{h.h}</h2>
        <p className="text-xs text-muted mt-0.5">{h.sub}</p>
      </div>
      <div className="card p-0 st-hub-list">
        {items.map(([to, key]) => {
          const c = HUB_COLOR[key] || '#64748B'
          return (
            <Link key={to} to={to} className="st-hub-item">
              <span className="st-hub-ico" style={{ background: `color-mix(in srgb, ${c} 14%, transparent)`, color: c }}>
                <HubIco d={HUB_ICONS[key]} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block font-semibold text-sm">{h[key].t}</span>
                <span className="block text-xs text-muted mt-0.5 truncate">{h[key].d}</span>
              </span>
              <HubIco d={HUB_ICONS.chevron} w={16} />
            </Link>
          )
        })}
        <button type="button" className="st-hub-item st-hub-item--danger" onClick={() => { logout(); go('/login') }}>
          <span className="st-hub-ico st-hub-ico--danger"><HubIco d={HUB_ICONS.logout} /></span>
          <span className="min-w-0 flex-1"><span className="block font-semibold text-sm">{h.logout}</span></span>
        </button>
      </div>
    </div>
  )
}

const T = {
  fa: {
    h1: 'تنظیمات عمومی',
    sub: 'پیکربندی پارامترهای پشتیبان‌گیری، قیمت‌گذاری، هشدارها و الزامات عضویت',
    card_h: 'پرداخت و کارت‌به‌کارت', card_sub: 'زمان رزرو فاکتور و بازهٔ مبلغ افزودهٔ خودکار برای تأیید پرداخت',
    alerts_h: 'هشدارها', alerts_sub: 'آستانهٔ هشدار حجم و تعداد روزهای باقی‌مانده تا انقضا',
    sync_h: 'همگام‌سازی سرویس‌ها', sync_sub: 'فاصلهٔ خواندن خودکار وضعیت سرویس‌ها از پنل‌های پاسارگارد',
    backup_h: 'بک‌آپ و پشتیبان‌گیری', backup_sub: 'فاصلهٔ زمانی پشتیبان‌گیری خودکار از پایگاه‌داده — همچنین در صفحهٔ ربات‌های تلگرام قابل تنظیم است',
    toggles_h: 'الزامات', toggles_sub: 'قوانین ثبت‌نام و ورود کاربران به سایت و ربات',
    display_h: 'نمایش', display_sub: 'زبان پیش‌فرض سامانه و شیوهٔ نمایش محصولات به خریداران',
    reset: 'بازنشانی مقادیر', save: 'ذخیرهٔ تغییرات',
    note: 'تغییر فاصلهٔ پشتیبان‌گیری بلافاصله زمان‌بند را به‌روز می‌کند.',
    info_h: 'راهنمای مبلغ تصادفی یکتا',
    info: 'مبلغ افزوده به قیمت، به‌صورت تصادفی بین حداقل و حداکثر به فاکتورهای کارت‌به‌کارت اضافه می‌شود تا سیستم بتواند بدون تداخل، پرداخت هر کاربر را از روی شناسهٔ مبلغ به‌صورت خودکار تأیید کند.',
    lang_fa: 'فارسی', lang_en: 'English',

    src_h: 'شماره‌های بانکی', src_sub: 'شماره‌های فرستندهٔ پیامک واریزی بانک — فقط پیامک از این شماره‌ها برای تأیید خودکار بررسی می‌شود',
    src_info: 'این‌ها شماره‌هایی هستند که بانک با آن‌ها پیامک واریز وجه ارسال می‌کند (مثلاً ۱۰۰۰۸۵۵۶ برای بانک ملت). فقط پیامک‌های دریافتی از این شماره‌ها برای تأیید خودکار پرداخت بررسی می‌شوند؛ پیامک از شماره‌های دیگر ذخیره می‌شود ولی نادیده گرفته می‌شود.',
    src_add: 'افزودن شماره', src_none: 'هنوز شماره‌ای ثبت نشده است — تا زمانی که شماره‌ای اضافه نشود، پیامک همهٔ فرستنده‌ها پذیرفته می‌شود.',
    src_col_phone: 'شماره', src_col_desc: 'توضیحات', src_col_active: 'وضعیت', src_col_created: 'تاریخ ایجاد', src_col_actions: 'عملیات',
    src_edit: 'ویرایش', src_delete: 'حذف',
    src_delete_confirm: 'این شماره حذف شود؟ پیامک‌های آینده از این شماره دیگر برای تأیید خودکار بررسی نمی‌شوند.',
    src_add_title: 'افزودن شمارهٔ مجاز', src_edit_title: 'ویرایش شمارهٔ مجاز',
    src_phone_label: 'شماره فرستنده (مثلاً 10008556)', src_phone_placeholder: '10008556',
    src_desc_label: 'توضیحات (مثلاً نام بانک)', src_desc_placeholder: 'مثلاً بانک ملت',
    src_create_btn: 'افزودن شماره', src_save_btn: 'ذخیرهٔ تغییرات',

    dev_h: 'دستگاه‌های SMS', dev_sub: 'دستگاه‌های اندرویدی مجاز برای ارسال پیامک‌های واریزی به سرور',
    dev_add: 'افزودن دستگاه', dev_none: 'هنوز دستگاهی ثبت نشده است',
    dev_col_name: 'نام دستگاه', dev_col_token: 'توکن', dev_col_active: 'وضعیت',
    dev_col_seen: 'آخرین اتصال', dev_col_created: 'تاریخ ایجاد', dev_col_actions: 'عملیات',
    dev_reveal: 'نمایش توکن', dev_edit: 'ویرایش', dev_delete: 'حذف', dev_never: 'هرگز',
    dev_delete_confirm: 'این دستگاه حذف شود؟ اتصال آن به سرور بلافاصله قطع می‌شود.',
    dev_add_title: 'افزودن دستگاه جدید', dev_reveal_title: 'توکن دستگاه', dev_edit_title: 'ویرایش نام دستگاه',
    dev_name_label: 'نام دستگاه (مثلاً گوشی اپراتور)', dev_name_placeholder: 'مثلاً Samsung A54 — اپراتور اصلی',
    dev_create_btn: 'ایجاد دستگاه', dev_save_btn: 'ذخیرهٔ تغییرات', dev_done: 'متوجه شدم',
    dev_token_warn: 'این توکن دیگر نمایش داده نمی‌شود — همین حالا آن را کپی و در برنامهٔ اندروید وارد کنید.',
    dev_copy: 'کپی', dev_copied: 'کپی شد',
  },
  en: {
    h1: 'General settings',
    sub: 'Configure backup, pricing, alerts and membership requirement parameters',
    card_h: 'Payment & card-to-card', card_sub: 'Invoice reservation window and the auto-added amount range used to confirm payments',
    alerts_h: 'Alerts', alerts_sub: 'Volume warning threshold and days-before-expiry notice',
    sync_h: 'Service sync', sync_sub: 'How often service status is auto-read from the Pasargad panels',
    backup_h: 'Backup & scheduling', backup_sub: 'How often the database is auto-backed up — also editable on the Telegram Bots page',
    toggles_h: 'Requirements', toggles_sub: 'Rules for how users register and sign in on the site and the bot',
    display_h: 'Display', display_sub: 'Default system language and how products are shown to buyers',
    reset: 'Reset values', save: 'Save changes',
    note: 'Changing the backup interval reschedules the backup task immediately.',
    info_h: 'About the unique random amount',
    info: 'A random amount between the min and max is added to each card-to-card invoice so the system can auto-verify every payment by its unique amount without clashing with other users’ bank transactions.',
    lang_fa: 'Persian', lang_en: 'English',

    src_h: 'Bank Numbers', src_sub: 'Sender numbers the bank uses for deposit SMS — only messages from these numbers are checked for auto-confirmation',
    src_info: 'These are the phone numbers the bank sends deposit SMS from (e.g. 10008556 for Bank Mellat). Only incoming SMS from these numbers are checked for auto-confirming a payment; SMS from any other number is stored but ignored.',
    src_add: 'Add number', src_none: 'No numbers registered yet — until one is added, SMS from any sender is accepted.',
    src_col_phone: 'Number', src_col_desc: 'Description', src_col_active: 'Status', src_col_created: 'Created', src_col_actions: 'Actions',
    src_edit: 'Edit', src_delete: 'Delete',
    src_delete_confirm: 'Delete this number? Future SMS from it will no longer be checked for auto-confirmation.',
    src_add_title: 'Add an allowed number', src_edit_title: 'Edit allowed number',
    src_phone_label: 'Sender number (e.g. 10008556)', src_phone_placeholder: '10008556',
    src_desc_label: 'Description (e.g. bank name)', src_desc_placeholder: 'e.g. Bank Mellat',
    src_create_btn: 'Add number', src_save_btn: 'Save changes',

    dev_h: 'SMS Devices', dev_sub: 'Android devices authorized to forward deposit SMS to the server',
    dev_add: 'Add device', dev_none: 'No devices registered yet',
    dev_col_name: 'Device name', dev_col_token: 'Token', dev_col_active: 'Status',
    dev_col_seen: 'Last seen', dev_col_created: 'Created', dev_col_actions: 'Actions',
    dev_reveal: 'Reveal token', dev_edit: 'Edit', dev_delete: 'Delete', dev_never: 'Never',
    dev_delete_confirm: 'Delete this device? It will be disconnected from the server immediately.',
    dev_add_title: 'Add a new device', dev_reveal_title: 'Device token', dev_edit_title: 'Edit device name',
    dev_name_label: 'Device name (e.g. the operator\'s phone)', dev_name_placeholder: 'e.g. Samsung A54 — main operator',
    dev_create_btn: 'Create device', dev_save_btn: 'Save changes', dev_done: 'Got it',
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
    service_sync_interval_minutes: 'پیش‌فرض: ۶۰ — هر چند دقیقه وضعیت سرویس‌ها از پنل‌ها خوانده شود',
  },
  en: {
    backup_interval_minutes: 'default: 1440 (24h)',
    unique_amount_reservation_minutes: 'card-to-card invoice expiry',
    unique_amount_min: 'floor of the added amount — toman',
    unique_amount_max: 'ceiling of the added amount — toman',
    alert_volume_percent: 'e.g. at 80% usage',
    alert_expire_days: 'notify this many days before expiry',
    service_sync_interval_minutes: 'default: 60 — how often services are re-read from the panels',
  },
}
const RANGE = {
  backup_interval_minutes: [5, 43200], unique_amount_reservation_minutes: [5, 720],
  unique_amount_min: [1, 100000], unique_amount_max: [1, 100000],
  alert_volume_percent: [1, 100], alert_expire_days: [1, 60],
  service_sync_interval_minutes: [1, 1440],
}

const SRC_MODAL_TITLE = { add: 'src_add_title', edit: 'src_edit_title' }

// simple add/edit form for one allowed SMS sender number — no token flow,
// unlike the device modal below.
function SmsSourceModal({ mode, source, s, t, onClose, onSaved }) {
  const [phone, setPhone] = useState(mode === 'edit' && source ? source.phone_number : '')
  const [desc, setDesc] = useState(mode === 'edit' && source ? source.description : '')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr('')
    const body = { phone_number: phone.trim(), description: desc.trim() }
    try {
      if (mode === 'edit') await api.patch(`/admin/sms-sources/${source.id}/`, body)
      else await api.post('/admin/sms-sources/', body)
      onSaved()
      onClose()
    } catch (e2) { setErr(apiError(e2)) } finally { setBusy(false) }
  }

  return (
    <div className="sdm-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form className="sdm-modal card" onSubmit={submit} role="dialog" aria-modal="true">
        <div className="sdm-modal-head">
          <h2 className="font-bold">{s[SRC_MODAL_TITLE[mode]]}</h2>
          <button type="button" className="sdm-icon-btn" onClick={onClose} aria-label={t('cancel')}>✕</button>
        </div>

        <div className="sdm-modal-body">
          <Alert>{err}</Alert>
          <Field label={s.src_phone_label}>
            <input className="input mono-num" dir="ltr" required autoFocus inputMode="numeric"
              placeholder={s.src_phone_placeholder}
              value={phone} onChange={(e) => setPhone(e.target.value)} />
          </Field>
          <Field label={s.src_desc_label}>
            <input className="input" placeholder={s.src_desc_placeholder}
              value={desc} onChange={(e) => setDesc(e.target.value)} />
          </Field>
        </div>

        <div className="sdm-modal-foot">
          <button type="button" className="btn-ghost text-sm" onClick={onClose}>{t('cancel')}</button>
          <button type="submit" className="btn-primary text-sm" disabled={busy}>
            {busy ? '…' : (mode === 'edit' ? s.src_save_btn : s.src_create_btn)}
          </button>
        </div>
      </form>
    </div>
  )
}

function SmsSourcesSection({ t, s, lang }) {
  const [sources, setSources] = useState(null)
  const [err, setErr] = useState('')
  const [modal, setModal] = useState(null) // { mode: 'add' } | { mode: 'edit', source }

  const load = () =>
    api.get('/admin/sms-sources/')
      .then((r) => { setSources(r.data.results ?? r.data); setErr('') })
      .catch((e) => { setSources([]); setErr(apiError(e, t('load_error'))) })
  useEffect(() => { load() }, [])

  const toggle = async (src) => {
    setErr('')
    try {
      await api.patch(`/admin/sms-sources/${src.id}/`, { is_active: !src.is_active })
      setSources((cur) => cur.map((x) => (x.id === src.id ? { ...x, is_active: !x.is_active } : x)))
    } catch (e2) { setErr(apiError(e2)) }
  }
  const del = async (src) => {
    if (!confirm(s.src_delete_confirm)) return
    try { await api.delete(`/admin/sms-sources/${src.id}/`); load() } catch (e2) { setErr(apiError(e2)) }
  }

  return (
    <div id="sms-sources" className="card sms-dev-card">
      <div className="sms-dev-head">
        <div>
          <h3 className="font-bold text-sm">{s.src_h}</h3>
          <p className="text-xs text-muted mt-0.5">{s.src_sub}</p>
        </div>
        <button type="button" className="btn-primary text-sm" onClick={() => setModal({ mode: 'add' })}>
          {s.src_add}
        </button>
      </div>

      <div className="sms-src-info">{s.src_info}</div>

      <Alert>{err}</Alert>

      {sources === null ? (
        <div className="grid place-items-center py-10"><Spinner /></div>
      ) : sources.length === 0 ? (
        <div className="sms-dev-empty">{s.src_none}</div>
      ) : (
        <div className="sms-dev-table-wrap">
          <table className="sms-dev-table">
            <thead>
              <tr>
                <th>{s.src_col_phone}</th>
                <th>{s.src_col_desc}</th>
                <th>{s.src_col_active}</th>
                <th>{s.src_col_created}</th>
                <th>{s.src_col_actions}</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((src) => (
                <tr key={src.id}>
                  <td data-label={s.src_col_phone}><code className="mono-num" dir="ltr">{src.phone_number}</code></td>
                  <td data-label={s.src_col_desc}>{src.description || '—'}</td>
                  <td data-label={s.src_col_active}>
                    <Toggle checked={src.is_active} onChange={() => toggle(src)} label={s.src_col_active} />
                  </td>
                  <td data-label={s.src_col_created}>{jalali(src.created_at, false, lang)}</td>
                  <td data-label={s.src_col_actions}>
                    <div className="sms-dev-actions">
                      <button type="button" className="btn-ghost text-xs" onClick={() => setModal({ mode: 'edit', source: src })}>
                        {s.src_edit}
                      </button>
                      <button type="button" className="btn-ghost text-xs sms-dev-del" onClick={() => del(src)}>
                        {s.src_delete}
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
        <SmsSourceModal
          mode={modal.mode}
          source={modal.source}
          s={s}
          t={t}
          onClose={() => setModal(null)}
          onSaved={load}
        />
      )}
    </div>
  )
}

const DEV_MODAL_TITLE = { add: 'dev_add_title', reveal: 'dev_reveal_title', edit: 'dev_edit_title' }

// mode: 'add' (name form -> shows the new token once) | 'edit' (name form ->
// PATCHes the name, no token involved) | 'reveal' (fetches an existing
// device's token on open). Whenever a token is in hand it's shown the same
// way — copy button + "won't be shown again" style warning.
function SmsDeviceModal({ mode, device, s, t, onClose, onCreated }) {
  const [name, setName] = useState(mode === 'edit' && device ? device.name : '')
  const [token, setToken] = useState(null)
  const [busy, setBusy] = useState(mode === 'reveal')
  const [err, setErr] = useState('')
  const [copied, setCopied] = useState(false)
  const showsForm = mode === 'add' || mode === 'edit'

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
      if (mode === 'edit') {
        await api.patch(`/admin/sms-devices/${device.id}/`, { name })
        onCreated()
        onClose()
      } else {
        const { data } = await api.post('/admin/sms-devices/', { name })
        setToken(data.api_token)
        onCreated()
      }
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
          <h2 className="font-bold">{s[DEV_MODAL_TITLE[mode]]}</h2>
          <button type="button" className="sdm-icon-btn" onClick={onClose} aria-label={t('cancel')}>✕</button>
        </div>

        <div className="sdm-modal-body">
          <Alert>{err}</Alert>

          {showsForm && !token && (
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
          ) : showsForm ? (
            <>
              <button type="button" className="btn-ghost text-sm" onClick={onClose}>{t('cancel')}</button>
              <button type="submit" form="sms-dev-form" className="btn-primary text-sm" disabled={busy}>
                {busy ? '…' : (mode === 'edit' ? s.dev_save_btn : s.dev_create_btn)}
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
    <div id="sms-devices" className="card sms-dev-card">
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
                      <button type="button" className="btn-ghost text-xs" onClick={() => setModal({ mode: 'edit', device: d })}>
                        {s.dev_edit}
                      </button>
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
  const toast = useToast()
  const s = T[lang] || T.fa
  const h = HINT[lang] || HINT.fa
  const [rows, setRows] = useState(null)
  const [form, setForm] = useState({})
  const [initial, setInitial] = useState({})
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const location = useLocation()

  const load = () =>
    api.get('/admin/settings/')
      .then((r) => {
        const f = Object.fromEntries(r.data.settings.map((x) => [x.key, x.value]))
        setRows(r.data.settings); setForm(f); setInitial(f); setErr('')
      })
      .catch(() => { setRows([]); setErr(t('load_error')) })
  useEffect(() => { load() }, [])

  // the mobile hub links to /settings#section — the form itself is normally
  // hidden below 768px (mobile only shows the hub), so a hash target forces
  // it visible too (see .st-force-show below) before we scroll to it
  const ANCHOR_IDS = ['sms-devices', 'sms-sources', 'alerts', 'unique-amount', 'requirements', 'backup']
  const hashId = location.hash ? location.hash.slice(1) : ''
  const hasAnchor = ANCHOR_IDS.includes(hashId)

  useEffect(() => {
    if (!rows || !hashId) return
    const el = document.getElementById(hashId)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [rows, hashId])

  const save = async (e) => {
    e.preventDefault(); setBusy(true); setErr('')
    toast.loading(t('action_in_progress'))
    try {
      await api.put('/admin/settings/', form)
      toast.success(t('saved'))
      load()
    } catch (e2) { toast.error(apiError(e2)) } finally { setBusy(false) }
  }
  const reset = () => setForm(initial)

  if (!rows) return <div className="grid place-items-center py-16"><Spinner /></div>

  // moved to the Telegram Bots page (they're bot-specific, not general system
  // settings) — keep them out of this generic list so they don't show twice.
  // backup_interval_minutes stays editable there too, but also gets its own
  // card here (id="backup") so the mobile hub shortcut has somewhere to land.
  const MOVED_TO_BOTS = ['force_channel_join', 'force_share_phone']
  const nums = rows.filter((x) => x.type === 'int' && !MOVED_TO_BOTS.includes(x.key))
  const bools = rows.filter((x) => x.type === 'bool' && !MOVED_TO_BOTS.includes(x.key))
  const strs = rows.filter((x) => x.type === 'str')
  // clearly separate int groups — the reservation/amount fields belong
  // together, alert thresholds and the sync/backup intervals are distinct concerns
  const AMOUNT_KEYS = ['unique_amount_reservation_minutes', 'unique_amount_min', 'unique_amount_max']
  const SYNC_KEYS = ['service_sync_interval_minutes']
  const BACKUP_KEYS = ['backup_interval_minutes']
  const amountNums = nums.filter((x) => AMOUNT_KEYS.includes(x.key))
  const alertNums = nums.filter((x) => !AMOUNT_KEYS.includes(x.key) && !SYNC_KEYS.includes(x.key) && !BACKUP_KEYS.includes(x.key))
  const syncNums = nums.filter((x) => SYNC_KEYS.includes(x.key))
  const backupNums = nums.filter((x) => BACKUP_KEYS.includes(x.key))

  const SectionSave = () => (
    <button type="submit" form="settings-form" className="btn-primary text-xs st-card-save" disabled={busy}>
      {busy ? '…' : s.save}
    </button>
  )

  const NumField = (x) => (
    <label key={x.key} className="st-fld">
      <span className="st-fld-top">
        <span className="label">{t('set_' + x.key)}</span>
        {h[x.key] && <span className="st-hint">{h[x.key]}</span>}
      </span>
      <input className="input" dir="ltr" type="number"
        min={RANGE[x.key]?.[0]} max={RANGE[x.key]?.[1]}
        value={form[x.key] ?? ''} onChange={(e) => setForm({ ...form, [x.key]: e.target.value })} />
    </label>
  )

  return (
    <div className="st space-y-5">
      <style>{CSS}</style>

      <SettingsHub />

      <div className={'st-desktop-only space-y-5' + (hasAnchor ? ' st-force-show' : '')}>
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

      <form id="settings-form" onSubmit={save} className="space-y-4">
        {amountNums.length > 0 && (
          <div id="unique-amount" className="card st-card">
            <div className="st-card-head">
              <div>
                <h3 className="font-bold text-sm">{s.card_h}</h3>
                <p className="text-xs text-muted mt-0.5">{s.card_sub}</p>
              </div>
              <SectionSave />
            </div>
            <div className="st-fields">{amountNums.map(NumField)}</div>
          </div>
        )}

        {alertNums.length > 0 && (
          <div id="alerts" className="card st-card">
            <div className="st-card-head">
              <div>
                <h3 className="font-bold text-sm">{s.alerts_h}</h3>
                <p className="text-xs text-muted mt-0.5">{s.alerts_sub}</p>
              </div>
              <SectionSave />
            </div>
            <div className="st-fields">{alertNums.map(NumField)}</div>
          </div>
        )}

        {syncNums.length > 0 && (
          <div className="card st-card">
            <div className="st-card-head">
              <div>
                <h3 className="font-bold text-sm">{s.sync_h}</h3>
                <p className="text-xs text-muted mt-0.5">{s.sync_sub}</p>
              </div>
              <SectionSave />
            </div>
            <div className="st-fields">{syncNums.map(NumField)}</div>
          </div>
        )}

        {backupNums.length > 0 && (
          <div id="backup" className="card st-card">
            <div className="st-card-head">
              <div>
                <h3 className="font-bold text-sm">{s.backup_h}</h3>
                <p className="text-xs text-muted mt-0.5">{s.backup_sub}</p>
              </div>
              <SectionSave />
            </div>
            <div className="st-fields">{backupNums.map(NumField)}</div>
          </div>
        )}

        {bools.length > 0 && (
          <div id="requirements" className="card st-card">
            <div className="st-card-head">
              <div>
                <h3 className="font-bold text-sm">{s.toggles_h}</h3>
                <p className="text-xs text-muted mt-0.5">{s.toggles_sub}</p>
              </div>
              <SectionSave />
            </div>
            <div className="st-toggles">
              {bools.map((x, i) => (
                <div key={x.key} className={'st-toggle-row' + (i ? ' st-div' : '')}>
                  <span className="text-sm">{t('set_' + x.key)}</span>
                  <Toggle checked={!!form[x.key]} onChange={(v) => setForm({ ...form, [x.key]: v })} label={t('set_' + x.key)} />
                </div>
              ))}
            </div>
          </div>
        )}

        {strs.length > 0 && (
          <div className="card st-card">
            <div className="st-card-head">
              <div>
                <h3 className="font-bold text-sm">{s.display_h}</h3>
                <p className="text-xs text-muted mt-0.5">{s.display_sub}</p>
              </div>
              <SectionSave />
            </div>
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
          </div>
        )}

        <div className="card st-foot">
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

      <SmsSourcesSection t={t} s={s} lang={lang} />
      <SmsDevicesSection t={t} s={s} lang={lang} />
      </div>
    </div>
  )
}

const CSS = `
.set-mobile-only { display: none; }
/* the full form is desktop-only by default, but a hub shortcut that points
   at a specific card (e.g. /settings#alerts) forces it visible on mobile
   too — see the .st-force-show class toggled from location.hash */
@media (max-width: 767px) { .st-desktop-only:not(.st-force-show) { display: none; } }
.st-hub-list { overflow: hidden; }
.st-hub-item { display: flex; align-items: center; gap: 12px; padding: 13px 16px; border-bottom: 1px solid var(--c-border); color: inherit; text-decoration: none; width: 100%; text-align: start; }
.st-hub-item:last-child { border-bottom: 0; }
.st-hub-item:hover { background: color-mix(in srgb, var(--c-primary) 5%, transparent); }
.st-hub-ico { width: 36px; height: 36px; border-radius: 11px; flex-shrink: 0; display: grid; place-items: center;
  background: color-mix(in srgb, var(--c-primary) 12%, transparent); color: var(--c-primary); }
.st-hub-ico--danger { background: color-mix(in srgb, var(--c-danger) 12%, transparent); color: var(--c-danger); }
.st-hub-item--danger { color: var(--c-danger); }
@media (max-width: 767px) { .set-mobile-only { display: block; } }

.st-head { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-start; justify-content: space-between; }
@media (max-width: 640px) {
  .st-head { position: sticky; top: 0; z-index: 20; margin: -12px -12px 4px; padding: 12px; background: color-mix(in srgb, var(--c-bg) 92%, transparent); backdrop-filter: blur(8px); }
  .st-head > div:last-child { width: 100%; }
  .st-head .btn-primary, .st-head .btn-ghost { flex: 1; }
  .st-foot { flex-direction: column; align-items: stretch; }
  .st-foot .btn-primary { width: 100%; }
}
.st-card { padding: 0; overflow: hidden; }
.st-card-head { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 10px;
  padding: 18px 20px; border-bottom: 1px solid var(--c-border); }
.st-card-save { flex-shrink: 0; }
.st-fields { padding: 20px; display: grid; grid-template-columns: 1fr; gap: 16px; }
@media (min-width: 640px) { .st-fields { grid-template-columns: 1fr 1fr; } }
.st-fld { display: flex; flex-direction: column; gap: 6px; }
.st-fld .label { font-size: 12px; }
.st-fld-top { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.st-hint { font-size: 11px; color: var(--c-text-muted); }

.st-toggles { padding: 16px 20px 8px; }
.st-toggle-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 13px 0; }
.st-div { border-top: 1px solid var(--c-border); }

.st-selects { padding: 16px 20px 20px; display: grid; grid-template-columns: 1fr; gap: 16px; }
@media (min-width: 640px) { .st-selects { grid-template-columns: 1fr 1fr; } }

.st-foot { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }

.st-info { display: flex; gap: 14px; align-items: flex-start; }
.st-info-ico { width: 38px; height: 38px; border-radius: 11px; flex-shrink: 0; display: grid; place-items: center;
  background: color-mix(in srgb, var(--c-primary) 13%, transparent); color: var(--c-primary); }

/* ---- SMS sources & devices sections (share the same table/modal look) ---- */
.sms-dev-card { padding: 0; overflow: hidden; }
.sms-dev-head { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-start; justify-content: space-between;
  padding: 18px 20px; border-bottom: 1px solid var(--c-border); }
.sms-dev-empty { padding: 32px 20px; text-align: center; color: var(--c-text-muted); font-size: 13px; }
.sms-src-info { margin: 16px 20px 0; padding: 12px 14px; border-radius: 12px; font-size: 12px; line-height: 1.8;
  color: var(--c-text-muted); background: color-mix(in srgb, var(--c-primary) 6%, transparent);
  border: 1px solid color-mix(in srgb, var(--c-primary) 16%, transparent); }

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
