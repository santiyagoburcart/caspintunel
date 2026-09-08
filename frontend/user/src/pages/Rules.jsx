import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { Spinner } from '../components/ui'

// The "Rules" CMS page (slug: rules) as a top-level screen.
export default function Rules() {
  const { t, lang } = useI18n()
  const [page, setPage] = useState(undefined)

  useEffect(() => {
    api.get('/pages/rules/')
      .then((r) => setPage(r.data))
      .catch(() => setPage(null))
  }, [])

  if (page === undefined) return <div className="grid place-items-center py-16"><Spinner /></div>

  const title = page && ((lang === 'fa' ? page.title_fa : page.title_en) || page.title_fa)
  const body = page && ((lang === 'fa' ? page.body_fa : page.body_en) || page.body_fa)

  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold">{title || t('rules')}</h1>
      <div className="card whitespace-pre-wrap leading-7">
        {body || t('no_content')}
      </div>
    </div>
  )
}
