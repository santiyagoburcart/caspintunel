import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali, toman } from '../lib/format'
import { Alert, Spinner } from '../components/ui'
import { ReceiptThumb } from '../components/ReceiptThumb'
import { useToast } from '../components/Toast'
import { useConfirm } from '../components/ConfirmDialog'
import { useLivePayments, usePaymentsEvents } from '../lib/livePayments'
import BluDeposits from '../components/BluDeposits'
import RoundedReason from '../components/RoundedReason'

const T = {
  fa: {
    title: 'صف تأیید پرداخت', none: 'موردی برای بررسی نیست',
    subtitle: 'تراکنش‌های کارت‌به‌کارت و فیش‌های نیازمند تطبیق و تأیید دستی',
    user: 'کاربر', order: 'سفارش', plan: 'پلن', account: 'نام اکانت', receipt: 'رسید',
    no_receipt: 'رسیدی پیوست نشده', reject_reason: 'دلیل رد (برای کاربر نمایش داده می‌شود)',
    reject_title: 'رد پرداخت', reject_btn: 'بله، پرداخت را رد کن', reject_ph: 'مثلاً: مبلغ واریزی با فاکتور مغایرت دارد',
    reject_msg_a: 'پرداخت', reject_msg_b: 'کاربر', reject_msg_c: 'رد می‌شود؛ سفارش در انتظار پرداخت می‌ماند و کاربر می‌تواند رسید جدید ارسال کند.',
    audit: 'این عملیات با نام کاربری شما در گزارش ممیزی ثبت می‌شود.', unspecified: 'نامشخص',
    load_fail: 'دریافت فهرست ناموفق بود', src_site: 'سایت', src_bot: 'ربات',
    deposit_card: 'واریز به کارت', customer_card: 'کارت اعلام‌شده توسط کاربر',
    tab_all: 'همه', tab_receipt: 'دارای فیش', tab_active: 'در انتظار', tab_expired: 'منقضی',
    mm_less: 'مبلغ نامطابق: کمتر از فاکتور', mm_more: 'مبلغ نامطابق: بیشتر از فاکتور', mm_sms: 'پیامک بانک', mm_invoice: 'فاکتور', mm_diff: 'اختلاف', mm_hint: 'خودکار تأیید نشد — پس از بررسی، تأیید یا رد کنید.',
    expired_note: 'مهلت رزرو مبلغ یکتا به پایان رسیده است.',
    none_tab: 'موردی در این دسته نیست',
    live_on: 'به‌روزرسانی زنده', live_off: 'اتصال زنده قطع است — تا وصل شدن دوباره، صف هر 15 ثانیه خودکار به‌روز می‌شود',
    live_short_off: 'آفلاین',
    w_amount: 'مبلغ فیش با مبلغ یکتای سفارش برابر نیست', w_receipt: 'فیش',
    w_recent_sms: 'این مشتری در 24 ساعت اخیر پرداختی دارد که با پیامک بانک / واریز بلو تأیید شده — شاید همین واریز باشد',
    w_dup_image: 'همین تصویر رسید روی تراکنش دیگری هم ثبت شده است',
    w_dup_ref: 'همین شماره سند/پیگیری روی تراکنش دیگری هم ثبت شده است',
    w_renewal: 'این سرویس از قبل یک تمدید پرداخت‌شده در انتظار دارد (سفارش #{id}) — با تأیید، تمدید دوم صف نمی‌شود و سفارش «ناموفق» می‌شود',
    w_same_service: 'همین سرویس', w_voided: 'حذف‌شده', w_open: 'مشاهده',
    w_confirm: 'این پرداخت {n} هشدار دارد — پیش از تأیید، تراکنش‌های مرتبط را بررسی کنید.',
    ri_title: 'اطلاعات فیش (برای بررسی تکراری)', ri_amount: 'مبلغ روی فیش', ri_ref: 'شماره سند / پیگیری',
    ri_rial: 'ریال', ri_toman: 'تومان', ri_save: 'ثبت',
    v_queue: 'صف تأیید', v_blu: 'واریزهای بلو', mm_blu: 'واریز بلو',
  },
  en: {
    title: 'Payment approval queue', none: 'Nothing to review',
    subtitle: 'Card-to-card transactions and receipts that need manual matching and approval',
    user: 'User', order: 'Order', plan: 'Plan', account: 'Account', receipt: 'Receipt',
    no_receipt: 'No receipt attached', reject_reason: 'Rejection reason (shown to the customer)',
    reject_title: 'Reject payment', reject_btn: 'Yes, reject payment', reject_ph: 'e.g. the transferred amount does not match the invoice',
    reject_msg_a: 'The payment of', reject_msg_b: 'by', reject_msg_c: 'will be rejected; the order stays awaiting payment and the customer can upload a new receipt.',
    audit: 'This action is recorded under your username in the audit log.', unspecified: 'unspecified',
    load_fail: 'Failed to load the queue', src_site: 'Website', src_bot: 'Bot',
    deposit_card: 'Deposited to card', customer_card: 'Card the customer selected',
    tab_all: 'All', tab_receipt: 'Has receipt', tab_active: 'Waiting', tab_expired: 'Expired',
    mm_less: 'Amount mismatch: LESS than the invoice', mm_more: 'Amount mismatch: MORE than the invoice', mm_sms: 'Bank SMS', mm_invoice: 'Invoice', mm_diff: 'Difference', mm_hint: 'Not auto-approved — check, then approve or reject.',
    expired_note: 'The unique-amount reservation window has elapsed.',
    none_tab: 'Nothing in this tab',
    live_on: 'Live updates', live_off: 'Live connection lost — the queue auto-refreshes every 15 s until it reconnects',
    live_short_off: 'Offline',
    w_amount: "The receipt amount doesn't equal the order's unique amount", w_receipt: 'Receipt',
    w_recent_sms: 'This customer had a payment approved by bank SMS / Blu in the last 24 h — it may be the same transfer',
    w_dup_image: 'The same receipt image is on another transaction',
    w_dup_ref: 'The same bank document / tracking number is on another transaction',
    w_renewal: 'This service already has a paid renewal waiting (order #{id}) — approving will NOT queue a second one; the order becomes "failed"',
    w_same_service: 'same service', w_voided: 'deleted', w_open: 'Open',
    w_confirm: 'This payment has {n} warning(s) — check the linked transactions before approving.',
    ri_title: 'Receipt details (duplicate check)', ri_amount: 'Amount on receipt', ri_ref: 'Document / tracking no.',
    ri_rial: 'Rial', ri_toman: 'Toman', ri_save: 'Save',
    v_queue: 'Approval queue', v_blu: 'Blu deposits', mm_blu: 'Blu deposit',
  },
}

