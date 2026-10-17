import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali, toman } from '../lib/format'
import { toISO, todayCell } from '../lib/jalaliCalendar'
import { Alert, Spinner } from '../components/ui'
import { useConfirm } from '../components/ConfirmDialog'

// Agency accounting (caspintunel addition — never changes PAMP's numbers).
// Amounts and balances come from the server; this file only formats.

export const LT = {
  fa: {
    tab: 'حسابداری', title: 'حساب نماینده', overview: 'بدهی نماینده‌ها', total: 'جمع بدهی', balance: 'بدهی',
    price: 'قیمت هر گیگ', price_none: 'قیمتی ثبت نشده', from: 'از تاریخ', prices: 'تاریخچهٔ قیمت',
    charges: 'جمع بدهکاری', payments: 'جمع پرداخت', entries: 'گردش حساب', none: 'هنوز گردشی ثبت نشده است.',
    k_quota_charge: 'شارژ حجم', k_manual_charge: 'بدهکاری دستی', k_adjustment: 'اصلاحیه', k_payment: 'پرداخت',
    m_card: 'کارت به کارت', m_cash: 'نقدی', m_crypto: 'رمزارز', m_other: 'سایر',
    date: 'تاریخ', amount: 'مبلغ (تومان)', gb: 'حجم (گیگ)', note: 'یادداشت', method: 'روش', running: 'مانده',
    add_price: 'قیمت جدید', add_charge: 'بدهکاری دستی', add_adjust: 'اصلاحیه', add_payment: 'ثبت پرداخت', export: 'خروجی CSV',
    void: 'باطل کردن', voided: 'باطل‌شده', void_reason: 'دلیل باطل کردن', save: 'ثبت',
    adjust_hint: 'مثبت = بدهی بیشتر، منفی = بدهی کمتر', date_hint: 'شمسی، مثلاً 1405/07/24',
    price_hint: 'قیمت جدید فقط از این تاریخ به بعد اعمال می‌شود؛ شارژهای قبلی تغییر نمی‌کنند.',
    quota_note: 'با افزایش سقف یک نماینده از همین پنل (پس از انتقال نهایی)، شارژ حجم خودکار ثبت می‌شود: افزایش گیگ × قیمت همان روز.',
    off_panel: 'روی پنل نیست', limit_change: '{a} → {b}',
  },
  en: {
    tab: 'Accounting', title: 'Reseller account', overview: 'Reseller balances', total: 'Total owed', balance: 'Balance',
    price: 'Price per GB', price_none: 'no price set', from: 'from', prices: 'Price history',
    charges: 'Total charged', payments: 'Total paid', entries: 'Account activity', none: 'No entries yet.',
    k_quota_charge: 'Quota charge', k_manual_charge: 'Manual charge', k_adjustment: 'Adjustment', k_payment: 'Payment',
    m_card: 'Card to card', m_cash: 'Cash', m_crypto: 'Crypto', m_other: 'Other',
    date: 'Date', amount: 'Amount (Toman)', gb: 'Volume (GB)', note: 'Note', method: 'Method', running: 'Balance',
    add_price: 'New price', add_charge: 'Manual charge', add_adjust: 'Adjustment', add_payment: 'Record payment', export: 'Export CSV',
    void: 'Void', voided: 'voided', void_reason: 'Reason for voiding', save: 'Save',
    adjust_hint: 'positive = owes more, negative = owes less', date_hint: 'Jalali, e.g. 1405/07/24',
    price_hint: 'A new price only applies from this date on; earlier charges do not change.',
    quota_note: 'Raising a reseller limit from this panel (after the cut-over) records a quota charge automatically: GB increase × that day\'s price.',
    off_panel: 'not on the panel', limit_change: 'limit {a} → {b}',
  },
}
const useLT = () => { const { lang } = useI18n(); return [LT[lang] || LT.fa, lang] }
const FA_DIGITS = /[۰-۹٠-٩]/g
const latin = (v) => String(v ?? '').replace(FA_DIGITS, (d) => '0123456789'['۰۱۲۳۴۵۶۷۸۹'.indexOf(d) >= 0 ? '۰۱۲۳۴۵۶۷۸۹'.indexOf(d) : '٠١٢٣٤٥٦٧٨٩'.indexOf(d)]).replace(/[,٬\s]/g, '')
const todayJ = () => { const c = todayCell(); return `${c.jy}/${String(c.jm).padStart(2, '0')}/${String(c.jd).padStart(2, '0')}` }
const isoFromJ = (j) => {
  const m = latin(j).match(/^(\d{4})\/(\d{1,2})\/(\d{1,2})$/)
  if (!m) throw new Error('date')
  return toISO(+m[1], +m[2], +m[3])
}
const signed = (n, lang) => (Number(n) < 0 ? '-' : '') + toman(Math.abs(Number(n)), lang)

