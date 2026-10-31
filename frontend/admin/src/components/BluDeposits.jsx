import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { jalali, toman } from '../lib/format'
import { Alert, Spinner } from './ui'
import { useConfirm } from './ConfirmDialog'
import { usePaymentsEvents } from '../lib/livePayments'

// Blu Bank deposits pushed by the Iran-side collector (backend payments_sms/blu.py).
const T = {
  fa: {
    health_on: 'جمع‌کننده متصل است', health_off: 'جمع‌کننده آفلاین است', health_never: 'هنوز دسته‌ای از جمع‌کننده نرسیده',
    health_disabled: 'وب‌هوک بلو پیکربندی نشده (BLU_PUSH_SECRET)', last_batch: 'آخرین دسته',
    offline_hint: 'بیش از {m} دقیقه خبری نیست — تأیید خودکار بلو متوقف است؛ پیامک آیفون همچنان کار می‌کند.',
    f_all: 'همه', f_unmatched: 'تطبیق‌نشده', f_matched: 'تأییدشده', f_duplicate: 'تکراری', f_ignored: 'نادیده',
    st_unmatched: 'تطبیق‌نشده', st_matched: 'تأییدشده', st_duplicate: 'تکراری', st_ignored: 'نادیده',
    payer: 'واریزکننده', card: 'کارت', receipt: 'شماره پیگیری', reference: 'شماره مرجع', order: 'سفارش',
    open_tx: 'مشاهدهٔ تراکنش', none: 'واریزی ثبت نشده است', none_f: 'موردی در این دسته نیست',
    attach: 'اتصال به سفارش', order_ph: 'شماره سفارش', load_fail: 'دریافت واریزهای بلو ناموفق بود',
    a_title: 'اتصال واریز به سفارش', a_btn: 'بله، تأیید و تحویل سرویس',
    a_msg: 'واریز {amount} به سفارش #{id} وصل می‌شود؛ پرداخت تأیید و سرویس تحویل داده می‌شود.',
    a_audit: 'این عملیات با نام کاربری شما در گزارش ممیزی ثبت می‌شود.',
  },
  en: {
    health_on: 'Collector connected', health_off: 'Collector offline', health_never: 'No batch from the collector yet',
    health_disabled: 'Blu webhook is not configured (BLU_PUSH_SECRET)', last_batch: 'Last batch',
    offline_hint: 'Silent for more than {m} min — Blu auto-confirm is paused; the iPhone SMS still works.',
    f_all: 'All', f_unmatched: 'Unmatched', f_matched: 'Approved', f_duplicate: 'Duplicate', f_ignored: 'Ignored',
    st_unmatched: 'Unmatched', st_matched: 'Approved', st_duplicate: 'Duplicate', st_ignored: 'Ignored',
    payer: 'Payer', card: 'Card', receipt: 'Tracking no.', reference: 'Reference no.', order: 'Order',
    open_tx: 'Open transaction', none: 'No deposits yet', none_f: 'Nothing in this filter',
    attach: 'Attach to order', order_ph: 'Order number', load_fail: 'Failed to load Blu deposits',
    a_title: 'Attach deposit to order', a_btn: 'Yes, approve and deliver',
    a_msg: 'The {amount} deposit will be attached to order #{id}; the payment is approved and the service delivered.',
    a_audit: 'This action is recorded under your username in the audit log.',
  },
}

const FILTERS = ['all', 'unmatched', 'matched', 'duplicate', 'ignored']
const TONE = { unmatched: 'warning', matched: 'success', duplicate: 'muted', ignored: 'muted' }

