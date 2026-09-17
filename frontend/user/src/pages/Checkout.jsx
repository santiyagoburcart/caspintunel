import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { toman, gb } from '../lib/format'
import { Alert, Copyable, Field, Spinner, StatusBadge } from '../components/ui'
import { AuthImage } from '../components/AuthImage'
import { useToast } from '../components/Toast'

export default function Checkout() {
  const { t, lang } = useI18n()
  const toast = useToast()
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
  const [selectedCard, setSelectedCard] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [changingPlan, setChangingPlan] = useState(false)
  const [agreed, setAgreed] = useState(false)

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

  // a single active card needs no choice; with several, the customer must pick one
  useEffect(() => {
    const cards = instructions?.cards || []
    if (cards.length === 1) setSelectedCard(cards[0].id)
  }, [instructions])

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
    toast.loading(t('action_in_progress'))
    try {
      const body = renewId
        ? { plan: Number(chosenPlan), type: 'renew', service: Number(renewId), terms_accepted: agreed }
        : { plan: Number(chosenPlan), type: 'new', requested_account_name: accountName || undefined,
            custom_volume_gb: customGb ? Number(customGb) : undefined, terms_accepted: agreed }
      const { data } = await api.post('/orders/', body)
      setOrder(data.order)
      setInstructions(data.payment_instructions)
      toast.dismiss()
    } catch (e2) { const msg = apiError(e2, t('order_failed')); setErr(msg); toast.error(msg) }
    finally { setBusy(false) }
  }

  const uploadReceipt = async (file) => {
    setBusy(true); setErr('')
    toast.loading(t('action_in_progress'))
    try {
      const fd = new FormData()
      fd.append('order', order.id)
      fd.append('receipt_image', file)
      if (selectedCard) fd.append('bank_card', selectedCard)
      const { data } = await api.post('/payments/receipt/', fd)
      setPayment(data)
      // refresh the order so payment_status reflects "pending"
      const o = await api.get(`/orders/${order.id}/`)
      setOrder(o.data)
      toast.success(t('receipt_saved'))
    } catch (e2) { const msg = apiError(e2); setErr(msg); toast.error(msg) }
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
    const renewingService = renewId ? services.find((sv) => String(sv.id) === String(renewId)) : null
    const showPicker = !plan || changingPlan
    const volumeText = plan?.type === 'custom_volume' ? t('selectable')
      : plan?.data_limit ? `${gb(plan.data_limit)} GB` : t('unlimited')
    const durationText = plan?.duration_days ? `${plan.duration_days} ${t('days')}` : t('no_expiry')

    return (
      <form onSubmit={createOrder} className="card mx-auto max-w-lg space-y-4">
        <style>{CHECKOUT_CSS}</style>

        {renewId && (
          <div className="ckt-renew-banner">
            <span className="ckt-renew-ico" aria-hidden="true">↻</span>
            <span>{t('renew_service_title', { id: renewingService?.id ?? renewId })}</span>
          </div>
        )}

        <h1 className="text-lg font-bold">{t('buy')}</h1>
        <Alert>{err}</Alert>

        {showPicker ? (
          <Field label={t('store')}>
            <select className="input" value={chosenPlan}
              onChange={(e) => { setChosenPlan(e.target.value); setChangingPlan(false) }}>
              <option value="">—</option>
              {plans.map((p) => <option key={p.id} value={p.id}>{(lang === 'fa' ? p.name_fa : p.name_en) || p.name_fa}</option>)}
            </select>
          </Field>
        ) : (
          <div className="ckt-plan-card">
            <div className="ckt-plan-head">
              <div className="min-w-0">
                <div className="ckt-plan-name-en" dir="ltr">{plan.name_en || plan.name_fa}</div>
                {plan.name_en && plan.name_fa && <div className="ckt-plan-name-fa">{plan.name_fa}</div>}
              </div>
              <button type="button" className="ckt-plan-change" onClick={() => setChangingPlan(true)}>{t('change_plan')}</button>
            </div>
            <div className="ckt-plan-details">
              <div className="ckt-plan-detail">
                <span className="ckt-plan-detail-label">{t('volume')}</span>
                <span className="ckt-plan-detail-val">{volumeText}</span>
              </div>
              <div className="ckt-plan-detail">
                <span className="ckt-plan-detail-label">{t('duration')}</span>
                <span className="ckt-plan-detail-val">{durationText}</span>
              </div>
              {plan.type !== 'custom_volume' && (
                <div className="ckt-plan-detail ckt-plan-detail--price">
                  <span className="ckt-plan-detail-label">{t('amount')}</span>
                  <span className="ckt-plan-detail-val ckt-plan-price">{toman(plan.final_price, lang)}</span>
                </div>
              )}
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

        <label className="ckt-terms">
          <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
          <span>
            {t('agree_prefix')}
            <Link to="/rules" target="_blank" rel="noreferrer" className="ckt-terms-link">{t('terms_of_service')}</Link>
            {t('agree_suffix')}
          </span>
        </label>

        <button className="btn-primary w-full"
          disabled={busy || !agreed || !chosenPlan || (!renewId && !accountName.trim())
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
      <style>{`
        .ctd-ring { position: relative; margin: 4px auto 0; display: grid; place-items: center; }
        .ctd-ring-label { position: absolute; font-size: 15px; font-weight: 800; }
      `}</style>
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
          {/* 1. countdown timer */}
          {instructions?.reserved_until && <CountdownRing deadline={instructions.reserved_until} />}

          {/* 2. card number — bold/prominent, the thing the customer actually needs to act on */}
          {(instructions?.cards || []).length > 1 ? (
            <div className="space-y-2">
              <div className="text-xs text-muted">{t('choose_card')}</div>
              {instructions.cards.map((c) => {
                const isSel = selectedCard === c.id
                return (
                  <div key={c.id} role="radio" aria-checked={isSel} tabIndex={0}
                    className="flex cursor-pointer items-center justify-between gap-2 rounded-xl border-2 px-3 py-3 transition outline-none"
                    style={{
                      borderColor: isSel ? 'var(--c-primary)' : 'var(--c-border)',
                      background: isSel ? 'color-mix(in srgb, var(--c-primary) 7%, transparent)' : undefined,
                    }}
                    onClick={() => setSelectedCard(c.id)}
                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelectedCard(c.id) } }}>
                    <div className="flex items-center gap-2">
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white"
                        style={{ background: isSel ? 'var(--c-primary)' : 'transparent', border: `2px solid ${isSel ? 'var(--c-primary)' : 'var(--c-border)'}` }}
                        aria-hidden="true">{isSel ? '✓' : ''}</span>
                      <div>
                        <div dir="ltr" className="font-mono text-lg font-extrabold tracking-wide" style={{ color: 'var(--c-ink)' }}>{c.card_number}</div>
                        <div className="text-xs text-muted">{c.holder_name}</div>
                      </div>
                    </div>
                    <Copyable text={c.card_number} />
                  </div>
                )
              })}
            </div>
          ) : (instructions?.cards || []).length === 1 ? (
            <div className="space-y-2">
              {instructions.cards.map((c) => (
                <div key={c.id} className="flex items-center justify-between rounded-xl border-2 px-3 py-3" style={{ borderColor: 'var(--c-primary)' }}>
                  <div>
                    <div dir="ltr" className="font-mono text-lg font-extrabold tracking-wide" style={{ color: 'var(--c-ink)' }}>{c.card_number}</div>
                    <div className="text-xs text-muted">{c.holder_name}</div>
                  </div>
                  <Copyable text={c.card_number} />
                </div>
              ))}
            </div>
          ) : (
            <Alert kind="warning">{t('no_cards')}</Alert>
          )}

          {/* 3. amount */}
          <div className="rounded-xl p-3 text-center" style={{ background: 'color-mix(in srgb, var(--c-primary) 12%, transparent)' }}>
            <div className="text-sm text-muted">{t('amount')}</div>
            <div className="text-2xl font-bold" style={{ color: 'var(--c-primary)' }}>{toman(order.amount_unique ?? instructions?.amount_to_pay, lang)}</div>
            <div className="text-xs text-muted">{t('pay_exact')}</div>
          </div>

          {/* --- receipt status --- */}
          {payStatus === 'pending' && <Alert kind="success">{t('pay_pending')}</Alert>}
          {payStatus === 'approved' && <Alert kind="success">{t('pay_approved')}</Alert>}
          {payStatus === 'rejected' && (
            <Alert kind="warning">
              {t('pay_rejected')}{order.reject_reason ? ` — ${order.reject_reason}` : ''}
            </Alert>
          )}

          {/* 4. receipt upload */}
          {needsReceipt && (() => {
            const needsCardChoice = (instructions?.cards || []).length > 1 && !selectedCard
            return (
              <label className={`block rounded-2xl border-2 border-dashed p-6 text-center transition ${busy || needsCardChoice ? 'pointer-events-none opacity-60' : 'cursor-pointer'}`}
                style={{ borderColor: 'var(--c-border)' }}>
                <div className="mb-1 text-3xl">📸</div>
                <div className="font-medium" style={{ color: 'var(--c-ink)' }}>
                  {busy ? t('uploading') : needsCardChoice ? t('choose_card_first') : (payStatus === 'rejected' ? t('pay_reupload') : t('uploadReceipt'))}
                </div>
                <div className="mt-1 text-xs text-muted">{t('receipt_drop_hint')}</div>
                <input type="file" accept="image/*" hidden disabled={busy || needsCardChoice}
                  onChange={(e) => e.target.files[0] && uploadReceipt(e.target.files[0])} />
              </label>
            )
          })()}
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

/** Visual depletion ring for the unique-amount reservation window — shows
 * only the remaining mm:ss (no date), colored green -> amber (<5min) ->
 * red (<2min). The "100%" reference is however much time was left the
 * moment this first rendered, not a value fetched from settings. */
function CountdownRing({ deadline }) {
  const [now, setNow] = useState(Date.now())
  const totalMsRef = useRef(null)

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])

  const deadlineMs = new Date(deadline).getTime()
  const remainingMs = Math.max(0, deadlineMs - now)
  if (totalMsRef.current == null) totalMsRef.current = remainingMs || 1
  const pct = Math.min(1, remainingMs / totalMsRef.current)

  const totalSeconds = Math.floor(remainingMs / 1000)
  const mm = String(Math.floor(totalSeconds / 60)).padStart(2, '0')
  const ss = String(totalSeconds % 60).padStart(2, '0')

  const minutesLeft = remainingMs / 60000
  const color = minutesLeft < 2 ? 'var(--c-danger)' : minutesLeft < 5 ? 'var(--c-warning)' : 'var(--c-success)'

  const size = 80
  const stroke = 6
  const r = (size - stroke) / 2
  const circumference = 2 * Math.PI * r

  return (
    <div className="ctd-ring" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--c-border)" strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
          strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={circumference * (1 - pct)}
          transform={`rotate(-90 ${size / 2} ${size / 2})`} style={{ transition: 'stroke-dashoffset 1s linear, stroke .3s' }} />
      </svg>
      <div className="ctd-ring-label mono-num" dir="ltr" style={{ color }}>{mm}:{ss}</div>
    </div>
  )
}

