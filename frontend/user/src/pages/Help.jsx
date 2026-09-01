import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { Spinner } from '../components/ui'

export default function Help() {
  const { t, lang } = useI18n()
  const [pages, setPages] = useState(null)
  const [open, setOpen] = useState(null)

  useEffect(() => {
    api.get('/pages/').then((r) => { setPages(r.data.results || r.data); setOpen((r.data.results || r.data)[0]?.slug) })
      .catch(() => setPages([]))
  }, [])

  if (pages === null) return <div className="grid place-items-center py-16"><Spinner /></div>
  const cur = pages.find((p) => p.slug === open)

  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold">{t('pages')}</h1>
      {pages.length === 0 ? (
        <div className="card text-center text-muted">{t('no_content')}</div>
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            {pages.map((p) => (
              <button key={p.slug} onClick={() => setOpen(p.slug)}
                className={`btn-ghost text-sm ${open === p.slug ? 'text-primary' : ''}`}>
                {(lang === 'fa' ? p.title_fa : p.title_en) || p.title_fa}
              </button>
            ))}
          </div>
          <div className="card whitespace-pre-wrap leading-7">
            {(lang === 'fa' ? cur?.body_fa : cur?.body_en) || cur?.body_fa || t('no_content')}
          </div>
        </>
      )}
    </div>
  )
}