export default function BluDeposits() {
  const { lang } = useI18n()
  const { can } = useAuth()
  const s = T[lang] || T.fa
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [filter, setFilter] = useState('all')
  const timer = useRef(null)

  const load = () =>
    api.get('/admin/payments/blu-transactions/', { params: filter === 'all' ? {} : { status: filter } })
      .then((r) => { setData(r.data); setErr('') })
      .catch(() => { setData((cur) => cur || { results: [], counts: {}, collector: null }); setErr(s.load_fail) })

  useEffect(() => { load() }, [filter])
  // new deposits / approvals arrive over the payments socket; also refresh the health line every minute
  usePaymentsEvents(() => { clearTimeout(timer.current); timer.current = setTimeout(load, 300) })
  useEffect(() => {
    const id = setInterval(load, 60000)
    return () => { clearInterval(id); clearTimeout(timer.current) }
  }, [filter])

  if (data === null) return <div className="grid place-items-center py-16"><Spinner /></div>
  const counts = data.counts || {}
  const total = Object.values(counts).reduce((a, b) => a + b, 0)

  return (
    <div className="space-y-3">
      <style>{CSS}</style>
      <Health c={data.collector} s={s} lang={lang} />
      <Alert>{err}</Alert>
      <div className="pq-tabs">
        {FILTERS.map((f) => (
          <button key={f} type="button" onClick={() => setFilter(f)} className={'pq-tab' + (filter === f ? ' on' : '')}>
            {s['f_' + f]}
            <span className="pq-tab-n">{f === 'all' ? total : counts[f] || 0}</span>
          </button>
        ))}
      </div>
      {data.results.length === 0 && !err && (
        <div className="card text-center text-muted">{total ? s.none_f : s.none}</div>
      )}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {data.results.map((tx) => (
          <Deposit key={tx.id} tx={tx} s={s} lang={lang} canAttach={can('payment.approve')} onDone={load} />
        ))}
      </div>
    </div>
  )
}

function Health({ c, s, lang }) {
  if (!c) return null
  const state = !c.enabled ? 'disabled' : c.connected ? 'on' : c.last_batch_at ? 'off' : 'never'
  const label = { disabled: s.health_disabled, on: s.health_on, off: s.health_off, never: s.health_never }[state]
  return (
    <div className="blu-health card" data-state={state} role="status">
      <span className="blu-dot" />
      <div className="min-w-0">
        <b>{label}</b>
        {c.last_batch_at && (
          <div className="text-xs text-muted">{s.last_batch}: {jalali(c.last_batch_at, true, lang)}</div>
        )}
        {state === 'off' && <div className="blu-hint">{s.offline_hint.replace('{m}', c.stale_minutes)}</div>}
      </div>
    </div>
  )
}

