import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useAuth } from '../lib/auth'
import { jalali, toman } from '../lib/format'
import { Alert, Spinner } from '../components/ui'
import { useConfirm } from '../components/ConfirmDialog'
import { useToast } from '../components/Toast'
import { Ic } from '../components/AgencyIcons'
import { useLiveApprovals } from '../lib/liveApprovals'
import { usePaymentsEvents } from '../lib/livePayments'
import { LedgerSubNav, GM_CSS } from './AgencyManagers'

// v1.34 staff side of agency invoices + agency payments (backend apps/agency/billing.py,
// adminpanel/views/agency_billing.py). Agency payments are separate from customer payments:
// own queue «واریزهای نمایندگان», own count, never in Transactions / Accounting revenue.
const T = {
  fa: {
    inv_h: 'فاکتورهای نمایندگان', pay_h: 'واریزهای نمایندگان', none: 'موردی نیست.', admin: 'ادمین', group: 'گروه', amount: 'مبلغ',
    status: 'وضعیت', date: 'تاریخ', kind: 'نوع', void: 'باطل کردن', void_t: 'باطل کردن فاکتور', void_reason: 'دلیل',
    void_msg: 'فاکتور و شارژ آن (در صورت وجود) باطل می‌شوند و از بدهی ادمین کم می‌شوند.',
    st_unpaid: 'پرداخت‌نشده', st_pending: 'در حال بررسی', st_paid: 'پرداخت‌شده', st_voided: 'باطل‌شده', all: 'همه',
    k_quota_charge: 'شارژ حجم', k_manual_charge: 'بدهکاری', k_request: 'درخواست / مدیر گروه', k_settlement: 'تسویه مانده قبلی',
    f_review: 'در انتظار بررسی', f_open: 'باز', p_approved: 'تأییدشده', p_rejected: 'ردشده', p_pending_payment: 'در انتظار واریز',
    p_pending_review: 'در انتظار بررسی', p_expired: 'منقضی', p_cancelled: 'لغو شده',
    payer: 'پرداخت‌کننده', payer_admin: 'ادمین', payer_manager: 'مدیر گروه', unique: 'مبلغ یکتا', invoices: 'فاکتورها',
    approve: 'تأیید', reject: 'رد', approve_t: 'تأیید واریز نماینده', approve_msg: 'فاکتورها پرداخت‌شده می‌شوند و یک «پرداخت» در حساب ادمین ثبت می‌شود.',
    reject_t: 'رد واریز نماینده', reject_reason: 'دلیل (به پرداخت‌کننده نشان داده می‌شود)', receipt: 'رسید', no_receipt: 'رسید ندارد',
    deposit: 'واریز', less: 'کمتر از مبلغ', more: 'بیشتر از مبلغ', dup_image: 'تصویر رسید تکراری', dup_ref: 'شماره پیگیری تکراری',
    rounded: 'مبلغ گرد شده', method: 'روش', m_sms_auto: 'پیامک خودکار', m_blu_auto: 'بلو خودکار', m_manual: 'دستی',
    shortfall: 'کسری', settle: 'تسویه مانده قبلی', settle_t: 'صدور فاکتور «تسویه مانده قبلی»',
    settle_msg: 'بدهی فعلی که در فاکتورهای باز نیست، یک بار برای این ادمین فاکتور می‌شود: {a}', settle_done: 'قبلاً صادر شده: {n}',
    unpaid_total: 'جمع پرداخت‌نشده', search: 'جستجوی ادمین / پرداخت‌کننده', ambiguous: 'هم‌مبلغ با سفارش مشتری — بررسی دستی',
    open_admin: 'صفحهٔ ادمین',
  },
  en: {
    inv_h: 'Agency invoices', pay_h: 'Agency payments', none: 'Nothing here.', admin: 'Admin', group: 'Group', amount: 'Amount',
    status: 'Status', date: 'Date', kind: 'Kind', void: 'Void', void_t: 'Void invoice', void_reason: 'Reason',
    void_msg: 'The invoice and its charge (if any) are voided and leave the admin’s balance.',
    st_unpaid: 'Unpaid', st_pending: 'Under review', st_paid: 'Paid', st_voided: 'Voided', all: 'All',
    k_quota_charge: 'Volume', k_manual_charge: 'Charge', k_request: 'Request / group manager', k_settlement: 'Previous balance',
    f_review: 'Waiting for review', f_open: 'Open', p_approved: 'Approved', p_rejected: 'Rejected', p_pending_payment: 'Waiting for transfer',
    p_pending_review: 'Waiting for review', p_expired: 'Expired', p_cancelled: 'Cancelled',
    payer: 'Payer', payer_admin: 'admin', payer_manager: 'group manager', unique: 'Unique amount', invoices: 'Invoices',
    approve: 'Approve', reject: 'Reject', approve_t: 'Approve agency payment', approve_msg: 'The invoices become paid and a payment is recorded in the admin’s account.',
    reject_t: 'Reject agency payment', reject_reason: 'Reason (shown to the payer)', receipt: 'Receipt', no_receipt: 'No receipt',
    deposit: 'Deposit', less: 'less than the amount', more: 'more than the amount', dup_image: 'duplicate receipt image', dup_ref: 'duplicate tracking number',
    rounded: 'rounded amount', method: 'Method', m_sms_auto: 'SMS auto', m_blu_auto: 'Blu auto', m_manual: 'manual',
    shortfall: 'short', settle: 'Previous balance invoice', settle_t: 'Issue the “previous balance” invoice',
    settle_msg: 'The current balance not covered by open invoices becomes one invoice for this admin, once: {a}', settle_done: 'already issued: {n}',
    unpaid_total: 'Total unpaid', search: 'Search admin / payer', ambiguous: 'Same amount as a customer order — review by hand',
    open_admin: 'Admin page',
  },
}
const useT = () => { const { lang } = useI18n(); return [T[lang] || T.fa, lang] }
const N = ({ children }) => <bdi dir="ltr" className="mono-num">{children}</bdi>
const gbt = (v) => Number(v || 0).toLocaleString('en-US', { maximumFractionDigits: 2 })

