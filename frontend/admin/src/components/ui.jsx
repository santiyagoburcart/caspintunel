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

export function StatusBadge({ status }) {
  const map = {
    active: ['success', 'فعال'], on_hold: ['warning', 'در انتظار اتصال'],
    expired: ['danger', 'منقضی'], limited: ['danger', 'اتمام حجم'],
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
