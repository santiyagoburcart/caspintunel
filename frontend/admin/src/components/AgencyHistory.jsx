import { useEffect, useState } from 'react'
import { jalali } from '../lib/format'
import { moneyTone } from '../lib/agencyTone'

// v1.54 «تاریخچه» — IDENTICAL in both SPAs (admin: our staff + group managers · user: the /agency/ portal). Every number
// comes from the server (apps/agency/history.py, built from the ledger + invoices — never reset by a settlement, payments
// or adjustments); this file only lays it out. Props: http (axios-like), base (endpoint), lang, fixedAdmin (one admin only).
// v1.57: «فروش» = charges + adjustments is THE sales figure (no gross charges anywhere); «اصلاحیه‌ها» only as an information line.
// The per-admin table filters (only debtors, sort by debt, page) and the period / scope live in the URL (h_* params).
export const HT = {
  fa: {
    title: 'تاریخچه', sub: 'از روی دفتر حساب ساخته می‌شود و صفر نمی‌شود. فروش = شارژها منهای «کاهش بدهی» به‌اضافهٔ «افزایش بدهی» (در همان بازه‌ای که ثبت شده).',
    d7: '7 روز اخیر', month: 'ماه جاری', prev: 'ماه قبل', custom: 'بازهٔ دلخواه', from: 'از', to: 'تا', show: 'نمایش',
    date_hint: 'مثلاً 1405/08/01', scope: 'برای', all: 'همهٔ ادمین‌ها', groups: 'گروه‌ها', admins: 'ادمین‌ها',
    gb: 'حجم فروخته‌شده', sales: 'فروش', invoiced: 'فاکتورشده', paid: 'پرداخت‌شده', adjustments: 'اصلاحیه‌ها',
    adj_info: 'فقط برای اطلاع — در «فروش» حساب شده است', adj_n: '{n} مورد', adj_down: 'کاهش بدهی', adj_up: 'افزایش بدهی',
    debtors: 'فقط بدهکارها', sort_debt: 'مرتب به بدهی', page: 'صفحهٔ {p} از {n}', prev_p: 'قبلی', next_p: 'بعدی', no_rows: 'ادمینی با این فیلتر نیست.',
    opening: 'مانده ابتدای بازه', closing: 'مانده پایان بازه', new_users: 'کاربران جدید', no_users: '—',
    users_hint: 'شمارش کاربران جدید از نسخهٔ 1.54 شروع شده است؛ برای قبل از آن سابقه‌ای نیست.',
    per_admin: 'به تفکیک ادمین', monthly: '12 ماه اخیر', mon: 'ماه', admin: 'ادمین', archived: 'بایگانی',
    csv: 'CSV', xlsx: 'Excel', none: 'در این بازه گردشی نیست.', range: '{a} تا {b}', toman: 'تومان', err: 'دریافت تاریخچه ناموفق بود',
  },
  en: {
    title: 'History', sub: 'Built from the ledger and never reset. Sales = charges minus debt decreases plus debt increases (in the period they are recorded).',
    d7: 'Last 7 days', month: 'This month', prev: 'Last month', custom: 'Custom range', from: 'From', to: 'To', show: 'Show',
    date_hint: 'e.g. 1405/08/01', scope: 'For', all: 'All admins', groups: 'Groups', admins: 'Admins',
    gb: 'Volume sold', sales: 'Sales', invoiced: 'Invoiced', paid: 'Paid', adjustments: 'Adjustments',
    adj_info: 'information only — already inside «Sales»', adj_n: '{n} entries', adj_down: 'Debt decreases', adj_up: 'Debt increases',
    debtors: 'Only debtors', sort_debt: 'Sort by debt', page: 'Page {p} of {n}', prev_p: 'Previous', next_p: 'Next', no_rows: 'No admin matches this filter.',
    opening: 'Opening balance', closing: 'Closing balance', new_users: 'New users', no_users: '—',
    users_hint: 'New users are counted from version 1.54 on; there is no earlier record.',
    per_admin: 'Per admin', monthly: 'Last 12 months', mon: 'Month', admin: 'Admin', archived: 'archived',
    csv: 'CSV', xlsx: 'Excel', none: 'Nothing in this period.', range: '{a} to {b}', toman: 'T', err: 'Failed to load the history',
  },
}
const PERIODS = ['d7', 'month', 'prev', 'custom']
const num = (v) => Number(v || 0)
const gbt = (v) => `${num(v).toLocaleString('en-US', { maximumFractionDigits: 2 })} GB`
const latin = (v) => String(v ?? '').replace(/[۰-۹]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d))
const PAGE = 20
// v1.57: the filters live in the URL (router-agnostic: both SPAs) — a reload or a shared link shows the same view
const qget = (k, d = '') => { try { return new URLSearchParams(window.location.search).get(k) ?? d } catch { return d } }
const qset = (o) => {
  try {
    const u = new URL(window.location.href)
    Object.entries(o).forEach(([k, v]) => (v === '' || v === null || v === undefined || v === false ? u.searchParams.delete(k) : u.searchParams.set(k, String(v))))
    window.history.replaceState(window.history.state, '', u.pathname + (u.search || '') + u.hash)
  } catch { /* no URL support: filters still work for this view */ }
}

