import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { useI18n, enumLabel } from '../lib/i18n'
import { toman, jalali, digits } from '../lib/format'
import { Alert, Spinner } from '../components/ui'
import { DateRangeModal, DRP_CSS } from '../components/DateRangePicker'
import { BankFilterSheet, BFS_CSS } from '../components/BankFilterSheet'

function Ico({ d, w = 16 }) {
  return (
    <svg viewBox="0 0 24 24" width={w} height={w} fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{d}</svg>
  )
}
const ICONS = {
  wallet: <><rect x="2" y="6" width="20" height="14" rx="2" /><path d="M16 12h.01M2 10h20" /></>,
  calendar: <><rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" /></>,
  trendUp: <><polyline points="23 6 13.5 15.5 8.5 10.5 1 18" /><polyline points="17 6 23 6 23 12" /></>,
  receipt: <><path d="M4 2h16v20l-3-2-3 2-3-2-3 2-3-2-1 2z" /><line x1="8" y1="7" x2="16" y2="7" /><line x1="8" y1="11" x2="16" y2="11" /></>,
  hub: <><circle cx="12" cy="12" r="3" /><circle cx="12" cy="3" r="1.5" /><circle cx="12" cy="21" r="1.5" /><circle cx="3" cy="12" r="1.5" /><circle cx="21" cy="12" r="1.5" /><path d="M12 6v3M12 15v3M6 12h3M15 12h3" /></>,
  card: <><rect x="2" y="5" width="20" height="14" rx="2" /><line x1="2" y1="10" x2="22" y2="10" /></>,
  panel: <><rect x="3" y="3" width="7" height="9" rx="1" /><rect x="14" y="3" width="7" height="5" rx="1" /><rect x="14" y="12" width="7" height="9" rx="1" /><rect x="3" y="16" width="7" height="5" rx="1" /></>,
  filter: <path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3z" />,
  bank: <><path d="M3 21h18M4 10h16M6 21V10M18 21V10M12 3l9 5H3l9-5z" /></>,
  arrow: <><line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" /></>,
}

const T = {
  fa: {
    h1: 'حسابداری و تحلیل درآمد', sub: 'بررسی گردش مالی، روند دریافتی‌ها و تفکیک تراکنش‌های تأییدشده',
    daily: 'روزانه', weekly: 'هفتگی', monthly: 'ماهانه', filter_dates: 'بازهٔ تاریخ',
    filter_banks: 'بانک‌ها و روش‌ها',
    revenue: 'درآمد کل دوره', tx_count: 'تعداد تراکنش‌ها', avg_tx: 'میانگین هر تراکنش', period_range: 'بازهٔ محاسباتی',
    growth: 'نسبت به دورهٔ مشابه قبل', tx_unit: 'تراکنش',
    daily_trend: 'روند روزانهٔ دریافتی‌ها', peak: 'اوج دریافت',
    by_panel: 'بر اساس پنل', by_method: 'بر اساس روش پرداخت', by_source: 'بر اساس منبع ورودی', by_card: 'بر اساس کارت مقصد',
    none_found: 'داده‌ای برای این بازه ثبت نشده است',
    recent: 'تراکنش‌های اخیر', view_all: 'مشاهده همه',
    of_total: 'از کل درآمد دوره',
  },
  en: {
    h1: 'Accounting & revenue analysis', sub: 'Review cashflow, the daily trend and a breakdown of approved transactions',
    daily: 'Daily', weekly: 'Weekly', monthly: 'Monthly', filter_dates: 'Date range',
    filter_banks: 'Banks & methods',
    revenue: 'Total period revenue', tx_count: 'Transaction count', avg_tx: 'Average per transaction', period_range: 'Calculation range',
    growth: 'vs. the previous equal period', tx_unit: 'tx',
    daily_trend: 'Daily revenue trend', peak: 'Peak',
    by_panel: 'By panel', by_method: 'By payment method', by_source: 'By source', by_card: 'By destination card',
    none_found: 'No data recorded for this range',
    recent: 'Recent transactions', view_all: 'View all',
    of_total: 'of period revenue',
  },
}

