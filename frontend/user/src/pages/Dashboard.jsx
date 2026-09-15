import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useTheme } from '../theme/ThemeProvider'
import { jalali, gb } from '../lib/format'
import { Alert, Copyable, Spinner, StatusBadge } from '../components/ui'
import { AuthImage } from '../components/AuthImage'
import { useToast } from '../components/Toast'

export default function Dashboard() {
  const { styleKey } = useTheme()
  return styleKey === 'caspian' ? <CaspianDashboard /> : <LegacyDashboard />
}

/* shared data hook — polling + activation flash, used by both variants */
function useServices(t) {
  const { state } = useLocation()
  const [items, setItems] = useState(null)
  const [flash, setFlash] = useState(state?.flash || '')
  const [err, setErr] = useState('')

  const apply = (rows) => {
    setItems((cur) => {
      const before = Object.fromEntries((cur || []).map((x) => [x.id, x.status]))
      const activated = rows.some((r) => before[r.id] && before[r.id] !== 'active' && r.status === 'active')
      if (activated) setFlash(t('service_activated'))
      return rows
    })
    setErr('')
  }
  const load = () =>
    api.get('/services/').then((r) => apply(r.data.results)).catch(() => { setItems((c) => c || []); setErr(t('load_error') || '') })
  useEffect(() => { load() }, [])

  const waitingCount = (items || []).filter((s) => s.status === 'on_hold' || s.status === 'pending').length
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
  const revokeOne = async (id) => {
    const { data } = await api.post(`/services/${id}/revoke/`)
    setItems((cur) => (cur || []).map((x) => (x.id === id ? data : x)))
    return data
  }
  return { items, flash, err, refreshOne, revokeOne }
}

/* ================= Legacy (Aurora / Frost) — unchanged ================= */
function LegacyDashboard() {
  const { t, lang } = useI18n()
  const { items, flash, err, refreshOne } = useServices(t)
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
            {items.map((s) => <LegacyServiceCard key={s.id} s={s} t={t} lang={lang} onRefresh={refreshOne} />)}
          </div>}
    </div>
  )
}

