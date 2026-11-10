import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali, toman } from '../lib/format'
import { usePaymentsEvents } from '../lib/livePayments'
import AccountNameInput, { nameOk } from './AccountNameInput'

// v1.52.1 «ساخت ناموفق» of a reseller store (backend apps/tenancy/failed_orders.py): paid orders PasarGuard refused, with its
// error, an editable account name and «تلاش دوباره». Used on the store's own Payments page (base = /admin/orders/provision-failed/)
// and on our «فروشگاه» card (base = …/store/failed-orders/). A retry runs the SAME paid order again — never a new charge.
const T = {
  fa: {
    title: 'سفارش‌های ناموفق (ساخت ناموفق)', none: 'سفارش ناموفقی نیست.',
    desc: 'پرداخت این سفارش‌ها تأیید شده ولی PasarGuard ساخت سرویس را رد کرده. نام اکانت را در صورت نیاز اصلاح کنید و «تلاش دوباره» را بزنید — مبلغی دوباره از مشتری گرفته نمی‌شود. مشتری پیام «در حال آماده‌سازی» دیده است.',
    order: 'سفارش', customer: 'مشتری', plan: 'پلن', amount: 'مبلغ', since: 'از', error: 'پیام PasarGuard', name: 'نام اکانت',
    retry: 'تلاش دوباره', renew: 'تمدید', addon: 'حجم اضافه', no_perm: 'برای تلاش دوباره دسترسی «تأیید پرداخت» لازم است.',
  },
  en: {
    title: 'Failed orders (provisioning failed)', none: 'No failed orders.',
    desc: 'These orders are paid but PasarGuard refused to create the service. Fix the account name if needed and press “Retry” — the customer is never charged again. The customer was told the service is being prepared.',
    order: 'Order', customer: 'Customer', plan: 'Plan', amount: 'Amount', since: 'since', error: 'PasarGuard said', name: 'Account name',
    retry: 'Retry', renew: 'Renewal', addon: 'Add-on volume', no_perm: 'Retrying needs the “approve payments” permission.',
  },
}

export default function FailedOrders({ base, canRetry, live = false, hideEmpty = true, onChanged }) {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const [rows, setRows] = useState(null)
  const load = () => api.get(base).then((r) => setRows(r.data.results || [])).catch(() => setRows([]))
  useEffect(() => { load() }, [base])
  usePaymentsEvents(() => { if (live) load() })          // the store's own socket: a retry result / a new failure

  if (rows === null || (hideEmpty && rows.length === 0)) return null
  return (
    <section className="fo" data-testid="failed-orders">
      <style>{CSS}</style>
      <div className="fo-head"><span className="fo-pill">{rows.length}</span><b>{s.title}</b></div>
      {rows.length === 0 ? <p className="text-sm text-muted">{s.none}</p> : <p className="fo-desc">{s.desc}</p>}
      {!canRetry && rows.length > 0 && <p className="text-xs text-muted">{s.no_perm}</p>}
      <div className="fo-list">
        {rows.map((r) => <Row key={r.order} r={r} s={s} lang={lang} base={base} canRetry={canRetry}
          onDone={() => { load(); onChanged?.() }} />)}
      </div>
    </section>
  )
}

