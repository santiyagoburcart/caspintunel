// Only in preview builds (VITE_PREVIEW=1, scripts/preview.sh): a fixed strip on
// every page saying this is the preview and that actions hit the LIVE API.
// Its height is published as --preview-h so sticky headers sit below it.
import { useEffect, useRef } from 'react'
import { IS_PREVIEW } from '../lib/site'

export default function PreviewBanner() {
  const ref = useRef(null)
  useEffect(() => {
    if (!IS_PREVIEW || !ref.current) return undefined
    const root = document.documentElement
    root.setAttribute('data-preview', '')
    const set = () => root.style.setProperty('--preview-h', `${ref.current.offsetHeight}px`)
    set()
    const ro = new ResizeObserver(set)
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])
  if (!IS_PREVIEW) return null
  return (
    <div ref={ref} className="preview-banner" role="status">
      <span lang="fa" dir="rtl">نسخه پیش‌نمایش — عملیات انجام‌شده واقعی است</span>
      <span aria-hidden="true" className="preview-banner-sep">/</span>
      <span lang="en" dir="ltr">Preview version — actions are real</span>
    </div>
  )
}
