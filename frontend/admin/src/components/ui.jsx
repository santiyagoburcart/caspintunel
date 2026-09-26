import { useState } from 'react'
import { CheckCircle, Check, Copy, Info, Warning, WarningCircle } from '@phosphor-icons/react'
import { copyToClipboard } from '../lib/clipboard'
import { useI18n } from '../lib/i18n'

export function Spinner() {
  return <div role="status" aria-busy="true" aria-label="…" className="h-6 w-6 animate-spin rounded-full border-2 border-muted border-t-primary" />
}

const ALERT_ICON = { danger: WarningCircle, success: CheckCircle, warning: Warning, info: Info }

export function Alert({ kind = 'danger', children }) {
  if (!children) return null
  const role = { danger: 'danger', success: 'success', warning: 'warning', info: 'primary' }[kind] || 'danger'
  const Icon = ALERT_ICON[kind] || WarningCircle
  return (
    <div role={kind === 'danger' ? 'alert' : 'status'} className="flex items-start gap-2 rounded-xl px-3 py-2.5 text-sm"
      style={{ background: `color-mix(in srgb, var(--c-${role}) 12%, transparent)`, color: `var(--c-${role}-fg)`,
        border: `1px solid color-mix(in srgb, var(--c-${role}) 25%, transparent)` }}>
      <Icon size={18} weight="bold" aria-hidden="true" style={{ flexShrink: 0, marginTop: 1 }} />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  )
}

/** Labelled form field. Renders a real <label> so the input gets an accessible
 *  name; `group` is for a set of controls (checkbox/toggle groups) instead. */
export function Field({ label, children, hint, group = false }) {
  if (group) {
    return (
      <div role="group" aria-label={typeof label === 'string' ? label : undefined}>
        <span className="label">{label}</span>{children}{hint && <span className="hint">{hint}</span>}
      </div>
    )
  }
  return <label className="block"><span className="label">{label}</span>{children}{hint && <span className="hint">{hint}</span>}</label>
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
    expired: ['danger', 'منقضی'], limited: ['warning', 'اتمام حجم'],
    disabled: ['muted', 'غیرفعال'], pending: ['secondary', 'در حال ساخت'],
    pending_payment: ['warning', 'در انتظار پرداخت'], paid: ['secondary', 'پرداخت شد'],
    completed: ['success', 'تکمیل شد'], rejected: ['danger', 'رد شد'],
  }
  const [c, label] = map[status] || ['muted', status]
  return <span className={`badge ${c === 'muted' ? '' : c === 'secondary' ? 'badge-primary' : 'badge-' + c}`}>{label}</span>
}

export function Copyable({ text }) {
  const { t } = useI18n()
  const [ok, setOk] = useState(false)
  return (
    <button
      className="icon-btn"
      type="button"
      aria-label={ok ? t('copied') : t('copy')}
      title={ok ? t('copied') : t('copy')}
      onClick={async () => {
        if (await copyToClipboard(text)) { setOk(true); setTimeout(() => setOk(false), 1500) }
      }}
    >
      {ok ? <Check size={18} weight="bold" style={{ color: 'var(--c-success-fg)' }} aria-hidden="true" /> : <Copy size={18} aria-hidden="true" />}
    </button>
  )
}
