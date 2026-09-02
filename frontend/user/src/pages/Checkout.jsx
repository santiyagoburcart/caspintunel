import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali, toman } from '../lib/format'
import { Alert, Copyable, Field, Spinner, StatusBadge } from '../components/ui'

export default function Checkout() {
  const { t, lang } = useI18n()
  const nav = useNavigate()
  const [sp] = useSearchParams()
  const planId = sp.get('plan')
  const renewId = sp.get('renew')
  const resumeId = sp.get('resume')

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
    // resume an existing pending order (from the History page)
    if (resumeId) {
      Promise.all([
        api.get(`/orders/${resumeId}/`),
        api.get('/payments/cards/').catch(() => ({ data: [] })),
      ]).then(([o, c]) => {
        setOrder(o.data)
        setInstructions({
          amount_to_pay: o.data.amount_unique,
          reserved_until: o.data.unique_expire_at,
          cards: c.data.results || c.data || [],
        })
      }).catch((e) => setErr(apiError(e)))
    }
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
    } catch (e2) { setErr(apiError(e2, t('order_failed'))) }
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
      // refresh the order so payment_status reflects "pending"
      const o = await api.get(`/orders/${order.id}/`)
      setOrder(o.data)
    } catch (e2) { setErr(apiError(e2)) }
    finally { setBusy(false) }
  }

  const checkStatus = async () => {
    setErr('')
    try {
      const { data } = await api.get(`/orders/${order.id}/`)
      setOrder(data)
      if (data.status === 'completed') nav('/', { state: { flash: t('service_activated') } })
    } catch (e2) { setErr(apiError(e2)) }
  }

  if (!order) {
    return (
      <form onSubmit={createOrder} className="card mx-auto max-w-md space-y-3">
        <h1 className="text-lg font-bold">{renewId ? t('renew') : t('buy')}</h1>
        <Alert>{err}</Alert>
        <Field label={t('store')}>
          <select className="input" value={chosenPlan} onChange={(e) => setChosenPlan(e.target.value)}>
            <option value="">—</option>
            {plans.map((p) => <option key={p.id} value={p.id}>{(lang === 'fa' ? p.name_fa : p.name_en) || p.name_fa}</option>)}
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

  const payStatus = order.payment_status   // null | pending | approved | rejected
  const needsReceipt = order.status === 'pending_payment' && (!payStatus || payStatus === 'rejected')

  return (
    <div className="card mx-auto max-w-md space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">{t('pay')}</h1>
        <StatusBadge status={order.status} />
      </div>
      <Alert>{err}</Alert>

      {order.status === 'completed' && (
        <Alert kind="success">{t('service_activated')}</Alert>
      )}

      {order.status === 'pending_payment' && (
        <>
          <div className="rounded-xl p-3 text-center" style={{ background: 'color-mix(in srgb, var(--c-primary) 12%, transparent)' }}>
            <div className="text-sm text-muted">{t('amount')}</div>
            <div className="text-2xl font-bold">{toman(order.amount_unique ?? instructions?.amount_to_pay, lang)}</div>
            <div className="text-xs text-muted">{t('pay_exact')}</div>
          </div>

          {(instructions?.cards || []).length > 0 ? (
            <div className="space-y-2">
              {instructions.cards.map((c) => (
                <div key={c.id} className="flex items-center justify-between rounded-xl border px-3 py-2" style={{ borderColor: 'var(--c-border)' }}>
                  <div><div className="font-mono">{c.card_number}</div><div className="text-xs text-muted">{c.holder_name}</div></div>
                  <Copyable text={c.card_number} />
                </div>
              ))}
            </div>
          ) : (
            <Alert kind="warning">{t('no_cards')}</Alert>
          )}

          {instructions?.reserved_until && (
            <div className="text-xs text-muted">{t('deadline')}: {jalali(instructions.reserved_until, true, lang)}</div>
          )}

          {/* --- receipt status --- */}
          {payStatus === 'pending' && <Alert kind="success">{t('pay_pending')}</Alert>}
          {payStatus === 'approved' && <Alert kind="success">{t('pay_approved')}</Alert>}
          {payStatus === 'rejected' && (
            <Alert kind="warning">
              {t('pay_rejected')}{order.reject_reason ? ` — ${order.reject_reason}` : ''}
            </Alert>
          )}

          {needsReceipt && (
            <label className={`btn-ghost w-full cursor-pointer ${busy ? 'pointer-events-none opacity-60' : ''}`}>
              {busy ? t('uploading') : (payStatus === 'rejected' ? t('pay_reupload') : t('uploadReceipt'))}
              <input type="file" accept="image/*" hidden disabled={busy}
                onChange={(e) => e.target.files[0] && uploadReceipt(e.target.files[0])} />
            </label>
          )}
        </>
      )}

      <button className="btn-primary w-full" onClick={checkStatus}>{t('refresh_status')}</button>
    </div>
  )
}
