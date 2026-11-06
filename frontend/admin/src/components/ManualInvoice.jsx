import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { jalali, toman } from '../lib/format'
import { todayCell, toISO } from '../lib/jalaliCalendar'
import { useConfirm } from './ConfirmDialog'
import { useToast } from './Toast'
import { DateRangeModal, DRP_CSS } from './DateRangePicker'
import ReceiptDrop, { uploadPct } from './ReceiptDrop'
import AccountNameInput, { nameOk } from './AccountNameInput'

// v1.42.1: staff type TEHRAN dates / times (the server runs in UTC) — default = now in Tehran, sent with +03:30
const tehranNow = () => {
  const f = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Tehran', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false })
  const p = Object.fromEntries(f.formatToParts(new Date()).map((x) => [x.type, x.value]))
  return { date: `${p.year}-${p.month}-${p.day}`, time: `${p.hour === '24' ? '00' : p.hour}:${p.minute}` }
}
const TEHRAN = '+03:30'

// v1.38 «فاکتور دستی» (backend apps/orders/manual.py, adminpanel/views/manual_invoices.py).
// A: «قبلاً پرداخت شده» → approved payment + completed order on the entered date (tag «دستی»).
// B: «صدور فاکتور برای پرداخت» → the customer pays it in their panel (normal checkout).
export const MT = {
  fa: {
    btn: 'فاکتور دستی', h: 'فاکتور دستی', mode_a: 'قبلاً پرداخت شده', mode_b: 'صدور فاکتور برای پرداخت',
    item: 'آیتم', plan: 'پلن', custom: 'آیتم دلخواه', title: 'عنوان', gb: 'حجم (گیگ، اختیاری)', days: 'روز (اختیاری)',
    amount: 'مبلغ (تومان)', paid_at: 'تاریخ پرداخت', time: 'ساعت', method: 'روش پرداخت', m_card: 'کارت‌به‌کارت', m_cash: 'نقدی',
    m_other: 'سایر', card: 'کارت مقصد (اختیاری)', none: '—', ref: 'شماره پیگیری (اختیاری)', receipt: 'تصویر رسید (اختیاری)',
    note: 'یادداشت', due: 'مهلت پرداخت (اختیاری)', pick_date: 'انتخاب تاریخ', apply_svc: 'اعمال روی سرویس (پاسارگارد)',
    a_new: 'سرویس جدید', a_renew: 'تمدید سرویس', a_addon: 'افزایش حجم', service: 'سرویس مشتری', account: 'نام اکانت جدید',
    svc_need_plan: 'برای اعمال روی سرویس یک پلن انتخاب کنید.', save: 'ثبت فاکتور',
    hint_a: 'به‌عنوان پرداخت تأییدشده با برچسب «دستی» ثبت می‌شود و در درآمد همان تاریخ پرداخت حساب می‌شود.',
    hint_b: 'مشتری در سایت، مینی‌اپ و ربات فاکتور را می‌بیند و با «پرداخت» آن را مثل یک سفارش عادی می‌پردازد.',
    err_amount: 'مبلغ را وارد کنید', err_item: 'پلن یا عنوان را وارد کنید', err_date: 'تاریخ پرداخت را انتخاب کنید', err_account: 'نام اکانت معتبر نیست؛ پیشنهاد زیر کادر را ببینید',
    list_h: 'فاکتورهای دستی', st_open: 'باز', st_paid: 'پرداخت‌شده', st_cancelled: 'لغو‌شده', overdue: 'سررسید گذشته',
    cancel: 'لغو فاکتور', cancel_t: 'لغو فاکتور دستی', cancel_msg: 'فاکتور از پنل مشتری برداشته می‌شود.', reason: 'دلیل',
    tag: 'دستی', by: 'ثبت توسط', warn_image: 'تصویر رسید تکراری است', warn_ref: 'شماره پیگیری تکراری است', tx: 'تراکنش',
    md_paid: 'پرداخت‌شده (ثبت دستی)', md_issued: 'صادرشده برای پرداخت',
  },
  en: {
    btn: 'Manual invoice', h: 'Manual invoice', mode_a: 'Already paid', mode_b: 'Issue for payment',
    item: 'Item', plan: 'Plan', custom: 'Custom item', title: 'Title', gb: 'Volume (GB, optional)', days: 'Days (optional)',
    amount: 'Amount (Toman)', paid_at: 'Payment date', time: 'Time', method: 'Method', m_card: 'Card to card', m_cash: 'Cash',
    m_other: 'Other', card: 'Destination card (optional)', none: '—', ref: 'Tracking number (optional)', receipt: 'Receipt image (optional)',
    note: 'Note', due: 'Due date (optional)', pick_date: 'Pick a date', apply_svc: 'Apply to a service (PasarGuard)',
    a_new: 'New service', a_renew: 'Renew a service', a_addon: 'Add volume', service: 'Customer service', account: 'New account name',
    svc_need_plan: 'Pick a plan to apply it to a service.', save: 'Save invoice',
    hint_a: 'Saved as an approved payment tagged “Manual”, counted in revenue on the payment date.',
    hint_b: 'The customer sees it on the site, Mini App and bot and pays it like a normal order.',
    err_amount: 'Enter the amount', err_item: 'Pick a plan or enter a title', err_date: 'Pick the payment date', err_account: 'The account name is not valid — see the suggestion under the field',
    list_h: 'Manual invoices', st_open: 'Open', st_paid: 'Paid', st_cancelled: 'Cancelled', overdue: 'overdue',
    cancel: 'Cancel invoice', cancel_t: 'Cancel manual invoice', cancel_msg: 'The invoice is removed from the customer’s panel.', reason: 'Reason',
    tag: 'Manual', by: 'by', warn_image: 'duplicate receipt image', warn_ref: 'duplicate tracking number', tx: 'Transaction',
    md_paid: 'Paid (entered by staff)', md_issued: 'Issued for payment',
  },
}
const useMT = () => { const { lang } = useI18n(); return [MT[lang] || MT.fa, lang] }
const N = ({ children }) => <bdi dir="ltr" className="mono-num">{children}</bdi>
const latin = (v) => String(v ?? '').replace(/[۰-۹]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d)).replace(/[٠-٩]/g, (d) => '٠١٢٣٤٥٦٧٨٩'.indexOf(d))
const digitsOnly = (v) => latin(v).replace(/[^\d]/g, '')
const jLabel = (iso, lang) => (iso ? jalali(iso, false, lang) : '')

