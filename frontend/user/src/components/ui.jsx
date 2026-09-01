import { useState } from 'react'
import { useI18n } from '../lib/i18n'

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

const BADGE_COLOR = {
  active: 'success', on_hold: 'warning', expired: 'danger', limited: 'danger',
  disabled: 'muted', pending: 'secondary', pending_payment: 'warning',
  paid: 'secondary', completed: 'success', rejected: 'danger',
}

export function StatusBadge({ status }) {
  const { t } = useI18n()
  const c = BADGE_COLOR[status] || 'muted'
  const color = `var(--c-${c === 'muted' ? 'text-muted' : c})`
  const key = 'st_' + status
  const label = t(key) === key ? status : t(key)
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
