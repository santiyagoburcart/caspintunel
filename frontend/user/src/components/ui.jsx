import { useState } from 'react'
import { copyToClipboard } from '../lib/clipboard'
import { useI18n } from '../lib/i18n'
import { normalizeIrPhone } from '../lib/phone'
import { useTheme } from '../theme/ThemeProvider'

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

function EyeIcon({ off }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {off ? (
        <>
          <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
          <path d="M6.61 6.61A18.5 18.5 0 0 0 1 12s4 8 11 8a9.26 9.26 0 0 0 5.39-1.61" />
          <line x1="1" y1="1" x2="23" y2="23" />
        </>
      ) : (
        <>
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8Z" />
          <circle cx="12" cy="12" r="3" />
        </>
      )}
    </svg>
  )
}

/** Password input with a show/hide eye toggle — RTL/LTR aware (logical `end`). */
export function PasswordField({ label, value, onChange, autoComplete, autoFocus }) {
  const { t } = useI18n()
  const [show, setShow] = useState(false)
  return (
    <Field label={label}>
      <div className="relative">
        <input
          className="input" type={show ? 'text' : 'password'} value={value} onChange={onChange}
          autoComplete={autoComplete} autoFocus={autoFocus}
          style={{ paddingInlineEnd: '2.75rem' }}
        />
        <button
          type="button" tabIndex={-1}
          className="absolute inset-y-0 end-0 flex items-center px-3 text-muted"
          onClick={() => setShow((v) => !v)}
          aria-label={show ? t('hide_password') : t('show_password')}
          title={show ? t('hide_password') : t('show_password')}
        >
          <EyeIcon off={show} />
        </button>
      </div>
    </Field>
  )
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

const BADGE_COLOR = {
  active: 'success', on_hold: 'warning', expired: 'danger', limited: 'warning',
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
      type="button"
      aria-label={ok ? 'copied' : 'copy'}
      onClick={async () => {
        if (await copyToClipboard(text)) { setOk(true); setTimeout(() => setOk(false), 1500) }
      }}
    >
      {ok ? '✓' : '⧉'}
    </button>
  )
}

/** Phone rules for site forms: with `iran_phone_only` (default on) a valid
 * Iranian mobile is required. Returns { required, error(value) }. */
export function usePhoneRule() {
  const { t } = useI18n()
  const { config } = useTheme()
  const required = config?.iran_phone_only !== false
  const error = (value) => {
    const v = String(value || '').trim()
    if (!v) return required ? t('phone_err_required') : ''
    if (required && !normalizeIrPhone(v)) return t('phone_err_ir')
    return ''
  }
  return { required, error }
}

/** Mobile-number input: LTR, numeric keypad, format hint + inline error
 * (shown after the field is touched). Persian/Arabic digits are accepted. */
export function PhoneInput({ value, onChange, className = 'input', hintClassName = 'mt-1 block text-xs text-muted', showError }) {
  const { t } = useI18n()
  const { required, error } = usePhoneRule()
  const [touched, setTouched] = useState(false)
  const err = (touched || showError) ? error(value) : ''
  return (
    <>
      <input className={className} dir="ltr" type="tel" inputMode="tel" autoComplete="tel"
        placeholder="09121234567" value={value} required={required} aria-invalid={!!err}
        onBlur={() => setTouched(true)} onChange={(e) => onChange(e.target.value)}
        style={err ? { borderColor: 'var(--c-danger)' } : undefined} />
      {err
        ? <span className={hintClassName} style={{ color: 'var(--c-danger)' }} role="alert">{err}</span>
        : <span className={hintClassName}>{required ? t('phone_hint') : t('phone_hint_any')}</span>}
    </>
  )
}
