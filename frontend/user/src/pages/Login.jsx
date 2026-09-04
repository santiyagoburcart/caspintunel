import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { apiError } from '../lib/api'
import { Alert, Field, PasswordField, Spinner } from '../components/ui'

function AuthShell({ title, children }) {
  const { lang, setLang } = useI18n()
  return (
    <div className="min-h-full aurora grid place-items-center p-4">
      <div className="card w-full max-w-sm">
        <div className="mb-4 flex items-center justify-between">
          <h1 className="text-xl font-bold">{title}</h1>
          <button type="button" className="btn-ghost text-xs"
            onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}>
            {lang === 'fa' ? 'EN' : 'فا'}
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

export default function Login() {
  const { t } = useI18n()
  const { login } = useAuth()
  const nav = useNavigate()
  const [f, setF] = useState({ username: '', password: '' })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setErr('')
    try { await login(f.username, f.password); nav('/') }
    catch (e2) { setErr(apiError(e2, t('login_failed'))) }
    finally { setBusy(false) }
  }

  return (
    <AuthShell title={t('login')}>
      <form onSubmit={submit} className="space-y-3">
        <Alert>{err}</Alert>
        <Field label={t('username')}>
          <input className="input" value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} autoFocus />
        </Field>
        <PasswordField label={t('password')} value={f.password} autoComplete="current-password"
          onChange={(e) => setF({ ...f, password: e.target.value })} />
        <button className="btn-primary w-full" disabled={busy}>{busy ? <Spinner /> : t('login')}</button>
        <div className="flex justify-between text-sm text-muted">
          <Link to="/register" className="hover:text-primary">{t('register')}</Link>
          <Link to="/reset" className="hover:text-primary">{t('forgot')}</Link>
        </div>
      </form>
    </AuthShell>
  )
}

export { AuthShell }
