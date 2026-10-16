import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

// Agency UI kit — one button hierarchy, an accessible overflow menu, a data table
// with sticky sortable headers + density, threshold usage bars, status chips,
// skeletons, empty states. Colours only from theme tokens.

// ── icons (stroke 1.75, 24 grid) ───────────────────────────────────────────
const P = {
  dots: 'M6 12h.01M12 12h.01M18 12h.01',
  search: 'M21 21l-4.3-4.3M11 18a7 7 0 100-14 7 7 0 000 14z',
  x: 'M6 6l12 12M18 6L6 18',
  gauge: 'M12 13l4-4M3.5 17a9 9 0 1117 0',
  infinity: 'M7.5 15c-1.9 0-3.5-1.3-3.5-3s1.6-3 3.5-3c3 0 6 6 9 6 1.9 0 3.5-1.3 3.5-3s-1.6-3-3.5-3c-3 0-6 6-9 6z',
  power: 'M12 3v9M7 6.3a7 7 0 1010 0',
  users: 'M16 19v-1a4 4 0 00-4-4H7a4 4 0 00-4 4v1M9.5 11a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM21 19v-1a4 4 0 00-3-3.9M16 4.1a3.5 3.5 0 010 6.8',
  reset: 'M4 4v6h6M20 20v-6h-6M5.6 15A8 8 0 0019 17M18.4 9A8 8 0 005 7',
  link: 'M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1-1',
  copy: 'M9 9h10v10H9zM5 15V5h10',
  qr: 'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h2v2h-2zM18 18h2v2h-2zM14 18h2v2h-2zM18 14h2v2h-2z',
  chevron: 'M9 6l6 6-6 6',
  arrowUp: 'M12 19V5M5 12l7-7 7 7',
  arrowDown: 'M12 5v14M19 12l-7 7-7-7',
  rows: 'M4 6h16M4 12h16M4 18h16',
  rowsTight: 'M4 5h16M4 9.5h16M4 14h16M4 18.5h16',
  wallet: 'M3 7h16a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7zm0 0l13-3v3M16 13h.01',
  plus: 'M12 5v14M5 12h14',
  download: 'M12 4v11M7 10l5 5 5-5M5 20h14',
  open: 'M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 01-1 1H5a1 1 0 01-1-1V7a1 1 0 011-1h5',
  check: 'M5 12l5 5 9-10',
  sync: 'M20 11a8 8 0 00-14.9-3M4 13a8 8 0 0014.9 3M4 4v4h4M20 20v-4h-4',
}
export function Icon({ name, size = 18 }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="1.75"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"><path d={P[name]} /></svg>
  )
}

// ── buttons ──────────────────────────────────────────────────────────────
/** variant: primary (one per view) | tonal | ghost | danger */
export function Btn({ variant = 'tonal', icon, children, loading, disabled, className = '', ...rest }) {
  return (
    <button type="button" className={`agk-btn agk-btn--${variant} ${className}`} disabled={disabled || loading}
      aria-busy={loading || undefined} {...rest}>
      {loading ? <span className="agk-spin" aria-hidden="true" /> : icon && <Icon name={icon} size={17} />}
      {children && <span>{children}</span>}
    </button>
  )
}

