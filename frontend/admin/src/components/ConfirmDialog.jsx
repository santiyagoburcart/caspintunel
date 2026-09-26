/**
 * The one confirmation / alert popup used everywhere (admin panel + user site;
 * this file is kept identical in both apps). Ported from the Stitch screens
 * "پاپ‌آپ فعال تایید روی صفحه" (desktop) and "پاپ‌آپ فعال تایید حذف سرویس -
 * نسخه موبایل" (≤767px: bottom sheet).
 *
 * Two ways to use it:
 *  - declarative:  <ConfirmDialog open tone="danger" title=… onConfirm=… onCancel=… loading=… />
 *  - imperative:   const confirm = useConfirm()
 *                  const ok = await confirm({ tone, title, message, action: async (reason) => … })
 *    `action` runs with the confirm button spinning; if it throws, the error is
 *    shown inside the dialog and it stays open. Resolves true once confirmed
 *    (and the action succeeded), false when dismissed.
 *
 * Colours are fixed per tone and mode (not theme tokens) so the confirm button
 * is always a clearly filled button — danger red, success #11AB53, primary
 * #1464BA, warning amber — in every theme, light and dark.
 */
import { createContext, useCallback, useContext, useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'

const STR = {
  fa: { cancel: 'انصراف', close: 'بستن', confirm: 'تأیید', working: 'در حال انجام…', ok: 'متوجه شدم' },
  en: { cancel: 'Cancel', close: 'Close', confirm: 'Confirm', working: 'Working…', ok: 'Got it' },
}

// Heroicons-style outline paths (inline, no icon font)
const ICONS = {
  trash: 'M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0',
  warning: 'M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z',
  check: 'M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
  info: 'M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z',
  refresh: 'M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99',
  link: 'M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244',
  ban: 'M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636',
  x: 'M6 18L18 6M6 6l12 12',
  shield: 'M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z',
  lock: 'M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z',
  cart: 'M2.25 3h1.386c.51 0 .955.343 1.087.835l.383 1.437M7.5 14.25a3 3 0 00-3 3h15.75m-12.75-3h11.218c1.121-2.3 2.1-4.684 2.924-7.138a60.114 60.114 0 00-16.536-1.84M7.5 14.25L5.106 5.272M6 20.25a.75.75 0 11-1.5 0 .75.75 0 011.5 0zm12.75 0a.75.75 0 11-1.5 0 .75.75 0 011.5 0z',
}
const TONE_ICON = { danger: 'trash', success: 'check', primary: 'info', warning: 'warning' }

function Svg({ name, size = 20, stroke = 1.8 }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth={stroke}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={ICONS[name] || ICONS.info} />
    </svg>
  )
}

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function ConfirmDialog({
  open, tone = 'danger', icon, title, message, badge, targetLabel, targetId, details, footnote,
  confirmLabel, cancelLabel, loading = false, confirmDisabled = false, hideCancel = false, error,
  onConfirm, onCancel, children,
}) {
  const { lang } = useI18n()
  const s = STR[lang] || STR.fa
  const cardRef = useRef(null)
  const titleId = useId()
  const loadingRef = useRef(loading)
  loadingRef.current = loading
  const cancelRef = useRef(onCancel)
  cancelRef.current = onCancel

  // Esc to close (never while the request runs), focus trap, restore focus, lock scroll
  useEffect(() => {
    if (!open) return undefined
    const prevFocus = document.activeElement
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const card = cardRef.current
    // destructive: land on "cancel" so Enter never deletes by accident
    const first = card?.querySelector(tone === 'danger' && !hideCancel ? '.cdlg-cancel' : '.cdlg-confirm')
    ;(first || card)?.focus({ preventScroll: true })

    const onKey = (e) => {
      if (e.key === 'Escape') {
        if (!loadingRef.current) { e.stopPropagation(); cancelRef.current?.() }
        return
      }
      if (e.key !== 'Tab' || !card) return
      const items = [...card.querySelectorAll(FOCUSABLE)].filter((el) => el.offsetParent !== null)
      if (!items.length) { e.preventDefault(); return }
      const firstEl = items[0]
      const lastEl = items[items.length - 1]
      if (e.shiftKey && (document.activeElement === firstEl || !card.contains(document.activeElement))) {
        e.preventDefault(); lastEl.focus()
      } else if (!e.shiftKey && (document.activeElement === lastEl || !card.contains(document.activeElement))) {
        e.preventDefault(); firstEl.focus()
      }
    }
    document.addEventListener('keydown', onKey, true)
    return () => {
      document.removeEventListener('keydown', onKey, true)
      document.body.style.overflow = prevOverflow
      try { prevFocus?.focus?.({ preventScroll: true }) } catch { /* element gone */ }
    }
  }, [open])

  if (!open) return null
  const iconName = typeof icon === 'string' ? icon : TONE_ICON[tone] || 'info'

  return createPortal(
    <div className="cdlg-backdrop" dir={lang === 'fa' ? 'rtl' : 'ltr'}
      onMouseDown={(e) => { if (e.target === e.currentTarget && !loading) onCancel?.() }}>
      <style>{CDLG_CSS}</style>
      <div ref={cardRef} className={`cdlg cdlg--${tone}`} role="alertdialog" aria-modal="true"
        aria-labelledby={titleId} tabIndex={-1}>
        <span className="cdlg-glow" aria-hidden="true" />
        <span className="cdlg-grab" aria-hidden="true" />

        {/* top row: optional tag chip + close */}
        <div className="cdlg-top">
          {badge ? <span className="cdlg-badge"><Svg name="shield" size={14} stroke={2} />{badge}</span> : <span />}
          <button type="button" className="cdlg-x" onClick={onCancel} disabled={loading} aria-label={s.close}>
            <Svg name="x" size={18} stroke={2} />
          </button>
        </div>

        {/* icon tile + title (+ target id chip) */}
        <div className="cdlg-head">
          <span className="cdlg-ico">{typeof icon === 'object' && icon ? icon : <Svg name={iconName} size={26} stroke={1.9} />}</span>
          <div className="cdlg-head-txt">
            <h2 id={titleId} className="cdlg-title">{title}</h2>
            {targetId != null && targetId !== '' && (
              <div className="cdlg-target">
                {targetLabel && <span>{targetLabel}</span>}
                <b dir="ltr">{targetId}</b>
              </div>
            )}
          </div>
        </div>

        {message && <div className="cdlg-msg">{message}</div>}

        {/* impact / details box */}
        {details && (details.rows?.length > 0 || details.title) && (
          <div className="cdlg-box">
            {(details.title || details.tag) && (
              <div className="cdlg-box-h">
                <span className="cdlg-box-t"><Svg name="warning" size={15} stroke={2} />{details.title}</span>
                {details.tag && <span className="cdlg-box-tag">{details.tag}</span>}
              </div>
            )}
            {(details.rows || []).map(([k, v], i) => (
              <div key={i} className="cdlg-box-row"><span>{k}</span><b>{v}</b></div>
            ))}
          </div>
        )}

        {children && <div className="cdlg-extra">{children}</div>}
        {error && <div className="cdlg-err" role="alert">{error}</div>}

        <div className="cdlg-acts">
          <button type="button" className="cdlg-confirm" onClick={onConfirm} disabled={loading || confirmDisabled}
            aria-busy={loading}>
            {loading
              ? <><span className="cdlg-spin" aria-hidden="true" />{s.working}</>
              : <><Svg name={iconName} size={18} stroke={2} />{confirmLabel || s.confirm}</>}
          </button>
          {!hideCancel && (
            <button type="button" className="cdlg-cancel" onClick={onCancel} disabled={loading}>
              {cancelLabel || s.cancel}
            </button>
          )}
        </div>

        {footnote && <div className="cdlg-foot"><Svg name="lock" size={13} stroke={2} />{footnote}</div>}
      </div>
    </div>,
    document.body,
  )
}

