import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali, toman, digits } from '../lib/format'
import { useConfirm } from './ConfirmDialog'
import { DateRangeModal, DRP_CSS } from './DateRangePicker'

// v1.53 (multi-tenant Phase 12) the monthly store fee on «فروشگاه» (backend apps/tenancy/fees.py) — OFF by default.
// On: one agency invoice (kind «اشتراک فروشگاه») to the reseller every Jalali month on the due day, paid like any agency
// invoice; a reminder after N days; optional suspension after N days unpaid (off by default), active again once paid.
const T = {
  fa: {
    title: 'اشتراک ماهانهٔ فروشگاه', off_note: 'خاموش است — هیچ فاکتوری صادر نمی‌شود.',
    desc: 'هر ماه (شمسی) در روز سررسید یک فاکتور «اشتراک فروشگاه» برای نماینده صادر می‌شود و مثل بقیهٔ فاکتورهای نمایندگی پرداخت می‌شود.',
    enabled: 'صدور فاکتور ماهانه روشن باشد', amount: 'مبلغ ماهانه (تومان)', due: 'سررسید بعدی', pick: 'انتخاب تاریخ',
    remind: 'یادآوری پس از (روز، ۰ = بدون یادآوری)', suspend: 'تعلیق فروشگاه اگر پرداخت نشد', suspend_days: 'تعلیق پس از (روز از سررسید)',
    suspend_hint: 'فروشگاه معلق روی دامنه‌اش در دسترس نیست؛ پس از پرداخت خودکار فعال می‌شود.', save: 'ذخیره',
    hist: 'فاکتورهای اشتراک', period: 'ماه', inv: 'فاکتور', st_unpaid: 'پرداخت‌نشده', st_pending: 'در حال بررسی',
    st_paid: 'پرداخت شد', st_voided: 'باطل', left: 'مانده', suspended: 'معلق‌شده به خاطر این فاکتور', read_only: 'تغییر آن دسترسی «حسابداری نمایندگی» لازم دارد.',
    c_title: 'روشن‌کردن اشتراک ماهانه', c_msg: 'از {d} هر ماه {a} برای {u} فاکتور صادر می‌شود.', c_sus: ' اگر {n} روز پس از سررسید پرداخت نشود، فروشگاه معلق می‌شود.',
    c_btn: 'بله، روشن کن', by_fee: 'این فروشگاه الان به خاطر اشتراک پرداخت‌نشده معلق است.',
  },
  en: {
    title: 'Monthly store fee', off_note: 'Off — no invoice is issued.',
    desc: 'Every (Jalali) month on the due day a “Store fee” invoice is issued to the reseller and paid like any other agency invoice.',
    enabled: 'Issue the monthly invoice', amount: 'Monthly amount (Toman)', due: 'Next due date', pick: 'Pick a date',
    remind: 'Reminder after (days, 0 = none)', suspend: 'Suspend the store when unpaid', suspend_days: 'Suspend after (days from due date)',
    suspend_hint: 'A suspended store is not reachable on its domain; it comes back by itself once paid.', save: 'Save',
    hist: 'Fee invoices', period: 'Month', inv: 'Invoice', st_unpaid: 'Unpaid', st_pending: 'Under review',
    st_paid: 'Paid', st_voided: 'Voided', left: 'Left', suspended: 'Store suspended for this invoice', read_only: 'Changing it needs the “agency accounting” permission.',
    c_title: 'Turn the monthly fee on', c_msg: 'From {d}, {a} is invoiced to {u} every month.', c_sus: ' The store is suspended {n} days after the due date if unpaid.',
    c_btn: 'Yes, turn it on', by_fee: 'This store is suspended right now because the fee is unpaid.',
  },
}

const latin = (v) => String(v ?? '').replace(/[۰-۹]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d)).replace(/[٠-٩]/g, (d) => '٠١٢٣٤٥٦٧٨٩'.indexOf(d))
const num = (v) => latin(v).replace(/[^\d]/g, '')
const from = (f) => ({ enabled: !!f?.enabled, amount: f?.amount && Number(f.amount) ? String(Number(f.amount)) : '',
  next_due: f?.next_due || f?.suggested_due || '', remind_after_days: String(f?.remind_after_days ?? 3),
  suspend_enabled: !!f?.suspend_enabled, suspend_after_days: String(f?.suspend_after_days ?? 10) })

