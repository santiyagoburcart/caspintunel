import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useI18n, enumLabel } from '../lib/i18n'
import { jalali, toman } from '../lib/format'
import { Alert, Spinner } from '../components/ui'
import { ReceiptThumb } from '../components/ReceiptThumb'

const T = {
  fa: {
    title: 'تراکنش‌ها', all: 'همه', pending: 'در انتظار', approved: 'تأییدشده', rejected: 'ردشده',
    amount: 'مبلغ', user: 'کاربر', source: 'منبع', card: 'کارت', confirmer: 'تأییدکننده',
    date: 'تاریخ', receipt: 'رسید', plan: 'پلن', none: 'تراکنشی نیست', reason: 'دلیل رد',
    src_site: 'سایت', src_bot: 'ربات', by_admin: 'ادمین', by_system: 'سیستم پیامک',
    not_delivered: 'پرداخت تأییدشده ولی سرویس تحویل نشده — به‌صورت خودکار تلاش مجدد می‌شود',
  },
  en: {
    title: 'Transactions', all: 'All', pending: 'Pending', approved: 'Approved', rejected: 'Rejected',
    amount: 'Amount', user: 'User', source: 'Source', card: 'Card', confirmer: 'Confirmed by',
    date: 'Date', receipt: 'Receipt', plan: 'Plan', none: 'No transactions', reason: 'Reject reason',
    src_site: 'Website', src_bot: 'Bot', by_admin: 'admin', by_system: 'SMS system',
    not_delivered: 'Payment approved but service not delivered — auto-retrying',
  },
}

const FILTERS = ['', 'pending', 'approved', 'rejected']

export default function Transactions() {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const [rows, setRows] = useState(null)
  const [status, setStatus] = useState('')
  const [err, setErr] = useState('')

  const load = () => {
    setRows(null); setErr('')
    api.get(`/admin/transactions/${status ? `?status=${status}` : ''}`)
      .then((r) => setRows(r.data.results ?? r.data))
      .catch(() => { setRows([]); setErr(lang === 'fa' ? 'خطا در دریافت' : 'Failed to load') })
  }
  useEffect(load, [status])

  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold">{s.title}</h1>
      <Alert>{err}</Alert>
      <div className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button key={f || 'all'} onClick={() => setStatus(f)}
            className={`btn-ghost text-sm ${status === f ? 'text-primary' : ''}`}>
            {f ? s[f] : s.all}
          </button>
        ))}
      </div>

      {rows === null ? (
        <div className="grid place-items-center py-16"><Spinner /></div>
      ) : rows.length === 0 ? (
        <div className="card text-center text-muted">{s.none}</div>
      ) : (
        <div className="space-y-2">
          {rows.map((r) => (
            <div key={r.id} className="card flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
              <span className="font-bold">{toman(r.amount, lang)}</span>
              <span className="rounded-full px-2 py-0.5 text-xs"
                style={{ background: 'color-mix(in srgb, var(--c-secondary) 16%, transparent)', color: 'var(--c-secondary)' }}>
                {r.order_source === 'bot' ? s.src_bot : s.src_site}
              </span>
              <StatusPill status={r.status} s={s} />
              <span className="text-muted">{s.user}: {r.user}</span>
              {r.plan_name && <span className="text-muted">{s.plan}: {r.plan_name}</span>}
              {r.card && <span dir="ltr" className="text-muted">{s.card}: {r.card}</span>}
              {r.confirmer && (
                <span className="text-muted">
                  {s.confirmer}: {r.confirmer === 'admin' ? s.by_admin : r.confirmer === 'SMS system' ? s.by_system : r.confirmer}
                </span>
              )}
              {r.status === 'rejected' && r.reject_reason && (
                <span className="text-warning">{s.reason}: {r.reject_reason}</span>
              )}
              {r.status === 'approved' && r.order_status === 'paid' && (
                <span className="w-full text-xs text-warning">⚠ {s.not_delivered}</span>
              )}
              <span className="ms-auto text-xs text-muted">{jalali(r.created_at, true, lang)}</span>
              {r.receipt_url && <ReceiptThumb url={r.receipt_url} alt={s.receipt} />}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function StatusPill({ status, s }) {
  const c = { pending: 'warning', approved: 'success', rejected: 'danger' }[status] || 'text-muted'
  const color = `var(--c-${c})`
  return (
    <span className="rounded-full px-2 py-0.5 text-xs"
      style={{ background: `color-mix(in srgb, ${color} 18%, transparent)`, color }}>
      {s[status] || status}
    </span>
  )
}
