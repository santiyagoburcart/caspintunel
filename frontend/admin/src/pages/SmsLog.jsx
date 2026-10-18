// /panel/sms-log — every SMS the operator phone (Android app / iPhone Shortcut)
// forwarded: sender, the amount the parser found, the matched order or WHY it
// did not match (sender not allowed, no amount, order expired/rejected, server
// rejected an empty message …). Card / account numbers arrive masked.
import { useEffect, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali, toman } from '../lib/format'
import { Spinner } from '../components/ui'
import { DataTable } from '../components/DataTable'

const T = {
  fa: {
    h1: 'لاگ پیامک‌ها', sub: 'پیامک‌هایی که گوشیِ دریافت‌کنندهٔ پیامک بانک به سرور فرستاده و نتیجهٔ تطبیق هرکدام با سفارش‌ها',
    all: 'همه', matched: 'تطبیق‌یافته', unmatched: 'تطبیق‌نیافته', mismatch: 'مغایرت مبلغ', mismatch_pill: 'مغایرت مبلغ — بررسی دستی', mm_less: 'مبلغ نامطابق: کمتر از فاکتور', mm_more: 'مبلغ نامطابق: بیشتر از فاکتور', mm_order: 'سفارش', rial: 'ریال', toman_u: 'تومان',
    time: 'زمان', sender: 'فرستنده', device: 'دستگاه', amount: 'مبلغ یافت‌شده', result: 'نتیجه', text: 'متن (شماره‌ها پوشانده شده)',
    ok: 'سفارش', none: 'تطبیق نشد', empty: 'پیامکی ثبت نشده است', more: 'بیشتر', unknown: 'نامشخص',
    hint: 'اگر پیامکی اینجا نیست، گوشی چیزی به سرور نفرستاده است (اتوماسیون/اپ را بررسی کنید). اگر هست، ستون «نتیجه» دلیل را می‌گوید.',
  },
  en: {
    h1: 'SMS log', sub: 'SMS the bank-SMS phone forwarded to the server, and how each was matched to an order',
    all: 'All', matched: 'Matched', unmatched: 'Not matched', mismatch: 'Amount mismatch', mismatch_pill: 'Amount mismatch — check by hand', mm_less: 'Amount mismatch: LESS than the invoice', mm_more: 'Amount mismatch: MORE than the invoice', mm_order: 'order', rial: 'Rial', toman_u: 'Toman',
    time: 'Time', sender: 'Sender', device: 'Device', amount: 'Amount found', result: 'Result', text: 'Text (numbers masked)',
    ok: 'Order', none: 'Not matched', empty: 'No SMS recorded yet', more: 'Load more', unknown: 'unknown',
    hint: 'If an SMS is missing here, the phone never sent it (check the automation / app). If it is here, "Result" says why.',
  },
}
const PAGE = 50

