import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { Alert, Field, PasswordField, Spinner } from '../components/ui'
import { AuthShell } from './Login'

export default function ResetPassword() {
  const { t } = useI18n()
  const [sp] = useSearchParams()
  const token = sp.get('token')
  const [identifier, setIdentifier] = useState('')
  const [pw, setPw] = useState('')
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const request = async (e) => {
    e.preventDefault(); setBusy(true); setErr(''); setMsg('')
    try {
      const { data } = await api.post('/auth/password/reset/', { identifier })
      setMsg(data.detail)
    } catch (e2) { setErr(apiError(e2)) } finally { setBusy(false) }
  }
  const confirm = async (e) => {
    e.preventDefault(); setBusy(true); setErr(''); setMsg('')
    try {
      const { data } = await api.post('/auth/password/reset/confirm/', { token, new_password: pw })
      setMsg(data.detail)
    } catch (e2) { setErr(apiError(e2)) } finally { setBusy(false) }
  }

  return (
    <AuthShell title={t('reset')}>
      <form onSubmit={token ? confirm : request} className="space-y-3">
        <Alert>{err}</Alert>
        <Alert kind="success">{msg}</Alert>
        {token ? (
          <PasswordField label={t('new_password')} value={pw} autoComplete="new-password"
            onChange={(e) => setPw(e.target.value)} />
        ) : (
          <Field label={`${t('username')} / ${t('email')}`}>
            <input className="input" dir="ltr" value={identifier} onChange={(e) => setIdentifier(e.target.value)} autoComplete="username" autoCapitalize="none" autoCorrect="off" spellCheck={false} />
          </Field>
        )}
        <button className="btn-primary w-full" disabled={busy}>{busy ? <Spinner /> : t('submit')}</button>
        <div className="text-sm text-muted"><Link to="/login" className="auth-link hover:text-primary">{t('login')}</Link></div>
      </form>
    </AuthShell>
  )
}
