import { useCallback, useEffect, useState } from 'react'
import { Link, NavLink, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { toman } from '../lib/format'
import { Spinner } from '../components/ui'
import { DateRangeModal, DRP_CSS } from '../components/DateRangePicker'
import { useToast } from '../components/Toast'

// Business overview + CRM accounting & analytics (backend: apps/crm/analytics.py).
// Read-only: every number comes from the server; this file only lays out and draws.
const T = {
  fa: {
    title: 'تحلیل کسب‌وکار', sub: 'درآمد، نگهداشت مشتری و عملکرد پشتیبانی — فقط خواندنی، از داده‌های موجود',
    t_overview: 'نمای کلی', t_fin: 'مالی مشتریان', t_ret: 'نگهداشت', t_tk: 'پشتیبانی',
    this_month: 'این ماه', last_month: 'ماه قبل', m3: '3 ماه', m6: '6 ماه', m12: '12 ماه', all: 'همه', custom: 'بازهٔ دلخواه',
    csv: 'CSV', xlsx: 'Excel', export: 'خروجی', toman: 'تومان', none: '—',
    rev_month: 'درآمد این ماه', vs_prev: 'نسبت به همین بازهٔ ماه قبل', active: 'مشتریان فعال', at_risk: 'در خطر', expired: 'منقضی', churned: 'ریزش',
    wb_rate: 'نرخ بازگشت (30 روز)', open_tk: 'تیکت‌های باز', first_resp: 'میانگین اولین پاسخ', open_cases: 'پیگیری‌های باز', min: 'دقیقه', h: 'ساعت',
    tr_rev: 'درآمد ماهانه', tr_new: 'مشتریان جدید در ماه', tr_active: 'مشتریان فعال در ماه', tr_tk: 'تیکت در هفته',
    revenue: 'درآمد', payments: 'پرداخت‌ها', payers: 'مشتریان پرداخت‌کننده', aov: 'میانگین ارزش سفارش (AOV)', arpu: 'درآمد به ازای مشتری (ARPU)',
    new_rev: 'درآمد مشتریان جدید', ret_rev: 'درآمد مشتریان قبلی', new_cust: 'مشتریان جدید', discount: 'هزینهٔ تخفیف', codes: 'کد استفاده‌شده', by_code: 'کدهای تخفیف (استفاده · تخفیف · درآمد)',
    avg_ltv: 'میانگین LTV (کل)', monthly: 'درآمد به تفکیک ماه', new_vs_ret: 'جدید / قبلی', by_plan: 'به تفکیک پلن', by_channel: 'به تفکیک کانال',
    by_card: 'به تفکیک کارت', ch: { site: 'سایت', bot: 'ربات', admin: 'پنل' }, count: 'تعداد',
    churn: 'نرخ ریزش ماهانه', renewal: 'نرخ تمدید ماهانه', cohort: 'کوهورت: درصد مشتریان فعال در ماه‌های بعد از اولین خرید', customers: 'مشتری',
    lifetime: 'میانگین عمر مشتری', days: 'روز', top: 'برترین مشتریان بر اساس LTV', month: 'ماه', due: 'سررسید', renewed: 'تمدید', lost: 'ریزش',
    staff: 'عملکرد پشتیبان‌ها', handled: 'تیکت رسیدگی‌شده', replies: 'پاسخ', resolved: 'حل‌شده', resolution: 'میانگین زمان حل', reopened: 'بازگشایی',
    topics: 'حجم تیکت به تفکیک موضوع', opened: 'باز شده', closed: 'بسته شده', defs: 'تعریف‌ها',
    defs_txt: 'درآمد = پرداخت‌های تأییدشده (مثل صفحهٔ حسابداری). ARPU = درآمد ÷ مشتریان پرداخت‌کننده. «فعال در ماه» = سفارش پرداخت‌شده‌ای که بازهٔ پلنش آن ماه را پوشش می‌دهد. ریزش = فعال در ماه قبل و نه در این ماه. تمدید = سفارشی که پایانش در این ماه بود و مشتری تا 14 روز بعد دوباره خرید کرد.',
    no_access: 'برای این بخش دسترسی «حسابداری» و «CRM» لازم است.',
  },
  en: {
    title: 'Business analytics', sub: 'Revenue, customer retention and support performance — read-only, from existing data',
    t_overview: 'Overview', t_fin: 'Customer finance', t_ret: 'Retention', t_tk: 'Support',
    this_month: 'This month', last_month: 'Last month', m3: '3 months', m6: '6 months', m12: '12 months', all: 'All', custom: 'Custom range',
    csv: 'CSV', xlsx: 'Excel', export: 'Export', toman: 'T', none: '—',
    rev_month: 'Revenue this month', vs_prev: 'vs the same part of last month', active: 'Active customers', at_risk: 'At risk', expired: 'Expired', churned: 'Churned',
    wb_rate: 'Win-back rate (30 days)', open_tk: 'Open tickets', first_resp: 'Avg first response', open_cases: 'Open follow-ups', min: 'min', h: 'h',
    tr_rev: 'Monthly revenue', tr_new: 'New customers per month', tr_active: 'Active customers per month', tr_tk: 'Tickets per week',
    revenue: 'Revenue', payments: 'Payments', payers: 'Paying customers', aov: 'Average order value (AOV)', arpu: 'Revenue per customer (ARPU)',
    new_rev: 'New-customer revenue', ret_rev: 'Returning revenue', new_cust: 'New customers', discount: 'Discount cost', codes: 'codes used', by_code: 'Discount codes (uses · discount · revenue)',
    avg_ltv: 'Average LTV (all time)', monthly: 'Revenue per month', new_vs_ret: 'new / returning', by_plan: 'By plan', by_channel: 'By channel',
    by_card: 'By bank card', ch: { site: 'Site', bot: 'Bot', admin: 'Panel' }, count: 'Count',
    churn: 'Monthly churn rate', renewal: 'Monthly renewal rate', cohort: 'Cohorts: % of customers active in the months after their first purchase', customers: 'customers',
    lifetime: 'Average customer lifetime', days: 'days', top: 'Top customers by LTV', month: 'Month', due: 'Due', renewed: 'Renewed', lost: 'Churned',
    staff: 'Staff performance', handled: 'Tickets handled', replies: 'Replies', resolved: 'Resolved', resolution: 'Avg resolution', reopened: 'Reopened',
    topics: 'Ticket volume per topic', opened: 'Opened', closed: 'Closed', defs: 'Definitions',
    defs_txt: 'Revenue = approved payments (as on the Accounting page). ARPU = revenue ÷ paying customers. "Active in a month" = a paid order whose plan period covers that month. Churn = active last month, not this month. Renewal = orders ending this month that the customer followed with another purchase within 14 days.',
    no_access: 'This section needs the Accounting and CRM permissions.',
  },
}
const useT = () => { const { lang } = useI18n(); return [T[lang] || T.fa, lang] }
const n = (v) => Number(v || 0).toLocaleString('en-US')

function useGet(url) {
  const [d, setD] = useState(null)
  const load = useCallback(() => { setD(null); return api.get(url).then((r) => setD(r.data)).catch((e) => setD({ __err: e?.response?.status || 1 })) }, [url])
  useEffect(() => { load() }, [load])
  return d
}

/** tiny dependency-free charts */
function Spark({ data, money }) {
  const vals = data.map((x) => Number(x.value) || 0)
  const max = Math.max(1, ...vals)
  const w = 100 / Math.max(1, vals.length)
  return (
    <svg className="an-spark" viewBox="0 0 100 32" preserveAspectRatio="none" role="img" aria-label={vals.join(', ')}>
      {vals.map((v, i) => <rect key={i} x={i * w + w * 0.15} y={32 - (v / max) * 30} width={w * 0.7} height={(v / max) * 30 || 0.6} rx="1">
        <title>{(data[i].month || data[i].week)}: {money ? n(v) : v}</title></rect>)}
    </svg>
  )
}
function Bar({ v, max, tone }) {
  return <span className="an-bar"><i data-tone={tone} style={{ width: `${max ? Math.max(1, Math.round((v / max) * 100)) : 0}%` }} /></span>
}
function Kpi({ label, value, sub, tone }) {
  return <div className="an-kpi" data-tone={tone}><span className="an-kpi-l">{label}</span><b dir="ltr">{value}</b>{sub && <span className="an-kpi-s">{sub}</span>}</div>
}

function Header() {
  const [s] = useT()
  const tabs = [['/analytics', s.t_overview, true], ['/analytics/finance', s.t_fin], ['/analytics/retention', s.t_ret], ['/analytics/support', s.t_tk]]
  return (
    <>
      <style>{CSS + DRP_CSS}</style>
      <div><h1 className="text-lg font-bold">{s.title}</h1><p className="text-sm text-muted mt-1">{s.sub}</p></div>
      <nav className="an-tabs">{tabs.map(([to, l, end]) => <NavLink key={to} to={to} end={!!end} className={({ isActive }) => 'an-tab' + (isActive ? ' on' : '')}>{l}</NavLink>)}</nav>
    </>
  )
}

function usePeriod() {
  const [p, setP] = useState(() => { try { return JSON.parse(sessionStorage.getItem('an_period') || 'null') || { preset: 'this_month' } } catch { return { preset: 'this_month' } } })
  useEffect(() => { try { sessionStorage.setItem('an_period', JSON.stringify(p)) } catch { /* private */ } }, [p])
  const qs = p.preset === 'custom' ? `from=${p.from}&to=${p.to}` : `preset=${p.preset}`
  return [p, setP, qs]
}

function PeriodBar({ p, setP, range, exportTo }) {
  const [s, lang] = useT()
  const [pick, setPick] = useState(false)
  const toast = useToast()
  const dl = async (fmt) => {
    try {
      const r = await api.get(`${exportTo}&export=${fmt}&lang=${lang}`, { responseType: 'blob' })
      const u = URL.createObjectURL(r.data)
      const a = document.createElement('a')
      a.href = u; a.download = `crm-${p.preset}.${fmt}`; a.click()
      setTimeout(() => URL.revokeObjectURL(u), 5000)
    } catch { toast.error('—') }
  }
  return (
    <div className="card an-period">
      <div className="an-seg">
        {['this_month', 'last_month', '3m', '6m', '12m', 'all'].map((k) => (
          <button key={k} type="button" className={p.preset === k ? 'on' : ''} onClick={() => setP({ preset: k })}>{s[k === '3m' ? 'm3' : k === '6m' ? 'm6' : k === '12m' ? 'm12' : k]}</button>
        ))}
        <button type="button" className={p.preset === 'custom' ? 'on' : ''} onClick={() => setPick(true)}>{s.custom}</button>
      </div>
      {range && <span className="an-range" dir="ltr">{range.from} — {range.to}</span>}
      {exportTo && <span className="an-exp">{s.export}: <button type="button" onClick={() => dl('csv')}>{s.csv}</button><button type="button" onClick={() => dl('xlsx')}>{s.xlsx}</button></span>}
      <DateRangeModal open={pick} onClose={() => setPick(false)} onApply={(r) => { if (r.from && r.to) setP({ preset: 'custom', from: r.from, to: r.to }); setPick(false) }} />
    </div>
  )
}

function Denied({ d }) {
  const [s] = useT()
  if (!d?.__err) return null
  return <div className="card text-muted">{d.__err === 403 ? s.no_access : '—'}</div>
}

// ================================ overview ==========================================
export function AnalyticsOverview() {
  const [s, lang] = useT()
  const d = useGet('/admin/crm/analytics/overview/')
  return (
    <div className="an space-y-4">
      <Header />
      {!d ? <div className="grid place-items-center py-12"><Spinner /></div> : d.__err ? <Denied d={d} /> : <>
        <div className="an-kpis">
          <Kpi label={s.rev_month} value={`${n(d.revenue_month)}`} sub={d.revenue_change == null ? s.toman : `${d.revenue_change > 0 ? '▲' : d.revenue_change < 0 ? '▼' : ''} ${d.revenue_change}% · ${s.vs_prev}`}
            tone={d.revenue_change == null ? 'primary' : d.revenue_change >= 0 ? 'success' : 'danger'} />
          <Kpi label={s.active} value={n(d.active_customers)} tone="success" />
          <Kpi label={s.at_risk} value={n(d.at_risk)} tone="warning" />
          <Kpi label={s.expired} value={n(d.expired)} sub={`${s.churned}: ${n(d.churned)}`} tone="danger" />
          <Kpi label={s.wb_rate} value={d.winback_rate == null ? s.none : `${d.winback_rate}%`} tone="primary" />
          <Kpi label={s.open_tk} value={n(d.open_tickets)} sub={`${s.open_cases}: ${n(d.open_cases)}`} tone="primary" />
          <Kpi label={s.first_resp} value={d.avg_first_response_min == null ? s.none : `${d.avg_first_response_min} ${s.min}`} tone="primary" />
        </div>
        <div className="an-grid2">
          {[['revenue', s.tr_rev, true], ['new_customers', s.tr_new], ['active', s.tr_active], ['tickets', s.tr_tk]].map(([k, l, money]) => (
            <section key={k} className="card an-trend">
              <div className="an-trend-h"><h4>{l}</h4><b dir="ltr">{money ? n(d.trends[k].at(-1)?.value) : d.trends[k].at(-1)?.value}</b></div>
              <Spark data={d.trends[k]} money={money} />
              <div className="an-trend-x" dir="ltr"><span>{d.trends[k][0]?.month || d.trends[k][0]?.week}</span><span>{d.trends[k].at(-1)?.month || d.trends[k].at(-1)?.week}</span></div>
            </section>
          ))}
        </div>
        <p className="an-note">{lang === 'en' ? 'Month' : 'ماه'}: <span dir="ltr">{d.month}</span> · <Link to="/accounting">{lang === 'en' ? 'Accounting' : 'حسابداری'} →</Link> · <Link to="/crm/reports">CRM →</Link></p>
      </>}
    </div>
  )
}

// ================================ finance =============================================
export function AnalyticsFinance() {
  const [s, lang] = useT()
  const [p, setP, qs] = usePeriod()
  const d = useGet(`/admin/crm/analytics/financial/?${qs}`)
  const maxM = d && !d.__err ? Math.max(1, ...d.monthly.map((m) => Number(m.revenue))) : 1
  return (
    <div className="an space-y-4">
      <Header />
      <PeriodBar p={p} setP={setP} range={d?.range} exportTo={`/admin/crm/analytics/financial/?${qs}`} />
      {!d ? <div className="grid place-items-center py-12"><Spinner /></div> : d.__err ? <Denied d={d} /> : <>
        <div className="an-kpis">
          <Kpi label={s.revenue} value={n(d.revenue)} sub={s.toman} tone="success" />
          <Kpi label={s.payments} value={n(d.payments)} sub={`${s.payers}: ${n(d.paying_customers)}`} tone="primary" />
          <Kpi label={s.aov} value={n(d.aov)} sub={s.toman} tone="primary" />
          <Kpi label={s.arpu} value={n(d.arpu)} sub={s.toman} tone="primary" />
          <Kpi label={s.new_rev} value={n(d.new_revenue)} sub={`${s.new_cust}: ${n(d.new_customers)}`} tone="success" />
          <Kpi label={s.ret_rev} value={n(d.returning_revenue)} sub={s.toman} tone="success" />
          <Kpi label={s.discount} value={n(d.discount_cost)} sub={`${n(d.codes_used)} ${s.codes}`} tone="warning" />
          <Kpi label={s.avg_ltv} value={n(d.avg_ltv)} sub={`${n(d.customers_with_ltv)} ${s.customers}`} tone="primary" />
        </div>
        {d.discount_codes?.length > 0 && (
          <section className="card space-y-2"><h4>{s.by_code}</h4>
            {d.discount_codes.map((r) => (
              <div key={r.id} className="an-row4"><span dir="ltr" className="an-code">{r.code}</span>
                <span className="an-sub">{n(r.uses)} {s.codes} · {n(r.customers)} {s.customers}</span>
                <b dir="ltr">−{n(r.discount)}</b><span className="an-sub" dir="ltr">{n(r.revenue)}</span></div>
            ))}
          </section>
        )}
        <section className="card space-y-2"><h4>{s.monthly} <span className="an-sub">({s.new_vs_ret})</span></h4>
          {d.monthly.map((m) => (
            <div key={m.month} className="an-row4"><span dir="ltr">{m.month}</span>
              <span className="an-stack"><i data-tone="success" style={{ width: `${(Number(m.new) / maxM) * 100}%` }} /><i data-tone="primary" style={{ width: `${(Number(m.returning) / maxM) * 100}%` }} /></span>
              <b dir="ltr">{n(m.revenue)}</b><span className="an-sub" dir="ltr">{n(m.new)} / {n(m.returning)}</span></div>
          ))}
        </section>
        <div className="an-grid3">
          {[['by_plan', (x) => (lang === 'en' ? x.name_en || x.name_fa : x.name_fa)], ['by_channel', (x) => s.ch[x.channel] || x.channel], ['by_card', (x) => `${x.bank || ''} ${x.card === '—' ? '—' : '•••• ' + x.card}`]].map(([k, label]) => {
            const max = Math.max(1, ...d[k].map((x) => Number(x.revenue)))
            return (
              <section key={k} className="card space-y-2"><h4>{s[k]}</h4>
                {d[k].length === 0 ? <p className="an-sub">—</p> : d[k].map((x, i) => (
                  <div key={i} className="an-row3"><span className="truncate">{label(x)}</span><Bar v={Number(x.revenue)} max={max} tone="primary" /><b dir="ltr">{n(x.revenue)}</b></div>
                ))}
              </section>
            )
          })}
        </div>
        <details className="card an-defs"><summary>{s.defs}</summary><p>{s.defs_txt}</p></details>
      </>}
    </div>
  )
}

// ================================ retention ===========================================
export function AnalyticsRetention() {
  const [s, lang] = useT()
  const [p, setP, qs] = usePeriod()
  const d = useGet(`/admin/crm/analytics/retention/?${qs}`)
  const cell = (v, i) => <td key={i} style={{ '--a': v / 100 }} className="an-cell">{v}%</td>
  return (
    <div className="an space-y-4">
      <Header />
      <PeriodBar p={p} setP={setP} range={d?.range} />
      {!d ? <div className="grid place-items-center py-12"><Spinner /></div> : d.__err ? <Denied d={d} /> : <>
        <div className="an-kpis">
          <Kpi label={s.lifetime} value={d.avg_lifetime_days == null ? s.none : n(d.avg_lifetime_days)} sub={s.days} tone="primary" />
          <Kpi label={s.customers} value={n(d.customers)} tone="primary" />
          <Kpi label={s.churn} value={d.churn.at(-1)?.rate == null ? s.none : `${d.churn.at(-1).rate}%`} sub={d.churn.at(-1)?.month} tone="danger" />
          <Kpi label={s.renewal} value={d.renewal.at(-1)?.rate == null ? s.none : `${d.renewal.at(-1).rate}%`} sub={d.renewal.at(-1)?.month} tone="success" />
        </div>
        <div className="an-grid2">
          <section className="card space-y-2"><h4>{s.churn}</h4>
            {d.churn.map((c) => <div key={c.month} className="an-row3"><span dir="ltr">{c.month}</span><Bar v={c.rate || 0} max={100} tone="danger" /><b dir="ltr">{c.rate == null ? '—' : `${c.rate}%`}</b></div>)}</section>
          <section className="card space-y-2"><h4>{s.renewal}</h4>
            {d.renewal.map((c) => <div key={c.month} className="an-row3"><span dir="ltr">{c.month}</span><Bar v={c.rate || 0} max={100} tone="success" /><b dir="ltr">{c.rate == null ? '—' : `${c.rate}%`} <span className="an-sub">({c.renewed}/{c.due})</span></b></div>)}</section>
        </div>
        <section className="card space-y-2"><h4>{s.cohort}</h4>
          <div className="an-scroll"><table className="an-cohort" dir="ltr">
            <thead><tr><th>{s.month}</th><th>#</th>{Array.from({ length: 12 }, (_, i) => <th key={i}>+{i}</th>)}</tr></thead>
            <tbody>{d.cohorts.map((c) => <tr key={c.cohort}><th>{c.cohort}</th><td>{c.customers}</td>{c.pct.map(cell)}</tr>)}</tbody>
          </table></div>
        </section>
        <section className="card space-y-2"><h4>{s.top}</h4>
          {d.top_ltv.map((t, i) => (
            <Link key={t.id} to={`/crm/customers/${t.id}`} className="an-row4 an-link"><span>{i + 1}</span><span className="truncate">{t.name || t.username} <span className="an-sub" dir="ltr">{t.username}</span></span>
              <b dir="ltr">{toman(t.ltv, lang)}</b><span className="an-sub">{t.payments} {s.payments}</span></Link>
          ))}
        </section>
        <details className="card an-defs"><summary>{s.defs}</summary><p>{s.defs_txt}</p></details>
      </>}
    </div>
  )
}

// ================================ support ==============================================
export function AnalyticsSupport() {
  const [s, lang] = useT()
  const [p, setP, qs] = usePeriod()
  const d = useGet(`/admin/crm/analytics/tickets/?${qs}`)
  const { can } = useAuth()
  return (
    <div className="an space-y-4">
      <Header />
      <PeriodBar p={p} setP={setP} range={d?.range} />
      {!d ? <div className="grid place-items-center py-12"><Spinner /></div> : d.__err ? <Denied d={d} /> : <>
        <div className="an-kpis">
          <Kpi label={s.opened} value={n(d.opened)} tone="primary" />
          <Kpi label={s.closed} value={n(d.closed)} tone="success" />
          <Kpi label={s.open_tk} value={n(d.open_now)} tone="warning" />
          <Kpi label={s.first_resp} value={d.avg_first_response_min == null ? s.none : `${d.avg_first_response_min} ${s.min}`} tone="primary" />
          <Kpi label={s.reopened} value={n(d.reopened)} tone="danger" />
        </div>
        <section className="card space-y-2"><h4>{s.staff}</h4>
          <div className="an-scroll"><table className="an-table">
            <thead><tr><th /><th>{s.handled}</th><th>{s.replies}</th><th>{s.first_resp}</th><th>{s.resolved}</th><th>{s.resolution}</th><th>{s.reopened}</th></tr></thead>
            <tbody>{d.staff.map((x) => (
              <tr key={x.id}><th>{x.name}</th><td>{x.handled}</td><td>{x.replies}</td><td>{x.first_response_min == null ? '—' : `${x.first_response_min} ${s.min}`}</td>
                <td>{x.resolved}</td><td>{x.resolution_h == null ? '—' : `${x.resolution_h} ${s.h}`}</td><td>{x.reopened}</td></tr>
            ))}</tbody>
          </table></div>
        </section>
        <section className="card space-y-2"><h4>{s.topics}</h4>
          {d.topics.map((t) => {
            const max = Math.max(1, ...d.topics.map((x) => x.opened))
            return <div key={t.id} className="an-row4"><span className="truncate">{lang === 'en' ? t.name_en : t.name_fa}</span><Bar v={t.opened} max={max} tone="primary" />
              <b dir="ltr">{t.opened} / {t.closed}</b><span className="an-sub">{t.first_response_min == null ? '' : `${t.first_response_min} ${s.min}`}</span></div>
          })}
        </section>
        {can('tickets.view') && <p className="an-note"><Link to="/tickets">{lang === 'en' ? 'Ticket inbox' : 'صندوق تیکت‌ها'} →</Link></p>}
      </>}
    </div>
  )
}

export default function Analytics() {
  const { tab } = useParams()
  if (tab === 'finance') return <AnalyticsFinance />
  if (tab === 'retention') return <AnalyticsRetention />
  if (tab === 'support') return <AnalyticsSupport />
  return <AnalyticsOverview />
}

const CSS = `
.an-tabs { display: flex; gap: 6px; overflow-x: auto; }
.an-tab { white-space: nowrap; padding: 7px 14px; border-radius: 999px; font-size: 13px; font-weight: 700; color: var(--c-text); border: 1px solid var(--c-border); text-decoration: none; }
.an-tab.on { background: color-mix(in srgb, var(--c-primary) 85%, #000); border-color: transparent; color: #fff; }
.an-period { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.an-seg { display: flex; flex-wrap: wrap; gap: 4px; }
.an-seg button { padding: 6px 12px; border-radius: 999px; font-size: 12.5px; font-weight: 700; border: 1px solid var(--c-border); background: none; color: var(--c-text-muted); cursor: pointer; }
.an-seg button.on { background: var(--c-primary); border-color: var(--c-primary); color: #fff; }
.an-range { font-size: 12.5px; color: var(--c-text-muted); font-family: 'JetBrains Mono', monospace; }
.an-exp { margin-inline-start: auto; display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--c-text-muted); }
.an-exp button { padding: 5px 11px; border-radius: 9px; border: 1px solid var(--c-border); background: none; color: var(--c-text); font-weight: 700; cursor: pointer; }
.an-kpis { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 170px), 1fr)); }
.an-kpi { display: flex; flex-direction: column; gap: 3px; padding: 13px 14px; border-radius: 14px; border: 1px solid var(--c-border); background: var(--c-surface);
  border-inline-start: 3px solid var(--tone, var(--c-primary)); }
.an-kpi[data-tone="success"] { --tone: var(--c-success); } .an-kpi[data-tone="warning"] { --tone: var(--c-warning); } .an-kpi[data-tone="danger"] { --tone: var(--c-danger); }
.an-kpi-l { font-size: 12px; color: var(--c-text-muted); }
.an-kpi b { font-size: 21px; font-family: 'JetBrains Mono', monospace; font-weight: 800; }
.an-kpi-s { font-size: 11.5px; color: var(--c-text-muted); }
.an-grid2 { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 360px), 1fr)); align-items: start; }
.an-grid3 { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr)); align-items: start; }
.an h4 { margin: 0; font-size: 13px; font-weight: 800; }
.an-sub { font-size: 11.5px; color: var(--c-text-muted); font-weight: 500; }
.an-trend-h { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
.an-trend-h b { font-family: 'JetBrains Mono', monospace; font-size: 16px; }
.an-spark { width: 100%; height: 64px; margin-top: 8px; fill: color-mix(in srgb, var(--c-primary) 70%, transparent); }
.an-spark rect:last-child { fill: var(--c-primary); }
.an-trend-x { display: flex; justify-content: space-between; font-size: 10.5px; color: var(--c-text-muted); font-family: 'JetBrains Mono', monospace; }
.an-bar { height: 8px; border-radius: 999px; background: color-mix(in srgb, var(--c-text-muted) 14%, transparent); overflow: hidden; display: block; }
.an-bar i, .an-stack i { display: block; height: 100%; border-radius: 999px; background: var(--c-primary); }
.an-bar i[data-tone="success"], .an-stack i[data-tone="success"] { background: var(--c-success); }
.an-bar i[data-tone="danger"] { background: var(--c-danger); }
.an-stack { display: flex; height: 10px; border-radius: 999px; overflow: hidden; background: color-mix(in srgb, var(--c-text-muted) 14%, transparent); }
.an-stack i { border-radius: 0; }
.an-row3 { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, 2fr) auto; gap: 10px; align-items: center; font-size: 12.5px; }
.an-row4 { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 2fr) auto auto; gap: 10px; align-items: center; font-size: 12.5px; }
.an-link { color: var(--c-text); text-decoration: none; padding: 6px 8px; border-radius: 10px; }
.an-link:hover { background: color-mix(in srgb, var(--c-primary) 6%, transparent); }
.an-scroll { overflow-x: auto; }
.an-cohort, .an-table { border-collapse: collapse; font-size: 12px; width: 100%; }
.an-cohort th, .an-cohort td, .an-table th, .an-table td { padding: 6px 8px; text-align: center; border-bottom: 1px solid var(--c-border); white-space: nowrap; }
.an-table th:first-child { text-align: start; }
.an-cell { background: color-mix(in srgb, var(--c-success) calc(var(--a) * 70%), transparent); font-family: 'JetBrains Mono', monospace; }
.an-defs summary { cursor: pointer; font-weight: 700; font-size: 13px; }
.an-defs p { margin: 8px 0 0; font-size: 12.5px; line-height: 1.8; color: var(--c-text-muted); }
.an-note { font-size: 12.5px; color: var(--c-text-muted); }
@media (max-width: 767px) { .an-row4 { grid-template-columns: minmax(0, 1fr) auto; } .an-row4 > :nth-child(2) { grid-column: 1 / -1; order: 3; } .an-exp { margin-inline-start: 0; } }
`
