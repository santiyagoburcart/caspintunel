// Modern 3D illustrations for visual accents (dashboard cards, hubs, empty
// states, success screens, plan cards). Source: Microsoft Fluent Emoji 3D
// (MIT, see assets/3d/LICENSE.txt), resized to 128px WebP (~3 KB each) and
// bundled — no CDN, works offline. Decorative by default (alt="").
import { Children } from 'react'

const FILES = import.meta.glob('../assets/3d/*.webp', { eager: true, import: 'default' })
const SRC = Object.fromEntries(Object.entries(FILES).map(([p, url]) => [p.split('/').pop().replace('.webp', ''), url]))

export function Art({ name, size = 48, alt = '', className = '', style }) {
  const src = SRC[name]
  if (!src) return null
  return (
    <img src={src} width={size} height={size} alt={alt} aria-hidden={alt ? undefined : true}
      loading="lazy" decoding="async" draggable={false} className={`art ${className}`} style={style} />
  )
}

/** Art on a soft tinted tile (Settings hub rows, KPI cards). */
export function ArtTile({ name, size = 44, tile = 56, className = '' }) {
  return (
    <span className={`art-tile ${className}`} style={{ width: tile, height: tile }}>
      <Art name={name} size={size} />
    </span>
  )
}

/** Empty / zero state: illustration + title + short guidance + optional action. */
export function EmptyState({ art = 'inbox', title, text, children, compact = false }) {
  return (
    <div className="empty-state" role="status" style={compact ? { padding: '20px 12px' } : undefined}>
      <Art name={art} size={compact ? 56 : 72} />
      {title && <div className="empty-state-title">{title}</div>}
      {text && <div className="empty-state-text">{text}</div>}
      {Children.count(children) > 0 && children}
    </div>
  )
}

export const ART_NAMES = Object.keys(SRC)