function InvoiceRows({ rows, s, lang, onVoid, showAdmin = true }) {
  return (
    <div className="ab-tbl-wrap"><table className="ab-tbl">
      <thead><tr><th>#</th>{showAdmin && <th>{s.admin}</th>}<th>{s.kind}</th><th>{s.amount}</th><th>{s.status}</th><th>{s.date}</th><th /></tr></thead>
      <tbody>{rows.map((r) => (
        <tr key={r.id} data-st={r.status}>
          <td data-label="#"><N>{r.number}</N></td>
          {showAdmin && <td data-label={s.admin}><Link to={`/agency/admins/${encodeURIComponent(r.admin)}/accounting`}>{r.admin}</Link>{r.group && <small className="ab-sub">{r.group}</small>}</td>}
          <td data-label={s.kind}>{s['k_' + r.kind]}{r.gb ? <small className="ab-sub"><N>{gbt(r.gb)} GB × {toman(r.price_per_gb, lang)}</N></small> : null}</td>
          <td data-label={s.amount}><N>{toman(r.amount, lang)}</N></td>
          <td data-label={s.status}><span className="ab-pill" data-st={r.status}>{s['st_' + r.status]}</span>{r.void_reason && <small className="ab-sub">{r.void_reason}</small>}</td>
          <td data-label={s.date}><N>{jalali(r.created_at, false, lang)}</N></td>
          <td>{r.status === 'unpaid' && onVoid && <button type="button" className="ab-mini" onClick={() => onVoid(r)}>{s.void}</button>}</td>
        </tr>))}</tbody>
    </table></div>
  )
}

function useVoid(s, done) {
  const confirm = useConfirm()
  return (r) => confirm({
    tone: 'danger', title: s.void_t, targetLabel: '#', targetId: r.number, message: s.void_msg, confirmLabel: s.void,
    reason: { label: s.void_reason, required: true },
    action: async (reason) => { await api.post(`/admin/agency/invoices/${r.id}/void/`, { reason }); done() },
  })
}

export function AgencyInvoicesView({ Header }) {
  const [s, lang] = useT()
  const [f, setF] = useState('unpaid')
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const load = () => api.get('/admin/agency/invoices/', { params: { status: f } }).then((r) => { setD(r.data); setErr('') }).catch((e) => { setErr(apiError(e)); setD({ results: [] }) })
  useEffect(() => { setD(null); load() }, [f])
  const onVoid = useVoid(s, load)
  return (
    <div className="ag space-y-4">
      {Header}
      <style>{GM_CSS + CSS}</style>
      <LedgerSubNav />
      <Alert>{err}</Alert>
      <div className="card ag-card" data-testid="staff-invoices">
        <div className="ab-h"><h3 className="ag-sh" data-ac="blue"><Ic n="doc" size={15} />{s.inv_h}</h3>
          {d && d.unpaid_total != null && <span className="ab-total">{s.unpaid_total}: <N>{toman(d.unpaid_total, lang)}</N></span>}</div>
        <div className="ab-seg">{['unpaid', 'pending', 'paid', 'voided', 'all'].map((k) => (
          <button key={k} type="button" className={'ab-segb' + (f === k ? ' on' : '')} onClick={() => setF(k)}>{k === 'all' ? s.all : s['st_' + k]}</button>))}</div>
        {d === null ? <div className="grid place-items-center py-10"><Spinner /></div>
          : d.results.length === 0 ? <p className="text-sm text-muted">{s.none}</p> : <InvoiceRows rows={d.results} s={s} lang={lang} onVoid={onVoid} />}
      </div>
    </div>
  )
}