export function BalanceText({ value, lang }) {
  const n = Number(value || 0)
  return <bdi dir="ltr" className="lg-bal" data-sign={n > 0 ? 'owes' : n < 0 ? 'credit' : 'zero'}>{signed(n, lang)}</bdi>
}

function EntryForm({ s, kind, box }) {
  const [v, setV] = useState({ date: todayJ(), amount: '', gb: '', note: '', method: 'card', price: '' })
  const set = (k) => (e) => { const nv = { ...v, [k]: e.target.value }; setV(nv); Object.assign(box, nv) }
  useEffect(() => { Object.assign(box, v) }, [])
  return (
    <div className="lg-form">
      <label><span>{kind === 'price' ? s.from : s.date}</span>
        <input className="input" dir="ltr" value={v.date} onChange={set('date')} placeholder={s.date_hint} aria-label={s.date} /></label>
      {kind === 'price' ? (
        <label><span>{s.price}</span><input className="input" dir="ltr" inputMode="numeric" value={v.price} onChange={set('price')} aria-label={s.price} /></label>
      ) : (
        <label><span>{s.amount}</span><input className="input" dir="ltr" inputMode="numeric" value={v.amount} onChange={set('amount')} aria-label={s.amount} /></label>
      )}
      {kind === 'payment' && (
        <label><span>{s.method}</span>
          <select className="input" value={v.method} onChange={set('method')}>
            {['card', 'cash', 'crypto', 'other'].map((m) => <option key={m} value={m}>{s['m_' + m]}</option>)}
          </select></label>
      )}
      {kind === 'manual_charge' && (
        <label><span>{s.gb}</span><input className="input" dir="ltr" inputMode="decimal" value={v.gb} onChange={set('gb')} aria-label={s.gb} /></label>
      )}
      <label className="lg-wide"><span>{s.note}</span><input className="input" value={v.note} onChange={set('note')} aria-label={s.note} /></label>
      {kind === 'adjustment' && <p className="lg-hint lg-wide">{s.adjust_hint}</p>}
      {kind === 'price' && <p className="lg-hint lg-wide">{s.price_hint}</p>}
    </div>
  )
}

