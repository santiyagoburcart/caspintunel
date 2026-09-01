import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { toman } from '../lib/format'
import { Spinner } from '../components/ui'

const GB = 1024 ** 3

export default function Store() {
  const { t } = useI18n()
  const nav = useNavigate()
  const [plans, setPlans] = useState(null)

  useEffect(() => {
    api.get('/plans/').then((r) => setPlans(r.data.results)).catch(() => setPlans([]))
  }, [])

  if (plans === null) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold">{t('store')}</h1>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {plans.map((p) => (
          <div key={p.id} className="card flex flex-col gap-2">
            <div className="font-bold">{p.name_fa}</div>
            <div className="text-sm text-muted">{p.desc_fa}</div>
            <ul className="mt-1 space-y-1 text-sm">
              <li>حجم: {p.type === 'custom_volume' ? 'انتخابی' : p.data_limit ? `${p.data_limit / GB} GB` : t('unlimited')}</li>
              <li>مدت: {p.duration_days ? `${p.duration_days} روز` : 'بدون انقضا'}</li>
              {p.discount_percent > 0 && <li className="text-success">تخفیف {p.discount_percent}%</li>}
            </ul>
            <div className="mt-auto flex items-center justify-between pt-2">
              <span className="font-bold">
                {p.type === 'custom_volume' ? `${toman(p.price_per_gb)} / GB` : toman(p.final_price)}
              </span>
              <button className="btn-primary text-sm" onClick={() => nav(`/checkout?plan=${p.id}`)}>{t('buy')}</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
