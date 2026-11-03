import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali, toman } from '../lib/format'
import { toISO, todayCell } from '../lib/jalaliCalendar'
import { Alert, Spinner } from '../components/ui'
import { useConfirm } from '../components/ConfirmDialog'
import { Ic } from '../components/AgencyIcons'
import { AgencyReports } from './AgencyReports'

// Agency accounting (caspintunel addition — never changes PAMP's numbers).
// Amounts and balances come from the server; this file only formats.

// a limit in exact GB ("5,200 GB"), as the operator types it; 0 / missing keeps the server text
const limGB = (b, f) => (Number(b) > 0 ? `${(Number(b) / 1024 ** 3).toLocaleString('en-US', { maximumFractionDigits: 2 })} GB` : f)

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
    adjust_hint: 'نوع اصلاحیه را انتخاب کنید و مبلغ را مثبت وارد کنید.', date_hint: 'شمسی، مثلاً 1405/07/24',
    adj_inc: 'افزایش بدهی', adj_dec: 'کاهش بدهی', adj_pick: 'اول «افزایش بدهی» یا «کاهش بدهی» را انتخاب کنید',
    adj_amount: 'مبلغ را به عدد مثبت وارد کنید', adj_more: 'بدهی {u} {a} بیشتر می‌شود', adj_less: 'بدهی {u} {a} کمتر می‌شود',
    adj_admin: 'ادمین', adj_up: 'افزایش بدهی', adj_down: 'کاهش بدهی',
    price_hint: 'قیمت جدید فقط از این تاریخ به بعد اعمال می‌شود؛ شارژهای قبلی تغییر نمی‌کنند.',
    charge_hint: 'با واردکردن حجم، مبلغ = حجم × قیمت هر گیگ همان روز (بدون قیمت، شارژ ثبت نمی‌شود). هر شارژ یک فاکتور صادر می‌کند.',
    quota_note: 'با افزایش سقف یک نماینده از همین پنل (پس از انتقال نهایی)، شارژ حجم خودکار ثبت می‌شود: افزایش گیگ × قیمت همان روز.',
    off_panel: 'روی پنل نیست', limit_change: '{a} → {b}',
    inv_h: 'فاکتورهایی که تسویه می‌شوند', inv_auto: 'خودکار (قدیمی‌ترین اول)', inv_sel: 'انتخاب فاکتورها', inv_none: 'بدون فاکتور',
    inv_none_hint: 'فاکتورها دست نمی‌خورند؛ فقط اگر جمع فاکتورهای پرداخت‌نشده از بدهی بیشتر شود، قدیمی‌ترین‌ها خودکار تسویه می‌شوند.',
    inv_empty: 'فاکتور پرداخت‌نشده‌ای ندارد.', inv_pick: 'دست‌کم یک فاکتور انتخاب کنید', inv_full: 'کامل', inv_part: 'جزئی — مانده {r}',
    inv_will: 'تسویه می‌شود:', inv_left: 'باقی مبلغ ({a}) از بدهی قبلی کم می‌شود.', inv_rem: 'مانده {r}',
    inc_no_inv: '«افزایش بدهی» به فاکتورها دست نمی‌زند.', settles: 'تسویه', mismatch: 'ناهماهنگی: جمع فاکتورهای پرداخت‌نشده ({o}) از بدهی دفتر ({b}) بیشتر است.',
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
    adjust_hint: 'Pick the kind of adjustment and enter a positive amount.', date_hint: 'Jalali, e.g. 1405/07/24',
    adj_inc: 'Increase debt', adj_dec: 'Decrease debt', adj_pick: 'Pick “Increase debt” or “Decrease debt” first',
    adj_amount: 'Enter a positive amount', adj_more: '{u} will owe {a} more', adj_less: '{u} will owe {a} less',
    adj_admin: 'Admin', adj_up: 'debt up', adj_down: 'debt down',
    price_hint: 'A new price only applies from this date on; earlier charges do not change.',
    charge_hint: 'With a volume, the amount = GB × that day\'s price per GB (no price → no charge). Every charge issues an invoice.',
    quota_note: 'Raising a reseller limit from this panel (after the cut-over) records a quota charge automatically: GB increase × that day\'s price.',
    off_panel: 'not on the panel', limit_change: 'limit {a} → {b}',
    inv_h: 'Invoices this settles', inv_auto: 'Automatic (oldest first)', inv_sel: 'Choose invoices', inv_none: 'No invoices',
    inv_none_hint: 'Invoices are left alone; only if unpaid invoices would exceed the debt are the oldest settled automatically.',
    inv_empty: 'No unpaid invoices.', inv_pick: 'Choose at least one invoice', inv_full: 'in full', inv_part: 'partly — {r} left',
    inv_will: 'Settles:', inv_left: 'The rest ({a}) lowers the older balance.', inv_rem: '{r} left',
    inc_no_inv: '“Increase debt” never touches invoices.', settles: 'settles', mismatch: 'Out of sync: unpaid invoices ({o}) exceed the ledger debt ({b}).',
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

