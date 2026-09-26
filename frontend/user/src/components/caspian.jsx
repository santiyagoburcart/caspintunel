/**
 * Shared components for the "Caspian" theme (dark "Caspian Tunnel" /
 * light "Azure Telemetry" — one `style` key, switched by the user's own
 * dark-mode toggle, see index.css). Purely presentational and token-driven
 * (var(--c-*) / var(--csp-*)) so they render correctly in whichever
 * variant is active — nothing here reads the active theme directly.
 *
 * These are building blocks for later phases to compose real pages from;
 * this phase only ships the components themselves, not any page wiring.
 */
import { useRef } from 'react'
import { useI18n } from '../lib/i18n'
import { ADMIN_URL } from '../lib/site'

let idSeq = 0

/** Brand mark for the Caspian theme — uploaded logo if present, else a
 *  gradient shield tile. Used in the header + auth pages. */
export function CaspianBrand({ logo, size = 36 }) {
  if (logo) {
    return <img src={logo} alt="" className="csp-brandmark" style={{ width: size, height: size }} />
  }
  return (
    <span className="csp-brandmark csp-brandmark--fallback" style={{ width: size, height: size }} aria-hidden="true">
      <svg viewBox="0 0 24 24" width={size * 0.5} height={size * 0.5} fill="none" stroke="#fff"
        strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        <path d="M9 12l2 2 4-4" />
      </svg>
    </span>
  )
}

/** Centered auth card shell for the Caspian theme (Register / Reset /
 *  VerifyEmail). Login has its own richer split-card layout. */
export function CaspianAuthShell({ title, children, hideAdminLink = false }) {
  const { lang, setLang, t } = useI18n()
  return (
    <div className="csp-authshell">
      <div className="csp-authshell-card">
        <div className="csp-authshell-head">
          <CaspianBrand size={34} />
          <h1 className="csp-headline csp-authshell-title">{title}</h1>
          <button type="button" className="csp-lang" onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}>
            {lang === 'fa' ? 'EN' : 'فا'}
          </button>
        </div>
        {children}
        {!hideAdminLink && (
          <div className="csp-authshell-back">
            <a href={ADMIN_URL} className="csp-link">{t('foot_admin')}</a>
          </div>
        )}
      </div>
    </div>
  )
}

/** Circular SVG progress gauge (double-ring: track + animated value arc). */
export function Gauge({ percent, size = 96, stroke = 10, label, valueText, color }) {
  const pct = Math.max(0, Math.min(100, percent ?? 0))
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const gid = useRef('csp-gauge-' + (++idSeq)).current
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="csp-gauge">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={color || 'var(--csp-gauge-from)'} />
          <stop offset="1" stopColor={color || 'var(--csp-gauge-to)'} />
        </linearGradient>
      </defs>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--c-border)" strokeWidth={stroke} />
      <circle
        cx={size / 2} cy={size / 2} r={r} fill="none" stroke={`url(#${gid})`} strokeWidth={stroke}
        strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c - (pct / 100) * c}
        transform={`rotate(-90 ${size / 2} ${size / 2})`} style={{ transition: 'stroke-dashoffset .6s ease' }}
      />
      <text x="50%" y={label ? '46%' : '52%'} textAnchor="middle" dominantBaseline="middle" className="csp-gauge-value"
        fontSize={size * 0.2}>
        {valueText ?? `${Math.round(pct)}%`}
      </text>
      {label && (
        <text x="50%" y="66%" textAnchor="middle" dominantBaseline="middle" className="csp-gauge-label" fontSize={size * 0.1}>
          {label}
        </text>
      )}
    </svg>
  )
}

/** Live pulsating status dot — center solid, expanding ripple ring. */
export function PulseDot({ status = 'success' }) {
  const cls = status === 'success' ? '' : ' ' + status
  return <span className={'csp-pulse' + cls} aria-hidden="true" />
}

/** Segmented pill tab bar / filter bar. `tabs`: [{ value, label }]. */
export function PillTabs({ tabs, value, onChange }) {
  return (
    <div className="csp-tabs" role="tablist">
      {tabs.map((tb) => (
        <button
          key={tb.value} type="button" role="tab" aria-selected={tb.value === value}
          className={'csp-tab' + (tb.value === value ? ' active' : '')}
          onClick={() => onChange?.(tb.value)}
        >
          {tb.label}
        </button>
      ))}
    </div>
  )
}

/** Build an SVG line+area path (any viewBox) from a plain numeric series. */
function sparkPath(vals, w, h, pad = 3) {
  const pts = (vals || []).filter((v) => typeof v === 'number')
  if (pts.length < 2) return { line: '', area: '' }
  const max = Math.max(...pts, 1)
  const min = Math.min(0, ...pts)
  const span = Math.max(max - min, 1)
  const step = w / (pts.length - 1)
  const xy = pts.map((v, i) => [i * step, h - pad - ((v - min) / span) * (h - pad * 2)])
  const line = xy.map(([x, y], i) => (i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1)).join(' ')
  return { line, area: `${line} L${w} ${h} L0 ${h} Z` }
}

/**
 * Sparkline / area chart. By default it's a bare SVG block (matches the
 * Stitch reference: card sparklines and the big traffic charts sit directly
 * on the card background, pinned to the bottom edge, no bordered box).
 * Pass `well` to drop it into the recessed "chart well" surface instead
 * (useful outside a card, e.g. a standalone chart tile), and `gridLines`
 * to draw N evenly-spaced dashed horizontal guides behind the curve.
 */
export function Sparkline({ series, width = 240, height = 64, color, well = false, gridLines = 0 }) {
  const gid = useRef('csp-spark-' + (++idSeq)).current
  const { line, area } = sparkPath(series, width, height)
  const chart = (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" style={{ display: 'block' }}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={color || 'var(--csp-gauge-to)'} stopOpacity="0.4" />
          <stop offset="1" stopColor={color || 'var(--csp-gauge-to)'} stopOpacity="0" />
        </linearGradient>
      </defs>
      {gridLines > 0 && Array.from({ length: gridLines }).map((_, i) => {
        const y = (height / (gridLines + 1)) * (i + 1)
        return (
          <line key={i} x1="0" y1={y} x2={width} y2={y} stroke="var(--c-text-muted)"
            strokeOpacity="0.25" strokeWidth="1" strokeDasharray="4 4" />
        )
      })}
      {area && <path d={area} fill={`url(#${gid})`} />}
      {line && (
        <path d={line} fill="none" stroke={color || 'var(--csp-gauge-to)'} strokeWidth="2"
          strokeLinejoin="round" strokeLinecap="round" className="csp-glow-path" />
      )}
    </svg>
  )
  return well ? <div className="csp-chart-well" style={{ padding: 8 }}>{chart}</div> : chart
}