export default function AgencyHistory({ http, base, lang = 'fa', fixedAdmin = '' }) {
  const s = HT[lang] || HT.fa
  const [period, setPeriod] = useState(() => (PERIODS.includes(qget('h_period')) ? qget('h_period') : 'month'))
  const [range, setRange] = useState(() => ({ from: qget('h_from'), to: qget('h_to') }))
  const [applied, setApplied] = useState(() => ({ from: qget('h_from'), to: qget('h_to') }))
  const [scope, setScope] = useState(() => (fixedAdmin ? `a:${fixedAdmin}` : qget('h_scope', 'all') || 'all'))
  const [debtors, setDebtors] = useState(() => qget('h_debt') === '1')
  const [sortDebt, setSortDebt] = useState(() => qget('h_sort') === 'debt')
  const [page, setPage] = useState(() => Math.max(1, Number(qget('h_page', '1')) || 1))
  useEffect(() => {
    qset({ h_period: period === 'month' ? '' : period, h_from: period === 'custom' ? applied.from : '', h_to: period === 'custom' ? applied.to : '',
      h_scope: fixedAdmin || scope === 'all' ? '' : scope, h_debt: debtors ? '1' : '', h_sort: sortDebt ? 'debt' : '', h_page: page > 1 ? page : '' })
  }, [period, applied, scope, debtors, sortDebt, page])
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')

  const params = () => {
    const p = { period, lang }
    if (period === 'custom') Object.assign(p, applied)
    if (scope.startsWith('g:')) Object.assign(p, { scope: 'group', group: scope.slice(2) })
    else if (scope.startsWith('a:')) Object.assign(p, { scope: 'admin', admin: scope.slice(2) })
    return p
  }
  useEffect(() => {
    if (period === 'custom' && !(applied.from && applied.to)) return
    let stop = false
    setErr('')
    http.get(base, { params: params() }).then((r) => { if (!stop) setD(r.data) })
      .catch((e) => { if (!stop) setErr(e?.response?.data?.detail_fa && lang === 'fa' ? e.response.data.detail_fa : e?.response?.data?.detail || s.err) })
    return () => { stop = true }
  }, [period, applied, scope, base])

  const download = async (fmt) => {
    try {
      const r = await http.get(base, { params: { ...params(), export: fmt }, responseType: 'blob' })
      const url = URL.createObjectURL(r.data)
      const a = document.createElement('a')
      a.href = url; a.download = `history.${fmt}`; document.body.appendChild(a); a.click(); a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 2000)
    } catch { setErr(s.err) }
  }

  const t = d?.totals
  // the signed number isolated (LRI … PDI): in Persian a leading minus would otherwise land on the far side
  const money = (v) => <span>{'\u2066' + (num(v) < 0 ? '-' : '') + Math.abs(num(v)).toLocaleString('en-US') + '\u2069 ' + (lang === 'en' ? 'T' : 'تومان')}</span>
  const users = (v) => (v === null || v === undefined ? s.no_users : num(v).toLocaleString('en-US'))
  const sales = (r) => r.sales ?? r.net_sales          // v1.57 key (older servers: net_sales — the same number)
  const tiles = t ? [
    ['gb', <bdi dir="ltr">{gbt(t.gb)}</bdi>, 'info'], ['sales', money(sales(t)), 'info'], ['invoiced', money(t.invoiced), 'info'],
    ['paid', money(t.paid), 'success'], ['opening', money(t.opening), moneyTone(t.opening)],
    ['closing', money(t.closing), moneyTone(t.closing)], ['new_users', users(t.new_users), 'info'],
  ] : []
  const absT = (v) => <span>{'\u2066' + Math.abs(num(v)).toLocaleString('en-US') + '\u2069 ' + (lang === 'en' ? 'T' : 'تومان')}</span>
  let rows = [...(d?.admins || [])]
  if (debtors) rows = rows.filter((r) => num(r.closing) > 0)
  if (sortDebt) rows.sort((a, b) => num(b.closing) - num(a.closing))
  const pages = Math.max(1, Math.ceil(rows.length / PAGE))
  const pg = Math.min(page, pages)
  const shown = rows.slice((pg - 1) * PAGE, pg * PAGE)
  return (
    <section className="ah" data-testid="agency-history">
      <style>{CSS}</style>
      <div className="ah-head">
        <div><h3 className="ah-title">{s.title}</h3><p className="ah-sub">{s.sub}</p></div>
        <div className="ah-exp">
          <button type="button" className="ah-btn" onClick={() => download('csv')} data-testid="history-csv">{s.csv}</button>
          <button type="button" className="ah-btn" onClick={() => download('xlsx')}>{s.xlsx}</button>
        </div>
      </div>
      {!fixedAdmin && d && ((d.groups || []).length > 0 || (d.admins_list || []).length > 1) && (
        <label className="ah-scope"><span>{s.scope}</span>
          <select className="input" value={scope} onChange={(e) => setScope(e.target.value)} data-testid="history-scope">
            <option value="all">{s.all}</option>
            {(d.groups || []).length > 0 && <optgroup label={s.groups}>{d.groups.map((g) => <option key={g.id} value={`g:${g.id}`}>{g.name}</option>)}</optgroup>}
            {(d.admins_list || []).length > 1 && <optgroup label={s.admins}>{d.admins_list.map((u) => <option key={u} value={`a:${u}`}>{u}</option>)}</optgroup>}
          </select>
        </label>
      )}
      <div className="ah-chips" role="radiogroup" aria-label={s.title}>
        {PERIODS.map((p) => (
          <button key={p} type="button" role="radio" aria-checked={period === p} className={'ah-chip' + (period === p ? ' on' : '')}
            onClick={() => setPeriod(p)} data-testid={`history-period-${p}`}>{s[p]}</button>
        ))}
      </div>
      {period === 'custom' && (
        <form className="ah-range" onSubmit={(e) => { e.preventDefault(); setApplied({ from: latin(range.from).trim(), to: latin(range.to).trim() }) }}>
          <label><span>{s.from}</span><input className="input" dir="ltr" inputMode="numeric" placeholder={s.date_hint} value={range.from}
            onChange={(e) => setRange({ ...range, from: e.target.value })} data-testid="history-from" /></label>
          <label><span>{s.to}</span><input className="input" dir="ltr" inputMode="numeric" placeholder={s.date_hint} value={range.to}
            onChange={(e) => setRange({ ...range, to: e.target.value })} data-testid="history-to" /></label>
          <button className="ah-btn ah-btn--p" disabled={!range.from || !range.to}>{s.show}</button>
        </form>
      )}
      {err && <p className="ah-err" role="alert">{err}</p>}
      {d && (
        <>
          <p className="ah-range-txt">{s.range.replace('{a}', jalali(d.from, false, lang)).replace('{b}', jalali(d.to, false, lang))}</p>
          <dl className="ah-kpis" data-testid="history-kpis">
            {tiles.map(([k, v, tone]) => <div key={k} className="ah-kpi tn-tile" data-k={k} data-tn={tone}><dt>{s[k]}</dt><dd>{v}</dd></div>)}
          </dl>
          {t && (
            <p className="tn-info" data-testid="history-adjustments">
              <b>{s.adjustments}</b><span>{s.adj_n.replace('{n}', num(t.adjust_count).toLocaleString('en-US'))}</span>
              {num(t.adjust_down) > 0 && <span>{s.adj_down}: {absT(t.adjust_down)}</span>}
              {num(t.adjust_up) > 0 && <span>{s.adj_up}: {absT(t.adjust_up)}</span>}
              <span>· {s.adj_info}</span>
            </p>
          )}
          {t && (t.new_users === null || t.new_users === undefined) && <p className="ah-hint">{s.users_hint}</p>}
          {(d.admins || []).length > 0 && (
            <div className="ah-block">
              <div className="ah-bh">
                <h4>{s.per_admin}</h4>
                <label className="ah-tg"><input type="checkbox" checked={debtors} onChange={(e) => { setDebtors(e.target.checked); setPage(1) }} data-testid="history-debtors" />{s.debtors}</label>
                <label className="ah-tg"><input type="checkbox" checked={sortDebt} onChange={(e) => { setSortDebt(e.target.checked); setPage(1) }} data-testid="history-sort-debt" />{s.sort_debt}</label>
              </div>
              {shown.length === 0 ? <p className="ah-hint">{s.no_rows}</p> : (
                <table className="ah-table"><thead><tr><th>{s.admin}</th><th>{s.gb}</th><th>{s.sales}</th><th>{s.paid}</th><th>{s.closing}</th></tr></thead>
                  <tbody>{shown.map((r) => (
                    <tr key={r.username} data-testid="history-admin">
                      <td data-label={s.admin}><bdi>{r.username}</bdi>{r.archived && <em className="ah-arch">{s.archived}</em>}</td>
                      <td data-label={s.gb}><bdi dir="ltr">{gbt(r.gb)}</bdi></td><td data-label={s.sales}>{money(sales(r))}</td>
                      <td data-label={s.paid}><span className="tn-money" data-tone={num(r.paid) > 0 ? 'success' : 'muted'}>{money(r.paid)}</span></td>
                      <td data-label={s.closing}><span className="tn-money" data-tone={moneyTone(r.closing)}>{money(r.closing)}</span></td>
                    </tr>))}</tbody></table>
              )}
              {pages > 1 && (
                <div className="ah-pager">
                  <button type="button" className="ah-btn" disabled={pg <= 1} onClick={() => setPage(pg - 1)}>{s.prev_p}</button>
                  <span>{s.page.replace('{p}', pg).replace('{n}', pages)}</span>
                  <button type="button" className="ah-btn" disabled={pg >= pages} onClick={() => setPage(pg + 1)} data-testid="history-next">{s.next_p}</button>
                </div>
              )}
            </div>
          )}
          <div className="ah-block">
            <h4>{s.monthly}</h4>
            <table className="ah-table"><thead><tr><th>{s.mon}</th><th>{s.gb}</th><th>{s.sales}</th><th>{s.invoiced}</th><th>{s.paid}</th><th>{s.closing}</th><th>{s.new_users}</th></tr></thead>
              <tbody>{(d.monthly || []).map((m) => (
                <tr key={m.key} data-testid="history-month">
                  <td data-label={s.mon}><bdi dir="ltr">{m.key}</bdi></td><td data-label={s.gb}><bdi dir="ltr">{gbt(m.gb)}</bdi></td>
                  <td data-label={s.sales}>{money(sales(m))}</td><td data-label={s.invoiced}>{money(m.invoiced)}</td>
                  <td data-label={s.paid}><span className="tn-money" data-tone={num(m.paid) > 0 ? 'success' : 'muted'}>{money(m.paid)}</span></td>
                  <td data-label={s.closing}><span className="tn-money" data-tone={moneyTone(m.closing)}>{money(m.closing)}</span></td><td data-label={s.new_users}>{users(m.new_users)}</td>
                </tr>))}</tbody></table>
          </div>
        </>
      )}
    </section>
  )
}

