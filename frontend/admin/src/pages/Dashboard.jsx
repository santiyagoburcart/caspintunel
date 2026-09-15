import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { useI18n, enumLabel } from '../lib/i18n'
import { jalali, toman, digits } from '../lib/format'
import { Alert, Spinner } from '../components/ui'
import { DataTable } from '../components/DataTable'

const ICONS = {
  services: 'M6.429 9.75L2.25 12l4.179 2.25m0-4.5l5.571 3 5.571-3m-11.142 0L2.25 7.5 12 2.25l9.75 5.25-4.179 2.25m0 0L21.75 12l-4.179 2.25m0 0l4.179 2.25L12 21.75 2.25 16.5l4.179-2.25m11.142 0l-5.571 3-5.571-3',
  online: 'M9.348 14.651a3.75 3.75 0 010-5.303m5.304 0a3.75 3.75 0 010 5.303m-7.425 2.122a6.75 6.75 0 010-9.546m9.546 0a6.75 6.75 0 010 9.546M5.106 18.894c-3.808-3.807-3.808-9.98 0-13.789m13.788 0c3.808 3.808 3.808 9.981 0 13.79M12 12h.008v.008H12V12z',
  revenue: 'M2.25 18.75a60.07 60.07 0 0115.797 2.101c.727.198 1.453-.342 1.453-1.096V18.75M3.75 4.5v.75A.75.75 0 013 6h-.75m0 0v-.375c0-.621.504-1.125 1.125-1.125H20.25M2.25 6v9m18-10.5v.75c0 .414.336.75.75.75h.75m-1.5-1.5h.375c.621 0 1.125.504 1.125 1.125v9.75c0 .621-.504 1.125-1.125 1.125h-.375m1.5-1.5H21a.75.75 0 00-.75.75v.75m0 0H3.75m0 0h-.375a1.125 1.125 0 01-1.125-1.125V15m1.5 1.5v-.75A.75.75 0 003 15h-.75M15 10.5a3 3 0 11-6 0 3 3 0 016 0zm3 0h.008v.008H18V10.5zm-12 0h.008v.008H6V10.5z',
  health: 'M3.75 12h3.128l1.782-4.898a.375.375 0 01.704.007l3.257 9.302a.375.375 0 00.71.006l2.09-5.888a.375.375 0 01.351-.237h4.728',
}

function DIcon({ name }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={ICONS[name] || ICONS.services} />
    </svg>
  )
}

function Kpi({ icon, label, value, sub, tone = 'blue' }) {
  return (
    <div className={'kpi kpi--' + tone}>
      <span className="kpi-ico"><DIcon name={icon} /></span>
      <div className="kpi-body">
        <div className="kpi-label">{label}</div>
        <div className="kpi-value">{value}</div>
        {sub ? <div className="kpi-sub">{sub}</div> : null}
      </div>
    </div>
  )
}

const STATUS_COLOR = { pending: 'warning', approved: 'success', rejected: 'danger' }
function StatusPill({ t, status }) {
  const color = `var(--c-${STATUS_COLOR[status] || 'text-muted'})`
  return (
    <span className="rounded-full px-2 py-0.5 text-xs"
      style={{ background: `color-mix(in srgb, ${color} 16%, transparent)`, color }}>
      {enumLabel(t, 'tx_', status)}
    </span>
  )
}

const ST_TONE = { active: 'success', on_hold: 'warning', pending: 'warning', limited: 'danger', expired: 'danger', disabled: 'danger' }

