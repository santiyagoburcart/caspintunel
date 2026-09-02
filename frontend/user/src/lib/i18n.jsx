import { createContext, useContext, useEffect, useState } from 'react'

const dict = {
  fa: {
    login: 'ورود', register: 'ثبت‌نام', logout: 'خروج', email: 'ایمیل', username: 'نام کاربری',
    password: 'رمز عبور', name: 'نام', phone: 'شماره تلفن', referral: 'کد معرف',
    dashboard: 'داشبورد', store: 'فروشگاه', services: 'سرویس‌های من', history: 'تاریخچه',
    profile: 'پروفایل', pages: 'راهنما', notifications: 'اعلان‌ها',
    buy: 'خرید', renew: 'تمدید', qr: 'دریافت QR', status: 'وضعیت',
    amount: 'مبلغ', pay: 'پرداخت', uploadReceipt: 'بارگذاری رسید', account_name: 'نام اکانت',
    change_password: 'تغییر رمز عبور', current_password: 'رمز فعلی', new_password: 'رمز جدید',
    language: 'زبان', theme: 'پوسته', dark: 'تیره', light: 'روشن',
    days_left: 'روز باقی‌مانده', volume: 'حجم', unlimited: 'نامحدود', save: 'ذخیره',
    forgot: 'فراموشی رمز', reset: 'بازیابی', verify_email: 'تأیید ایمیل',
    referral_count: 'تعداد معرفی‌ها', no_services: 'هنوز سرویسی ندارید',
    submit: 'ثبت', copy: 'کپی', copied: 'کپی شد',
    duration: 'مدت', days: 'روز', no_expiry: 'بدون انقضا', selectable: 'انتخابی',
    discount: 'تخفیف', per_gb: 'هر گیگ', menu: 'منو', close: 'بستن',
    login_failed: 'ورود ناموفق بود', register_failed: 'ثبت‌نام ناموفق بود',
    order_failed: 'ثبت سفارش ناموفق بود', pw_changed: 'رمز عبور تغییر کرد',
    verify_sent: 'ایمیل تأیید ارسال شد', pay_exact: 'دقیقاً همین مبلغ را واریز کنید',
    deadline: 'مهلت پرداخت', receipt_saved: 'رسید ثبت شد؛ پس از تأیید، سرویس فعال می‌شود.',
    service_activated: 'سرویس شما فعال شد 🎉', no_content: 'محتوایی ثبت نشده است.',
    pay_status: 'وضعیت پرداخت', pay_pending: 'رسید ارسال شد — در انتظار تأیید ادمین ⏳',
    pay_rejected: 'رسید رد شد', pay_approved: 'پرداخت تأیید شد ✅', pay_reupload: 'ارسال رسید جدید',
    no_cards: 'کارتی برای واریز ثبت نشده — با پشتیبانی تماس بگیرید.',
    refresh_status: 'بررسی وضعیت', uploading: 'در حال ارسال…',
    invalid_link: 'لینک نامعتبر است', checking: 'در حال بررسی…', back: 'بازگشت',
    no_orders: 'هنوز سفارشی ثبت نشده', checkout: 'تکمیل خرید',
    o_new: 'خرید جدید', o_renew: 'تمدید', o_addon_volume: 'افزودن حجم',
    st_active: 'فعال', st_on_hold: 'در انتظار اتصال', st_expired: 'منقضی',
    st_limited: 'اتمام حجم', st_disabled: 'غیرفعال', st_pending: 'در حال ساخت',
    st_pending_payment: 'در انتظار پرداخت', st_paid: 'پرداخت شد',
    st_completed: 'تکمیل شد', st_rejected: 'رد شد',
  },
  en: {
    login: 'Login', register: 'Register', logout: 'Logout', email: 'Email', username: 'Username',
    password: 'Password', name: 'Name', phone: 'Phone', referral: 'Referral code',
    dashboard: 'Dashboard', store: 'Store', services: 'My services', history: 'History',
    profile: 'Profile', pages: 'Help', notifications: 'Notifications',
    buy: 'Buy', renew: 'Renew', qr: 'Get QR', status: 'Status',
    amount: 'Amount', pay: 'Pay', uploadReceipt: 'Upload receipt', account_name: 'Account name',
    change_password: 'Change password', current_password: 'Current password', new_password: 'New password',
    language: 'Language', theme: 'Theme', dark: 'Dark', light: 'Light',
    days_left: 'days left', volume: 'Volume', unlimited: 'Unlimited', save: 'Save',
    forgot: 'Forgot password', reset: 'Reset', verify_email: 'Verify email',
    referral_count: 'Referrals', no_services: 'You have no services yet',
    submit: 'Submit', copy: 'Copy', copied: 'Copied',
    duration: 'Duration', days: 'days', no_expiry: 'No expiry', selectable: 'Selectable',
    discount: 'Discount', per_gb: 'per GB', menu: 'Menu', close: 'Close',
    login_failed: 'Login failed', register_failed: 'Registration failed',
    order_failed: 'Could not create the order', pw_changed: 'Password changed',
    verify_sent: 'Verification email sent', pay_exact: 'Transfer exactly this amount',
    deadline: 'Payment deadline', receipt_saved: 'Receipt submitted — the service activates after approval.',
    service_activated: 'Your service is active 🎉', no_content: 'No content yet.',
    pay_status: 'Payment status', pay_pending: 'Receipt submitted — waiting for admin approval ⏳',
    pay_rejected: 'Receipt rejected', pay_approved: 'Payment approved ✅', pay_reupload: 'Upload a new receipt',
    no_cards: 'No card configured for transfer — contact support.',
    refresh_status: 'Check status', uploading: 'Uploading…',
    invalid_link: 'Invalid link', checking: 'Checking…', back: 'Back',
    no_orders: 'No orders yet', checkout: 'Checkout',
    o_new: 'New purchase', o_renew: 'Renewal', o_addon_volume: 'Add-on volume',
    st_active: 'Active', st_on_hold: 'Awaiting connection', st_expired: 'Expired',
    st_limited: 'Data used up', st_disabled: 'Disabled', st_pending: 'Provisioning',
    st_pending_payment: 'Awaiting payment', st_paid: 'Paid',
    st_completed: 'Completed', st_rejected: 'Rejected',
  },
}

// enum value -> label, falls back to the raw value
export function label(t, prefix, value) {
  if (!value) return '—'
  const k = prefix + value
  const out = t(k)
  return out === k ? value : out
}

const I18n = createContext(null)

export function I18nProvider({ children }) {
  const [lang, setLang] = useState(() => localStorage.getItem('ct_lang') || 'fa')
  useEffect(() => {
    localStorage.setItem('ct_lang', lang)
    document.documentElement.lang = lang
    document.documentElement.dir = lang === 'fa' ? 'rtl' : 'ltr'
  }, [lang])
  const t = (k) => (dict[lang][k] ?? dict.fa[k] ?? k)
  return <I18n.Provider value={{ lang, setLang, t }}>{children}</I18n.Provider>
}

export const useI18n = () => useContext(I18n)