function Row({ r, s, lang, base, canRetry, onDone }) {
  const [name, setName] = useState(r.account_name || '')
  const [busy, setBusy] = useState(false)
  const [nameErr, setNameErr] = useState('')
  const editable = r.name_editable
  const kind = r.type === 'renew' ? s.renew : r.type === 'addon_volume' ? s.addon : null
  const retry = async () => {
    setBusy(true); setNameErr('')
    try {
      const changed = editable && name.trim() && name.trim() !== (r.account_name || '')
      await api.post(`${base}${r.order}/retry/`, changed ? { account_name: name.trim() } : {})
      onDone()
    } catch (e) {
      const d = e?.response?.data
      if (d?.code === 'account_name' || d?.detail_fa) setNameErr(lang === 'fa' ? d.detail_fa || d.detail : d.detail)
    } finally { setBusy(false) }
  }
  return (
    <article className="fo-card" data-testid="failed-order">
      <div className="fo-meta">
        <span><small>{s.order}</small><bdi dir="ltr">#{r.order}</bdi>{kind && <em className="fo-kind">{kind}</em>}</span>
        <span><small>{s.customer}</small><bdi dir="ltr">{r.user}</bdi></span>
        <span><small>{s.plan}</small>{lang === 'fa' ? (r.plan_fa || r.plan_en) : (r.plan_en || r.plan_fa)}</span>
        <span><small>{s.amount}</small>{toman(r.amount, lang)}{r.tx && <bdi dir="ltr" className="fo-tx">{r.tx}</bdi>}</span>
        <span><small>{s.since}</small>{jalali(r.failed_at, true, lang)}</span>
      </div>
      <div className="fo-err"><b>{s.error}:</b> <bdi dir="ltr">{r.error || '—'}</bdi></div>
      {canRetry && (
        <div className="fo-act">
          {editable
            ? <AccountNameInput label={s.name} value={name} onChange={(v) => { setName(v); setNameErr('') }} lang={lang}
                serverError={nameErr} testid={`fo-name-${r.order}`} />
            : <div className="fo-name"><small>{s.name}</small><bdi dir="ltr">{r.account_name || '—'}</bdi>
                {nameErr && <span className="fo-bad" role="alert">{nameErr}</span>}</div>}
          <button type="button" className="btn-primary text-sm fo-btn" disabled={busy || (editable && !nameOk(name))}
            onClick={retry} data-testid={`fo-retry-${r.order}`}>{busy ? '…' : s.retry}</button>
        </div>
      )}
    </article>
  )
}

const CSS = `
.fo { display: flex; flex-direction: column; gap: 8px; padding: 12px 14px; border-radius: 14px; min-width: 0;
  border: 1px solid color-mix(in srgb, var(--c-danger) 35%, var(--c-border)); background: color-mix(in srgb, var(--c-danger) 6%, var(--c-bg)); }
.fo-head { display: flex; align-items: center; gap: 8px; font-size: 14px; }
.fo-pill { min-width: 24px; height: 24px; padding: 0 8px; border-radius: 999px; display: inline-grid; place-items: center; font-size: 12px;
  font-weight: 800; color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 16%, transparent); }
.fo-desc { font-size: 12.5px; line-height: 1.8; color: var(--c-text-muted); margin: 0; }
.fo-list { display: flex; flex-direction: column; gap: 8px; }
.fo-card { display: flex; flex-direction: column; gap: 8px; padding: 10px 12px; border-radius: 12px; border: 1px solid var(--c-border);
  background: var(--c-bg); min-width: 0; }
.fo-meta { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 140px), 1fr)); gap: 6px 12px; font-size: 13px; }
.fo-meta span { display: flex; flex-direction: column; gap: 2px; min-width: 0; overflow-wrap: anywhere; }
.fo-meta small, .fo-name small { font-size: 11px; color: var(--c-text-muted); }
.fo-kind { font-style: normal; font-size: 11px; font-weight: 700; color: var(--c-text-muted); }
.fo-tx { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 11.5px; color: var(--c-text-muted); }
.fo-err { font-size: 12.5px; line-height: 1.7; padding: 8px 10px; border-radius: 10px; overflow-wrap: anywhere;
  background: color-mix(in srgb, var(--c-danger) 8%, transparent); color: var(--c-danger-fg); }
.fo-act { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); gap: 8px; align-items: end; }
.fo-name { display: flex; flex-direction: column; gap: 2px; font-size: 13px; min-width: 0; }
.fo-bad { font-size: 12px; color: var(--c-danger-fg); }
.fo-btn { min-height: 44px; }
`
