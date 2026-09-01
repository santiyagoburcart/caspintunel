import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { apiError } from '../lib/api'
import { Alert, Field, Spinner } from '../components/ui'
import { AuthShell } from './Login'

export default function Register() {
  const { t } = useI18n()
  const { register } = useAuth()
  const nav = useNavigate()
  const [f, setF] = useState({ username: '', password: '', email: '', name: '', phone: '', referral_code: '' })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setErr('')
    try {
      const res = await register(f)
      nav('/', { state: { flash: res.detail } })
    } catch (e2) { setErr(apiError(e2, t('register_failed'))) }
    finally { setBusy(false) }
  }

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  return (
    <AuthShell title={t('register')}>
      <form onSubmit={submit} className="space-y-3">
        <Alert>{err}</Alert>
        <Field label={t('username')}><input className="input" value={f.username} onChange={set('username')} /></Field>
        <Field label={t('password')}><input className="input" type="password" value={f.password} onChange={set('password')} /></Field>
        <Field label={t('email')}><input className="input" type="email" value={f.email} onChange={set('email')} /></Field>
        <Field label={t('name')}><input className="input" value={f.name} onChange={set('name')} /></Field>
        <Field label={t('phone')}><input className="input" value={f.phone} onChange={set('phone')} /></Field>
        <Field label={t('referral')}><input className="input" value={f.referral_code} onChange={set('referral_code')} /></Field>
        <button className="btn-primary w-full" disabled={busy}>{busy ? <Spinner /> : t('register')}</button>
        <div className="text-sm text-muted"><Link to="/login" className="hover:text-primary">{t('login')}</Link></div>
      </form>
    </AuthShell>
  )
}
