import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali, toman } from '../lib/format'
import { Alert, Spinner } from '../components/ui'
import { ReceiptThumb } from '../components/ReceiptThumb'

const T = {
  fa: {
    title: 'صف تأیید پرداخت', none: 'موردی برای بررسی نیست', refresh: '↻ تازه‌سازی',
    user: 'کاربر', order: 'سفارش', plan: 'پلن', account: 'نام اکانت', receipt: 'رسید',
    no_receipt: 'رسیدی پیوست نشده', reject_reason: 'دلیل رد؟', unspecified: 'نامشخص',
    load_fail: 'دریافت فهرست ناموفق بود', src_site: 'سایت', src_bot: 'ربات',
    deposit_card: 'واریز به کارت',
  },
  en: {
    title: 'Payment approval queue', none: 'Nothing to review', refresh: '↻ Refresh',
    user: 'User', order: 'Order', plan: 'Plan', account: 'Account', receipt: 'Receipt',
    no_receipt: 'No receipt attached', reject_reason: 'Rejection reason?', unspecified: 'unspecified',
    load_fail: 'Failed to load the queue', src_site: 'Website', src_bot: 'Bot',
    deposit_card: 'Deposited to card',
  },
}

export default function Payments() {
  const { t, lang } = useI18n()
  const navigate = useNavigate()
  const s = T[lang] || T.fa
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  const [busyId, setBusyId] = useState(null)
  const [cards, setCards] = useState([])
  const [cardById, setCardById] = useState({})

  const load = () =>
    api.get('/admin/payments/pending/')
      .then((r) => { setRows(r.data.results); setErr('') })
      .catch(() => { setRows([]); setErr(s.load_fail) })

  useEffect(() => {
    load()
    api.get('/admin/cards/')
      .then((r) => setCards((r.data.results || r.data || []).filter((c) => c.is_active)))
      .catch(() => setCards([]))
  }, [])

  const act = async (id, kind) => {
    setErr('')
    let reason
    if (kind === 'reject') {
      reason = prompt(s.reject_reason)
      if (reason === null) return
    }
    setBusyId(id)
    const body = kind === 'reject'
      ? { reason: reason || s.unspecified }
      : { bank_card: cardById[id] ?? rows.find((r) => r.id === id)?.bank_card ?? cards[0]?.id ?? null }
    try {
      await api.post(`/admin/payments/${id}/${kind}/`, body)
      await load()
    } catch (e) { setErr(apiError(e)) } finally { setBusyId(null) }
  }

  if (rows === null) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">{s.title}</h1>
        <button className="btn-ghost text-sm" onClick={load}>{s.refresh}</button>
      </div>
      <Alert>{err}</Alert>
      {rows.length === 0 && !err && (
        <div className="card text-center text-muted">{s.none}</div>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        {rows.map((p) => (
          <div key={p.id} className="card space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="font-bold">{toman(p.amount, lang)}</span>
              <span className="rounded-full px-2 py-0.5 text-xs"
                style={{ background: 'color-mix(in srgb, var(--c-secondary) 18%, transparent)', color: 'var(--c-secondary)' }}>
                {p.order_source === 'bot' ? s.src_bot : s.src_site}
              </span>
            </div>
            <div className="space-y-0.5 text-sm text-muted">
              <div>{s.user}: {p.user}{p.user_telegram ? ` (@${p.user_telegram})` : ''}</div>
              <div>{s.order} #{p.order_id} · {s.plan}: {p.plan_name || '—'}{p.account_name ? ` · ${s.account}: ${p.account_name}` : ''}</div>
              <div className="text-xs">{jalali(p.created_at, true, lang)}</div>
            </div>
            {p.receipt_url
              ? <ReceiptThumb url={p.receipt_url} alt={s.receipt} variant="full" />
              : <div className="text-xs text-muted">{s.no_receipt}</div>}
            {cards.length > 0 && (
              <label className="block text-xs text-muted">
                {s.deposit_card}
                <select className="input mt-0.5 text-sm"
                  value={cardById[p.id] ?? p.bank_card ?? cards[0]?.id ?? ''}
                  onChange={(e) => setCardById((m) => ({ ...m, [p.id]: Number(e.target.value) }))}>
                  {cards.map((c) => (
                    <option key={c.id} value={c.id}>{c.card_number}{c.holder_name ? ` — ${c.holder_name}` : ''}</option>
                  ))}
                </select>
              </label>
            )}
            <div className="flex flex-wrap gap-2 pt-1">
              <button className="btn-primary text-sm" disabled={busyId === p.id}
                onClick={() => act(p.id, 'approve')}>
                {busyId === p.id ? '…' : t('approve')}
              </button>
              <button className="btn-ghost text-sm" disabled={busyId === p.id}
                onClick={() => act(p.id, 'reject')}>
                {t('reject')}
              </button>
              <button type="button" className="btn-ghost text-sm ms-auto inline-flex items-center gap-1.5"
                style={{ color: 'var(--c-primary)', borderColor: 'color-mix(in srgb, var(--c-primary) 32%, transparent)' }}
                onClick={() => navigate(`/payments/${p.id}`)}>
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor"
                  strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
                {t('txd_details')}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

