import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali } from '../lib/format'
import { Spinner } from '../components/ui'

export default function Monitoring() {
  const { t } = useI18n()
  const [health, setHealth] = useState(null)
  const [res, setRes] = useState(null)
  const [backups, setBackups] = useState(null)
  const [sys, setSys] = useState(null)

  const load = () => {
    api.get('/admin/health/').then((r) => setHealth(r.data)).catch(() => setHealth({ targets: [] }))
    api.get('/admin/resources/?limit=40').then((r) => setRes(r.data)).catch(() => {})
    api.get('/admin/backups/').then((r) => setBackups(r.data.results)).catch(() => setBackups([]))
    api.get('/admin/system/').then((r) => setSys(r.data)).catch(() => {})
  }
  const doUpdate = async () => {
    if (!confirm('نسخهٔ جدید نصب شود؟ سرویس‌ها چند لحظه بازراه‌اندازی می‌شوند.')) return
    await api.post('/admin/system/')
    load()
  }
  useEffect(() => { load(); const id = setInterval(load, 15000); return () => clearInterval(id) }, [])

  const runBackup = async () => { await api.post('/admin/backups/run/'); setTimeout(load, 2000) }

  if (!health) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold">{t('monitoring')}</h1>

      {sys && (
        <div className="card flex flex-wrap items-center gap-3">
          <span className="font-bold">نسخه {sys.version}</span>
          {sys.update_available
            ? <span className="text-warning text-sm">نسخهٔ {sys.latest_version} در دسترس است</span>
            : <span className="text-muted text-sm">به‌روز</span>}
          {sys.update_requested && <span className="text-secondary text-sm">درخواست به‌روزرسانی ثبت شده…</span>}
          <button className="btn-primary ms-auto text-sm" onClick={doUpdate}
            disabled={sys.update_requested || (!sys.update_available && sys.latest_version)}>
            به‌روزرسانی
          </button>
        </div>
      )}

      <div className="card">
        <div className="mb-2 font-bold">{t('health')} — {health.overall}</div>
        <div className="grid gap-2 sm:grid-cols-3">
          {health.targets.map((x) => (
            <div key={x.target} className="flex items-center justify-between rounded-xl border px-3 py-2 text-sm" style={{ borderColor: 'var(--c-border)' }}>
              <span>{x.target}</span>
              <span style={{ color: x.is_up == null ? 'var(--c-text-muted)' : x.is_up ? 'var(--c-success)' : 'var(--c-danger)' }}>
                {x.is_up == null ? '?' : x.is_up ? '●' : '●'} {x.detail}
              </span>
            </div>
          ))}
        </div>
      </div>

      {res?.latest && (
        <div className="card">
          <div className="mb-2 font-bold">{t('resources')}</div>
          <div className="grid gap-3 sm:grid-cols-3 text-sm">
            <Gauge label="CPU" pct={res.latest.cpu_percent} />
            <Gauge label="RAM" pct={res.latest.ram_percent} />
            <Gauge label="Disk" pct={res.latest.disk_percent} />
          </div>
        </div>
      )}

      <div className="card">
        <div className="mb-2 flex items-center justify-between">
          <span className="font-bold">پشتیبان‌ها</span>
          <button className="btn-primary text-sm" onClick={runBackup}>{t('run_backup')}</button>
        </div>
        {(backups || []).slice(0, 8).map((b) => (
          <div key={b.id} className="flex justify-between py-1 text-sm">
            <span className="truncate">{b.filename}</span>
            <span className="text-muted">{b.status} · {b.sent_to_telegram ? '✈' : '—'} · {jalali(b.created_at, true)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function Gauge({ label, pct }) {
  const p = Math.round(pct || 0)
  return (
    <div>
      <div className="flex justify-between"><span className="text-muted">{label}</span><span>{p}%</span></div>
      <div className="mt-1 h-2 rounded-full" style={{ background: 'var(--c-border)' }}>
        <div className="h-2 rounded-full" style={{ width: `${p}%`, background: p > 85 ? 'var(--c-danger)' : 'var(--c-primary)' }} />
      </div>
    </div>
  )
}
