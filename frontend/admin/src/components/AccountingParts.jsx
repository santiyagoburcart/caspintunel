import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { toman, jalali } from '../lib/format'
import { moneyTone } from '../lib/agencyTone'

// v1.58 Agency → «حسابداری» building blocks, shared by our staff's page (pages/AgencyLedger.jsx → AgencyAccounting) and the
// group manager's (pages/GroupManager.jsx → Accounting): period chips, the summary strip, sortable headers, the side drawer
// and the pager. Numbers always come from the server (apps/agency/accounting.py · managers.admin_summaries).
export const AT = {
  fa: {
    month: 'ماه جاری', prev: 'ماه قبل', d7: '7 روز اخیر', custom: 'بازهٔ دلخواه', from: 'از', to: 'تا', apply: 'نمایش', date_ph: 'مثلاً 1405/08/01',
    sales: 'فروش', paid: 'پرداخت‌شده', debt: 'جمع بدهی', debtors: 'تعداد بدهکارها', credit: 'بستانکاری {v}', range: '{a} تا {b}',
    adj: 'اصلاحیه‌ها', adj_n: '{n} مورد', adj_d: 'کاهش بدهی {v}', adj_u: 'افزایش بدهی {v}', adj_note: 'فقط اطلاع — در «فروش» حساب شده',
    t_debtors: 'بدهکارها', t_all: 'همه نماینده‌ها', t_all_gm: 'همهٔ ادمین‌ها', t_payments: 'واریزهای نمایندگان', t_history: 'تاریخچه ۱۲ ماهه', t_statement: 'صورت‌حساب گروه',
    c_admin: 'ادمین', c_group: 'گروه', c_sales: 'فروش (بازه)', c_paid: 'پرداخت (بازه)', c_debt: 'بدهی', c_last: 'آخرین پرداخت', c_open: 'فاکتور باز', c_act: 'اقدام',
    pay: 'ثبت پرداخت', statement: 'صورت‌حساب', search: 'جستجوی ادمین یا گروه…', all_groups: 'همهٔ گروه‌ها', none: 'موردی با این فیلتر نیست.',
    page: 'صفحهٔ {p} از {n}', prev_p: 'قبلی', next_p: 'بعدی', per_page: 'در هر صفحه', close: 'بستن', open_n: '{n} فاکتور · {v}', no_open: 'ندارد',
    sort_by: 'مرتب‌سازی بر اساس {c}', archived: 'بایگانی', off_panel: 'روی پنل نیست', total_rows: '{n} ادمین',
    d_summary: 'خلاصه', d_recent: '۵ گردش آخر', d_full: 'صفحهٔ کامل ادمین', d_all_time: 'کل دوره', d_none: 'هنوز گردشی نیست.',
    k_quota_charge: 'شارژ حجم', k_manual_charge: 'بدهکاری دستی', k_adjustment: 'اصلاحیه', k_payment: 'پرداخت', voided: 'باطل‌شده',
  },
  en: {
    month: 'This month', prev: 'Last month', d7: 'Last 7 days', custom: 'Custom', from: 'From', to: 'To', apply: 'Show', date_ph: 'e.g. 1405/08/01',
    sales: 'Sales', paid: 'Paid', debt: 'Total debt', debtors: 'Debtors', credit: 'credit {v}', range: '{a} to {b}',
    adj: 'Adjustments', adj_n: '{n} entries', adj_d: 'debt decreases {v}', adj_u: 'debt increases {v}', adj_note: 'information only — already inside «Sales»',
    t_debtors: 'Debtors', t_all: 'All resellers', t_all_gm: 'All admins', t_payments: 'Reseller payments', t_history: '12-month history', t_statement: 'Group statement',
    c_admin: 'Admin', c_group: 'Group', c_sales: 'Sales (period)', c_paid: 'Paid (period)', c_debt: 'Debt', c_last: 'Last payment', c_open: 'Open invoices', c_act: 'Actions',
    pay: 'Record payment', statement: 'Statement', search: 'Search admin or group…', all_groups: 'All groups', none: 'Nothing matches this filter.',
    page: 'Page {p} of {n}', prev_p: 'Previous', next_p: 'Next', per_page: 'Per page', close: 'Close', open_n: '{n} · {v}', no_open: 'none',
    sort_by: 'Sort by {c}', archived: 'archived', off_panel: 'not on the panel', total_rows: '{n} admins',
    d_summary: 'Summary', d_recent: 'Last 5 entries', d_full: 'Full admin page', d_all_time: 'all time', d_none: 'No entries yet.',
    k_quota_charge: 'Quota charge', k_manual_charge: 'Manual charge', k_adjustment: 'Adjustment', k_payment: 'Payment', voided: 'voided',
  },
}
export const useAT = (lang) => AT[lang] || AT.fa
export const PERIODS = ['month', 'prev', 'd7', 'custom']
const latin = (v) => String(v ?? '').replace(/[۰-۹]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d))

