import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { toman } from '../lib/format'
import { DataTable } from '../components/DataTable'
import { Spinner } from '../components/ui'

export default function Cards() {
  const { t } = useI18n()
  const [d, setD] = useState(null)

  useEffect(() => {
    api.get('/admin/cards/deposit-report/').then((r) => setD(r.data)).catch(() => setD({ cards: [], grand_total: 0 }))
  }, [])

  if (!d) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold">{t('deposit_report')}</h1>
      <DataTable
        columns={[
          { key: 'card_number', label: 'شماره کارت' },
          { key: 'holder_name', label: 'صاحب' },
          { key: 'bank_name', label: 'بانک' },
          { key: 'deposit_count', label: 'تعداد واریز' },
          { key: 'deposit_total', label: 'جمع واریز', render: (r) => toman(r.deposit_total || 0) },
          { key: 'is_active', label: 'فعال', render: (r) => (r.is_active ? '✓' : '—') },
        ]}
        rows={d.cards}
      />
      <div className="card flex justify-between font-bold">
        <span>{t('total')}</span><span>{toman(d.grand_total)}</span>
      </div>
    </div>
  )
}