/** v1.35.1: which unpaid invoices a payment / debt decrease settles — oldest first (default), chosen, or
 * none (adjustments). The preview mirrors the server (apps/agency/allocation.py): the last one may be partial. */
function InvoicePick({ s, lang, admin, kind, v, put, amount }) {
  const [list, setList] = useState(null)
  useEffect(() => {
    if (!admin) { setList(null); return }
    api.get('/admin/agency/invoices/', { params: { admin, status: 'unpaid' } })
      .then((r) => setList([...r.data.results].reverse())).catch(() => setList([]))
  }, [admin])
  if (!admin || list === null) return null
  const modes = kind === 'payment' ? ['auto', 'selected'] : ['auto', 'selected', 'none']
  const ids = v.invoice_ids || []
  const order = v.settle === 'selected' ? list.filter((r) => ids.includes(r.id)) : v.settle === 'none' ? [] : list
  let left = amount > 0 ? amount : 0
  const plan = []
  for (const r of order) {
    if (left <= 0) break
    const take = Math.min(left, Number(r.remaining))
    plan.push({ r, take, rest: Number(r.remaining) - take }); left -= take
  }
  const toggle = (id) => put({ ...v, invoice_ids: ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id] })
  return (
    <div className="lg-wide lg-inv" data-testid="inv-pick">
      <span className="lg-inv-h">{s.inv_h}</span>
      {list.length === 0 ? <p className="lg-hint">{s.inv_empty}</p> : (
        <>
          <div className="lg-seg" role="radiogroup" aria-label={s.inv_h}>
            {modes.map((m) => (
              <button key={m} type="button" role="radio" aria-checked={v.settle === m} data-on={v.settle === m || undefined}
                onClick={() => put({ ...v, settle: m })} data-testid={'inv-mode-' + m}>{s['inv_' + (m === 'selected' ? 'sel' : m)]}</button>))}
          </div>
          {v.settle === 'selected' && (
            <ul className="lg-inv-list">{list.map((r) => (
              <li key={r.id}><label>
                <input type="checkbox" checked={ids.includes(r.id)} onChange={() => toggle(r.id)} aria-label={r.number} />
                <bdi dir="ltr">{r.number}</bdi>
                <span className="lg-inv-amt"><bdi dir="ltr">{toman(r.remaining, lang)}</bdi>{r.partial && <small> / {toman(r.amount, lang)}</small>}</span>
                <small className="lg-inv-d">{jalali(r.created_at, false, lang)}</small>
              </label></li>))}</ul>
          )}
          {v.settle === 'none' ? <p className="lg-hint">{s.inv_none_hint}</p> : plan.length > 0 && (
            <p className="lg-inv-plan" data-testid="inv-plan">{s.inv_will}{' '}
              {plan.map((x, i) => <span key={x.r.id}>{i > 0 && '، '}<bdi dir="ltr">{x.r.number}</bdi> ({x.rest > 0 ? s.inv_part.replace('{r}', toman(x.rest, lang)) : s.inv_full})</span>)}
              {left > 0 && <> · {s.inv_left.replace('{a}', toman(left, lang))}</>}</p>
          )}
        </>
      )}
    </div>
  )
}

