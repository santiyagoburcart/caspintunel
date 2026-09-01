import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { Alert } from '../components/ui'
import { AuthShell } from './Login'

export default function VerifyEmail() {
  const [sp] = useSearchParams()
  const [state, setState] = useState('loading')
  const [msg, setMsg] = useState('')

  useEffect(() => {
    const token = sp.get('token')
    if (!token) { setState('error'); setMsg('لینک نامعتبر'); return }
    api.post('/auth/email/verify/confirm/', { token })
      .then((r) => { setState('ok'); setMsg(r.data.detail) })
      .catch((e) => { setState('error'); setMsg(apiError(e)) })
  }, [])

  return (
    <AuthShell title="تأیید ایمیل">
      {state === 'loading' && <p className="text-muted">در حال بررسی…</p>}
      {state === 'ok' && <Alert kind="success">{msg}</Alert>}
      {state === 'error' && <Alert>{msg}</Alert>}
      <div className="mt-4 text-sm"><Link to="/" className="hover:text-primary">بازگشت</Link></div>
    </AuthShell>
  )
}
