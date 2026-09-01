import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { toman } from '../lib/format'
import { DataTable } from '../components/DataTable'
import { Alert, Spinner } from '../components/ui'

export default function Cards() {
  const { t, lang } = useI18n()
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    api.get('/admin/cards/deposit-report/')
      .then((r) => setD(r.data))
      .catch(() => { setD({ cards: [], grand_total: 0 }); setErr(t('load_error')) })
  }, [])

  if (!d) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold">{t('deposit_report')}</h1>
      <Alert>{err}</Alert>
      <DataTable
        empty={t('none_found')}
        columns={[
          { key: 'card_number', label: t('card_number') },
          { key: 'holder_name', label: t('holder') },
          { key: 'bank_name', label: t('bank'), render: (r) => r.bank_name || '—' },
          { key: 'deposit_count', label: t('deposit_count'), render: (r) => r.deposit_count || 0 },
          { key: 'deposit_total', label: t('deposit_total'), render: (r) => toman(r.deposit_total || 0, lang) },
          { key: 'is_active', label: t('active'), render: (r) => (r.is_active ? '✓' : '—') },
        ]}
        rows={d.cards || []}
      />
      <div className="card flex justify-between font-bold">
        <span>{t('total')}</span><span>{toman(d.grand_total, lang)}</span>
      </div>
    </div>
  )
}