/** The «دستی» tag (Transactions, payment detail, purchase history). */
export function ManualTag({ m, lang }) {
  if (!m) return null
  const s = MT[lang] || MT.fa
  return <span className="mi-tag" title={`${m.number}${m.created_by ? ` · ${s.by} ${m.created_by}` : ''}`}>{s.tag}<style>{TAG_CSS}</style></span>
}

function DateField({ label, value, onChange, s, lang, testid }) {
  const [open, setOpen] = useState(false)
  return (
    <label className="mi-l"><span>{label}</span>
      <button type="button" className="input mi-date" onClick={() => setOpen(true)} data-testid={testid}>
        {value ? <N>{jLabel(value, lang)}</N> : <span className="text-muted">{s.pick_date}</span>}
      </button>
      {open && createPortal(<div className="mi-drp"><style>{DRP_CSS + '.mi-drp .drp-backdrop{z-index:1300}'}</style>
        <DateRangeModal open single initial={value || ''} onClose={() => setOpen(false)} onApply={(r) => onChange(r.from || '')} /></div>, document.body)}
    </label>
  )
}

function Form({ box, opts, s, lang }) {
  const today = todayCell()
  const [v, setV] = useState({ mode: 'paid', kind: 'plan', plan: '', title: '', gb: '', days: '', amount: '',
    date: tehranNow().date || toISO(today.jy, today.jm, today.jd), time: tehranNow().time, method: 'card', card: '', ref: '', file: null,
    note: '', due: '', svc: false, action: 'renew', service: '', account: '' })
  const [pct, setPct] = useState(null)
  const put = (nv) => { setV(nv); Object.assign(box, nv) }
  useEffect(() => { Object.assign(box, v); box.onPct = setPct }, [])
  const plans = opts?.plans || []
  const plan = plans.find((p) => String(p.id) === String(v.plan))
  const pickPlan = (id) => {
    const p = plans.find((x) => String(x.id) === String(id))
    put({ ...v, plan: id, amount: p && !v.amount ? String(p.price) : v.amount,
      gb: p?.data_limit_gb ? String(p.data_limit_gb) : v.gb, days: p?.duration_days ? String(p.duration_days) : v.days })
  }
  const services = (opts?.services || []).filter((x) => !plan || x.panel === plan.panel)
  return (
    <div className="mi-form" data-testid="mi-form">
      <div className="mi-seg" role="radiogroup" aria-label={s.h}>
        {[['paid', s.mode_a], ['issued', s.mode_b]].map(([k, t]) => (
          <button key={k} type="button" role="radio" aria-checked={v.mode === k} data-on={v.mode === k || undefined} onClick={() => put({ ...v, mode: k })} data-testid={'mi-mode-' + k}>{t}</button>))}
      </div>
      <p className="mi-hint">{v.mode === 'paid' ? s.hint_a : s.hint_b}</p>
      <div className="mi-seg mi-seg--sm" role="radiogroup" aria-label={s.item}>
        {[['plan', s.plan], ['custom', s.custom]].map(([k, t]) => (
          <button key={k} type="button" role="radio" aria-checked={v.kind === k} data-on={v.kind === k || undefined} onClick={() => put({ ...v, kind: k, ...(k === 'custom' ? { plan: '', svc: false } : {}) })}>{t}</button>))}
      </div>
      <div className="mi-grid">
        {v.kind === 'plan' ? (
          <label className="mi-l mi-wide"><span>{s.plan}</span>
            <select className="input" value={v.plan} onChange={(e) => pickPlan(e.target.value)} data-testid="mi-plan">
              <option value="">—</option>
              {plans.map((p) => <option key={p.id} value={p.id}>{(lang === 'en' && p.name_en) || p.name} · {toman(p.price, lang)}</option>)}
            </select></label>
        ) : (
          <label className="mi-l mi-wide"><span>{s.title}</span><input className="input" maxLength={120} value={v.title} onChange={(e) => put({ ...v, title: e.target.value })} data-testid="mi-title" /></label>
        )}
        <label className="mi-l"><span>{s.gb}</span><input className="input" dir="ltr" inputMode="numeric" value={v.gb} onChange={(e) => put({ ...v, gb: digitsOnly(e.target.value) })} /></label>
        <label className="mi-l"><span>{s.days}</span><input className="input" dir="ltr" inputMode="numeric" value={v.days} onChange={(e) => put({ ...v, days: digitsOnly(e.target.value) })} /></label>
        <label className="mi-l mi-wide"><span>{s.amount}</span><input className="input" dir="ltr" inputMode="numeric" value={v.amount} onChange={(e) => put({ ...v, amount: digitsOnly(e.target.value) })} data-testid="mi-amount" />
          {Number(v.amount) > 0 && <small className="mi-hint"><N>{toman(v.amount, lang)}</N></small>}</label>
        {v.mode === 'paid' ? (
          <>
            <DateField label={s.paid_at} value={v.date} onChange={(d) => put({ ...v, date: d })} s={s} lang={lang} testid="mi-date" />
            <label className="mi-l"><span>{s.time}</span><input className="input" dir="ltr" type="time" value={v.time} onChange={(e) => put({ ...v, time: e.target.value })} /></label>
            <div className="mi-l mi-wide"><span>{s.method}</span>
              <div className="mi-seg mi-seg--sm" role="radiogroup" aria-label={s.method}>
                {['card', 'cash', 'other'].map((k) => <button key={k} type="button" role="radio" aria-checked={v.method === k} data-on={v.method === k || undefined} onClick={() => put({ ...v, method: k })}>{s['m_' + k]}</button>)}
              </div></div>
            {v.method === 'card' && (
              <label className="mi-l mi-wide"><span>{s.card}</span>
                <select className="input" value={v.card} onChange={(e) => put({ ...v, card: e.target.value })}>
                  <option value="">{s.none}</option>
                  {(opts?.cards || []).map((c) => <option key={c.id} value={c.id}>{c.card_number} · {c.holder_name}</option>)}
                </select></label>
            )}
            <label className="mi-l"><span>{s.ref}</span><input className="input" dir="ltr" inputMode="numeric" value={v.ref} onChange={(e) => put({ ...v, ref: e.target.value })} /></label>
            <div className="mi-l mi-wide"><ReceiptDrop file={v.file} onChange={(file) => put({ ...v, file })} lang={lang} label={s.receipt} progress={pct} testId="mi-receipt" /></div>
          </>
        ) : (
          <DateField label={s.due} value={v.due} onChange={(d) => put({ ...v, due: d })} s={s} lang={lang} testid="mi-due" />
        )}
        <label className="mi-l mi-wide"><span>{s.note}</span><input className="input" value={v.note} onChange={(e) => put({ ...v, note: e.target.value })} /></label>
      </div>
      <label className="mi-check"><input type="checkbox" checked={v.svc} disabled={!plan} onChange={(e) => put({ ...v, svc: e.target.checked })} data-testid="mi-svc" />{s.apply_svc}</label>
      {!plan && <p className="mi-hint">{s.svc_need_plan}</p>}
      {v.svc && plan && (
        <div className="mi-svc">
          <div className="mi-seg mi-seg--sm" role="radiogroup" aria-label={s.apply_svc}>
            {['renew', 'addon', 'new'].map((k) => <button key={k} type="button" role="radio" aria-checked={v.action === k} data-on={v.action === k || undefined} onClick={() => put({ ...v, action: k })}>{s['a_' + k]}</button>)}
          </div>
          {v.action === 'new' ? (
            <div className="mi-l"><AccountNameInput label={s.account} value={v.account} lang={lang} testid="mi-account"
              onChange={(x) => put({ ...v, account: x })} /></div>
          ) : (
            <label className="mi-l"><span>{s.service}</span>
              <select className="input" value={v.service} onChange={(e) => put({ ...v, service: e.target.value })} data-testid="mi-service">
                <option value="">—</option>{services.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
              </select></label>
          )}
        </div>
      )}
    </div>
  )
}

/** «+ فاکتور دستی» — Users → user (purchase history) and CRM 360. Needs payments.manual_invoice. */
export function ManualInvoiceButton({ userId, onDone, className = '' }) {
  const [s, lang] = useMT()
  const { can } = useAuth()
  const confirm = useConfirm()
  const toast = useToast()
  if (!can('payments.manual_invoice')) return null
  const open = async () => {
    const opts = (await api.get(`/admin/users/${userId}/manual-invoices/options/`)).data
    const box = {}
    await confirm({
      tone: 'primary', title: s.h, confirmLabel: s.save, content: <Form box={box} opts={opts} s={s} lang={lang} />,
      action: async () => {
        if (box.kind === 'plan' ? !box.plan : !box.title?.trim()) throw new Error(s.err_item)
        if (!(Number(box.amount) > 0)) throw new Error(s.err_amount)
        const f = new FormData()
        f.append('mode', box.mode)
        if (box.kind === 'plan') f.append('plan', box.plan); else f.append('title', box.title.trim())
        if (box.gb) f.append('volume_gb', box.gb)
        if (box.days) f.append('days', box.days)
        f.append('amount', box.amount)
        if (box.note) f.append('note', box.note)
        if (box.mode === 'paid') {
          if (!box.date) throw new Error(s.err_date)
          f.append('paid_at', `${box.date}T${box.time || '12:00'}:00${TEHRAN}`)
          f.append('method', box.method)
          if (box.method === 'card' && box.card) f.append('bank_card', box.card)
          if (box.ref) f.append('receipt_ref', latin(box.ref))
          if (box.file) f.append('receipt_image', box.file)
        } else if (box.due) f.append('due_at', `${box.due}T23:59:00${TEHRAN}`)
        if (box.svc && box.plan) {
          f.append('service_action', box.action)
          if (box.action === 'new') {
            if (!nameOk(box.account)) throw new Error(s.err_account)
            f.append('account_name', box.account.trim())
          } else f.append('service', box.service || '')
        }
        let r
        try {
          r = await api.post(`/admin/users/${userId}/manual-invoices/`, f,
            box.file ? { onUploadProgress: (ev) => box.onPct?.(uploadPct(ev) ?? 0) } : undefined)
        } finally { box.onPct?.(null) }
        ;(r.data.warnings || []).forEach((w) => toast.error(`${r.data.tx_number}: ${w.kind === 'duplicate_image' ? s.warn_image : s.warn_ref}`))
        onDone?.(r.data)
      },
    })
  }
  return <button type="button" className={'mi-btn ' + className} onClick={open} data-testid="mi-open"><style>{CSS}</style>+ {s.btn}</button>
}

/** The customer's manual invoices (purchase history page / CRM 360). */
export function ManualInvoicesCard({ userId, reloadKey = 0 }) {
  const [s, lang] = useMT()
  const { can } = useAuth()
  const confirm = useConfirm()
  const [rows, setRows] = useState(null)
  const load = () => api.get(`/admin/users/${userId}/manual-invoices/`, { params: { lang } }).then((r) => setRows(r.data.results)).catch(() => setRows([]))
  useEffect(() => { load() }, [userId, reloadKey])
  if (!rows || !rows.length) return null
  const cancel = (r) => confirm({ tone: 'danger', title: s.cancel_t, targetLabel: '#', targetId: r.number, message: s.cancel_msg, confirmLabel: s.cancel,
    reason: { label: s.reason, required: false }, action: async (reason) => { await api.post(`/admin/manual-invoices/${r.id}/cancel/`, { reason: reason || '' }); load() } })
  return (
    <div className="card mi-card" data-testid="mi-list">
      <style>{CSS}</style>
      <h3 className="mi-card-h">{s.list_h}</h3>
      <ul className="mi-list">
        {rows.map((r) => (
          <li key={r.id} data-st={r.status}>
            <div className="mi-r1"><b><N>{r.number}</N></b><span className="mi-st" data-st={r.status}>{s['st_' + r.status]}</span>
              {r.overdue && <span className="mi-st" data-st="overdue">{s.overdue}</span>}<span className="mi-mode">{s['md_' + r.mode]}</span></div>
            <div className="mi-r2"><span>{r.title}{r.volume_gb ? <> · <N>{r.volume_gb} GB</N></> : null}{r.days ? <> · <N>{r.days}</N> {lang === 'fa' ? 'روز' : 'd'}</> : null}</span><b><N>{toman(r.amount, lang)}</N></b></div>
            <div className="mi-r3">
              <span>{jalali(r.paid_at || r.created_at, true, lang)}{r.created_by ? ` · ${s.by} ${r.created_by}` : ''}</span>
              {r.payment_id && <Link to={`/transactions/${r.payment_id}`}>{s.tx} <N>{r.tx_number}</N></Link>}
              {r.status === 'open' && r.mode === 'issued' && can('payments.manual_invoice') && <button type="button" className="mi-x" onClick={() => cancel(r)}>{s.cancel}</button>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

const TAG_CSS = `.mi-tag { display: inline-flex; align-items: center; font-size: 10.5px; font-weight: 800; padding: 1px 8px; border-radius: 999px; margin-inline-start: 6px;
  color: #fff; background: #7C3AED; white-space: nowrap; vertical-align: middle; }`
const CSS = `
.mi-btn { display: inline-flex; align-items: center; gap: 4px; min-height: 36px; padding: 0 14px; border-radius: 10px; font-size: 12.5px; font-weight: 800;
  color: #fff; background: #7C3AED; border: 0; white-space: nowrap; }
.mi-form { display: flex; flex-direction: column; gap: 10px; text-align: start; min-width: 0; }
.mi-seg { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); gap: 6px; }
.mi-seg button { min-height: 44px; border-radius: 12px; border: 1.5px solid var(--c-border); background: transparent; color: var(--c-text); font-weight: 800; font-size: 13px; padding: 0 8px; }
.mi-seg button[data-on] { border-color: #7C3AED; background: color-mix(in srgb, #7C3AED 12%, transparent); color: var(--c-text); }
.mi-seg--sm button { min-height: 40px; font-size: 12.5px; font-weight: 700; }
.mi-hint { font-size: 11.5px; color: var(--c-muted-fg); line-height: 1.7; }
.mi-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 10px; }
.mi-l { display: flex; flex-direction: column; gap: 4px; font-size: 12px; font-weight: 700; min-width: 0; }
.mi-l .input { width: 100%; min-width: 0; }
.mi-wide { grid-column: 1 / -1; }
.mi-date { text-align: start; }
.mi-check { display: flex; align-items: center; gap: 8px; min-height: 44px; font-size: 13px; font-weight: 700; }
.mi-check input { width: 20px; height: 20px; }
.mi-svc { display: flex; flex-direction: column; gap: 8px; padding: 10px; border-radius: 12px; border: 1px dashed color-mix(in srgb, #7C3AED 45%, var(--c-border)); }
.mi-card { padding: 14px; }
.mi-card-h { font-size: 14px; font-weight: 800; margin-bottom: 8px; }
.mi-list { display: flex; flex-direction: column; }
.mi-list li { display: flex; flex-direction: column; gap: 3px; padding: 9px 0; border-top: 1px solid var(--c-border); font-size: 13px; min-width: 0; }
.mi-list li:first-child { border-top: 0; }
.mi-r1, .mi-r2, .mi-r3 { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; justify-content: space-between; min-width: 0; }
.mi-r1 { justify-content: flex-start; }
.mi-r3 { font-size: 11.5px; color: var(--c-muted-fg); }
.mi-r3 a { color: var(--c-primary); font-weight: 700; }
.mi-mode { font-size: 11px; color: var(--c-muted-fg); }
.mi-st { font-size: 11px; font-weight: 700; padding: 1px 8px; border-radius: 999px; color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 14%, transparent); }
.mi-st[data-st="paid"] { color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 14%, transparent); }
.mi-st[data-st="cancelled"] { color: var(--c-muted-fg); background: color-mix(in srgb, var(--c-text-muted) 14%, transparent); }
.mi-st[data-st="overdue"] { color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 12%, transparent); }
.mi-x { min-height: 32px; padding: 0 10px; border-radius: 8px; border: 1px solid var(--c-danger); color: var(--c-danger-fg); background: transparent; font-size: 11.5px; font-weight: 700; }
@media (max-width: 767px) {
  .mi-grid { grid-template-columns: minmax(0, 1fr); }
  .mi-form .input { font-size: 16px; min-height: 44px; }
  .mi-btn, .mi-x { min-height: 44px; }
}
` + TAG_CSS
