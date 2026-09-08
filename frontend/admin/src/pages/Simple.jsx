import { useEffect, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { DataTable } from '../components/DataTable'
import { Alert, Field, Spinner, Toggle } from '../components/ui'

function useList(url) {
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  const load = () => api.get(url)
    .then((r) => { setRows(r.data.results ?? r.data); setErr('') })
    .catch(() => { setRows([]); setErr('load') })
  useEffect(() => { load() }, [url])
  return { rows, err, load, setErr }
}

/* ============================ Themes (unchanged behaviour) ============================ */
export function Themes() {
  const { t } = useI18n()
  const { rows, err, load } = useList('/admin/themes/')
  const [e2, setE2] = useState('')
  const activate = async (id) => {
    setE2('')
    try { await api.post(`/admin/themes/${id}/activate/`); load() } catch (e) { setE2(apiError(e)) }
  }
  if (!rows) return <div className="grid place-items-center py-16"><Spinner /></div>
  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold">{t('themes')}</h1>
      <Alert>{err ? t('load_error') : e2}</Alert>
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

/* ================================ Pages — full CRUD ================================ */
const blankPage = { slug: '', title_fa: '', title_en: '', body_fa: '', body_en: '', is_active: true }

export function Pages() {
  const { t, lang } = useI18n()
  const { rows, err, load } = useList('/admin/pages/')
  const [edit, setEdit] = useState(null)
  const [e2, setE2] = useState('')
  const [busy, setBusy] = useState(false)

  const save = async (e) => {
    e.preventDefault(); setBusy(true); setE2('')
    try {
      if (edit.id) await api.patch(`/admin/pages/${edit.id}/`, edit)
      else await api.post('/admin/pages/', edit)
      setEdit(null); load()
    } catch (err2) { setE2(apiError(err2)) } finally { setBusy(false) }
  }
  const del = async (r) => {
    if (!confirm(t('delete_confirm'))) return
    try { await api.delete(`/admin/pages/${r.id}/`); load() } catch (e) { setE2(apiError(e)) }
  }

  if (!rows) return <div className="grid place-items-center py-16"><Spinner /></div>
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">{t('pages')}</h1>
        {!edit && <button className="btn-primary text-sm" onClick={() => setEdit({ ...blankPage })}>{t('create')}</button>}
      </div>
      <Alert>{err ? t('load_error') : e2}</Alert>

      {edit && (
        <form onSubmit={save} className="card grid gap-4 sm:grid-cols-2">
          <Field label={t('slug')}>
            <input className="input" dir="ltr" required disabled={!!edit.id}
              value={edit.slug} onChange={(e) => setEdit({ ...edit, slug: e.target.value })} />
          </Field>
          <label className="flex items-center gap-2 text-sm">
            <Toggle checked={edit.is_active} onChange={(v) => setEdit({ ...edit, is_active: v })} label={t('active')} />
            {t('active')}
          </label>
          <Field label={t('title_fa')}>
            <input className="input" value={edit.title_fa} onChange={(e) => setEdit({ ...edit, title_fa: e.target.value })} />
          </Field>
          <Field label={t('title_en')}>
            <input className="input" dir="ltr" value={edit.title_en} onChange={(e) => setEdit({ ...edit, title_en: e.target.value })} />
          </Field>
          <Field label={t('body_fa')}>
            <textarea className="input" rows={7} value={edit.body_fa} onChange={(e) => setEdit({ ...edit, body_fa: e.target.value })} />
          </Field>
          <Field label={t('body_en')}>
            <textarea className="input" dir="ltr" rows={7} value={edit.body_en} onChange={(e) => setEdit({ ...edit, body_en: e.target.value })} />
          </Field>
          <div className="col-span-full flex gap-2">
            <button className="btn-primary text-sm" disabled={busy}>{busy ? '…' : t('save')}</button>
            <button type="button" className="btn-ghost text-sm" onClick={() => setEdit(null)}>{t('cancel')}</button>
          </div>
        </form>
      )}

      <DataTable rows={rows} empty={t('none_found')} columns={[
        { key: 'slug', label: t('slug'), render: (r) => <span dir="ltr">{r.slug}</span> },
        { key: 'title', label: t('title'), render: (r) => (lang === 'fa' ? r.title_fa : r.title_en) || r.title_fa || '—' },
        { key: 'is_active', label: t('active'), render: (r) => (r.is_active ? '✓' : '—') },
        {
          key: 'act', label: '', render: (r) => (
            <span className="flex gap-1">
              <button className="btn-ghost text-xs" onClick={() => setEdit({ ...r })}>{t('edit')}</button>
              <button className="btn-ghost text-xs" onClick={() => del(r)}>{t('delete')}</button>
            </span>
          ),
        },
      ]} />
    </div>
  )
}

/* ================= Roles + Staff accounts — full CRUD, wired to RBAC ================= */
const blankRole = { name: '', description: '', permission_codes: [] }
const blankStaff = { username: '', password: '', role: '', is_active: true, is_superadmin: false }

export function Roles() {
  const { t } = useI18n()
  const roles = useList('/admin/roles/?limit=200')
  const staff = useList('/admin/staff/?limit=200')
  const perms = useList('/admin/permissions/?limit=200')
  const [role, setRole] = useState(null)
  const [sf, setSf] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const saveRole = async (e) => {
    e.preventDefault(); setBusy(true); setErr('')
    try {
      if (role.id) await api.patch(`/admin/roles/${role.id}/`, role)
      else await api.post('/admin/roles/', role)
      setRole(null); roles.load()
    } catch (e2) { setErr(apiError(e2)) } finally { setBusy(false) }
  }
  const delRole = async (r) => {
    if (!confirm(t('delete_confirm'))) return
    try { await api.delete(`/admin/roles/${r.id}/`); roles.load() } catch (e) { setErr(apiError(e)) }
  }
  const togglePerm = (code) => setRole((r) => ({
    ...r,
    permission_codes: r.permission_codes.includes(code)
      ? r.permission_codes.filter((c) => c !== code)
      : [...r.permission_codes, code],
  }))

  const saveStaff = async (e) => {
    e.preventDefault(); setBusy(true); setErr('')
    const body = { ...sf }
    if (sf.id && !body.password) delete body.password
    if (!body.role) body.role = null
    try {
      if (sf.id) await api.patch(`/admin/staff/${sf.id}/`, body)
      else await api.post('/admin/staff/', body)
      setSf(null); staff.load()
    } catch (e2) { setErr(apiError(e2)) } finally { setBusy(false) }
  }
  const delStaff = async (r) => {
    if (!confirm(t('delete_confirm'))) return
    try { await api.delete(`/admin/staff/${r.id}/`); staff.load() } catch (e) { setErr(apiError(e)) }
  }

  if (!roles.rows || !staff.rows || !perms.rows) {
    return <div className="grid place-items-center py-16"><Spinner /></div>
  }

  return (
    <div className="space-y-6">
      <Alert>{(roles.err || staff.err || perms.err) ? t('load_error') : err}</Alert>

      {/* ---- roles ---- */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-bold">{t('roles')}</h1>
          {!role && <button className="btn-primary text-sm" onClick={() => setRole({ ...blankRole })}>{t('new_role')}</button>}
        </div>

        {role && (
          <form onSubmit={saveRole} className="card space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t('name')}>
                <input className="input" required value={role.name} onChange={(e) => setRole({ ...role, name: e.target.value })} />
              </Field>
              <Field label={t('description')}>
                <input className="input" value={role.description} onChange={(e) => setRole({ ...role, description: e.target.value })} />
              </Field>
            </div>
            <div>
              <div className="label">{t('permissions')}</div>
              <div className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
                {perms.rows.map((p) => (
                  <label key={p.code} className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={role.permission_codes.includes(p.code)}
                      onChange={() => togglePerm(p.code)} />
                    <span>{p.name} <span className="text-muted text-xs" dir="ltr">({p.code})</span></span>
                  </label>
                ))}
              </div>
            </div>
            <div className="flex gap-2">
              <button className="btn-primary text-sm" disabled={busy}>{busy ? '…' : t('save')}</button>
              <button type="button" className="btn-ghost text-sm" onClick={() => setRole(null)}>{t('cancel')}</button>
            </div>
          </form>
        )}

        <DataTable rows={roles.rows} empty={t('none_found')} columns={[
          { key: 'name', label: t('name') },
          { key: 'description', label: t('description'), render: (r) => r.description || '—' },
          { key: 'permission_codes', label: t('permissions'), render: (r) => (r.permission_codes || []).length },
          {
            key: 'act', label: '', render: (r) => (
              <span className="flex gap-1">
                <button className="btn-ghost text-xs" onClick={() => setRole({ ...r, permission_codes: [...(r.permission_codes || [])] })}>{t('edit')}</button>
                <button className="btn-ghost text-xs" onClick={() => delRole(r)}>{t('delete')}</button>
              </span>
            ),
          },
        ]} />
      </section>

      {/* ---- staff accounts ---- */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold">{t('staff_accounts')}</h2>
          {!sf && <button className="btn-primary text-sm" onClick={() => setSf({ ...blankStaff })}>{t('new_staff')}</button>}
        </div>

        {sf && (
          <form onSubmit={saveStaff} className="card grid gap-4 sm:grid-cols-2">
            <Field label={t('username')}>
              <input className="input" dir="ltr" required disabled={!!sf.id}
                value={sf.username} onChange={(e) => setSf({ ...sf, username: e.target.value })} />
            </Field>
            <Field label={t('password') + (sf.id ? ' (—)' : '')}>
              <input className="input" dir="ltr" type="password" minLength={8} required={!sf.id}
                value={sf.password || ''} onChange={(e) => setSf({ ...sf, password: e.target.value })} />
            </Field>
            <Field label={t('role')}>
              <select className="input" value={sf.role || ''} onChange={(e) => setSf({ ...sf, role: e.target.value })}>
                <option value="">— {t('select_role')} —</option>
                {roles.rows.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
            </Field>
            <div className="flex flex-col gap-2 self-end">
              <label className="flex items-center gap-2 text-sm">
                <Toggle checked={sf.is_active} onChange={(v) => setSf({ ...sf, is_active: v })} label={t('active')} />
                {t('active')}
              </label>
              <label className="flex items-center gap-2 text-sm">
                <Toggle checked={sf.is_superadmin} onChange={(v) => setSf({ ...sf, is_superadmin: v })} label={t('superadmin')} />
                {t('superadmin')}
              </label>
            </div>
            <div className="col-span-full flex gap-2">
              <button className="btn-primary text-sm" disabled={busy}>{busy ? '…' : t('save')}</button>
              <button type="button" className="btn-ghost text-sm" onClick={() => setSf(null)}>{t('cancel')}</button>
            </div>
          </form>
        )}

        <DataTable rows={staff.rows} empty={t('none_found')} columns={[
          { key: 'username', label: t('username'), render: (r) => <span dir="ltr">{r.username}</span> },
          { key: 'role_name', label: t('role'), render: (r) => r.is_superadmin ? t('superadmin') : (r.role_name || '—') },
          { key: 'is_active', label: t('active'), render: (r) => (r.is_active ? '✓' : '—') },
          {
            key: 'act', label: '', render: (r) => (
              <span className="flex gap-1">
                <button className="btn-ghost text-xs" onClick={() => setSf({ id: r.id, username: r.username, password: '', role: r.role || '', is_active: r.is_active, is_superadmin: r.is_superadmin })}>{t('edit')}</button>
                <button className="btn-ghost text-xs" onClick={() => delStaff(r)}>{t('delete')}</button>
              </span>
            ),
          },
        ]} />
      </section>
    </div>
  )
}
