import { useEffect, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali, toman } from '../lib/format'
import { Alert, Spinner } from '../components/ui'

const T = {
  fa: {
    title: 'صف تأیید پرداخت', none: 'موردی برای بررسی نیست',
    user: 'کاربر', order: 'سفارش', receipt: 'رسید', no_receipt: 'رسیدی پیوست نشده',
    reject_reason: 'دلیل رد؟', unspecified: 'نامشخص', load_fail: 'دریافت فهرست ناموفق بود',
  },
  en: {
    title: 'Payment approval queue', none: 'Nothing to review',
    user: 'User', order: 'Order', receipt: 'Receipt', no_receipt: 'No receipt attached',
    reject_reason: 'Rejection reason?', unspecified: 'unspecified', load_fail: 'Failed to load the queue',
  },
}

export default function Payments() {
  const { t, lang } = useI18n()
  const s = T[lang] || T.fa
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  const [busyId, setBusyId] = useState(null)

  const load = () =>
    api.get('/admin/payments/pending/')
      .then((r) => { setRows(r.data.results); setErr('') })
      .catch(() => { setRows([]); setErr(s.load_fail) })

  useEffect(() => { load() }, [])

  const act = async (id, kind) => {
    setErr('')
    let reason
    if (kind === 'reject') {
      reason = prompt(s.reject_reason)
      if (reason === null) return
    }
    setBusyId(id)
    try {
      if (kind === 'approve') await api.post(`/payments/${id}/approve/`)
      else await api.post(`/payments/${id}/reject/`, { reason: reason || s.unspecified })
      await load()
    } catch (e) { setErr(apiError(e)) } finally { setBusyId(null) }
  }

  if (rows === null) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold">{s.title}</h1>
      <Alert>{err}</Alert>
      {rows.length === 0 && !err && (
        <div className="card text-center text-muted">{s.none}</div>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        {rows.map((p) => (
          <div key={p.id} className="card space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="font-bold">{toman(p.amount, lang)}</span>
              <span className="text-xs text-muted">{jalali(p.created_at, true, lang)}</span>
            </div>
            <div className="text-sm text-muted">
              {s.user}: {p.user} · {s.order} #{p.order_id}
            </div>
            <Receipt url={p.receipt_url} s={s} />
            <div className="flex gap-2 pt-1">
              <button className="btn-primary text-sm" disabled={busyId === p.id}
                onClick={() => act(p.id, 'approve')}>
                {busyId === p.id ? '…' : t('approve')}
              </button>
              <button className="btn-ghost text-sm" disabled={busyId === p.id}
                onClick={() => act(p.id, 'reject')}>
                {t('reject')}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/** Lazily fetches the receipt as an authenticated blob (the URL is not public). */
function Receipt({ url, s }) {
  const [src, setSrc] = useState(null)
  const [state, setState] = useState('idle') // idle | loading | ok | error

  useEffect(() => {
    if (!url) return
    let revoked = false
    let objectUrl
    setState('loading')
    api.get(url.replace(/^\/api\/v1/, ''), { responseType: 'blob' })
      .then((r) => {
        if (revoked) return
        objectUrl = URL.createObjectURL(r.data)
        setSrc(objectUrl)
        setState('ok')
      })
      .catch(() => !revoked && setState('error'))
    return () => { revoked = true; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [url])

  if (!url) return <div className="text-xs text-muted">{s.no_receipt}</div>
  if (state === 'loading') return <div className="grid h-24 place-items-center"><Spinner /></div>
  if (state === 'error') return <div className="text-xs text-danger">— {s.receipt} —</div>
  return (
    <a href={src} target="_blank" rel="noreferrer">
      <img src={src} alt={s.receipt} className="max-h-48 rounded-xl border"
        style={{ borderColor: 'var(--c-border)' }} />
    </a>
  )
}
