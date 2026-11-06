import { useId, useState } from 'react'
import { checkName } from '../lib/accountName'

// v1.42.1 the account-name field of every order form (site checkout, Mini App, rename of a paid order; admin: manual
// invoice, new service, provisioning retry). Live check while typing (PasarGuard's rule, lib/accountName.js), the reason
// in Persian / English and a one-tap fixed suggestion. Identical file in frontend/user and frontend/admin.
const T = {
  fa: { use: 'استفاده از', hint: 'حروف انگلیسی، عدد و _ (بدون فاصله)، 3 تا 64 حرف' },
  en: { use: 'Use', hint: 'English letters, digits and _ (no spaces), 3–64 characters' },
}

export default function AccountNameInput({ value, onChange, lang = 'fa', label, testid = 'account-name', serverError = '', autoFocus = false, maxLen = 64, hint = '' }) {
  const s = T[lang] || T.fa
  const id = useId()
  const [touched, setTouched] = useState(false)
  const problem = value ? checkName(value, lang, maxLen) : null
  const show = (touched || (value || '').length > 0) && problem
  const err = show ? problem.message : serverError
  const help = hint || s.hint.replace('64', String(maxLen))
  return (
    <div className="acn">
      <style>{CSS}</style>
      {label && <label className="acn-l" htmlFor={id}>{label}</label>}
      <input id={id} className="input acn-in" dir="ltr" value={value} autoFocus={autoFocus} autoComplete="off"
        autoCapitalize="none" spellCheck={false} maxLength={80} data-testid={testid}
        aria-invalid={!!err} aria-describedby={`${id}-h`}
        onChange={(e) => onChange(e.target.value)} onBlur={() => setTouched(true)} />
      <div id={`${id}-h`} className={'acn-h' + (err ? ' bad' : '')} role={err ? 'alert' : undefined}>{err || help}</div>
      {show && problem.suggestion && (
        <button type="button" className="acn-sug" data-testid={`${testid}-suggest`} onClick={() => onChange(problem.suggestion)}>
          {s.use} <bdi dir="ltr">{problem.suggestion}</bdi>
        </button>
      )}
    </div>
  )
}

/** true when the name passes PasarGuard's rule (for disabling a submit button) */
export const nameOk = (v, maxLen = 64) => !checkName(v, 'fa', maxLen)

const CSS = `
.acn { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.acn-l { font-size: 13px; font-weight: 600; color: var(--c-text); }
.acn-in { width: 100%; }
@media (max-width: 767px) { .acn-in { font-size: 16px; } }
.acn-in[aria-invalid="true"] { border-color: var(--c-danger, #d93025); }
.acn-h { font-size: 12px; color: var(--c-text-muted); line-height: 1.6; }
.acn-h.bad { color: var(--c-danger-fg, var(--c-danger, #d93025)); }
.acn-sug { align-self: flex-start; min-height: 44px; padding: 0 14px; border-radius: 12px; font-size: 14px; font-weight: 600;
  border: 1px dashed var(--c-primary); color: var(--c-primary); background: transparent; cursor: pointer; }
.acn-sug:hover { background: color-mix(in srgb, var(--c-primary) 8%, transparent); }
`
