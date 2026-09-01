// Jalali dates via Intl (no dependency). Store/receive UTC, display Persian calendar.
const jf = new Intl.DateTimeFormat('fa-IR-u-ca-persian-nu-latn', {
  year: 'numeric', month: '2-digit', day: '2-digit',
})
const jfTime = new Intl.DateTimeFormat('fa-IR-u-ca-persian-nu-latn', {
  year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
})

const gEn = new Intl.DateTimeFormat('en-GB', { year: 'numeric', month: '2-digit', day: '2-digit' })
const gEnTime = new Intl.DateTimeFormat('en-GB', {
  year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
})

export function jalali(value, withTime = false, lang = 'fa') {
  if (!value) return '—'
  const d = new Date(value)
  if (lang === 'en') return (withTime ? gEnTime : gEn).format(d)
  return (withTime ? jfTime : jf).format(d)
}

export function toman(n, lang = 'fa') {
  if (n == null) return '—'
  const v = Number(n).toLocaleString('en-US')
  return lang === 'en' ? `${v} T` : `${v} تومان`
}

const GB = 1024 ** 3
export function gb(bytes) {
  if (!bytes) return 0
  return Math.round((bytes / GB) * 10) / 10
}
