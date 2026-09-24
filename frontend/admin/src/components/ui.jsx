import { useState } from 'react'

export function Spinner() {
  return <div className="h-6 w-6 animate-spin rounded-full border-2 border-muted border-t-primary" />
}

export function Alert({ kind = 'danger', children }) {
  if (!children) return null
  const color = { danger: 'var(--c-danger)', success: 'var(--c-success)', warning: 'var(--c-warning)' }[kind]
  return (
    <div className="rounded-xl px-3 py-2 text-sm" style={{ background: `color-mix(in srgb, ${color} 15%, transparent)`, color }}>
      {children}
    </div>
  )
}

export function Field({ label, children }) {
  return <div><span className="label">{label}</span>{children}</div>
}

/** Modern on/off switch — shared control for every boolean setting. */
export function Toggle({ checked, onChange, disabled, label }) {
  return (
    <label className="toggle" aria-label={label}>
      <input
        type="checkbox"
        checked={!!checked}
        disabled={disabled}
        onChange={(e) => onChange?.(e.target.checked)}
      />
      <span className="track" />
    </label>
  )
}

/** Confirmation dialog for a destructive/irreversible action — warning icon,
 * a short description, Cancel + Confirm. `tone` picks the confirm button's
 * color: 'danger' (red, default — delete/revoke) or 'success' (green — a
 * safe-ish reset). Renders nothing when `open` is false. */
export function ConfirmModal({ open, title, message, confirmLabel, cancelLabel, tone = 'danger', busy, onConfirm, onCancel }) {
  if (!open) return null
  return (
    <div className="cfm-backdrop" onMouseDown={(e) => e.target === e.currentTarget && !busy && onCancel?.()}>
      <div className={`cfm-modal card cfm-modal--${tone}`} role="alertdialog" aria-modal="true">
        <span className={`cfm-ico cfm-ico--${tone}`}>
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
        </span>
        <div className="cfm-body">
          {title && <h3 className="cfm-title">{title}</h3>}
          <p className="cfm-msg">{message}</p>
        </div>
        <div className="cfm-acts">
          <button type="button" className="btn-ghost text-sm" onClick={onCancel} disabled={busy}>{cancelLabel}</button>
          <button type="button" className={`btn text-white text-sm cfm-confirm cfm-confirm--${tone}`} onClick={onConfirm} disabled={busy}>
            {busy ? '…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

export function StatusBadge({ status }) {
  const map = {
    active: ['success', 'فعال'], on_hold: ['warning', 'در انتظار اتصال'],
    expired: ['danger', 'منقضی'], limited: ['warning', 'اتمام حجم'],
    disabled: ['muted', 'غیرفعال'], pending: ['secondary', 'در حال ساخت'],
    pending_payment: ['warning', 'در انتظار پرداخت'], paid: ['secondary', 'پرداخت شد'],
    completed: ['success', 'تکمیل شد'], rejected: ['danger', 'رد شد'],
  }
  const [c, label] = map[status] || ['muted', status]
  const color = `var(--c-${c === 'muted' ? 'text-muted' : c})`
  return (
    <span className="rounded-full px-2 py-0.5 text-xs" style={{ background: `color-mix(in srgb, ${color} 18%, transparent)`, color }}>
      {label}
    </span>
  )
}

export function Copyable({ text }) {
  const [ok, setOk] = useState(false)
  return (
    <button
      className="btn-ghost text-xs"
      onClick={() => { navigator.clipboard?.writeText(text); setOk(true); setTimeout(() => setOk(false), 1500) }}
    >
      {ok ? '✓' : '⧉'}
    </button>
  )
}
