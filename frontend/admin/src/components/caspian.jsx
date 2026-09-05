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

/** Circular SVG progress gauge (double-ring: track + animated value arc). */
export function Gauge({ percent, size = 96, stroke = 10, label, valueText, color }) {
  const pct = Math.max(0, Math.min(100, percent ?? 0))
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const gid = 'csp-gauge-' + Math.round(r) + '-' + Math.round(pct)
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

/** Sparkline / area chart, drawn inside the recessed "chart well" surface. */
export function Sparkline({ series, width = 240, height = 64, color }) {
  const gid = 'csp-spark-' + width + '-' + height
  const { line, area } = sparkPath(series, width, height)
  return (
    <div className="csp-chart-well" style={{ padding: 8 }}>
      <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={color || 'var(--csp-gauge-to)'} stopOpacity="0.35" />
            <stop offset="1" stopColor={color || 'var(--csp-gauge-to)'} stopOpacity="0" />
          </linearGradient>
        </defs>
        {area && <path d={area} fill={`url(#${gid})`} />}
        {line && (
          <path d={line} fill="none" stroke={color || 'var(--csp-gauge-to)'} strokeWidth="2"
            strokeLinejoin="round" strokeLinecap="round" />
        )}
      </svg>
    </div>
  )
}