export function Money({ v, lang, tone }) {
  return <bdi dir="ltr" className="tn-money" data-tone={tone}>{toman(v, lang)}</bdi>
}

/** period chips + custom range (values are kept by the caller — in the URL) */
export function PeriodChips({ period, from, to, onChange, lang }) {
  const t = useAT(lang)
  const fRef = useRef(null); const tRef = useRef(null)
  return (
    <div className="ac-period" data-testid="acc-period">
      <div className="ac-chips" role="radiogroup" aria-label={t.month}>
        {PERIODS.map((p) => (
          <button key={p} type="button" role="radio" aria-checked={period === p} className={'ac-chip' + (period === p ? ' on' : '')}
            onClick={() => onChange({ period: p, from: p === 'custom' ? from : '', to: p === 'custom' ? to : '' })} data-testid={`acc-period-${p}`}>{t[p]}</button>
        ))}
      </div>
      {period === 'custom' && (
        <form className="ac-range" onSubmit={(e) => { e.preventDefault(); onChange({ period: 'custom', from: latin(fRef.current.value).trim(), to: latin(tRef.current.value).trim() }) }}>
          <input ref={fRef} className="input" dir="ltr" inputMode="numeric" defaultValue={from} placeholder={`${t.from} · ${t.date_ph}`} aria-label={t.from} />
          <input ref={tRef} className="input" dir="ltr" inputMode="numeric" defaultValue={to} placeholder={`${t.to} · ${t.date_ph}`} aria-label={t.to} />
          <button className="btn-primary text-sm ac-apply">{t.apply}</button>
        </form>
      )}
    </div>
  )
}

/** «فروش» · «پرداخت‌شده» · «جمع بدهی» · «تعداد بدهکارها» + «اصلاحیه‌ها» as information only */
export function SummaryStrip({ sum, lang, from, to }) {
  const t = useAT(lang)
  if (!sum) return null
  const adj = [t.adj_n.replace('{n}', Number(sum.adjust_count || 0).toLocaleString('en-US')),
    Number(sum.adjust_down) > 0 && t.adj_d.replace('{v}', toman(sum.adjust_down, lang)),
    Number(sum.adjust_up) > 0 && t.adj_u.replace('{v}', toman(sum.adjust_up, lang))].filter(Boolean)
  return (
    <div className="ac-strip-w" data-testid="acc-strip">
      {from && <p className="ac-range-txt">{t.range.replace('{a}', jalali(from, false, lang)).replace('{b}', jalali(to, false, lang))}</p>}
      <dl className="ac-strip">
        <div className="tn-tile" data-tn="info"><dt>{t.sales}</dt><dd><bdi dir="ltr">{toman(sum.sales, lang)}</bdi></dd></div>
        <div className="tn-tile" data-tn="success"><dt>{t.paid}</dt><dd><bdi dir="ltr">{toman(sum.paid, lang)}</bdi></dd></div>
        <div className="tn-tile" data-tn={Number(sum.debt) > 0 ? 'danger' : 'muted'}><dt>{t.debt}</dt><dd><bdi dir="ltr">{toman(sum.debt, lang)}</bdi></dd>
          {Number(sum.credit) > 0 && <small>{t.credit.replace('{v}', toman(sum.credit, lang))}</small>}</div>
        <div className="tn-tile" data-tn={Number(sum.debtors) > 0 ? 'warning' : 'success'}><dt>{t.debtors}</dt><dd>{Number(sum.debtors || 0).toLocaleString('en-US')}</dd></div>
      </dl>
      <p className="tn-info" data-testid="acc-adjustments"><b>{t.adj}</b><span>{adj.join(' · ')}</span><span>· {t.adj_note}</span></p>
    </div>
  )
}

