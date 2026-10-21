import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, apiError, failureReason } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali } from '../lib/format'
import { addDays, addMonths, cellFromISO, monthName, toISO, todayCell } from '../lib/jalaliCalendar'
import { DateRangeModal, DRP_CSS } from '../components/DateRangePicker'
import { Ic } from '../components/AgencyIcons'
import { useToast } from '../components/Toast'

// Agency → Accounting: period overview + Jalali monthly report, all from the ledger
// (apps/agency/reports.py). Numbers come from the server; this file only lays out.

const T = {
  fa: {
    period: 'بازهٔ زمانی', today: 'امروز', d7: '7 روز اخیر', month: 'ماه جاری', prev: 'ماه گذشته', year: 'امسال', custom: 'بازهٔ دلخواه',
    charges: 'شارژ (درآمد)', payments: 'پرداخت‌های دریافتی', net: 'خالص (شارژ − پرداخت)', gb: 'گیگ واگذارشده', pay_n: 'تعداد پرداخت',
    outstanding: 'مانده بدهی همهٔ نماینده‌ها', outstanding_sub: '{n} نماینده بدهکار · بستانکاری {c}', all_time: 'کل دوره',
    chart: 'شارژ و پرداخت در طول زمان', per_day: 'روزانه', per_month: 'ماهانه', no_data: 'در این بازه گردشی ثبت نشده است.',
    recent: 'پرداخت‌های این بازه', date: 'تاریخ', reseller: 'نماینده', amount: 'مبلغ', method: 'روش', note: 'یادداشت',
    m_card: 'کارت به کارت', m_cash: 'نقدی', m_crypto: 'رمزارز', m_other: 'سایر',
    monthly: 'گزارش ماهانه', mon: 'ماه', resellers_charged: 'نماینده‌های شارژشده', open_month: 'جزئیات ماه',
    breakdown: 'جزئیات {m} به تفکیک نماینده', balance_end: 'مانده پایان ماه', total: 'جمع', close: 'بستن',
    csv: 'CSV', xlsx: 'Excel', downloaded: 'فایل دانلود شد', defs: 'شارژ = شارژ حجم + بدهکاری دستی + اصلاحیه‌ها · خالص = شارژ − پرداخت · ورودی‌های باطل‌شده حساب نمی‌شوند.',
    toman: 'تومان',
  },
  en: {
    period: 'Period', today: 'Today', d7: 'Last 7 days', month: 'This month', prev: 'Last month', year: 'This year', custom: 'Custom range',
    charges: 'Charges (income)', payments: 'Payments received', net: 'Net (charges − payments)', gb: 'GB granted', pay_n: 'Payments',
    outstanding: 'Outstanding (all resellers)', outstanding_sub: '{n} resellers owe · credit {c}', all_time: 'all time',
    chart: 'Charges vs payments over time', per_day: 'per day', per_month: 'per month', no_data: 'No ledger activity in this period.',
    recent: 'Payments in this period', date: 'Date', reseller: 'Reseller', amount: 'Amount', method: 'Method', note: 'Note',
    m_card: 'Card to card', m_cash: 'Cash', m_crypto: 'Crypto', m_other: 'Other',
    monthly: 'Monthly report', mon: 'Month', resellers_charged: 'Resellers charged', open_month: 'Month details',
    breakdown: '{m} by reseller', balance_end: 'Balance at month end', total: 'Total', close: 'Close',
    csv: 'CSV', xlsx: 'Excel', downloaded: 'Downloaded', defs: 'Charges = quota charges + manual charges + adjustments · Net = charges − payments · voided entries are excluded.',
    toman: 'T',
  },
}

const N = ({ children }) => <bdi dir="ltr" className="ag-num">{children}</bdi>
const fmtN = (n, d = 0) => Number(n || 0).toLocaleString('en-US', { maximumFractionDigits: d })
const short = (n) => { const a = Math.abs(n); return a >= 1e9 ? `${fmtN(n / 1e9, 1)}B` : a >= 1e6 ? `${fmtN(n / 1e6, 1)}M` : a >= 1e3 ? `${fmtN(n / 1e3, 0)}K` : fmtN(n) }

