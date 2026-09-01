import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { toman } from '../lib/format'
import { Spinner } from '../components/ui'

function Stat({ label, value, sub }) {
  return (
    <div className="card">
      <div className="text-sm text-muted">{label}</div>
      <div className="text-2xl font-bold">{value}</div>
      {sub && <div className="text-xs text-muted">{sub}</div>}
    </div>
  )
}

export default function Dashboard() {
  const { t } = useI18n()
  const [d, setD] = useState(null)
  const [rev, setRev] = useState(null)

  useEffect(() => {
    api.get('/admin/dashboard/').then((r) => setD(r.data)).catch(() => setD({}))
    api.get('/admin/accounting/?period=monthly').then((r) => setRev(r.data)).catch(() => {})
  }, [])

  if (!d) return <div className="grid place-items-center py-16"><Spinner /></div>

  const byStatus = d.services?.by_status || {}
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold">{t('dashboard')}</h1>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label={t('users')} value={d.services?.total ?? '—'} sub="سرویس فعال" />
        <Stat label="آنلاین" value={d.services?.online_now ?? 0} />
        <Stat label={t('revenue') + ' (۳۰ روز)'} value={rev ? toman(rev.revenue) : '—'} sub={rev ? `${rev.transactions} تراکنش` : ''} />
        <Stat label={t('health')} value={`${d.health?.up ?? 0} ${t('up')}`} sub={(d.health?.down || []).join(', ') || '—'} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="card">
          <div className="mb-2 font-bold">سرویس‌ها بر اساس وضعیت</div>
          {Object.entries(byStatus).map(([k, v]) => (
            <div key={k} className="flex justify-between py-1 text-sm"><span className="text-muted">{k}</span><span>{v}</span></div>
          ))}
        </div>
        <div className="card">
          <div className="mb-2 font-bold">{t('resources')}</div>
          <div className="space-y-1 text-sm">
            <div className="flex justify-between"><span className="text-muted">CPU</span><span>{d.resources?.cpu_percent ?? '—'}%</span></div>
            <div className="flex justify-between"><span className="text-muted">RAM</span><span>{d.resources?.ram_percent ?? '—'}%</span></div>
            <div className="flex justify-between"><span className="text-muted">Disk</span><span>{d.resources?.disk_percent ?? '—'}%</span></div>
          </div>
        </div>
      </div>
    </div>
  )
}
