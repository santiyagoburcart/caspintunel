import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { toman } from '../lib/format'
import { Spinner } from '../components/ui'

export default function Accounting() {
  const { t } = useI18n()
  const [period, setPeriod] = useState('monthly')
  const [range, setRange] = useState({ from: '', to: '' })
  const [d, setD] = useState(null)

  const load = () => {
    setD(null)
    const p = new URLSearchParams()
    if (range.from || range.to) { if (range.from) p.set('from', range.from); if (range.to) p.set('to', range.to) }
    else p.set('period', period)
    api.get(`/admin/accounting/?${p}`).then((r) => setD(r.data)).catch(() => setD({}))
  }
  useEffect(load, [period])

  const max = d?.daily?.reduce((m, x) => Math.max(m, Number(x.revenue || 0)), 0) || 1

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold">{t('accounting')}</h1>
      <div className="card flex flex-wrap items-end gap-3">
        {['daily', 'weekly', 'monthly'].map((x) => (
          <button key={x} className={`btn-ghost text-sm ${period === x && !range.from ? 'text-primary' : ''}`}
            onClick={() => { setRange({ from: '', to: '' }); setPeriod(x) }}>{t(x === 'daily' ? 'روزانه' : x === 'weekly' ? 'هفتگی' : 'ماهانه')}</button>
        ))}
        <div><span className="label">{t('from')} (۱۴۰۳/۰۱/۰۱)</span><input className="input" value={range.from} onChange={(e) => setRange({ ...range, from: e.target.value })} /></div>
        <div><span className="label">{t('to')}</span><input className="input" value={range.to} onChange={(e) => setRange({ ...range, to: e.target.value })} /></div>
        <button className="btn-primary text-sm" onClick={load}>{t('search')}</button>
      </div>

      {!d ? <div className="grid place-items-center py-16"><Spinner /></div> : (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="card"><div className="text-sm text-muted">{t('revenue')}</div><div className="text-2xl font-bold">{toman(d.revenue)}</div></div>
            <div className="card"><div className="text-sm text-muted">{t('transactions')}</div><div className="text-2xl font-bold">{d.transactions}</div></div>
            <div className="card"><div className="text-sm text-muted">{t('period')}</div><div className="text-sm">{d.range?.from} — {d.range?.to}</div></div>
          </div>
          <div className="card">
            <div className="mb-2 font-bold">روند روزانه</div>
            <div className="flex h-40 items-end gap-1">
              {(d.daily || []).map((x, i) => (
                <div key={i} title={`${x.date}: ${toman(x.revenue)}`} className="flex-1 rounded-t"
                  style={{ height: `${(Number(x.revenue || 0) / max) * 100}%`, background: 'var(--c-primary)', minHeight: 2 }} />
              ))}
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Breakdown title="بر اساس روش" rows={d.by_method} keyName="method" />
            <Breakdown title="بر اساس منبع" rows={d.by_source} keyName="order__source" />
          </div>
        </>
      )}
    </div>
  )
}

function Breakdown({ title, rows, keyName }) {
  return (
    <div className="card">
      <div className="mb-2 font-bold">{title}</div>
      {(rows || []).map((r, i) => (
        <div key={i} className="flex justify-between py-1 text-sm">
          <span className="text-muted">{r[keyName] || '—'}</span><span>{toman(r.revenue)} ({r.count})</span>
        </div>
      ))}
    </div>
  )
}
