import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali, digits } from '../lib/format'

// v1.53 (multi-tenant Phase 10) a store's backups (backend apps/tenancy/export.py): start one (built in the background,
// progress shown), then «دریافت» makes a ONE-TIME link and the browser downloads the zip. Used on the store's own page
// (base = /admin/store-export/) and on our «فروشگاه» card (base = …/store/exports/, `platform`: no 6-hour gap).
const T = {
  fa: {
    title: 'پشتیبان داده‌های فروشگاه', start: 'ساخت پشتیبان جدید', none: 'هنوز پشتیبانی ساخته نشده است.',
    desc: 'یک فایل zip از داده‌های همین فروشگاه، با فرمت JSON و CSV (قابل باز کردن در Excel). در پس‌زمینه ساخته می‌شود.',
    has: 'شامل:', hasnt: 'بدون رمز عبور، توکن ربات و فایل‌های پیوست/رسید؛ از شمارهٔ کارت‌ها فقط ۴ رقم آخر می‌ماند.',
    rules: 'هر لینک دریافت فقط یک بار کار می‌کند؛ فایل {h} ساعت پس از آماده شدن پاک می‌شود. هر {g} ساعت یک پشتیبان.',
    rules_p: 'هر لینک دریافت فقط یک بار و فقط روی همین پنل کار می‌کند؛ فایل {h} ساعت پس از آماده شدن پاک می‌شود.',
    off: 'دریافت پشتیبان برای این فروشگاه فعال نیست — از پشتیبانی بخواهید فعالش کند.', next: 'پشتیبان بعدی از {t}',
    queued: 'در صف', running: 'در حال ساخت', ready: 'آماده', failed: 'ناموفق', expired: 'منقضی شد',
    get: 'دریافت فایل', size: 'حجم', rows: 'ردیف', by: 'درخواست', until: 'تا', downloads: 'دریافت‌ها', support: 'پشتیبانی',
  },
  en: {
    title: 'Store data backup', start: 'Make a new backup', none: 'No backup yet.',
    desc: 'A zip of this store’s own data as JSON and CSV (opens in Excel). It is prepared in the background.',
    has: 'Includes:', hasnt: 'No passwords, bot token or attachment / receipt files; card numbers keep only the last 4 digits.',
    rules: 'Each download link works once; the file is deleted {h} hours after it is ready. One backup every {g} hours.',
    rules_p: 'Each download link works once and only on this panel; the file is deleted {h} hours after it is ready.',
    off: 'Backups are not enabled for this store — ask support to turn them on.', next: 'Next backup from {t}',
    queued: 'Queued', running: 'Preparing', ready: 'Ready', failed: 'Failed', expired: 'Expired',
    get: 'Download', size: 'Size', rows: 'rows', by: 'Asked by', until: 'until', downloads: 'Downloads', support: 'Support',
  },
}

