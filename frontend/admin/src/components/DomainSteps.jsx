import { useI18n } from '../lib/i18n'
import { jalali } from '../lib/format'

// v1.60: a store domain's walk «DNS → گواهی → پیکربندی nginx → بررسی سلامت → فعال» (backend tenancy/domains.py::steps).
// Each step: done / current / error / failed / waiting + its time and last error (our staff only — the store gets none).
const T = {
  fa: {
    dns: 'DNS', cert: 'گواهی', nginx: 'پیکربندی nginx', health: 'بررسی سلامت', active: 'فعال',
    done: 'انجام شد', current: 'در حال انجام', error: 'خطا', failed: 'متوقف شد', waiting: 'در انتظار',
    since: 'از', watcher: 'منتظر نوبت بعدی سرور (هر دقیقه)', expires: 'گواهی تا', aria: 'مراحل فعال‌سازی دامنه',
  },
  en: {
    dns: 'DNS', cert: 'Certificate', nginx: 'nginx config', health: 'Health check', active: 'Live',
    done: 'done', current: 'in progress', error: 'error', failed: 'stopped', waiting: 'waiting',
    since: 'since', watcher: 'waiting for the server’s next run (every minute)', expires: 'certificate until', aria: 'Domain activation steps',
  },
}
const MARK = { done: '✓', current: '•', error: '!', failed: '✗', waiting: '' }

export default function DomainSteps({ steps, certExpires }) {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  if (!steps?.length) return null
  return (
    <div className="dst">
      <style>{CSS}</style>
      <ol className="dst-row" aria-label={s.aria} data-testid="domain-steps">
        {steps.map((x, i) => (
          <li key={x.key} className="dst-step" data-st={x.state} data-testid={`step-${x.key}`} aria-current={x.state === 'current' || x.state === 'error' ? 'step' : undefined}>
            <span className="dst-dot" aria-hidden="true">{MARK[x.state] || i + 1}</span>
            <span className="dst-body">
              <b>{s[x.key]}</b>
              <span className="dst-st">{s[x.state] || x.state}</span>
              {x.at && <span className="dst-at">{jalali(x.at, true, lang)}</span>}
              {x.since && x.state !== 'done' && <span className="dst-at">{s.since} {jalali(x.since, true, lang)}</span>}
              {x.waiting_watcher && <span className="dst-at">{s.watcher}</span>}
              {x.key === 'cert' && certExpires && <span className="dst-at">{s.expires} {jalali(certExpires, false, lang)}</span>}
            </span>
          </li>
        ))}
      </ol>
      {steps.filter((x) => x.error).map((x) => (
        <p key={x.key} className="dst-err" data-testid={`step-error-${x.key}`}><b>{s[x.key]}:</b> <bdi dir="ltr">{x.error}</bdi></p>
      ))}
    </div>
  )
}

const CSS = `
.dst { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.dst-row { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 118px), 1fr)); gap: 6px; }
.dst-step { display: flex; gap: 6px; align-items: flex-start; padding: 8px; border-radius: 12px; min-width: 0;
  border: 1px solid var(--c-border); background: var(--c-bg); }
.dst-dot { width: 22px; height: 22px; flex: 0 0 auto; border-radius: 999px; display: grid; place-items: center; font-size: 12px; font-weight: 800;
  color: var(--c-text-muted); background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); }
.dst-body { display: flex; flex-direction: column; gap: 2px; min-width: 0; font-size: 12px; line-height: 1.5; }
.dst-body b { font-size: 12.5px; }
.dst-st { font-weight: 700; color: var(--c-text-muted); }
.dst-at { color: var(--c-text-muted); font-size: 11.5px; overflow-wrap: anywhere; }
.dst-step[data-st="done"] .dst-dot { color: #fff; background: #11AB53; }
.dst-step[data-st="done"] .dst-st { color: var(--c-success-fg); }
.dst-step[data-st="current"] { border-color: color-mix(in srgb, var(--c-primary) 45%, var(--c-border)); }
.dst-step[data-st="current"] .dst-dot { color: #fff; background: var(--c-primary); }
.dst-step[data-st="current"] .dst-st { color: var(--c-text); }
.dst-step[data-st="error"], .dst-step[data-st="failed"] { border-color: color-mix(in srgb, var(--c-danger) 45%, var(--c-border)); }
.dst-step[data-st="error"] .dst-dot, .dst-step[data-st="failed"] .dst-dot { color: #fff; background: var(--c-danger); }
.dst-step[data-st="error"] .dst-st, .dst-step[data-st="failed"] .dst-st { color: var(--c-danger-fg); }
.dst-err { margin: 0; font-size: 12px; color: var(--c-danger-fg); overflow-wrap: anywhere; }
@media (max-width: 767px) {
  .dst-row { grid-template-columns: minmax(0, 1fr); }
  .dst-step { min-height: 44px; align-items: center; }
  .dst-body { flex-direction: row; flex-wrap: wrap; column-gap: 8px; }
}
`
