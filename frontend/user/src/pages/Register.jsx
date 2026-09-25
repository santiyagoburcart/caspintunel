import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { apiError } from '../lib/api'
import { Alert, Field, PasswordField, PhoneInput, Spinner, usePhoneRule } from '../components/ui'
import { localizeError } from '../lib/phone'
import { AuthShell } from './Login'

export default function Register() {
  const { t, lang } = useI18n()
  const phoneRule = usePhoneRule()
  const [tried, setTried] = useState(false)
  const { register } = useAuth()
  const nav = useNavigate()
  const [params] = useSearchParams()
  const [f, setF] = useState({
    username: '', password: '', email: '', name: '', phone: '',
    referral_code: (params.get('ref') || '').toUpperCase(),
  })
  const [agreed, setAgreed] = useState(false)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setTried(true)
    const phoneErr = phoneRule.error(f.phone)
    if (phoneErr) { setErr(phoneErr); return }
    if (!agreed) { setErr(t('must_accept_terms')); return }
    setBusy(true); setErr('')
    try {
      const res = await register({ ...f, terms_accepted: true })
      nav('/', { state: { flash: res.detail } })
    } catch (e2) { setErr(localizeError(apiError(e2, t('register_failed')), lang)) }
    finally { setBusy(false) }
  }

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  return (
    <AuthShell title={t('register')} hideAdminLink>
      <style>{`.reg-terms { display: flex; align-items: flex-start; gap: 8px; font-size: 13px; color: var(--c-text-muted); cursor: pointer; line-height: 1.7; }
.reg-terms input { margin-top: 4px; flex-shrink: 0; width: 18px; height: 18px; accent-color: var(--c-primary); cursor: pointer; }
.reg-terms-link { color: var(--c-primary); font-weight: 700; }
.reg-terms-link:hover { text-decoration: underline; }`}</style>
      <form onSubmit={submit} className="space-y-3">
        <Alert>{err}</Alert>
        <Field label={t('username')}><input className="input" value={f.username} onChange={set('username')} /></Field>
        <PasswordField label={t('password')} value={f.password} autoComplete="new-password" onChange={set('password')} />
        <Field label={t('email')}><input className="input" type="email" value={f.email} onChange={set('email')} /></Field>
        <Field label={t('name')}><input className="input" value={f.name} onChange={set('name')} /></Field>
        <Field label={t('phone') + (phoneRule.required ? ' *' : '')}>
          <PhoneInput value={f.phone} onChange={(v) => setF({ ...f, phone: v })} showError={tried} />
        </Field>
        <Field label={t('referral')}><input className="input" value={f.referral_code} onChange={set('referral_code')} /></Field>
        <label className="reg-terms">
          <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} required />
          <span>
            {t('agree_prefix')}
            <Link to="/terms" target="_blank" rel="noreferrer" className="reg-terms-link">{t('terms_of_service')}</Link>
            {t('agree_suffix')}
          </span>
        </label>
        <button className="btn-primary w-full" disabled={busy || !agreed}>{busy ? <Spinner /> : t('register')}</button>
        <div className="text-sm text-muted"><Link to="/login" className="hover:text-primary">{t('login')}</Link></div>
      </form>
    </AuthShell>
  )
}
