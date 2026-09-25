// Shared Jalali date-range picker — renders as a centred dialog on desktop
// and a bottom sheet on mobile (same markup, `.drp-*` media queries switch
// the chrome), so Accounting and Transactions both get one real, working
// implementation instead of two divergent one-offs.
import { useMemo, useState } from 'react'
import { useI18n } from '../lib/i18n'
import { digits } from '../lib/format'
import {
  WEEKDAYS, addMonths, cellFromISO, cmpDay, monthMatrix, monthName, presetRanges, toISO, todayCell,
} from '../lib/jalaliCalendar'

const T = {
  fa: {
    title: 'انتخاب بازهٔ تاریخ', quick: 'انتخاب سریع بازه:',
    from: 'شروع', to: 'پایان', apply: 'اعمال فیلتر', cancel: 'انصراف', clear: 'پاک‌سازی',
    range_label: 'بازهٔ انتخابی', single_title: 'انتخاب تاریخ', picked: 'تاریخ انتخابی', apply_single: 'تأیید تاریخ',
  },
  en: {
    title: 'Select a date range', quick: 'Quick select:',
    from: 'Start', to: 'End', apply: 'Apply filter', cancel: 'Cancel', clear: 'Clear',
    range_label: 'Selected range', single_title: 'Pick a date', picked: 'Selected date', apply_single: 'Use this date',
  },
}

function Grid({ jy, jm, from, to, onPick, lang }) {
  const weeks = useMemo(() => monthMatrix(jy, jm), [jy, jm])
  const wd = WEEKDAYS[lang] || WEEKDAYS.fa
  return (
    <div className="drp-grid">
      <div className="drp-wd-row">
        {wd.map((w, i) => <span key={i} className={i === 6 ? 'drp-fri' : ''}>{w}</span>)}
      </div>
      <div className="drp-days">
        {weeks.flat().map((c) => {
          const isFrom = from && cmpDay(c, from) === 0
          const isTo = to && cmpDay(c, to) === 0
          const inRange = from && to && cmpDay(c, from) > 0 && cmpDay(c, to) < 0
          const cls = ['drp-day']
          if (!c.inMonth) cls.push('out')
          if (c.isFriday) cls.push('fri')
          if (isFrom || isTo) cls.push('edge')
          else if (inRange) cls.push('in')
          return (
            <button type="button" key={c.key} className={cls.join(' ')} onClick={() => onPick(c)}>
              {digits(c.jd, lang)}
            </button>
          )
        })}
      </div>
    </div>
  )
}

/** value: { from: 'YYYY-MM-DD' | '', to: 'YYYY-MM-DD' | '' } (ISO, ready for the API).
 * `single`: pick one day (from === to); `initial` (ISO) preselects it;
 * "clear" then means "no date". */
export function DateRangeModal({ open, onClose, onApply, extra, single = false, initial = '', title, clearLabel }) {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const init = initial ? cellFromISO(initial) : null
  const [cursor, setCursor] = useState(init || todayCell())
  const [pick, setPick] = useState({ from: init, to: null })
  if (!open) return null

  const presets = presetRanges(lang)

  const handlePick = (c) => {
    if (single) { setPick({ from: c, to: null }); return }
    setPick((p) => {
      if (!p.from || p.to) return { from: c, to: null }
      return cmpDay(c, p.from) < 0 ? { from: c, to: p.from } : { from: p.from, to: c }
    })
  }
  const applyPreset = (pr) => { setPick({ from: pr.from, to: pr.to }); setCursor(pr.from) }
  // DOM order is always [previous, label, next] — the browser mirrors the
  // visual position for dir="rtl"; only the glyph needs to flip to keep
  // pointing the right way for each reading direction.
  const nav = (delta) => setCursor((cur) => addMonths(cur.jy, cur.jm, delta))

  const apply = () => {
    if (!pick.from) return
    const to = pick.to || pick.from
    onApply({ from: toISO(pick.from.jy, pick.from.jm, pick.from.jd), to: toISO(to.jy, to.jm, to.jd) })
    onClose()
  }
  const clear = () => { setPick({ from: null, to: null }); onApply({ from: '', to: '' }); onClose() }

  const dayLabel = (c) => `${digits(c.jd, lang)} ${monthName(c.jm, lang)} ${digits(c.jy, lang)}`

  return (
    <div className="drp-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="drp-sheet card" role="dialog" aria-modal="true">
        <div className="drp-handle" />
        <div className="drp-head">
          <h2 className="font-bold text-sm">{title || (single ? s.single_title : s.title)}</h2>
          <button type="button" className="drp-icon-btn" onClick={onClose} aria-label={s.cancel}>✕</button>
        </div>

        <div className="drp-body">
          {!single && <div className="drp-presets">
            <span className="drp-presets-label">{s.quick}</span>
            <div className="drp-preset-row">
              {presets.map((pr) => (
                <button key={pr.key} type="button" className="drp-chip" onClick={() => applyPreset(pr)}>
                  {pr.label}
                </button>
              ))}
            </div>
          </div>}

          <div className="drp-summary">
            {single ? (
              <span className="drp-summary-item">
                <i className="drp-dot drp-dot--from" />{s.picked}: <b>{pick.from ? dayLabel(pick.from) : '—'}</b>
              </span>
            ) : (<>
              <span className="drp-summary-item">
                <i className="drp-dot drp-dot--from" />{s.from}: <b>{pick.from ? dayLabel(pick.from) : '—'}</b>
              </span>
              <span className="drp-summary-item">
                <i className="drp-dot drp-dot--to" />{s.to}: <b>{pick.to ? dayLabel(pick.to) : (pick.from ? dayLabel(pick.from) : '—')}</b>
              </span>
            </>)}
          </div>

          <div className="drp-nav">
            <button type="button" className="drp-nav-btn" onClick={() => nav(-1)} aria-label="prev">{lang === 'fa' ? '›' : '‹'}</button>
            <span className="drp-nav-label">{monthName(cursor.jm, lang)} {digits(cursor.jy, lang)}</span>
            <button type="button" className="drp-nav-btn" onClick={() => nav(1)} aria-label="next">{lang === 'fa' ? '‹' : '›'}</button>
          </div>

          <Grid jy={cursor.jy} jm={cursor.jm} from={pick.from} to={pick.to} onPick={handlePick} lang={lang} />

          {extra}
        </div>

        <div className="drp-foot">
          <button type="button" className="btn-ghost text-sm" onClick={clear}>{clearLabel || s.clear}</button>
          <button type="button" className="btn-ghost text-sm" onClick={onClose}>{s.cancel}</button>
          <button type="button" className="btn-primary text-sm" disabled={!pick.from} onClick={apply}>{single ? s.apply_single : s.apply}</button>
        </div>
      </div>
    </div>
  )
}

