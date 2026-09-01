import { useEffect, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n, enumLabel } from '../lib/i18n'
import { jalali } from '../lib/format'
import { DataTable } from '../components/DataTable'
import { Alert, Spinner } from '../components/ui'

export default function Users() {
  const { t, lang } = useI18n()
  const [rows, setRows] = useState(null)
  const [q, setQ] = useState('')
  const [active, setActive] = useState('')
  const [err, setErr] = useState('')

  const load = () => {
    setRows(null); setErr('')
    const p = new URLSearchParams()
    if (q) p.set('search', q)
    if (active) p.set('is_active', active)
    api.get(`/admin/users/?${p}`)
      .then((r) => setRows(r.data.results))
      .catch(() => { setRows([]); setErr(t('load_error')) })
  }
  useEffect(load, [active])

  const toggle = async (u) => {
    setErr('')
    try {
      await api.post(`/admin/users/${u.id}/${u.is_active ? 'disable' : 'enable'}/`)
      load()
    } catch (e) { setErr(apiError(e)) }
  }

  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold">{t('users')}</h1>
      <Alert>{err}</Alert>
      <div className="flex flex-wrap gap-2">
        <input className="input max-w-xs" placeholder={t('search')} value={q}
          onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && load()} />
        <select className="input max-w-[10rem]" value={active} onChange={(e) => setActive(e.target.value)}>
          <option value="">{t('all')}</option>
          <option value="true">{t('active')}</option>
          <option value="false">{t('inactive')}</option>
        </select>
        <button className="btn-ghost text-sm" onClick={load}>{t('search')}</button>
      </div>
      {rows === null ? <div className="grid place-items-center py-16"><Spinner /></div> : (
        <DataTable
          empty={t('none_found')}
          columns={[
            { key: 'username', label: t('username') },
            { key: 'name', label: t('name') },
            { key: 'phone', label: t('phone'), render: (r) => r.phone || '—' },
            { key: 'source', label: t('source'), render: (r) => enumLabel(t, 'src_', r.source) },
            { key: 'service_count', label: t('services_total'), render: (r) => r.service_count ?? 0 },
            { key: 'created_at', label: t('date'), render: (r) => jalali(r.created_at, false, lang) },
            {
              key: 'act', label: '', render: (r) => (
                <button className="btn-ghost text-xs" onClick={() => toggle(r)}>
                  {r.is_active ? t('disable') : t('enable')}
                </button>
              ),
            },
          ]}
          rows={rows}
        />
      )}
    </div>
  )
}
