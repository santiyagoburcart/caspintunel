import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali, gb } from '../lib/format'
import { Alert, Copyable, Spinner, StatusBadge } from '../components/ui'

function ServiceCard({ s, t, lang }) {
  const pct = s.data_limit ? Math.min(100, Math.round((s.data_used / s.data_limit) * 100)) : 0
  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <span className="font-bold">{s.panel_username}</span>
        <StatusBadge status={s.status} />
      </div>
      <div className="text-sm text-muted">
        {t('volume')}: {s.data_limit ? `${gb(s.data_used)} / ${gb(s.data_limit)} GB` : t('unlimited')}
      </div>
      {s.data_limit > 0 && (
        <div className="h-2 rounded-full" style={{ background: 'var(--c-border)' }}>
          <div className="h-2 rounded-full" style={{ width: `${pct}%`, background: pct > 85 ? 'var(--c-danger)' : 'var(--c-primary)' }} />
        </div>
      )}
      <div className="text-sm text-muted">
        {s.expire_at ? `${s.days_left} ${t('days_left')} — ${jalali(s.expire_at, false, lang)}` : t('unlimited')}
      </div>
      {s.subscription_url && (
        <div className="flex items-center gap-2">
          <code className="truncate rounded bg-black/10 px-2 py-1 text-xs">{s.subscription_url}</code>
          <Copyable text={s.subscription_url} />
        </div>
      )}
      <div className="flex gap-2">
        {s.qr && <a className="btn-ghost text-sm" href={s.qr} target="_blank" rel="noreferrer">{t('qr')}</a>}
        <Link className="btn-primary text-sm" to={`/checkout?renew=${s.id}`}>{t('renew')}</Link>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const { t, lang } = useI18n()
  const { state } = useLocation()
  const [items, setItems] = useState(null)
  const [flash, setFlash] = useState(state?.flash || '')

  useEffect(() => {
    api.get('/services/').then((r) => setItems(r.data.results)).catch(() => setItems([]))
  }, [])

  return (
    <div className="space-y-4">
      {flash && <Alert kind="success">{flash}</Alert>}
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">{t('services')}</h1>
        <Link to="/store" className="btn-primary text-sm">{t('buy')}</Link>
      </div>
      {items === null ? <div className="grid place-items-center py-16"><Spinner /></div>
        : items.length === 0 ? <div className="card text-center text-muted">{t('no_services')}</div>
        : <div className="grid gap-4 sm:grid-cols-2">{items.map((s) => <ServiceCard key={s.id} s={s} t={t} lang={lang} />)}</div>}
    </div>
  )
}