function EntryForm({ s, kind, box, username, admins, lang }) {
  const [v, setV] = useState({ date: todayJ(), amount: '', gb: '', note: '', method: 'card', price: '', direction: '',
    admin: username || (admins && admins.length === 1 ? admins[0] : ''), settle: 'auto', invoice_ids: [] })
  const put = (nv) => { setV(nv); Object.assign(box, nv) }
  // v1.33: an adjustment amount is a positive number; the direction buttons give the sign
  const set = (k) => (e) => put({ ...v, [k]: kind === 'adjustment' && k === 'amount' ? e.target.value.replace(/[-−]/g, '') : e.target.value })
  useEffect(() => { Object.assign(box, v) }, [])
  const amt = Number(latin(v.amount))
  const who = v.admin || username || '—'
  return (
    <div className="lg-form">
      {kind === 'adjustment' && (
        <div className="lg-wide lg-dir" role="radiogroup" aria-label={s.add_adjust}>
          <button type="button" role="radio" aria-checked={v.direction === 'increase'} data-on={v.direction === 'increase' || undefined}
            className="lg-dir-btn lg-dir-btn--inc" onClick={() => put({ ...v, direction: 'increase' })} data-testid="adj-inc">▲ {s.adj_inc}</button>
          <button type="button" role="radio" aria-checked={v.direction === 'decrease'} data-on={v.direction === 'decrease' || undefined}
            className="lg-dir-btn lg-dir-btn--dec" onClick={() => put({ ...v, direction: 'decrease' })} data-testid="adj-dec">▼ {s.adj_dec}</button>
        </div>
      )}
      {kind === 'adjustment' && admins && (
        <label className="lg-wide"><span>{s.adj_admin}</span>
          <select className="input" value={v.admin} onChange={set('admin')} aria-label={s.adj_admin}>
            <option value="">—</option>
            {admins.map((a) => <option key={a} value={a}>{a}</option>)}
          </select></label>
      )}
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
      {kind === 'adjustment' && (v.direction && amt > 0
        ? <p className="lg-wide lg-result" data-dir={v.direction} data-testid="adj-result">
          {(v.direction === 'increase' ? s.adj_more : s.adj_less).replace('{u}', who).replace('{a}', toman(amt, lang))}</p>
        : <p className="lg-hint lg-wide">{s.adjust_hint}</p>)}
      {(kind === 'payment' || (kind === 'adjustment' && v.direction === 'decrease')) &&
        <InvoicePick s={s} lang={lang} admin={v.admin || username} kind={kind} v={v} put={put} amount={amt} />}
      {kind === 'adjustment' && v.direction === 'increase' && <p className="lg-hint lg-wide">{s.inc_no_inv}</p>}
      {kind === 'price' && <p className="lg-hint lg-wide">{s.price_hint}</p>}
      {kind === 'manual_charge' && <p className="lg-hint lg-wide">{s.charge_hint}</p>}
    </div>
  )
}

// v1.35.1: the invoice choice of a payment / decrease, and a page event so the invoices card reloads
const settleBody = (box, s) => {
  if (box.settle === 'selected' && !(box.invoice_ids || []).length) throw new Error(s.inv_pick)
  return box.direction === 'increase' ? {} : { settle: box.settle || 'auto', invoice_ids: box.settle === 'selected' ? box.invoice_ids : undefined }
}
export const ledgerChanged = (who) => window.dispatchEvent(new CustomEvent('ct:agency-ledger', { detail: { admin: who } }))

/** v1.33 «اصلاحیه»: two buttons (increase / decrease debt), a positive amount and the result in
 * words. `username` for one admin, or `admins` (group statement) to pick one. Existing entries
 * are not touched. */
