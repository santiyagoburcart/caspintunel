import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali, toman } from '../lib/format'
import { Alert, Copyable, Field, Spinner, StatusBadge } from '../components/ui'

export default function Checkout() {
  const { t } = useI18n()
  const nav = useNavigate()
  const [sp] = useSearchParams()
  const planId = sp.get('plan')
  const renewId = sp.get('renew')

  const [plans, setPlans] = useState([])
  const [services, setServices] = useState([])
  const [chosenPlan, setChosenPlan] = useState(planId || '')
  const [accountName, setAccountName] = useState('')
  const [customGb, setCustomGb] = useState('')
  const [order, setOrder] = useState(null)
  const [instructions, setInstructions] = useState(null)
  const [payment, setPayment] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.get('/plans/').then((r) => setPlans(r.data.results))
    if (renewId) api.get('/services/').then((r) => setServices(r.data.results))
  }, [])

  const plan = useMemo(() => plans.find((p) => String(p.id) === String(chosenPlan)), [plans, chosenPlan])

  const createOrder = async (e) => {
    e.preventDefault()
    setBusy(true); setErr('')
    try {
      const body = renewId
        ? { plan: Number(chosenPlan), type: 'renew', service: Number(renewId) }
        : { plan: Number(chosenPlan), type: 'new', requested_account_name: accountName || undefined,
            custom_volume_gb: customGb ? Number(customGb) : undefined }
      const { data } = await api.post('/orders/', body)
      setOrder(data.order)
      setInstructions(data.payment_instructions)
    } catch (e2) { setErr(apiError(e2, 'ثبت سفارش ناموفق بود')) }
    finally { setBusy(false) }
  }

  const uploadReceipt = async (file) => {
    setBusy(true); setErr('')
    try {
      const fd = new FormData()
      fd.append('order', order.id)
      fd.append('receipt_image', file)
      const { data } = await api.post('/payments/receipt/', fd)
      setPayment(data)
    } catch (e2) { setErr(apiError(e2)) }
    finally { setBusy(false) }
  }

  const checkStatus = async () => {
    const { data } = await api.get(`/orders/${order.id}/`)
    setOrder(data)
    if (data.status === 'completed') nav('/', { state: { flash: 'سرویس شما فعال شد 🎉' } })
  }

  if (!order) {
    return (
      <form onSubmit={createOrder} className="card mx-auto max-w-md space-y-3">
        <h1 className="text-lg font-bold">{renewId ? t('renew') : t('buy')}</h1>
        <Alert>{err}</Alert>
        <Field label={t('store')}>
          <select className="input" value={chosenPlan} onChange={(e) => setChosenPlan(e.target.value)}>
            <option value="">—</option>
            {plans.map((p) => <option key={p.id} value={p.id}>{p.name_fa}</option>)}
          </select>
        </Field>
        {!renewId && plan?.type !== 'custom_volume' && (
          <Field label={t('account_name')}>
            <input className="input" value={accountName} onChange={(e) => setAccountName(e.target.value)} />
          </Field>
        )}
        {!renewId && plan?.type === 'custom_volume' && (
          <Field label={`${t('volume')} (GB) — ${plan.min_gb}..${plan.max_gb}`}>
            <input className="input" type="number" value={customGb} onChange={(e) => setCustomGb(e.target.value)} />
          </Field>
        )}
        <button className="btn-primary w-full" disabled={busy || !chosenPlan}>{busy ? <Spinner /> : t('submit')}</button>
      </form>
    )
  }

  return (
    <div className="card mx-auto max-w-md space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">{t('pay')}</h1>
        <StatusBadge status={order.status} />
      </div>
      <Alert>{err}</Alert>
      {order.status === 'pending_payment' && instructions && (
        <>
          <div className="rounded-xl p-3 text-center" style={{ background: 'color-mix(in srgb, var(--c-primary) 12%, transparent)' }}>
            <div className="text-sm text-muted">{t('amount')}</div>
            <div className="text-2xl font-bold">{toman(instructions.amount_to_pay)}</div>
            <div className="text-xs text-muted">دقیقاً همین مبلغ را واریز کنید</div>
          </div>
          <div className="space-y-2">
            {instructions.cards.map((c) => (
              <div key={c.id} className="flex items-center justify-between rounded-xl border px-3 py-2" style={{ borderColor: 'var(--c-border)' }}>
                <div><div className="font-mono">{c.card_number}</div><div className="text-xs text-muted">{c.holder_name}</div></div>
                <Copyable text={c.card_number} />
              </div>
            ))}
          </div>
          <div className="text-xs text-muted">مهلت: {jalali(instructions.reserved_until, true)}</div>
          {payment ? (
            <Alert kind="success">رسید ثبت شد؛ پس از تأیید، سرویس فعال می‌شود.</Alert>
          ) : (
            <label className="btn-ghost w-full cursor-pointer">
              {t('uploadReceipt')}
              <input type="file" accept="image/*" hidden onChange={(e) => e.target.files[0] && uploadReceipt(e.target.files[0])} />
            </label>
          )}
        </>
      )}
      <button className="btn-primary w-full" onClick={checkStatus}>{t('status')}</button>
    </div>
  )
}
