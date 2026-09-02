import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { toman } from '../lib/format'
import { Spinner } from '../components/ui'

const GB = 1024 ** 3

// language-aware category: label shown + a stable key for grouping
function category(plan, lang) {
  const fa = (plan.category_fa || '').trim()
  const en = (plan.category_en || '').trim()
  const label = lang === 'fa' ? (fa || en) : (en || fa)
  const key = `${fa.toLowerCase()}|${en.toLowerCase()}`
  return { label, key: label ? key : '' }   // '' key == no category == "Other"
}

export default function Store() {
  const { t, lang } = useI18n()
  const nav = useNavigate()
  const [plans, setPlans] = useState(null)
  const [mode, setMode] = useState('grouped')

  useEffect(() => {
    api.get('/plans/').then((r) => setPlans(r.data.results || [])).catch(() => setPlans([]))
    api.get('/config/').then((r) => {
      if (r.data?.product_display_mode) setMode(r.data.product_display_mode)
    }).catch(() => {})
  }, [])

  // grouped: [{key, label, plans}] in first-seen order; no-category group last
  const groups = useMemo(() => {
    if (!plans) return []
    const byKey = new Map()
    for (const p of plans) {
      const { label, key } = category(p, lang)
      if (!byKey.has(key)) byKey.set(key, { key, label: label || t('other_group'), plans: [] })
      byKey.get(key).plans.push(p)
    }
    const list = [...byKey.values()]
    list.sort((a, b) => (a.key === '' ? 1 : b.key === '' ? -1 : 0))   // "Other" last
    return list
  }, [plans, lang, t])

  if (plans === null) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="space-y-5">
      <h1 className="text-lg font-bold">{t('store')}</h1>

      {plans.length === 0 && (
        <div className="card text-center text-muted">{t('no_plans')}</div>
      )}

      {mode === 'grouped' ? (
        groups.map((g) => (
          <section key={g.key || '_other'} className="space-y-3">
            <div className="flex items-center gap-3">
              <h2 className="text-base font-bold">{g.label}</h2>
              <span className="h-px flex-1" style={{ background: 'var(--c-border)' }} />
              <span className="text-xs text-muted">{g.plans.length}</span>
            </div>
            <PlanGrid plans={g.plans} lang={lang} t={t} nav={nav} />
          </section>
        ))
      ) : (
        <PlanGrid plans={plans} lang={lang} t={t} nav={nav} showBadge />
      )}
    </div>
  )
}

function PlanGrid({ plans, lang, t, nav, showBadge }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {plans.map((p) => (
        <PlanCard key={p.id} p={p} lang={lang} t={t} nav={nav} showBadge={showBadge} />
      ))}
    </div>
  )
}

function PlanCard({ p, lang, t, nav, showBadge }) {
  const { label: cat } = category(p, lang)
  return (
    <div className="card flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2">
        <div className="font-bold">{(lang === 'fa' ? p.name_fa : p.name_en) || p.name_fa}</div>
        {showBadge && cat && (
          <span className="shrink-0 rounded-full px-2 py-0.5 text-xs"
            style={{ background: 'color-mix(in srgb, var(--c-primary) 14%, transparent)', color: 'var(--c-primary)' }}>
            {cat}
          </span>
        )}
      </div>
      <div className="whitespace-pre-line text-sm text-muted">
        {(lang === 'fa' ? p.desc_fa : p.desc_en) || p.desc_fa}
      </div>
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
  )
}
