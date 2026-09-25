// Client mirror of apps.accounts.phone.normalize_ir_phone — the backend is the
// authority; this only lets the form show the problem before submitting.
const FA = '۰۱۲۳۴۵۶۷۸۹'
const AR = '٠١٢٣٤٥٦٧٨٩'

export function toAsciiDigits(s) {
  return String(s ?? '').replace(/[۰-۹٠-٩]/g, (d) => {
    const i = FA.indexOf(d)
    return String(i >= 0 ? i : AR.indexOf(d))
  })
}

export function normalizeIrPhone(raw) {
  let s = toAsciiDigits(raw).replace(/[\s ‌‎‏\-‐‑–—.()/]/g, '')
  if (!s) return null
  if (s.startsWith('+')) { s = s.slice(1); if (!s.startsWith('98')) return null }
  else if (s.startsWith('00')) { s = s.slice(2); if (!s.startsWith('98')) return null }
  if (!/^\d+$/.test(s)) return null
  if (s.startsWith('98') && (s.length === 12 || s.length === 13)) {
    const rest = s.slice(2)
    s = rest.startsWith('0') ? rest : '0' + rest
  } else if (s.startsWith('9') && s.length === 10) s = '0' + s
  return /^09\d{9}$/.test(s) ? s : null
}

/** Backend phone errors are "fa / en" pairs — show the half for the UI language. */
export function localizeError(msg, lang) {
  const parts = String(msg || '').split(' / ')
  return parts.length === 2 ? parts[lang === 'en' ? 1 : 0] : msg
}
