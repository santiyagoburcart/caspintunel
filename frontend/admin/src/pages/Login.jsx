import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { apiError } from '../lib/api'
import { Alert, Field, Spinner } from '../components/ui'

export default function Login() {
  const { t } = useI18n()
  const { login } = useAuth()
  const go = useNavigate()
  const [f, setF] = useState({ username: '', password: '' })
  const [err, setErr] = useState(''); const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr('')
    try { await login(f.username, f.password); go('/') }
    catch (e2) { setErr(apiError(e2, 'ورود ناموفق')) } finally { setBusy(false) }
  }

  return (
    <div className="min-h-full aurora grid place-items-center p-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-3">
        <h1 className="text-xl font-bold">پنل مدیریت</h1>
        <Alert>{err}</Alert>
        <Field label={t('username')}><input className="input" autoFocus value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} /></Field>
        <Field label={t('password')}><input className="input" type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
        <button className="btn-primary w-full" disabled={busy}>{busy ? <Spinner /> : t('login')}</button>
      </form>
    </div>
  )
}
