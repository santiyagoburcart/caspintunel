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

// Latin digits -> Persian digits, for any string/number.
export function faDigits(value) {
  if (value == null) return '—'
  return String(value).replace(/\d/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[d])
}

// Locale-aware digits: Persian digits for fa, plain Latin for en.
export function digits(value, lang = 'fa') {
  if (value == null) return '—'
  return lang === 'fa' ? faDigits(value) : String(value)
}

const rtf = {
  fa: new Intl.RelativeTimeFormat('fa', { numeric: 'auto' }),
  en: new Intl.RelativeTimeFormat('en', { numeric: 'auto' }),
}
const STEPS = [
  ['year', 31536000],
  ['month', 2592000],
  ['day', 86400],
  ['hour', 3600],
  ['minute', 60],
  ['second', 1],
]
// Relative time from an ISO timestamp — "۳ ساعت پیش" / "3 hours ago".
export function relTime(value, lang = 'fa') {
  if (!value) return '—'
  const diff = (new Date(value).getTime() - Date.now()) / 1000
  const abs = Math.abs(diff)
  for (const [unit, secs] of STEPS) {
    if (abs >= secs || unit === 'second') {
      return (rtf[lang] || rtf.fa).format(Math.round(diff / secs), unit)
    }
  }
  return '—'
}

// Human bytes/sec -> "۴۲ KB/s" / "42 KB/s".
export function bps(n, lang = 'fa') {
  const u = ['B', 'KB', 'MB', 'GB']
  if (!n || n < 1) return digits(0, lang) + ' B/s'
  const i = Math.min(Math.floor(Math.log(n) / Math.log(1024)), u.length - 1)
  const v = n / 1024 ** i
  return digits(v >= 100 ? v.toFixed(0) : v.toFixed(1), lang) + ' ' + u[i] + '/s'
}
