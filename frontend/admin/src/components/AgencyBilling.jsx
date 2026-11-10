import { useEffect, useRef, useState } from 'react'
import { jalali, toman } from '../lib/format'
import { copyToClipboard } from '../lib/clipboard'
import { useToast } from './Toast'
import { useConfirm } from './ConfirmDialog'
import { Ic } from './AgencyIcons'
import ReceiptDrop, { uploadPct } from './ReceiptDrop'

// v1.34 /agency/ portal: invoices + «پرداخت», «درخواست شارژ», my requests, notices and the
// checkout (card, unique amount, timer, receipt). Backend: apps/agency/billing_views.py.
// `http` = the portal's own client (Agency token).
export const BT = {
  fa: {
    inv_h: 'فاکتورها', unpaid_total: 'جمع پرداخت‌نشده', pay: 'پرداخت', none_inv: 'فاکتوری ندارید.',
    st_unpaid: 'پرداخت‌نشده', st_pending: 'در حال بررسی', st_paid: 'پرداخت‌شده', st_voided: 'باطل‌شده',
    sv_payment: 'پرداخت‌شده', sv_manual: 'پرداخت‌شده (دستی)', sv_adjustment: 'تسویه با اصلاحیه', sv_outside: 'تسویه خارج از سیستم',
    sv_balance: 'تسویه با مانده حساب', sv_mixed: 'پرداخت‌شده', st_partial: 'پرداخت جزئی', paid_rem: 'پرداخت‌شده {p} · مانده {r}',
    k_quota_charge: 'شارژ حجم', k_manual_charge: 'بدهکاری', k_request: 'درخواست شارژ', k_settlement: 'تسویه مانده قبلی', k_store_fee: 'اشتراک فروشگاه',
    src_admin_request: 'درخواست ادمین', src_manager: 'مدیر گروه', src_manual: 'شارژ دستی', src_settlement: 'تسویه مانده قبلی', src_store_fee: 'اشتراک ماهانهٔ فروشگاه',
    req_h: 'درخواست شارژ', req_for: 'درخواست شارژ برای: {u}', gb: 'حجم (گیگ)', note: 'یادداشت (اختیاری)', send: 'ارسال درخواست', preview: 'مبلغ: {gb} گیگ × {p} = {a}',
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
    sv_payment: 'Paid', sv_manual: 'Paid (manual)', sv_adjustment: 'Settled by adjustment', sv_outside: 'Settled outside the system',
    sv_balance: 'Settled by the balance', sv_mixed: 'Paid', st_partial: 'Partly paid', paid_rem: 'paid {p} · {r} left',
    k_quota_charge: 'Volume', k_manual_charge: 'Charge', k_request: 'Volume request', k_settlement: 'Previous balance', k_store_fee: 'Store fee',
    src_admin_request: 'Admin request', src_manager: 'Group manager', src_manual: 'Manual charge', src_settlement: 'Previous balance', src_store_fee: 'Store monthly fee',
    req_h: 'Request volume', req_for: 'Volume request for: {u}', gb: 'Volume (GB)', note: 'Note (optional)', send: 'Send request', preview: 'Amount: {gb} GB × {p} = {a}',
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
// v1.35.1: how an invoice was settled / partly paid (the rest is what a payment asks for)
const invSt = (r, s) => (r.status === 'paid' && r.settled_via && s['sv_' + r.settled_via]) || (r.partial ? s.st_partial : s['st_' + r.status])
const owed = (r) => Number(r.remaining ?? r.amount)
function InvAmount({ r, s, lang }) {
  return <span className="ab-amt"><b><B>{toman(r.partial ? r.remaining : r.amount, lang)}</B></b>
    {r.partial && <small className="ab-muted"><B>{s.paid_rem.replace('{p}', toman(r.paid_amount, lang)).replace('{r}', toman(r.remaining, lang))}</B></small>}</span>
}

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
                <div className="ab-inv-top"><b><B>{r.number}</B></b><span className="ab-pill" data-st={r.partial ? 'partial' : r.status}>{invSt(r, s)}</span></div>
                <div className="ab-inv-mid">
                  <span>{s['src_' + r.source] || s['k_' + r.kind]}{r.gb ? <> · <B>{gbt(r.gb)} GB</B></> : null}{r.admin ? <> · <bdi>{r.admin}</bdi></> : null}</span>
                  <InvAmount r={r} s={s} lang={lang} />
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
  const [pct, setPct] = useState(null)
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
    try { const r = await http.post(`/payments/${p.id}/receipt/`, fd, { quiet: true, onUploadProgress: (ev) => setPct(uploadPct(ev) ?? 0) }); setP(r.data); setFile(null); toast.success(lang === 'fa' ? r.data.message_fa : r.data.message) }
    catch (e2) { toast.error(errL(e2, lang, '!')) } finally { setBusy(false); setPct(null) }
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
            <ReceiptDrop file={file} onChange={setFile} lang={lang} label={s.co_receipt} progress={busy && file ? pct ?? 0 : null} disabled={busy} testId="ab-receipt" />
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
.ab-amt { display: flex; flex-direction: column; align-items: flex-end; gap: 2px; text-align: end; }
.ab-amt small { font-size: 11px; }
.ab-pill[data-st="partial"] { color: var(--c-primary-fg, var(--c-text)); background: color-mix(in srgb, var(--c-primary, #1464BA) 13%, transparent); }
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
.ab-sum { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; font-size: 14px; font-weight: 700; }
.ab-sum b { font-size: 18px; color: var(--c-danger-fg); }
.ab-seg { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
.ab-segb { min-height: 40px; padding: 0 12px; border-radius: 999px; border: 1px solid var(--c-border); background: transparent; color: var(--c-text); font-size: 13px; font-weight: 700; }
.ab-segb.on { background: var(--c-primary); border-color: var(--c-primary); color: #fff; }
.ab-gd { gap: 8px; margin-top: 12px; }
.ab-gd-h { display: flex; align-items: center; justify-content: space-between; gap: 10px; min-height: 48px; padding: 0 12px; border-radius: 12px; border: 1px solid var(--c-border);
  background: color-mix(in srgb, var(--c-danger) 5%, transparent); color: var(--c-text); font-size: 14px; font-weight: 700; width: 100%; }
.ab-gd-h b { margin-inline-start: auto; font-size: 17px; color: var(--c-danger-fg); }
.ab-gd-h b[data-zero] { color: var(--c-success-fg); }
.ab-big { display: flex; flex-direction: column; align-items: center; gap: 10px; text-align: center; padding: 20px 16px; }
.ab-big-l { font-size: 14px; font-weight: 700; }
.ab-big-n { font-size: clamp(28px, 7vw, 40px); font-weight: 900; color: var(--c-danger-fg); line-height: 1.15; overflow-wrap: anywhere; }
.ab-big-n[data-zero] { color: var(--c-success-fg); }
.ab-btn--big { min-height: 52px; width: min(360px, 100%); font-size: 16px; border-radius: 14px; }
.ab-btn:disabled { opacity: .6; }
.ab-tabs { margin-bottom: 0; }
.ab-tabs .ab-segb { min-height: 44px; padding: 0 16px; }
.ab-adm details > summary { list-style: none; cursor: pointer; display: flex; align-items: center; justify-content: space-between; gap: 10px; min-height: 48px; padding: 4px 12px; }
.ab-adm details > summary::-webkit-details-marker { display: none; }
.ab-adm { border: 1px solid var(--c-border); border-radius: 12px; min-width: 0; }
.ab-adm details[open] > summary { border-bottom: 1px solid var(--c-border); }
.ab-adm-n, .ab-adm-t { display: flex; flex-direction: column; gap: 1px; min-width: 0; font-size: 13.5px; font-weight: 700; overflow-wrap: anywhere; }
.ab-adm-t { align-items: flex-end; text-align: end; }
.ab-items2 { display: flex; flex-direction: column; padding: 4px 12px 8px; }
.ab-items2 li { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 7px 0; font-size: 13px; min-width: 0; overflow-wrap: anywhere; }
.ab-items2 li + li { border-top: 1px dashed var(--c-border); }
.ab-items2 li[data-type="old"] span { font-weight: 700; }
.ab-items2 .ab-pill { margin-inline-start: 6px; }
.ab-adv > summary { cursor: pointer; min-height: 44px; display: flex; align-items: center; font-weight: 800; font-size: 14px; }
.ab-adv[open] > summary { margin-bottom: 6px; }
.ab-chk--row { display: grid !important; grid-template-columns: auto minmax(0, 1fr) auto; width: 100%; min-height: 44px; font-size: 13px; }
.ab-chk-t { overflow-wrap: anywhere; }
.ab-items2 .ab-num, .ab-chk-t .ab-num { white-space: nowrap; }
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
  fa: { rq_h: 'درخواست شارژ برای ادمین', rq_admin: 'ادمین', rq_pick: 'انتخاب ادمین', rq_send: 'ارسال درخواست برای تأیید',
    rq_list: 'درخواست‌های من', rq_none: 'درخواستی ثبت نکرده‌اید.',
    t_debt: 'بدهی', t_hist: 'سابقه پرداخت‌ها', total_h: 'کل بدهی گروه', pay_all: 'پرداخت کل بدهی', nothing: 'بدهی‌ای ندارید ✓',
    review: '{a} در حال بررسی (در یک پرداخت دیگر)', payable: 'قابل پرداخت: {a}', open_pay: 'یک پرداخت نیمه‌تمام دارید — ادامه',
    changed_t: 'مبلغ کل تغییر کرد', changed: 'از وقتی صفحه باز شد، بدهی گروه تغییر کرده است. مبلغ جدید:', pay_new: 'پرداخت {a}',
    br_h: 'ریز بدهی', show_all: 'نمایش همه', hide_zero: 'فقط بدهکارها', old_line: 'مانده قبلی (بی‌فاکتور)', no_admins: 'ادمینی در گروه‌های شما نیست.',
    zero: 'بدون بدهی', items: '{n} قلم', in_review: 'در حال بررسی', partial: 'پرداخت جزئی — از {f}',
    sel_h: 'پرداخت انتخابی (پیشرفته)', sel_hint: 'فقط وقتی لازم است بخشی از بدهی را بپردازید.', sel: '{n} قلم انتخاب شد · {a}', pay_sel: 'پرداخت انتخاب‌شده‌ها',
    hist_none: 'هنوز پرداختی ثبت نکرده‌اید.', open: 'ادامهٔ پرداخت', group: 'گروه', ledger_check: 'دفتر حساب: {a}',
    p_pending_payment: 'در انتظار واریز', p_pending_review: 'در حال بررسی', p_approved: 'تأیید شد', p_rejected: 'رد شد',
    p_expired: 'منقضی', p_cancelled: 'لغو شد' },
  en: { rq_h: 'Request volume for an admin', rq_admin: 'Admin', rq_pick: 'Choose an admin', rq_send: 'Send for approval',
    rq_list: 'My requests', rq_none: 'No requests yet.',
    t_debt: 'Debt', t_hist: 'Payment history', total_h: 'Total group debt', pay_all: 'Pay the whole debt', nothing: 'Nothing owed ✓',
    review: '{a} under review (in another payment)', payable: 'Payable: {a}', open_pay: 'You have an unfinished payment — continue',
    changed_t: 'The total changed', changed: 'The group debt changed since the page was opened. New amount:', pay_new: 'Pay {a}',
    br_h: 'Debt breakdown', show_all: 'Show all', hide_zero: 'Only admins who owe', old_line: 'Old balance (no invoice)', no_admins: 'No admins in your groups.',
    zero: 'nothing owed', items: '{n} items', in_review: 'under review', partial: 'partly paid — of {f}',
    sel_h: 'Pay selected items (advanced)', sel_hint: 'Only when you need to pay part of the debt.', sel: '{n} selected · {a}', pay_sel: 'Pay selected',
    hist_none: 'No payments yet.', open: 'Continue', group: 'Group', ledger_check: 'Ledger: {a}',
    p_pending_payment: 'Waiting for transfer', p_pending_review: 'Under review', p_approved: 'Approved', p_rejected: 'Rejected',
    p_expired: 'Expired', p_cancelled: 'Cancelled' },
}

/** v1.35.2 «ریز بدهی»: read-only, one collapsible row per admin (zero-debt admins hidden unless «نمایش همه»).
 * Used by the group-manager page and the staff group card. */
export function DebtBreakdown({ d, lang, testid = 'debt-breakdown' }) {
  const s = BT[lang] || BT.fa
  const m = MT[lang] || MT.fa
  const [all, setAll] = useState(false)
  const rows = (d?.admins || []).filter((a) => all || Number(a.total) > 0)
  const hidden = (d?.admins || []).length - rows.length
  return (
    <div className="ab-br" data-testid={testid}>
      <div className="ab-h"><h2><Ic n="doc" size={16} />{m.br_h}</h2>
        {(hidden > 0 || all) && <button type="button" className="ab-link" onClick={() => setAll(!all)} data-testid="br-toggle">{all ? m.hide_zero : `${m.show_all} (+${hidden})`}</button>}</div>
      {!(d?.admins || []).length ? <p className="ab-muted">{m.no_admins}</p> : rows.length === 0 ? <p className="ab-muted">{m.nothing}</p> : (
        <ul className="ab-list">{rows.map((a) => (
          <li key={a.admin} className="ab-adm">
            <details>
              <summary>
                <span className="ab-adm-n"><bdi>{a.admin}</bdi>{a.group && <small className="ab-muted">{a.group}</small>}</span>
                <span className="ab-adm-t">{Number(a.total) > 0 ? <b><B>{toman(a.total, lang)}</B></b> : <span className="ab-muted">{m.zero}</span>}
                  {a.items.length > 0 && <small className="ab-muted">{m.items.replace('{n}', a.items.length)}</small>}</span>
              </summary>
              {a.items.length > 0 && <ul className="ab-items2">{a.items.map((it, i) => (
                <li key={i} data-type={it.type}>
                  {it.type === 'old' ? <span>{m.old_line}</span> : (
                    <span><B>{it.number}</B><> · {s['src_' + it.source] || s['k_' + it.kind]}</>{it.gb ? <> · <B>{gbt(it.gb)} GB</B></> : null}
                      <small className="ab-muted"> · {jalali(it.date, false, lang)}</small>
                      {it.status === 'pending' && <small className="ab-pill" data-st="pending">{m.in_review}</small>}
                      {it.partial && <small className="ab-muted"> · {m.partial.replace('{f}', toman(it.full, lang))}</small>}</span>)}
                  <b><B>{toman(it.amount, lang)}</B></b>
                </li>))}</ul>}
            </details>
          </li>))}</ul>
      )}
    </div>
  )
}

/** v1.35.2 staff: «کل بدهی گروه» on a group card (Agency → Groups), same numbers as the group manager sees. */
export function GroupDebt({ api, groupId, lang }) {
  const m = MT[lang] || MT.fa
  const [d, setD] = useState(null)
  const [open, setOpen] = useState(false)
  useEffect(() => { api.get(`/admin/agency/groups/${groupId}/debt/`).then((r) => setD(r.data)).catch(() => setD(false)) }, [groupId])
  if (!d) return null
  const differs = Number(d.ledger_debt) !== Number(d.total)
  return (
    <div className="ab ab-gd" data-testid="group-debt">
      <style>{AB_CSS}</style>
      <button type="button" className="ab-gd-h" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span>{m.total_h}</span>
        <b data-zero={Number(d.total) === 0 || undefined}><B>{toman(d.total, lang)}</B></b>
        <span className="ab-gd-c" aria-hidden="true">{open ? '▴' : '▾'}</span>
      </button>
      {differs && <small className="ab-muted">{m.ledger_check.replace('{a}', toman(d.ledger_debt, lang))}</small>}
      {open && <DebtBreakdown d={d} lang={lang} testid="group-debt-breakdown" />}
    </div>
  )
}

export function ManagerInvoices({ http, lang, canRequest = false }) {
  const s = BT[lang] || BT.fa
  const m = MT[lang] || MT.fa
  const toast = useToast()
  const confirm = useConfirm()
  const [tab, setTab] = useState('debt')
  const [d, setD] = useState(null)
  const [pay, setPay] = useState(null)
  const [pays, setPays] = useState(null)
  const [sel, setSel] = useState(new Set())
  const [busy, setBusy] = useState(false)
  const load = () => {
    http.get('/debt/').then((r) => setD(r.data)).catch((e) => { setD({ admins: [], total: 0, payable: 0 }); toast.error(errL(e, lang, '!')) })
    http.get('/payments/').then((r) => setPays(r.data.results)).catch(() => setPays([]))
  }
  useEffect(() => { load() }, [])
  const payAll = async (expected) => {
    setBusy(true)
    try {
      setPay((await http.post('/payments/all/', { expected_total: String(expected) }, { quiet: true })).data)
    } catch (e) {
      const x = e?.response?.data
      if (x?.reason === 'total_changed') {
        const fresh = (await http.get('/debt/')).data
        setD(fresh)
        setBusy(false)
        if (Number(fresh.payable) > 0) {
          await confirm({ tone: 'warning', title: m.changed_t, message: m.changed, targetLabel: m.total_h, targetId: toman(fresh.payable, lang),
            confirmLabel: m.pay_new.replace('{a}', toman(fresh.payable, lang)),
            action: async () => { setPay((await http.post('/payments/all/', { expected_total: String(fresh.payable) }, { quiet: true })).data) } })
        }
        return
      }
      toast.error(errL(e, lang, '!')); load()
    }
    setBusy(false)
  }
  // advanced: pick invoice / old-balance items
  const items = (d?.admins || []).flatMap((a) => a.items.filter((it) => it.type === 'old' || it.status === 'unpaid')
    .map((it) => ({ ...it, admin: a.admin, key: it.type === 'old' ? `old:${a.admin}` : `inv:${it.id}` })))
  const chosen = items.filter((it) => sel.has(it.key))
  const selTotal = chosen.reduce((t, it) => t + Number(it.amount), 0)
  const toggle = (k) => setSel((cur) => { const n = new Set(cur); n.has(k) ? n.delete(k) : n.add(k); return n })
  const paySel = async () => {
    try {
      const ids = chosen.filter((it) => it.type === 'invoice').map((it) => it.id)
      for (const it of chosen.filter((x) => x.type === 'old')) ids.push((await http.post('/invoices/settlement/', { admin: it.admin }, { quiet: true })).data.id)
      setPay((await http.post('/payments/', { invoice_ids: ids }, { quiet: true })).data)
    } catch (e) { toast.error(errL(e, lang, '!')); load() }
  }
  const total = Number(d?.total || 0)
  const payable = Number(d?.payable || 0)
  return (
    <div className="ab">
      <style>{AB_CSS}</style>
      {pay && <Checkout http={http} lang={lang} p={pay} onClose={() => { setPay(null); setSel(new Set()); load() }} />}
      {/* v1.37: notices live in the header bell / «اعلان‌ها» page, not in the middle of this page */}
      <div className="ab-seg ab-tabs" role="tablist">
        {['debt', 'hist'].map((k) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} className={'ab-segb' + (tab === k ? ' on' : '')} onClick={() => setTab(k)} data-testid={'gm-tab-' + k}>
            {m['t_' + k]}{k === 'hist' && (pays || []).some((p) => p.status === 'pending_review') && <span className="ab-badge">{(pays || []).filter((p) => p.status === 'pending_review').length}</span>}</button>))}
      </div>
      {tab === 'debt' ? (
        <>
          <section className="ap-card ab-big" data-testid="gm-total">
            <span className="ab-big-l">{m.total_h}{d?.groups?.length ? <small className="ab-muted"> · {d.groups.map((g) => g.name).join('، ')}</small> : null}</span>
            <b className="ab-big-n" data-zero={total === 0 || undefined}><B>{d ? toman(total, lang) : '…'}</B></b>
            {d && Number(d.review) > 0 && <span className="ab-muted">{m.review.replace('{a}', toman(d.review, lang))}</span>}
            {d && (payable > 0
              ? <button type="button" className="ab-btn ab-btn--big" disabled={busy} onClick={() => payAll(payable)} data-testid="gm-pay-all">
                {m.pay_all}{Number(d.review) > 0 && <> · <B>{toman(payable, lang)}</B></>}</button>
              : total === 0 && <span className="ab-ok">{m.nothing}</span>)}
            {d?.open_payment && <button type="button" className="ab-link" onClick={() => setPay(d.open_payment)} data-testid="gm-open-pay">{m.open_pay}</button>}
          </section>
          <section className="ap-card"><DebtBreakdown d={d} lang={lang} /></section>
          {canRequest && <ManagerRequest http={http} lang={lang} admins={(d?.admins || []).map((a) => a.admin)} />}
          {items.length > 0 && (
            <details className="ap-card ab-adv" data-testid="gm-advanced">
              <summary>{m.sel_h}</summary>
              <p className="ab-muted">{m.sel_hint}</p>
              <ul className="ab-list">{items.map((it) => (
                <li key={it.key} className="ab-inv"><label className="ab-chk ab-chk--row">
                  <input type="checkbox" checked={sel.has(it.key)} onChange={() => toggle(it.key)} aria-label={it.number || m.old_line} />
                  <span className="ab-chk-t"><bdi>{it.admin}</bdi> · {it.type === 'old' ? m.old_line : <B>{it.number}</B>}</span>
                  <b><B>{toman(it.amount, lang)}</B></b></label></li>))}</ul>
              {chosen.length > 0 && (
                <div className="ab-paybar" data-testid="gm-paybar">
                  <span>{m.sel.replace('{n}', chosen.length).replace('{a}', toman(selTotal, lang))}</span>
                  <button type="button" className="ab-btn" onClick={paySel} data-testid="gm-pay">{m.pay_sel}</button>
                </div>
              )}
            </details>
          )}
        </>
      ) : (
        <section className="ap-card" data-testid="gm-history">
          <div className="ab-h"><h2><Ic n="money" size={16} />{m.t_hist}</h2></div>
          {pays === null ? <div className="ap-spin" /> : pays.length === 0 ? <p className="ab-muted">{m.hist_none}</p> : (
            <ul className="ab-list">{pays.map((p) => (
              <li key={p.id} className="ab-inv">
                <div className="ab-inv-top"><b><B>{p.number}</B></b><span className="ab-pill" data-st={p.status}>{m['p_' + p.status]}</span></div>
                <div className="ab-inv-mid"><span className="ab-muted">{p.invoices.map((i) => i.number).join('، ')}</span><b><B>{toman(p.amount_unique, lang)}</B></b></div>
                <div className="ab-inv-bot"><span className="ab-muted">{jalali(p.created_at, true, lang)}{p.admins?.length ? <> · {p.admins.join('، ')}</> : null}</span>
                  {['pending_payment', 'pending_review'].includes(p.status) && <button type="button" className="ab-link" onClick={() => setPay(p)}>{m.open}</button>}</div>
                {p.reject_reason && <p className="ab-reason">{s.reason}: {p.reject_reason}</p>}
              </li>))}</ul>
          )}
        </section>
      )}
    </div>
  )
}


function ManagerRequest({ http, lang, admins }) {
  const s = BT[lang] || BT.fa
  const m = MT[lang] || MT.fa
  const toast = useToast()
  const [admin, setAdmin] = useState('')
  const [gb, setGb] = useState('')
  const [note, setNote] = useState('')
  const [q, setQ] = useState(null)
  const [list, setList] = useState(null)
  const [busy, setBusy] = useState(false)
  const loadList = () => http.get('/requests/').then((r) => setList(r.data.results)).catch(() => setList([]))
  useEffect(() => { loadList() }, [])
  useEffect(() => {
    const v = Number(String(gb).replace(/[^\d.]/g, ''))
    if (!admin || !(v > 0)) { setQ(null); return undefined }
    const t = setTimeout(() => http.get('/requests/', { params: { quote: 1, admin, gb: v } }).then((r) => setQ(r.data)).catch(() => setQ(null)), 300)
    return () => clearTimeout(t)
  }, [admin, gb])
  const send = async (e) => {
    e.preventDefault(); setBusy(true)
    try {
      await http.post('/requests/', { admin, gb: String(gb).replace(/[^\d.]/g, ''), note })
      setGb(''); setNote(''); setQ(null); loadList()
    } catch (e2) { toast.error(errL(e2, lang, '!')) } finally { setBusy(false) }
  }
  return (
    <>
      <form className="ap-card ab-form" onSubmit={send} data-testid="gm-request">
        <div className="ab-h"><h2><Ic n="plus" size={16} />{admin ? <>{s.req_for.split('{u}')[0]}<bdi>{admin}</bdi></> : m.rq_h}</h2></div>
        <label><span>{m.rq_admin}</span>
          <select className="ap-input" value={admin} onChange={(e) => setAdmin(e.target.value)} required>
            <option value="">{m.rq_pick}</option>{admins.map((a) => <option key={a} value={a}>{a}</option>)}
          </select></label>
        <label><span>{s.gb}</span><input className="ap-input" dir="ltr" inputMode="decimal" value={gb} onChange={(e) => setGb(e.target.value)} required /></label>
        <label><span>{s.note}</span><input className="ap-input" value={note} maxLength={255} onChange={(e) => setNote(e.target.value)} /></label>
        {q && (q.missing_price ? <p className="ab-reason">{s.no_price}</p>
          : <p className="ab-preview" data-testid="gm-quote">{s.preview.replace('{gb}', gbt(q.gb)).replace('{p}', toman(q.price_per_gb, lang)).replace('{a}', toman(q.amount, lang))}</p>)}
        <button className="ap-btn" disabled={busy || !q || q.missing_price}>{m.rq_send}</button>
      </form>
      <section className="ap-card">
        <div className="ab-h"><h2><Ic n="clock" size={16} />{m.rq_list}</h2></div>
        {!list ? <div className="ap-spin" /> : list.length === 0 ? <p className="ab-muted">{m.rq_none}</p> : (
          <ul className="ab-list">{list.map((r) => (
            <li key={r.id} className="ab-inv">
              <div className="ab-inv-top"><b><bdi>{r.admin}</bdi> · <B>+{gbt(r.gb)} GB</B></b><span className="ab-pill" data-st={r.status}>{s['r_' + r.status]}</span></div>
              <div className="ab-inv-mid"><span className="ab-muted">{jalali(r.created_at, true, lang)}</span>{r.amount != null && <b><B>{toman(r.amount, lang)}</B></b>}</div>
              {r.reason && <p className="ab-reason">{s.reason}: {r.reason}</p>}
              {r.invoice && <p className="ab-muted">{s.invoice}: <B>{r.invoice}</B></p>}
            </li>))}</ul>
        )}
      </section>
    </>
  )
}
