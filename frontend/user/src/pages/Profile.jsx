import { useState } from 'react'
import { api, apiError } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { useTheme } from '../theme/ThemeProvider'
import { Alert, Copyable, Field, Spinner, Toggle } from '../components/ui'

export default function Profile() {
  const { t, lang, setLang } = useI18n()
  const { mode, toggle, locked } = useTheme()
  const { user, refreshMe } = useAuth()
  const [pw, setPw] = useState({ current_password: '', new_password: '' })
  const [msg, setMsg] = useState(''); const [err, setErr] = useState(''); const [busy, setBusy] = useState(false)

  const changePw = async (e) => {
    e.preventDefault(); setBusy(true); setErr(''); setMsg('')
    try { await api.post('/auth/password/change/', pw); setMsg(t('pw_changed')); setPw({ current_password: '', new_password: '' }) }
    catch (e2) { setErr(apiError(e2)) } finally { setBusy(false) }
  }
  const resend = async () => {
    try { await api.post('/auth/email/verify/resend/'); setMsg(t('verify_sent')) }
    catch (e2) { setErr(apiError(e2)) }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold">{t('profile')}</h1>

      <div className="card space-y-2">
        <div className="flex justify-between"><span className="text-muted">{t('username')}</span><span>{user?.username}</span></div>
        <div className="flex justify-between"><span className="text-muted">{t('email')}</span>
          <span>{user?.email || '—'} {user?.email && !user?.email_verified && <button className="btn-ghost text-xs" onClick={resend}>{t('verify_email')}</button>}</span></div>
        <div className="flex items-center justify-between"><span className="text-muted">{t('referral')}</span>
          <span className="flex items-center gap-2"><code>{user?.referral_code}</code><Copyable text={user?.referral_code || ''} /></span></div>
        <div className="flex justify-between"><span className="text-muted">{t('referral_count')}</span><span>{user?.referral_count}</span></div>
      </div>

      <div className="card">
        {!locked && (
          <div className="toggle-row">
            <span>{t('theme')}: {mode === 'dark' ? t('dark') : t('light')}</span>
            <Toggle checked={mode === 'dark'} onChange={toggle} label={t('theme')} />
          </div>
        )}
        <div className="toggle-row">
          <span>{t('language')}: {lang === 'fa' ? 'فارسی' : 'English'}</span>
          <Toggle checked={lang === 'en'} onChange={(v) => setLang(v ? 'en' : 'fa')} label={t('language')} />
        </div>
      </div>

      <form onSubmit={changePw} className="card space-y-3">
        <h2 className="font-bold">{t('change_password')}</h2>
        <Alert>{err}</Alert>
        <Alert kind="success">{msg}</Alert>
        <Field label={t('current_password')}><input className="input" type="password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} /></Field>
        <Field label={t('new_password')}><input className="input" type="password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} /></Field>
        <button className="btn-primary" disabled={busy}>{busy ? <Spinner /> : t('save')}</button>
      </form>
    </div>
  )
}