function LegacyServiceCard({ s, t, lang, onRefresh }) {
  const [showQr, setShowQr] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const pct = s.data_limit ? Math.min(100, Math.round((s.data_used / s.data_limit) * 100)) : 0
  // timer hasn't started yet whenever the panel hasn't given us an expiry —
  // covers the just-connected moment too, before the next sync flips status/expire_at
  const waiting = s.status === 'on_hold' && !s.expire_at
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
            <button className="btn-ghost px-1.5 py-0.5 text-sm leading-none" onClick={refresh} disabled={busy}
              title={t('refresh_status')} aria-label={t('refresh_status')}>
              <span className={busy ? 'inline-block animate-spin' : ''}>↻</span>
            </button>
          )}
          <StatusBadge status={s.status} />
        </div>
      </div>
      {waiting ? (
        <div className="rounded-xl px-3 py-2 text-sm" style={{ background: 'color-mix(in srgb, var(--c-warning) 14%, transparent)', color: 'var(--c-warning)' }}>
          <div className="font-medium">{t('waiting_connect')}</div>
          <div className="text-xs opacity-90">{s.validity_days ? t('validity_after', { n: s.validity_days }) : t('unlimited_time')}</div>
        </div>
      ) : (
        <div className="text-sm text-muted">
          {s.expire_at ? `${s.days_left} ${t('days_left')} — ${jalali(s.expire_at, false, lang)}` : t('unlimited_time')}
        </div>
      )}
      <div className="text-sm text-muted">
        {t('volume')}: {gbTotal != null ? t('used_of', { used: gbUsed, total: gbTotal }) : t('unlimited')}
        {gbTotal != null && ` · ${Math.max(gbTotal - gbUsed, 0)} ${t('remaining')}`}
      </div>
      {gbTotal != null && (
        <div className="h-2 rounded-full" style={{ background: 'var(--c-border)' }}>
          <div className="h-2 rounded-full" style={{ width: `${pct}%`, background: pct > 85 ? 'var(--c-danger)' : 'var(--c-primary)' }} />
        </div>
      )}
      {(s.status === 'limited' || s.status === 'expired') && (
        <div className="text-xs" style={{ color: 'var(--c-danger)' }}>
          {s.status === 'limited' ? t('st_limited_note') : t('st_expired_note')}
        </div>
      )}
      {s.subscription_url && (
        <div className="space-y-2">
          <div className="text-xs text-muted">{t('qr_link')}</div>
          <div className="flex items-center gap-2">
            <code dir="ltr" className="min-w-0 flex-1 truncate rounded bg-black/10 px-2 py-1 text-xs">{s.subscription_url}</code>
            <Copyable text={s.subscription_url} />
          </div>
          <button className="btn-ghost w-full text-sm" onClick={() => setShowQr((v) => !v)}>{showQr ? '▲ QR' : '▼ QR'}</button>
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

/* ================= Caspian — Stitch redesign port ================= */
const D = {
  tune: 'M4 6h10M4 12h6M4 18h13M18 4v4M13 10v4M20 16v4',
  add: 'M12 5v14M5 12h14',
  key: ['M15 7a4 4 0 11-4 4l-6 6v3h3l1-1v-2h2v-2h2l1-1a4 4 0 014-4z'],
  data: 'M4 20V10M10 20V4M16 20v-8M22 20H2',
  clock: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z',
  search: 'M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z',
  shield: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z',
  hourglass: 'M6 3h12M6 21h12M8 3c0 5 8 5 8 9s-8 4-8 9M16 3c0 5-8 5-8 9',
  copy: ['M8 8h10v12H8z', 'M6 16H4V4h12v2'],
  qr: ['M4 4h6v6H4z', 'M14 4h6v6h-6z', 'M4 14h6v6H4z', 'M14 14h2v2h-2z M18 18h2v2h-2z M14 18h2v2h-2z M18 14h2v2h-2z'],
  renew: 'M4 4v5h5M20 20v-5h-5M20 9A8 8 0 006 5M4 15a8 8 0 0014 4',
  arrow: 'M19 12H5m7 7l-7-7 7-7',
  x: 'M6 18L18 6M6 6l12 12',
  link: ['M9 15l6-6', 'M11 6l1-1a4 4 0 015.5 5.5l-1.5 1.5', 'M13 18l-1 1a4 4 0 01-5.5-5.5l1.5-1.5'],
  warn: 'M12 9v4m0 4h.01M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z',
  spark: 'M12 3v3M12 18v3M4 12H1M23 12h-3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2',
}
function DI({ d, w = 18, className }) {
  return (
    <svg width={w} height={w} viewBox="0 0 24 24" fill="none" stroke="currentColor" className={className}
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {Array.isArray(d) ? d.map((p, i) => <path key={i} d={p} />) : <path d={d} />}
    </svg>
  )
}
const fnum = (n, lang) => (lang === 'fa' ? String(n).replace(/\d/g, (x) => '۰۱۲۳۴۵۶۷۸۹'[x]) : String(n))
const FILTERS = [
  ['all', 'f_all', () => true],
  ['active', 'f_active', (s) => s.status === 'active'],
  ['pending', 'f_pending', (s) => s.status === 'on_hold' || s.status === 'pending'],
  ['expired', 'f_expired', (s) => s.status === 'expired' || s.status === 'limited'],
]

function CaspianDashboard() {
  const { t, lang } = useI18n()
  const { items, flash, err, revokeOne } = useServices(t)
  const [filter, setFilter] = useState('all')
  const [q, setQ] = useState('')

  const stats = useMemo(() => {
    const rows = items || []
    const active = rows.filter((s) => s.status === 'active').length
    const waiting = rows.filter((s) => s.status === 'on_hold' || s.status === 'pending').length
    const totalUsed = rows.reduce((a, s) => a + (s.data_used || 0), 0)
    const next = rows
      .filter((s) => s.expire_at && s.days_left != null && s.days_left >= 0)
      .sort((a, b) => a.days_left - b.days_left)[0]
    return { count: rows.length, active, waiting, totalUsed, next }
  }, [items])

  const shown = useMemo(() => {
    const rows = items || []
    const byF = rows.filter(FILTERS.find(([k]) => k === filter)[2])
    const s = q.trim().toLowerCase()
    return s ? byF.filter((x) => (x.panel_username || '').toLowerCase().includes(s)) : byF
  }, [items, filter, q])

  const fcount = (fn) => (items || []).filter(fn).length

  return (
    <div className="csp-dash">
      <style>{CSS}</style>
      {flash && <Alert kind="success">{flash}</Alert>}
      {err && <Alert>{err}</Alert>}

      {/* hero */}
      <section className="csp-dash-hero">
        <span className="csp-dash-hero-blob" />
        <div className="csp-dash-hero-inner">
          <div className="csp-dash-hero-txt">
            <div className="csp-dash-hero-h">
              <span className="csp-dash-hero-ico"><DI d={D.tune} w={20} /></span>
              <h1 className="csp-headline">{t('svc_hero_h1')}</h1>
            </div>
            <p className="csp-dash-hero-lead">{t('svc_hero_lead')}</p>
          </div>
          <Link to="/store" className="csp-dash-buy"><DI d={D.add} w={16} />{t('buy_new')}</Link>
        </div>

        <div className="csp-dash-stats">
          <Stat icon={D.key} label={t('stat_my_services')}
            value={fnum(stats.count, lang)}
            sub={`${t('n_active_short', { n: fnum(stats.active, lang) })}${stats.waiting ? ` · ${t('n_new_short', { n: fnum(stats.waiting, lang) })}` : ''}`} />
          <Stat icon={D.data} label={t('stat_total_used')}
            value={fnum(gb(stats.totalUsed), lang)} sub={t('gigabytes')} />
          <Stat icon={D.clock} label={t('stat_next_renewal')}
            value={stats.next ? fnum(stats.next.days_left, lang) : '—'}
            sub={stats.next ? `${t('days_more', { n: '' }).trim()} · ${stats.next.panel_username}` : t('unlimited_time')} />
        </div>
      </section>

      {/* filter + search */}
      {items && items.length > 0 && (
        <div className="csp-dash-bar">
          <div className="csp-dash-tabs">
            {FILTERS.map(([k, key, fn]) => (
              <button key={k} type="button" className={'csp-dash-tab' + (filter === k ? ' on' : '')}
                onClick={() => setFilter(k)}>
                {t(key)} <span className="csp-dash-tab-n">{fnum(fcount(fn), lang)}</span>
              </button>
            ))}
          </div>
          <div className="csp-dash-search">
            <DI d={D.search} w={16} />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('search_service')} dir="auto" />
          </div>
        </div>
      )}

      {/* service cards */}
      {items === null ? (
        <div className="grid place-items-center py-20"><Spinner /></div>
      ) : items.length === 0 ? (
        <div className="csp-card csp-dash-empty">
          <p>{t('no_services')}</p>
          <Link to="/store" className="csp-dash-buy"><DI d={D.add} w={16} />{t('buy')}</Link>
        </div>
      ) : shown.length === 0 ? (
        <div className="csp-card csp-dash-empty"><p>{t('no_match')}</p></div>
      ) : (
        <div className="csp-dash-grid">
          {shown.map((s) => <SvcCard key={s.id} s={s} t={t} lang={lang} onRevoke={revokeOne} />)}
        </div>
      )}

      {/* connection guide strip */}
      <Link to="/help" className="csp-dash-guide">
        <span className="csp-dash-guide-ico"><DI d={D.spark} /></span>
        <div className="csp-dash-guide-txt">
          <div className="csp-dash-guide-t">{t('connect_guide_t')}</div>
          <div className="csp-dash-guide-d">{t('connect_guide_d')}</div>
        </div>
        <span className="csp-dash-guide-cta">{t('watch_tutorials')} <DI d={D.arrow} w={15} /></span>
      </Link>
    </div>
  )
}

function Stat({ icon, label, value, sub }) {
  return (
    <div className="csp-stat">
      <span className="csp-stat-ico"><DI d={icon} w={22} /></span>
      <div className="csp-stat-txt">
        <span className="csp-stat-label">{label}</span>
        <div className="csp-stat-val"><b className="mono-num">{value}</b><span>{sub}</span></div>
      </div>
    </div>
  )
}

function SvcCard({ s, t, lang, onRevoke }) {
  const toast = useToast()
  const [qrOpen, setQrOpen] = useState(false)
  const [revokeOpen, setRevokeOpen] = useState(false)
  // timer hasn't started yet whenever the panel hasn't given us an expiry —
  // covers the just-connected moment too, before the next sync flips status/expire_at
  const waiting = s.status === 'on_hold' && !s.expire_at
  const gbUsed = gb(s.data_used)
  const gbTotal = s.data_limit ? gb(s.data_limit) : null
  const pct = gbTotal ? Math.min(100, Math.round((gbUsed / gbTotal) * 100)) : 0
  const dayPct = s.days_left != null && s.validity_days
    ? Math.max(3, Math.min(100, Math.round((s.days_left / s.validity_days) * 100)))
    : (s.days_left != null && s.days_left <= 30 ? Math.max(3, Math.round((s.days_left / 30) * 100)) : 100)

  const st = waiting ? 'pending' : s.status
  const badgeTone = st === 'active' ? 'success' : (st === 'pending' || st === 'on_hold') ? 'warning' : 'danger'

  return (
    <div className="csp-svc">
      <div className="csp-svc-head">
        <div className="csp-svc-id">
          <span className="csp-svc-icon"><DI d={waiting ? D.hourglass : D.shield} w={20} /></span>
          <div>
            <h2 className="csp-headline" dir="ltr">{s.panel_username}</h2>
            <span className="csp-svc-code mono-num">{t('svc_id')}: #CT-{s.id}</span>
          </div>
        </div>
        <span className="csp-svc-badge" data-tone={badgeTone}>
          <i className={badgeTone === 'warning' ? 'spin' : ''} />
          {waiting ? t('f_pending') : (t('st_' + s.status) === ('st_' + s.status) ? s.status : t('st_' + s.status))}
        </span>
      </div>

      {waiting ? (
        <div className="csp-svc-box csp-svc-box--wait">
          <div className="csp-svc-box-t">{t('waiting_connect')}</div>
          <div className="csp-svc-box-d">{s.validity_days ? t('validity_after', { n: fnum(s.validity_days, lang) }) : t('unlimited_time')}</div>
        </div>
      ) : (
        <div className="csp-svc-box">
          <div className="csp-svc-row">
            <span>{t('days_left')}</span>
            <b>{s.expire_at ? `${fnum(s.days_left, lang)} — ${jalali(s.expire_at, false, lang)}` : t('unlimited_time')}</b>
          </div>
          {s.expire_at && <div className="csp-bar"><i style={{ width: `${dayPct}%` }} /></div>}
          <div className="csp-svc-row csp-svc-row--sub">
            <span>{gbTotal != null ? t('used_of', { used: fnum(gbUsed, lang), total: fnum(gbTotal, lang) }) : `${t('volume')}: ${fnum(gbUsed, lang)} GB`}</span>
            <span className="csp-svc-unl">{gbTotal == null ? t('unlimited') : `${fnum(Math.max(gbTotal - gbUsed, 0), lang)} ${t('remaining')}`}</span>
          </div>
          {gbTotal != null && <div className="csp-bar"><i style={{ width: `${pct}%`, background: pct > 85 ? 'var(--c-danger)' : undefined }} /></div>}
          {(s.status === 'limited' || s.status === 'expired') && (
            <div className="csp-svc-warn">{s.status === 'limited' ? t('st_limited_note') : t('st_expired_note')}</div>
          )}
        </div>
      )}

      {s.subscription_url && (
        <div className="csp-svc-sub">
          <span className="csp-svc-sub-label">{t('sub_link_label')}</span>
          <div className="csp-svc-sub-row">
            <Copyable text={s.subscription_url} />
            <input dir="ltr" readOnly value={s.subscription_url} className="mono-num" />
          </div>
        </div>
      )}

      <div className="csp-svc-actions">
        {s.subscription_url && (
          <button type="button" className="csp-svc-btn" onClick={() => setQrOpen(true)}>
            <DI d={D.qr} w={16} />{t('show_qr')}
          </button>
        )}
        {s.subscription_url && (
          <button type="button" className="csp-svc-btn" onClick={() => setRevokeOpen(true)}>
            <DI d={D.link} w={16} />{t('change_sub_link')}
          </button>
        )}
        <Link to={`/checkout?renew=${s.id}`} className="csp-svc-btn csp-svc-btn--primary">
          <DI d={D.renew} w={16} />{t('renew')}
        </Link>
      </div>

      {qrOpen && <QrModal s={s} t={t} lang={lang} onClose={() => setQrOpen(false)} />}
      {revokeOpen && (
        <RevokeSubModal
          s={s} t={t}
          onClose={() => setRevokeOpen(false)}
          onConfirm={async () => {
            toast.loading(t('action_in_progress'))
            try {
              await onRevoke(s.id)
              toast.success(t('sub_link_changed'))
              setRevokeOpen(false)
            } catch (e) { toast.error(apiError(e)) }
          }}
        />
      )}
    </div>
  )
}

/** Confirmation gate before revoking the subscription link — every device
 * on the old link disconnects, so this is deliberately not a one-click action. */
function RevokeSubModal({ s, t, onClose, onConfirm }) {
  const [busy, setBusy] = useState(false)
  const confirm = async () => {
    setBusy(true)
    try { await onConfirm() } finally { setBusy(false) }
  }
  return (
    <div className="csp-qr-overlay" onClick={onClose}>
      <div className="csp-qr-modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 380 }}>
        <div className="csp-qr-head">
          <div className="flex items-center gap-2">
            <span style={{ color: 'var(--c-warning)' }}><DI d={D.warn} w={22} /></span>
            <h2 className="csp-headline">{t('change_sub_link')}</h2>
          </div>
          <button type="button" className="csp-qr-x" onClick={onClose} aria-label={t('close')}><DI d={D.x} w={18} /></button>
        </div>
        <p className="text-sm" style={{ color: 'var(--c-text-muted)', lineHeight: 1.9 }}>{t('revoke_warning')}</p>
        <div className="csp-qr-btns">
          <button type="button" className="csp-qr-btn" onClick={onClose} disabled={busy}>{t('cancel')}</button>
          <button type="button" className="csp-qr-btn csp-qr-btn--primary" onClick={confirm} disabled={busy}
            style={{ background: 'var(--c-danger)', borderColor: 'var(--c-danger)' }}>
            {busy ? '…' : t('confirm')}
          </button>
        </div>
      </div>
    </div>
  )
}

/* ---- QR + quick-connect modal (Stitch redesign screen 5) ---- */
function QrModal({ s, t, lang, onClose }) {
  const [src, setSrc] = useState(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    const h = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', h)
    let dead = false, obj
    api.get(`/services/${s.id}/qr/`, { responseType: 'blob' })
      .then((r) => { if (!dead) { obj = URL.createObjectURL(r.data); setSrc(obj) } })
      .catch(() => {})
    return () => { dead = true; window.removeEventListener('keydown', h); if (obj) URL.revokeObjectURL(obj) }
  }, [s.id, onClose])

  const copy = () => {
    navigator.clipboard?.writeText(s.subscription_url)
    setCopied(true); setTimeout(() => setCopied(false), 1800)
  }
  const downloadQr = () => {
    if (!src) return
    const a = document.createElement('a')
    a.href = src; a.download = `caspian-${s.panel_username}-qr.png`
    document.body.appendChild(a); a.click(); a.remove()
  }
  const waiting = s.status === 'on_hold' && !s.expire_at
  const tone = waiting ? 'warning' : s.status === 'active' ? 'success' : 'danger'
  const daysTxt = s.expire_at ? t('days_remaining', { n: fnum(s.days_left, lang) })
    : waiting ? t('waiting_connect') : t('unlimited_time')
  const steps = [['1', 'step_install'], ['2', 'step_scan'], ['3', 'step_connect']]

  return (
    <div className="csp-qr-overlay" onClick={onClose}>
      <div className="csp-qr-modal" onClick={(e) => e.stopPropagation()}>
        <div className="csp-qr-head">
          <div>
            <h2 className="csp-headline">{t('qr_title')}</h2>
            <div className="csp-qr-sub">
              <b dir="ltr">{s.panel_username}</b>
              <span className="csp-qr-pill" data-tone={tone}><i />{waiting ? t('f_pending') : (t('st_' + s.status) === ('st_' + s.status) ? s.status : t('st_' + s.status))}</span>
              <span className="csp-qr-days">{daysTxt}</span>
            </div>
          </div>
          <button type="button" className="csp-qr-x" onClick={onClose} aria-label={t('close')}><DI d={D.x} w={18} /></button>
        </div>

        {s.data_limit ? (
          <div className="csp-qr-usage">
            <div className="csp-qr-usage-row">
              <span>{t('usage_label')}</span>
              <span className="mono-num">{fnum(gb(s.data_used), lang)} / {fnum(gb(s.data_limit), lang)} GB</span>
            </div>
            <div className="csp-bar"><i style={{ width: `${Math.min(100, Math.round((s.data_used / s.data_limit) * 100))}%` }} /></div>
          </div>
        ) : null}

        <div className="csp-qr-stage">
          <div className="csp-qr-img">{src ? <img src={src} alt="QR" /> : <Spinner />}</div>
          <p className="csp-qr-scan">{t('scan_hint')}</p>
        </div>

        <div className="csp-qr-btns">
          <a href={s.subscription_url} target="_blank" rel="noreferrer" className="csp-qr-btn csp-qr-btn--primary">
            <DI d={D.arrow} w={16} />{t('open_sub')}
          </a>
          <button type="button" className="csp-qr-btn" onClick={downloadQr} disabled={!src}>
            <DI d={D.qr} w={16} />{t('download_qr')}
          </button>
        </div>

        <div className="csp-qr-link">
          <span className="csp-qr-link-label">{t('sub_url_label')}</span>
          <div className="csp-qr-link-row">
            <input dir="ltr" readOnly value={s.subscription_url} className="mono-num" />
            <button type="button" onClick={copy}>{copied ? t('link_copied') : t('copy_link')}</button>
          </div>
        </div>

        <div className="csp-qr-steps">
          <div className="csp-qr-steps-t">{t('connect_3steps')}</div>
          <div className="csp-qr-steps-row">
            {steps.map(([n, key]) => (
              <div key={n} className="csp-qr-step">
                <span className="csp-qr-step-n mono-num">{fnum(n, lang)}</span>
                <span>{t(key)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

const CSS = `
.csp-dash { display: flex; flex-direction: column; gap: 20px; }

/* hero */
.csp-dash-hero {
  position: relative; overflow: hidden; border-radius: 22px; padding: clamp(18px, 3vw, 26px);
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--c-primary) 16%, transparent), color-mix(in srgb, var(--c-secondary) 8%, transparent)),
    var(--c-surface);
  border: 1px solid var(--c-border);
}
:root:not(.dark) .csp-dash-hero { background: linear-gradient(135deg, #e8effc, #f4f7ff); }
.csp-dash-hero-blob {
  position: absolute; width: 260px; height: 260px; border-radius: 50%; top: -110px; inset-inline-end: -70px;
  background: color-mix(in srgb, var(--c-primary) 16%, transparent); filter: blur(60px); pointer-events: none;
}
.csp-dash-hero-inner { position: relative; display: flex; align-items: center; justify-content: space-between; gap: 14px; flex-wrap: wrap; }
.csp-dash-hero-h { display: flex; align-items: center; gap: 10px; }
.csp-dash-hero-ico {
  width: 34px; height: 34px; flex-shrink: 0; display: grid; place-items: center; border-radius: 10px;
  background: var(--c-primary); color: #fff;
}
.csp-dash-hero-h h1 { font-size: clamp(19px, 3vw, 25px); font-weight: 800; }
.csp-dash-hero-lead { font-size: 12.5px; color: var(--c-text-muted); margin-top: 8px; line-height: 1.8; max-width: 560px; }
.csp-dash-buy {
  display: inline-flex; align-items: center; gap: 6px; flex-shrink: 0;
  padding: 11px 18px; border-radius: 13px; font-size: 13px; font-weight: 700; color: #fff;
  background: linear-gradient(135deg, var(--c-primary), color-mix(in srgb, var(--c-primary) 60%, #3f2bd0));
  box-shadow: 0 8px 20px -6px color-mix(in srgb, var(--c-primary) 55%, transparent);
}
.csp-dash-buy:hover { filter: brightness(1.06); }

.csp-dash-stats { position: relative; margin-top: 20px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
@media (max-width: 720px) { .csp-dash-stats { grid-template-columns: 1fr; } }
.csp-stat {
  display: flex; align-items: center; gap: 12px; padding: 13px; border-radius: 14px;
  background: var(--c-surface); border: 1px solid var(--c-border);
}
:root:not(.dark) .csp-stat { background: #fff; }
.csp-stat-ico {
  width: 44px; height: 44px; flex-shrink: 0; display: grid; place-items: center; border-radius: 12px;
  background: color-mix(in srgb, var(--c-primary) 12%, transparent); color: var(--c-primary);
}
.csp-stat-txt { min-width: 0; }
.csp-stat-label { font-size: 11.5px; color: var(--c-text-muted); }
.csp-stat-val { display: flex; align-items: baseline; gap: 6px; margin-top: 2px; }
.csp-stat-val b { font-size: 20px; font-weight: 800; }
.csp-stat-val span { font-size: 11px; color: var(--c-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* filter bar */
.csp-dash-bar {
  display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;
  padding: 8px; border-radius: 16px; background: color-mix(in srgb, var(--c-text-muted) 7%, transparent);
}
.csp-dash-tabs { display: flex; gap: 3px; overflow-x: auto; }
.csp-dash-tab {
  border: 0; cursor: pointer; white-space: nowrap; padding: 8px 13px; border-radius: 11px;
  font-size: 12.5px; font-weight: 600; color: var(--c-text-muted); background: transparent; transition: .15s;
}
.csp-dash-tab.on { background: var(--c-surface); color: var(--c-primary); box-shadow: 0 1px 3px rgba(15,23,42,.12); }
:root:not(.dark) .csp-dash-tab.on { background: #fff; }
.csp-dash-tab-n { font-family: 'JetBrains Mono', ui-monospace, monospace; opacity: .7; }
.csp-dash-search {
  position: relative; display: flex; align-items: center; gap: 8px; flex: 1; min-width: 200px;
  padding: 0 12px; border-radius: 12px; background: var(--c-surface); border: 1px solid var(--c-border); color: var(--c-text-muted);
}
:root:not(.dark) .csp-dash-search { background: #fff; }
.csp-dash-search input { flex: 1; border: 0; background: transparent; outline: none; padding: 9px 0; font: inherit; font-size: 13px; color: var(--c-text); }

/* service grid */
.csp-dash-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
.csp-card, .csp-svc {
  background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 18px;
}
:root:not(.dark) .csp-card, :root:not(.dark) .csp-svc { background: #fff; }
[data-theme-style="caspian"].dark .csp-svc, [data-theme-style="caspian"].dark .csp-card {
  box-shadow: -6px -6px 14px rgba(255,255,255,.02), 6px 6px 18px rgba(0,0,0,.55);
}
.csp-svc { padding: 18px; display: flex; flex-direction: column; gap: 13px; }
.csp-svc-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.csp-svc-id { display: flex; align-items: center; gap: 10px; min-width: 0; }
.csp-svc-icon {
  width: 40px; height: 40px; flex-shrink: 0; display: grid; place-items: center; border-radius: 12px;
  background: color-mix(in srgb, var(--c-primary) 12%, transparent); color: var(--c-primary);
}
.csp-svc-id h2 { font-size: 16px; font-weight: 800; }
.csp-svc-code { font-size: 10.5px; color: var(--c-text-muted); }
.csp-svc-badge {
  flex-shrink: 0; display: inline-flex; align-items: center; gap: 5px; white-space: nowrap;
  padding: 4px 10px; border-radius: 999px; font-size: 10.5px; font-weight: 700;
}
.csp-svc-badge i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.csp-svc-badge i.spin { border-radius: 2px; animation: csp-spin 1.1s linear infinite; }
@keyframes csp-spin { to { transform: rotate(360deg); } }
.csp-svc-badge[data-tone="success"] { color: var(--c-success); background: color-mix(in srgb, var(--c-success) 14%, transparent); }
.csp-svc-badge[data-tone="warning"] { color: var(--c-warning); background: color-mix(in srgb, var(--c-warning) 14%, transparent); }
.csp-svc-badge[data-tone="danger"] { color: var(--c-danger); background: color-mix(in srgb, var(--c-danger) 14%, transparent); }

.csp-svc-box { padding: 11px; border-radius: 12px; background: color-mix(in srgb, var(--c-text-muted) 6%, transparent); display: flex; flex-direction: column; gap: 7px; }
.csp-svc-box--wait { background: color-mix(in srgb, var(--c-warning) 12%, transparent); }
.csp-svc-box-t { font-size: 12.5px; font-weight: 700; color: var(--c-warning); }
.csp-svc-box-d { font-size: 11px; color: var(--c-text-muted); }
.csp-svc-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 11.5px; }
.csp-svc-row span { color: var(--c-text-muted); }
.csp-svc-row b { font-weight: 700; color: var(--c-primary); font-size: 11.5px; }
.csp-svc-row--sub { font-size: 11px; }
.csp-svc-row--sub span { color: var(--c-text-muted); }
.csp-svc-unl { color: var(--c-success) !important; font-weight: 600; }
.csp-svc-warn { font-size: 11px; color: var(--c-danger); font-weight: 600; }
.csp-bar { height: 6px; border-radius: 999px; overflow: hidden; background: color-mix(in srgb, var(--c-text-muted) 18%, transparent); }
.csp-bar > i { display: block; height: 100%; border-radius: 999px; background: linear-gradient(90deg, var(--c-primary), var(--c-secondary)); }

.csp-svc-sub { display: flex; flex-direction: column; gap: 6px; }
.csp-svc-sub-label { font-size: 10.5px; color: var(--c-text-muted); font-weight: 600; }
.csp-svc-sub-row {
  display: flex; align-items: center; gap: 6px; padding: 5px; border-radius: 12px;
  background: color-mix(in srgb, var(--c-text-muted) 8%, transparent);
}
.csp-svc-sub-row input {
  flex: 1; min-width: 0; border: 0; background: transparent; outline: none; font-size: 10.5px; color: var(--c-text-muted);
}
.csp-svc-qr { display: grid; place-items: center; padding: 12px; border-radius: 14px; background: #fff; }
.csp-svc-qr-img { width: 168px; height: 168px; }

.csp-svc-actions { margin-top: auto; padding-top: 12px; border-top: 1px solid var(--c-border); display: flex; gap: 8px; flex-wrap: wrap; }
.csp-svc-btn {
  flex: 1; min-width: 120px; display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  padding: 10px 12px; border-radius: 12px; font-size: 12px; font-weight: 700; cursor: pointer;
  border: 1px solid var(--c-border); background: color-mix(in srgb, var(--c-text-muted) 8%, transparent); color: var(--c-text);
  transition: .15s;
}
.csp-svc-btn:hover { border-color: var(--c-primary); }
.csp-svc-btn--primary { background: var(--c-primary); color: #fff; border-color: var(--c-primary); }
.csp-svc-btn--primary:hover { filter: brightness(1.06); }
.csp-svc-btn .spin { animation: csp-spin 1s linear infinite; }
[dir="rtl"] .csp-svc-btn svg { }

.csp-dash-empty {
  padding: 40px; text-align: center; color: var(--c-text-muted); display: flex; flex-direction: column; align-items: center; gap: 14px;
}

/* connection guide */
.csp-dash-guide {
  display: flex; align-items: center; gap: 13px; padding: 15px 17px; border-radius: 18px;
  background: var(--c-surface); border: 1px solid var(--c-border); text-decoration: none; color: var(--c-text);
}
:root:not(.dark) .csp-dash-guide { background: #fff; }
.csp-dash-guide:hover { border-color: var(--c-primary); }
.csp-dash-guide-ico {
  width: 40px; height: 40px; flex-shrink: 0; display: grid; place-items: center; border-radius: 12px;
  background: color-mix(in srgb, var(--c-primary) 12%, transparent); color: var(--c-primary);
}
.csp-dash-guide-txt { flex: 1; min-width: 0; }
.csp-dash-guide-t { font-size: 13px; font-weight: 700; }
.csp-dash-guide-d { font-size: 11px; color: var(--c-text-muted); margin-top: 2px; }
.csp-dash-guide-cta { flex-shrink: 0; display: inline-flex; align-items: center; gap: 4px; font-size: 12px; font-weight: 700; color: var(--c-primary); }
[dir="rtl"] .csp-dash-guide-cta svg, [dir="rtl"] .csp-dash-buy svg:first-child { }
[dir="rtl"] .csp-dash-guide-cta svg { transform: scaleX(-1); }

/* ---- QR modal ---- */
.csp-qr-overlay {
  position: fixed; inset: 0; z-index: 70; display: grid; place-items: center; padding: 16px; overflow-y: auto;
  background: rgba(11, 28, 48, .5); backdrop-filter: blur(6px); -webkit-backdrop-filter: blur(6px);
}
.csp-qr-modal {
  width: 100%; max-width: 460px; margin: auto; background: var(--c-surface); border: 1px solid var(--c-border);
  border-radius: 22px; padding: 20px; display: flex; flex-direction: column; gap: 16px;
  box-shadow: 0 30px 70px -14px rgba(0,0,0,.45); animation: csp-qr-in .18s ease-out;
}
:root:not(.dark) .csp-qr-modal { background: #fff; }
@keyframes csp-qr-in { from { opacity: 0; transform: translateY(10px) scale(.98); } }
.csp-qr-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.csp-qr-head h2 { font-size: 16px; font-weight: 800; }
.csp-qr-sub { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 6px; }
.csp-qr-sub b { font-size: 13px; font-weight: 700; color: var(--c-primary); }
.csp-qr-pill { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 999px; font-size: 10px; font-weight: 700; }
.csp-qr-pill i { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }
.csp-qr-pill[data-tone="success"] { color: var(--c-success); background: color-mix(in srgb, var(--c-success) 14%, transparent); }
.csp-qr-pill[data-tone="warning"] { color: var(--c-warning); background: color-mix(in srgb, var(--c-warning) 14%, transparent); }
.csp-qr-pill[data-tone="danger"] { color: var(--c-danger); background: color-mix(in srgb, var(--c-danger) 14%, transparent); }
.csp-qr-days { font-size: 10.5px; color: var(--c-text-muted); }
.csp-qr-x { color: var(--c-text-muted); flex-shrink: 0; }
.csp-qr-usage { display: flex; flex-direction: column; gap: 6px; }
.csp-qr-usage-row { display: flex; justify-content: space-between; font-size: 11px; color: var(--c-text-muted); }
.csp-qr-stage {
  display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 16px; border-radius: 16px;
  background: color-mix(in srgb, var(--c-text-muted) 6%, transparent);
}
.csp-qr-img { display: grid; place-items: center; width: 200px; height: 200px; padding: 12px; border-radius: 14px; background: #fff; }
.csp-qr-img img { width: 100%; height: 100%; object-fit: contain; }
.csp-qr-scan { font-size: 11px; color: var(--c-text-muted); text-align: center; line-height: 1.7; max-width: 300px; }
.csp-qr-btns { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
@media (max-width: 420px) { .csp-qr-btns { grid-template-columns: 1fr; } }
.csp-qr-btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 11px 12px; border-radius: 13px;
  font-size: 12px; font-weight: 700; cursor: pointer; border: 1px solid var(--c-border);
  background: color-mix(in srgb, var(--c-text-muted) 8%, transparent); color: var(--c-text); transition: .15s;
}
.csp-qr-btn:hover { border-color: var(--c-primary); }
.csp-qr-btn:disabled { opacity: .5; cursor: default; }
.csp-qr-btn--primary { background: var(--c-primary); color: #fff; border-color: var(--c-primary); }
.csp-qr-link { display: flex; flex-direction: column; gap: 6px; }
.csp-qr-link-label { font-size: 11px; font-weight: 700; color: var(--csp-text-2, var(--c-text)); }
.csp-qr-link-row { display: flex; align-items: center; gap: 6px; padding: 5px; border-radius: 13px; background: color-mix(in srgb, var(--c-text-muted) 8%, transparent); }
.csp-qr-link-row input { flex: 1; min-width: 0; border: 0; background: transparent; outline: none; font-size: 10.5px; color: var(--c-text-muted); }
.csp-qr-link-row button {
  flex-shrink: 0; padding: 7px 12px; border-radius: 9px; font-size: 11px; font-weight: 700; cursor: pointer;
  background: var(--c-surface); color: var(--c-primary); border: 1px solid var(--c-border);
}
:root:not(.dark) .csp-qr-link-row button { background: #fff; }
.csp-qr-steps { padding: 12px 14px; border-radius: 14px; background: color-mix(in srgb, var(--c-primary) 7%, transparent); }
.csp-qr-steps-t { font-size: 11.5px; font-weight: 700; margin-bottom: 8px; }
.csp-qr-steps-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
@media (max-width: 420px) { .csp-qr-steps-row { grid-template-columns: 1fr; } }
.csp-qr-step { display: flex; align-items: center; gap: 6px; font-size: 10.5px; color: var(--c-text-muted); }
.csp-qr-step-n {
  width: 20px; height: 20px; flex-shrink: 0; display: grid; place-items: center; border-radius: 50%;
  background: var(--c-primary); color: #fff; font-size: 10px; font-weight: 700;
}
[dir="rtl"] .csp-qr-btn--primary svg { transform: scaleX(-1); }
`