function presets() {
  const t = todayCell()
  const prev = addMonths(t.jy, t.jm, -1)
  const thisStart = toISO(t.jy, t.jm, 1)
  const prevEnd = addDays({ jy: t.jy, jm: t.jm, jd: 1 }, -1)        // last day of the previous Jalali month
  return {
    today: { from: t.iso, to: t.iso },
    d7: { from: addDays(t, -6).iso, to: t.iso },
    month: { from: thisStart, to: t.iso },
    prev: { from: toISO(prev.jy, prev.jm, 1), to: prevEnd.iso },
    year: { from: toISO(t.jy, 1, 1), to: t.iso },
  }
}

async function download(url, name, toast, s, lang) {
  try {
    const r = await api.get(url, { responseType: 'blob' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(r.data); a.download = name; document.body.appendChild(a); a.click(); a.remove()
    setTimeout(() => URL.revokeObjectURL(a.href), 3000)
    toast.success(s.downloaded)
  } catch (e) { toast.error(failureReason(e, lang)) }
}

function Kpi({ label, value, unit, ac, icon, sub }) {
  return (
    <div className="card ag-kpi" data-ac={ac}>
      <span className="ag-kpi-ico"><Ic n={icon} size={16} /></span>
      <span className="ag-kpi-l">{label}</span>
      <span className="ag-kpi-val"><N>{value}</N>{unit && <span className="rp-unit">{unit}</span>}</span>
      {sub && <span className="ag-kpi-sub">{sub}</span>}
    </div>
  )
}

function Chart({ series, bucket, s, lang }) {
  // drawn at the container's real width (no stretching → crisp text); scrolls if very dense
  const wrap = useRef(null)
  const [cw, setCw] = useState(640)
  useEffect(() => {
    const el = wrap.current
    if (!el) return undefined
    const ro = new ResizeObserver(([e]) => setCw(Math.max(280, Math.floor(e.contentRect.width))))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const max = Math.max(1, ...series.map((p) => Math.max(p.charges, p.payments)))
  const n = series.length
  const W = Math.max(cw, n * 14), H = 210, L = 44, B = 26, top = 8
  const bw = Math.max(3, Math.min(9, (W - L) / n / 2 - 2))
  const x = (i) => L + ((W - L) / n) * (i + 0.5)
  const y = (v) => top + (H - top - B) * (1 - v / max)
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => max * f)
  const every = Math.max(1, Math.ceil(n / Math.max(4, Math.floor((W - L) / 56))))
  const label = (k) => {
    if (bucket === 'month') { const [jy, jm] = k.split('/').map(Number); return `${monthName(jm, lang)} ${String(jy).slice(2)}` }
    const c = cellFromISO(k); return c ? `${c.jm}/${c.jd}` : k
  }
  return (
    <div className="rp-chart-wrap" ref={wrap} dir="ltr">
      <svg className="rp-chart" width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img"
        aria-label={`${s.chart} (${bucket === 'month' ? s.per_month : s.per_day})`}>
        {ticks.map((v, i) => (
          <g key={i}>
            <line x1={L} x2={W} y1={y(v)} y2={y(v)} className="rp-grid" />
            <text x={L - 6} y={y(v) + 4} className="rp-axis" textAnchor="end">{short(v)}</text>
          </g>
        ))}
        {series.map((p, i) => (
          <g key={p.key}>
            <title>{`${label(p.key)} — ${s.charges}: ${fmtN(p.charges)} · ${s.payments}: ${fmtN(p.payments)}`}</title>
            <rect x={x(i) - bw - 1} y={y(p.charges)} width={bw} height={Math.max(0, y(0) - y(p.charges))} rx="2" className="rp-bar rp-bar--c" />
            <rect x={x(i) + 1} y={y(p.payments)} width={bw} height={Math.max(0, y(0) - y(p.payments))} rx="2" className="rp-bar rp-bar--p" />
            {i % every === 0 && <text x={x(i)} y={H - 8} className="rp-axis" textAnchor="middle">{label(p.key)}</text>}
          </g>
        ))}
      </svg>
    </div>
  )
}

export function AgencyReports() {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const toast = useToast()
  const P = useMemo(presets, [])
  const [key, setKey] = useState('month')
  const [range, setRange] = useState(P.month)
  const [pick, setPick] = useState(false)
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [months, setMonths] = useState(null)
  const [sel, setSel] = useState(null)
  const [bd, setBd] = useState(null)

  useEffect(() => {
    setD(null); setErr('')
    api.get('/admin/agency/ledger/report/overview/', { params: { from: range.from, to: range.to } })
      .then((r) => setD(r.data)).catch((e) => { setErr(apiError(e)); setD(false) })
  }, [range.from, range.to])
  useEffect(() => { api.get('/admin/agency/ledger/report/monthly/').then((r) => setMonths(r.data.results)).catch((e) => setErr(apiError(e))) }, [])
  useEffect(() => {
    if (!sel) { setBd(null); return }
    setBd(null)
    api.get(`/admin/agency/ledger/report/monthly/${sel.year}/${sel.month}/`).then((r) => setBd(r.data)).catch((e) => toast.error(failureReason(e, lang)))
  }, [sel?.year, sel?.month])

  const choose = (k) => { setKey(k); if (k === 'custom') setPick(true); else setRange(P[k]) }
  const mLabel = (r) => `${monthName(r.month, lang)} ${r.year}`
  const k = d?.kpis
  return (
    <section className="rp space-y-4">
      <style>{RP_CSS + DRP_CSS}</style>
      <div className="card ag-card rp-filter">
        <span className="rp-filter-l"><Ic n="clock" size={14} />{s.period}</span>
        <div className="rp-chips" role="group" aria-label={s.period}>
          {['today', 'd7', 'month', 'prev', 'year', 'custom'].map((x) => (
            <button key={x} type="button" className={'ag-chip' + (key === x ? ' on' : '')} aria-pressed={key === x} onClick={() => choose(x)}>{s[x]}</button>
          ))}
        </div>
        <span className="rp-range"><N>{jalali(range.from, false, lang)}</N> — <N>{jalali(range.to, false, lang)}</N></span>
      </div>
      <DateRangeModal open={pick} onClose={() => setPick(false)}
        onApply={(r) => { if (r.from && r.to) setRange({ from: r.from, to: r.to }); else setKey(Object.keys(P).find((x) => P[x].from === range.from && P[x].to === range.to) || 'custom') }} />
      {err && <p className="ag-err" role="alert">{err}</p>}

      <div className="rp-kpis">
        <Kpi label={s.charges} value={k ? fmtN(k.charges) : '…'} unit={s.toman} ac="blue" icon="sold" />
        <Kpi label={s.payments} value={k ? fmtN(k.payments) : '…'} unit={s.toman} ac="green" icon="money" />
        <Kpi label={s.net} value={k ? fmtN(k.net) : '…'} unit={s.toman} ac="purple" icon="sliders" />
        <Kpi label={s.gb} value={k ? fmtN(k.gb, 2) : '…'} unit="GB" ac="cyan" icon="gauge" />
        <Kpi label={s.pay_n} value={k ? fmtN(k.payments_count) : '…'} ac="gray" icon="list" />
        <Kpi label={`${s.outstanding}`} value={k ? fmtN(k.outstanding) : '…'} unit={s.toman} ac="red" icon="wallet"
          sub={k ? s.outstanding_sub.replace('{n}', fmtN(k.resellers_owing)).replace('{c}', `${fmtN(k.credit)} ${s.toman}`) + ` · ${s.all_time}` : null} />
      </div>
      <p className="rp-defs">{s.defs}</p>

      <div className="card ag-card">
        <div className="ag-card-h">
          <h3 className="ag-sh" data-ac="blue"><Ic n="sold" size={15} />{s.chart} <small className="rp-sub">({d?.bucket === 'month' ? s.per_month : s.per_day})</small></h3>
          <span className="rp-legend"><i className="rp-dot rp-dot--c" />{s.charges} <i className="rp-dot rp-dot--p" />{s.payments}</span>
        </div>
        {d === null ? <div className="rp-skel" /> : d && (d.series.some((p) => p.charges || p.payments)
          ? <Chart series={d.series} bucket={d.bucket} s={s} lang={lang} /> : <p className="ag-empty">{s.no_data}</p>)}
      </div>

      <div className="card ag-card">
        <div className="ag-card-h"><h3 className="ag-sh" data-ac="green"><Ic n="money" size={15} />{s.recent}</h3><span className="ag-count">{d ? fmtN(d.recent_payments.length) : '…'}</span></div>
        {d && d.recent_payments.length === 0 ? <p className="ag-empty">{s.no_data}</p> : d && (
          <div className="ag-table-wrap">
            <table className="ag-table">
              <thead><tr><th>{s.date}</th><th>{s.reseller}</th><th>{s.amount}</th><th>{s.method}</th><th>{s.note}</th></tr></thead>
              <tbody>{d.recent_payments.map((p) => (
                <tr key={p.id}>
                  <td data-label={s.date}><N>{jalali(p.date, false, lang)}</N></td>
                  <td data-label={s.reseller} className="ag-t-name"><Link to={`/agency/admins/${encodeURIComponent(p.username)}#accounting`}>{p.username}</Link></td>
                  <td data-label={s.amount}><N>{fmtN(p.amount)}</N> <span className="rp-unit">{s.toman}</span></td>
                  <td data-label={s.method}>{s['m_' + p.method] || '—'}</td>
                  <td data-label={s.note} className="rp-note">{p.note || '—'}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card ag-card">
        <div className="ag-card-h">
          <h3 className="ag-sh" data-ac="purple"><Ic n="doc" size={15} />{s.monthly}</h3>
          <div className="ag-actions">
            <button type="button" className="ag-act ag-act--sm" data-tone="neutral" onClick={() => download(`/admin/agency/ledger/report/monthly/?export=csv&lang=${lang}`, 'agency-monthly.csv', toast, s, lang)}><Ic n="download" size={13} />{s.csv}</button>
            <button type="button" className="ag-act ag-act--sm" data-tone="neutral" onClick={() => download(`/admin/agency/ledger/report/monthly/?export=xlsx&lang=${lang}`, 'agency-monthly.xlsx', toast, s, lang)}><Ic n="download" size={13} />{s.xlsx}</button>
          </div>
        </div>
        {months === null ? <div className="rp-skel" /> : months.length === 0 ? <p className="ag-empty">{s.no_data}</p> : (
          <div className="ag-table-wrap">
            <table className="ag-table rp-months">
              <thead><tr><th>{s.mon}</th><th>{s.gb}</th><th>{s.charges}</th><th>{s.payments}</th><th>{s.net}</th><th>{s.resellers_charged}</th><th><span className="sr-only">{s.open_month}</span></th></tr></thead>
              <tbody>{months.map((r) => {
                const on = sel && sel.year === r.year && sel.month === r.month
                return (
                  <tr key={`${r.year}-${r.month}`} className={on ? 'rp-on' : ''} onClick={() => setSel(on ? null : r)}>
                    <td data-label={s.mon} className="ag-t-name"><b>{mLabel(r)}</b></td>
                    <td data-label={s.gb}><N>{fmtN(r.gb, 2)}</N></td>
                    <td data-label={s.charges}><N>{fmtN(r.charges)}</N></td>
                    <td data-label={s.payments}><N>{fmtN(r.payments)}</N></td>
                    <td data-label={s.net}><N>{fmtN(r.net)}</N></td>
                    <td data-label={s.resellers_charged}><N>{fmtN(r.resellers_charged)}</N></td>
                    <td><button type="button" className="ag-act ag-act--sm" data-tone={on ? 'primary' : 'neutral'} aria-expanded={!!on}
                      onClick={(e) => { e.stopPropagation(); setSel(on ? null : r) }}><Ic n="list" size={13} />{s.open_month}</button></td>
                  </tr>
                )
              })}</tbody>
            </table>
          </div>
        )}
      </div>

      {sel && (
        <div className="card ag-card" id="rp-breakdown">
          <div className="ag-card-h">
            <h3 className="ag-sh" data-ac="orange"><Ic n="users" size={15} />{s.breakdown.replace('{m}', mLabel(sel))}</h3>
            <div className="ag-actions">
              <button type="button" className="ag-act ag-act--sm" data-tone="neutral" onClick={() => download(`/admin/agency/ledger/report/monthly/${sel.year}/${sel.month}/?export=csv&lang=${lang}`, `agency-${sel.year}-${sel.month}.csv`, toast, s, lang)}><Ic n="download" size={13} />{s.csv}</button>
              <button type="button" className="ag-act ag-act--sm" data-tone="neutral" onClick={() => download(`/admin/agency/ledger/report/monthly/${sel.year}/${sel.month}/?export=xlsx&lang=${lang}`, `agency-${sel.year}-${sel.month}.xlsx`, toast, s, lang)}><Ic n="download" size={13} />{s.xlsx}</button>
              <button type="button" className="ag-act ag-act--sm" data-tone="neutral" onClick={() => setSel(null)}><Ic n="x" size={13} />{s.close}</button>
            </div>
          </div>
          {!bd ? <div className="rp-skel" /> : (
            <div className="ag-table-wrap">
              <table className="ag-table">
                <thead><tr><th>{s.reseller}</th><th>{s.gb}</th><th>{s.charges}</th><th>{s.payments}</th><th>{s.net}</th><th>{s.balance_end}</th></tr></thead>
                <tbody>
                  {bd.rows.map((r) => (
                    <tr key={r.username}>
                      <td data-label={s.reseller} className="ag-t-name"><Link to={`/agency/admins/${encodeURIComponent(r.username)}#accounting`}>{r.username}</Link></td>
                      <td data-label={s.gb}><N>{fmtN(r.gb, 2)}</N></td>
                      <td data-label={s.charges}><N>{fmtN(r.charges)}</N></td>
                      <td data-label={s.payments}><N>{fmtN(r.payments)}</N></td>
                      <td data-label={s.net}><N>{fmtN(r.net)}</N></td>
                      <td data-label={s.balance_end}><span className="rp-bal" data-sign={r.balance_end > 0 ? 'owes' : r.balance_end < 0 ? 'credit' : 'zero'}><N>{fmtN(r.balance_end)}</N></span></td>
                    </tr>
                  ))}
                  <tr className="rp-total">
                    <td data-label={s.total}><b>{s.total}</b></td>
                    <td data-label={s.gb}><N>{fmtN(bd.totals.gb, 2)}</N></td>
                    <td data-label={s.charges}><N>{fmtN(bd.totals.charges)}</N></td>
                    <td data-label={s.payments}><N>{fmtN(bd.totals.payments)}</N></td>
                    <td data-label={s.net}><N>{fmtN(bd.totals.net)}</N></td>
                    <td />
                  </tr>
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </section>
  )
}

const RP_CSS = `
.rp-filter { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; padding: 10px 12px; }
.rp-filter-l { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 700; color: var(--c-muted-fg); }
.rp-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.rp-range { margin-inline-start: auto; font-size: 12.5px; color: var(--c-muted-fg); white-space: nowrap; }
.rp-kpis { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 190px), 1fr)); }
.rp-unit { font-size: .55em; font-weight: 600; color: var(--c-muted-fg); margin: 0 5px; }
.rp-defs { font-size: 11.5px; color: var(--c-muted-fg); margin-top: -6px; line-height: 1.7; }
.rp-sub { font-weight: 500; color: var(--c-muted-fg); font-size: 12px; }
.rp-legend { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--c-muted-fg); }
.rp-dot { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-inline-start: 6px; }
.rp-dot--c, .rp-bar--c { background: var(--ac-blue); fill: var(--ac-blue); }
.rp-dot--p, .rp-bar--p { background: var(--ac-green); fill: var(--ac-green); }
.rp-chart-wrap { overflow-x: auto; }
.rp-chart { display: block; }
.rp-grid { stroke: var(--c-border); stroke-width: 1; }
.rp-axis { font-size: 10px; fill: var(--c-muted-fg); font-family: 'JetBrains Mono', ui-monospace, monospace; }
.rp-skel { height: 120px; border-radius: 10px; background: color-mix(in srgb, var(--c-text) 6%, transparent); animation: rp-p 1.2s ease-in-out infinite; }
@keyframes rp-p { 50% { opacity: .5; } }
@media (prefers-reduced-motion: reduce) { .rp-skel { animation: none; } }
.rp-note { max-width: 260px; white-space: normal !important; color: var(--c-muted-fg); font-size: 12px; }
.rp-months tbody tr { cursor: pointer; }
.rp-months tbody tr:hover > td, .rp-months tr.rp-on > td { background: color-mix(in srgb, var(--c-primary) 6%, transparent); }
.rp-total > td { font-weight: 800; border-top: 2px solid var(--c-border); }
.rp-bal[data-sign="owes"] { color: var(--c-danger-fg); font-weight: 700; } .rp-bal[data-sign="credit"] { color: var(--c-success-fg); font-weight: 700; } .rp-bal[data-sign="zero"] { color: var(--c-muted-fg); }
@media (max-width: 767px) { .rp-range { margin-inline-start: 0; width: 100%; } .rp-chips { flex-wrap: nowrap; overflow-x: auto; } .ag-chip { flex-shrink: 0; } }
`
