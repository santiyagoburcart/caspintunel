// PasarGuard admin passwords (v1.27) — the same rule the server checks before calling
// PasarGuard (apps/agency/admin_crud.py password_problem / generate_password):
// 12+ characters, 2+ upper-case, 2+ lower-case, 2+ digits, one of SPECIALS, no username.
export const SPECIALS = '#.$@!%&*-_+=?'
const UP = 'ABCDEFGHJKLMNPQRSTUVWXYZ'
const LO = 'abcdefghijkmnpqrstuvwxyz'
const DG = '23456789'

export const PW_RULE = {
  fa: 'رمز ادمین باید حداقل ۱۲ نویسه باشد و دست‌کم ۲ حرف بزرگ انگلیسی، ۲ حرف کوچک، ۲ رقم و یک نماد از # . $ @ ! % & * - _ + = ? داشته باشد و نام کاربری در آن نباشد.',
  en: 'Admin password: at least 12 characters with 2+ upper-case, 2+ lower-case, 2+ digits and one of # . $ @ ! % & * - _ + = ? — and not containing the username.',
}

const rnd = (n) => { const a = new Uint32Array(1); crypto.getRandomValues(a); return a[0] % n }
const pick = (set) => set[rnd(set.length)]

export function genAdminPassword(length = 16) {
  const out = [pick(UP), pick(UP), pick(LO), pick(LO), pick(DG), pick(DG), pick(SPECIALS), pick(SPECIALS)]
  while (out.length < length) out.push(pick(UP + LO + DG))
  for (let i = out.length - 1; i > 0; i--) { const j = rnd(i + 1); [out[i], out[j]] = [out[j], out[i]] }
  return out.join('')
}

/** null = fine, else a reason code (length | upper | lower | digits | special | charset | username) */
export function passwordProblem(pw, username = '') {
  pw = String(pw || '')
  const count = (re) => (pw.match(re) || []).length
  if (pw.length < 12) return 'length'
  if (count(/[A-Z]/g) < 2) return 'upper'
  if (count(/[a-z]/g) < 2) return 'lower'
  if (count(/[0-9]/g) < 2) return 'digits'
  if (![...pw].some((c) => SPECIALS.includes(c))) return 'special'
  if (/[\s]/.test(pw) || [...pw].some((c) => c.charCodeAt(0) > 126)) return 'charset'
  if (username && pw.toLowerCase().includes(String(username).toLowerCase())) return 'username'
  return null
}
