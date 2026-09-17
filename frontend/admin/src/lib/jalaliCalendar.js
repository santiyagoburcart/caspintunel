// Jalali (Persian) calendar-grid helpers built on jalaali-js — used by the
// shared date-range picker (calendar grids, quick presets, month paging).
// `lib/format.js` already covers *display* of a single ISO date; this file
// is only about building/selecting whole months and ranges.
import jalaali from 'jalaali-js'

export const WEEKDAYS = {
  fa: ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج'],
  en: ['Sa', 'Su', 'Mo', 'Tu', 'We', 'Th', 'Fr'],
}
const MONTH_NAMES = {
  fa: ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'],
  en: ['Farvardin', 'Ordibehesht', 'Khordad', 'Tir', 'Mordad', 'Shahrivar', 'Mehr', 'Aban', 'Azar', 'Dey', 'Bahman', 'Esfand'],
}

export function monthName(jm, lang = 'fa') {
  return (MONTH_NAMES[lang] || MONTH_NAMES.fa)[jm - 1]
}

const pad = (n) => String(n).padStart(2, '0')

export function toISO(jy, jm, jd) {
  const g = jalaali.toGregorian(jy, jm, jd)
  return `${g.gy}-${pad(g.gm)}-${pad(g.gd)}`
}

export function toJalaliStr(jy, jm, jd) {
  return `${jy}/${pad(jm)}/${pad(jd)}`
}

function mkCell(jy, jm, jd, inMonth) {
  const g = jalaali.toGregorian(jy, jm, jd)
  const dow = new Date(g.gy, g.gm - 1, g.gd).getDay() // 0=Sun..6=Sat
  return { jy, jm, jd, inMonth, iso: toISO(jy, jm, jd), key: `${jy}-${jm}-${jd}`, isFriday: dow === 5 }
}

export function todayCell() {
  const t = jalaali.toJalaali(new Date())
  return mkCell(t.jy, t.jm, t.jd, true)
}

export function addMonths(jy, jm, delta) {
  let m = jm - 1 + delta
  let y = jy + Math.floor(m / 12)
  m = ((m % 12) + 12) % 12
  return { jy: y, jm: m + 1 }
}

export function addDays(cell, n) {
  const g = jalaali.toGregorian(cell.jy, cell.jm, cell.jd)
  const d = new Date(g.gy, g.gm - 1, g.gd)
  d.setDate(d.getDate() + n)
  const j = jalaali.toJalaali(d)
  return mkCell(j.jy, j.jm, j.jd, true)
}

export function cmpDay(a, b) {
  if (a.jy !== b.jy) return a.jy - b.jy
  if (a.jm !== b.jm) return a.jm - b.jm
  return a.jd - b.jd
}

/** 7-column week grid for one Jalali month, padded with the neighbouring months' days. */
export function monthMatrix(jy, jm) {
  const daysInMonth = jalaali.jalaaliMonthLength(jy, jm)
  const g1 = jalaali.toGregorian(jy, jm, 1)
  const jsDow = new Date(g1.gy, g1.gm - 1, g1.gd).getDay() // 0=Sun..6=Sat
  const leading = (jsDow + 1) % 7 // Saturday-first offset

  const prev = addMonths(jy, jm, -1)
  const prevLen = jalaali.jalaaliMonthLength(prev.jy, prev.jm)
  const cells = []
  for (let i = leading - 1; i >= 0; i -= 1) cells.push(mkCell(prev.jy, prev.jm, prevLen - i, false))
  for (let d = 1; d <= daysInMonth; d += 1) cells.push(mkCell(jy, jm, d, true))
  const next = addMonths(jy, jm, 1)
  let nd = 1
  while (cells.length % 7 !== 0) { cells.push(mkCell(next.jy, next.jm, nd, false)); nd += 1 }

  const weeks = []
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7))
  return weeks
}

/** Quick-select preset ranges, computed from the real current date. */
export function presetRanges(lang = 'fa') {
  const today = todayCell()
  const startOfMonth = mkCell(today.jy, today.jm, 1, true)
  const prevM = addMonths(today.jy, today.jm, -1)
  const prevMonthStart = mkCell(prevM.jy, prevM.jm, 1, true)
  const prevMonthEnd = mkCell(prevM.jy, prevM.jm, jalaali.jalaaliMonthLength(prevM.jy, prevM.jm), true)
  const L = {
    today: { fa: 'امروز', en: 'Today' },
    yesterday: { fa: 'دیروز', en: 'Yesterday' },
    d7: { fa: '۷ روز اخیر', en: 'Last 7 days' },
    d30: { fa: '۳۰ روز اخیر', en: 'Last 30 days' },
    month: { fa: 'ماه جاری', en: 'This month' },
    prevMonth: { fa: 'ماه گذشته', en: 'Last month' },
  }
  const lb = (k) => L[k][lang] || L[k].fa
  return [
    { key: 'today', label: lb('today'), from: today, to: today },
    { key: 'yesterday', label: lb('yesterday'), from: addDays(today, -1), to: addDays(today, -1) },
    { key: 'd7', label: lb('d7'), from: addDays(today, -6), to: today },
    { key: 'd30', label: lb('d30'), from: addDays(today, -29), to: today },
    { key: 'month', label: lb('month'), from: startOfMonth, to: today },
    { key: 'prevMonth', label: lb('prevMonth'), from: prevMonthStart, to: prevMonthEnd },
  ]
}
