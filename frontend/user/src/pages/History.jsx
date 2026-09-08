import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { useI18n, label } from '../lib/i18n'
import { useTheme } from '../theme/ThemeProvider'
import { jalali, toman, tomanParts } from '../lib/format'
import { Spinner, StatusBadge } from '../components/ui'
import { AuthImage } from '../components/AuthImage'

const PAY_NOTE = {
  pending: ['pay_pending', 'var(--c-success)'],
  rejected: ['pay_rejected', 'var(--c-warning)'],
  approved: ['pay_approved', 'var(--c-success)'],
}

export default function History() {
  const { styleKey } = useTheme()
  return styleKey === 'caspian' ? <CaspianHistory /> : <LegacyHistory />
}

/* ================= Legacy (Aurora / Frost) — unchanged ================= */
function LegacyHistory() {
  const { t, lang } = useI18n()
  const [rows, setRows] = useState(null)
  useEffect(() => { api.get('/orders/').then((r) => setRows(r.data.results)).catch(() => setRows([])) }, [])
  if (rows === null) return <div className="grid place-items-center py-16"><Spinner /></div>
  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold">{t('history')}</h1>
      <div className="card divide-y" style={{ borderColor: 'var(--c-border)' }}>
        {rows.length === 0 && <div className="py-8 text-center text-muted">{t('no_orders')}</div>}
        {rows.map((o) => {
          const note = o.status === 'pending_payment' && PAY_NOTE[o.payment_status]
          return (
            <div key={o.id} className="flex items-start justify-between gap-3 py-3">
              <div className="min-w-0">
                <div className="truncate text-sm">{o.plan_name} · {label(t, 'o_', o.type)}</div>
                <div className="text-xs text-muted">{jalali(o.created_at, true, lang)}</div>
                {note && (
                  <div className="mt-1 text-xs" style={{ color: note[1] }}>
                    {t(note[0])}{o.reject_reason ? ` — ${o.reject_reason}` : ''}
                  </div>
                )}
                {o.status === 'pending_payment' && (
                  <Link to={`/checkout?resume=${o.id}`} className="mt-1 inline-block text-xs text-primary hover:underline">
                    {t('pay')} →
                  </Link>
                )}
              </div>
              <div className="shrink-0 text-end">
                <div className="text-sm">{toman(o.amount_unique, lang)}</div>
                <StatusBadge status={o.status} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ================= Caspian — Stitch redesign port ================= */
const H = {
  bar: 'M4 6h16M4 12h16M4 18h16',
  cart: 'M6 7V6a4 4 0 018 0v1M4 7h16l-1 13H5L4 7z',
  search: 'M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z',
  cal: ['M4 6h16v14H4z', 'M4 10h16M9 3v4M15 3v4'],
  tag: 'M20 12l-8 8-9-9V4h7l10 10-0 0z',
  dns: ['M4 5h16v6H4z', 'M4 13h16v6H4z', 'M8 8h.01M8 16h.01'],
  receipt: 'M6 3h12v18l-3-2-3 2-3-2-3 2V3zM9 7h6M9 11h6M9 15h4',
  replay: 'M4 4v5h5M20 20v-5h-5M20 9A8 8 0 006 5M4 15a8 8 0 0014 4',
  shield: ['M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z', 'M9 12l2 2 4-4'],
  timerOff: 'M10 2h4M12 8v5M4 4l16 16M18.4 8.6A7 7 0 015 18',
  clock: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z',
  x: 'M6 18L18 6M6 6l12 12',
  support: 'M18.4 6.6a9 9 0 11-12.8 0M12 2v8',
}
function HI({ d, w = 15 }) {
  return (
    <svg width={w} height={w} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {Array.isArray(d) ? d.map((p, i) => <path key={i} d={p} />) : <path d={d} />}
    </svg>
  )
}
const fnum = (n, lang) => (lang === 'fa' ? String(n).replace(/\d/g, (x) => '۰۱۲۳۴۵۶۷۸۹'[x]) : String(n))
const methodLabel = (t, m) => (m === 'card_manual' ? t('m_card') : m === 'sms_auto' ? t('m_sms') : m === 'gateway' ? t('m_gateway') : '—')

const FILTERS = [
  ['all', 'f_all', () => true],
  ['completed', 'f_completed', (o) => o.status === 'completed' || o.status === 'paid'],
  ['rejected', 'f_rejected', (o) => o.status === 'rejected'],
  ['pending_payment', 'f_pending_pay', (o) => o.status === 'pending_payment'],
]

function CaspianHistory() {
  const { t, lang } = useI18n()
  const [rows, setRows] = useState(null)
  const [filter, setFilter] = useState('all')
  const [q, setQ] = useState('')
  const [receipt, setReceipt] = useState(null)

  useEffect(() => { api.get('/orders/').then((r) => setRows(r.data.results)).catch(() => setRows([])) }, [])

  const shown = useMemo(() => {
    const list = (rows || []).filter(FILTERS.find(([k]) => k === filter)[2])
    const s = q.trim().toLowerCase()
    return s ? list.filter((o) =>
      String(o.id).includes(s) || (o.plan_name || '').toLowerCase().includes(s) ||
      (o.plan_name_en || '').toLowerCase().includes(s)) : list
  }, [rows, filter, q])
  const fc = (fn) => (rows || []).filter(fn).length

  if (rows === null) return <div className="csp-hist"><div className="grid place-items-center py-24"><Spinner /></div></div>

  return (
    <div className="csp-hist">
      <style>{CSS}</style>

      <header className="csp-hist-head">
        <div>
          <div className="csp-hist-title"><span className="csp-hist-bar" /><h1 className="csp-headline">{t('hist_h1')}</h1></div>
          <p className="csp-hist-lead">{t('hist_lead')}</p>
        </div>
        <Link to="/store" className="csp-hist-buy"><HI d={H.cart} w={16} />{t('buy_new')}</Link>
      </header>

      <div className="csp-card csp-hist-body">
        <div className="csp-hist-bar-row">
          <div className="csp-hist-tabs">
            {FILTERS.map(([k, key, fn]) => (
              <button key={k} type="button" className={'csp-hist-tab' + (filter === k ? ' on' : '')} onClick={() => setFilter(k)}>
                {t(key)} <span className="csp-hist-tab-n mono-num">{fnum(fc(fn), lang)}</span>
              </button>
            ))}
          </div>
          <div className="csp-hist-search">
            <HI d={H.search} w={16} />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('search_order')} dir="auto" />
          </div>
        </div>

        {shown.length === 0 ? (
          <div className="csp-hist-empty">{t('no_orders')}</div>
        ) : (
          <div className="csp-hist-list">
            {shown.map((o) => <Row key={o.id} o={o} t={t} lang={lang} onReceipt={() => setReceipt(o)} />)}
          </div>
        )}

        {shown.length > 0 && (
          <div className="csp-hist-foot">{t('orders_count', { n: fnum(shown.length, lang) })}</div>
        )}
      </div>

      <div className="csp-hist-tips">
        {[['tip_instant_t', 'tip_instant_d', H.shield], ['tip_support_t', 'tip_support_d', H.support]].map(([tk, dk, icon]) => (
          <div key={tk} className="csp-hist-tip">
            <span className="csp-hist-tip-ico"><HI d={icon} w={18} /></span>
            <div>
              <div className="csp-hist-tip-t">{t(tk)}</div>
              <div className="csp-hist-tip-d">{t(dk)}</div>
            </div>
          </div>
        ))}
      </div>

      {receipt && <ReceiptModal o={receipt} t={t} onClose={() => setReceipt(null)} />}
    </div>
  )
}

function Row({ o, t, lang, onReceipt }) {
  const rejected = o.status === 'rejected'
  const pendingPay = o.status === 'pending_payment'
  const plan = (lang === 'fa' ? o.plan_name : (o.plan_name_en || o.plan_name)) || o.plan_name || '—'
  const icon = rejected ? H.timerOff : pendingPay ? H.clock : H.shield
  const tone = rejected ? 'danger' : pendingPay ? 'warning' : 'success'
  const { num, unit } = tomanParts(o.amount_unique ?? o.amount, lang)
  const svc = o.requested_account_name

  return (
    <div className={'csp-hist-row csp-hist-row--' + tone}>
      <div className="csp-hist-row-l">
        <span className="csp-hist-row-ico" data-tone={tone}><HI d={icon} w={22} /></span>
        <div className="csp-hist-row-info">
          <div className="csp-hist-row-title">
            <b>{plan} · {label(t, 'o_', o.type)}</b>
            <span className="csp-hist-pill" data-tone={tone}>
              <i />{t('st_' + o.status) === ('st_' + o.status) ? o.status : t('st_' + o.status)}
            </span>
          </div>
          <div className="csp-hist-meta mono-num">
            <span><HI d={H.cal} w={13} />{jalali(o.created_at, true, lang)}</span>
            <span><HI d={H.tag} w={13} />{t('ord_id')}: #ORD-{o.id}</span>
            {svc && <span className="csp-hist-meta-svc"><HI d={H.dns} w={13} />{svc}</span>}
          </div>
          {rejected && o.reject_reason && <div className="csp-hist-reason">{o.reject_reason}</div>}
        </div>
      </div>

      <div className="csp-hist-row-r">
        <div className="csp-hist-amt">
          <span><b className="mono-num">{num}</b> {unit}</span>
          <small>{methodLabel(t, o.payment_method)}</small>
        </div>
        <div className="csp-hist-row-actions">
          {o.receipt_url && (
            <button type="button" className="csp-hist-btn" onClick={onReceipt}>
              <HI d={H.receipt} w={15} /><span className="csp-hist-btn-txt">{t('view_receipt')}</span>
            </button>
          )}
          {(pendingPay || rejected) && (
            <Link to={`/checkout?resume=${o.id}`} className={'csp-hist-btn' + (rejected ? ' csp-hist-btn--danger' : ' csp-hist-btn--primary')}>
              <HI d={rejected ? H.replay : H.receipt} w={15} />{rejected ? t('pay_again') : t('pay')}
            </Link>
          )}
        </div>
      </div>
    </div>
  )
}

function ReceiptModal({ o, t, onClose }) {
  useEffect(() => {
    const h = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])
  return (
    <div className="csp-hist-overlay" onClick={onClose}>
      <div className="csp-hist-modal" onClick={(e) => e.stopPropagation()}>
        <div className="csp-hist-modal-head">
          <span>{t('receipt')} · #ORD-{o.id}</span>
          <button type="button" onClick={onClose} aria-label={t('close')}><HI d={H.x} w={18} /></button>
        </div>
        <div className="csp-hist-modal-body">
          <AuthImage path={o.receipt_url.replace(/^\/api\/v1/, '')} alt={t('receipt')} className="csp-hist-modal-img" />
        </div>
      </div>
    </div>
  )
}

const CSS = `
.csp-hist { display: flex; flex-direction: column; gap: 18px; }
.csp-hist-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; flex-wrap: wrap; }
.csp-hist-title { display: flex; align-items: center; gap: 9px; }
.csp-hist-bar { width: 4px; height: 22px; border-radius: 999px; background: var(--c-primary); }
.csp-hist-title h1 { font-size: clamp(18px, 3vw, 24px); font-weight: 800; }
.csp-hist-lead { font-size: 12.5px; color: var(--c-text-muted); margin-top: 6px; line-height: 1.7; }
.csp-hist-buy {
  display: inline-flex; align-items: center; gap: 6px; flex-shrink: 0; padding: 10px 16px; border-radius: 999px;
  font-size: 12.5px; font-weight: 700; color: #fff; background: var(--c-primary);
  box-shadow: 0 6px 16px -6px color-mix(in srgb, var(--c-primary) 55%, transparent);
}
.csp-hist-buy:hover { filter: brightness(1.06); }

.csp-card, .csp-hist-body {
  background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 18px;
}
:root:not(.dark) .csp-card, :root:not(.dark) .csp-hist-body { background: #fff; }
[data-theme-style="caspian"].dark .csp-hist-body { box-shadow: -6px -6px 14px rgba(255,255,255,.02), 6px 6px 18px rgba(0,0,0,.5); }
.csp-hist-body { padding: 16px; display: flex; flex-direction: column; gap: 16px; }

.csp-hist-bar-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.csp-hist-tabs { display: flex; gap: 3px; padding: 4px; border-radius: 999px; overflow-x: auto; background: color-mix(in srgb, var(--c-text-muted) 9%, transparent); }
.csp-hist-tab {
  border: 0; cursor: pointer; white-space: nowrap; padding: 7px 13px; border-radius: 999px;
  font-size: 12px; font-weight: 600; color: var(--c-text-muted); background: transparent; transition: .15s;
}
.csp-hist-tab.on { background: var(--c-primary); color: #fff; }
.csp-hist-tab-n { opacity: .8; }
.csp-hist-search {
  position: relative; display: flex; align-items: center; gap: 8px; flex: 1; min-width: 180px;
  padding: 0 12px; border-radius: 12px; background: color-mix(in srgb, var(--c-text-muted) 8%, transparent); color: var(--c-text-muted);
}
.csp-hist-search input { flex: 1; border: 0; background: transparent; outline: none; padding: 9px 0; font: inherit; font-size: 12.5px; color: var(--c-text); }

.csp-hist-list { display: flex; flex-direction: column; gap: 8px; }
.csp-hist-row {
  display: flex; align-items: center; justify-content: space-between; gap: 14px; flex-wrap: wrap;
  padding: 14px; border-radius: 14px; background: color-mix(in srgb, var(--c-text-muted) 5%, transparent);
  transition: background .15s;
}
.csp-hist-row:hover { background: color-mix(in srgb, var(--c-text-muted) 9%, transparent); }
.csp-hist-row-l { display: flex; align-items: center; gap: 12px; min-width: 0; flex: 1; }
.csp-hist-row-ico { width: 44px; height: 44px; flex-shrink: 0; display: grid; place-items: center; border-radius: 12px; }
.csp-hist-row-ico[data-tone="success"] { background: color-mix(in srgb, var(--c-primary) 12%, transparent); color: var(--c-primary); }
.csp-hist-row-ico[data-tone="warning"] { background: color-mix(in srgb, var(--c-warning) 14%, transparent); color: var(--c-warning); }
.csp-hist-row-ico[data-tone="danger"] { background: color-mix(in srgb, var(--c-danger) 12%, transparent); color: var(--c-danger); }
.csp-hist-row-info { min-width: 0; }
.csp-hist-row-title { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.csp-hist-row-title b { font-size: 13.5px; font-weight: 700; }
.csp-hist-pill {
  display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 999px;
  font-size: 10px; font-weight: 700;
}
.csp-hist-pill i { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }
.csp-hist-pill[data-tone="success"] { color: var(--c-success); background: color-mix(in srgb, var(--c-success) 14%, transparent); }
.csp-hist-pill[data-tone="warning"] { color: var(--c-warning); background: color-mix(in srgb, var(--c-warning) 14%, transparent); }
.csp-hist-pill[data-tone="danger"] { color: var(--c-danger); background: color-mix(in srgb, var(--c-danger) 14%, transparent); }
.csp-hist-meta { display: flex; flex-wrap: wrap; gap: 4px 14px; margin-top: 5px; font-size: 10.5px; color: var(--c-text-muted); }
.csp-hist-meta span { display: inline-flex; align-items: center; gap: 4px; }
.csp-hist-meta-svc { color: var(--c-primary) !important; }
.csp-hist-reason { margin-top: 5px; font-size: 10.5px; color: var(--c-danger); line-height: 1.6; }

.csp-hist-row-r { display: flex; align-items: center; gap: 14px; margin-inline-start: auto; }
.csp-hist-amt { display: flex; flex-direction: column; gap: 2px; text-align: end; }
.csp-hist-amt span b { font-size: 16px; font-weight: 800; }
.csp-hist-amt span { font-size: 11px; color: var(--c-text-muted); }
.csp-hist-amt small { font-size: 10px; color: var(--c-text-muted); }
.csp-hist-row-actions { display: flex; gap: 6px; }
.csp-hist-btn {
  display: inline-flex; align-items: center; gap: 5px; padding: 8px 13px; border-radius: 999px;
  font-size: 11.5px; font-weight: 700; cursor: pointer; white-space: nowrap;
  border: 1px solid var(--c-border); background: var(--c-surface); color: var(--c-primary); transition: .15s;
}
:root:not(.dark) .csp-hist-btn { background: #fff; }
.csp-hist-btn:hover { border-color: var(--c-primary); }
.csp-hist-btn--primary { background: var(--c-primary); color: #fff; border-color: var(--c-primary); }
.csp-hist-btn--danger { background: var(--c-danger); color: #fff; border-color: var(--c-danger); }
@media (max-width: 560px) { .csp-hist-btn-txt { display: none; } }

.csp-hist-empty { padding: 40px; text-align: center; color: var(--c-text-muted); }
.csp-hist-foot { padding-top: 12px; border-top: 1px solid var(--c-border); font-size: 11px; color: var(--c-text-muted); }

.csp-hist-tips { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 640px) { .csp-hist-tips { grid-template-columns: 1fr; } }
.csp-hist-tip {
  display: flex; align-items: flex-start; gap: 10px; padding: 13px 15px; border-radius: 14px;
  background: var(--c-surface); border: 1px solid var(--c-border);
}
:root:not(.dark) .csp-hist-tip { background: #fff; }
.csp-hist-tip-ico { width: 34px; height: 34px; flex-shrink: 0; display: grid; place-items: center; border-radius: 10px; background: color-mix(in srgb, var(--c-primary) 12%, transparent); color: var(--c-primary); }
.csp-hist-tip-t { font-size: 12.5px; font-weight: 700; }
.csp-hist-tip-d { font-size: 10.5px; color: var(--c-text-muted); margin-top: 3px; line-height: 1.6; }

/* receipt modal */
.csp-hist-overlay { position: fixed; inset: 0; z-index: 70; display: grid; place-items: center; padding: 16px; background: rgba(15,23,42,.6); backdrop-filter: blur(4px); }
.csp-hist-modal {
  width: 100%; max-width: 420px; background: var(--c-surface); border: 1px solid var(--c-border);
  border-radius: 20px; overflow: hidden; box-shadow: 0 24px 60px -12px rgba(0,0,0,.4);
}
:root:not(.dark) .csp-hist-modal { background: #fff; }
.csp-hist-modal-head { display: flex; align-items: center; justify-content: space-between; padding: 13px 16px; border-bottom: 1px solid var(--c-border); font-size: 12.5px; font-weight: 700; }
.csp-hist-modal-head button { color: var(--c-text-muted); }
.csp-hist-modal-body { padding: 16px; display: grid; place-items: center; }
.csp-hist-modal-img { max-width: 100%; max-height: 60vh; border-radius: 12px; }
`