const CHECKOUT_CSS = `
.ckt-terms { display: flex; align-items: flex-start; gap: 8px; font-size: 12.5px; color: var(--c-text-muted); cursor: pointer; }
.ckt-terms input { margin-top: 3px; flex-shrink: 0; width: 16px; height: 16px; accent-color: var(--c-primary); cursor: pointer; }
.ckt-terms-link { color: var(--c-primary); font-weight: 600; }
.ckt-terms-link:hover { text-decoration: underline; }
.ckt-renew-banner {
  display: flex; align-items: center; gap: 8px; padding: 10px 14px; border-radius: 12px;
  background: color-mix(in srgb, var(--c-warning) 14%, transparent);
  color: var(--c-warning); font-size: 13px; font-weight: 700;
}
.ckt-renew-ico { flex-shrink: 0; font-size: 15px; line-height: 1; }
.ckt-plan-card {
  border-radius: 16px; padding: 14px 16px; border: 1px solid var(--c-border);
  background: color-mix(in srgb, var(--c-primary) 5%, transparent);
}
.ckt-plan-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.ckt-plan-name-en { font-size: 17px; font-weight: 800; color: var(--c-ink); line-height: 1.3; }
.ckt-plan-name-fa { margin-top: 2px; font-size: 12.5px; color: var(--c-text-muted); opacity: .75; }
.ckt-plan-change { flex-shrink: 0; font-size: 11.5px; font-weight: 600; color: var(--c-primary); background: none; border: 0; cursor: pointer; white-space: nowrap; }
.ckt-plan-change:hover { text-decoration: underline; }
.ckt-plan-details { margin-top: 12px; display: flex; flex-direction: column; gap: 7px; padding-top: 12px; border-top: 1px solid var(--c-border); }
.ckt-plan-detail { display: flex; align-items: center; justify-content: space-between; gap: 10px; font-size: 13px; }
.ckt-plan-detail-label { color: var(--c-text-muted); opacity: .7; }
.ckt-plan-detail-val { font-weight: 700; color: var(--c-ink); }
.ckt-plan-detail--price .ckt-plan-price { color: var(--c-primary); font-size: 15px; font-weight: 800; }
`
