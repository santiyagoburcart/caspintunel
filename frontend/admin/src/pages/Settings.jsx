import { useEffect, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { Alert, Field, Spinner, Toggle } from '../components/ui'

export default function Settings() {
  const { t, lang } = useI18n()
  const [rows, setRows] = useState(null)
  const [form, setForm] = useState({})
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  const load = () =>
    api.get('/admin/settings/')
      .then((r) => {
        setRows(r.data.settings)
        setForm(Object.fromEntries(r.data.settings.map((s) => [s.key, s.value])))
        setErr('')
      })
      .catch(() => { setRows([]); setErr(t('load_error')) })
  useEffect(() => { load() }, [])

  const save = async (e) => {
    e.preventDefault(); setBusy(true); setErr(''); setMsg('')
    try {
      await api.put('/admin/settings/', form)
      setMsg(t('saved'))
      load()
    } catch (e2) { setErr(apiError(e2)) } finally { setBusy(false) }
  }

  if (!rows) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <form onSubmit={save} className="card mx-auto max-w-lg space-y-4">
      <h1 className="text-lg font-bold">{t('settings')}</h1>
      <Alert>{err}</Alert>
      {msg && <Alert kind="success">{msg}</Alert>}

      {rows.map((s) => {
        const label = t('set_' + s.key)
        if (s.type === 'bool') {
          return (
            <div key={s.key} className="toggle-row">
              <span className="text-sm">{label}</span>
              <Toggle checked={!!form[s.key]}
                onChange={(v) => setForm({ ...form, [s.key]: v })} label={label} />
            </div>
          )
        }
        if (s.key === 'default_language') {
          return (
            <Field key={s.key} label={label}>
              <select className="input" value={form[s.key]}
                onChange={(e) => setForm({ ...form, [s.key]: e.target.value })}>
                <option value="fa">فارسی</option>
                <option value="en">English</option>
              </select>
            </Field>
          )
        }
        if (s.key === 'product_display_mode') {
          return (
            <Field key={s.key} label={label}>
              <select className="input" value={form[s.key]}
                onChange={(e) => setForm({ ...form, [s.key]: e.target.value })}>
                <option value="grouped">{t('display_grouped')}</option>
                <option value="flat">{t('display_flat')}</option>
              </select>
            </Field>
          )
        }
        return (
          <Field key={s.key} label={label}>
            <input className="input" dir="ltr" type="number"
              value={form[s.key]} onChange={(e) => setForm({ ...form, [s.key]: e.target.value })} />
          </Field>
        )
      })}

      <button className="btn-primary" disabled={busy}>{busy ? <Spinner /> : t('save')}</button>
      <p className="text-xs text-muted">
        {lang === 'fa'
          ? 'تغییر فاصلهٔ پشتیبان‌گیری بلافاصله زمان‌بند را به‌روز می‌کند.'
          : 'Changing the backup interval reschedules the backup task immediately.'}
      </p>
    </form>
  )
}