/* ---------------- imperative API ---------------- */
const Ctx = createContext(null)

export function ConfirmProvider({ children }) {
  const [state, setState] = useState(null) // { opts, resolve }
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [reason, setReason] = useState('')

  const confirm = useCallback((opts) => new Promise((resolve) => {
    setLoading(false); setError(''); setReason(opts.reason?.defaultValue || '')
    setState({ opts, resolve })
  }), [])

  const close = (result) => {
    state?.resolve(result)
    setState(null); setLoading(false); setError('')
  }
  const onConfirm = async () => {
    const { opts } = state
    if (!opts.action) { close(true); return }
    setLoading(true); setError('')
    try {
      await opts.action(opts.reason ? reason.trim() : undefined)
      close(true)
    } catch (e) {
      setLoading(false)
      setError(apiError(e, e?.message || 'Error'))
    }
  }

  const o = state?.opts
  return (
    <Ctx.Provider value={confirm}>
      {children}
      {o && (
        <ConfirmDialog
          open tone={o.tone} icon={o.icon} title={o.title} message={o.message} badge={o.badge}
          targetLabel={o.targetLabel} targetId={o.targetId} details={o.details} footnote={o.footnote}
          confirmLabel={o.confirmLabel} cancelLabel={o.cancelLabel} hideCancel={o.hideCancel}
          loading={loading} error={error}
          confirmDisabled={!!(o.reason?.required && !reason.trim())}
          onConfirm={onConfirm} onCancel={() => !loading && close(false)}
        >
          {o.reason && (
            <label className="cdlg-field">
              <span>{o.reason.label}</span>
              <textarea rows={3} value={reason} placeholder={o.reason.placeholder || ''}
                onChange={(e) => setReason(e.target.value)} disabled={loading} />
            </label>
          )}
          {o.content}
        </ConfirmDialog>
      )}
    </Ctx.Provider>
  )
}