export async function addAdjustment({ confirm, s, lang, username, admins, onDone }) {
  const box = {}
  await confirm({
    tone: 'warning', title: s.add_adjust, targetLabel: username || undefined, confirmLabel: s.save,
    content: <EntryForm s={s} kind="adjustment" box={box} username={username} admins={admins} lang={lang} />,
    action: async () => {
      const who = username || box.admin
      if (!who) throw new Error(s.adj_admin)
      if (!box.direction) throw new Error(s.adj_pick)
      const amount = latin(box.amount)
      if (!(Number(amount) > 0)) throw new Error(s.adj_amount)
      let date
      try { date = isoFromJ(box.date) } catch { throw new Error(s.date_hint) }
      const r = await api.post(`/admin/agency/ledger/${encodeURIComponent(who)}/entries/`,
        { kind: 'adjustment', direction: box.direction, amount, date, note: box.note, ...settleBody(box, s) })
      onDone?.(r.data, who)
      ledgerChanged(who)
    },
  })
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
  useEffect(() => {          // an invoice voided / settled on the invoices card
    const on = (e) => { if (e.detail?.admin === username && e.detail?.from === 'invoices') load() }
    window.addEventListener('ct:agency-ledger', on)
    return () => window.removeEventListener('ct:agency-ledger', on)
  }, [username])

  const add = async (kind, title, tone = 'primary') => {
    if (kind === 'adjustment') { await addAdjustment({ confirm, s, lang, username, onDone: setSt }); return }
    const box = {}
    await confirm({
      tone, title, targetLabel: username, confirmLabel: s.save, content: <EntryForm s={s} kind={kind} box={box} lang={lang} username={username} />,
      action: async () => {
        let date
        try { date = isoFromJ(box.date) } catch { throw new Error(s.date_hint) }
        const r = kind === 'price'
          ? await api.post(base + 'prices/', { price_per_gb: latin(box.price), valid_from: date, note: box.note })
          : await api.post(base + 'entries/', { kind, amount: latin(box.amount), date, method: box.method, note: box.note, gb: latin(box.gb) || undefined,
            ...(kind === 'payment' ? settleBody(box, s) : {}) })
        setSt(r.data)
        if (kind !== 'price') ledgerChanged(username)
      },
    })
  }
  const voidEntry = async (e) => {
    await confirm({
      tone: 'danger', title: s.void, targetLabel: `${s['k_' + e.kind]} · ${signed(e.amount, lang)}`, confirmLabel: s.void,
      reason: { label: s.void_reason, required: true },
      action: async (reason) => { const r = await api.post(`/admin/agency/ledger/entries/${e.id}/void/`, { reason }); setSt(r.data); ledgerChanged(username) },
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
        <h3 className="ag-sh" data-ac="green"><Ic n="wallet" size={15} />{s.title}</h3>
        {st && <span className="lg-head-bal">{s.balance}: <BalanceText value={st.balance} lang={lang} /></span>}
      </div>
      <Alert>{err}</Alert>
      {!st ? <div className="grid place-items-center py-8"><Spinner /></div> : (
        <>
          {st.invoices_mismatch && <p className="lg-mismatch" data-testid="lg-mismatch">⚠ {s.mismatch.replace('{o}', toman(st.invoices_mismatch.open, lang)).replace('{b}', toman(st.invoices_mismatch.balance, lang))}</p>}
          <dl className="ag-nums lg-sum">
            <div><dt>{s.price}</dt><dd>{st.price ? <><bdi dir="ltr">{toman(st.price.price_per_gb, lang)}</bdi><small> · {s.from} {jalali(st.price.valid_from, false, lang)}</small></> : <span className="text-muted">{s.price_none}</span>}</dd></div>
            <div><dt>{s.charges}</dt><dd><bdi dir="ltr">{toman(st.charges, lang)}</bdi></dd></div>
            <div><dt>{s.payments}</dt><dd><bdi dir="ltr">{toman(st.payments, lang)}</bdi></dd></div>
            <div><dt>{s.balance}</dt><dd><BalanceText value={st.balance} lang={lang} /></dd></div>
          </dl>
          <p className="lg-hint">{s.quota_note}</p>
          <div className="lg-actions">
            <button type="button" className="ag-act" data-tone="success" onClick={() => add('payment', s.add_payment, 'success')}><Ic n="money" />{s.add_payment}</button>
            <button type="button" className="ag-act" data-tone="warning" onClick={() => add('manual_charge', s.add_charge)}><Ic n="plus" />{s.add_charge}</button>
            <button type="button" className="ag-act" data-tone="warning" onClick={() => add('adjustment', s.add_adjust, 'warning')}><Ic n="sliders" />{s.add_adjust}</button>
            <button type="button" className="ag-act" data-tone="neutral" onClick={() => add('price', s.add_price)}><Ic n="tag" />{s.add_price}</button>
            <button type="button" className="ag-act" data-tone="neutral" onClick={exportCsv}><Ic n="download" />{s.export}</button>
          </div>
          <h3 className="ag-sec-h ag-sh" data-ac="blue"><Ic n="doc" size={15} />{s.entries}</h3>
          {st.entries.length === 0 ? <p className="ag-empty">{s.none}</p> : (
            <ul className="lg-list">
              {[...st.entries].reverse().map((e) => (
                <li key={e.id} data-voided={e.voided || undefined}>
                  <span className="lg-kind" data-kind={e.kind}>{s['k_' + e.kind]}{e.kind === 'adjustment' && <> · {Number(e.signed) < 0 ? s.adj_down : s.adj_up}</>}</span>
                  <span className="lg-date">{jalali(e.date, false, lang)}</span>
                  <span className="lg-amt"><bdi dir="ltr">{e.kind === 'payment' ? '−' : e.signed < 0 ? '−' : '+'}{toman(Math.abs(Number(e.amount)), lang)}</bdi></span>
                  <span className="lg-run">{s.running}: <BalanceText value={e.balance} lang={lang} /></span>
                  <span className="lg-meta">
                    {e.kind === 'quota_charge' && e.new_limit_fmt && <bdi dir="ltr">{s.limit_change.replace('{a}', limGB(e.old_limit_bytes, e.old_limit_fmt)).replace('{b}', limGB(e.new_limit_bytes, e.new_limit_fmt))}</bdi>}
                    {e.gb && <> · <bdi dir="ltr">{e.gb} GB</bdi></>}{e.price_per_gb && <> × <bdi dir="ltr">{toman(e.price_per_gb, lang)}</bdi></>}
                    {e.method && <> · {s['m_' + e.method]}</>}{e.note && <> · {(lang === 'fa' && e.note_fa) || e.note}</>}{e.created_by && <> · {e.created_by}</>}
                    {e.voided && <> · <b>{s.voided}</b>: {e.void_reason}</>}
                    {!e.voided && e.settles?.length > 0 && <> · {s.settles}: {e.settles.map((x, i) => <span key={i}>{i > 0 && '، '}<bdi dir="ltr">{x.invoice}</bdi></span>)}</>}
                  </span>
                  {!e.voided && <button type="button" className="lg-void" onClick={() => voidEntry(e)}><Ic n="x" size={13} />{s.void}</button>}
                </li>
              ))}
            </ul>
          )}
          {st.prices.length > 0 && (
            <>
              <h3 className="ag-sec-h ag-sh" data-ac="orange"><Ic n="tag" size={15} />{s.prices}</h3>
              <ul className="lg-prices">
                {st.prices.map((p) => <li key={p.id}><bdi dir="ltr">{toman(p.price_per_gb, lang)}</bdi> · {s.from} {jalali(p.valid_from, false, lang)}{p.note && ` · ${(lang === 'fa' && p.note_fa) || p.note}`}{p.created_by && ` · ${p.created_by}`}</li>)}
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
          <AgencyReports />
          <div className="card ag-card lg-total"><span>{s.total}</span><BalanceText value={d.total_balance} lang={lang} /></div>
          <div className="card ag-table-wrap">
            <table className="ag-table">
              <thead><tr><th><span className="ag-th" data-ac="blue"><Ic n="user" size={13} />{s.overview}</span></th><th><span className="ag-th" data-ac="orange"><Ic n="tag" size={13} />{s.price}</span></th><th><span className="ag-th" data-ac="red"><Ic n="wallet" size={13} />{s.balance}</span></th></tr></thead>
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

export const LG_CSS = `
.lg-dir { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 8px; }
.lg-dir-btn { min-height: 44px; border-radius: 12px; font-weight: 800; font-size: 13.5px; border: 1.5px solid currentColor; background: transparent; }
.lg-dir-btn--inc { color: var(--c-danger-fg); }
.lg-dir-btn--dec { color: var(--c-success-fg); }
.lg-dir-btn--inc[data-on] { color: #fff; background: var(--c-danger); border-color: var(--c-danger); }
.lg-dir-btn--dec[data-on] { color: #fff; background: #11AB53; border-color: #11AB53; }
.lg-result { overflow-wrap: anywhere; font-size: 13.5px; font-weight: 800; padding: 8px 12px; border-radius: 10px; }
.lg-result[data-dir="increase"] { color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 10%, transparent); }
.lg-result[data-dir="decrease"] { color: var(--c-success-fg); background: color-mix(in srgb, #11AB53 12%, transparent); }
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
.lg-void { display: inline-flex; align-items: center; gap: 4px; grid-column: -2; font-size: 12px; font-weight: 700; color: var(--c-danger-fg); padding: 4px 8px; border-radius: 8px; justify-self: end;
  background: color-mix(in srgb, var(--c-danger) 11%, transparent); border: 1px solid color-mix(in srgb, var(--c-danger) 30%, transparent); }
.lg-void:hover { background: color-mix(in srgb, var(--c-danger) 19%, transparent); }
.lg-prices { font-size: 12.5px; display: flex; flex-direction: column; gap: 4px; }
.lg-form { display: grid; gap: 10px; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); margin-top: 10px; text-align: start; min-width: 0; }
.lg-form label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; font-weight: 700; min-width: 0; }
.lg-form .input { width: 100%; min-width: 0; }
.lg-form .lg-wide { grid-column: 1 / -1; }
.lg-inv { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.lg-inv-h { font-size: 12px; font-weight: 700; }
.lg-seg { display: flex; flex-wrap: wrap; gap: 6px; }
.lg-seg button { min-height: 44px; padding: 0 12px; border-radius: 999px; border: 1px solid var(--c-border); background: transparent; color: var(--c-text); font-size: 13px; font-weight: 700; }
.lg-seg button[data-on] { background: var(--c-primary); border-color: var(--c-primary); color: #fff; }
.lg-inv-list { display: flex; flex-direction: column; border: 1px solid var(--c-border); border-radius: 12px; max-height: 220px; overflow-y: auto; }
.lg-inv-list li + li { border-top: 1px solid var(--c-border); }
.lg-inv-list label { display: grid; grid-template-columns: auto auto minmax(0, 1fr) auto; gap: 8px; align-items: center; min-height: 44px; padding: 4px 10px; font-size: 13px; font-weight: 600; flex-direction: row; }
.lg-inv-list input { width: 20px; height: 20px; }
.lg-inv-amt { font-weight: 800; text-align: end; font-family: 'JetBrains Mono', ui-monospace, monospace; }
.lg-inv-amt small, .lg-inv-d { color: var(--c-muted-fg); font-weight: 600; font-size: 11px; }
.lg-inv-plan { font-size: 12.5px; font-weight: 700; color: var(--c-success-fg); background: color-mix(in srgb, #11AB53 10%, transparent); border-radius: 10px; padding: 8px 10px; overflow-wrap: anywhere; }
.lg-inv-plan bdi, .ab-items2 bdi, .ab-chk-t bdi { white-space: nowrap; }
.lg-mismatch { font-size: 12.5px; font-weight: 700; color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 13%, transparent); border-radius: 10px; padding: 8px 10px; margin-bottom: 8px; }
.lg-total { display: flex; align-items: center; justify-content: space-between; font-weight: 800; }
@media (max-width: 767px) {
  .lg-list li { grid-template-columns: auto 1fr; }
  .lg-amt, .lg-run { text-align: start; }
  .lg-meta { grid-column: 1 / -1; }
  .lg-void { grid-column: 1 / -1; justify-self: start; min-height: 40px; }
  .lg-form { grid-template-columns: minmax(0, 1fr); }
  .lg-form .input { font-size: 16px; height: 44px; }
  .lg-actions .ag-act { flex: 1 1 calc(50% - 8px); }
}
`
