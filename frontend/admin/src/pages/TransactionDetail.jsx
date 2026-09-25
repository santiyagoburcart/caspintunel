import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n, enumLabel } from '../lib/i18n'
import { jalali, toman } from '../lib/format'
import { Alert, Spinner } from '../components/ui'
import { useConfirm } from '../components/ConfirmDialog'

/* ------------------------------------------------------------------ *
 *  Transaction Detail — direct port of the Stitch screens
 *  "طراحی مجدد تراکنش کارت‌به‌کارت" (desktop / mobile / reject / lightbox).
 *  Token-driven (var(--c-*)) so it themes for Caspian + Aurora + Frost.
 *  Opened from /panel/transactions/:id and /panel/payments/:id.
 *  Icons are the reference screens' own SVG paths (Heroicons set).
 * ------------------------------------------------------------------ */

const STATES = ['approved', 'pending', 'rejected']
const ST_TONE = { pending: 'warning', approved: 'success', rejected: 'danger' }
const ST_ICON = { pending: 'clock', approved: 'checkCircle', rejected: 'xCircle' }
const ST_PILL_ICON = { pending: 'clock', approved: 'checkSolid', rejected: 'xCircle' }

/* exact paths lifted from the 4 reference HTML screens */
const ICONS = {
  back: { p: ['M15 19l-7-7 7-7'] },
  close: { p: ['M6 18L18 6M6 6l12 12'] },
  check: { p: ['M5 13l4 4L19 7'] },
  checkCircle: { p: ['M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z'] },
  xCircle: { p: ['M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z'] },
  clock: { p: ['M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z'] },
  card: { p: ['M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z'] },
  download: { p: ['M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4'] },
  expand: { p: ['M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4'] },
  search: { p: ['M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z'] },
  photo: { p: ['M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z'] },
  rotate: { p: ['M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15'] },
  plus: { p: ['M12 5v14M5 12h14'] },
  minus: { p: ['M5 12h14'] },
  fit: { p: ['M9 9V4.5M9 9H4.5M9 9L3.75 3.75M15 9h4.5M15 9V4.5M15 9l5.25-5.25M9 15v4.5M9 15H4.5M9 15l-5.25 5.25M15 15h4.5M15 15v4.5m0-4.5l5.25 5.25'] },
  move: { p: ['M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122'] },
  // filled (viewBox 0 0 20 20)
  infoSolid: { vb: '0 0 20 20', fill: true, p: ['M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z'] },
  checkSolid: { vb: '0 0 20 20', fill: true, p: ['M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z'] },
  magnifySolid: { vb: '0 0 20 20', fill: true, p: ['M5 8a1 1 0 011-1h1V6a1 1 0 012 0v1h1a1 1 0 110 2H9v1a1 1 0 11-2 0V9H6a1 1 0 01-1-1z', 'M2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8zm6-4a4 4 0 100 8 4 4 0 000-8z'] },
}

function Ico({ name, w = 18 }) {
  const ic = ICONS[name] || ICONS.close
  return (
    <svg className="txd-ico" width={w} height={w} viewBox={ic.vb || '0 0 24 24'}
      fill={ic.fill ? 'currentColor' : 'none'} stroke={ic.fill ? 'none' : 'currentColor'}
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {ic.p.map((d, i) => (
        <path key={i} d={d} fillRule={ic.fill ? 'evenodd' : undefined} clipRule={ic.fill ? 'evenodd' : undefined} />
      ))}
    </svg>
  )
}

const groupCard = (raw) => {
  const s = String(raw || '').replace(/\D/g, '')
  return s.length >= 12 ? s.replace(/(.{4})(?=.)/g, '$1 ') : (raw || '—')
}
const last4 = (raw) => {
  const s = String(raw || '').replace(/\D/g, '')
  return s.length >= 4 ? s.slice(-4) : null
}

