import { createContext, useCallback, useContext, useRef, useState } from 'react'

const ToastContext = createContext(null)

/** Global "در حال انجام… / ✓ / ✗" popup — mount once at the app root.
 * Use `useToast()` anywhere to drive it. */
export function ToastProvider({ children }) {
  const [toast, setToast] = useState(null) // { kind: 'loading'|'success'|'error', message }
  const timerRef = useRef(null)

  const clearTimer = () => {
    if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null }
  }

  const dismiss = useCallback(() => { clearTimer(); setToast(null) }, [])

  const show = useCallback((kind, message) => {
    clearTimer()
    setToast({ kind, message })
    if (kind !== 'loading') {
      timerRef.current = setTimeout(() => setToast(null), 3000)
    }
  }, [])

  const api = {
    loading: (message) => show('loading', message),
    success: (message) => show('success', message),
    error: (message) => show('error', message),
    dismiss,
  }

  return (
    <ToastContext.Provider value={api}>
      {children}
      {toast && <ToastPopup kind={toast.kind} message={toast.message} onClose={dismiss} />}
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast() must be used inside <ToastProvider>')
  return ctx
}

function ToastPopup({ kind, message, onClose }) {
  return (
    <div className="gtoast-backdrop" onMouseDown={onClose}>
      <div className={`gtoast gtoast--${kind}`} onMouseDown={(e) => e.stopPropagation()} onClick={onClose}
        role="status" aria-live="polite">
        <span className="gtoast-ico">
          {kind === 'loading' ? <span className="gtoast-spin" /> : kind === 'success' ? '✓' : '✗'}
        </span>
        <span className="gtoast-msg">{message}</span>
      </div>
    </div>
  )
}
