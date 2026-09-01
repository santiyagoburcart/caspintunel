import { useEffect, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { Alert, Field, Spinner } from '../components/ui'

const FIELDS = [
  ['site_name_fa', 'نام سایت (فا)'], ['site_name_en', 'نام سایت (EN)'],
  ['site_domain', 'دامنه'], ['support_telegram', 'پشتیبانی تلگرام'],
  ['bot_description_fa', 'توضیح ربات (فا)'], ['bot_description_en', 'توضیح ربات (EN)'],
  ['meta_description', 'meta description'],
]

export default function Branding() {
  const { t } = useI18n()
  const [f, setF] = useState(null)
  const [msg, setMsg] = useState(''); const [err, setErr] = useState(''); const [busy, setBusy] = useState(false)

  useEffect(() => { api.get('/admin/branding/').then((r) => setF(r.data)).catch(() => setF({})) }, [])

  const save = async (e) => {
    e.preventDefault(); setBusy(true); setErr(''); setMsg('')
    try {
      const fd = new FormData()
      FIELDS.forEach(([k]) => fd.append(k, f[k] ?? ''))
      if (f._logo) fd.append('logo', f._logo)
      if (f._favicon) fd.append('favicon', f._favicon)
      const { data } = await api.patch('/admin/branding/', fd)
      setF(data); setMsg('ذخیره شد')
    } catch (e2) { setErr(apiError(e2)) } finally { setBusy(false) }
  }

  if (!f) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <form onSubmit={save} className="card mx-auto max-w-lg space-y-3">
      <h1 className="text-lg font-bold">{t('branding')}</h1>
      <Alert>{err}</Alert><Alert kind="success">{msg}</Alert>
      {FIELDS.map(([k, label]) => (
        <Field key={k} label={label}>
          <input className="input" value={f[k] || ''} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
        </Field>
      ))}
      <Field label="لوگو"><input type="file" accept="image/*" onChange={(e) => setF({ ...f, _logo: e.target.files[0] })} /></Field>
      <Field label="فاویکون"><input type="file" accept="image/*" onChange={(e) => setF({ ...f, _favicon: e.target.files[0] })} /></Field>
      <button className="btn-primary" disabled={busy}>{busy ? <Spinner /> : t('save')}</button>
      <p className="text-xs text-muted">دامنه بدون بازسازی اعمال می‌شود.</p>
    </form>
  )
}