export default function StoreFee({ base, fee, reseller, canEdit, onChanged }) {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const confirm = useConfirm()
  const [v, setV] = useState(from(fee))
  const [pick, setPick] = useState(false)
  useEffect(() => { setV(from(fee)) }, [fee])
  if (!fee) return null

  const body = () => ({ ...v, amount: num(v.amount) || '0', remind_after_days: num(v.remind_after_days) || '0',
    suspend_after_days: num(v.suspend_after_days) || '1' })
  const save = async (e) => {
    e.preventDefault()
    if (v.enabled && !fee.enabled) {
      const msg = s.c_msg.replace('{d}', jalali(v.next_due, false, lang)).replace('{a}', toman(num(v.amount) || 0, lang)).replace('{u}', reseller)
        + (v.suspend_enabled ? s.c_sus.replace('{n}', digits(num(v.suspend_after_days) || 1, lang)) : '')
      const ok = await confirm({ tone: 'warning', icon: 'cart', title: s.c_title, targetLabel: s.title, targetId: reseller,
        message: msg, confirmLabel: s.c_btn, action: () => api.patch(base, body()) })
      if (ok) onChanged?.()
      return
    }
    try { await api.patch(base, body()); onChanged?.() } catch { /* the toast shows why */ }
  }
  const put = (k) => (e) => setV({ ...v, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })

  return (
    <section className="sf" data-testid="store-fee">
      <style>{CSS}</style>
      <div className="sf-head"><b>{s.title}</b><span className="sf-pill" data-on={fee.enabled}>{fee.enabled ? '●' : '○'}</span></div>
      <p className="sf-desc">{fee.enabled ? s.desc : s.off_note}</p>
      {fee.suspended_by_fee && <p className="sf-bad" role="status">{s.by_fee}</p>}
      {!canEdit && <p className="text-xs text-muted">{s.read_only}</p>}
      <form className="sf-form" onSubmit={save}>
        <label className="sf-chk"><input type="checkbox" checked={v.enabled} disabled={!canEdit} onChange={put('enabled')}
          data-testid="fee-enabled" />{s.enabled}</label>
        <label className="sf-f"><span>{s.amount}</span>
          <input className="input" inputMode="numeric" dir="ltr" value={v.amount} disabled={!canEdit} placeholder="0"
            onChange={(e) => setV({ ...v, amount: num(e.target.value) })} data-testid="fee-amount" />
          {v.amount && <small className="text-xs text-muted">{toman(v.amount, lang)}</small>}</label>
        <label className="sf-f"><span>{s.due}</span>
          <button type="button" className="input sf-date" disabled={!canEdit} onClick={() => setPick(true)} data-testid="fee-due">
            {v.next_due ? <bdi dir="ltr">{jalali(v.next_due, false, lang)}</bdi> : <span className="text-muted">{s.pick}</span>}
          </button></label>
        <label className="sf-f"><span>{s.remind}</span>
          <input className="input" inputMode="numeric" dir="ltr" value={v.remind_after_days} disabled={!canEdit}
            onChange={(e) => setV({ ...v, remind_after_days: num(e.target.value) })} /></label>
        <label className="sf-chk"><input type="checkbox" checked={v.suspend_enabled} disabled={!canEdit} onChange={put('suspend_enabled')}
          data-testid="fee-suspend" />{s.suspend}</label>
        {v.suspend_enabled && (
          <label className="sf-f"><span>{s.suspend_days}</span>
            <input className="input" inputMode="numeric" dir="ltr" value={v.suspend_after_days} disabled={!canEdit}
              onChange={(e) => setV({ ...v, suspend_after_days: num(e.target.value) })} />
            <small className="text-xs text-muted">{s.suspend_hint}</small></label>
        )}
        {canEdit && <button className="btn-primary text-sm sf-save" data-testid="fee-save">{s.save}</button>}
      </form>
      {pick && createPortal(<div className="sf-drp"><style>{DRP_CSS + '.sf-drp .drp-backdrop{z-index:1300}'}</style>
        <DateRangeModal open single initial={v.next_due || ''} onClose={() => setPick(false)}
          onApply={(r) => { setV({ ...v, next_due: r.from || '' }); setPick(false) }} /></div>, document.body)}
      {fee.invoices?.length > 0 && (
        <div className="sf-hist">
          <b className="text-sm">{s.hist}</b>
          {fee.invoices.map((r) => (
            <div key={r.id} className="sf-row" data-testid="fee-invoice">
              <span><small>{s.period}</small><bdi dir="ltr">{r.period.replace('-', '/')}</bdi></span>
              <span><small>{s.inv}</small><bdi dir="ltr">{r.invoice || '—'}</bdi></span>
              <span><small>{toman(r.amount, lang)}</small><em className="sf-st" data-st={r.status}>{s['st_' + r.status] || r.status}</em></span>
              {Number(r.remaining) > 0 && <span><small>{s.left}</small>{toman(r.remaining, lang)}</span>}
              {r.suspended_at && !r.resumed_at && <span className="sf-badtxt">{s.suspended}</span>}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

const CSS = `
.sf { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.sf-head { display: flex; align-items: center; gap: 8px; font-size: 14px; }
.sf-pill { font-size: 12px; color: var(--c-text-muted); }
.sf-pill[data-on="true"] { color: var(--c-success-fg); }
.sf-desc { font-size: 12.5px; line-height: 1.8; color: var(--c-text-muted); margin: 0; }
.sf-bad { font-size: 13px; padding: 8px 10px; border-radius: 10px; margin: 0; color: var(--c-danger-fg);
  background: color-mix(in srgb, var(--c-danger) 10%, transparent); }
.sf-form { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); gap: 10px; align-items: end; }
.sf-f { display: flex; flex-direction: column; gap: 4px; font-size: 12px; font-weight: 700; min-width: 0; }
.sf-chk { display: flex; align-items: center; gap: 8px; font-size: 13px; min-height: 44px; }
.sf-date { text-align: start; min-height: 44px; }
.sf-save { min-height: 44px; }
.sf-hist { display: flex; flex-direction: column; gap: 6px; }
.sf-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 120px), 1fr)); gap: 6px 12px; font-size: 13px;
  padding: 8px 10px; border-radius: 10px; border: 1px solid var(--c-border); background: var(--c-bg); }
.sf-row span { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.sf-row small { font-size: 11px; color: var(--c-text-muted); }
.sf-st { font-style: normal; font-weight: 700; color: var(--c-warning-fg); }
.sf-st[data-st="paid"] { color: var(--c-success-fg); }
.sf-st[data-st="voided"] { color: var(--c-text-muted); }
.sf-badtxt { color: var(--c-danger-fg); font-size: 12px; font-weight: 700; }
@media (max-width: 767px) { .sf-f .input { font-size: 16px; min-height: 44px; } }
`
