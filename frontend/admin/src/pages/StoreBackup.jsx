import { useI18n } from '../lib/i18n'
import StoreExports from '../components/StoreExports'

// v1.53 (multi-tenant Phase 10) store mode only: «پشتیبان‌گیری» — a backup of the store's own data (needs `store.export`,
// and only while we allow it on «فروشگاه»). Backend: apps/tenancy/export.py, /api/v1/admin/store-export/.
const T = {
  fa: { title: 'پشتیبان‌گیری', sub: 'دریافت یک نسخه از داده‌های فروشگاه شما (مشتری‌ها، سرویس‌ها، سفارش‌ها، پرداخت‌ها، تیکت‌ها و…)' },
  en: { title: 'Backup', sub: 'Download a copy of your store’s data (customers, services, orders, payments, tickets…)' },
}

export default function StoreBackup() {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  return (
    <div className="space-y-4">
      <div><h1 className="text-lg font-bold">{s.title}</h1><p className="text-sm text-muted">{s.sub}</p></div>
      <div className="card"><StoreExports base="/admin/store-export/" /></div>
    </div>
  )
}