const CSS = `
.ah { display: flex; flex-direction: column; gap: 10px; min-width: 0; padding: 14px; border-radius: 16px; border: 1px solid var(--c-border);
  background: var(--c-bg); color: var(--c-text); }
.ah-head { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 8px; }
.ah-title { font-size: 15px; font-weight: 800; margin: 0; }
.ah-sub, .ah-hint, .ah-range-txt { font-size: 12.5px; line-height: 1.8; color: var(--c-text-muted); margin: 0; }
.ah-exp { display: flex; gap: 6px; }
.ah-btn { min-height: 40px; padding: 0 14px; border-radius: 10px; border: 1px solid var(--c-border); background: var(--c-bg);
  color: var(--c-text); font-size: 13px; font-weight: 700; cursor: pointer; }
.ah-btn--p { background: var(--c-primary); border-color: var(--c-primary); color: #fff; }
.ah-btn:disabled { opacity: .6; cursor: default; }
.ah-scope { display: flex; flex-direction: column; gap: 4px; font-size: 12px; font-weight: 700; max-width: 360px; }
.ah-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.ah-chip { min-height: 44px; padding: 0 14px; border-radius: 999px; border: 1px solid var(--c-border); background: transparent;
  color: var(--c-text); font-size: 13px; font-weight: 700; cursor: pointer; }
.ah-chip.on { background: var(--c-primary); border-color: var(--c-primary); color: #fff; }
.ah-range { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 160px), 1fr)); gap: 8px; align-items: end; }
.ah-range label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; font-weight: 700; min-width: 0; }
.ah-err { font-size: 13px; color: var(--c-danger-fg, #b91c1c); margin: 0; }
.ah-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 150px), 1fr)); gap: 8px; margin: 0; }
.ah-kpi { min-width: 0; }
.ah-bh { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 14px; }
.ah-tg { display: inline-flex; align-items: center; gap: 6px; min-height: 40px; font-size: 12.5px; font-weight: 700; cursor: pointer; }
.ah-tg input { width: 17px; height: 17px; }
.ah-pager { display: flex; align-items: center; justify-content: center; gap: 10px; margin-top: 8px; font-size: 12.5px; }
.ah-block h4 { font-size: 13.5px; font-weight: 800; margin: 6px 0; }
.ah-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.ah-table th { text-align: start; font-weight: 700; color: var(--c-text-muted); padding: 6px 8px; border-bottom: 1px solid var(--c-border); white-space: nowrap; }
.ah-table td { padding: 7px 8px; border-bottom: 1px solid var(--c-border); white-space: nowrap; }
.ah-arch { font-style: normal; font-size: 11px; font-weight: 700; margin-inline-start: 6px; padding: 1px 8px; border-radius: 999px;
  color: var(--c-text-muted); background: color-mix(in srgb, var(--c-text-muted) 14%, transparent); }
@media (max-width: 767px) {
  .ah-table thead { display: none; }
  .ah-table, .ah-table tbody, .ah-table tr, .ah-table td { display: block; width: 100%; }
  .ah-table tr { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 6px 12px; border: 1px solid var(--c-border);
    border-radius: 12px; padding: 8px 10px; margin-bottom: 8px; background: var(--c-bg); }
  .ah-table td { display: flex; flex-direction: column; gap: 1px; border: 0; padding: 0; white-space: normal; min-width: 0; overflow-wrap: anywhere; }
  .ah-table td:first-child { grid-column: 1 / -1; font-weight: 800; }
  .ah-table td::before { content: attr(data-label); color: var(--c-text-muted); font-weight: 700; font-size: 11px; }
  .ah-range .input, .ah-scope .input { font-size: 16px; min-height: 44px; }
}
@media (min-width: 768px) { .ah-block { overflow-x: auto; } }
`
