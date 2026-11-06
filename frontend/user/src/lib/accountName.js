// Account names (= PasarGuard usernames) — the SAME rule as backend apps/panel/account_names.py
// (PasarGuard v5.6: 3–128 characters of a-z A-Z 0-9 - _ @ . and no two of - _ @ . in a row; our columns hold 64).
// Identical file in frontend/user and frontend/admin — keep all three copies in step.
export const MIN_LEN = 3
export const MAX_LEN = 64
const SPECIAL = '_.@-'
const FA_DIGITS = '۰۱۲۳۴۵۶۷۸۹'
const AR_DIGITS = '٠١٢٣٤٥٦٧٨٩'

const MESSAGES = {
  required: ['نام اکانت را وارد کنید.', 'Enter an account name.'],
  short: [`نام اکانت باید حداقل ${MIN_LEN} حرف باشد.`, `The account name needs at least ${MIN_LEN} characters.`],
  long: ['نام اکانت حداکثر {n} حرف است.', 'The account name can have at most {n} characters.'],
  space: ['نام اکانت نمی‌تواند فاصله داشته باشد؛ به جای فاصله _ بگذارید.', "The account name can't contain spaces — use _ instead."],
  chars: ['نام اکانت فقط می‌تواند حروف انگلیسی، عدد و _ - . @ داشته باشد.', 'Use only English letters, digits and _ - . @ in the account name.'],
  consecutive: ['دو علامت از _ - . @ نباید پشت سر هم بیایند.', "Two of _ - . @ can't be next to each other."],
}

/** The first rule the name breaks (a MESSAGES key) or null when PasarGuard accepts it. */
export function nameProblem(raw, maxLen = MAX_LEN) {
  const name = (raw || '').trim()
  if (!name) return 'required'
  if (/\s/.test(name)) return 'space'
  if (!/^[A-Za-z0-9_.@-]+$/.test(name)) return 'chars'
  if (/[-_@.]{2,}/.test(name)) return 'consecutive'
  if (name.length < MIN_LEN) return 'short'
  if (name.length > maxLen) return 'long'
  return null
}

/** A fixed version (spaces → _, Persian digits → Latin, other characters dropped, repeated symbols collapsed) or null. */
export function suggestName(raw) {
  const orig = (raw || '').trim()
  if (!nameProblem(orig)) return null
  let s = orig.replace(/[۰-۹٠-٩]/g, (d) => String(FA_DIGITS.indexOf(d) >= 0 ? FA_DIGITS.indexOf(d) : AR_DIGITS.indexOf(d)))
  s = s.replace(/\s+/g, '_').replace(/[^A-Za-z0-9_.@-]/g, '').replace(/[-_@.]{2,}/g, (m) => m[0])
  const trim = (v) => { let a = 0; let b = v.length; while (a < b && SPECIAL.includes(v[a])) a++; while (b > a && SPECIAL.includes(v[b - 1])) b--; return v.slice(a, b) }
  s = trim(trim(s).slice(0, MAX_LEN))
  if (!s || s === orig || nameProblem(s)) return null
  return s
}

/** { code, message, suggestion } for the name, or null when it is fine. lang = 'fa' | 'en'. */
export function checkName(raw, lang = 'fa', maxLen = MAX_LEN) {
  const code = nameProblem(raw, maxLen)
  if (!code) return null
  const sug = suggestName(raw)
  return { code, message: MESSAGES[code][lang === 'en' ? 1 : 0].replace('{n}', maxLen),
    suggestion: sug && sug.length > maxLen ? sug.slice(0, maxLen) : sug }
}
