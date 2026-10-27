import { useEffect, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali } from '../lib/format'
import { Alert, Spinner } from '../components/ui'

// Agency → admin → "Limit history": every data-limit change of this admin, from our
// panel or made directly on PasarGuard (detected by the sync). Old → new, who, where.

const T = {
  fa: {
    h: 'تاریخچهٔ سقف', sub: 'هر تغییر سقف این ادمین — از همین پنل یا مستقیماً در PasarGuard (در همگام‌سازی تشخیص داده می‌شود).',
    empty: 'هنوز تغییری ثبت نشده است.', unlimited: 'نامحدود', unknown: 'نامشخص',
    when: 'زمان', change: 'تغییر', what: 'نوع', by: 'توسط', where: 'منبع', ledger: 'حسابداری', none: '—', voided: 'باطل‌شده',
    actions: { create: 'ساخت با سقف', set: 'تنظیم', add: 'افزایش', reduce: 'کاهش', remove: 'برداشتن سقف', external: 'تغییر در PasarGuard', baseline: 'مقدار اولیه' },
    sources: { panel: 'پنل نمایندگی', pasarguard: 'مستقیم در PasarGuard', history: 'تاریخچه' },
    toman: 'تومان', system: 'سیستم',
  },
  en: {
    h: 'Limit history', sub: "Every change of this admin's limit — from this panel or made directly on PasarGuard (detected by the sync).",
    empty: 'No changes recorded yet.', unlimited: 'Unlimited', unknown: 'unknown',
    when: 'Time', change: 'Change', what: 'Type', by: 'By', where: 'Source', ledger: 'Accounting', none: '—', voided: 'voided',
    actions: { create: 'Created with a limit', set: 'Set', add: 'Increase', reduce: 'Decrease', remove: 'Limit removed', external: 'Changed in PasarGuard', baseline: 'Baseline' },
    sources: { panel: 'Agency panel', pasarguard: 'PasarGuard directly', history: 'History' },
    toman: 'T', system: 'system',
  },
}
const GIB = 1024 ** 3

function Val({ b, s }) {
  if (b === null || b === undefined) return <span className="alh-u">{s.unknown}</span>
  if (b <= 0) return <span className="alh-u">{s.unlimited}</span>
  return <bdi dir="ltr" className="alh-v">{(b / GIB).toLocaleString('en-US', { maximumFractionDigits: 1 })} GB <small>({(b / 1024 ** 4).toLocaleString('en-US', { maximumFractionDigits: 3 })} TB)</small></bdi>
}

export default function AgencyLimitHistory({ username }) {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    setRows(null)
    api.get(`/admin/agency/admins/${encodeURIComponent(username)}/limit-history/`)
      .then((r) => setRows(r.data.results)).catch((e) => { setErr(apiError(e)); setRows([]) })
  }, [username])

  return (
    <div className="card ag-card alh">
      <style>{CSS}</style>
      <h3 className="font-bold">{s.h}</h3>
      <p className="text-xs text-muted">{s.sub}</p>
      <Alert>{err}</Alert>
      {rows === null ? <div className="grid place-items-center py-8"><Spinner /></div>
        : !rows.length ? <p className="text-sm text-muted py-4">{s.empty}</p> : (
          <ol className="alh-list">
            {rows.map((r) => {
              const d = r.old_limit_bytes > 0 && r.new_limit_bytes > 0 ? r.new_limit_bytes - r.old_limit_bytes : null
              return (
                <li key={r.id} className={`alh-row alh-${r.source}`}>
                  <div className="alh-top">
                    <span className="alh-act">{s.actions[r.action] || r.action}</span>
                    <span className={`alh-src alh-src-${r.source}`}>{s.sources[r.source] || r.source}</span>
                    <span className="alh-when">{jalali(r.at, true, lang)}</span>
                  </div>
                  <div className="alh-chg">
                    {r.action !== 'baseline' && <><Val b={r.old_limit_bytes} s={s} /><span aria-hidden>{lang === 'fa' ? ' ← ' : ' → '}</span></>}
                    <Val b={r.new_limit_bytes} s={s} />
                    {d !== null && d !== 0 && <bdi dir="ltr" className={d > 0 ? 'alh-up' : 'alh-down'}>({d > 0 ? '+' : '−'}{(Math.abs(d) / GIB).toLocaleString('en-US', { maximumFractionDigits: 1 })} GB)</bdi>}
                  </div>
                  <div className="alh-meta">
                    <span>{s.by}: <b>{r.staff || s.system}</b></span>
                    {r.ledger && <span>{s.ledger}: <bdi dir="ltr">{Number(r.ledger.amount).toLocaleString('en-US')} {s.toman}</bdi>{r.ledger.voided && ` (${s.voided})`}</span>}
                    {r.note && <span className="alh-note" dir="auto">{r.note}</span>}
                  </div>
                </li>
              )
            })}
          </ol>
        )}
    </div>
  )
}

const CSS = `
.alh { display: flex; flex-direction: column; gap: 8px; }
.alh-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
.alh-row { padding: 10px 0; border-top: 1px solid var(--c-border); display: flex; flex-direction: column; gap: 4px; }
.alh-row:first-child { border-top: 0; }
.alh-top { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; font-size: 13px; }
.alh-act { font-weight: 800; }
.alh-when { margin-inline-start: auto; font-size: 12px; color: var(--c-muted-fg); }
.alh-src { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--c-border); }
.alh-src-pasarguard { color: var(--c-warning-fg, var(--c-text)); background: color-mix(in srgb, var(--c-warning) 18%, transparent); border-color: transparent; }
.alh-src-panel { color: var(--c-primary); }
.alh-chg { font-size: 13.5px; }
.alh-v small, .alh-u { color: var(--c-muted-fg); }
.alh-up { color: var(--c-success-fg); font-weight: 700; } .alh-down { color: var(--c-danger-fg); font-weight: 700; }
.alh-up, .alh-down, .alh-v { display: inline-block; white-space: nowrap; } .alh-up, .alh-down { margin-inline-start: 8px; }
.alh-chg { display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 4px; }
.alh-meta { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 12px; color: var(--c-muted-fg); }
.alh-note { overflow-wrap: anywhere; }
`
