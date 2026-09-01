// Jalali dates via Intl (no dependency). Store/receive UTC, display Persian calendar.
const jf = new Intl.DateTimeFormat('fa-IR-u-ca-persian-nu-latn', {
  year: 'numeric', month: '2-digit', day: '2-digit',
})
const jfTime = new Intl.DateTimeFormat('fa-IR-u-ca-persian-nu-latn', {
  year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
})

export function jalali(value, withTime = false) {
  if (!value) return '—'
  const d = new Date(value)
  return (withTime ? jfTime : jf).format(d)
}

export function toman(n) {
  if (n == null) return '—'
  return Number(n).toLocaleString('en-US') + ' تومان'
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

const rtf = new Intl.RelativeTimeFormat('fa', { numeric: 'auto' })
const STEPS = [
  ['year', 31536000],
  ['month', 2592000],
  ['day', 86400],
  ['hour', 3600],
  ['minute', 60],
  ['second', 1],
]
// "۳ ساعت پیش" — Persian relative time from an ISO timestamp.
export function relTime(value) {
  if (!value) return '—'
  const diff = (new Date(value).getTime() - Date.now()) / 1000
  const abs = Math.abs(diff)
  for (const [unit, secs] of STEPS) {
    if (abs >= secs || unit === 'second') {
      return rtf.format(Math.round(diff / secs), unit)
    }
  }
  return '—'
}

// Human bytes/sec -> "۴۲ KB/s" (Persian digits).
export function bps(n) {
  if (!n || n < 1) return faDigits(0) + ' B/s'
  const u = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(Math.floor(Math.log(n) / Math.log(1024)), u.length - 1)
  const v = n / 1024 ** i
  return faDigits(v >= 100 ? v.toFixed(0) : v.toFixed(1)) + ' ' + u[i] + '/s'
}
