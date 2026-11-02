import { useEffect, useRef, useState } from 'react'
import { jalali, toman } from '../lib/format'
import { copyToClipboard } from '../lib/clipboard'
import { useToast } from './Toast'
import { Ic } from './AgencyIcons'

// v1.34 /agency/ portal: invoices + «پرداخت», «درخواست شارژ», my requests, notices and the
// checkout (card, unique amount, timer, receipt). Backend: apps/agency/billing_views.py.
// `http` = the portal's own client (Agency token).
export const BT = {
  fa: {
    inv_h: 'فاکتورها', unpaid_total: 'جمع پرداخت‌نشده', pay: 'پرداخت', none_inv: 'فاکتوری ندارید.',
    st_unpaid: 'پرداخت‌نشده', st_pending: 'در حال بررسی', st_paid: 'پرداخت‌شده', st_voided: 'باطل‌شده',
    k_quota_charge: 'شارژ حجم', k_manual_charge: 'بدهکاری', k_request: 'درخواست / مدیر گروه', k_settlement: 'تسویه مانده قبلی',
    req_h: 'درخواست شارژ', gb: 'حجم (گیگ)', note: 'یادداشت (اختیاری)', send: 'ارسال درخواست', preview: 'مبلغ: {gb} گیگ × {p} = {a}',
    no_price: 'قیمت هر گیگ برای این ادمین تعریف نشده', my_req: 'درخواست‌های من', none_req: 'درخواستی ثبت نکرده‌اید.',
    r_pending: 'در انتظار تأیید', r_approved: 'تأیید شد', r_rejected: 'رد شد', reason: 'دلیل', invoice: 'فاکتور',
    notices: 'اعلان‌ها', mark_read: 'خواندم', none_n: 'اعلانی نیست.',
    co_h: 'پرداخت {n}', co_amount: 'مبلغ دقیق قابل پرداخت', co_exact: 'لطفاً دقیقاً همین مبلغ را کارت‌به‌کارت کنید تا خودکار تأیید شود.',
    co_card: 'شماره کارت مقصد', co_copy: 'کپی', co_copied: 'کپی شد', co_timer: 'زمان باقی‌مانده', co_expired: 'مهلت تمام شد — دوباره «پرداخت» را بزنید.',
    co_receipt: 'آپلود رسید (اختیاری)', co_ref: 'شماره پیگیری (اختیاری)', co_upload: 'ارسال رسید', co_cancel: 'انصراف',
    co_review: 'رسید دریافت شد — پس از بررسی تأیید می‌شود.', co_ok: 'پرداخت تأیید شد ✓', co_rej: 'پرداخت رد شد', close: 'بستن',
    co_items: 'فاکتورهای این پرداخت', loading: 'در حال بارگذاری…',
  },
  en: {
    inv_h: 'Invoices', unpaid_total: 'Total unpaid', pay: 'Pay', none_inv: 'No invoices.',
    st_unpaid: 'Unpaid', st_pending: 'Pending review', st_paid: 'Paid', st_voided: 'Voided',
    k_quota_charge: 'Volume', k_manual_charge: 'Charge', k_request: 'Request / group manager', k_settlement: 'Previous balance',
    req_h: 'Request volume', gb: 'Volume (GB)', note: 'Note (optional)', send: 'Send request', preview: 'Amount: {gb} GB × {p} = {a}',
    no_price: 'No price per GB is set for this admin', my_req: 'My requests', none_req: 'No requests yet.',
    r_pending: 'Waiting for approval', r_approved: 'Approved', r_rejected: 'Rejected', reason: 'Reason', invoice: 'Invoice',
    notices: 'Notifications', mark_read: 'Mark read', none_n: 'No notifications.',
    co_h: 'Pay {n}', co_amount: 'Exact amount to pay', co_exact: 'Transfer exactly this amount so it is confirmed automatically.',
    co_card: 'Destination card', co_copy: 'Copy', co_copied: 'Copied', co_timer: 'Time left', co_expired: 'Time is up — press “Pay” again.',
    co_receipt: 'Upload receipt (optional)', co_ref: 'Tracking number (optional)', co_upload: 'Send receipt', co_cancel: 'Cancel',
    co_review: 'Receipt received — it will be confirmed after review.', co_ok: 'Payment approved ✓', co_rej: 'Payment rejected', close: 'Close',
    co_items: 'Invoices in this payment', loading: 'Loading…',
  },
}
const err = (e, f) => (e?.response?.data && (e.response.data.detail_fa || e.response.data.detail)) || f
const errL = (e, lang, f) => {
  const d = e?.response?.data
  if (!d) return f
  return (lang === 'fa' ? d.detail_fa : null) || d.detail || (d.receipt_image && d.receipt_image[0]) || f
}
const B = ({ children }) => <bdi dir="ltr" className="ab-num">{children}</bdi>
const gbt = (v) => Number(v || 0).toLocaleString('en-US', { maximumFractionDigits: 2 })

