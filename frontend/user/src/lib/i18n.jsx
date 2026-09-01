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
  },
}

const I18n = createContext(null)

export function I18nProvider({ children }) {
  const [lang, setLang] = useState(() => localStorage.getItem('ct_lang') || 'fa')
  useEffect(() => {
    localStorage.setItem('ct_lang', lang)
    document.documentElement.lang = lang
    document.documentElement.dir = lang === 'fa' ? 'rtl' : 'ltr'
  }, [lang])
  const t = (k) => dict[lang][k] || k
  return <I18n.Provider value={{ lang, setLang, t }}>{children}</I18n.Provider>
}

export const useI18n = () => useContext(I18n)