function useBlob(url) {
  const [src, setSrc] = useState(null)
  useEffect(() => {
    if (!url) return undefined
    let u = null
    api.get(url.replace(/^\/api\/v1/, ''), { responseType: 'blob' }).then((r) => { u = URL.createObjectURL(r.data); setSrc(u) }).catch(() => setSrc(null))
    return () => { if (u) URL.revokeObjectURL(u) }
  }, [url])
  return src
}

function Receipt({ url, s }) {
  const src = useBlob(url)
  const [big, setBig] = useState(false)
  if (!url) return <span className="ab-sub">{s.no_receipt}</span>
  if (!src) return <Spinner />
  return (
    <>
      <button type="button" className="ab-thumb" onClick={() => setBig(true)} aria-label={s.receipt}><img src={src} alt={s.receipt} /></button>
      {big && <div className="ab-light" onClick={() => setBig(false)} role="dialog" aria-label={s.receipt}><img src={src} alt={s.receipt} /></div>}
    </>
  )
}

export function AgencyPaymentsView({ Header }) {
  const [s, lang] = useT()
  const confirm = useConfirm()
  const { can } = useAuth()
  const { setAgencyReview } = useLiveApprovals()
  const [f, setF] = useState('review')
  const [q, setQ] = useState('')
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const load = () => api.get('/admin/agency/payments/', { params: { status: f, search: q || undefined } })
    .then((r) => { setD(r.data); setErr(''); setAgencyReview?.(r.data.review) }).catch((e) => { setErr(apiError(e)); setD({ results: [], counts: {} }) })
  useEffect(() => { setD(null); load() }, [f])
  usePaymentsEvents((e) => { if (e.event?.startsWith('agency_')) load() })
  const approve = (p) => confirm({ tone: 'success', icon: 'check', title: s.approve_t, targetLabel: '#', targetId: p.number, message: s.approve_msg,
    confirmLabel: s.approve, action: async () => { await api.post(`/admin/agency/payments/${p.id}/approve/`); load() } })
  const reject = (p) => confirm({ tone: 'danger', title: s.reject_t, targetLabel: '#', targetId: p.number, confirmLabel: s.reject,
    reason: { label: s.reject_reason, required: true },
    action: async (reason) => { await api.post(`/admin/agency/payments/${p.id}/reject/`, { reason }); load() } })
  const may = can('agency.payments')
  const counts = d?.counts || {}
  return (
    <div className="ag space-y-4">
      {Header}
      <style>{GM_CSS + CSS}</style>
      <LedgerSubNav />
      <Alert>{err}</Alert>
      <div className="card ag-card" data-testid="agency-payments">
        <div className="ab-h"><h3 className="ag-sh" data-ac="green"><Ic n="money" size={15} />{s.pay_h}</h3></div>
        <div className="ab-seg">
          {[['review', s.f_review, counts.pending_review], ['open', s.f_open], ['approved', s.p_approved, counts.approved], ['rejected', s.p_rejected], ['all', s.all]].map(([k, label, n]) => (
            <button key={k} type="button" className={'ab-segb' + (f === k ? ' on' : '')} onClick={() => setF(k)}>{label}{n ? <span className="ab-n">{n}</span> : null}</button>))}
        </div>
        <form className="ab-search" onSubmit={(e) => { e.preventDefault(); load() }}>
          <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder={s.search} aria-label={s.search} />
        </form>
        {d === null ? <div className="grid place-items-center py-10"><Spinner /></div> : d.results.length === 0 ? <p className="text-sm text-muted">{s.none}</p> : (
          <div className="ab-cards">
            {d.results.map((p) => (
              <article key={p.id} className="ab-pcard" data-st={p.status}>
                <div className="ab-ph"><b><N>{p.number}</N></b><span className="ab-pill" data-st={p.status}>{s['p_' + p.status]}</span></div>
                <dl className="ab-kv">
                  <div><dt>{s.payer}</dt><dd><bdi>{p.payer}</bdi> <small>({p.payer_kind === 'manager' ? s.payer_manager : s.payer_admin})</small></dd></div>
                  <div><dt>{s.unique}</dt><dd><N>{toman(p.amount_unique, lang)}</N>{p.paid_amount != null && <small> · {s.deposit} <N>{toman(p.paid_amount, lang)}</N></small>}</dd></div>
                  <div><dt>{s.date}</dt><dd><N>{jalali(p.created_at, true, lang)}</N></dd></div>
                  {p.method && <div><dt>{s.method}</dt><dd>{s['m_' + p.method] || p.method}{p.auto_rule === 'rounded' && <> · {s.rounded}</>}{p.shortfall && <> · {s.shortfall} <N>{toman(p.shortfall, lang)}</N></>}</dd></div>}
                </dl>
                <ul className="ab-invs">{p.invoices.map((i) => <li key={i.id}><N>{i.number}</N> · <Link to={`/agency/admins/${encodeURIComponent(i.admin)}/accounting`}>{i.admin}</Link>{i.group && <> · {i.group}</>} · <N>{toman(i.amount, lang)}</N></li>)}</ul>
                {(p.warnings || []).map((w, n) => (
                  <p key={n} className="ab-warn">{w.kind === 'amount_mismatch' ? `${s.deposit} ${toman(w.deposit, lang)} — ${s[w.direction] || ''}`
                    : w.kind === 'duplicate_image' ? s.dup_image : w.kind === 'duplicate_ref' ? s.dup_ref : w.kind}</p>
                ))}
                {p.auto_reason?.why_not === 'ambiguous_customer_order' && <p className="ab-warn">{s.ambiguous}</p>}
                {p.reject_reason && <p className="ab-warn">{p.reject_reason}</p>}
                <div className="ab-pfoot">
                  <Receipt url={p.receipt_url} s={s} />
                  {may && ['pending_review', 'pending_payment', 'expired'].includes(p.status) && (
                    <div className="ab-acts">
                      <button type="button" className="ab-ok-btn" onClick={() => approve(p)} data-testid="ap-approve">{s.approve}</button>
                      <button type="button" className="ab-no-btn" onClick={() => reject(p)}>{s.reject}</button>
                    </div>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

/** On the admin's accounting page: its invoices + «تسویه مانده قبلی». */
export function AdminInvoicesCard({ username }) {
  const [s, lang] = useT()
  const confirm = useConfirm()
  const { can } = useAuth()
  const [d, setD] = useState(null)
  const load = () => api.get('/admin/agency/invoices/', { params: { admin: username, status: 'all' } }).then((r) => setD(r.data)).catch(() => setD(false))
  useEffect(() => { load() }, [username])
  const onVoid = useVoid(s, load)
  if (!d) return null
  const st = d.settlement
  const settle = () => confirm({ tone: 'primary', title: s.settle_t, targetLabel: s.admin, targetId: username,
    message: s.settle_msg.replace('{a}', toman(st.amount, lang)), confirmLabel: s.settle,
    action: async () => { await api.post('/admin/agency/invoices/settlement/', { admin: username }); load() } })
  return (
    <div className="card ag-card" data-testid="admin-invoices">
      <style>{CSS}</style>
      <div className="ab-h"><h3 className="ag-sh" data-ac="blue"><Ic n="doc" size={15} />{s.inv_h}</h3>
        <span className="ab-total">{s.unpaid_total}: <N>{toman(d.unpaid_total, lang)}</N></span></div>
      {can('agency.accounting') && st && (st.allowed
        ? <button type="button" className="ag-act" data-tone="primary" onClick={settle} data-testid="settle-btn"><Ic n="money" />{s.settle} · <N>{toman(st.amount, lang)}</N></button>
        : st.existing ? <p className="ab-sub">{s.settle} — {s.settle_done.replace('{n}', st.existing)}</p> : null)}
      {d.results.length === 0 ? <p className="text-sm text-muted mt-2">{s.none}</p> : <InvoiceRows rows={d.results} s={s} lang={lang} onVoid={can('agency.accounting') ? onVoid : null} showAdmin={false} />}
    </div>
  )
}

const CSS = `
.ab-h { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 10px; }
.ab-total { font-size: 13px; font-weight: 700; color: var(--c-danger-fg); }
.ab-seg { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
.ab-segb { min-height: 40px; padding: 0 12px; border-radius: 999px; border: 1px solid var(--c-border); background: transparent; color: var(--c-text); font-size: 13px; font-weight: 700; display: inline-flex; align-items: center; gap: 6px; }
.ab-segb.on { background: var(--c-primary); border-color: var(--c-primary); color: #fff; }
.ab-n { display: inline-grid; place-items: center; min-width: 18px; height: 18px; padding: 0 5px; border-radius: 999px; font-size: 11px; font-weight: 800; color: #fff; background: var(--c-danger); }
.ab-search { margin-bottom: 10px; max-width: 360px; }
.ab-tbl-wrap { overflow-x: auto; }
.ab-tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.ab-tbl th { text-align: start; font-size: 11.5px; color: var(--c-text-muted); font-weight: 700; padding: 8px; border-bottom: 1px solid var(--c-border); white-space: nowrap; }
.ab-tbl td { padding: 9px 8px; border-bottom: 1px solid var(--c-border); vertical-align: top; }
.ab-tbl tr[data-st="voided"] td { opacity: .6; }
.ab-sub { display: block; font-size: 11.5px; color: var(--c-text-muted); margin-top: 2px; }
.ab-pill { font-size: 11.5px; font-weight: 700; padding: 2px 9px; border-radius: 999px; white-space: nowrap; color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 14%, transparent); }
.ab-pill[data-st="paid"], .ab-pill[data-st="approved"] { color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 14%, transparent); }
.ab-pill[data-st="voided"], .ab-pill[data-st="rejected"], .ab-pill[data-st="cancelled"], .ab-pill[data-st="expired"] { color: var(--c-muted-fg); background: color-mix(in srgb, var(--c-text-muted) 14%, transparent); }
.ab-pill[data-st="pending"], .ab-pill[data-st="pending_review"] { color: #fff; background: #0891B2; }
.ab-mini { min-height: 36px; padding: 0 10px; border-radius: 8px; border: 1px solid var(--c-danger); color: var(--c-danger-fg); background: transparent; font-size: 12px; font-weight: 700; }
.ab-cards { display: grid; gap: 10px; grid-template-columns: repeat(auto-fill, minmax(min(100%, 320px), 1fr)); }
.ab-pcard { border: 1px solid var(--c-border); border-radius: 14px; padding: 12px; display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.ab-pcard[data-st="pending_review"] { border-color: color-mix(in srgb, #0891B2 50%, var(--c-border)); }
.ab-ph { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.ab-kv { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; font-size: 12.5px; }
.ab-kv dt { color: var(--c-text-muted); font-size: 11px; font-weight: 700; }
.ab-kv dd { font-weight: 700; overflow-wrap: anywhere; }
.ab-invs { font-size: 12.5px; display: flex; flex-direction: column; gap: 2px; overflow-wrap: anywhere; }
.ab-warn { font-size: 12px; font-weight: 700; color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 12%, transparent); border-radius: 8px; padding: 5px 8px; }
.ab-pfoot { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: 8px; }
.ab-thumb { width: 64px; height: 64px; border-radius: 10px; overflow: hidden; border: 1px solid var(--c-border); padding: 0; background: transparent; }
.ab-thumb img { width: 100%; height: 100%; object-fit: cover; }
.ab-light { position: fixed; inset: 0; z-index: 80; background: rgba(0,0,0,.8); display: grid; place-items: center; padding: 16px; }
.ab-light img { max-width: 100%; max-height: 92vh; border-radius: 10px; }
.ab-acts { display: flex; gap: 6px; }
.ab-ok-btn, .ab-no-btn { min-height: 44px; padding: 0 16px; border-radius: 10px; font-weight: 800; font-size: 13px; border: 0; }
.ab-ok-btn { color: #fff; background: #11AB53; }
.ab-no-btn { color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 12%, transparent); }
@media (max-width: 767px) {
  .ab-tbl thead { display: none; }
  .ab-tbl, .ab-tbl tbody, .ab-tbl tr, .ab-tbl td { display: block; width: 100%; }
  .ab-tbl tr { border: 1px solid var(--c-border); border-radius: 12px; padding: 6px 10px; margin-bottom: 8px; }
  .ab-tbl td { border: 0; padding: 4px 0; display: flex; justify-content: space-between; gap: 10px; }
  .ab-tbl td[data-label]::before { content: attr(data-label); font-size: 11.5px; font-weight: 700; color: var(--c-text-muted); flex-shrink: 0; }
  .ab-tbl td > * { text-align: end; min-width: 0; overflow-wrap: anywhere; }
  .ab-mini { min-height: 44px; }
}
`