/** `const confirm = useConfirm(); if (!(await confirm({...}))) return` */
export function useConfirm() {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useConfirm() must be used inside <ConfirmProvider>')
  return ctx
}

export const CDLG_CSS = `
.cdlg-backdrop {
  --cdlg-surface: #ffffff; --cdlg-border: #e2e8f0; --cdlg-title: #0f172a; --cdlg-text: #475569;
  --cdlg-muted: #94a3b8; --cdlg-box: #f8fafc; --cdlg-chip: #f1f5f9; --cdlg-chip-text: #334155;
  --cdlg-cancel-border: #cbd5e1; --cdlg-cancel-hover: #f1f5f9; --cdlg-field: #ffffff;
  position: fixed; inset: 0; z-index: 1200; display: flex; align-items: center; justify-content: center;
  padding: 16px; background: rgba(15, 23, 42, .6); -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px);
  animation: cdlg-fade .18s ease-out;
}
.dark .cdlg-backdrop {
  --cdlg-surface: #121826; --cdlg-border: rgba(255,255,255,.09); --cdlg-title: #f1f5f9; --cdlg-text: #b6c0cf;
  --cdlg-muted: #7d889b; --cdlg-box: rgba(255,255,255,.04); --cdlg-chip: rgba(255,255,255,.07); --cdlg-chip-text: #d5dbe5;
  --cdlg-cancel-border: rgba(255,255,255,.18); --cdlg-cancel-hover: rgba(255,255,255,.06); --cdlg-field: rgba(255,255,255,.04);
  background: rgba(2, 6, 17, .72);
}
.cdlg { --tone: #E11D48; --tone-hover: #BE123C; --tone-btn: #DC2626; --tone-btn-hover: #B91C1C; --tone-fg: #C81E1E;
  position: relative; overflow: hidden; width: 100%; max-width: 448px; max-height: calc(100dvh - 32px); overflow-y: auto;
  display: flex; flex-direction: column; gap: 18px; padding: 24px; border-radius: 18px; outline: none;
  background: var(--cdlg-surface); color: var(--cdlg-text); border: 1px solid var(--cdlg-border);
  box-shadow: 0 25px 50px -12px rgba(0,0,0,.35); text-align: start; font-size: 14px;
  animation: cdlg-pop .2s ease-out;
}
.cdlg--success { --tone: #11AB53; --tone-hover: #0E9447; --tone-btn: #0A7F3F; --tone-btn-hover: #086B35; --tone-fg: #0A7A3C; }
.cdlg--primary { --tone: #1464BA; --tone-hover: #0F4E92; --tone-btn: #1464BA; --tone-btn-hover: #0F4E92; --tone-fg: #1464BA; }
.cdlg--warning { --tone: #D97706; --tone-hover: #B45309; --tone-btn: #B45309; --tone-btn-hover: #92400E; --tone-fg: #9A4A00; }
/* text-safe tone text in dark mode (the fill stays the same) */
.dark .cdlg { --tone-fg: #FF8585; } .dark .cdlg--success { --tone-fg: #3DD37F; } .dark .cdlg--primary { --tone-fg: #6AA9EE; } .dark .cdlg--warning { --tone-fg: #FBBF24; }
.cdlg-glow { position: absolute; top: -48px; inset-inline-end: -48px; width: 128px; height: 128px; border-radius: 50%;
  background: color-mix(in srgb, var(--tone) 18%, transparent); filter: blur(28px); pointer-events: none; }
.cdlg > *:not(.cdlg-glow) { position: relative; }
.cdlg-grab { display: none; }

.cdlg-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.cdlg-badge { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 999px;
  background: var(--cdlg-chip); border: 1px solid var(--cdlg-border); color: var(--cdlg-chip-text);
  font: 600 12px/1.2 'JetBrains Mono', ui-monospace, monospace; }
.cdlg-badge svg { color: var(--cdlg-muted); }
.cdlg-x { width: 32px; height: 32px; display: grid; place-items: center; border-radius: 10px; border: 0;
  background: transparent; color: var(--cdlg-muted); cursor: pointer; transition: .15s; }
.cdlg-x:hover:not(:disabled) { color: var(--cdlg-title); background: var(--cdlg-chip); }
.cdlg-x:disabled { opacity: .4; cursor: not-allowed; }

.cdlg-head { display: flex; align-items: flex-start; gap: 16px; }
.cdlg-ico { width: 56px; height: 56px; flex-shrink: 0; border-radius: 16px; display: grid; place-items: center;
  color: var(--tone); background: color-mix(in srgb, var(--tone) 10%, var(--cdlg-surface));
  border: 1px solid color-mix(in srgb, var(--tone) 22%, transparent); box-shadow: 0 1px 2px rgba(0,0,0,.05); }
.cdlg-head-txt { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 6px; padding-top: 2px; }
.cdlg-title { margin: 0; font-size: 18px; font-weight: 800; line-height: 1.5; color: var(--cdlg-title); }
.cdlg-target { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--cdlg-muted); font-weight: 500; }
.cdlg-target b { font: 700 12px 'JetBrains Mono', ui-monospace, monospace; color: var(--c-primary-fg); padding: 2px 8px; border-radius: 6px;
  background: color-mix(in srgb, #1464BA 9%, transparent); border: 1px solid color-mix(in srgb, #1464BA 22%, transparent); }
.dark .cdlg-target b { color: #7fb3ec; }

.cdlg-msg { font-size: 14px; line-height: 1.9; color: var(--cdlg-text); }
.cdlg-msg strong, .cdlg-msg code { font-family: 'JetBrains Mono', ui-monospace, monospace; font-weight: 700; color: var(--cdlg-title);
  background: var(--cdlg-chip); border: 1px solid var(--cdlg-border); padding: 1px 6px; border-radius: 6px; }
.cdlg-msg em { font-style: normal; font-weight: 700; color: var(--tone-fg); text-decoration: underline; text-underline-offset: 4px; }

.cdlg-box { display: flex; flex-direction: column; gap: 10px; padding: 14px; border-radius: 12px; font-size: 12px;
  background: var(--cdlg-box); border: 1px solid var(--cdlg-border); }
.cdlg-box-h { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.cdlg-box-t { display: inline-flex; align-items: center; gap: 6px; font-weight: 700; color: var(--cdlg-title); }
.cdlg-box-t svg { color: var(--tone); }
.cdlg-box-tag { font-weight: 700; color: var(--tone-fg); padding: 2px 8px; border-radius: 6px; white-space: nowrap;
  background: color-mix(in srgb, var(--tone) 10%, transparent); border: 1px solid color-mix(in srgb, var(--tone) 20%, transparent); }
.cdlg-box-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-top: 10px;
  border-top: 1px solid var(--cdlg-border); color: var(--cdlg-text); }
.cdlg-box-h + .cdlg-box-row { margin-top: 0; }
.cdlg-box-row b { font-weight: 700; color: var(--cdlg-title); text-align: end; min-width: 0; overflow-wrap: anywhere; }

.cdlg-extra { display: flex; flex-direction: column; gap: 10px; }
.cdlg-field { display: flex; flex-direction: column; gap: 6px; font-size: 12.5px; font-weight: 600; color: var(--cdlg-title); }
.cdlg-field textarea { width: 100%; resize: vertical; min-height: 76px; padding: 10px 12px; border-radius: 12px; font: inherit;
  font-weight: 400; font-size: 14px; color: var(--cdlg-title); background: var(--cdlg-field); border: 1px solid var(--cdlg-cancel-border); outline: none; }
.cdlg-field textarea:focus { border-color: var(--tone); box-shadow: 0 0 0 3px color-mix(in srgb, var(--tone) 18%, transparent); }
.cdlg-err { font-size: 13px; line-height: 1.7; padding: 10px 12px; border-radius: 10px; color: var(--c-danger-fg);
  background: color-mix(in srgb, #E11D48 9%, transparent); border: 1px solid color-mix(in srgb, #E11D48 22%, transparent); }
.dark .cdlg-err { color: #fb7185; }

.cdlg-acts { display: flex; flex-direction: column; gap: 8px; padding-top: 2px; }
.cdlg-confirm, .cdlg-cancel { width: 100%; display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  border-radius: 12px; font: inherit; font-size: 14px; cursor: pointer; transition: background .15s, box-shadow .15s, transform .1s; }
.cdlg-confirm { min-height: 48px; padding: 12px 20px; border: 0; font-weight: 700; color: #ffffff !important;
  background: var(--tone-btn) !important; box-shadow: 0 6px 16px -4px color-mix(in srgb, var(--tone) 45%, transparent); }
.cdlg-confirm:hover:not(:disabled) { background: var(--tone-btn-hover) !important; }
.cdlg-confirm:active:not(:disabled) { transform: scale(.99); }
.cdlg-confirm:disabled { cursor: not-allowed; opacity: .75; }
.cdlg-confirm:focus-visible, .cdlg-cancel:focus-visible, .cdlg-x:focus-visible {
  outline: 2px solid var(--tone); outline-offset: 2px; }
.cdlg-cancel { min-height: 44px; padding: 10px 20px; font-weight: 600; color: var(--cdlg-title);
  background: transparent; border: 1px solid var(--cdlg-cancel-border); }
.cdlg-cancel:hover:not(:disabled) { background: var(--cdlg-cancel-hover); }
.cdlg-cancel:disabled { opacity: .5; cursor: not-allowed; }
.cdlg-spin { width: 18px; height: 18px; border-radius: 50%; border: 2.5px solid rgba(255,255,255,.35); border-top-color: #fff;
  animation: cdlg-spin .7s linear infinite; }

.cdlg-foot { display: flex; align-items: center; justify-content: center; gap: 6px; margin-top: -6px;
  font-size: 12px; color: var(--cdlg-muted); text-align: center; }

@keyframes cdlg-fade { from { opacity: 0; } to { opacity: 1; } }
@keyframes cdlg-pop { from { opacity: 0; transform: scale(.96); } to { opacity: 1; transform: none; } }
@keyframes cdlg-up { from { transform: translateY(100%); } to { transform: none; } }
@keyframes cdlg-spin { to { transform: rotate(360deg); } }

/* ---- phones: bottom sheet (Stitch mobile screen) ---- */
@media (max-width: 767px) {
  .cdlg-backdrop { align-items: flex-end; padding: 0; }
  .cdlg { max-width: none; max-height: 92dvh; border-radius: 24px 24px 0 0; border-bottom: 0; gap: 16px;
    padding: 12px 20px calc(20px + env(safe-area-inset-bottom, 0px)); animation: cdlg-up .24s ease-out; }
  .cdlg-grab { display: block; width: 40px; height: 4px; border-radius: 999px; margin: 0 auto -4px; background: var(--cdlg-border); }
  .cdlg-badge { background: color-mix(in srgb, var(--tone) 12%, transparent); border-color: transparent; color: var(--tone); }
  .cdlg-badge svg { color: currentColor; }
  .cdlg-x { border-radius: 999px; background: var(--cdlg-chip); }
  .cdlg-ico { width: 48px; height: 48px; }
  .cdlg-title { font-size: 16.5px; }
  .cdlg-msg { text-align: justify; }
  .cdlg-box { border-radius: 16px; }
  .cdlg-confirm, .cdlg-cancel { border-radius: 16px; }
  .cdlg-confirm { min-height: 50px; font-size: 15px; }
}
@media (prefers-reduced-motion: reduce) { .cdlg, .cdlg-backdrop { animation: none; } }
`