export default function Dashboard() {
  const { t, lang } = useI18n()
  const [d, setD] = useState(null)
  const [rev, setRev] = useState(null)
  const [recent, setRecent] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    api.get('/admin/dashboard/').then((r) => setD(r.data)).catch(() => { setD({}); setErr(t('load_error')) })
    api.get('/admin/accounting/?period=monthly').then((r) => setRev(r.data)).catch(() => {})
    api.get('/admin/transactions/?limit=5').then((r) => setRecent(r.data.results ?? r.data)).catch(() => setRecent([]))
  }, [])

  if (!d) return <div className="grid place-items-center py-16"><Spinner /></div>

  const byStatus = Object.entries(d.services?.by_status || {})
  const maxStatus = Math.max(1, ...byStatus.map(([, v]) => v))
  const down = d.health?.down || []

  const upCount = d.health?.up ?? 0
  const downCount = down.length

  return (
    <div className="dash space-y-4">
      <style>{CSS}</style>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-bold">{t('dashboard')}</h1>
        <span className="dash-live"><i />{t('live_sync')}</span>
      </div>
      <Alert>{err}</Alert>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi icon="services" tone="blue" label={t('services_total')} value={digits(d.services?.total ?? '—', lang)}
          sub={byStatus.length ? `${digits(d.services?.by_status?.active ?? 0, lang)} ${t('st_active')}` : ''} />
        <Kpi icon="online" tone="green" label={t('online_now')} value={digits(d.services?.online_now ?? 0, lang)} />
        <Kpi icon="revenue" tone="blue" label={`${t('revenue')} · ${t('last_30d')}`}
          value={rev ? toman(rev.revenue, lang) : '—'}
          sub={rev ? `${digits(rev.transactions, lang)} ${t('transactions')}` : ''} />
        <Kpi icon="health" tone={down.length ? 'amber' : 'green'} label={t('health')}
          value={`${digits(d.health?.up ?? 0, lang)} ${t('up')}`}
          sub={down.length ? down.join(' · ') : '—'} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="card lg:col-span-2">
          <div className="mb-3 flex items-center justify-between gap-2">
            <span className="font-bold">{t('services_by_status')}</span>
            <span className="dash-chip">{t('total')} {digits(d.services?.total ?? 0, lang)}</span>
          </div>
          {byStatus.length === 0 && <div className="text-sm text-muted">{t('none_found')}</div>}
          <div className="space-y-2.5">
            {byStatus.map(([k, v]) => (
              <div key={k} className="dash-srow">
                <span className="dash-dot" style={{ background: `var(--c-${ST_TONE[k] || 'text-muted'})` }} />
                <span className="dash-srow-l">{enumLabel(t, 'st_', k)}</span>
                <div className="dash-bar"><i style={{ width: `${(v / maxStatus) * 100}%`, background: `var(--c-${ST_TONE[k] || 'secondary'})` }} /></div>
                <b className="dash-srow-n">{digits(v, lang)}</b>
              </div>
            ))}
          </div>
        </div>

        <div className="card flex flex-col">
          <div className="mb-3 flex items-center justify-between gap-2">
            <span className="font-bold text-sm">{t('gateway_core_status')}</span>
            <span className={'dash-ring ' + (downCount ? 'warn' : 'ok')} />
          </div>
          <p className="text-xs text-muted leading-6">
            {downCount ? t('some_down', { n: digits(downCount, lang) }) : t('all_connected')}
          </p>
          <div className="mt-auto flex items-center justify-between border-t pt-3 text-xs" style={{ borderColor: 'var(--c-border)' }}>
            <span className="text-muted">{t('health')}</span>
            <span className="dash-srow-n font-bold" style={{ color: downCount ? 'var(--c-warning)' : 'var(--c-success)' }}>
              {digits(upCount, lang)}{d.health?.total ? ` / ${digits(d.health.total, lang)}` : ''} {t('up')}
            </span>
          </div>
        </div>
      </div>

      {recent && recent.length > 0 && (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-bold">{t('recent_transactions')}
              <span className="dash-chip ms-2">{t('recent_n', { n: digits(recent.length, lang) })}</span>
            </span>
            <Link to="/transactions" className="text-xs font-bold" style={{ color: 'var(--c-primary)' }}>
              {t('view_all_tx')} →
            </Link>
          </div>
          <DataTable
            empty={t('none_found')}
            columns={[
              { key: 'user', label: t('user'), render: (r) => (
                <span className="dash-uchip">
                  <span className="dash-uav">{String(r.user || '?').replace(/^tg_/, '').slice(0, 2).toUpperCase()}</span>
                  <span dir="ltr">{r.user}</span>
                </span>
              ) },
              { key: 'plan_name', label: t('plan'), render: (r) => r.plan_name || '—' },
              { key: 'amount', label: t('amount'), render: (r) => toman(r.amount, lang) },
              { key: 'status', label: t('status'), render: (r) => <StatusPill t={t} status={r.status} /> },
              { key: 'created_at', label: t('date'), render: (r) => jalali(r.created_at, true, lang) },
            ]}
            rows={recent}
          />
        </div>
      )}
    </div>
  )
}

