import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { Spinner } from './ui'

/** Fetches an image from an authenticated API path as a blob (a plain <img src>
 *  wouldn't carry the JWT). Used for the service QR code. */
export function AuthImage({ path, alt = '', className = '' }) {
  const [src, setSrc] = useState(null)
  const [state, setState] = useState('loading')

  useEffect(() => {
    if (!path) { setState('error'); return }
    let dead = false
    let objectUrl
    setState('loading')
    api.get(path, { responseType: 'blob' })
      .then((r) => {
        if (dead) return
        objectUrl = URL.createObjectURL(r.data)
        setSrc(objectUrl)
        setState('ok')
      })
      .catch(() => !dead && setState('error'))
    return () => { dead = true; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [path])

  if (state === 'loading') return <div className="grid h-40 w-40 place-items-center"><Spinner /></div>
  if (state === 'error') return null
  return <img src={src} alt={alt} className={className} />
}