export function PortalBilling({ http, lang, onChange }) {
  const s = BT[lang] || BT.fa
  const toast = useToast()
  const [inv, setInv] = useState(null)
  const [reqs, setReqs] = useState(null)
  const [notes, setNotes] = useState(null)
  const [pay, setPay] = useState(null)
  const load = () => {
    http.get('/invoices/').then((r) => setInv(r.data)).catch(() => setInv({ results: [], unpaid_total: 0 }))
    http.get('/requests/').then((r) => setReqs(r.data.results)).catch(() => setReqs([]))
    http.get('/notices/').then((r) => setNotes(r.data)).catch(() => setNotes({ results: [], unread: 0 }))
  }
  useEffect(() => { load() }, [])
  const startPay = async (id) => {
    try { setPay((await http.post('/payments/', { invoice_id: id })).data) } catch (e) { toast.error(errL(e, lang, '!')) }
  }
  return (
    <div className="ab">
      <style>{AB_CSS}</style>
      {pay && <Checkout http={http} lang={lang} p={pay} onClose={() => { setPay(null); load(); onChange?.() }} />}
      <Notices s={s} lang={lang} data={notes} onRead={async () => { await http.post('/notices/', { read: true }); load() }} />
      <section className="ap-card" data-testid="ab-invoices">
        <div className="ab-h"><h2><Ic n="doc" size={16} />{s.inv_h}</h2>
          {inv && <span className="ab-total">{s.unpaid_total}: <B>{toman(inv.unpaid_total, lang)}</B></span>}</div>
        {!inv ? <div className="ap-spin" /> : inv.results.length === 0 ? <p className="ab-muted">{s.none_inv}</p> : (
          <ul className="ab-list">
            {inv.results.map((r) => (
              <li key={r.id} className="ab-inv" data-st={r.status}>
                <div className="ab-inv-top"><b><B>{r.number}</B></b><span className="ab-pill" data-st={r.status}>{s['st_' + r.status]}</span></div>
                <div className="ab-inv-mid">
                  <span>{s['k_' + r.kind]}{r.gb ? <> · <B>{gbt(r.gb)} GB</B></> : null}{r.admin ? <> · <bdi>{r.admin}</bdi></> : null}</span>
                  <b><B>{toman(r.amount, lang)}</B></b>
                </div>
                <div className="ab-inv-bot"><span className="ab-muted">{jalali(r.created_at, false, lang)}</span>
                  {r.status === 'unpaid' && <button type="button" className="ab-btn" onClick={() => startPay(r.id)} data-testid="ab-pay">{s.pay}</button>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
      <RequestForm http={http} s={s} lang={lang} onSent={load} />
      <section className="ap-card" data-testid="ab-requests">
        <div className="ab-h"><h2><Ic n="clock" size={16} />{s.my_req}</h2></div>
        {!reqs ? <div className="ap-spin" /> : reqs.length === 0 ? <p className="ab-muted">{s.none_req}</p> : (
          <ul className="ab-list">
            {reqs.map((r) => (
              <li key={r.id} className="ab-inv">
                <div className="ab-inv-top"><b><B>+{gbt(r.gb)} GB</B></b><span className="ab-pill" data-st={r.status}>{s['r_' + r.status]}</span></div>
                <div className="ab-inv-mid"><span className="ab-muted">{jalali(r.created_at, true, lang)}</span>
                  {r.amount != null && <b><B>{toman(r.amount, lang)}</B></b>}</div>
                {r.reason && <p className="ab-reason">{s.reason}: {r.reason}</p>}
                {r.invoice && <p className="ab-muted">{s.invoice}: <B>{r.invoice}</B></p>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

function Notices({ s, lang, data, onRead }) {
  if (!data || !data.results.length) return null
  return (
    <section className="ap-card" data-testid="ab-notices">
      <div className="ab-h"><h2><Ic n="alert" size={16} />{s.notices}{data.unread > 0 && <span className="ab-badge">{data.unread}</span>}</h2>
        {data.unread > 0 && <button type="button" className="ab-link" onClick={onRead}>{s.mark_read}</button>}</div>
      <ul className="ab-list">
        {data.results.slice(0, 8).map((n) => (
          <li key={n.id} className="ab-note" data-unread={!n.read || undefined}>
            <b>{(lang === 'en' && n.title_en) || n.title}</b>
            {(n.body || n.body_en) && <span>{(lang === 'en' && n.body_en) || n.body}</span>}
            <small className="ab-muted">{jalali(n.created_at, true, lang)}</small>
          </li>
        ))}
      </ul>
    </section>
  )
}

function RequestForm({ http, s, lang, onSent }) {
  const toast = useToast()
  const [gb, setGb] = useState('')
  const [note, setNote] = useState('')
  const [q, setQ] = useState(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    const v = Number(String(gb).replace(/[^\d.]/g, ''))
    if (!(v > 0)) { setQ(null); return undefined }
    const t = setTimeout(() => http.get('/requests/quote/', { params: { gb: v } }).then((r) => setQ(r.data)).catch(() => setQ(null)), 300)
    return () => clearTimeout(t)
  }, [gb])
  const send = async (e) => {
    e.preventDefault(); setBusy(true)
    try {
      const r = await http.post('/requests/', { gb: String(gb).replace(/[^\d.]/g, ''), note })
      toast.success(lang === 'fa' ? r.data.message_fa : r.data.message)
      setGb(''); setNote(''); onSent()
    } catch (e2) { toast.error(errL(e2, lang, '!')) } finally { setBusy(false) }
  }
  return (
    <form className="ap-card ab-form" onSubmit={send} data-testid="ab-request">
      <div className="ab-h"><h2><Ic n="plus" size={16} />{s.req_h}</h2></div>
      <label><span>{s.gb}</span><input className="ap-input" dir="ltr" inputMode="decimal" value={gb} onChange={(e) => setGb(e.target.value)} required /></label>
      <label><span>{s.note}</span><input className="ap-input" value={note} maxLength={255} onChange={(e) => setNote(e.target.value)} /></label>
      {q && (q.missing_price
        ? <p className="ab-reason" data-testid="ab-noprice">{s.no_price}</p>
        : <p className="ab-preview" data-testid="ab-quote">{s.preview.replace('{gb}', gbt(q.gb)).replace('{p}', toman(q.price_per_gb, lang)).replace('{a}', toman(q.amount, lang))}</p>)}
      <button className="ap-btn" disabled={busy || !q || q.missing_price}>{s.send}</button>
    </form>
  )
}

export function Checkout({ http, lang, p: initial, onClose }) {
  const s = BT[lang] || BT.fa
  const toast = useToast()
  const [p, setP] = useState(initial)
  const [left, setLeft] = useState(0)
  const [file, setFile] = useState(null)
  const [ref, setRef] = useState('')
  const [busy, setBusy] = useState(false)
  const timer = useRef(null)
  useEffect(() => {
    const tick = () => setLeft(Math.max(0, Math.floor((new Date(p.unique_expire_at) - Date.now()) / 1000)))
    tick(); timer.current = setInterval(tick, 1000)
    return () => clearInterval(timer.current)
  }, [p.unique_expire_at])
  useEffect(() => {          // a deposit may confirm it while the page is open
    if (!['pending_payment', 'pending_review'].includes(p.status)) return undefined
    const t = setInterval(() => http.get(`/payments/${p.id}/`).then((r) => setP(r.data)).catch(() => {}), 10000)
    return () => clearInterval(t)
  }, [p.status])
  const copy = async (v) => { if (await copyToClipboard(String(v))) toast.success(s.co_copied) }
  const upload = async (e) => {
    e.preventDefault(); if (!file) return
    setBusy(true)
    const fd = new FormData(); fd.append('receipt_image', file); if (ref) fd.append('receipt_ref', ref)
    try { const r = await http.post(`/payments/${p.id}/receipt/`, fd, { quiet: true }); setP(r.data); toast.success(lang === 'fa' ? r.data.message_fa : r.data.message) }
    catch (e2) { toast.error(errL(e2, lang, '!')) } finally { setBusy(false) }
  }
  const cancel = async () => { try { await http.post(`/payments/${p.id}/cancel/`, {}, { quiet: true }) } catch { /* gone */ } onClose() }
  const mm = String(Math.floor(left / 60)).padStart(2, '0'), ss = String(left % 60).padStart(2, '0')
  const open = p.status === 'pending_payment'
  return (
    <div className="ab-back" role="dialog" aria-modal="true" aria-label={s.co_h.replace('{n}', p.number)}>
      <div className="ab-sheet" data-testid="ab-checkout">
        <div className="ab-h"><h2>{s.co_h.replace('{n}', p.number)}</h2><button type="button" className="ab-x" onClick={onClose} aria-label={s.close}>✕</button></div>
        {p.status === 'approved' && <p className="ab-ok">{s.co_ok}</p>}
        {p.status === 'pending_review' && <p className="ab-preview">{s.co_review}</p>}
        {p.status === 'rejected' && <p className="ab-reason">{s.co_rej}: {p.reject_reason}</p>}
        {open && left === 0 && <p className="ab-reason">{s.co_expired}</p>}
        {open && left > 0 && (
          <>
            <div className="ab-amount">
              <span>{s.co_amount}</span>
              <button type="button" onClick={() => copy(Math.round(Number(p.amount_unique)))} data-testid="ab-amount"><B>{toman(p.amount_unique, lang)}</B> <small>{s.co_copy}</small></button>
              <p>{s.co_exact}</p>
            </div>
            {p.cards.map((c) => (
              <div key={c.id} className="ab-card">
                <span>{s.co_card}{c.bank_name ? ` · ${c.bank_name}` : ''}</span>
                <button type="button" onClick={() => copy(c.card_number)}><B>{String(c.card_number).replace(/(\d{4})(?=\d)/g, '$1 ')}</B> <small>{s.co_copy}</small></button>
                <small>{c.holder_name}</small>
              </div>
            ))}
            <div className="ab-timer">{s.co_timer}: <B>{mm}:{ss}</B></div>
          </>
        )}
        <details className="ab-items"><summary>{s.co_items} ({p.invoices.length})</summary>
          <ul>{p.invoices.map((i) => <li key={i.id}><B>{i.number}</B> · <bdi>{i.admin}</bdi> · <B>{toman(i.amount, lang)}</B></li>)}</ul></details>
        {(open && left > 0 || p.status === 'pending_review') && (
          <form className="ab-form" onSubmit={upload}>
            <label><span>{s.co_receipt}</span><input type="file" accept="image/*" onChange={(e) => setFile(e.target.files?.[0] || null)} /></label>
            <label><span>{s.co_ref}</span><input className="ap-input" dir="ltr" inputMode="numeric" value={ref} onChange={(e) => setRef(e.target.value)} /></label>
            <button className="ap-btn" disabled={busy || !file}>{s.co_upload}</button>
          </form>
        )}
        {open && <button type="button" className="ab-link ab-cancel" onClick={cancel}>{s.co_cancel}</button>}
      </div>
    </div>
  )
}

export const AB_CSS = `
.ab { display: flex; flex-direction: column; gap: 14px; }
.ab-h { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
.ab-h h2 { display: flex; align-items: center; gap: 6px; font-size: 15.5px; font-weight: 800; }
.ab-total { font-size: 13px; font-weight: 700; color: var(--c-danger-fg); }
.ab-num { font-family: 'JetBrains Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }
.ab-muted { font-size: 12.5px; color: var(--c-muted-fg); }
.ab-list { display: flex; flex-direction: column; gap: 8px; }
.ab-inv { border: 1px solid var(--c-border); border-radius: 12px; padding: 10px 12px; display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.ab-inv-top, .ab-inv-mid, .ab-inv-bot { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; font-size: 13.5px; }
.ab-pill { font-size: 11.5px; font-weight: 700; padding: 2px 9px; border-radius: 999px; color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 14%, transparent); }
.ab-pill[data-st="paid"], .ab-pill[data-st="approved"] { color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 14%, transparent); }
.ab-pill[data-st="voided"], .ab-pill[data-st="rejected"] { color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 12%, transparent); }
.ab-pill[data-st="pending"] { color: var(--c-primary-fg, var(--c-primary)); background: color-mix(in srgb, var(--c-primary) 12%, transparent); }
.ab-btn { min-height: 44px; padding: 0 18px; border-radius: 12px; border: 0; font-weight: 800; color: #fff; background: color-mix(in srgb, var(--c-primary) 82%, #000); }
.ab-link { min-height: 44px; padding: 0 12px; border-radius: 10px; border: 0; font-weight: 700; font-size: 13px; color: var(--c-text); background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); }
.ab-badge { display: inline-grid; place-items: center; min-width: 20px; height: 20px; padding: 0 6px; border-radius: 999px; font-size: 11.5px; color: #fff; background: var(--c-danger); }
.ab-note { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; border-radius: 10px; font-size: 13px; border: 1px solid var(--c-border); }
.ab-note[data-unread] { border-color: color-mix(in srgb, var(--c-primary) 45%, var(--c-border)); background: color-mix(in srgb, var(--c-primary) 6%, transparent); }
.ab-form { display: flex; flex-direction: column; gap: 8px; }
.ab-form label { display: flex; flex-direction: column; gap: 4px; font-size: 12.5px; font-weight: 700; min-width: 0; }
.ab-form input[type=file] { font-size: 14px; max-width: 100%; }
.ab-preview { font-size: 13px; font-weight: 700; padding: 8px 10px; border-radius: 10px; color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 8%, transparent); overflow-wrap: anywhere; }
.ab-reason { font-size: 13px; font-weight: 700; padding: 8px 10px; border-radius: 10px; color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 10%, transparent); overflow-wrap: anywhere; }
.ab-ok { font-size: 15px; font-weight: 800; padding: 10px; border-radius: 10px; color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 12%, transparent); }
.ab-back { position: fixed; inset: 0; z-index: 70; background: rgba(0,0,0,.45); display: grid; place-items: center; padding: 16px; }
.ab-sheet { width: min(460px, 100%); max-height: 92dvh; overflow-y: auto; overflow-x: hidden; background: var(--c-bg); color: var(--c-text); border: 1px solid var(--c-border);
  border-radius: 18px; padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.ab-x { width: 44px; height: 44px; border: 0; border-radius: 10px; background: transparent; color: var(--c-muted-fg); }
.ab-amount, .ab-card { display: flex; flex-direction: column; gap: 4px; padding: 10px 12px; border-radius: 12px; border: 1px solid var(--c-border); font-size: 12.5px; }
.ab-amount button, .ab-card button { min-height: 44px; display: flex; align-items: center; justify-content: space-between; gap: 8px; border: 0; background: transparent; color: var(--c-text); font-size: 20px; font-weight: 800; padding: 0; text-align: start; }
.ab-card button { font-size: 17px; }
.ab-amount button small, .ab-card button small { font-size: 12px; color: var(--c-primary); font-weight: 700; }
.ab-amount p { color: var(--c-muted-fg); line-height: 1.7; }
.ab-timer { font-size: 13.5px; font-weight: 700; text-align: center; }
.ab-items summary { cursor: pointer; font-size: 13px; font-weight: 700; min-height: 32px; }
.ab-items li { font-size: 12.5px; padding: 3px 0; overflow-wrap: anywhere; }
.ab-cancel { align-self: center; }
.ab-seg { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
.ab-segb { min-height: 40px; padding: 0 12px; border-radius: 999px; border: 1px solid var(--c-border); background: transparent; color: var(--c-text); font-size: 13px; font-weight: 700; }
.ab-segb.on { background: var(--c-primary); border-color: var(--c-primary); color: #fff; }
.ab-chk { display: inline-flex; align-items: center; gap: 8px; min-height: 32px; }
.ab-chk input { width: 20px; height: 20px; }
.ab-paybar { position: sticky; bottom: 0; display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; margin-top: 10px;
  padding: 10px 12px; border-radius: 12px; background: var(--c-bg); border: 1px solid color-mix(in srgb, var(--c-primary) 40%, var(--c-border)); font-size: 13.5px; font-weight: 700; }
@media (max-width: 767px) { .ab-paybar { bottom: calc(70px + env(safe-area-inset-bottom, 0px)); } }
@media (max-width: 767px) {
  .ab-back { place-items: end stretch; padding: 0; }
  .ab-sheet { width: 100%; border-radius: 20px 20px 0 0; padding-bottom: calc(16px + env(safe-area-inset-bottom, 0px)); }
}
`

// ---- group manager (/panel/my-groups/invoices): select several unpaid invoices → one payment
const MT = {
  fa: { h: 'فاکتورهای گروه', sel: '{n} فاکتور انتخاب شد · {a}', pay_sel: 'پرداخت انتخاب‌شده‌ها', all: 'همه',
    f_unpaid: 'پرداخت‌نشده', f_pending: 'در حال بررسی', f_paid: 'پرداخت‌شده', f_all: 'همه', admin: 'ادمین', my_pay: 'پرداخت‌های من',
    p_pending_payment: 'در انتظار واریز', p_pending_review: 'در حال بررسی', p_approved: 'تأیید شد', p_rejected: 'رد شد',
    p_expired: 'منقضی', p_cancelled: 'لغو شد', open: 'ادامهٔ پرداخت' },
  en: { h: 'Group invoices', sel: '{n} selected · {a}', pay_sel: 'Pay selected', all: 'All',
    f_unpaid: 'Unpaid', f_pending: 'Under review', f_paid: 'Paid', f_all: 'All', admin: 'Admin', my_pay: 'My payments',
    p_pending_payment: 'Waiting for transfer', p_pending_review: 'Under review', p_approved: 'Approved', p_rejected: 'Rejected',
    p_expired: 'Expired', p_cancelled: 'Cancelled', open: 'Continue' },
}

export function ManagerInvoices({ http, lang }) {
  const s = BT[lang] || BT.fa
  const m = MT[lang] || MT.fa
  const toast = useToast()
  const [f, setF] = useState('unpaid')
  const [inv, setInv] = useState(null)
  const [sel, setSel] = useState(new Set())
  const [pay, setPay] = useState(null)
  const [pays, setPays] = useState([])
  const [notes, setNotes] = useState(null)
  const load = () => {
    http.get('/invoices/', { params: { status: f } }).then((r) => setInv(r.data)).catch((e) => { setInv({ results: [], unpaid_total: 0 }); toast.error(errL(e, lang, '!')) })
    http.get('/payments/').then((r) => setPays(r.data.results)).catch(() => {})
    http.get('/notices/').then((r) => setNotes(r.data)).catch(() => {})
  }
  useEffect(() => { setSel(new Set()); load() }, [f])
  const rows = inv?.results || []
  const chosen = rows.filter((r) => sel.has(r.id))
  const total = chosen.reduce((a, r) => a + Number(r.amount), 0)
  const toggle = (id) => setSel((cur) => { const n = new Set(cur); n.has(id) ? n.delete(id) : n.add(id); return n })
  const paySel = async () => {
    try { setPay((await http.post('/payments/', { invoice_ids: chosen.map((r) => r.id) }, { quiet: true })).data) } catch (e) { toast.error(errL(e, lang, '!')) }
  }
  return (
    <div className="ab">
      <style>{AB_CSS}</style>
      {pay && <Checkout http={http} lang={lang} p={pay} onClose={() => { setPay(null); setSel(new Set()); load() }} />}
      <Notices s={s} lang={lang} data={notes} onRead={async () => { await http.post('/notices/', { read: true }, { quiet: true }); load() }} />
      <section className="ap-card" data-testid="gm-invoices">
        <div className="ab-h"><h2><Ic n="doc" size={16} />{m.h}</h2>
          {inv && <span className="ab-total">{s.unpaid_total}: <B>{toman(inv.unpaid_total, lang)}</B></span>}</div>
        <div className="ab-seg">{['unpaid', 'pending', 'paid', 'all'].map((k) => (
          <button key={k} type="button" className={'ab-segb' + (f === k ? ' on' : '')} onClick={() => setF(k)}>{m['f_' + k]}</button>))}</div>
        {!inv ? <div className="ap-spin" /> : rows.length === 0 ? <p className="ab-muted">{s.none_inv}</p> : (
          <ul className="ab-list">
            {rows.map((r) => (
              <li key={r.id} className="ab-inv" data-st={r.status}>
                <div className="ab-inv-top">
                  <label className="ab-chk">{r.status === 'unpaid' && <input type="checkbox" checked={sel.has(r.id)} onChange={() => toggle(r.id)} aria-label={r.number} />}
                    <b><B>{r.number}</B></b></label>
                  <span className="ab-pill" data-st={r.status}>{s['st_' + r.status]}</span>
                </div>
                <div className="ab-inv-mid"><span><bdi>{r.admin}</bdi> · {s['k_' + r.kind]}{r.gb ? <> · <B>{gbt(r.gb)} GB</B></> : null}</span><b><B>{toman(r.amount, lang)}</B></b></div>
                <div className="ab-inv-bot"><span className="ab-muted">{r.group} · {jalali(r.created_at, false, lang)}</span></div>
              </li>
            ))}
          </ul>
        )}
        {chosen.length > 0 && (
          <div className="ab-paybar" data-testid="gm-paybar">
            <span>{m.sel.replace('{n}', chosen.length).replace('{a}', toman(total, lang))}</span>
            <button type="button" className="ab-btn" onClick={paySel} data-testid="gm-pay">{m.pay_sel}</button>
          </div>
        )}
      </section>
      {pays.length > 0 && (
        <section className="ap-card">
          <div className="ab-h"><h2><Ic n="money" size={16} />{m.my_pay}</h2></div>
          <ul className="ab-list">{pays.slice(0, 10).map((p) => (
            <li key={p.id} className="ab-inv">
              <div className="ab-inv-top"><b><B>{p.number}</B></b><span className="ab-pill" data-st={p.status}>{m['p_' + p.status]}</span></div>
              <div className="ab-inv-mid"><span className="ab-muted">{p.invoices.length} × · {jalali(p.created_at, true, lang)}</span><b><B>{toman(p.amount_unique, lang)}</B></b></div>
              {p.reject_reason && <p className="ab-reason">{s.reason}: {p.reject_reason}</p>}
              {['pending_payment', 'pending_review'].includes(p.status) && <button type="button" className="ab-link" onClick={() => setPay(p)}>{m.open}</button>}
            </li>))}</ul>
        </section>
      )}
    </div>
  )
}
