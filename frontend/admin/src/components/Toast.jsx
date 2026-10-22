import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'

/**
 * The one success / error / loading popup (admin panel + user site + reseller
 * portal — this file is identical in both apps). Mount once at the app root,
 * drive it with `useToast()`: toast.success(msg) · toast.error(msg) ·
 * toast.loading(msg) · toast.dismiss().
 *
 * Top centre of the screen. Success: a green circle with a check that draws
 * itself; error: a red circle with an X. A thin ring around the close button
 * counts down until it closes (success 4 s, error 6 s — reasons need time to
 * read). Hover / focus pauses the countdown, click or Esc closes it.
 * prefers-reduced-motion: no draw / slide animations, the ring stays full.
 */
const ToastContext = createContext(null)
const DURATION = { success: 4000, error: 6000 }

export function ToastProvider({ children }) {
  const [toast, setToast] = useState(null) // { id, kind: 'loading'|'success'|'error', message }
  const seq = useRef(0)
  const dismiss = useCallback(() => setToast(null), [])
  const show = useCallback((kind, message) => { seq.current += 1; setToast({ id: seq.current, kind, message }) }, [])
  const api = useRef(null)
  if (!api.current) {
    api.current = {
      loading: (m) => show('loading', m), success: (m) => show('success', m),
      error: (m) => show('error', m), dismiss,
    }
  }
  return (
    <ToastContext.Provider value={api.current}>
      {children}
      {toast && <ToastPopup key={toast.id} kind={toast.kind} message={toast.message} onClose={dismiss} />}
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast() must be used inside <ToastProvider>')
  return ctx
}

const R = 15
const C = 2 * Math.PI * R

function ToastPopup({ kind, message, onClose }) {
  const total = DURATION[kind] || 0
  const [paused, setPaused] = useState(false)
  const left = useRef(total)
  const started = useRef(0)

  // the countdown: a timer that can be paused (hover / focus) and resumed with what is left
  useEffect(() => {
    if (!total || paused) return undefined
    started.current = Date.now()
    const t = setTimeout(onClose, left.current)
    return () => { clearTimeout(t); left.current -= Date.now() - started.current }
  }, [paused, total, onClose])
  useEffect(() => {
    const k = (e) => { if (e.key === 'Escape' && kind !== 'loading') onClose() }
    document.addEventListener('keydown', k)
    return () => document.removeEventListener('keydown', k)
  }, [kind, onClose])

  const hold = () => setPaused(true)
  const go = () => setPaused(false)
  return (
    <div className="gtoast-wrap" aria-live={kind === 'error' ? 'assertive' : 'polite'}>
      <style>{TOAST_CSS}</style>
      <div className={`gtoast gtoast--${kind}`} role={kind === 'error' ? 'alert' : 'status'}
        onMouseEnter={hold} onMouseLeave={go} onFocus={hold} onBlur={go}
        onClick={kind === 'loading' ? undefined : onClose}>
        <span className="gtoast-ico" aria-hidden="true">
          {kind === 'loading' ? <span className="gtoast-spin" /> : (
            <svg viewBox="0 0 36 36" width="34" height="34">
              <circle className="gtoast-circle" cx="18" cy="18" r="16" />
              {kind === 'success'
                ? <path className="gtoast-mark" d="M11 18.5l4.6 4.6L25.5 13" />
                : <><path className="gtoast-mark" d="M12.5 12.5l11 11" /><path className="gtoast-mark gtoast-mark--2" d="M23.5 12.5l-11 11" /></>}
            </svg>
          )}
        </span>
        <span className="gtoast-msg">{message}</span>
        {kind !== 'loading' && (
          <button type="button" className="gtoast-x" aria-label="close" onClick={(e) => { e.stopPropagation(); onClose() }}>
            <svg viewBox="0 0 36 36" width="30" height="30" aria-hidden="true">
              <circle className="gtoast-ring-bg" cx="18" cy="18" r={R} />
              <circle className="gtoast-ring" cx="18" cy="18" r={R}
                style={{ strokeDasharray: C, animationDuration: `${total}ms`, animationPlayState: paused ? 'paused' : 'running' }} />
              <path d="M14 14l8 8M22 14l-8 8" className="gtoast-x-icon" />
            </svg>
          </button>
        )}
      </div>
    </div>
  )
}

const TOAST_CSS = `
.gtoast-wrap { position: fixed; top: calc(12px + env(safe-area-inset-top, 0px)); left: 0; right: 0; z-index: 400;
  display: flex; justify-content: center; padding: 0 12px; pointer-events: none; }
.gtoast { pointer-events: auto; display: flex; align-items: center; gap: 12px; width: max-content; max-width: min(92vw, 460px);
  padding: 10px 10px 10px 14px; border-radius: 18px; cursor: pointer; font-size: 14px; font-weight: 600; line-height: 1.6;
  color: var(--c-text); background: var(--c-surface); border: 1px solid var(--c-border);
  box-shadow: 0 18px 44px -14px rgba(2, 8, 23, .45), 0 2px 6px rgba(2, 8, 23, .08);
  animation: gtoast-in .32s cubic-bezier(.2, .9, .3, 1.2); }
.dark .gtoast { background: color-mix(in srgb, var(--c-surface) 92%, #0b1220); box-shadow: 0 18px 44px -12px rgba(0, 0, 0, .7); }
[dir="rtl"] .gtoast { padding: 10px 14px 10px 10px; }
.gtoast--success { border-color: color-mix(in srgb, #11AB53 45%, var(--c-border)); }
.gtoast--error { border-color: color-mix(in srgb, #E5484D 50%, var(--c-border)); }
.gtoast-ico { flex-shrink: 0; width: 34px; height: 34px; display: grid; place-items: center; }
.gtoast-circle { fill: none; stroke-width: 2.6; stroke-dasharray: 101; stroke-dashoffset: 101; stroke-linecap: round;
  transform: rotate(-90deg); transform-origin: center; animation: gtoast-draw .5s ease-out forwards; }
.gtoast-mark { fill: none; stroke-width: 3; stroke-linecap: round; stroke-linejoin: round; stroke-dasharray: 30; stroke-dashoffset: 30;
  animation: gtoast-draw .32s ease-out .42s forwards; }
.gtoast-mark--2 { animation-delay: .6s; }
.gtoast--success .gtoast-circle, .gtoast--success .gtoast-mark { stroke: #11AB53; }
.gtoast--error .gtoast-circle, .gtoast--error .gtoast-mark { stroke: #E5484D; }
.gtoast--success .gtoast-ico svg { filter: drop-shadow(0 4px 10px rgba(17, 171, 83, .28)); }
.gtoast--error .gtoast-ico svg { filter: drop-shadow(0 4px 10px rgba(229, 72, 77, .28)); }
.gtoast-msg { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.gtoast-x { flex-shrink: 0; width: 30px; height: 30px; padding: 0; border: 0; background: none; color: var(--c-text-muted); cursor: pointer; border-radius: 999px; }
.gtoast-x:hover, .gtoast-x:focus-visible { color: var(--c-text); }
.gtoast-x:focus-visible { outline: 2px solid var(--c-primary); outline-offset: 1px; }
.gtoast-ring-bg { fill: none; stroke: color-mix(in srgb, var(--c-text-muted) 22%, transparent); stroke-width: 2; }
.gtoast-ring { fill: none; stroke-width: 2; stroke-linecap: round; transform: rotate(-90deg); transform-origin: center;
  stroke-dashoffset: 0; animation-name: gtoast-count; animation-timing-function: linear; animation-fill-mode: forwards; }
.gtoast--success .gtoast-ring { stroke: #11AB53; }
.gtoast--error .gtoast-ring { stroke: #E5484D; }
.gtoast-x-icon { fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; }
.gtoast--loading { cursor: default; padding-inline-end: 18px; }
.gtoast-spin { width: 22px; height: 22px; border-radius: 50%; border: 2.5px solid color-mix(in srgb, var(--c-primary) 25%, transparent);
  border-top-color: var(--c-primary); animation: gtoast-spin .7s linear infinite; }
@keyframes gtoast-in { from { opacity: 0; transform: translateY(-18px) scale(.96); } to { opacity: 1; transform: none; } }
@keyframes gtoast-draw { to { stroke-dashoffset: 0; } }
@keyframes gtoast-count { from { stroke-dashoffset: 0; } to { stroke-dashoffset: ${C.toFixed(2)}; } }
@keyframes gtoast-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) {
  .gtoast { animation: none; }
  .gtoast-circle, .gtoast-mark { animation: none; stroke-dashoffset: 0; }
  .gtoast-ring { animation: none !important; }
  .gtoast-spin { animation-duration: 1.6s; }
}
`
