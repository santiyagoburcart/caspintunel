import { useEffect, useState } from 'react'
import { jalali } from '../lib/format'

// v1.54 «تاریخچه» — IDENTICAL in both SPAs (admin: our staff + group managers · user: the /agency/ portal). Every number
// comes from the server (apps/agency/history.py, built from the ledger + invoices — never reset by a settlement, payments
// or adjustments); this file only lays it out. Props: http (axios-like), base (endpoint), lang, fixedAdmin (one admin only).
export const HT = {
  fa: {
    title: 'تاریخچه', sub: 'از روی دفتر حساب ساخته می‌شود؛ تسویه، پرداخت یا اصلاحیه آن را صفر نمی‌کند.',
    d7: '7 روز اخیر', month: 'ماه جاری', prev: 'ماه قبل', custom: 'بازهٔ دلخواه', from: 'از', to: 'تا', show: 'نمایش',
    date_hint: 'مثلاً 1405/08/01', scope: 'برای', all: 'همهٔ ادمین‌ها', groups: 'گروه‌ها', admins: 'ادمین‌ها',
    gb: 'حجم فروخته‌شده', charged: 'فروش / شارژ', invoiced: 'فاکتورشده', paid: 'پرداخت‌شده', adjustments: 'اصلاحیه‌ها',
    opening: 'مانده ابتدای بازه', closing: 'مانده پایان بازه', new_users: 'کاربران جدید', no_users: '—',
    users_hint: 'شمارش کاربران جدید از نسخهٔ 1.54 شروع شده است؛ برای قبل از آن سابقه‌ای نیست.',
    per_admin: 'به تفکیک ادمین', monthly: '12 ماه اخیر', mon: 'ماه', admin: 'ادمین', archived: 'بایگانی',
    csv: 'CSV', xlsx: 'Excel', none: 'در این بازه گردشی نیست.', range: '{a} تا {b}', toman: 'تومان', err: 'دریافت تاریخچه ناموفق بود',
  },
  en: {
    title: 'History', sub: 'Built from the ledger — a settlement, payments or adjustments never reset it.',
    d7: 'Last 7 days', month: 'This month', prev: 'Last month', custom: 'Custom range', from: 'From', to: 'To', show: 'Show',
    date_hint: 'e.g. 1405/08/01', scope: 'For', all: 'All admins', groups: 'Groups', admins: 'Admins',
    gb: 'Volume sold', charged: 'Sales / charged', invoiced: 'Invoiced', paid: 'Paid', adjustments: 'Adjustments',
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

export default function AgencyHistory({ http, base, lang = 'fa', fixedAdmin = '' }) {
  const s = HT[lang] || HT.fa
  const [period, setPeriod] = useState('month')
  const [range, setRange] = useState({ from: '', to: '' })
  const [applied, setApplied] = useState({ from: '', to: '' })
  const [scope, setScope] = useState(fixedAdmin ? `a:${fixedAdmin}` : 'all')
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
  const tiles = t ? [
    ['gb', <bdi dir="ltr">{gbt(t.gb)}</bdi>], ['charged', money(t.charged)], ['invoiced', money(t.invoiced)],
    ['paid', money(t.paid)], ['adjustments', money(t.adjustments)], ['opening', money(t.opening)],
    ['closing', money(t.closing)], ['new_users', users(t.new_users)],
  ] : []
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
            {tiles.map(([k, v]) => <div key={k} className="ah-kpi" data-k={k}><dt>{s[k]}</dt><dd>{v}</dd></div>)}
          </dl>
          {t && (t.new_users === null || t.new_users === undefined) && <p className="ah-hint">{s.users_hint}</p>}
          {(d.admins || []).length > 0 && (
            <div className="ah-block">
              <h4>{s.per_admin}</h4>
              <table className="ah-table"><thead><tr><th>{s.admin}</th><th>{s.gb}</th><th>{s.charged}</th><th>{s.paid}</th><th>{s.adjustments}</th><th>{s.closing}</th></tr></thead>
                <tbody>{d.admins.map((r) => (
                  <tr key={r.username} data-testid="history-admin">
                    <td data-label={s.admin}><bdi>{r.username}</bdi>{r.archived && <em className="ah-arch">{s.archived}</em>}</td>
                    <td data-label={s.gb}><bdi dir="ltr">{gbt(r.gb)}</bdi></td><td data-label={s.charged}>{money(r.charged)}</td>
                    <td data-label={s.paid}>{money(r.paid)}</td><td data-label={s.adjustments}>{money(r.adjustments)}</td>
                    <td data-label={s.closing}>{money(r.closing)}</td>
                  </tr>))}</tbody></table>
            </div>
          )}
          <div className="ah-block">
            <h4>{s.monthly}</h4>
            <table className="ah-table"><thead><tr><th>{s.mon}</th><th>{s.gb}</th><th>{s.charged}</th><th>{s.invoiced}</th><th>{s.paid}</th><th>{s.adjustments}</th><th>{s.closing}</th><th>{s.new_users}</th></tr></thead>
              <tbody>{(d.monthly || []).map((m) => (
                <tr key={m.key} data-testid="history-month">
                  <td data-label={s.mon}><bdi dir="ltr">{m.key}</bdi></td><td data-label={s.gb}><bdi dir="ltr">{gbt(m.gb)}</bdi></td>
                  <td data-label={s.charged}>{money(m.charged)}</td><td data-label={s.invoiced}>{money(m.invoiced)}</td>
                  <td data-label={s.paid}>{money(m.paid)}</td><td data-label={s.adjustments}>{money(m.adjustments)}</td>
                  <td data-label={s.closing}>{money(m.closing)}</td><td data-label={s.new_users}>{users(m.new_users)}</td>
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
.ah-kpi { padding: 10px 12px; border-radius: 12px; border: 1px solid var(--c-border); background: var(--c-bg); min-width: 0; }
.ah-kpi dt { font-size: 11.5px; font-weight: 700; color: var(--c-text-muted); }
.ah-kpi dd { margin: 4px 0 0; font-size: 15px; font-weight: 800; overflow-wrap: anywhere; }
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