/* fetch the receipt as an authenticated blob (URL is never public) */
function useReceiptBlob(url) {
  const [src, setSrc] = useState(null)
  const [state, setState] = useState('idle') // idle | loading | ok | error
  useEffect(() => {
    if (!url) { setState('idle'); return }
    let dead = false
    let objectUrl
    setState('loading')
    api.get(url.replace(/^\/api\/v1/, ''), { responseType: 'blob' })
      .then((r) => {
        if (dead) return
        objectUrl = URL.createObjectURL(r.data)
        setSrc(objectUrl); setState('ok')
      })
      .catch(() => !dead && setState('error'))
    return () => { dead = true; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [url])
  return { src, state }
}

export default function TransactionDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const confirm = useConfirm()
  const { lang, t } = useI18n()

  const [r, setR] = useState(null)
  const [err, setErr] = useState('')
  const [notFound, setNotFound] = useState(false)
  const [busy, setBusy] = useState(false)
  const [sel, setSel] = useState(null)          // status picked in the switcher
  const [lightbox, setLightbox] = useState(false)

  const load = useCallback(async () => {
    setErr('')
    try {
      const res = await api.get(`/admin/transactions/${id}/`)
      setR(res.data)
      setSel(res.data.status)
    } catch (e) {
      if (e?.response?.status === 404) setNotFound(true)
      else setErr(apiError(e))
    }
  }, [id])
  useEffect(() => { load() }, [load])

  const { src: receiptSrc, state: receiptState } = useReceiptBlob(r?.receipt_url)

  const commit = async (status, why) => {
    setBusy(true); setErr('')
    try {
      await api.post(`/admin/transactions/${id}/status/`, { status, reason: why || '' })
      await load()
    } catch (e) { setErr(apiError(e)) } finally { setBusy(false) }
  }
  const onSave = () => {
    if (sel === r.status) return
    if (sel === 'rejected') {
      // the reason is shown to the customer — asked for in the shared ConfirmDialog
      confirm({
        tone: 'danger', icon: 'ban', badge: 'payment.approve',
        title: t('txd_reject_modal_title'), message: t('txd_reject_modal_desc'),
        targetLabel: t('txd_id_label'), targetId: `#${r.id}`,
        reason: { label: t('txd_reject_reason_label'), placeholder: t('txd_reject_placeholder') },
        confirmLabel: t('txd_reject_confirm'),
        action: async (why) => {
          await api.post(`/admin/transactions/${id}/status/`, { status: 'rejected', reason: why || '' })
          await load()
        },
      }).then((ok) => { if (!ok) setSel(r.status) })
      return
    }
    commit(sel)
  }

  const download = () => {
    if (!receiptSrc) return
    const a = document.createElement('a')
    a.href = receiptSrc
    a.download = `receipt-${id}.jpg`
    document.body.appendChild(a); a.click(); a.remove()
  }

  const back = () => (window.history.length > 1 ? navigate(-1) : navigate('/transactions'))

  if (notFound) {
    return (
      <div className="txd"><style>{CSS}</style>
        <Header t={t} onBack={back} status={null} />
        <div className="txd-empty">{t('txd_not_found')}</div>
      </div>
    )
  }
  if (!r) {
    return (
      <div className="txd"><style>{CSS}</style>
        <div className="txd-loading">{err ? <p className="txd-err">{err}</p> : <Spinner />}</div>
      </div>
    )
  }

  const l4 = last4(r.card)
  const plan = (lang === 'fa' ? r.plan_name : (r.plan_name_en || r.plan_name)) || '—'
  const showUnique = r.amount_unique && String(r.amount_unique) !== String(r.amount)
  const confirmer = !r.confirmer ? null
    : r.confirmer === 'admin' ? t('src_admin')
    : r.confirmer === 'SMS system' ? t('m_sms_auto')
    : r.confirmer
  const hasAudit = confirmer || r.confirmed_at || r.reject_reason

  const rows = [
    [t('txd_amount'), <b className="txd-amt-v">{toman(r.amount, lang)}</b>, true],
    ...(showUnique ? [[t('txd_amount_unique'), <b>{toman(r.amount_unique, lang)}</b>]] : []),
    [t('txd_requester'), (
      <span>
        <b>{r.user}</b>{r.user_telegram ? <span className="txd-dim"> @{r.user_telegram}</span> : null}
        <span className="txd-kv-sub">{plan}{r.user_name ? ` · ${r.user_name}` : ''}</span>
      </span>
    )],
    [t('txd_method'), (
      <span className="txd-chip"><Ico name="card" w={14} />{enumLabel(t, 'm_', r.method)}</span>
    )],
    [t('txd_dest_card'), <span className="txd-mono" dir="ltr">{groupCard(r.card)}</span>,
      false, r.card_bank || r.card_holder ? [r.card_bank, r.card_holder].filter(Boolean).join(' · ') : null],
    ...(r.gateway_ref ? [[t('txd_rrn'), <span className="txd-mono" dir="ltr">{r.gateway_ref}</span>]] : []),
    [t('txd_reg_date'), <span className="txd-mono">{jalali(r.created_at, true, lang)}</span>],
    [t('txd_order_type'), r.order_type === 'renew' ? t('txd_ot_renew') : t('txd_ot_new')],
    ...(r.account_name ? [[t('txd_account_name'), <span className="txd-mono" dir="ltr">{r.account_name}</span>]] : []),
    [t('txd_source'), r.order_source === 'bot' ? t('src_bot') : t('src_site')],
  ]

  return (
    <div className="txd">
      <style>{CSS}</style>
      <Header t={t} onBack={back} status={r.status} />
      <Alert>{err}</Alert>

      <div className="txd-split">
        {/* ---- receipt column ---- */}
        <section className="txd-col">
          <div className="txd-lbl-row">
            <span>{t('txd_receipt_label')}</span>
            {receiptState === 'ok' && (
              <button type="button" className="txd-link" onClick={() => setLightbox(true)}>
                {t('txd_zoom_full')} <Ico name="expand" w={13} />
              </button>
            )}
          </div>

          <div className={'txd-receipt' + (receiptState === 'ok' ? ' is-click' : '')}
            onClick={() => receiptState === 'ok' && setLightbox(true)}>
            {receiptState === 'loading' && <Spinner />}
            {(receiptState === 'error' || receiptState === 'idle') && (
              <span className="txd-receipt-empty"><Ico name="photo" w={26} /> {t('txd_no_receipt')}</span>
            )}
            {receiptState === 'ok' && (
              <>
                <img src={receiptSrc} alt={t('txd_receipt_label')} />
                <span className="txd-receipt-hint"><Ico name="search" w={13} /> {t('txd_touch_view')}</span>
              </>
            )}
          </div>

          {l4 && (
            <div className="txd-note">
              <Ico name="infoSolid" w={16} />
              <span>{t('txd_security_note', { last4: l4 })}</span>
            </div>
          )}

          {receiptState === 'ok' && (
            <button type="button" className="txd-btn txd-btn-ghost" onClick={download}>
              <Ico name="download" w={15} /> {t('txd_download')}
            </button>
          )}
        </section>

        {/* ---- details / status column ---- */}
        <section className="txd-col">
          <dl className="txd-kv">
            {rows.map(([k, v, big, sub], i) => (
              <div key={i} className={'txd-kv-row' + (big ? ' is-big' : '')}>
                <dt>{k}</dt>
                <dd>{v}{sub ? <span className="txd-kv-sub">{sub}</span> : null}</dd>
              </div>
            ))}
            <div className="txd-kv-row">
              <dt>{t('status')}</dt>
              <dd><StatusPill status={r.status} t={t} /></dd>
            </div>
          </dl>

          {/* status switcher — always visible, current state pre-selected (ref screen 1) */}
          <div className="txd-status">
            <div className="txd-status-h">{t('txd_set_status')}</div>
            <div className="txd-status-grid">
              {STATES.map((st) => (
                <button key={st} type="button" disabled={busy}
                  className={'txd-opt txd-opt--' + st + (sel === st ? ' on' : '')}
                  onClick={() => setSel(st)}>
                  <span className="txd-opt-badge"><Ico name={ST_ICON[st]} w={15} /></span>
                  <b>{t('txd_st_' + st)}</b>
                  <i>{t('txd_st_' + st + '_hint')}</i>
                </button>
              ))}
            </div>
            <button type="button" onClick={onSave} disabled={busy || sel === r.status}
              className={'txd-btn txd-save txd-save--' + sel}>
              <Ico name="check" w={15} /> {busy ? '…' : t('txd_save_status')}
            </button>

            {hasAudit && (
              <div className="txd-audit">
                <span className="txd-audit-h">{t('txd_last_change')}</span>
                <div className="txd-audit-grid">
                  {confirmer && <div><span>{t('txd_confirmed_by')}</span><b>{confirmer}</b></div>}
                  {r.confirmed_at && (
                    <div><span>{t('txd_confirmed_at')}</span>
                      <b className="txd-mono">{jalali(r.confirmed_at, true, lang)}</b></div>
                  )}
                </div>
                {r.status === 'rejected' && r.reject_reason && (
                  <div className="txd-audit-reason">
                    <span>{t('txd_reject_reason_label')}</span>
                    <p>{r.reject_reason}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </section>
      </div>

      {lightbox && (
        <Lightbox t={t} src={receiptSrc} txId={r.order_id || id}
          onDownload={download} onClose={() => setLightbox(false)} />
      )}
    </div>
  )
}

function Header({ t, onBack, status }) {
  return (
    <header className="txd-header">
      <button type="button" className="txd-back" onClick={onBack} aria-label={t('txd_back')}>
        <Ico name="back" w={18} />
      </button>
      <div className="txd-header-txt">
        <div className="txd-header-t">
          <h1>{t('txd_title')}</h1>
          {status && <StatusPill status={status} t={t} sm />}
        </div>
        <p>{t('txd_subtitle')}</p>
      </div>
    </header>
  )
}

function StatusPill({ status, t, sm }) {
  const tone = ST_TONE[status] || 'text-muted'
  const label = t(status === 'pending' ? 'tx_pending' : status === 'approved' ? 'tx_approved' : 'tx_rejected')
  const c = `var(--c-${tone})`
  return (
    <span className={'txd-pill' + (sm ? ' txd-pill--sm' : '')}
      style={{ background: `color-mix(in srgb, ${c} 15%, transparent)`, color: c,
        borderColor: `color-mix(in srgb, ${c} 32%, transparent)` }}>
      <Ico name={ST_PILL_ICON[status] || 'clock'} w={sm ? 11 : 13} />{label}
    </span>
  )
}

function Lightbox({ t, src, txId, onDownload, onClose }) {
  const [scale, setScale] = useState(1)
  const [rot, setRot] = useState(0)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const drag = useRef(null)

  useEffect(() => {
    const h = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  const reset = () => { setScale(1); setRot(0); setPan({ x: 0, y: 0 }) }
  const zoom = (delta) => setScale((s) => Math.min(5, Math.max(0.5, +(s + delta).toFixed(2))))
  const onWheel = (e) => { zoom(e.deltaY < 0 ? 0.2 : -0.2) }
  const onPointerDown = (e) => {
    drag.current = { px: e.clientX, py: e.clientY, ox: pan.x, oy: pan.y }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const onPointerMove = (e) => {
    const g = drag.current
    if (!g) return
    setPan({ x: g.ox + (e.clientX - g.px), y: g.oy + (e.clientY - g.py) })
  }
  const onPointerUp = () => { drag.current = null }

  return (
    <div className="txd-lb" onClick={onClose}>
      <header className="txd-lb-bar" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="txd-lb-btn" onClick={onClose} aria-label={t('txd_close')}><Ico name="close" w={18} /></button>
        <div className="txd-lb-meta">
          <span className="txd-lb-title">{t('txd_zoom_full')}</span>
          <span className="txd-lb-id txd-mono" dir="ltr">#TX-{txId}</span>
        </div>
        <div className="txd-lb-tools">
          <button type="button" className="txd-lb-btn" onClick={() => zoom(-0.2)} aria-label={t('txd_zoom_out')}><Ico name="minus" w={16} /></button>
          <button type="button" className="txd-lb-btn" onClick={() => zoom(0.2)} aria-label={t('txd_zoom_in')}><Ico name="plus" w={16} /></button>
          <button type="button" className="txd-lb-btn" onClick={() => setRot((d) => (d + 90) % 360)} aria-label={t('txd_rotate')}><Ico name="rotate" w={16} /></button>
          <button type="button" className="txd-lb-btn" onClick={reset} aria-label={t('txd_reset')}><Ico name="fit" w={16} /></button>
          <button type="button" className="txd-lb-btn" onClick={onDownload} aria-label={t('txd_download')}><Ico name="download" w={16} /></button>
        </div>
      </header>

      <div className="txd-lb-badge"><Ico name="magnifySolid" w={13} /> {Math.round(scale * 100)}%</div>

      <div className="txd-lb-stage" onClick={(e) => e.stopPropagation()} onWheel={onWheel}
        onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerLeave={onPointerUp}>
        {src
          ? <img src={src} alt={t('txd_receipt_label')} draggable={false}
              style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale}) rotate(${rot}deg)` }} />
          : <Spinner />}
      </div>

      <div className="txd-lb-hint" onClick={(e) => e.stopPropagation()}>
        <Ico name="move" w={13} /> {t('txd_pan_hint')}
      </div>
    </div>
  )
}

const CSS = `
.txd { display: flex; flex-direction: column; gap: 18px; }
.txd-loading, .txd-empty { display: grid; place-items: center; padding: 80px 0; color: var(--c-text-muted); }
.txd-err { color: var(--c-danger); font-size: 14px; }
.txd-mono { font-family: 'JetBrains Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }
.txd-dim { color: var(--c-text-muted); }
.txd-ico { flex-shrink: 0; }

/* ---- header ---- */
.txd-header { display: flex; align-items: center; gap: 12px; }
.txd-back {
  flex-shrink: 0; width: 38px; height: 38px; display: grid; place-items: center;
  border-radius: 12px; border: 1px solid var(--c-border); color: var(--c-text);
  background: var(--c-surface); transition: background .18s;
}
.txd-back:hover { background: color-mix(in srgb, var(--c-primary) 8%, transparent); }
[dir="rtl"] .txd-back .txd-ico { transform: scaleX(-1); }
.txd-header-txt { min-width: 0; }
.txd-header-t { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.txd-header-t h1 { font-size: 17px; font-weight: 700; line-height: 1.3; }
.txd-header-txt p { font-size: 12px; color: var(--c-text-muted); margin-top: 2px; }

/* ---- status pill ---- */
.txd-pill {
  display: inline-flex; align-items: center; gap: 5px; padding: 4px 11px;
  border-radius: 999px; font-size: 12px; font-weight: 600; white-space: nowrap;
  border: 1px solid transparent;
}
.txd-pill--sm { font-size: 10.5px; padding: 2px 8px; gap: 3px; }

/* ---- split layout ---- */
.txd-split { display: grid; grid-template-columns: 5fr 7fr; gap: 20px; align-items: start; }
.txd-col { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
@media (max-width: 900px) { .txd-split { grid-template-columns: 1fr; } }

/* ---- receipt ---- */
.txd-lbl-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 12.5px; font-weight: 600; }
.txd-link {
  display: inline-flex; align-items: center; gap: 4px; font-size: 11.5px; font-weight: 600;
  color: var(--c-primary);
}
.txd-link:hover { text-decoration: underline; }
.txd-receipt {
  position: relative; display: grid; place-items: center; min-height: 220px; padding: 12px;
  border-radius: 16px; border: 1px solid var(--c-border); overflow: hidden;
  background: #0b1220;
}
.txd-receipt.is-click { cursor: zoom-in; }
.txd-receipt img { max-height: 340px; width: 100%; object-fit: contain; border-radius: 10px; }
.txd-receipt-empty { display: flex; flex-direction: column; align-items: center; gap: 8px; color: #64748b; font-size: 12px; }
.txd-receipt-hint {
  position: absolute; inset-inline-start: 12px; bottom: 12px;
  display: inline-flex; align-items: center; gap: 5px;
  background: rgba(0,0,0,.65); color: #fff; font-size: 10.5px; padding: 4px 9px; border-radius: 8px;
  backdrop-filter: blur(4px); -webkit-backdrop-filter: blur(4px); pointer-events: none;
}
.txd-note {
  display: flex; align-items: flex-start; gap: 8px; padding: 11px 13px; border-radius: 12px;
  font-size: 11.5px; line-height: 1.7;
  background: color-mix(in srgb, var(--c-primary) 9%, transparent);
  border: 1px solid color-mix(in srgb, var(--c-primary) 22%, transparent);
  color: color-mix(in srgb, var(--c-primary) 82%, var(--c-text));
}
.txd-note .txd-ico { margin-top: 1px; color: var(--c-primary); }

/* ---- key/value ---- */
.txd-kv {
  border-radius: 16px; border: 1px solid var(--c-border); overflow: hidden;
  background: color-mix(in srgb, var(--c-text-muted) 5%, transparent);
}
.txd-kv-row {
  display: grid; grid-template-columns: 40% 1fr; gap: 10px; align-items: center;
  padding: 11px 15px; border-bottom: 1px solid var(--c-border); font-size: 13px;
}
.txd-kv-row:last-child { border-bottom: 0; }
.txd-kv-row dt { color: var(--c-text-muted); font-size: 11.5px; }
.txd-kv-row dd { font-weight: 500; text-align: end; overflow-wrap: anywhere; }
.txd-kv-row.is-big dd { font-size: 15px; }
.txd-amt-v { font-weight: 800; }
.txd-kv-sub { display: block; font-size: 10.5px; color: var(--c-text-muted); font-weight: 400; margin-top: 2px; }
.txd-chip {
  display: inline-flex; align-items: center; gap: 5px; padding: 3px 9px; border-radius: 8px;
  background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); font-size: 12px; font-weight: 600;
}
.txd-chip .txd-ico { color: var(--c-text-muted); }

/* ---- buttons ---- */
.txd-btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 7px;
  padding: 10px 16px; border-radius: 12px; font-size: 13px; font-weight: 700;
  border: 1px solid transparent; cursor: pointer; transition: filter .15s, background .15s;
}
.txd-btn:disabled { opacity: .55; cursor: default; }
.txd-btn-ghost { background: var(--c-surface); border-color: var(--c-border); color: var(--c-text); font-weight: 600; }
.txd-btn-ghost:hover:not(:disabled) { background: color-mix(in srgb, var(--c-primary) 7%, transparent); }
.txd-btn-danger { background: var(--c-danger); color: #fff; }
.txd-btn-danger:hover:not(:disabled) { filter: brightness(1.06); }

/* ---- status switcher (ref screen 1) ---- */
.txd-status {
  border-radius: 16px; border: 1px solid var(--c-border); padding: 15px;
  display: flex; flex-direction: column; gap: 12px;
}
.txd-status-h { font-size: 12.5px; font-weight: 700; }
.txd-status-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
@media (max-width: 560px) { .txd-status-grid { grid-template-columns: 1fr; } }
.txd-opt {
  display: flex; flex-direction: column; align-items: center; gap: 4px; text-align: center;
  padding: 12px 8px; border-radius: 14px; border: 1px solid var(--c-border);
  background: var(--c-surface); cursor: pointer; transition: border-color .15s, background .15s;
  line-height: 1.3;
}
.txd-opt:disabled { cursor: default; }
.txd-opt b { font-size: 12px; font-weight: 700; }
.txd-opt i { font-style: normal; font-size: 9.5px; font-weight: 500; color: var(--c-text-muted); }
.txd-opt-badge {
  width: 26px; height: 26px; display: grid; place-items: center; border-radius: 999px;
  background: color-mix(in srgb, var(--c-text-muted) 15%, transparent); color: var(--c-text-muted);
}
@media (max-width: 560px) { .txd-opt { flex-direction: row; justify-content: flex-start; text-align: start; }
  .txd-opt i { margin-inline-start: auto; } }
.txd-opt.on { border-width: 2px; padding: 11px 7px; }
.txd-opt--approved.on { border-color: var(--c-success); background: color-mix(in srgb, var(--c-success) 10%, transparent); }
.txd-opt--approved.on .txd-opt-badge { background: var(--c-success); color: #fff; }
.txd-opt--approved.on b { color: color-mix(in srgb, var(--c-success) 80%, var(--c-text)); }
.txd-opt--pending.on { border-color: var(--c-warning); background: color-mix(in srgb, var(--c-warning) 10%, transparent); }
.txd-opt--pending.on .txd-opt-badge { background: var(--c-warning); color: #fff; }
.txd-opt--pending.on b { color: color-mix(in srgb, var(--c-warning) 80%, var(--c-text)); }
.txd-opt--rejected.on { border-color: var(--c-danger); background: color-mix(in srgb, var(--c-danger) 10%, transparent); }
.txd-opt--rejected.on .txd-opt-badge { background: var(--c-danger); color: #fff; }
.txd-opt--rejected.on b { color: color-mix(in srgb, var(--c-danger) 80%, var(--c-text)); }

.txd-save { width: 100%; }
.txd-save--approved { background: var(--c-success); color: #fff;
  box-shadow: 0 6px 18px -6px color-mix(in srgb, var(--c-success) 55%, transparent); }
.txd-save--rejected { background: var(--c-danger); color: #fff; }
.txd-save--pending { background: var(--c-primary); color: #fff; }
.txd-save:hover:not(:disabled) { filter: brightness(1.05); }

.txd-audit { border-top: 1px solid var(--c-border); padding-top: 11px; display: flex; flex-direction: column; gap: 8px; }
.txd-audit-h { font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: var(--c-text-muted); }
.txd-audit-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
@media (max-width: 480px) { .txd-audit-grid { grid-template-columns: 1fr; } }
.txd-audit-grid > div { display: flex; flex-direction: column; gap: 2px; font-size: 12.5px; }
.txd-audit-grid span { font-size: 10.5px; color: var(--c-text-muted); }
.txd-audit-reason span { font-size: 10.5px; color: var(--c-text-muted); }
.txd-audit-reason p { font-size: 12px; margin-top: 3px; line-height: 1.7; }

/* ---- lightbox ---- */
.txd-lb {
  position: fixed; inset: 0; z-index: 70; display: flex; flex-direction: column;
  background: rgba(3, 6, 12, .92); backdrop-filter: blur(6px); -webkit-backdrop-filter: blur(6px);
}
.txd-lb-bar {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 14px 16px; color: #e2e8f0;
  background: linear-gradient(to bottom, rgba(0,0,0,.6), transparent);
}
.txd-lb-meta { text-align: center; display: flex; flex-direction: column; gap: 2px; }
.txd-lb-title { font-size: 12.5px; font-weight: 700; color: #fff; }
.txd-lb-id { font-size: 10.5px; color: #94a3b8; }
.txd-lb-tools { display: flex; align-items: center; gap: 6px; }
.txd-lb-btn {
  width: 36px; height: 36px; flex-shrink: 0; display: grid; place-items: center; border-radius: 999px;
  background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.14); color: #e2e8f0;
  transition: background .15s;
}
.txd-lb-btn:hover { background: rgba(255,255,255,.18); }
.txd-lb-badge {
  position: absolute; top: 64px; left: 50%; transform: translateX(-50%); z-index: 2;
  display: inline-flex; align-items: center; gap: 5px;
  background: rgba(15,23,42,.8); border: 1px solid rgba(148,163,184,.35); color: #e2e8f0;
  font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 999px;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
}
.txd-lb-stage {
  flex: 1; display: grid; place-items: center; overflow: hidden; padding: 24px;
  touch-action: none; cursor: grab;
}
.txd-lb-stage:active { cursor: grabbing; }
.txd-lb-stage img {
  max-width: 92%; max-height: 100%; object-fit: contain; border-radius: 10px;
  transition: transform .08s linear; user-select: none;
  box-shadow: 0 20px 50px rgba(0,0,0,.5);
}
.txd-lb-hint {
  display: inline-flex; align-items: center; gap: 6px; align-self: center;
  margin-bottom: 18px; padding: 5px 12px; border-radius: 999px;
  background: rgba(0,0,0,.7); color: #cbd5e1; font-size: 11px;
}
`
