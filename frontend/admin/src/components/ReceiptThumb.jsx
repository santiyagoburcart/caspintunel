import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { Spinner } from './ui'

/**
 * Fetches a receipt image as an authenticated blob (the URL is never public —
 * it goes through /api/v1/payments/<id>/receipt/ which checks the staff token).
 *
 * `variant="thumb"` (default) shows a small clickable square; `variant="full"`
 * shows a larger inline image.
 */
export function ReceiptThumb({ url, alt = 'receipt', variant = 'thumb' }) {
  const [src, setSrc] = useState(null)
  const [state, setState] = useState('idle') // idle | loading | ok | error

  useEffect(() => {
    if (!url) return
    let dead = false
    let objectUrl
    setState('loading')
    api.get(url.replace(/^\/api\/v1/, ''), { responseType: 'blob' })
      .then((r) => {
        if (dead) return
        objectUrl = URL.createObjectURL(r.data)
        setSrc(objectUrl)
        setState('ok')
      })
      .catch(() => !dead && setState('error'))
    return () => { dead = true; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [url])

  if (!url) return null

  const box = variant === 'full' ? 'max-h-48' : 'h-12 w-12 object-cover'

  if (state === 'loading') {
    return <span className={`grid ${variant === 'full' ? 'h-24' : 'h-12 w-12'} place-items-center`}><Spinner /></span>
  }
  if (state === 'error') return <span className="text-xs text-danger">— {alt} —</span>
  return (
    <a href={src} target="_blank" rel="noreferrer" title={alt}>
      <img src={src} alt={alt} className={`rounded-lg border ${box}`}
        style={{ borderColor: 'var(--c-border)' }} />
    </a>
  )
}