// ── overflow menu (⋯) ────────────────────────────────────────────────────
/** items: [{ label, icon, onClick, danger, disabled, hint }] (null entries = divider) */
export function Menu({ items, label, align = 'end' }) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState(null)
  const btn = useRef(null)
  const menu = useRef(null)
  const place = () => {
    const r = btn.current.getBoundingClientRect()
    const rtl = getComputedStyle(btn.current).direction === 'rtl'
    const below = window.innerHeight - r.bottom
    setPos({ top: below > 260 ? r.bottom + 4 : undefined, bottom: below > 260 ? undefined : window.innerHeight - r.top + 4,
      [((align === 'end') !== rtl) ? 'right' : 'left']: (align === 'end') !== rtl ? window.innerWidth - r.right : r.left })
  }
  useLayoutEffect(() => { if (open) place() }, [open])
  useEffect(() => {
    if (!open) return
    const first = () => menu.current?.querySelector('[role="menuitem"]:not([disabled])')?.focus()
    requestAnimationFrame(first)
    const onDoc = (e) => { if (!menu.current?.contains(e.target) && !btn.current?.contains(e.target)) setOpen(false) }
    const onKey = (e) => {
      if (e.key === 'Escape') { setOpen(false); btn.current?.focus() }
      if (e.key === 'Tab') setOpen(false)
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault()
        const els = [...menu.current.querySelectorAll('[role="menuitem"]:not([disabled])')]
        const i = els.indexOf(document.activeElement)
        els[(i + (e.key === 'ArrowDown' ? 1 : -1) + els.length) % els.length]?.focus()
      }
    }
    const onScroll = () => setOpen(false)
    document.addEventListener('mousedown', onDoc); document.addEventListener('keydown', onKey)
    window.addEventListener('scroll', onScroll, true); window.addEventListener('resize', onScroll)
    return () => {
      document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey)
      window.removeEventListener('scroll', onScroll, true); window.removeEventListener('resize', onScroll)
    }
  }, [open])
  return (
    <>
      <button ref={btn} type="button" className="agk-btn agk-btn--ghost agk-btn--icon" aria-label={label}
        aria-haspopup="menu" aria-expanded={open} onClick={(e) => { e.stopPropagation(); e.preventDefault(); setOpen((v) => !v) }}>
        <Icon name="dots" size={20} />
      </button>
      {open && pos && createPortal(
        <div ref={menu} role="menu" aria-label={label} className="agk-menu" style={pos} onClick={(e) => e.stopPropagation()}>
          {items.filter((x) => x !== undefined).map((it, i) => it === null ? <div key={i} className="agk-menu-sep" role="separator" /> : (
            <button key={i} type="button" role="menuitem" className={'agk-menu-item' + (it.danger ? ' danger' : '')}
              disabled={it.disabled} title={it.hint || undefined}
              onClick={() => { setOpen(false); it.onClick?.() }}>
              {it.icon && <Icon name={it.icon} size={17} />}<span>{it.label}</span>
              {it.hint && it.disabled && <small>{it.hint}</small>}
            </button>
          ))}
        </div>, document.body)}
    </>
  )
}

// ── data bits ────────────────────────────────────────────────────────────
/** "12.46 TB" → number + muted unit (formatting only) */
export function Qty({ v, unl }) {
  if (v == null) return <span className="agk-muted">—</span>
  if (v === 'Unlimited') return <span className="agk-qty agk-muted">{unl}</span>
  const m = String(v).match(/^([+-]?[\d.,]+)\s*([A-Za-z]+)$/)
  if (!m) return <bdi dir="ltr" className="agk-qty">{v}</bdi>
  return <bdi dir="ltr" className="agk-qty">{m[1]}<span className="agk-unit">{m[2]}</span></bdi>
}

export function Money({ n, lang, signed }) {
  const v = Number(n || 0)
  const s = Math.abs(v).toLocaleString('en-US')
  return (
    <bdi dir="ltr" className="agk-qty" data-sign={signed ? (v > 0 ? 'owes' : v < 0 ? 'credit' : 'zero') : undefined}>
      {v < 0 ? '−' : ''}{s}<span className="agk-unit">{lang === 'en' ? 'T' : 'تومان'}</span>
    </bdi>
  )
}

/** usage % from the server; green < 70 · orange 70–90 · red ≥ 90 (the bar caps at 100 for width only) */
export function Usage({ pct, compact }) {
  const n = Number(pct) || 0
  const tone = n >= 90 ? 'high' : n >= 70 ? 'mid' : 'ok'
  return (
    <span className={'agk-usage' + (compact ? ' compact' : '')} data-tone={tone}>
      <span className="agk-usage-track" aria-hidden="true"><i style={{ inlineSize: `${Math.min(n, 100)}%` }} /></span>
      <bdi dir="ltr" className="agk-usage-pct">{n}%</bdi>
    </span>
  )
}

export function Status({ code, label }) {
  return <span className="agk-status" data-st={code}><i aria-hidden="true" />{label}</span>
}

