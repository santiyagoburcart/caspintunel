import { createContext, useContext, useEffect, useState } from 'react'

const dict = {
  fa: {
    login: 'ورود', logout: 'خروج', username: 'نام کاربری', password: 'رمز عبور',
    dashboard: 'داشبورد', users: 'کاربران', plans: 'پلن‌ها', payments: 'پرداخت‌ها',
    accounting: 'حسابداری', cards: 'کارت‌ها', monitoring: 'مانیتورینگ', branding: 'برندینگ',
    pages: 'صفحات', themes: 'پوسته‌ها', roles: 'نقش‌ها', staff: 'کارکنان', telegram: 'تلگرام',
    revenue: 'درآمد', transactions: 'تراکنش‌ها', approve: 'تأیید', reject: 'رد',
    active: 'فعال', disable: 'غیرفعال‌سازی', enable: 'فعال‌سازی', save: 'ذخیره',
    from: 'از', to: 'تا', period: 'بازه', deposit_report: 'گزارش واریز هر کارت',
    health: 'سلامت سرویس‌ها', resources: 'منابع سرور', run_backup: 'پشتیبان‌گیری',
    up: 'برقرار', down: 'قطع', search: 'جستجو', create: 'ایجاد', total: 'مجموع',
    panel_link: 'اتصال پنل پاسارگارد', bots: 'ربات‌های تلگرام', panel_word: 'پنل',
    cancel: 'انصراف', unlimited: 'نامحدود', test_connection: 'تست اتصال',
    settings: 'تنظیمات',
    set_backup_interval_minutes: 'فاصلهٔ پشتیبان‌گیری (دقیقه)',
    set_unique_amount_reservation_minutes: 'مهلت رزرو مبلغ یکتا (دقیقه)',
    set_unique_amount_min: 'حداقل مبلغ افزوده به قیمت (تومان)',
    set_unique_amount_max: 'حداکثر مبلغ افزوده به قیمت (تومان)',
    set_alert_volume_percent: 'هشدار مصرف حجم در درصد',
    set_alert_expire_days: 'هشدار انقضا چند روز مانده',
    set_email_verification_required: 'تأیید ایمیل الزامی است',
    set_force_channel_join: 'عضویت اجباری در کانال (ربات)',
    set_force_share_phone: 'اشتراک‌گذاری اجباری شماره (ربات)',
    set_default_language: 'زبان پیش‌فرض',
    // shared
    name: 'نام', phone: 'تلفن', source: 'منبع', date: 'تاریخ', all: 'همه',
    inactive: 'غیرفعال', description: 'توضیح', slug: 'اسلاگ', title: 'عنوان',
    activate: 'فعال‌سازی', deactivate: 'غیرفعال‌سازی', saved: 'ذخیره شد',
    none_found: 'موردی یافت نشد', load_error: 'خطا در دریافت اطلاعات', count: 'تعداد',
    // dashboard
    online_now: 'آنلاین', services_total: 'کل سرویس‌ها', last_30d: '۳۰ روز اخیر',
    services_by_status: 'سرویس‌ها بر اساس وضعیت',
    // accounting
    daily: 'روزانه', weekly: 'هفتگی', monthly: 'ماهانه', daily_trend: 'روند روزانه',
    by_method: 'بر اساس روش', by_source: 'بر اساس منبع', date_hint: 'مثال: ۱۴۰۳/۰۱/۰۱',
    // cards
    card_number: 'شماره کارت', holder: 'صاحب کارت', bank: 'بانک',
    deposit_count: 'تعداد واریز', deposit_total: 'جمع واریز',
    // branding
    site_name_fa: 'نام سایت (فارسی)', site_name_en: 'نام سایت (انگلیسی)', domain: 'دامنه',
    support_telegram: 'پشتیبانی تلگرام', bot_desc_fa: 'توضیح ربات (فارسی)',
    bot_desc_en: 'توضیح ربات (انگلیسی)', meta_desc: 'توضیح متا (SEO)',
    logo: 'لوگو', favicon: 'فاویکون', domain_note: 'دامنه بدون بازسازی اعمال می‌شود.',
    // permissions
    permissions: 'دسترسی‌ها',
    // statuses
    st_active: 'فعال', st_on_hold: 'در انتظار اتصال', st_expired: 'منقضی',
    st_limited: 'اتمام حجم', st_disabled: 'غیرفعال', st_pending: 'در حال ساخت',
    m_card_manual: 'کارت‌به‌کارت', m_sms_auto: 'تأیید خودکار پیامک', m_gateway: 'درگاه',
    src_site: 'سایت', src_bot: 'ربات', src_admin: 'ادمین',
    admin_panel: 'پنل مدیریت', login_failed: 'ورود ناموفق',
  },
  en: {
    login: 'Login', logout: 'Logout', username: 'Username', password: 'Password',
    dashboard: 'Dashboard', users: 'Users', plans: 'Plans', payments: 'Payments',
    accounting: 'Accounting', cards: 'Cards', monitoring: 'Monitoring', branding: 'Branding',
    pages: 'Pages', themes: 'Themes', roles: 'Roles', staff: 'Staff', telegram: 'Telegram',
    revenue: 'Revenue', transactions: 'Transactions', approve: 'Approve', reject: 'Reject',
    active: 'Active', disable: 'Disable', enable: 'Enable', save: 'Save',
    from: 'From', to: 'To', period: 'Period', deposit_report: 'Per-card deposit report',
    health: 'Health', resources: 'Server resources', run_backup: 'Run backup',
    up: 'up', down: 'down', search: 'Search', create: 'Create', total: 'Total',
    panel_link: 'Pasargad Panel', bots: 'Telegram Bots', panel_word: 'Panel',
    cancel: 'Cancel', unlimited: 'unlimited', test_connection: 'Test connection',
    settings: 'Settings',
    set_backup_interval_minutes: 'Backup interval (minutes)',
    set_unique_amount_reservation_minutes: 'Unique-amount reservation (minutes)',
    set_unique_amount_min: 'Min amount added to the price (toman)',
    set_unique_amount_max: 'Max amount added to the price (toman)',
    set_alert_volume_percent: 'Data-usage alert at percent',
    set_alert_expire_days: 'Expiry alert, days before',
    set_email_verification_required: 'Email verification is required',
    set_force_channel_join: 'Force channel join (bot)',
    set_force_share_phone: 'Force phone share (bot)',
    set_default_language: 'Default language',
    name: 'Name', phone: 'Phone', source: 'Source', date: 'Date', all: 'All',
    inactive: 'Inactive', description: 'Description', slug: 'Slug', title: 'Title',
    activate: 'Activate', deactivate: 'Deactivate', saved: 'Saved',
    none_found: 'Nothing found', load_error: 'Failed to load data', count: 'Count',
    online_now: 'Online now', services_total: 'Total services', last_30d: 'last 30 days',
    services_by_status: 'Services by status',
    daily: 'Daily', weekly: 'Weekly', monthly: 'Monthly', daily_trend: 'Daily trend',
    by_method: 'By method', by_source: 'By source', date_hint: 'e.g. 1403/01/01',
    card_number: 'Card number', holder: 'Card holder', bank: 'Bank',
    deposit_count: 'Deposits', deposit_total: 'Total deposited',
    site_name_fa: 'Site name (fa)', site_name_en: 'Site name (en)', domain: 'Domain',
    support_telegram: 'Support Telegram', bot_desc_fa: 'Bot description (fa)',
    bot_desc_en: 'Bot description (en)', meta_desc: 'Meta description (SEO)',
    logo: 'Logo', favicon: 'Favicon', domain_note: 'The domain applies without a rebuild.',
    permissions: 'Permissions',
    st_active: 'Active', st_on_hold: 'Awaiting first connection', st_expired: 'Expired',
    st_limited: 'Data used up', st_disabled: 'Disabled', st_pending: 'Provisioning',
    m_card_manual: 'Card transfer', m_sms_auto: 'SMS auto-confirm', m_gateway: 'Gateway',
    src_site: 'Website', src_bot: 'Bot', src_admin: 'Admin',
    admin_panel: 'Admin panel', login_failed: 'Login failed',
  },
}

const I18n = createContext(null)

export function I18nProvider({ children }) {
  const [lang, setLang] = useState(() => localStorage.getItem('cta_lang') || 'fa')
  useEffect(() => {
    localStorage.setItem('cta_lang', lang)
    document.documentElement.lang = lang
    document.documentElement.dir = lang === 'fa' ? 'rtl' : 'ltr'
  }, [lang])
  const t = (k) => (dict[lang][k] ?? dict.fa[k] ?? k)
  return <I18n.Provider value={{ lang, setLang, t }}>{children}</I18n.Provider>
}

export const useI18n = () => useContext(I18n)

// enum value -> readable label (status / method / source), falls back to the raw value
export function enumLabel(t, prefix, value) {
  if (!value) return '—'
  const key = prefix + value
  const out = t(key)
  return out === key ? value : out
}
