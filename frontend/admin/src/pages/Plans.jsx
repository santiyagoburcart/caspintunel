import { useEffect, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { toman } from '../lib/format'
import { DataTable } from '../components/DataTable'
import { Alert, Spinner } from '../components/ui'

const GB = 1024 ** 3
const blank = { type: 'fixed', name_fa: '', name_en: '', price: 0, discount_percent: 0,
  data_limit: 0, duration_days: 0, is_active: true }

export default function Plans() {
  const { t } = useI18n()
  const [rows, setRows] = useState(null)
  const [edit, setEdit] = useState(null)
  const [err, setErr] = useState('')

  const load = () => api.get('/admin/plans/').then((r) => setRows(r.data.results)).catch(() => setRows([]))
  useEffect(() => { load() }, [])

  const save = async (e) => {
    e.preventDefault(); setErr('')
    try {
      const body = { ...edit, data_limit: Number(edit.data_limit) || 0, duration_days: Number(edit.duration_days) || null }
      if (edit.id) await api.patch(`/admin/plans/${edit.id}/`, body)
      else await api.post('/admin/plans/', body)
      setEdit(null); load()
    } catch (e2) { setErr(apiError(e2)) }
  }
  const del = async (id) => { if (confirm('حذف شود؟')) { await api.delete(`/admin/plans/${id}/`); load() } }

  if (rows === null) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">{t('plans')}</h1>
        <button className="btn-primary text-sm" onClick={() => setEdit({ ...blank })}>{t('create')}</button>
      </div>
      <Alert>{err}</Alert>

      {edit && (
        <form onSubmit={save} className="card grid gap-3 sm:grid-cols-2">
          <label className="text-sm">نوع
            <select className="input" value={edit.type} onChange={(e) => setEdit({ ...edit, type: e.target.value })}>
              <option value="fixed">ثابت</option><option value="custom_volume">حجمی</option>
            </select>
          </label>
          <label className="text-sm">نام (فا)<input className="input" value={edit.name_fa} onChange={(e) => setEdit({ ...edit, name_fa: e.target.value })} /></label>
          <label className="text-sm">قیمت<input className="input" type="number" value={edit.price} onChange={(e) => setEdit({ ...edit, price: e.target.value })} /></label>
          <label className="text-sm">تخفیف %<input className="input" type="number" value={edit.discount_percent} onChange={(e) => setEdit({ ...edit, discount_percent: e.target.value })} /></label>
          <label className="text-sm">حجم (بایت، ۰=نامحدود)<input className="input" type="number" value={edit.data_limit} onChange={(e) => setEdit({ ...edit, data_limit: e.target.value })} /></label>
          <label className="text-sm">مدت (روز)<input className="input" type="number" value={edit.duration_days || ''} onChange={(e) => setEdit({ ...edit, duration_days: e.target.value })} /></label>
          {edit.type === 'custom_volume' && <>
            <label className="text-sm">قیمت هر گیگ<input className="input" type="number" value={edit.price_per_gb || ''} onChange={(e) => setEdit({ ...edit, price_per_gb: e.target.value })} /></label>
            <label className="text-sm">حداکثر گیگ<input className="input" type="number" value={edit.max_gb || ''} onChange={(e) => setEdit({ ...edit, max_gb: e.target.value })} /></label>
          </>}
          <label className="text-sm flex items-center gap-2"><input type="checkbox" checked={edit.is_active} onChange={(e) => setEdit({ ...edit, is_active: e.target.checked })} /> فعال</label>
          <div className="col-span-full flex gap-2">
            <button className="btn-primary text-sm">{t('save')}</button>
            <button type="button" className="btn-ghost text-sm" onClick={() => setEdit(null)}>انصراف</button>
          </div>
        </form>
      )}

      <DataTable
        columns={[
          { key: 'name_fa', label: 'نام' },
          { key: 'type', label: 'نوع' },
          { key: 'data_limit', label: 'حجم', render: (r) => (r.data_limit ? `${r.data_limit / GB} GB` : 'نامحدود') },
          { key: 'duration_days', label: 'مدت', render: (r) => r.duration_days || '∞' },
          { key: 'price', label: 'قیمت', render: (r) => toman(r.price) },
          { key: 'is_active', label: 'فعال', render: (r) => (r.is_active ? '✓' : '—') },
          { key: 'act', label: '', render: (r) => (
            <span className="flex gap-1">
              <button className="btn-ghost text-xs" onClick={() => setEdit(r)}>✎</button>
              <button className="btn-ghost text-xs" onClick={() => del(r.id)}>🗑</button>
            </span>
          ) },
        ]}
        rows={rows}
      />
    </div>
  )
}