export function SortTh({ k, label, sort, desc, onSort, className, lang }) {
  const t = useAT(lang)
  const on = sort === k
  return (
    <th className={className} aria-sort={on ? (desc ? 'descending' : 'ascending') : 'none'}>
      <button type="button" className={'ac-sort' + (on ? ' on' : '')} onClick={() => onSort(k, on ? !desc : k !== 'username' && k !== 'group')}
        title={t.sort_by.replace('{c}', label)} data-testid={`acc-sort-${k}`}>
        {label}<span aria-hidden="true">{on ? (desc ? '▼' : '▲') : '↕'}</span>
      </button>
    </th>
  )
}

/** phones: the table header is hidden there, so sorting is a select (column + direction) */
export function SortSelect({ cols, sort, desc, onSort, lang }) {
  const t = useAT(lang)
  const fa = lang !== 'en'
  return (
    <select className="input ac-sortsel" value={`${sort}:${desc ? 'd' : 'a'}`} aria-label={t.sort_by.replace('{c}', '')} data-testid="acc-sortsel"
      onChange={(e) => { const [k, d] = e.target.value.split(':'); onSort(k, d === 'd') }}>
      {cols.flatMap(([k, l]) => [<option key={k + 'd'} value={`${k}:d`}>{l} {fa ? '(نزولی)' : '(high → low)'}</option>,
        <option key={k + 'a'} value={`${k}:a`}>{l} {fa ? '(صعودی)' : '(low → high)'}</option>])}
    </select>
  )
}

export function Pager({ page, pages, size, onPage, onSize, lang, sizes = [25, 50, 100] }) {
  const t = useAT(lang)
  return (
    <div className="ac-pager">
      <label className="ac-psize"><span>{t.per_page}</span>
        <select className="input" value={size} onChange={(e) => onSize(Number(e.target.value))}>{sizes.map((n) => <option key={n} value={n}>{n}</option>)}</select></label>
      {pages > 1 && <>
        <button type="button" className="ag-act ag-act--sm" data-tone="neutral" disabled={page <= 1} onClick={() => onPage(page - 1)}>{t.prev_p}</button>
        <span>{t.page.replace('{p}', page).replace('{n}', pages)}</span>
        <button type="button" className="ag-act ag-act--sm" data-tone="neutral" disabled={page >= pages} onClick={() => onPage(page + 1)} data-testid="acc-next">{t.next_p}</button>
      </>}
    </div>
  )
}

/** side drawer from the inline-end edge (portal to <body>: never inside a backdrop-filter parent) */
export function Drawer({ open, onClose, title, children, lang }) {
  const t = useAT(lang)
  const ref = useRef(null)
  useEffect(() => {
    if (!open) return undefined
    const k = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', k)
    ref.current?.focus()
    return () => window.removeEventListener('keydown', k)
  }, [open])
  if (!open) return null
  return createPortal(
    <div className="ac-ov" onClick={onClose} role="presentation">
      <style>{ACC_CSS}</style>
      <aside className="ac-drawer" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={ref} onClick={(e) => e.stopPropagation()} data-testid="acc-drawer">
        <div className="ac-dh"><b><bdi>{title}</bdi></b><button type="button" className="ac-x" onClick={onClose} aria-label={t.close}>×</button></div>
        <div className="ac-db">{children}</div>
      </aside>
    </div>, document.body)
}

/** the drawer's «۵ گردش آخر» list */
export function RecentEntries({ entries, lang }) {
  const t = useAT(lang)
  if (!entries?.length) return <p className="ac-muted">{t.d_none}</p>
  return (
    <ul className="ac-recent" data-testid="acc-recent">
      {[...entries].reverse().map((e) => (
        <li key={e.id} data-voided={e.voided || undefined}>
          <span className="lg-kind" data-kind={e.kind}>{t['k_' + e.kind] || e.kind}</span>
          <span className="ac-muted">{jalali(e.date, false, lang)}{e.admin ? <> · <bdi>{e.admin}</bdi></> : null}</span>
          <bdi dir="ltr" className="tn-money" data-tone={e.voided ? 'muted' : e.kind === 'payment' || Number(e.signed) < 0 ? 'success' : 'danger'}>
            {e.kind === 'payment' || Number(e.signed) < 0 ? '−' : '+'}{toman(Math.abs(Number(e.amount)), lang)}</bdi>
          {e.voided && <small className="ac-muted">{t.voided}</small>}
        </li>
      ))}
    </ul>
  )
}

