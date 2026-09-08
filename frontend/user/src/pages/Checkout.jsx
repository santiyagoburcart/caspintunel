import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali, toman } from '../lib/format'
import { Alert, Copyable, Field, Spinner, StatusBadge } from '../components/ui'
import { AuthImage } from '../components/AuthImage'

export default function Checkout() {
  const { t, lang } = useI18n()
  const [sp] = useSearchParams()
  const planId = sp.get('plan')
  const renewId = sp.get('renew')
  const resumeId = sp.get('resume')
  const preGb = sp.get('gb')

  const [plans, setPlans] = useState([])
  const [services, setServices] = useState([])
  const [chosenPlan, setChosenPlan] = useState(planId || '')
  const [accountName, setAccountName] = useState('')
  const [customGb, setCustomGb] = useState(preGb || '')
  const [order, setOrder] = useState(null)
  const [instructions, setInstructions] = useState(null)
  const [payment, setPayment] = useState(null)
  const [service, setService] = useState(null)
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

  // default the custom-volume value to the plan's minimum once it's known
  useEffect(() => {
    if (plan?.type === 'custom_volume' && !customGb) setCustomGb(String(plan.min_gb || 60))
  }, [plan])

  // service delivery info (QR + subscription link) once the order completes
  useEffect(() => {
    if (order?.status === 'completed' && order.service && !service) {
      api.get(`/services/${order.service}/`).then((r) => setService(r.data)).catch(() => {})
    }
  }, [order?.status])

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
    } catch (e2) { setErr(apiError(e2)) }
  }

  if (!order) {
    const planName = plan ? ((lang === 'fa' ? plan.name_fa : plan.name_en) || plan.name_fa) : ''
    return (
      <form onSubmit={createOrder} className="card mx-auto max-w-lg space-y-4">
        <h1 className="text-lg font-bold">{renewId ? t('renew') : t('buy')}</h1>
        <Alert>{err}</Alert>

        {renewId || !plan ? (
          <Field label={t('store')}>
            <select className="input" value={chosenPlan} onChange={(e) => setChosenPlan(e.target.value)}>
              <option value="">—</option>
              {plans.map((p) => <option key={p.id} value={p.id}>{(lang === 'fa' ? p.name_fa : p.name_en) || p.name_fa}</option>)}
            </select>
          </Field>
        ) : (
          <div className="rounded-xl p-3" style={{ background: 'color-mix(in srgb, var(--c-primary) 8%, transparent)' }}>
            <div className="text-xs text-muted">{t('select_plan')}</div>
            <div className="flex items-center justify-between gap-2">
              <span className="font-bold" style={{ color: 'var(--c-ink)' }}>{planName}</span>
              <Link to="/store" className="shrink-0 text-xs text-primary hover:underline">{t('change_plan')}</Link>
            </div>
          </div>
        )}

        {!renewId && (
          <Field label={t('account_name')}>
            <input className="input" dir="ltr" value={accountName}
              onChange={(e) => setAccountName(e.target.value)} />
          </Field>
        )}

        {!renewId && plan?.type === 'custom_volume' && (
          <CustomVolumePicker plan={plan} value={customGb} onChange={setCustomGb} t={t} lang={lang} />
        )}

        <button className="btn-primary w-full"
          disabled={busy || !chosenPlan || (!renewId && !accountName.trim())
            || (plan?.type === 'custom_volume' && !customGb)}>
          {busy ? <Spinner /> : t('submit')}
        </button>
      </form>
    )
  }

  const payStatus = order.payment_status   // null | pending | approved | rejected
  const needsReceipt = order.status === 'pending_payment' && (!payStatus || payStatus === 'rejected')

  return (
    <div className="card mx-auto max-w-md space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">{order.status === 'completed' ? t('checkout') : t('pay')}</h1>
        <StatusBadge status={order.status} />
      </div>
      <Alert>{err}</Alert>

      {order.status === 'completed' && (
        <div className="space-y-4 py-2 text-center">
          <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl text-2xl text-white"
            style={{ background: 'var(--c-success)' }}>✓</div>
          <div>
            <h2 className="text-lg font-bold" style={{ color: 'var(--c-success)' }}>{t('delivery_ready')}</h2>
            <p className="text-sm text-muted">{t('delivery_hint')}</p>
          </div>
          {service?.subscription_url && (
            <>
              <div className="mx-auto inline-block rounded-2xl bg-white p-3">
                <AuthImage path={`/services/${service.id}/qr/`} alt="QR" className="h-36 w-36" />
              </div>
              <div className="mx-auto flex max-w-sm items-center gap-2">
                <code dir="ltr" className="min-w-0 flex-1 truncate rounded px-2 py-1 text-xs"
                  style={{ background: 'var(--c-border)' }}>
                  {service.subscription_url}
                </code>
                <Copyable text={service.subscription_url} />
              </div>
            </>
          )}
          <Link to="/" className="btn-primary inline-block">{t('services')}</Link>
        </div>
      )}

      {order.status === 'pending_payment' && (
        <>
          <div className="rounded-xl p-3 text-center" style={{ background: 'color-mix(in srgb, var(--c-primary) 12%, transparent)' }}>
            <div className="text-sm text-muted">{t('amount')}</div>
            <div className="text-2xl font-bold" style={{ color: 'var(--c-primary)' }}>{toman(order.amount_unique ?? instructions?.amount_to_pay, lang)}</div>
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
            <label className={`block cursor-pointer rounded-2xl border-2 border-dashed p-6 text-center transition ${busy ? 'pointer-events-none opacity-60' : ''}`}
              style={{ borderColor: 'var(--c-border)' }}>
              <div className="mb-1 text-3xl">📸</div>
              <div className="font-medium" style={{ color: 'var(--c-ink)' }}>
                {busy ? t('uploading') : (payStatus === 'rejected' ? t('pay_reupload') : t('uploadReceipt'))}
              </div>
              <div className="mt-1 text-xs text-muted">{t('receipt_drop_hint')}</div>
              <input type="file" accept="image/*" hidden disabled={busy}
                onChange={(e) => e.target.files[0] && uploadReceipt(e.target.files[0])} />
            </label>
          )}
        </>
      )}

      {order.status !== 'completed' && (
        <button className="btn-primary w-full" onClick={checkStatus}>{t('refresh_status')}</button>
      )}
    </div>
  )
}

