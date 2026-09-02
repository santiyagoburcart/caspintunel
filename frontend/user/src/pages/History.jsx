import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { useI18n, label } from '../lib/i18n'
import { jalali, toman } from '../lib/format'
import { Spinner, StatusBadge } from '../components/ui'

const PAY_NOTE = {
  pending: ['pay_pending', 'var(--c-success)'],
  rejected: ['pay_rejected', 'var(--c-warning)'],
  approved: ['pay_approved', 'var(--c-success)'],
}

export default function History() {
  const { t, lang } = useI18n()
  const [rows, setRows] = useState(null)

  useEffect(() => {
    api.get('/orders/').then((r) => setRows(r.data.results)).catch(() => setRows([]))
  }, [])

  if (rows === null) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold">{t('history')}</h1>
      <div className="card divide-y" style={{ borderColor: 'var(--c-border)' }}>
        {rows.length === 0 && <div className="py-8 text-center text-muted">{t('no_orders')}</div>}
        {rows.map((o) => {
          const note = o.status === 'pending_payment' && PAY_NOTE[o.payment_status]
          return (
            <div key={o.id} className="flex items-start justify-between gap-3 py-3">
              <div className="min-w-0">
                <div className="truncate text-sm">{o.plan_name} · {label(t, 'o_', o.type)}</div>
                <div className="text-xs text-muted">{jalali(o.created_at, true, lang)}</div>
                {note && (
                  <div className="mt-1 text-xs" style={{ color: note[1] }}>
                    {t(note[0])}{o.reject_reason ? ` — ${o.reject_reason}` : ''}
                  </div>
                )}
                {o.status === 'pending_payment' && (
                  <Link to={`/checkout?resume=${o.id}`} className="mt-1 inline-block text-xs text-primary hover:underline">
                    {t('pay')} →
                  </Link>
                )}
              </div>
              <div className="shrink-0 text-end">
                <div className="text-sm">{toman(o.amount_unique, lang)}</div>
                <StatusBadge status={o.status} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