/** Statement card for one admin (admin detail page). */
export function LedgerCard({ username }) {
  const [s, lang] = useLT()
  const confirm = useConfirm()
  const [st, setSt] = useState(null)
  const [err, setErr] = useState('')
  const base = `/admin/agency/ledger/${encodeURIComponent(username)}/`
  const load = () => api.get(base).then((r) => { setSt(r.data); setErr('') }).catch((e) => setErr(apiError(e)))
  useEffect(() => { load() }, [username])

  const add = async (kind, title, tone = 'primary') => {
    const box = {}
    await confirm({
      tone, title, targetLabel: username, confirmLabel: s.save, content: <EntryForm s={s} kind={kind} box={box} />,
      action: async () => {
        let date
        try { date = isoFromJ(box.date) } catch { throw new Error(s.date_hint) }
        const r = kind === 'price'
          ? await api.post(base + 'prices/', { price_per_gb: latin(box.price), valid_from: date, note: box.note })
          : await api.post(base + 'entries/', { kind, amount: latin(box.amount), date, method: box.method, note: box.note, gb: latin(box.gb) || undefined })
        setSt(r.data)
      },
    })
  }
  const voidEntry = async (e) => {
    await confirm({
      tone: 'danger', title: s.void, targetLabel: `${s['k_' + e.kind]} · ${signed(e.amount, lang)}`, confirmLabel: s.void,
      reason: { label: s.void_reason, required: true },
      action: async (reason) => { const r = await api.post(`/admin/agency/ledger/entries/${e.id}/void/`, { reason }); setSt(r.data) },
    })
  }
  const exportCsv = async () => {
    const r = await api.get(base + 'export.csv', { responseType: 'blob' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(r.data); a.download = `statement-${username}.csv`; a.click()
    setTimeout(() => URL.revokeObjectURL(a.href), 2000)
  }

  return (
    <div className="card ag-card lg">
      <style>{LG_CSS}</style>
      <div className="ag-card-h">
        <h3>{s.title}</h3>
        {st && <span className="lg-head-bal">{s.balance}: <BalanceText value={st.balance} lang={lang} /></span>}
      </div>
      <Alert>{err}</Alert>
      {!st ? <div className="grid place-items-center py-8"><Spinner /></div> : (
        <>
          <dl className="ag-nums lg-sum">
            <div><dt>{s.price}</dt><dd>{st.price ? <><bdi dir="ltr">{toman(st.price.price_per_gb, lang)}</bdi><small> · {s.from} {jalali(st.price.valid_from, false, lang)}</small></> : <span className="text-muted">{s.price_none}</span>}</dd></div>
            <div><dt>{s.charges}</dt><dd><bdi dir="ltr">{toman(st.charges, lang)}</bdi></dd></div>
            <div><dt>{s.payments}</dt><dd><bdi dir="ltr">{toman(st.payments, lang)}</bdi></dd></div>
            <div><dt>{s.balance}</dt><dd><BalanceText value={st.balance} lang={lang} /></dd></div>
          </dl>
          <p className="lg-hint">{s.quota_note}</p>
          <div className="lg-actions">
            <button type="button" className="ag-act" data-tone="success" onClick={() => add('payment', s.add_payment, 'success')}>{s.add_payment}</button>
            <button type="button" className="ag-act" data-tone="warning" onClick={() => add('manual_charge', s.add_charge)}>{s.add_charge}</button>
            <button type="button" className="ag-act" data-tone="warning" onClick={() => add('adjustment', s.add_adjust, 'warning')}>{s.add_adjust}</button>
            <button type="button" className="ag-act" data-tone="neutral" onClick={() => add('price', s.add_price)}>{s.add_price}</button>
            <button type="button" className="ag-act" data-tone="neutral" onClick={exportCsv}>{s.export}</button>
          </div>
          <h3 className="ag-sec-h">{s.entries}</h3>
          {st.entries.length === 0 ? <p className="ag-empty">{s.none}</p> : (
            <ul className="lg-list">
              {[...st.entries].reverse().map((e) => (
                <li key={e.id} data-voided={e.voided || undefined}>
                  <span className="lg-kind" data-kind={e.kind}>{s['k_' + e.kind]}</span>
                  <span className="lg-date">{jalali(e.date, false, lang)}</span>
                  <span className="lg-amt"><bdi dir="ltr">{e.kind === 'payment' ? '−' : e.signed < 0 ? '−' : '+'}{toman(Math.abs(Number(e.amount)), lang)}</bdi></span>
                  <span className="lg-run">{s.running}: <BalanceText value={e.balance} lang={lang} /></span>
                  <span className="lg-meta">
                    {e.kind === 'quota_charge' && e.new_limit_fmt && <bdi dir="ltr">{s.limit_change.replace('{a}', e.old_limit_fmt).replace('{b}', e.new_limit_fmt)}</bdi>}
                    {e.gb && <> · <bdi dir="ltr">{e.gb} GB</bdi></>}{e.price_per_gb && <> × <bdi dir="ltr">{toman(e.price_per_gb, lang)}</bdi></>}
                    {e.method && <> · {s['m_' + e.method]}</>}{e.note && <> · {e.note}</>}{e.created_by && <> · {e.created_by}</>}
                    {e.voided && <> · <b>{s.voided}</b>: {e.void_reason}</>}
                  </span>
                  {!e.voided && <button type="button" className="lg-void" onClick={() => voidEntry(e)}>{s.void}</button>}
                </li>
              ))}
            </ul>
          )}
          {st.prices.length > 0 && (
            <>
              <h3 className="ag-sec-h">{s.prices}</h3>
              <ul className="lg-prices">
                {st.prices.map((p) => <li key={p.id}><bdi dir="ltr">{toman(p.price_per_gb, lang)}</bdi> · {s.from} {jalali(p.valid_from, false, lang)}{p.note && ` · ${p.note}`}{p.created_by && ` · ${p.created_by}`}</li>)}
              </ul>
            </>
          )}
        </>
      )}
    </div>
  )
}

/** Overview page: every reseller's balance. */
export function AgencyLedgerOverview({ Header }) {
  const [s, lang] = useLT()
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { api.get('/admin/agency/ledger/').then((r) => setD(r.data)).catch((e) => { setErr(apiError(e)); setD(false) }) }, [])
  return (
    <div className="ag space-y-4">
      {Header}
      <style>{LG_CSS}</style>
      <Alert>{err}</Alert>
      {d === null ? <div className="grid place-items-center py-16"><Spinner /></div> : d && (
        <>
          <div className="card ag-card lg-total"><span>{s.total}</span><BalanceText value={d.total_balance} lang={lang} /></div>
          <div className="card ag-table-wrap">
            <table className="ag-table">
              <thead><tr><th>{s.overview}</th><th>{s.price}</th><th>{s.balance}</th></tr></thead>
              <tbody>
                {d.results.map((r) => (
                  <tr key={r.username}>
                    <td className="ag-t-name" data-label={s.overview}>
                      {r.on_panel ? <Link to={`/agency/admins/${encodeURIComponent(r.username)}`}>{r.username}</Link> : <bdi>{r.username}</bdi>}
                      {!r.on_panel && <span className="ag-t-grp">{s.off_panel}</span>}
                    </td>
                    <td data-label={s.price}>{r.price_per_gb != null ? <bdi dir="ltr">{toman(r.price_per_gb, lang)}</bdi> : <span className="text-muted">—</span>}</td>
                    <td data-label={s.balance}><BalanceText value={r.balance} lang={lang} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

const LG_CSS = `
.lg-bal { font-family: 'JetBrains Mono', ui-monospace, monospace; font-weight: 800; }
.lg-bal[data-sign="owes"] { color: var(--c-danger-fg); } .lg-bal[data-sign="credit"] { color: var(--c-success-fg); } .lg-bal[data-sign="zero"] { color: var(--c-muted-fg); }
.lg-head-bal { font-size: 13px; font-weight: 700; }
.lg-sum dd small { font-size: 11px; font-weight: 600; color: var(--c-muted-fg); }
.lg-hint { font-size: 12px; color: var(--c-muted-fg); line-height: 1.7; margin: 8px 0; }
.lg-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.lg-list { display: flex; flex-direction: column; }
.lg-list li { display: grid; grid-template-columns: auto auto 1fr auto; gap: 4px 12px; align-items: center; padding: 9px 0; border-top: 1px solid var(--c-border); font-size: 13px; }
.lg-list li:first-child { border-top: 0; }
.lg-list li[data-voided] { opacity: .55; }
.lg-list li[data-voided] .lg-amt { text-decoration: line-through; }
.lg-kind { font-size: 11.5px; font-weight: 700; padding: 2px 9px; border-radius: 999px; color: var(--c-primary-fg); background: color-mix(in srgb, var(--c-primary) 12%, transparent); white-space: nowrap; }
.lg-kind[data-kind="payment"] { color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 14%, transparent); }
.lg-kind[data-kind="adjustment"] { color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 14%, transparent); }
.lg-date { color: var(--c-muted-fg); font-size: 12.5px; }
.lg-amt { font-weight: 800; font-family: 'JetBrains Mono', ui-monospace, monospace; }
.lg-run { font-size: 12px; color: var(--c-muted-fg); text-align: end; }
.lg-meta { grid-column: 1 / -2; font-size: 12px; color: var(--c-muted-fg); overflow-wrap: anywhere; }
.lg-void { grid-column: -2; font-size: 12px; font-weight: 700; color: var(--c-danger-fg); padding: 4px 8px; border-radius: 8px; justify-self: end;
  background: color-mix(in srgb, var(--c-danger) 11%, transparent); border: 1px solid color-mix(in srgb, var(--c-danger) 30%, transparent); }
.lg-void:hover { background: color-mix(in srgb, var(--c-danger) 19%, transparent); }
.lg-prices { font-size: 12.5px; display: flex; flex-direction: column; gap: 4px; }
.lg-form { display: grid; gap: 10px; grid-template-columns: 1fr 1fr; margin-top: 10px; text-align: start; }
.lg-form label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; font-weight: 700; }
.lg-form .lg-wide { grid-column: 1 / -1; }
.lg-total { display: flex; align-items: center; justify-content: space-between; font-weight: 800; }
@media (max-width: 767px) {
  .lg-list li { grid-template-columns: auto 1fr; }
  .lg-amt, .lg-run { text-align: start; }
  .lg-meta { grid-column: 1 / -1; }
  .lg-void { grid-column: 1 / -1; justify-self: start; min-height: 40px; }
  .lg-form { grid-template-columns: 1fr; }
  .lg-form .input { font-size: 16px; height: 44px; }
  .lg-actions .ag-act { flex: 1 1 calc(50% - 8px); }
}
`
