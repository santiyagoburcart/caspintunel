import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali, gb } from '../lib/format'
import { Alert, Copyable, Spinner, StatusBadge } from '../components/ui'
import { AuthImage } from '../components/AuthImage'

function ServiceCard({ s, t, lang, onRefresh }) {
  const [showQr, setShowQr] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const pct = s.data_limit ? Math.min(100, Math.round((s.data_used / s.data_limit) * 100)) : 0
  const waiting = s.waiting_for_connection
  const gbUsed = gb(s.data_used)
  const gbTotal = s.data_limit ? gb(s.data_limit) : null

  const refresh = async () => {
    setBusy(true); setErr('')
    try { await onRefresh(s.id) } catch (e) { setErr(apiError(e)) } finally { setBusy(false) }
  }

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between gap-2">
        <span dir="ltr" className="truncate font-bold">{s.panel_username}</span>
        <div className="flex shrink-0 items-center gap-1">
          {waiting && (
            <button
              className="btn-ghost px-1.5 py-0.5 text-sm leading-none"
              onClick={refresh}
              disabled={busy}
              title={t('refresh_status')}
              aria-label={t('refresh_status')}
            >
              <span className={busy ? 'inline-block animate-spin' : ''}>↻</span>
            </button>
          )}
          <StatusBadge status={s.status} />
        </div>
      </div>

      {/* --- time / validity --- */}
      {waiting ? (
        <div className="rounded-xl px-3 py-2 text-sm" style={{ background: 'color-mix(in srgb, var(--c-warning) 14%, transparent)', color: 'var(--c-warning)' }}>
          <div className="font-medium">{t('waiting_connect')}</div>
          <div className="text-xs opacity-90">
            {s.validity_days ? t('validity_after', { n: s.validity_days }) : t('unlimited_time')}
          </div>
        </div>
      ) : (
        <div className="text-sm text-muted">
          {s.expire_at
            ? `${s.days_left} ${t('days_left')} — ${jalali(s.expire_at, false, lang)}`
            : t('unlimited_time')}
        </div>
      )}

      {/* --- volume --- */}
      <div className="text-sm text-muted">
        {t('volume')}: {gbTotal != null ? t('used_of', { used: gbUsed, total: gbTotal }) : t('unlimited')}
        {gbTotal != null && ` · ${Math.max(gbTotal - gbUsed, 0)} ${t('remaining')}`}
      </div>
      {gbTotal != null && (
        <div className="h-2 rounded-full" style={{ background: 'var(--c-border)' }}>
          <div className="h-2 rounded-full"
            style={{ width: `${pct}%`, background: pct > 85 ? 'var(--c-danger)' : 'var(--c-primary)' }} />
        </div>
      )}

      {(s.status === 'limited' || s.status === 'expired') && (
        <div className="text-xs" style={{ color: 'var(--c-danger)' }}>
          {s.status === 'limited' ? t('st_limited_note') : t('st_expired_note')}
        </div>
      )}

      {/* --- subscription link + QR --- */}
      {s.subscription_url && (
        <div className="space-y-2">
          <div className="text-xs text-muted">{t('qr_link')}</div>
          <div className="flex items-center gap-2">
            <code dir="ltr" className="min-w-0 flex-1 truncate rounded bg-black/10 px-2 py-1 text-xs">{s.subscription_url}</code>
            <Copyable text={s.subscription_url} />
          </div>
          <button className="btn-ghost w-full text-sm" onClick={() => setShowQr((v) => !v)}>
            {showQr ? '▲ QR' : '▼ QR'}
          </button>
          {showQr && (
            <div className="grid place-items-center rounded-xl bg-white p-3">
              <AuthImage path={`/services/${s.id}/qr/`} alt="QR" className="h-44 w-44" />
            </div>
          )}
        </div>
      )}

      <Alert>{err}</Alert>
      <div className="flex flex-wrap gap-2">
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
  const [err, setErr] = useState('')

  // merge a fresh /services/ payload in place; flash if anything just went live
  const apply = (rows) => {
    setItems((cur) => {
      const before = Object.fromEntries((cur || []).map((x) => [x.id, x.status]))
      const activated = rows.some(
        (r) => before[r.id] && before[r.id] !== 'active' && r.status === 'active',
      )
      if (activated) setFlash(t('service_activated'))
      return rows
    })
    setErr('')
  }

  const load = () =>
    api.get('/services/')
      .then((r) => apply(r.data.results))
      .catch(() => { setItems((cur) => cur || []); setErr(t('load_error') || '') })

  useEffect(() => { load() }, [])

  // While any service is still "waiting for first connection", poll silently so
  // the card flips to active on its own (backend throttles the real panel sync).
  const waitingCount = (items || []).filter(
    (s) => s.status === 'on_hold' || s.status === 'pending',
  ).length
  useEffect(() => {
    if (!waitingCount) return
    const started = Date.now()
    const id = setInterval(() => {
      if (Date.now() - started > 13 * 60 * 1000) { clearInterval(id); return }
      api.get('/services/').then((r) => apply(r.data.results)).catch(() => {})
    }, 20000)
    return () => clearInterval(id)
  }, [waitingCount])

  const refreshOne = async (id) => {
    const { data } = await api.post(`/services/${id}/refresh/`)
    setItems((cur) => (cur || []).map((x) => (x.id === id ? data : x)))
    if (data.status === 'active') setFlash(t('service_activated'))
  }

  return (
    <div className="space-y-4">
      {flash && <Alert kind="success">{flash}</Alert>}
      {err && <Alert>{err}</Alert>}
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">{t('services')}</h1>
        <Link to="/store" className="btn-primary text-sm">{t('buy')}</Link>
      </div>
      {items === null ? <div className="grid place-items-center py-16"><Spinner /></div>
        : items.length === 0 ? <div className="card text-center text-muted">{t('no_services')}</div>
        : <div className="grid gap-4 sm:grid-cols-2">
            {items.map((s) => <ServiceCard key={s.id} s={s} t={t} lang={lang} onRefresh={refreshOne} />)}
          </div>}
    </div>
  )
}