function Deposit({ tx, s, lang, canAttach, onDone }) {
  const confirm = useConfirm()
  const navigate = useNavigate()
  const [orderId, setOrderId] = useState(tx.matched_order ? String(tx.matched_order) : '')
  const tone = TONE[tx.status] || 'muted'

  const attach = async () => {
    const id = orderId.replace(/\D/g, '')
    if (!id) return
    const ok = await confirm({
      tone: 'success', icon: 'check', badge: 'payment.approve',
      title: s.a_title, targetLabel: s.order, targetId: `#${id}`,
      message: s.a_msg.replace('{amount}', toman(tx.amount_toman, lang)).replace('{id}', id),
      confirmLabel: s.a_btn, footnote: s.a_audit,
      action: () => api.post(`/admin/payments/blu-transactions/${tx.id}/attach/`, { order_id: Number(id) }),
    })
    if (ok) onDone()
  }

  return (
    <div className={'card space-y-2 blu-card' + (tx.status === 'unmatched' ? ' blu-card--open' : '')} data-status={tx.status}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-bold">
          {tx.amount_toman != null ? toman(tx.amount_toman, lang)
            : <bdi dir="ltr" className="mono-num">{Number(tx.amount_irr).toLocaleString('en-US')} {lang === 'en' ? 'IRR' : 'ریال'}</bdi>}
        </span>
        <span className={`blu-pill blu-pill--${tone}`}>{s['st_' + tx.status] || tx.status}</span>
      </div>
      <div className="blu-grid text-sm">
        <span className="text-muted">{jalali(tx.occurred_at, true, lang)}</span>
        {tx.payer_name && <span>{s.payer}: {tx.payer_name}</span>}
        {tx.payer_card && <span>{s.card}: <bdi dir="ltr" className="mono-num">{tx.payer_card}</bdi></span>}
        {tx.receipt && <span>{s.receipt}: <bdi dir="ltr" className="mono-num">{tx.receipt}</bdi></span>}
        {tx.reference && <span>{s.reference}: <bdi dir="ltr" className="mono-num">{tx.reference}</bdi></span>}
        {tx.matched_order && <span>{s.order} #{tx.matched_order}</span>}
      </div>
      {tx.match_note && <div className="blu-note" dir="ltr">{tx.match_note}</div>}
      {tx.status === 'unmatched' && canAttach && (
        <div className="blu-attach">
          <input className="input" dir="ltr" inputMode="numeric" aria-label={s.order_ph} placeholder={s.order_ph}
            value={orderId} onChange={(e) => setOrderId(e.target.value)} />
          <button type="button" className="btn-primary text-sm" disabled={!orderId.replace(/\D/g, '')} onClick={attach}>
            {s.attach}
          </button>
        </div>
      )}
      {tx.matched_payment && (
        <button type="button" className="btn-ghost text-sm blu-open" onClick={() => navigate(`/payments/${tx.matched_payment}`)}>
          {s.open_tx} ›
        </button>
      )}
    </div>
  )
}

const CSS = `
.blu-health { display: flex; align-items: flex-start; gap: 10px; padding: 12px 14px; }
.blu-dot { width: 10px; height: 10px; border-radius: 50%; margin-top: 6px; flex-shrink: 0; background: var(--c-text-muted); }
.blu-health[data-state="on"] .blu-dot { background: var(--c-success); animation: pq-blink 1.6s ease-in-out infinite; }
.blu-health[data-state="off"] { border-color: color-mix(in srgb, var(--c-danger) 40%, var(--c-border)); }
.blu-health[data-state="off"] .blu-dot { background: var(--c-danger); }
.blu-health[data-state="off"] b { color: var(--c-danger-fg); }
.blu-health[data-state="disabled"] .blu-dot, .blu-health[data-state="never"] .blu-dot { background: var(--c-warning); }
.blu-hint { font-size: 12px; margin-top: 2px; color: var(--c-danger-fg); }
.blu-card--open { border-color: color-mix(in srgb, var(--c-warning) 55%, var(--c-border));
  background: linear-gradient(color-mix(in srgb, var(--c-warning) 7%, transparent), color-mix(in srgb, var(--c-warning) 7%, transparent)), var(--c-surface); }
.blu-pill { font-size: 11px; font-weight: 700; padding: 2px 9px; border-radius: 999px; white-space: nowrap; }
.blu-pill--warning { color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 16%, transparent); }
.blu-pill--success { color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 16%, transparent); }
.blu-pill--muted { color: var(--c-muted-fg); background: color-mix(in srgb, var(--c-text-muted) 16%, transparent); }
.blu-grid { display: flex; flex-direction: column; gap: 2px; overflow-wrap: anywhere; }
.blu-note { font-size: 11.5px; color: var(--c-muted-fg); background: color-mix(in srgb, var(--c-text-muted) 8%, transparent);
  border-radius: 8px; padding: 6px 10px; text-align: start; overflow-wrap: anywhere; }
.blu-attach { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 6px; align-items: center; }
.blu-attach .input { font-size: 13px; padding-block: 6px; min-width: 0; }
.blu-open { color: var(--c-primary); }
@media (max-width: 767px) {
  .blu-attach .input { font-size: 16px; min-height: 44px; }
  .blu-attach button, .blu-open { min-height: 44px; }
  .blu-open { width: 100%; }
}
`