export function Skeleton({ rows = 6, cols = 5 }) {
  return (
    <div className="agk-skel" aria-busy="true" aria-live="polite">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="agk-skel-row">{Array.from({ length: cols }).map((__, c) => <span key={c} style={{ inlineSize: `${40 + ((r * 7 + c * 13) % 45)}%` }} />)}</div>
      ))}
    </div>
  )
}

export function Empty({ title, text, action }) {
  return (
    <div className="agk-empty">
      <p className="agk-empty-t">{title}</p>
      {text && <p className="agk-empty-d">{text}</p>}
      {action}
    </div>
  )
}

export function SortTh({ k, sort, setSort, children, num }) {
  const on = sort.k === k
  return (
    <th className={num ? 'num' : ''} aria-sort={on ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
      <button type="button" className={'agk-sort' + (on ? ' on' : '')} onClick={() => setSort({ k, dir: on ? -sort.dir : -1 })}>
        {children}<Icon name={on && sort.dir === 1 ? 'arrowUp' : 'arrowDown'} size={13} />
      </button>
    </th>
  )
}

export function useDensity(key = 'agk_density') {
  const [d, setD] = useState(() => { try { return localStorage.getItem(key) || 'comfortable' } catch { return 'comfortable' } })
  const set = (v) => { setD(v); try { localStorage.setItem(key, v) } catch { /* private mode */ } }
  return [d, set]
}

export const AGK_CSS = `
.agk-btn { --h: 36px; display: inline-flex; align-items: center; justify-content: center; gap: 6px; height: var(--h); min-width: var(--h);
  padding: 0 14px; border-radius: 10px; border: 1px solid transparent; font: inherit; font-size: 13.5px; font-weight: 650; line-height: 1;
  cursor: pointer; white-space: nowrap; transition: background-color .15s, color .15s, border-color .15s, box-shadow .15s; touch-action: manipulation; }
.agk-btn:focus-visible { outline: 2px solid var(--c-primary); outline-offset: 2px; }
.agk-btn:disabled { opacity: .45; cursor: not-allowed; }
.agk-btn--primary { background: color-mix(in srgb, var(--c-primary) 86%, #000); color: #fff; }
.agk-btn--primary:hover:not(:disabled) { background: color-mix(in srgb, var(--c-primary) 74%, #000); }
.agk-btn--primary:active:not(:disabled) { background: color-mix(in srgb, var(--c-primary) 64%, #000); }
.agk-btn--tonal { background: color-mix(in srgb, var(--c-primary) 11%, transparent); color: var(--c-primary-fg); }
.agk-btn--tonal:hover:not(:disabled) { background: color-mix(in srgb, var(--c-primary) 17%, transparent); }
.agk-btn--tonal:active:not(:disabled) { background: color-mix(in srgb, var(--c-primary) 24%, transparent); }
.agk-btn--ghost { background: transparent; color: var(--c-text); }
.agk-btn--ghost:hover:not(:disabled) { background: color-mix(in srgb, var(--c-text) 7%, transparent); }
.agk-btn--ghost:active:not(:disabled) { background: color-mix(in srgb, var(--c-text) 12%, transparent); }
.agk-btn--danger { background: color-mix(in srgb, var(--c-danger) 10%, transparent); color: var(--c-danger-fg); }
.agk-btn--danger:hover:not(:disabled) { background: color-mix(in srgb, var(--c-danger) 16%, transparent); }
.agk-btn--icon { padding: 0; width: var(--h); }
.agk-spin { width: 15px; height: 15px; border-radius: 50%; border: 2px solid currentColor; border-inline-end-color: transparent; animation: agk-r .7s linear infinite; }
@keyframes agk-r { to { transform: rotate(360deg); } }
@media (max-width: 767px), (pointer: coarse) { .agk-btn { --h: 44px; } }

.agk-menu { position: fixed; z-index: 1000; min-width: 220px; max-width: min(92vw, 320px); padding: 6px; border-radius: 12px;
  background: linear-gradient(var(--c-surface), var(--c-surface)), var(--c-bg); border: 1px solid var(--c-border);
  box-shadow: 0 12px 32px -12px rgb(0 0 0 / .28); }
.agk-menu-item { display: flex; align-items: center; gap: 10px; width: 100%; min-height: 38px; padding: 0 10px; border-radius: 8px;
  border: 0; background: transparent; color: var(--c-text); font: inherit; font-size: 13.5px; font-weight: 550; text-align: start; cursor: pointer; }
.agk-menu-item:hover:not(:disabled), .agk-menu-item:focus-visible { background: color-mix(in srgb, var(--c-text) 7%, transparent); outline: none; }
.agk-menu-item.danger { color: var(--c-danger-fg); }
.agk-menu-item:disabled { opacity: .5; cursor: not-allowed; }
.agk-menu-item small { margin-inline-start: auto; font-size: 11px; color: var(--c-muted-fg); }
.agk-menu-sep { height: 1px; margin: 5px 4px; background: var(--c-border); }
@media (max-width: 767px), (pointer: coarse) { .agk-menu-item { min-height: 44px; } }

.agk-qty { font-family: 'JetBrains Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; white-space: nowrap; }
.agk-unit { font-family: Inter, Vazirmatn, sans-serif; font-size: .78em; font-weight: 500; color: var(--c-muted-fg); margin-inline-start: 3px; }
.agk-qty[data-sign="owes"] { color: var(--c-danger-fg); } .agk-qty[data-sign="credit"] { color: var(--c-success-fg); }
.agk-muted { color: var(--c-muted-fg); }

.agk-usage { display: inline-flex; align-items: center; gap: 8px; min-width: 120px; }
.agk-usage-track { flex: 1; height: 6px; border-radius: 999px; background: color-mix(in srgb, var(--c-text) 9%, transparent); overflow: hidden; min-width: 56px; }
.agk-usage-track i { display: block; height: 100%; border-radius: inherit; background: var(--c-success); }
.agk-usage[data-tone="mid"] i { background: var(--c-warning); } .agk-usage[data-tone="high"] i { background: var(--c-danger); }
.agk-usage-pct { font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; font-size: 12.5px; min-width: 44px; text-align: end; }
.agk-usage[data-tone="mid"] .agk-usage-pct { color: var(--c-warning-fg); } .agk-usage[data-tone="high"] .agk-usage-pct { color: var(--c-danger-fg); }
.agk-usage.compact { min-width: 0; }

.agk-status { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 600; color: var(--c-text); white-space: nowrap; }
.agk-status i { width: 7px; height: 7px; border-radius: 50%; background: var(--c-success); flex-shrink: 0; }
.agk-status[data-st="panel_disabled"] i { background: var(--c-danger); } .agk-status[data-st="pamp_limited"] i { background: var(--c-warning); }

.agk-skel { display: flex; flex-direction: column; }
.agk-skel-row { display: flex; gap: 16px; padding: 14px 4px; border-bottom: 1px solid var(--c-border); }
.agk-skel-row span { height: 10px; border-radius: 6px; flex: 1; background: color-mix(in srgb, var(--c-text) 8%, transparent); animation: agk-pulse 1.4s ease-in-out infinite; }
@keyframes agk-pulse { 50% { opacity: .45; } }
@media (prefers-reduced-motion: reduce) { .agk-skel-row span, .agk-spin { animation: none; } }

.agk-empty { padding: 40px 16px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 6px; }
.agk-empty-t { font-weight: 700; }
.agk-empty-d { font-size: 13px; color: var(--c-muted-fg); margin-bottom: 8px; }

.agk-sort { display: inline-flex; align-items: center; gap: 4px; font: inherit; font-weight: 650; color: inherit; background: none; border: 0; padding: 4px 0; cursor: pointer; white-space: nowrap; }
.agk-sort svg { opacity: 0; transition: opacity .15s; }
.agk-sort:hover svg, .agk-sort.on svg, .agk-sort:focus-visible svg { opacity: .9; }
.agk-sort.on { color: var(--c-text); }
.agk-sort:focus-visible { outline: 2px solid var(--c-primary); outline-offset: 2px; border-radius: 4px; }
`
