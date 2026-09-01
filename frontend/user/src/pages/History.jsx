import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali, toman } from '../lib/format'
import { Spinner, StatusBadge } from '../components/ui'

export default function History() {
  const { t } = useI18n()
  const [rows, setRows] = useState(null)

  useEffect(() => {
    api.get('/orders/').then((r) => setRows(r.data.results)).catch(() => setRows([]))
  }, [])

  if (rows === null) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold">{t('history')}</h1>
      <div className="card divide-y" style={{ borderColor: 'var(--c-border)' }}>
        {rows.length === 0 && <div className="py-6 text-center text-muted">—</div>}
        {rows.map((o) => (
          <div key={o.id} className="flex items-center justify-between py-3" style={{ borderColor: 'var(--c-border)' }}>
            <div>
              <div className="text-sm">{o.plan_name} · {o.type}</div>
              <div className="text-xs text-muted">{jalali(o.created_at, true)}</div>
            </div>
            <div className="text-end">
              <div className="text-sm">{toman(o.amount_unique)}</div>
              <StatusBadge status={o.status} />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