export const DRP_CSS = `
.drp-backdrop { position: fixed; inset: 0; z-index: 70; background: color-mix(in srgb, #0b1220 62%, transparent);
  backdrop-filter: blur(3px); display: flex; align-items: center; justify-content: center; padding: 20px; overflow-y: auto; }
.drp-sheet { width: 100%; max-width: 420px; padding: 0; overflow: hidden; max-height: 92vh; display: flex; flex-direction: column; }
.drp-handle { display: none; }
.drp-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 16px 18px; border-bottom: 1px solid var(--c-border); flex-shrink: 0; }
.drp-icon-btn { padding: 6px; border-radius: 9px; color: var(--c-text-muted); }
.drp-icon-btn:hover { color: var(--c-text); background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); }
.drp-body { padding: 16px 18px; display: flex; flex-direction: column; gap: 14px; overflow-y: auto; }
.drp-foot { display: flex; justify-content: flex-end; gap: 8px; padding: 14px 18px; border-top: 1px solid var(--c-border); flex-shrink: 0; }

.drp-presets-label { font-size: 11.5px; font-weight: 600; color: var(--c-text-muted); display: block; margin-bottom: 6px; }
.drp-preset-row { display: flex; flex-wrap: wrap; gap: 6px; }
.drp-chip { padding: 5px 12px; border-radius: 999px; font-size: 12px; font-weight: 600; border: 1px solid var(--c-border);
  background: transparent; color: var(--c-text-muted); white-space: nowrap; transition: .15s; }
.drp-chip:hover { border-color: var(--c-primary); color: var(--c-primary); }

.drp-summary { display: flex; flex-wrap: wrap; gap: 8px; }
.drp-summary-item { flex: 1; min-width: 130px; display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--c-text-muted);
  padding: 8px 10px; border-radius: 10px; background: color-mix(in srgb, var(--c-text-muted) 6%, transparent); }
.drp-summary-item b { color: var(--c-text); font-weight: 700; }
.drp-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.drp-dot--from { background: var(--c-primary); } .drp-dot--to { background: var(--c-success); }

.drp-nav { display: flex; align-items: center; justify-content: center; gap: 14px; }
.drp-nav-btn { width: 30px; height: 30px; border-radius: 9px; border: 1px solid var(--c-border); background: transparent;
  color: var(--c-text-muted); font-size: 16px; display: grid; place-items: center; }
.drp-nav-btn:hover { color: var(--c-primary); border-color: var(--c-primary); }
.drp-nav-label { font-size: 13px; font-weight: 700; min-width: 110px; text-align: center; }

.drp-grid { display: flex; flex-direction: column; gap: 4px; }
.drp-wd-row, .drp-days { display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; }
.drp-wd-row span { text-align: center; font-size: 11px; font-weight: 600; color: var(--c-text-muted); padding-bottom: 6px; }
.drp-fri { color: var(--c-danger) !important; }
.drp-day { aspect-ratio: 1; border-radius: 9px; font-size: 12.5px; color: var(--c-text); background: transparent; border: 0;
  font-family: 'JetBrains Mono', ui-monospace, monospace; }
.drp-day:hover { background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); }
.drp-day.out { color: var(--c-text-muted); opacity: .4; }
.drp-day.fri:not(.edge):not(.in) { color: var(--c-danger); }
.drp-day.in { background: color-mix(in srgb, var(--c-primary) 16%, transparent); color: var(--c-primary); }
.drp-day.edge { background: var(--c-primary); color: #fff; font-weight: 700; }

@media (max-width: 640px) {
  .drp-backdrop { align-items: flex-end; padding: 0; }
  .drp-sheet { max-width: none; border-radius: 20px 20px 0 0; max-height: 88vh; }
  .drp-handle { display: block; width: 36px; height: 4px; border-radius: 999px; background: var(--c-border); margin: 10px auto 0; flex-shrink: 0; }
}
`
