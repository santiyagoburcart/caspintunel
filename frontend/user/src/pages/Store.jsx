import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { toman } from '../lib/format'
import { Spinner } from '../components/ui'

const GB = 1024 ** 3

export default function Store() {
  const { t, lang } = useI18n()
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
            <div className="font-bold">{(lang === 'fa' ? p.name_fa : p.name_en) || p.name_fa}</div>
            <div className="whitespace-pre-line text-sm text-muted">{(lang === 'fa' ? p.desc_fa : p.desc_en) || p.desc_fa}</div>
            <ul className="mt-1 space-y-1 text-sm">
              <li>{t('volume')}: {p.type === 'custom_volume' ? t('selectable') : p.data_limit ? `${p.data_limit / GB} GB` : t('unlimited')}</li>
              <li>{t('duration')}: {p.duration_days ? `${p.duration_days} ${t('days')}` : t('no_expiry')}</li>
              {p.discount_percent > 0 && <li className="text-success">{t('discount')} {p.discount_percent}%</li>}
            </ul>
            <div className="mt-auto flex items-center justify-between pt-2">
              <span className="font-bold">
                {p.type === 'custom_volume' ? `${toman(p.price_per_gb, lang)} / GB` : toman(p.final_price, lang)}
              </span>
              <button className="btn-primary text-sm" onClick={() => nav(`/checkout?plan=${p.id}`)}>{t('buy')}</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
