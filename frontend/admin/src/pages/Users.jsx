import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali } from '../lib/format'
import { DataTable } from '../components/DataTable'
import { Spinner } from '../components/ui'

export default function Users() {
  const { t } = useI18n()
  const [rows, setRows] = useState(null)
  const [q, setQ] = useState('')
  const [active, setActive] = useState('')

  const load = () => {
    setRows(null)
    const p = new URLSearchParams()
    if (q) p.set('search', q)
    if (active) p.set('is_active', active)
    api.get(`/admin/users/?${p}`).then((r) => setRows(r.data.results)).catch(() => setRows([]))
  }
  useEffect(load, [active])

  const toggle = async (u) => {
    await api.post(`/admin/users/${u.id}/${u.is_active ? 'disable' : 'enable'}/`)
    load()
  }

  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold">{t('users')}</h1>
      <div className="flex flex-wrap gap-2">
        <input className="input max-w-xs" placeholder={t('search')} value={q}
          onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && load()} />
        <select className="input max-w-[10rem]" value={active} onChange={(e) => setActive(e.target.value)}>
          <option value="">همه</option><option value="true">فعال</option><option value="false">غیرفعال</option>
        </select>
        <button className="btn-ghost text-sm" onClick={load}>{t('search')}</button>
      </div>
      {rows === null ? <div className="grid place-items-center py-16"><Spinner /></div> : (
        <DataTable
          columns={[
            { key: 'username', label: t('username') },
            { key: 'name', label: 'نام' },
            { key: 'phone', label: 'تلفن' },
            { key: 'source', label: 'منبع' },
            { key: 'service_count', label: 'سرویس' },
            { key: 'created_at', label: 'تاریخ', render: (r) => jalali(r.created_at) },
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