const TABS = ['all', 'receipt', 'active', 'expired']
const VIEWS = ['queue', 'blu']

/* Approval queue | Blu deposits (?view=blu keeps the choice on reload / back). */
export default function Payments() {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const [sp, setSp] = useSearchParams()
  const view = sp.get('view') === 'blu' ? 'blu' : 'queue'
  return (
    <div className="space-y-3">
      <style>{CSS}</style>
      <div className="pq-views" role="tablist">
        {VIEWS.map((v) => (
          <button key={v} type="button" role="tab" aria-selected={view === v}
            className={'pq-view' + (view === v ? ' on' : '')}
            onClick={() => setSp(v === 'queue' ? {} : { view: v }, { replace: true })}>
            {s['v_' + v]}
          </button>
        ))}
      </div>
      {view === 'blu' ? <BluDeposits /> : <PaymentQueue />}
    </div>
  )
}

function PaymentQueue() {
  const { t, lang } = useI18n()
  const toast = useToast()
  const confirm = useConfirm()
  const navigate = useNavigate()
  const s = T[lang] || T.fa
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  const [busyId, setBusyId] = useState(null)
  const [cards, setCards] = useState([])
  const [cardById, setCardById] = useState({})
  const [tab, setTab] = useState('all')
  const [resMin, setResMin] = useState(30)

  const { connected, refreshCount } = useLivePayments()
  const knownIds = useRef(null)          // ids already on screen — to flash newcomers
  const [freshIds, setFreshIds] = useState(() => new Set())
  const reloadTimer = useRef(null)

  const load = () =>
    api.get('/admin/payments/pending/')
      .then((r) => {
        const list = r.data.results
        if (knownIds.current) {
          const fresh = list.filter((p) => !knownIds.current.has(p.id)).map((p) => p.id)
          if (fresh.length) {
            setFreshIds(new Set(fresh))
            setTimeout(() => setFreshIds(new Set()), 4000)
          }
        }
        knownIds.current = new Set(list.map((p) => p.id))
        setRows(list); setErr('')
      })
      .catch(() => { setRows((cur) => cur || []); setErr(s.load_fail) })

  // live: refetch on any queue change (debounced — several events can arrive together)
  usePaymentsEvents(() => {
    clearTimeout(reloadTimer.current)
    reloadTimer.current = setTimeout(load, 250)
  })
  useEffect(() => () => clearTimeout(reloadTimer.current), [])
  // fallback only while the live socket is down: poll quietly, never a manual button
  useEffect(() => {
    if (connected) return undefined
    const id = setInterval(() => { load(); refreshCount() }, 15000)
    return () => clearInterval(id)
  }, [connected])

  useEffect(() => {
    load()
    api.get('/admin/cards/')
      .then((r) => setCards((r.data.results || r.data || []).filter((c) => c.is_active)))
      .catch(() => setCards([]))
    api.get('/admin/settings/')
      .then((r) => {
        const v = r.data.settings.find((x) => x.key === 'unique_amount_reservation_minutes')?.value
        if (v) setResMin(Number(v))
      }).catch(() => {})
  }, [])

  const isExpired = (p) => {
    const t = new Date(p.created_at).getTime() + resMin * 60000
    return Date.now() > t
  }
  const match = (p, tb) => {
    if (tb === 'receipt') return !!p.receipt_url
    if (tb === 'expired') return isExpired(p)
    if (tb === 'active') return !isExpired(p)
    return true
  }
  const counts = Object.fromEntries(TABS.map((tb) => [tb, (rows || []).filter((p) => match(p, tb)).length]))
  const shown = (rows || []).filter((p) => match(p, tab))

  const act = async (id, kind) => {
    setErr('')
    if (kind === 'reject') {
      const p = rows.find((r) => r.id === id)
      // the reason is shown to the customer (site + bot), so ask for it in the shared dialog
      const ok = await confirm({
        tone: 'danger', icon: 'ban', badge: 'payment.approve',
        title: s.reject_title, targetLabel: s.order, targetId: `#${p?.order_id ?? id}`,
        message: <>{s.reject_msg_a} <strong>{toman(p?.amount, lang)}</strong> {s.reject_msg_b} <strong>{p?.user}</strong> {s.reject_msg_c}</>,
        reason: { label: s.reject_reason, placeholder: s.reject_ph },
        confirmLabel: s.reject_btn, footnote: s.audit,
        action: (reason) => api.post(`/admin/payments/${id}/reject/`, { reason: reason || s.unspecified }),
      })
      if (ok) { toast.success(t('reject')); await load() }
      return
    }
    const p = rows.find((r) => r.id === id)
    const body = { bank_card: cardById[id] ?? p?.bank_card ?? cards[0]?.id ?? null }
    // approving delivers the service — say so in the shared dialog first
    setBusyId(id)
    try {
      const nw = p?.warnings?.length || 0
      const ok = await confirm({
        tone: nw ? 'warning' : 'success', icon: 'check', badge: 'payment.approve',
        title: t('approve_deliver_title'),
        message: nw ? <>{t('approve_deliver_msg')}<br /><b>{s.w_confirm.replace('{n}', nw)}</b></> : t('approve_deliver_msg'),
        targetLabel: s.order, targetId: `#${p?.order_id ?? id}`,
        confirmLabel: t('approve_deliver_btn'), footnote: s.audit,
        action: () => api.post(`/admin/payments/${id}/${kind}/`, body),
      })
      if (ok) { toast.success(t('approve')); await load() }
    } catch (e) { toast.error(apiError(e)); setErr(apiError(e)) } finally { setBusyId(null) }
  }

  if (rows === null) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="space-y-3">
      <div className="pq-head flex flex-wrap items-start justify-between gap-2">
        <div>
          <h1 className="text-lg font-bold">{s.title}</h1>
          <p className="text-sm text-muted mt-1">{s.subtitle}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className={'pq-live' + (connected ? ' on' : '')} title={connected ? s.live_on : s.live_off}>
            <i />{connected ? s.live_on : s.live_short_off}
          </span>
        </div>
      </div>
      <Alert>{err}</Alert>

      {rows.length > 0 && (
        <div className="pq-tabs">
          {TABS.map((tb) => (
            <button key={tb} type="button" onClick={() => setTab(tb)}
              className={'pq-tab' + (tab === tb ? ' on' : '')}>
              {s['tab_' + tb]}
              <span className="pq-tab-n">{counts[tb]}</span>
            </button>
          ))}
        </div>
      )}

      {rows.length === 0 && !err && (
        <div className="card text-center text-muted">{s.none}</div>
      )}
      {rows.length > 0 && shown.length === 0 && (
        <div className="card text-center text-muted">{s.none_tab}</div>
      )}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {shown.map((p) => (
          <div key={p.id} className={'card space-y-2' + (isExpired(p) ? ' pq-card--exp' : '') + (freshIds.has(p.id) ? ' pq-card--new' : '')}>
            <div className="flex items-center justify-between gap-2">
              <span className="font-bold">{toman(p.amount, lang)}</span>
              <div className="flex items-center gap-1.5">
                {isExpired(p) && <span className="pq-exp-tag">{s.tab_expired}</span>}
                <span className="rounded-full px-2 py-0.5 text-xs"
                  style={{ background: 'color-mix(in srgb, var(--c-secondary) 18%, transparent)', color: 'var(--c-secondary)' }}>
                  {p.order_source === 'bot' ? s.src_bot : s.src_site}
                </span>
              </div>
            </div>
            <div className="pq-main">
              <div className="pq-info space-y-0.5 text-sm text-muted">
                <div>{s.user}: {p.user}{p.user_telegram ? ` (@${p.user_telegram})` : ''}</div>
                <div>{s.order} #{p.order_id} · {s.plan}: {p.plan_name || '—'}{p.account_name ? ` · ${s.account}: ${p.account_name}` : ''}</div>
                <div className="text-xs">{jalali(p.created_at, true, lang)}</div>
              </div>
              <div className="pq-rcpt">
                {p.receipt_url
                  ? <ReceiptThumb url={p.receipt_url} alt={s.receipt} variant="full" />
                  : <div className="text-xs text-muted">{s.no_receipt}</div>}
              </div>
            </div>
            {isExpired(p) && <div className="pq-exp-note">{s.expired_note}</div>}
            {p.sms_mismatch && (
              <div className="pq-mm" data-kind={p.sms_mismatch.kind} role="status">
                <b>{p.sms_mismatch.kind === 'less' ? s.mm_less : s.mm_more}</b>
                <span>{p.sms_mismatch.source === 'blu' ? s.mm_blu : s.mm_sms}: <bdi dir="ltr" className="mono-num">{p.sms_mismatch.sms_amount != null ? toman(p.sms_mismatch.sms_amount, lang) : `${Number(p.sms_mismatch.sms_raw || 0).toLocaleString('en-US')} ${p.sms_mismatch.sms_unit}`}</bdi>
                  {' · '}{s.mm_invoice}: <bdi dir="ltr" className="mono-num">{toman(p.sms_mismatch.invoice_amount, lang)}</bdi>
                  {p.sms_mismatch.sms_amount != null && <>{' · '}{s.mm_diff}: <bdi dir="ltr" className="mono-num">{(Number(p.sms_mismatch.sms_amount) - Number(p.sms_mismatch.invoice_amount) > 0 ? '+' : '') + toman(Number(p.sms_mismatch.sms_amount) - Number(p.sms_mismatch.invoice_amount), lang)}</bdi></>}
                </span>
                <small>{s.mm_hint}</small>
              </div>
            )}
            {p.auto_reason?.rule === 'rounded' && <RoundedReason r={p.auto_reason} compact />}
            {p.warnings?.length > 0 && <PayWarnings ws={p.warnings} s={s} lang={lang} onOpen={(pid) => navigate(`/payments/${pid}`)} />}
            <ReceiptInfo p={p} s={s} onSaved={(row) => setRows((cur) => cur.map((r) => (r.id === row.id ? row : r)))} />
            {p.bank_card_number && (
              <div className="pq-customer-card">
                {s.customer_card}: <b className="mono-num" dir="ltr">{p.bank_card_number}</b>
                {(p.bank_card_bank || p.bank_card_holder) &&
                  ` — ${[p.bank_card_bank, p.bank_card_holder].filter(Boolean).join(' · ')}`}
              </div>
            )}
            {cards.length > 0 && (
              <label className="pq-deposit-l block text-xs text-muted" aria-label={s.deposit_card}>
                {s.deposit_card}
                <select className="input mt-0.5 text-sm"
                  value={cardById[p.id] ?? p.bank_card ?? cards[0]?.id ?? ''}
                  onChange={(e) => setCardById((m) => ({ ...m, [p.id]: Number(e.target.value) }))}>
                  {cards.map((c) => (
                    <option key={c.id} value={c.id}>{c.card_number}{c.holder_name ? ` — ${c.holder_name}` : ''}</option>
                  ))}
                </select>
              </label>
            )}
            <div className="pq-acts flex flex-wrap gap-2 pt-1">
              <button className="btn-primary text-sm" disabled={busyId === p.id}
                onClick={() => act(p.id, 'approve')}>
                {busyId === p.id ? '…' : t('approve')}
              </button>
              <button className="btn-ghost text-sm" disabled={busyId === p.id}
                onClick={() => act(p.id, 'reject')}>
                {t('reject')}
              </button>
              <button type="button" className="btn-ghost text-sm ms-auto inline-flex items-center gap-1.5"
                style={{ color: 'var(--c-primary)', borderColor: 'color-mix(in srgb, var(--c-primary) 32%, transparent)' }}
                onClick={() => navigate(`/payments/${p.id}`)}>
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor"
                  strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
                {t('txd_details')}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/* Duplicate / mismatch hints (backend payments_sms/checks.py), each with its linked payments. */
function PayWarnings({ ws, s, lang, onOpen }) {
  const title = (w) => ({
    amount_mismatch: s.w_amount, recent_sms: s.w_recent_sms, duplicate_image: s.w_dup_image,
    duplicate_ref: s.w_dup_ref, renewal_waiting: s.w_renewal.replace('{id}', w.order_id),
  }[w.kind] || w.kind)
  return (
    <div className="pq-warns" data-testid="pay-warnings">
      {ws.map((w) => (
        <div key={w.kind} className="pq-warn" data-kind={w.kind} role="alert">
          <b>⚠ {title(w)}</b>
          {w.kind === 'amount_mismatch' && (
            <span>{s.w_receipt}: <bdi dir="ltr" className="mono-num">{toman(w.receipt_amount, lang)}</bdi>
              {' · '}{s.mm_invoice}: <bdi dir="ltr" className="mono-num">{toman(w.invoice_amount, lang)}</bdi>
              {' · '}{s.mm_diff}: <bdi dir="ltr" className="mono-num">{(Number(w.diff) > 0 ? '+' : '') + toman(w.diff, lang)}</bdi></span>
          )}
          {w.kind === 'duplicate_ref' && <span className="mono-num" dir="ltr">{w.ref}</span>}
          {(w.payments || []).map((x) => (
            <button key={x.id} type="button" className="pq-warn-link" onClick={() => onOpen(x.id)}>
              <span className="mono-num" dir="ltr">{x.tx}</span>
              <span>{s.order} #{x.order_id}</span>
              <bdi dir="ltr" className="mono-num">{toman(x.amount, lang)}</bdi>
              <span>{jalali(x.confirmed_at || x.created_at, true, lang)}</span>
              {x.same_service && <em>{s.w_same_service}</em>}
              {x.voided && <em className="pq-warn-void">{s.w_voided}</em>}
              <span className="pq-warn-open">{s.w_open} ›</span>
            </button>
          ))}
        </div>
      ))}
    </div>
  )
}

/* What the receipt says, typed by staff — feeds the amount / document-number checks. */
function ReceiptInfo({ p, s, onSaved }) {
  const [amount, setAmount] = useState(p.receipt_amount != null ? String(p.receipt_amount) : '')
  const [unit, setUnit] = useState(p.receipt_amount != null ? 'toman' : 'rial')
  const [ref, setRef] = useState(p.receipt_ref || '')
  const [busy, setBusy] = useState(false)
  const save = async () => {
    setBusy(true)
    try {
      const { data } = await api.post(`/admin/payments/${p.id}/receipt-info/`, { receipt_amount: amount, unit, receipt_ref: ref })
      onSaved(data)
    } catch { /* the toast (FeedbackBridge) shows the reason */ } finally { setBusy(false) }
  }
  return (
    <div className="pq-ri" data-testid="receipt-info">
      <div className="pq-ri-t">{s.ri_title}</div>
      <div className="pq-ri-row">
        <input className="input" dir="ltr" inputMode="numeric" aria-label={s.ri_amount} placeholder={s.ri_amount}
          value={amount} onChange={(e) => setAmount(e.target.value)} />
        <select className="input" aria-label={s.ri_amount} value={unit} onChange={(e) => setUnit(e.target.value)}>
          <option value="rial">{s.ri_rial}</option><option value="toman">{s.ri_toman}</option>
        </select>
        <input className="input" dir="ltr" inputMode="numeric" aria-label={s.ri_ref} placeholder={s.ri_ref}
          value={ref} onChange={(e) => setRef(e.target.value)} />
        <button type="button" className="btn-ghost text-sm" disabled={busy} onClick={save}>{busy ? '…' : s.ri_save}</button>
      </div>
    </div>
  )
}

const CSS = `
.pq-views { display: inline-flex; gap: 2px; padding: 3px; border-radius: 12px; border: 1px solid var(--c-border); background: var(--c-surface); }
.pq-view { padding: 7px 16px; border-radius: 9px; font-size: 13.5px; font-weight: 700; color: var(--c-text-muted); }
.pq-view.on { background: color-mix(in srgb, var(--c-primary) 14%, transparent); color: var(--c-primary-fg); }
@media (max-width: 767px) {
  .pq-views { display: flex; width: 100%; }
  .pq-view { flex: 1 1 0; min-height: 44px; }
}
.pq-warns { display: flex; flex-direction: column; gap: 6px; }
.pq-warn { display: flex; flex-direction: column; gap: 4px; padding: 8px 12px; border-radius: 10px; font-size: 12.5px; line-height: 1.6;
  color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 12%, transparent); border: 1px solid color-mix(in srgb, var(--c-warning) 34%, transparent); }
.pq-warn[data-kind="duplicate_image"], .pq-warn[data-kind="duplicate_ref"], .pq-warn[data-kind="renewal_waiting"] {
  color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 10%, transparent); border-color: color-mix(in srgb, var(--c-danger) 30%, transparent); }
.pq-warn > span { color: var(--c-text); }
.pq-warn-link { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; text-align: start; padding: 6px 10px; border-radius: 8px;
  min-height: 36px; font-size: 12px; color: var(--c-text); background: color-mix(in srgb, var(--c-bg) 70%, transparent); border: 1px solid var(--c-border); }
.pq-warn-link em { font-style: normal; font-size: 10.5px; font-weight: 700; padding: 1px 7px; border-radius: 999px;
  background: color-mix(in srgb, var(--c-primary) 14%, transparent); color: var(--c-primary-fg); }
.pq-warn-link em.pq-warn-void { background: color-mix(in srgb, var(--c-text-muted) 16%, transparent); color: var(--c-muted-fg); }
.pq-warn-open { margin-inline-start: auto; color: var(--c-primary); font-weight: 600; }
.pq-ri { display: flex; flex-direction: column; gap: 4px; }
.pq-ri-t { font-size: 11.5px; color: var(--c-text-muted); }
.pq-ri-row { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(0, .8fr) minmax(0, 1.5fr) auto; gap: 6px; align-items: center; }
.pq-ri-row .input { font-size: 13px; padding-block: 6px; min-width: 0; }
@media (max-width: 767px) {
  .pq-ri-row { grid-template-columns: minmax(0, 1fr) 84px; }
  .pq-ri-row .input { font-size: 16px; min-height: 44px; }
  .pq-ri-row > :nth-child(3) { grid-column: 1 / 2; }
  .pq-ri-row > button { min-height: 44px; }
  .pq-warn-link { min-height: 44px; }
}
.pq-live { display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px; font-weight: 600; color: var(--c-warning);
  padding: 4px 10px; border-radius: 999px; background: color-mix(in srgb, var(--c-warning) 12%, transparent); }
.pq-live i { width: 7px; height: 7px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
.pq-live.on { color: var(--c-success); background: color-mix(in srgb, var(--c-success) 12%, transparent); }
.pq-live.on i { animation: pq-blink 1.6s ease-in-out infinite; }
@keyframes pq-blink { 50% { opacity: .3; } }
.pq-card--new { animation: pq-new 4s ease-out; }
@keyframes pq-new { 0%, 40% { box-shadow: 0 0 0 2px var(--c-success); } 100% { box-shadow: none; } }
.pq-tabs { display: flex; flex-wrap: wrap; gap: 4px; padding: 4px; border-radius: 12px; background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); }
.pq-tab { display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px; border-radius: 9px; font-size: 13px; font-weight: 600; color: var(--c-text-muted); }
.pq-tab.on { background: var(--c-primary); color: #fff; }
.pq-tab-n { font-size: 11px; font-weight: 700; padding: 0 6px; min-width: 18px; text-align: center; border-radius: 999px;
  background: color-mix(in srgb, currentColor 22%, transparent); font-family: 'JetBrains Mono', monospace; }
.pq-card--exp { border-color: color-mix(in srgb, var(--c-warning) 40%, var(--c-border)); }
.pq-mm { display: flex; flex-direction: column; gap: 2px; padding: 8px 12px; border-radius: 10px; font-size: 12.5px; line-height: 1.7;
  color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 10%, transparent); border: 1px solid color-mix(in srgb, var(--c-danger) 30%, transparent); }
.pq-mm[data-kind="more"] { color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 12%, transparent); border-color: color-mix(in srgb, var(--c-warning) 34%, transparent); }
.pq-mm span { color: var(--c-text); } .pq-mm small { color: var(--c-muted-fg); font-size: 11.5px; }
.pq-exp-tag { font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 999px; white-space: nowrap;
  background: color-mix(in srgb, var(--c-warning) 16%, transparent); color: var(--c-warning-fg); }
.pq-exp-note { font-size: 11.5px; color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 10%, transparent);
  border-radius: 8px; padding: 6px 10px; }
.pq-customer-card { font-size: 11.5px; color: var(--c-text-muted); background: color-mix(in srgb, var(--c-primary) 7%, transparent);
  border-radius: 8px; padding: 6px 10px; }
.pq-customer-card b { color: var(--c-text); }
.pq-main { display: flex; flex-direction: column; gap: 8px; }
/* tab counters readable on the filled and the plain tab */
.pq-tab.on .pq-tab-n { background: rgba(0, 0, 0, .22) !important; color: #fff; }
.pq-tab:not(.on) .pq-tab-n { background: color-mix(in srgb, var(--c-text-muted) 12%, transparent) !important; color: var(--c-text); }
/* phones: details beside a receipt thumbnail (tap opens it full size) */
@media (max-width: 767px) {
  .pq-tabs { flex-wrap: nowrap; overflow-x: auto; scrollbar-width: none; }
  .pq-tab { flex: 1 0 auto; justify-content: center; min-height: 44px; padding: 0 12px; }
  .pq-main { display: grid; grid-template-columns: minmax(0, 1fr) 92px; align-items: start; gap: 10px; }
  .pq-info { font-size: 13px; line-height: 1.55; overflow-wrap: anywhere; }
  .pq-rcpt img { width: 92px; height: 116px; max-height: none; object-fit: cover; }
  .pq-rcpt > span { height: 116px; }
  .pq-customer-card { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .pq-exp-note { padding: 5px 10px; }
  .pq-acts { flex-wrap: nowrap; }
  .pq-acts > button { flex: 1 1 0; min-width: 0; min-height: 44px; padding-inline: 10px; }
  .pq-acts > button:last-child { flex: 0 0 auto; margin-inline-start: 0 !important; }
}
@media (max-width: 767px) {
  .pq-head { flex-wrap: nowrap !important; align-items: center !important; }
  .pq-exp-note { display: none; }               /* the "expired" tag already says it */
  .pq-rcpt img { width: 76px !important; height: 96px !important; }
  .pq-rcpt > span { height: 96px !important; }
  .pq-main { grid-template-columns: minmax(0, 1fr) 76px !important; }
  .pq-deposit-l { font-size: 0 !important; }   /* the select shows the card itself */
}
`