const CSS = `
.dash .kpi {
  position: relative; overflow: hidden;
  display: flex; align-items: flex-start; gap: 14px;
  padding: 18px; border-radius: 16px;
  border: 1px solid var(--c-border);
  background:
    radial-gradient(120% 130% at 100% 0%, color-mix(in srgb, var(--kpi-c) 12%, transparent) 0%, transparent 55%),
    var(--c-surface);
}
[data-theme-style="caspian"] .dash .kpi { box-shadow: 0 1px 3px rgba(15,23,42,.05); }
[data-theme-style="caspian"].dark .dash .kpi {
  background:
    radial-gradient(120% 130% at 100% 0%, color-mix(in srgb, var(--kpi-c) 22%, transparent) 0%, transparent 55%),
    #0d131f;
  border-color: var(--c-border);
}
.dash .kpi::before {
  content: ''; position: absolute; inset-inline-start: 0; inset-block: 0; width: 3px;
  background: var(--kpi-c);
}
.dash .kpi--blue { --kpi-c: var(--c-primary); }
.dash .kpi--green { --kpi-c: var(--c-success); }
.dash .kpi--amber { --kpi-c: var(--c-warning); }

.dash .kpi-ico {
  flex: 0 0 auto; width: 42px; height: 42px; border-radius: 12px;
  display: grid; place-items: center;
  background: color-mix(in srgb, var(--kpi-c) 14%, transparent);
  color: var(--kpi-c);
}
.dash .kpi-ico svg { width: 22px; height: 22px; }
.dash .kpi-body { min-width: 0; }
.dash .kpi-label { font-size: 12px; color: var(--c-text-muted); }
.dash .kpi-value { font-size: 26px; font-weight: 800; line-height: 1.15; margin-top: 2px; letter-spacing: -.01em; }
.dash .kpi-sub { font-size: 11.5px; color: var(--c-text-muted); margin-top: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.dash .dash-bar { height: 7px; border-radius: 999px; overflow: hidden; background: color-mix(in srgb, var(--c-text-muted) 20%, transparent); }
.dash .dash-bar > i { display: block; height: 100%; border-radius: 999px; transition: width .4s ease; }

.dash-live { display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px; font-weight: 600; color: var(--c-text-muted); }
.dash-live i { width: 7px; height: 7px; border-radius: 50%; background: var(--c-success); animation: dash-pp 1.8s ease-in-out infinite; }
@keyframes dash-pp { 50% { opacity: .35; } }
.dash-chip { font-size: 11px; font-weight: 700; padding: 2px 9px; border-radius: 999px; color: var(--c-text-muted); background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); }
.dash-ring { width: 11px; height: 11px; border-radius: 50%; flex-shrink: 0; }
.dash-ring.ok { background: var(--c-success); box-shadow: 0 0 0 4px color-mix(in srgb, var(--c-success) 18%, transparent); }
.dash-ring.warn { background: var(--c-warning); box-shadow: 0 0 0 4px color-mix(in srgb, var(--c-warning) 18%, transparent); }
.dash-uchip { display: inline-flex; align-items: center; gap: 8px; }
.dash-uav { width: 26px; height: 26px; flex-shrink: 0; display: grid; place-items: center; border-radius: 8px; font-size: 10px; font-weight: 800; background: color-mix(in srgb, var(--c-primary) 14%, transparent); color: var(--c-primary); font-family: 'JetBrains Mono', ui-monospace, monospace; }

.dash .dash-srow { display: grid; grid-template-columns: auto 1fr minmax(70px, 90px) auto; align-items: center; gap: 10px; font-size: 13px; }
.dash .dash-dot { width: 8px; height: 8px; border-radius: 50%; flex: 0 0 auto; }
.dash .dash-srow-l { color: var(--c-text-muted); white-space: nowrap; }
.dash .dash-srow-n { font-variant-numeric: tabular-nums; }
@media (max-width: 420px) { .dash .dash-srow { grid-template-columns: auto 1fr auto; } .dash .dash-srow .dash-bar { display: none; } }
`