const size = (n, lang) => {
  const mb = Number(n || 0) / 1024 / 1024
  return digits(mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.max(1, Math.round(mb * 1024))} KB`, lang)
}

export default function StoreExports({ base, platform = false, canStart = true }) {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const [d, setD] = useState(null)
  const [busy, setBusy] = useState(false)
  const timer = useRef(null)
  const load = () => api.get(base).then((r) => setD(r.data)).catch(() => setD((x) => x || { results: [], allowed: false }))
  useEffect(() => { load(); return () => clearTimeout(timer.current) }, [base])
  useEffect(() => {                                   // follow a running export until it is ready
    clearTimeout(timer.current)
    if (d?.busy) timer.current = setTimeout(load, 2500)
  }, [d])

  const start = async () => {
    setBusy(true)
    try { await api.post(base, {}); await load() } catch { /* the toast shows why */ } finally { setBusy(false) }
  }
  const download = async (id) => {
    try {
      const r = await api.post(`${base}${id}/link/`, {})
      window.location.assign(r.data.url)                 // one-time link: the browser downloads the zip
      setTimeout(load, 1500)
    } catch { load() }
  }

  if (!d) return null
  const wait = d.next_allowed_at && new Date(d.next_allowed_at) > new Date()
  const names = (d.datasets || []).map((x) => (lang === 'fa' ? x.fa : x.en)).join(lang === 'fa' ? '، ' : ', ')
  return (
    <section className="sx" data-testid="store-exports">
      <style>{CSS}</style>
      <div className="sx-head">
        <b>{s.title}</b>
        {canStart && d.allowed && (
          <button type="button" className="btn-primary text-sm sx-btn" disabled={busy || d.busy || wait} onClick={start}
            data-testid="export-start">{busy ? '…' : s.start}</button>
        )}
      </div>
      <p className="sx-desc">{s.desc}</p>
      {names && <p className="sx-desc"><b>{s.has}</b> {names}.</p>}
      <p className="sx-desc">{s.hasnt}</p>
      <p className="sx-desc">{(platform ? s.rules_p : s.rules).replace('{h}', digits(d.keep_hours ?? 24, lang)).replace('{g}', digits(d.gap_hours ?? 6, lang))}</p>
      {!d.allowed && <p className="sx-off" role="status" data-testid="export-off">{s.off}</p>}
      {wait && <p className="text-xs text-muted">{s.next.replace('{t}', jalali(d.next_allowed_at, true, lang))}</p>}
      {d.results.length === 0 ? <p className="text-sm text-muted">{s.none}</p> : (
        <div className="sx-list">
          {d.results.map((e) => {
            const total = Object.values(e.counts || {}).reduce((a, b) => a + Number(b || 0), 0)
            return (
              <article key={e.id} className="sx-card" data-testid="export-row" data-state={e.state}>
                <div className="sx-top">
                  <span className="sx-pill" data-st={e.state}>{s[e.state] || e.state}</span>
                  <span className="text-xs text-muted">{jalali(e.created_at, true, lang)}</span>
                </div>
                {(e.state === 'running' || e.state === 'queued') && (
                  <div className="sx-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={e.progress}>
                    <i style={{ width: `${Math.max(3, e.progress)}%` }} /><span>{digits(`${e.progress}%`, lang)}</span>
                  </div>
                )}
                <div className="sx-meta">
                  {e.state === 'ready' && <span><small>{s.size}</small><span><bdi dir="ltr">{size(e.size, lang)}</bdi> · <bdi dir="ltr">{digits(total, lang)}</bdi> {s.rows}</span></span>}
                  {e.state === 'ready' && <span><small>{s.until}</small>{jalali(e.expires_at, true, lang)}</span>}
                  <span><small>{s.by}</small><bdi dir="auto">{e.requested_by === 'support' ? s.support : e.requested_by || '—'}</bdi></span>
                  {e.downloads > 0 && <span><small>{s.downloads}</small>{digits(e.downloads, lang)}</span>}
                </div>
                {e.state === 'failed' && e.error && <p className="sx-err"><bdi dir="ltr">{e.error}</bdi></p>}
                {e.state === 'ready' && (d.allowed || platform) && (
                  <button type="button" className="btn-primary text-sm sx-btn" onClick={() => download(e.id)}
                    data-testid={`export-get-${e.id}`}>{s.get}</button>
                )}
              </article>
            )
          })}
        </div>
      )}
    </section>
  )
}

const CSS = `
.sx { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.sx-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; font-size: 14px; }
.sx-desc { font-size: 12.5px; line-height: 1.8; color: var(--c-text-muted); margin: 0; }
.sx-off { font-size: 13px; padding: 8px 10px; border-radius: 10px; margin: 0; color: var(--c-warning-fg);
  background: color-mix(in srgb, var(--c-warning) 12%, transparent); }
.sx-btn { min-height: 44px; }
.sx-list { display: flex; flex-direction: column; gap: 8px; }
.sx-card { display: flex; flex-direction: column; gap: 8px; padding: 10px 12px; border-radius: 12px; border: 1px solid var(--c-border);
  background: var(--c-bg); min-width: 0; }
.sx-top { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; }
.sx-pill { font-size: 12px; font-weight: 800; padding: 2px 10px; border-radius: 999px; color: var(--c-muted-fg);
  background: color-mix(in srgb, var(--c-text-muted) 16%, transparent); }
.sx-pill[data-st="ready"] { color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 16%, transparent); }
.sx-pill[data-st="running"], .sx-pill[data-st="queued"] { color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 12%, transparent); }
.sx-pill[data-st="failed"] { color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 14%, transparent); }
.sx-bar { position: relative; height: 22px; border-radius: 999px; overflow: hidden; background: color-mix(in srgb, var(--c-primary) 10%, transparent); }
.sx-bar i { position: absolute; inset-block: 0; inset-inline-start: 0; background: var(--c-primary); transition: width .4s; }
.sx-bar span { position: relative; display: grid; place-items: center; height: 100%; font-size: 11.5px; font-weight: 800; color: var(--c-text); }
.sx-meta { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 140px), 1fr)); gap: 6px 12px; font-size: 13px; }
.sx-meta > span { display: flex; flex-direction: column; gap: 2px; min-width: 0; overflow-wrap: anywhere; }
.sx-meta small { font-size: 11px; color: var(--c-text-muted); }
.sx-err { font-size: 12.5px; margin: 0; color: var(--c-danger-fg); overflow-wrap: anywhere; }
`
