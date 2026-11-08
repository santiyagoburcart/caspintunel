import { toman } from './format'

// v1.44.1 rounded-amount auto-approve (backend payments_sms/rounded.py): `shortfall` = invoice − paid,
// positive = paid LESS, negative = paid MORE. Returns «کمتر 1,000 تومان» / «بیشتر 1,000 تومان».
export function roundedDiff(shortfall, lang = 'fa') {
  if (shortfall == null || shortfall === '') return ''
  const d = Number(shortfall)
  if (!d) return ''
  const word = lang === 'en' ? (d > 0 ? 'less' : 'more') : (d > 0 ? 'کمتر' : 'بیشتر')
  return `${word} ${toman(Math.abs(d), lang)}`
}