function shiftPrevRange(from, to) {
  if (!from || !to) return null
  const f = new Date(from), tt = new Date(to)
  const spanMs = tt.getTime() - f.getTime()
  const prevTo = new Date(f.getTime() - 86400000)
  const prevFrom = new Date(prevTo.getTime() - spanMs)
  return { from: prevFrom.toISOString().slice(0, 10), to: prevTo.toISOString().slice(0, 10) }
}

export default function Accounting() {
  const { t, lang } = useI18n()
  const s = T[lang] || T.fa
  const [period, setPeriod] = useState('monthly')
  const [range, setRange] = useState({ from: '', to: '' })
  const [d, setD] = useState(null)
  const [prevRevenue, setPrevRevenue] = useState(null)
  const [err, setErr] = useState('')
  const [dateOpen, setDateOpen] = useState(false)
  const [bankOpen, setBankOpen] = useState(false)
  const [bankFilter, setBankFilter] = useState({ banks: [], methods: [] })
  const [recent, setRecent] = useState(null)

  const load = () => {
    setD(null); setErr('')
    const p = new URLSearchParams()
    if (range.from || range.to) {
      if (range.from) p.set('from', range.from)
      if (range.to) p.set('to', range.to)
    } else p.set('period', period)
    api.get(`/admin/accounting/?${p}`)
      .then((r) => setD(r.data))
      .catch(() => { setD({}); setErr(t('load_error')) })
  }
  useEffect(load, [period, range.from, range.to])

  // real % growth vs. the immediately preceding period of equal length
  useEffect(() => {
    if (!d?.range?.from_gregorian || !d?.range?.to_gregorian) { setPrevRevenue(null); return }
    const prev = shiftPrevRange(d.range.from_gregorian, d.range.to_gregorian)
    if (!prev) return
    api.get(`/admin/accounting/?from=${prev.from}&to=${prev.to}`)
      .then((r) => setPrevRevenue(r.data.revenue || 0))
      .catch(() => setPrevRevenue(null))
  }, [d?.range?.from_gregorian, d?.range?.to_gregorian])

  useEffect(() => {
    api.get('/admin/transactions/?status=approved')
      .then((r) => setRecent((r.data.results ?? r.data).slice(0, 8)))
      .catch(() => setRecent([]))
  }, [])

  const daily = d?.daily || []
  const max = daily.reduce((m, x) => Math.max(m, Number(x.revenue || 0)), 0) || 1
  const peakIdx = daily.reduce((best, x, i) => (Number(x.revenue || 0) > Number(daily[best]?.revenue || -1) ? i : best), 0)

  const growthPct = useMemo(() => {
    if (prevRevenue == null || !d?.revenue) return null
    if (prevRevenue === 0) return d.revenue > 0 ? 100 : 0
    return Math.round(((d.revenue - prevRevenue) / prevRevenue) * 1000) / 10
  }, [prevRevenue, d?.revenue])

  const avgTx = d?.transactions ? Math.round((d.revenue || 0) / d.transactions) : 0

  const bankActive = bankFilter.banks.length + bankFilter.methods.length
  const filteredRecent = (recent || []).filter((r) => (
    (bankFilter.banks.length === 0 || bankFilter.banks.includes(r.card_bank))
    && (bankFilter.methods.length === 0 || bankFilter.methods.includes(r.method))
  ))

  return (
    <div className="acc space-y-4">
      <style>{DRP_CSS}{BFS_CSS}{CSS}</style>

      <div className="acc-head">
        <div className="acc-head-main">
          <span className="acc-head-ico"><Ico d={ICONS.wallet} w={20} /></span>
          <div>
            <h1 className="text-lg font-bold">{s.h1}</h1>
            <p className="mt-1 text-sm text-muted">{s.sub}</p>
          </div>
        </div>
      </div>

      <div className="card acc-toolbar">
        <div className="acc-periods">
          {['daily', 'weekly', 'monthly'].map((x) => (
            <button key={x} type="button" className={'acc-period-btn' + (period === x && !range.from ? ' on' : '')}
              onClick={() => { setRange({ from: '', to: '' }); setPeriod(x) }}>{s[x]}</button>
          ))}
        </div>
        <div className="acc-toolbar-acts">
          <button type="button" className="acc-tool-btn" onClick={() => setDateOpen(true)}>
            <Ico d={ICONS.calendar} w={14} />{s.filter_dates}
            {range.from && <span className="acc-tool-badge" dir="ltr">{range.from}→{range.to}</span>}
          </button>
          <button type="button" className="acc-tool-btn" onClick={() => setBankOpen(true)}>
            <Ico d={ICONS.filter} w={14} />{s.filter_banks}
            {bankActive > 0 && <span className="bfs-count-badge">{digits(bankActive, lang)}</span>}
          </button>
        </div>
      </div>

      <Alert>{err}</Alert>

      {!d ? <div className="grid place-items-center py-16"><Spinner /></div> : (
        <>
          <div className="acc-kpis">
            <div className="card acc-kpi acc-kpi--main">
              <div className="acc-kpi-top">
                <span className="acc-kpi-label">{s.revenue}</span>
                <span className="acc-kpi-ico" style={{ background: 'color-mix(in srgb, #1464BA 14%, transparent)', color: '#1464BA' }}>
                  <Ico d={ICONS.wallet} w={18} />
                </span>
              </div>
              <div className="acc-kpi-val">{toman(d.revenue, lang)}</div>
              {growthPct != null && (
                <div className={'acc-kpi-sub' + (growthPct >= 0 ? ' up' : ' down')}>
                  <Ico d={ICONS.trendUp} w={12} />{growthPct >= 0 ? '+' : ''}{digits(growthPct, lang)}٪ {s.growth}
                </div>
              )}
            </div>
            <div className="card acc-kpi">
              <div className="acc-kpi-top">
                <span className="acc-kpi-label">{s.tx_count}</span>
                <span className="acc-kpi-ico" style={{ background: 'color-mix(in srgb, #11AB53 14%, transparent)', color: '#11AB53' }}>
                  <Ico d={ICONS.receipt} w={18} />
                </span>
              </div>
              <div className="acc-kpi-val">{digits(d.transactions ?? 0, lang)}</div>
              <div className="acc-kpi-sub">{s.avg_tx}: {toman(avgTx, lang)}</div>
            </div>
            <div className="card acc-kpi">
              <div className="acc-kpi-top">
                <span className="acc-kpi-label">{s.period_range}</span>
                <span className="acc-kpi-ico" style={{ background: 'color-mix(in srgb, var(--c-secondary) 14%, transparent)', color: 'var(--c-secondary)' }}>
                  <Ico d={ICONS.calendar} w={18} />
                </span>
              </div>
              <div className="acc-kpi-val acc-kpi-val--sm" dir="ltr">{d.range?.from} — {d.range?.to}</div>
            </div>
          </div>

          <div className="card acc-chart">
            <div className="acc-chart-head">
              <span className="font-bold text-sm">{s.daily_trend}</span>
              {daily.length > 0 && (
                <span className="acc-peak-tag">
                  <Ico d={ICONS.trendUp} w={12} />{s.peak}: {daily[peakIdx].date} · {toman(daily[peakIdx].revenue, lang)}
                </span>
              )}
            </div>
            {daily.length === 0 ? (
              <div className="py-6 text-center text-sm text-muted">{s.none_found}</div>
            ) : (
              <div className="flex h-44 items-end gap-1">
                {daily.map((x, i) => (
                  <div key={i} title={`${x.date}: ${toman(x.revenue, lang)}`} className={'acc-bar' + (i === peakIdx ? ' acc-bar--peak' : '')}
                    style={{ height: `${Math.max((Number(x.revenue || 0) / max) * 100, 2)}%` }} />
                ))}
              </div>
            )}
          </div>

          <div className="acc-breakdown-grid">
            <Breakdown title={s.by_panel} icon={ICONS.panel} tone="#1464BA" rows={d.by_panel} keyName="panel" prefix="panel_" total={d.revenue} t={t} lang={lang} empty={s.none_found} ofTotal={s.of_total} />
            <Breakdown title={s.by_method} icon={ICONS.card} tone="#11AB53" rows={d.by_method} keyName="method" prefix="m_" total={d.revenue} t={t} lang={lang} empty={s.none_found} ofTotal={s.of_total} />
            <Breakdown title={s.by_source} icon={ICONS.hub} tone="#7C3AED" rows={d.by_source} keyName="order__source" prefix="src_" total={d.revenue} t={t} lang={lang} empty={s.none_found} ofTotal={s.of_total} />
            <Breakdown title={s.by_card} icon={ICONS.bank} tone="#D97706" rows={d.by_card} keyName="bank_card__card_number" prefix="card_" total={d.revenue} t={t} lang={lang} empty={s.none_found} ofTotal={s.of_total} />
          </div>

          <div className="card acc-recent">
            <div className="acc-recent-head">
              <span className="font-bold text-sm">{s.recent}</span>
              <Link className="acc-view-all" to="/transactions">{s.view_all} <Ico d={ICONS.arrow} w={12} /></Link>
            </div>
            {recent === null ? (
              <div className="grid place-items-center py-8"><Spinner /></div>
            ) : filteredRecent.length === 0 ? (
              <div className="py-6 text-center text-sm text-muted">{s.none_found}</div>
            ) : (
              <div className="acc-recent-list">
                {filteredRecent.map((r) => (
                  <div key={r.id} className="acc-recent-row">
                    <div className="min-w-0">
                      <div className="font-semibold text-sm truncate">{r.user}{r.plan_name ? ` · ${r.plan_name}` : ''}</div>
                      <div className="text-xs text-muted mt-0.5">
                        {jalali(r.created_at, true, lang)} · {r.card_bank || enumLabel(t, 'm_', r.method)}
                      </div>
                    </div>
                    <div className="acc-recent-amt">{toman(r.amount, lang)}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      <DateRangeModal open={dateOpen} onClose={() => setDateOpen(false)} onApply={setRange} />
      <BankFilterSheet open={bankOpen} onClose={() => setBankOpen(false)} value={bankFilter} onApply={setBankFilter} />
    </div>
  )
}

function Breakdown({ title, icon, tone, rows, keyName, prefix, total, t, lang, empty, ofTotal }) {
  const list = rows || []
  const max = list.reduce((m, x) => Math.max(m, Number(x.revenue || 0)), 0) || 1
  return (
    <div className="card acc-bd">
      <div className="acc-bd-head">
        <span className="acc-bd-ico" style={{ background: `color-mix(in srgb, ${tone} 14%, transparent)`, color: tone }}>
          <Ico d={icon} w={15} />
        </span>
        <span className="font-bold text-sm">{title}</span>
      </div>
      {list.length === 0 && <div className="text-sm text-muted py-3">{empty}</div>}
      {list.map((r, i) => {
        const rev = Number(r.revenue || 0)
        const pct = total ? Math.round((rev / total) * 1000) / 10 : 0
        return (
          <div key={i} className="acc-bd-row">
            <div className="acc-bd-row-top">
              <span className="text-sm truncate">{enumLabel(t, prefix, r[keyName])}</span>
              <span className="acc-bd-row-val">{digits(pct, lang)}٪</span>
            </div>
            <div className="acc-bd-bar"><i style={{ width: `${(rev / max) * 100}%`, background: tone }} /></div>
            <div className="acc-bd-row-sub">{toman(rev, lang)} ({digits(r.count, lang)}) · {ofTotal}</div>
          </div>
        )
      })}
    </div>
  )
}

const CSS = `
.acc-head { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-start; justify-content: space-between; }
.acc-head-main { display: flex; align-items: flex-start; gap: 12px; }
.acc-head-ico { width: 40px; height: 40px; border-radius: 12px; flex-shrink: 0; display: grid; place-items: center;
  background: color-mix(in srgb, #1464BA 12%, transparent); color: #1464BA; }

.acc-toolbar { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between; }
.acc-periods { display: inline-flex; gap: 4px; padding: 4px; border-radius: 12px; background: color-mix(in srgb, var(--c-text-muted) 10%, transparent); }
.acc-period-btn { padding: 6px 14px; border-radius: 9px; font-size: 13px; font-weight: 600; color: var(--c-text-muted); }
.acc-period-btn.on { background: var(--c-primary); color: #fff; }
.acc-toolbar-acts { display: flex; flex-wrap: wrap; gap: 8px; }
.acc-tool-btn { display: inline-flex; align-items: center; gap: 6px; padding: 7px 13px; border-radius: 10px; font-size: 12.5px; font-weight: 600;
  border: 1px solid var(--c-border); background: transparent; color: var(--c-text-muted); }
.acc-tool-btn:hover { color: var(--c-primary); border-color: var(--c-primary); }
.acc-tool-badge { font-family: 'JetBrains Mono', monospace; font-size: 10.5px; color: var(--c-primary); }

.acc-kpis { display: grid; grid-template-columns: 1fr; gap: 14px; }
@media (min-width: 720px) { .acc-kpis { grid-template-columns: repeat(3, 1fr); } }
.acc-kpi { display: flex; flex-direction: column; gap: 6px; }
.acc-kpi--main { border-color: color-mix(in srgb, #1464BA 30%, var(--c-border)); }
.acc-kpi-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.acc-kpi-label { font-size: 12px; font-weight: 600; color: var(--c-text-muted); }
.acc-kpi-ico { width: 36px; height: 36px; border-radius: 11px; display: grid; place-items: center; flex-shrink: 0; }
.acc-kpi-val { font-size: 22px; font-weight: 800; letter-spacing: -.01em; font-family: 'JetBrains Mono', ui-monospace, monospace; }
.acc-kpi-val--sm { font-size: 13px; font-weight: 700; }
.acc-kpi-sub { font-size: 11.5px; color: var(--c-text-muted); display: flex; align-items: center; gap: 4px; }
.acc-kpi-sub.up { color: var(--c-success); } .acc-kpi-sub.down { color: var(--c-danger); }

.acc-chart-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 14px; }
.acc-peak-tag { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 700; padding: 3px 10px; border-radius: 999px;
  background: color-mix(in srgb, var(--c-success) 14%, transparent); color: var(--c-success); white-space: nowrap; }
.acc-bar { flex: 1; border-radius: 4px 4px 0 0; background: color-mix(in srgb, var(--c-primary) 55%, transparent); min-height: 2px; transition: background .15s; }
.acc-bar:hover { background: var(--c-primary); }
.acc-bar--peak { background: var(--c-success); }

.acc-breakdown-grid { display: grid; grid-template-columns: 1fr; gap: 14px; }
@media (min-width: 720px) { .acc-breakdown-grid { grid-template-columns: 1fr 1fr; } }
.acc-bd-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.acc-bd-ico { width: 30px; height: 30px; border-radius: 9px; display: grid; place-items: center; flex-shrink: 0; }
.acc-bd-row { padding: 8px 0; border-top: 1px solid var(--c-border); }
.acc-bd-row:first-of-type { border-top: 0; }
.acc-bd-row-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.acc-bd-row-val { font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 700; color: var(--c-text-muted); flex-shrink: 0; }
.acc-bd-bar { height: 5px; border-radius: 999px; overflow: hidden; background: color-mix(in srgb, var(--c-text-muted) 16%, transparent); margin-top: 6px; }
.acc-bd-bar > i { display: block; height: 100%; border-radius: 999px; }
.acc-bd-row-sub { font-size: 11px; color: var(--c-text-muted); margin-top: 4px; }

.acc-recent-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
.acc-view-all { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; font-weight: 600; color: var(--c-primary); }
.acc-recent-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 0; border-top: 1px solid var(--c-border); }
.acc-recent-row:first-child { border-top: 0; }
.acc-recent-amt { font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 13px; white-space: nowrap; }

@media (max-width: 640px) {
  .acc-toolbar { flex-direction: column; align-items: stretch; }
  .acc-periods { justify-content: space-between; }
  .acc-toolbar-acts { flex-direction: column; }
  .acc-tool-btn { justify-content: center; }
}
`
