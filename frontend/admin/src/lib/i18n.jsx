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
  const t = (k) => dict[lang][k] || k
  return <I18n.Provider value={{ lang, setLang, t }}>{children}</I18n.Provider>
}

export const useI18n = () => useContext(I18n)
