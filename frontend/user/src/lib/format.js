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

// { num, unit } — so the Latin number can go in a mono span while the
// Persian "تومان" stays in the normal (non-isolated) run.
export function tomanParts(n, lang = 'fa') {
  if (n == null) return { num: '—', unit: '' }
  return { num: Number(n).toLocaleString('en-US'), unit: lang === 'en' ? 'T' : 'تومان' }
}

const GB = 1024 ** 3
export function gb(bytes) {
  if (!bytes) return 0
  return Math.round((bytes / GB) * 10) / 10
}

const AGO_FA = { y: 'سال', mo: 'ماه', w: 'هفته', d: 'روز', h: 'ساعت', m: 'دقیقه', s: 'ثانیه', now: 'همین الان' }
const AGO_EN = { y: 'y', mo: 'mo', w: 'w', d: 'd', h: 'h', m: 'm', s: 's', now: 'just now' }

export function timeAgo(value, lang = 'fa') {
  if (!value) return '—'
  const diff = Math.floor((Date.now() - new Date(value).getTime()) / 1000)
  if (diff < 5) return lang === 'en' ? AGO_EN.now : AGO_FA.now
  const units = [
    ['y', 31536000], ['mo', 2592000], ['w', 604800], ['d', 86400], ['h', 3600], ['m', 60], ['s', 1],
  ]
  for (const [key, secs] of units) {
    const n = Math.floor(diff / secs)
    if (n >= 1) {
      const labels = lang === 'en' ? AGO_EN : AGO_FA
      return lang === 'en' ? `${n}${labels[key]} ago` : `${n} ${labels[key]} پیش`
    }
  }
  return lang === 'en' ? AGO_EN.now : AGO_FA.now
}
