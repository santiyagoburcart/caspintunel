import { useEffect, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { DataTable } from '../components/DataTable'
import { Alert, Spinner, Toggle } from '../components/ui'

/** Generic list + toggle-active screen for Pages / Themes / Roles. */
export function Pages() {
  const { t } = useI18n()
  return <CrudList title={t('pages')} url="/admin/pages/" columns={[
    { key: 'slug', label: t('slug') },
    { key: 'title_fa', label: t('title') },
  ]} />
}

export function Themes() {
  const { t } = useI18n()
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  const load = () => api.get('/admin/themes/')
    .then((r) => setRows(r.data.results))
    .catch(() => { setRows([]); setErr(t('load_error')) })
  useEffect(() => { load() }, [])
  const activate = async (id) => {
    setErr('')
    try { await api.post(`/admin/themes/${id}/activate/`); load() }
    catch (e) { setErr(apiError(e)) }
  }
  if (!rows) return <div className="grid place-items-center py-16"><Spinner /></div>
  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold">{t('themes')}</h1>
      <Alert>{err}</Alert>
      <DataTable rows={rows} empty={t('none_found')} columns={[
        { key: 'name', label: t('name') },
        { key: 'is_active', label: t('active'), render: (r) => (r.is_active ? '✓' : '—') },
        {
          key: 'act', label: '', render: (r) => (!r.is_active && (
            <button className="btn-ghost text-xs" onClick={() => activate(r.id)}>{t('activate')}</button>
          )),
        },
      ]} />
    </div>
  )
}

export function Roles() {
  const { t } = useI18n()
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    api.get('/admin/roles/')
      .then((r) => setRows(r.data.results))
      .catch(() => { setRows([]); setErr(t('load_error')) })
  }, [])
  if (!rows) return <div className="grid place-items-center py-16"><Spinner /></div>
  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold">{t('roles')}</h1>
      <Alert>{err}</Alert>
      <DataTable rows={rows} empty={t('none_found')} columns={[
        { key: 'name', label: t('name') },
        { key: 'description', label: t('description'), render: (r) => r.description || '—' },
        { key: 'permission_codes', label: t('permissions'), render: (r) => (r.permission_codes || []).length },
      ]} />
    </div>
  )
}

function CrudList({ title, url, columns }) {
  const { t } = useI18n()
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  const load = () => api.get(url)
    .then((r) => setRows(r.data.results))
    .catch(() => { setRows([]); setErr(t('load_error')) })
  useEffect(() => { load() }, [])
  const toggle = async (r) => {
    setErr('')
    try { await api.patch(`${url}${r.id}/`, { is_active: !r.is_active }); load() }
    catch (e) { setErr(apiError(e)) }
  }
  if (!rows) return <div className="grid place-items-center py-16"><Spinner /></div>
  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold">{title}</h1>
      <Alert>{err}</Alert>
      <DataTable rows={rows} empty={t('none_found')} columns={[...columns, {
        key: 'is_active', label: t('active'),
        render: (r) => <Toggle checked={r.is_active} onChange={() => toggle(r)} label={t('active')} />,
      }]} />
    </div>
  )
}
