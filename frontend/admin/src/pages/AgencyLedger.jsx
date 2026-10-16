import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali, toman } from '../lib/format'
import { toISO, todayCell } from '../lib/jalaliCalendar'
import { useConfirm } from '../components/ConfirmDialog'
import { useToast } from '../components/Toast'
import { Btn, Empty, Menu, Money, Skeleton } from '../components/agency/kit'

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
    off_panel: 'روی پنل نیست', limit_change: 'سقف {a} ← {b}', more: 'عملیات بیشتر', saved: 'ثبت شد', kind: 'نوع', amount_short: 'مبلغ', details: 'جزئیات',
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
    off_panel: 'not on the panel', limit_change: 'limit {a} → {b}', more: 'More actions', saved: 'Saved', kind: 'Type', amount_short: 'Amount', details: 'Details',
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
  return <span className="lg-bal"><Money n={value} lang={lang} signed /></span>
}

function EntryForm({ s, kind, box }) {
  const [v, setV] = useState({ date: todayJ(), amount: '', gb: '', note: '', method: 'card', price: '' })
  const set = (k) => (e) => { const nv = { ...v, [k]: e.target.value }; setV(nv); Object.assign(box, nv) }
  useEffect(() => { Object.assign(box, v) }, [])
  return (
    <div className="lg-form">
      <label><span>{kind === 'price' ? s.from : s.date}</span>
        <input className="input" dir="ltr" value={v.date} onChange={set('date')} placeholder={s.date_hint} /></label>
      {kind === 'price' ? (
        <label><span>{s.price}</span><input className="input" dir="ltr" inputMode="numeric" value={v.price} onChange={set('price')} autoFocus /></label>
      ) : (
        <label><span>{s.amount}</span><input className="input" dir="ltr" inputMode="numeric" value={v.amount} onChange={set('amount')} autoFocus /></label>
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

/** Statement section for one admin (admin detail page). */
export function LedgerCard({ username }) {
  const [s, lang] = useLT()
  const confirm = useConfirm()
  const toast = useToast()
  const [st, setSt] = useState(null)
  const [err, setErr] = useState('')
  const base = `/admin/agency/ledger/${encodeURIComponent(username)}/`
  const load = () => api.get(base).then((r) => { setSt(r.data); setErr('') }).catch((e) => setErr(apiError(e)))
  useEffect(() => { load() }, [username])

  const add = async (kind, title, tone = 'primary') => {
    const box = {}
    const ok = await confirm({
      tone, title, targetLabel: s.title, targetId: username, confirmLabel: s.save, content: <EntryForm s={s} kind={kind} box={box} />,
      action: async () => {
        let date
        try { date = isoFromJ(box.date) } catch { throw new Error(s.date_hint) }
        const r = kind === 'price'
          ? await api.post(base + 'prices/', { price_per_gb: latin(box.price), valid_from: date, note: box.note })
          : await api.post(base + 'entries/', { kind, amount: latin(box.amount), date, method: box.method, note: box.note, gb: latin(box.gb) || undefined })
        setSt(r.data)
      },
    })
    if (ok) toast.success(s.saved)
  }
  const voidEntry = async (e) => {
    const ok = await confirm({
      tone: 'danger', title: s.void, targetLabel: s['k_' + e.kind], targetId: `${signed(e.amount, lang)} · ${jalali(e.date, false, lang)}`, confirmLabel: s.void,
      details: { rows: [[s.balance, `${signed(st.balance, lang)} ${lang === 'fa' ? '←' : '→'} ${signed(Number(st.balance) - Number(e.signed), lang)}`]] },
      reason: { label: s.void_reason, required: true },
      action: async (reason) => { const r = await api.post(`/admin/agency/ledger/entries/${e.id}/void/`, { reason }); setSt(r.data) },
    })
    if (ok) toast.success(s.saved)
  }
  const exportCsv = async () => {
    try {
      const r = await api.get(base + 'export.csv', { responseType: 'blob' })
      const a = document.createElement('a')
      a.href = URL.createObjectURL(r.data); a.download = `statement-${username}.csv`; a.click()
      setTimeout(() => URL.revokeObjectURL(a.href), 2000)
    } catch (e) { toast.error(apiError(e)) }
  }

  return (
    <section className="ag-sec lg">
      <style>{LG_CSS}</style>
      <div className="ag-sec-h">
        <h2>{s.title}</h2>
        <div className="lg-acts">
          <Btn variant="tonal" icon="plus" onClick={() => add('payment', s.add_payment, 'success')} disabled={!st}>{s.add_payment}</Btn>
          <Menu label={s.more} items={[
            { label: s.add_charge, icon: 'wallet', onClick: () => add('manual_charge', s.add_charge) },
            { label: s.add_adjust, icon: 'reset', onClick: () => add('adjustment', s.add_adjust, 'warning') },
            { label: s.add_price, icon: 'gauge', onClick: () => add('price', s.add_price) },
            null,
            { label: s.export, icon: 'download', onClick: exportCsv },
          ]} />
        </div>
      </div>
      {err && <p className="ag-err" role="alert">{err}</p>}
      {!st ? <Skeleton rows={3} cols={4} /> : (
        <>
          <dl className="ag-dl">
            <div><dt>{s.balance}</dt><dd><BalanceText value={st.balance} lang={lang} /></dd></div>
            <div><dt>{s.price}</dt><dd>{st.price ? <><Money n={st.price.price_per_gb} lang={lang} /><small className="lg-sub">{s.from} {jalali(st.price.valid_from, false, lang)}</small></> : <span className="agk-muted lg-none">{s.price_none}</span>}</dd></div>
            <div><dt>{s.charges}</dt><dd><Money n={st.charges} lang={lang} /></dd></div>
            <div><dt>{s.payments}</dt><dd><Money n={st.payments} lang={lang} /></dd></div>
          </dl>
          <p className="ag-hint">{s.quota_note}</p>
          <h3 className="lg-h3">{s.entries}</h3>
          {st.entries.length === 0 ? <Empty title={s.none} /> : (
            <div className="ag-tablewrap ag-tablewrap--scroll">
              <table className="ag-table dense lg-table">
                <thead><tr><th>{s.date}</th><th>{s.kind}</th><th className="num">{s.amount_short}</th><th className="num">{s.running}</th><th>{s.details}</th><th className="ag-act-col"><span className="sr-only">{s.more}</span></th></tr></thead>
                <tbody>
                  {[...st.entries].reverse().map((e) => (
                    <tr key={e.id} data-voided={e.voided || undefined}>
                      <td className="agk-muted c-date">{jalali(e.date, false, lang)}</td>
                      <td className="c-kind"><span className="lg-kind" data-kind={e.kind}>{s['k_' + e.kind]}</span></td>
                      <td className="num c-amt"><Money n={e.kind === 'payment' ? -Math.abs(Number(e.amount)) : e.signed} lang={lang} /></td>
                      <td className="num c-run" data-label={s.running}><BalanceText value={e.balance} lang={lang} /></td>
                      <td className="lg-meta">
                        {e.kind === 'quota_charge' && e.new_limit_fmt && <bdi>{s.limit_change.replace('{a}', e.old_limit_fmt).replace('{b}', e.new_limit_fmt)}</bdi>}
                        {e.gb && <> · <bdi dir="ltr">{e.gb} GB</bdi></>}{e.price_per_gb && <> × <bdi dir="ltr">{toman(e.price_per_gb, lang)}</bdi></>}
                        {e.method && <> · {s['m_' + e.method]}</>}{e.note && <> · {e.note}</>}{e.created_by && <> · {e.created_by}</>}
                        {e.voided && <> · <b>{s.voided}</b>: {e.void_reason}</>}
                      </td>
                      <td className="ag-act-col">
                        {!e.voided && <Menu label={`${s.more} — ${s['k_' + e.kind]}`} items={[{ label: s.void, icon: 'x', danger: true, onClick: () => voidEntry(e) }]} />}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {st.prices.length > 0 && (
            <>
              <h3 className="lg-h3">{s.prices}</h3>
              <ul className="lg-prices">
                {st.prices.map((p) => <li key={p.id}><Money n={p.price_per_gb} lang={lang} /> <span className="agk-muted">· {s.from} {jalali(p.valid_from, false, lang)}{p.note && ` · ${p.note}`}{p.created_by && ` · ${p.created_by}`}</span></li>)}
              </ul>
            </>
          )}
        </>
      )}
    </section>
  )
}

/** Overview page: every reseller's balance. */
export function AgencyLedgerOverview({ Header }) {
  const [s, lang] = useLT()
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { api.get('/admin/agency/ledger/').then((r) => setD(r.data)).catch((e) => { setErr(apiError(e)); setD(false) }) }, [])
  return (
    <div className="ag">
      {Header}
      <style>{LG_CSS}</style>
      {err && <p className="ag-err" role="alert">{err}</p>}
      {d === null ? <Skeleton rows={6} cols={3} /> : d && (
        <>
          <section className="ag-stats lg-stats">
            <div className="ag-stat"><span className="ag-stat-k">{s.total}</span><span className="ag-stat-v"><BalanceText value={d.total_balance} lang={lang} /></span></div>
          </section>
          {d.results.length === 0 ? <Empty title={s.none} /> : (
            <div className="ag-tablewrap">
              <table className="ag-table lg-over">
                <thead><tr><th>{s.overview}</th><th className="num">{s.price}</th><th className="num">{s.balance}</th></tr></thead>
                <tbody>
                  {d.results.map((r) => (
                    <tr key={r.username}>
                      <td className="ag-name">
                        {r.on_panel ? <Link to={`/agency/admins/${encodeURIComponent(r.username)}#accounting`}>{r.username}</Link> : <bdi>{r.username}</bdi>}
                        {!r.on_panel && <span className="ag-grp">{s.off_panel}</span>}
                      </td>
                      <td className="num">{r.price_per_gb != null ? <Money n={r.price_per_gb} lang={lang} /> : <span className="agk-muted">—</span>}</td>
                      <td className="num"><BalanceText value={r.balance} lang={lang} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}

const LG_CSS = `
.lg-bal .agk-qty { font-weight: 750; }
.lg-acts { display: flex; align-items: center; gap: 6px; }
.lg-sub { display: block; font-size: 11.5px; font-weight: 500; color: var(--c-muted-fg); margin-top: 2px; }
.lg-none { font-size: 13px; font-weight: 500; }
.lg-h3 { font-size: 13px; font-weight: 700; color: var(--c-muted-fg); margin-top: 4px; }
.lg-table tr[data-voided] td { opacity: .55; }
.lg-table tr[data-voided] .c-amt { text-decoration: line-through; }
.lg-kind { font-size: 12px; font-weight: 650; color: var(--c-primary-fg); white-space: nowrap; }
.lg-kind[data-kind="payment"] { color: var(--c-success-fg); }
.lg-kind[data-kind="adjustment"] { color: var(--c-warning-fg); }
.lg-meta { font-size: 12px; color: var(--c-muted-fg); white-space: normal !important; min-width: 200px; }
.lg-prices { font-size: 13px; display: flex; flex-direction: column; gap: 6px; }
.lg-form { display: grid; gap: 10px; grid-template-columns: 1fr 1fr; margin-top: 10px; text-align: start; }
.lg-form label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; font-weight: 700; }
.lg-form .lg-wide { grid-column: 1 / -1; }
.lg-hint { font-size: 12px; color: var(--c-muted-fg); line-height: 1.7; }
.lg-stats { grid-template-columns: minmax(0, 1fr); max-width: 360px; }
@media (max-width: 767px) {
  .lg-table thead { display: none; }
  .lg-table, .lg-table tbody { display: block; }
  .lg-table tr { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 4px 10px; padding: 10px 12px; border-bottom: 1px solid var(--c-border); }
  .lg-table td { padding: 0 !important; border: 0 !important; min-width: 0; text-align: start !important; }
  .lg-table .c-kind { grid-row: 1; grid-column: 1; } .lg-table .c-amt { grid-row: 1; grid-column: 2; text-align: end !important; }
  .lg-table .ag-act-col { grid-row: 1 / 3; grid-column: 3; }
  .lg-table .c-date { grid-row: 2; grid-column: 1; } .lg-table .c-run { grid-row: 2; grid-column: 2; text-align: end !important; font-size: 12px; }
  .lg-table .lg-meta { grid-column: 1 / -1; min-width: 0; }
  .lg-form { grid-template-columns: 1fr; }
  .lg-form .input { font-size: 16px; height: 44px; }
}
`