export default function SmsLog() {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const [filter, setFilter] = useState('')
  const [rows, setRows] = useState(null)
  const [next, setNext] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const load = async (offset = 0) => {
    setBusy(true); setErr('')
    try {
      const q = new URLSearchParams({ limit: PAGE, offset })
      if (filter) q.set('matched', filter)
      const { data } = await api.get(`/admin/sms-log/?${q}`)
      setRows((cur) => (offset ? [...(cur || []), ...data.results] : data.results))
      setNext(data.next ? offset + PAGE : null)
    } catch (e) { setErr(apiError(e)); setRows((cur) => cur || []) } finally { setBusy(false) }
  }
  useEffect(() => { setRows(null); load(0) }, [filter])

  return (
    <div className="smsl space-y-4">
      <style>{CSS}</style>
      <div>
        <h1 className="text-lg font-bold">{s.h1}</h1>
        <p className="text-sm text-muted mt-1">{s.sub}</p>
      </div>
      <div className="smsl-tabs" role="tablist">
        {[['', s.all], ['1', s.matched], ['0', s.unmatched], ['mismatch', s.mismatch]].map(([k, label]) => (
          <button key={k || 'all'} type="button" role="tab" aria-selected={filter === k}
            className={'smsl-tab' + (filter === k ? ' on' : '')} onClick={() => setFilter(k)}>{label}</button>
        ))}
      </div>
      <p className="smsl-hint">{s.hint}</p>
      {err && <div className="card text-sm" style={{ color: 'var(--c-danger)' }}>{err}</div>}
      {rows === null ? <div className="grid place-items-center py-16"><Spinner /></div> : (
        <>
          <DataTable
            empty={s.empty}
            emptyArt="inbox"
            rows={rows}
            columns={[
              { key: 'received_at', label: s.time, render: (r) => <span className="smsl-mono" dir="ltr">{jalali(r.received_at, true, lang)}</span> },
              { key: 'sender', label: s.sender, render: (r) => <span dir="auto">{r.sender || (r.source ? r.source : '—')}</span> },
              { key: 'device', label: s.device, render: (r) => r.device || '—' },
              { key: 'parsed_amount', label: s.amount, render: (r) => (r.parsed_raw != null ? (
                <span className="smsl-amt">
                  <span className="smsl-mono" dir="ltr">{r.parsed_raw.toLocaleString('en-US')} {r.parsed_unit === 'toman' ? s.toman_u : s.rial}</span>
                  {r.parsed_unit === 'rial' && <span className="text-xs text-muted">= {r.parsed_amount != null ? toman(r.parsed_amount, lang) : (r.parsed_raw / 10).toLocaleString('en-US', { maximumFractionDigits: 1 }) + (lang === 'en' ? ' T' : ' تومان')}</span>}
                </span>
              ) : r.parsed_amount != null ? toman(r.parsed_amount, lang) : <span className="text-muted">{s.unknown}</span>) },
              { key: 'result', label: s.result, render: (r) => (
                <div className="smsl-res">
                  {r.matched_order
                    ? <span className="smsl-pill smsl-pill--ok">{s.ok} #{r.matched_order}</span>
                    : r.mismatch_order
                      ? <span className="smsl-pill smsl-pill--bad">{r.mismatch_kind === 'more' ? s.mm_more : s.mm_less} · {s.mm_order} #{r.mismatch_order}{r.mismatch_invoice != null && <> · <bdi dir="ltr">{toman(r.mismatch_invoice, lang)}</bdi></>}</span>
                    : (r.note || '').startsWith('amount mismatch')
                      ? <span className="smsl-pill smsl-pill--bad">{s.mismatch_pill}</span>
                      : <span className="smsl-pill smsl-pill--no">{s.none}</span>}
                  {r.note && <span className="smsl-note" dir="auto">{r.note}</span>}
                </div>
              ) },
              { key: 'text', label: s.text, render: (r) => <pre className="smsl-text" dir="auto">{r.text || '—'}</pre> },
            ]}
          />
          {next != null && (
            <div className="flex justify-center">
              <button type="button" className="btn-ghost" disabled={busy} onClick={() => load(next)}>{busy ? '…' : s.more}</button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

const CSS = `
.smsl-tabs { display: inline-flex; flex-wrap: wrap; gap: 4px; padding: 4px; border-radius: 12px; background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); }
.smsl-tab { min-height: 40px; padding: 0 14px; border-radius: 9px; font-size: 13px; font-weight: 600; color: var(--c-text-muted); }
.smsl-tab.on { background: var(--c-primary); color: #fff; }
.smsl-hint { font-size: 12.5px; line-height: 1.9; color: var(--c-text-muted); }
.smsl-mono { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 12.5px; white-space: nowrap; }
.smsl-res { display: flex; flex-direction: column; gap: 4px; align-items: flex-start; min-width: 0; max-width: 340px; }
.smsl-pill { display: inline-flex; padding: 2px 9px; border-radius: 999px; font-size: 12px; font-weight: 700; white-space: nowrap; }
.smsl-pill--ok { color: var(--c-text); background: color-mix(in srgb, var(--c-success) 18%, transparent); }
.smsl-pill--no { color: var(--c-text); background: color-mix(in srgb, var(--c-warning) 20%, transparent); }
.smsl-pill--bad { color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 16%, transparent); font-weight: 700; }
.smsl-amt { display: inline-flex; flex-direction: column; gap: 1px; }
.smsl-note { font-size: 12px; line-height: 1.7; color: var(--c-text-muted); overflow-wrap: anywhere; }
.smsl-text { margin: 0; max-width: 360px; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 12px; line-height: 1.7;
  font-family: 'Vazirmatn', ui-sans-serif, system-ui, sans-serif; color: var(--c-text); }
@media (max-width: 767px), (pointer: coarse) { .smsl-tab { min-height: 44px; } .smsl-res, .smsl-text { max-width: none; } }
`