function CustomVolumePicker({ plan, value, onChange, t, lang }) {
  const min = plan.min_gb || 1
  const max = plan.max_gb || 800
  const gb = Number(value) || min
  const pct = Math.max(0, Math.min(100, ((gb - min) / ((max - min) || 1)) * 100))
  const price = Math.round(
    (Number(plan.price || 0) + Number(plan.price_per_gb || 0) * gb) * (1 - Number(plan.discount_percent || 0) / 100),
  )

  const setClamped = (v) => onChange(String(Math.max(min, Math.min(max, Number(v) || min))))

  return (
    <div className="space-y-3">
      <div className="label">{t('custom_volume_label')}</div>
      <div className="flex items-end justify-between gap-3">
        <div className="flex items-baseline gap-2">
          <input
            className="w-24 border-0 border-b-2 bg-transparent text-center text-2xl font-extrabold outline-none"
            style={{ borderColor: 'var(--c-border)', color: 'var(--c-ink)' }}
            type="number" min={min} max={max} value={gb}
            onChange={(e) => onChange(e.target.value)}
            onBlur={(e) => setClamped(e.target.value)}
          />
          <span className="text-sm font-medium text-muted">{t('gigabytes')}</span>
        </div>
        <div className="text-end">
          <div className="text-lg font-extrabold" style={{ color: 'var(--c-primary)' }}>{toman(price, lang)}</div>
          <div className="text-[11px] text-muted">{t('amount')}</div>
        </div>
      </div>
      {/* the slider stays LTR internally (min at the physical start) regardless of
          page direction — native range inputs mirror their value-to-position
          mapping under dir="rtl", which would fight the fill gradient otherwise */}
      <input
        dir="ltr"
        type="range" min={min} max={max} value={gb}
        style={{ '--pct': `${pct}%` }}
        onChange={(e) => setClamped(e.target.value)}
      />
      <div dir="ltr" className="flex justify-between text-xs text-muted">
        <span>{min} GB</span>
        <span>{max} GB</span>
      </div>
    </div>
  )
}
