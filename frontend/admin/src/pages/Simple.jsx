import { useEffect, useState } from 'react'
import { api, apiError } from '../lib/api'
import { DataTable } from '../components/DataTable'
import { Alert, Spinner } from '../components/ui'

/** Generic list + toggle-active screen for Pages / Themes / Roles. */
export function Pages() {
  return <CrudList title="صفحات" url="/admin/pages/" columns={[
    { key: 'slug', label: 'اسلاگ' }, { key: 'title_fa', label: 'عنوان' },
    { key: 'is_active', label: 'فعال', render: (r) => (r.is_active ? '✓' : '—') },
  ]} />
}

export function Themes() {
  const [rows, setRows] = useState(null)
  const load = () => api.get('/admin/themes/').then((r) => setRows(r.data.results)).catch(() => setRows([]))
  useEffect(() => { load() }, [])
  const activate = async (id) => { await api.post(`/admin/themes/${id}/activate/`); load() }
  if (!rows) return <div className="grid place-items-center py-16"><Spinner /></div>
  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold">پوسته‌ها</h1>
      <DataTable rows={rows} columns={[
        { key: 'name', label: 'نام' },
        { key: 'is_active', label: 'فعال', render: (r) => (r.is_active ? '✓' : '—') },
        { key: 'act', label: '', render: (r) => (!r.is_active && <button className="btn-ghost text-xs" onClick={() => activate(r.id)}>فعال‌سازی</button>) },
      ]} />
    </div>
  )
}

export function Roles() {
  const [rows, setRows] = useState(null)
  useEffect(() => { api.get('/admin/roles/').then((r) => setRows(r.data.results)).catch(() => setRows([])) }, [])
  if (!rows) return <div className="grid place-items-center py-16"><Spinner /></div>
  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold">نقش‌ها</h1>
      <DataTable rows={rows} columns={[
        { key: 'name', label: 'نام' },
        { key: 'description', label: 'توضیح' },
        { key: 'permission_codes', label: 'دسترسی‌ها', render: (r) => (r.permission_codes || []).length },
      ]} />
    </div>
  )
}

function CrudList({ title, url, columns }) {
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  const load = () => api.get(url).then((r) => setRows(r.data.results)).catch(() => setRows([]))
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
      <DataTable rows={rows} columns={[...columns, {
        key: 'act', label: '', render: (r) => <button className="btn-ghost text-xs" onClick={() => toggle(r)}>{r.is_active ? 'غیرفعال' : 'فعال'}</button>,
      }]} />
    </div>
  )
}