export function DrawerFacts({ items }) {
  return <dl className="ac-facts">{items.filter(Boolean).map(([k, v, tone]) => <div key={k} className="tn-tile" data-tn={tone || 'info'}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
}

export { moneyTone }

export const ACC_CSS = `
.ac { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.ac-period { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; }
.ac-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.ac-chip { min-height: 40px; padding: 0 14px; border-radius: 999px; border: 1px solid var(--c-border); background: transparent; color: var(--c-text);
  font-size: 13px; font-weight: 700; cursor: pointer; }
.ac-chip.on { background: var(--c-primary); border-color: var(--c-primary); color: #fff; }
.ac-range { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.ac-range .input { width: 170px; min-height: 40px; }
.ac-apply { min-height: 40px; }
.ac-range-txt { margin: 0; font-size: 12.5px; color: var(--c-muted-fg); }
.ac-strip-w { display: flex; flex-direction: column; gap: 8px; }
.ac-strip { display: grid; gap: 10px; margin: 0; grid-template-columns: repeat(4, minmax(0, 1fr)); }
.ac-strip .tn-tile dd { font-size: 19px; }
.ac-tabs { display: flex; flex-wrap: wrap; gap: 6px; border-bottom: 1px solid var(--c-border); padding-bottom: 8px; }
.ac-tab { position: relative; min-height: 42px; padding: 0 16px; border-radius: 12px; border: 1px solid transparent; background: transparent;
  color: var(--c-muted-fg); font-size: 14px; font-weight: 800; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; text-decoration: none; }
.ac-tab:hover { color: var(--c-text); background: color-mix(in srgb, var(--c-primary) 7%, transparent); }
.ac-tab.on { color: var(--c-primary-fg); background: color-mix(in srgb, var(--c-primary) 12%, transparent); border-color: color-mix(in srgb, var(--c-primary) 30%, transparent); }
.ac-tab-n { min-width: 20px; height: 20px; padding: 0 6px; border-radius: 999px; font-size: 11.5px; display: inline-grid; place-items: center;
  color: #fff; background: var(--c-danger); }
.ac-links { margin-inline-start: auto; display: flex; flex-wrap: wrap; gap: 6px; }
.ac-tools { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.ac-tools .input { min-height: 42px; }
.ac-tools input[type="search"] { flex: 1 1 220px; max-width: 320px; }
.ac-tools select { width: auto; min-width: 160px; }
.ac-sortsel { display: none; }
.ac-count { margin-inline-start: auto; font-size: 12.5px; color: var(--c-muted-fg); font-weight: 700; }
.ac-tw { overflow-x: auto; border: 1px solid var(--c-border); border-radius: 14px; background: var(--c-surface, var(--c-bg)); }
.ac-t { width: 100%; border-collapse: collapse; font-size: 13.5px; }
.ac-t th { text-align: start; padding: 0; border-bottom: 1px solid var(--c-border); white-space: nowrap; background: color-mix(in srgb, var(--c-text-muted) 5%, transparent); }
.ac-t th.ac-th-plain { padding: 10px 12px; font-size: 12px; font-weight: 800; color: var(--c-muted-fg); }
.ac-sort { display: inline-flex; align-items: center; gap: 6px; width: 100%; padding: 10px 12px; border: 0; background: transparent; color: var(--c-muted-fg);
  font-size: 12px; font-weight: 800; cursor: pointer; text-align: start; white-space: nowrap; }
.ac-sort.on { color: var(--c-primary-fg); }
.ac-sort span { font-size: 10px; opacity: .8; }
.ac-t td { padding: 10px 12px; border-bottom: 1px solid var(--c-border); white-space: nowrap; vertical-align: middle; }
.ac-t tbody tr { cursor: pointer; transition: background .12s; }
.ac-t tbody tr:hover { background: color-mix(in srgb, var(--c-primary) 6%, transparent); }
.ac-t tbody tr[data-debt] td:first-child { box-shadow: inset -3px 0 0 var(--c-danger); }
[dir="ltr"] .ac-t tbody tr[data-debt] td:first-child { box-shadow: inset 3px 0 0 var(--c-danger); }
.ac-name { font-weight: 800; display: inline-flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.ac-grp { font-size: 12.5px; color: var(--c-muted-fg); }
.ac-acts { display: inline-flex; gap: 6px; }
.ac-muted { font-size: 12px; color: var(--c-muted-fg); }
.ac-empty { padding: 18px; text-align: center; color: var(--c-muted-fg); font-size: 13px; }
.ac-pager { display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: 10px; font-size: 12.5px; }
.ac-psize { display: inline-flex; align-items: center; gap: 6px; color: var(--c-muted-fg); font-weight: 700; }
.ac-psize .input { width: auto; min-height: 36px; height: 36px; }
.ac-ov { position: fixed; inset: 0; z-index: 1100; background: rgba(0,0,0,.42); display: flex; justify-content: flex-end; }
.ac-drawer { width: min(460px, 100vw); height: 100%; overflow-y: auto; background: var(--c-bg); color: var(--c-text); box-shadow: 0 0 40px rgba(0,0,0,.3);
  display: flex; flex-direction: column; outline: none; animation: ac-in .18s ease-out; }
@keyframes ac-in { from { transform: translateX(24px); opacity: .6; } to { transform: none; opacity: 1; } }
[dir="rtl"] .ac-drawer { animation-name: ac-in-rtl; }
@keyframes ac-in-rtl { from { transform: translateX(-24px); opacity: .6; } to { transform: none; opacity: 1; } }
.ac-dh { position: sticky; top: 0; z-index: 1; display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 12px 16px;
  border-bottom: 1px solid var(--c-border); background: var(--c-bg); font-size: 16px; }
.ac-x { min-width: 44px; min-height: 44px; border: 0; background: transparent; color: var(--c-text); font-size: 26px; cursor: pointer; }
.ac-db { padding: 14px 16px 20px; display: flex; flex-direction: column; gap: 12px; }
.ac-db h4 { margin: 4px 0 0; font-size: 13px; font-weight: 800; color: var(--c-muted-fg); }
.ac-facts { display: grid; gap: 8px; margin: 0; grid-template-columns: repeat(2, minmax(0, 1fr)); }
.ac-facts dd { font-size: 15px !important; }
.ac-recent { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
.ac-recent li { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 4px 10px; padding: 9px 0; border-top: 1px solid var(--c-border); font-size: 13px; }
.ac-recent li:first-child { border-top: 0; }
.ac-recent li[data-voided] { opacity: .6; text-decoration: line-through; }
.ac-recent .lg-kind { font-size: 11.5px; font-weight: 800; padding: 2px 8px; border-radius: 999px; white-space: nowrap; }
.ac-dbtns { display: flex; flex-wrap: wrap; gap: 8px; }
@media (max-width: 900px) { .ac-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 767px) {
  .ac-tools input[type="search"], .ac-tools select { max-width: none; flex: 1 1 100%; font-size: 16px; min-height: 44px; }
  .ac-tools .ac-sortsel { display: block; }
  .ac-range .input { flex: 1 1 140px; width: auto; font-size: 16px; min-height: 44px; }
  .ac-links { margin-inline-start: 0; }
  .ac-tw { border: 0; background: transparent; overflow: visible; }
  .ac-t thead { display: none; }
  .ac-t, .ac-t tbody, .ac-t tr, .ac-t td { display: block; width: 100%; }
  .ac-t tbody tr { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 6px 12px; padding: 10px 12px; margin-bottom: 8px;
    border: 1px solid var(--c-border); border-radius: 14px; background: var(--c-surface, var(--c-bg)); }
  .ac-t tbody tr[data-debt] { border-inline-start: 4px solid var(--c-danger); }
  .ac-t tbody tr[data-debt] td:first-child { box-shadow: none; }
  .ac-t td { display: flex; flex-direction: column; gap: 1px; padding: 0; border: 0; white-space: normal; min-width: 0; overflow-wrap: anywhere; }
  .ac-t td::before { content: attr(data-label); font-size: 11px; font-weight: 700; color: var(--c-muted-fg); }
  .ac-t td.ac-td-name { grid-column: 1 / -1; }
  .ac-t td.ac-td-name::before { display: none; }
  .ac-t td.ac-td-act { grid-column: 1 / -1; }
  .ac-t td.ac-td-act::before { display: none; }
  .ac-acts .ag-act { flex: 1; justify-content: center; min-height: 44px; }
  .ac-acts { display: flex; width: 100%; }
  .ac-drawer { width: 100vw; }
}
`
