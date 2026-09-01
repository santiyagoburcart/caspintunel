import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useI18n, enumLabel } from '../lib/i18n'
import { toman } from '../lib/format'
import { Alert, Spinner } from '../components/ui'

export default function Accounting() {
  const { t, lang } = useI18n()
  const [period, setPeriod] = useState('monthly')
  const [range, setRange] = useState({ from: '', to: '' })
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')

  const load = () => {
    setD(null); setErr('')
    const p = new URLSearchParams()
    if (range.from || range.to) {
      if (range.from) p.set('from', range.from)
      if (range.to) p.set('to', range.to)
    } else p.set('period', period)
    api.get(`/admin/accounting/?${p}`)
      .then((r) => setD(r.data))
      .catch(() => { setD({}); setErr(t('load_error')) })
  }
  useEffect(load, [period])

  const daily = d?.daily || []
  const max = daily.reduce((m, x) => Math.max(m, Number(x.revenue || 0)), 0) || 1

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold">{t('accounting')}</h1>
      <Alert>{err}</Alert>
      <div className="card flex flex-wrap items-end gap-3">
        {['daily', 'weekly', 'monthly'].map((x) => (
          <button key={x} className={`btn-ghost text-sm ${period === x && !range.from ? 'text-primary' : ''}`}
            onClick={() => { setRange({ from: '', to: '' }); setPeriod(x) }}>{t(x)}</button>
        ))}
        <div>
          <span className="label">{t('from')}</span>
          <input className="input" placeholder={t('date_hint')} value={range.from}
            onChange={(e) => setRange({ ...range, from: e.target.value })} />
        </div>
        <div>
          <span className="label">{t('to')}</span>
          <input className="input" placeholder={t('date_hint')} value={range.to}
            onChange={(e) => setRange({ ...range, to: e.target.value })} />
        </div>
        <button className="btn-primary text-sm" onClick={load}>{t('search')}</button>
      </div>

      {!d ? <div className="grid place-items-center py-16"><Spinner /></div> : (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="card"><div className="text-sm text-muted">{t('revenue')}</div><div className="text-2xl font-bold">{toman(d.revenue, lang)}</div></div>
            <div className="card"><div className="text-sm text-muted">{t('transactions')}</div><div className="text-2xl font-bold">{d.transactions ?? 0}</div></div>
            <div className="card"><div className="text-sm text-muted">{t('period')}</div><div className="text-sm" dir="ltr">{d.range?.from} — {d.range?.to}</div></div>
          </div>
          <div className="card">
            <div className="mb-2 font-bold">{t('daily_trend')}</div>
            {daily.length === 0 ? (
              <div className="py-6 text-center text-sm text-muted">{t('none_found')}</div>
            ) : (
              <div className="flex h-40 items-end gap-1">
                {daily.map((x, i) => (
                  <div key={i} title={`${x.date}: ${toman(x.revenue, lang)}`} className="flex-1 rounded-t"
                    style={{ height: `${(Number(x.revenue || 0) / max) * 100}%`, background: 'var(--c-primary)', minHeight: 2 }} />
                ))}
              </div>
            )}
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Breakdown title={t('by_method')} rows={d.by_method} keyName="method" prefix="m_" t={t} lang={lang} empty={t('none_found')} />
            <Breakdown title={t('by_source')} rows={d.by_source} keyName="order__source" prefix="src_" t={t} lang={lang} empty={t('none_found')} />
          </div>
        </>
      )}
    </div>
  )
}

function Breakdown({ title, rows, keyName, prefix, t, lang, empty }) {
  const list = rows || []
  return (
    <div className="card">
      <div className="mb-2 font-bold">{title}</div>
      {list.length === 0 && <div className="text-sm text-muted">{empty}</div>}
      {list.map((r, i) => (
        <div key={i} className="flex justify-between py-1 text-sm">
          <span className="text-muted">{enumLabel(t, prefix, r[keyName])}</span>
          <span>{toman(r.revenue, lang)} ({r.count})</span>
        </div>
      ))}
    </div>
  )
}
