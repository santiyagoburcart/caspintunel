import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { Alert } from '../components/ui'
import { AuthShell } from './Login'

export default function VerifyEmail() {
  const { t } = useI18n()
  const [sp] = useSearchParams()
  const [state, setState] = useState('loading')
  const [msg, setMsg] = useState('')

  useEffect(() => {
    const token = sp.get('token')
    if (!token) { setState('error'); setMsg(t('invalid_link')); return }
    api.post('/auth/email/verify/confirm/', { token })
      .then((r) => { setState('ok'); setMsg(r.data.detail) })
      .catch((e) => { setState('error'); setMsg(apiError(e)) })
  }, [])

  return (
    <AuthShell title={t('verify_email')}>
      {state === 'loading' && <p className="text-muted">{t('checking')}</p>}
      {state === 'ok' && <Alert kind="success">{msg}</Alert>}
      {state === 'error' && <Alert>{msg}</Alert>}
      <div className="mt-4 text-sm"><Link to="/" className="hover:text-primary">{t('back')}</Link></div>
    </AuthShell>
  )
}
