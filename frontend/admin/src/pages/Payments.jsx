import { useEffect, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali, toman } from '../lib/format'
import { Alert, Spinner } from '../components/ui'

export default function Payments() {
  const { t } = useI18n()
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')

  const load = () => api.get('/admin/payments/pending/').then((r) => setRows(r.data.results)).catch(() => setRows([]))
  useEffect(() => { load() }, [])

  const act = async (id, kind) => {
    setErr('')
    try {
      if (kind === 'approve') await api.post(`/payments/${id}/approve/`)
      else await api.post(`/payments/${id}/reject/`, { reason: prompt('دلیل رد؟') || 'نامشخص' })
      load()
    } catch (e) { setErr(apiError(e)) }
  }

  if (rows === null) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold">صف تأیید پرداخت</h1>
      <Alert>{err}</Alert>
      {rows.length === 0 && <div className="card text-center text-muted">موردی نیست</div>}
      <div className="grid gap-3 sm:grid-cols-2">
        {rows.map((p) => (
          <div key={p.id} className="card space-y-2">
            <div className="flex justify-between"><span className="font-bold">{toman(p.amount)}</span><span className="text-xs text-muted">{jalali(p.created_at, true)}</span></div>
            <div className="text-sm text-muted">کاربر: {p.user} · سفارش #{p.order_id}</div>
            {p.receipt_image && <a href={p.receipt_image} target="_blank" rel="noreferrer"><img src={p.receipt_image} alt="رسید" className="max-h-48 rounded-xl border" style={{ borderColor: 'var(--c-border)' }} /></a>}
            <div className="flex gap-2">
              <button className="btn-primary text-sm" onClick={() => act(p.id, 'approve')}>{t('approve')}</button>
              <button className="btn-ghost text-sm" onClick={() => act(p.id, 'reject')}>{t('reject')}</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
