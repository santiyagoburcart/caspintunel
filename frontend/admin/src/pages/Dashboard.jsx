import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useI18n, enumLabel } from '../lib/i18n'
import { jalali, toman } from '../lib/format'
import { Alert, Spinner } from '../components/ui'
import { DataTable } from '../components/DataTable'

function Stat({ label, value, sub }) {
  return (
    <div className="card">
      <div className="text-sm text-muted">{label}</div>
      <div className="text-2xl font-bold">{value}</div>
      {sub && <div className="text-xs text-muted">{sub}</div>}
    </div>
  )
}

const STATUS_COLOR = { pending: 'warning', approved: 'success', rejected: 'danger' }

function StatusPill({ t, status }) {
  const color = `var(--c-${STATUS_COLOR[status] || 'text-muted'})`
  return (
    <span className="rounded-full px-2 py-0.5 text-xs"
      style={{ background: `color-mix(in srgb, ${color} 18%, transparent)`, color }}>
      {enumLabel(t, 'tx_', status)}
    </span>
  )
}

export default function Dashboard() {
  const { t, lang } = useI18n()
  const [d, setD] = useState(null)
  const [rev, setRev] = useState(null)
  const [recent, setRecent] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    api.get('/admin/dashboard/').then((r) => setD(r.data)).catch(() => { setD({}); setErr(t('load_error')) })
    api.get('/admin/accounting/?period=monthly').then((r) => setRev(r.data)).catch(() => {})
    // a staff role without payment.view simply won't see this section
    api.get('/admin/transactions/?limit=5').then((r) => setRecent(r.data.results ?? r.data)).catch(() => setRecent([]))
  }, [])

  if (!d) return <div className="grid place-items-center py-16"><Spinner /></div>

  const byStatus = Object.entries(d.services?.by_status || {})
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold">{t('dashboard')}</h1>
      <Alert>{err}</Alert>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label={t('services_total')} value={d.services?.total ?? '—'} />
        <Stat label={t('online_now')} value={d.services?.online_now ?? 0} />
        <Stat label={`${t('revenue')} · ${t('last_30d')}`} value={rev ? toman(rev.revenue, lang) : '—'}
          sub={rev ? `${rev.transactions} ${t('transactions')}` : ''} />
        <Stat label={t('health')} value={`${d.health?.up ?? 0} ${t('up')}`}
          sub={(d.health?.down || []).join(', ') || '—'} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="card">
          <div className="mb-2 font-bold">{t('services_by_status')}</div>
          {byStatus.length === 0 && <div className="text-sm text-muted">{t('none_found')}</div>}
          {byStatus.map(([k, v]) => (
            <div key={k} className="flex justify-between py-1 text-sm">
              <span className="text-muted">{enumLabel(t, 'st_', k)}</span><span>{v}</span>
            </div>
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

      {recent && recent.length > 0 && (
        <div className="space-y-2">
          <div className="font-bold">{t('recent_transactions')}</div>
          <DataTable
            empty={t('none_found')}
            columns={[
              { key: 'user', label: t('user') },
              { key: 'plan_name', label: t('plan'), render: (r) => r.plan_name || '—' },
              { key: 'amount', label: t('amount'), render: (r) => toman(r.amount, lang) },
              { key: 'status', label: t('status'), render: (r) => <StatusPill t={t} status={r.status} /> },
              { key: 'created_at', label: t('date'), render: (r) => jalali(r.created_at, true, lang) },
            ]}
            rows={recent}
          />
        </div>
      )}
    </div>
  )
}
