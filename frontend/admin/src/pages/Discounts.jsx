import { useEffect, useMemo, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useAuth } from '../lib/auth'
import { jalali, toman, digits } from '../lib/format'
import { Alert, Spinner, Toggle } from '../components/ui'
import { useToast } from '../components/Toast'
import { DateRangeModal, DRP_CSS } from '../components/DateRangePicker'

// Panel → Discount codes (v1.26). Backend: adminpanel/views/discounts.py, rules in
// apps/crm/discounts.py. Win-back codes (retention) are listed here too and can only be
// switched on/off or given another end date. Times are Tehran time (+03:30).

const T = {
  fa: {
    title: 'کدهای تخفیف', sub: 'کدهای تخفیف سایت، مینی‌اپ و ربات — همراه کدهای بازگشت مشتری (CRM).',
    new: 'کد تخفیف جدید', edit: 'ویرایش کد', k_active: 'کد فعال', k_sched: 'زمان‌بندی‌شده', k_uses: 'استفاده (پرداخت‌شده)', k_disc: 'جمع تخفیف', k_rev: 'درآمد با کد',
    all: 'همه', campaign: 'کد تخفیف', winback: 'بازگشت مشتری', search: 'جستجوی کد یا نام…',
    st_active: 'فعال', st_scheduled: 'زمان‌بندی‌شده', st_expired: 'منقضی', st_disabled: 'غیرفعال', st_used_up: 'تمام‌شده',
    code: 'کد', name: 'نام (داخلی)', random: 'تصادفی', active: 'فعال', start: 'شروع', end: 'پایان', none: 'بدون محدودیت', pick_date: 'انتخاب تاریخ', time: 'ساعت',
    type: 'نوع تخفیف', percent: 'درصدی', fixed: 'مبلغ ثابت', pct: 'درصد', max: 'سقف تخفیف (تومان، اختیاری)', amount: 'مبلغ تخفیف (تومان)',
    who: 'چه کسانی', all_c: 'همهٔ مشتریان', sel_c: 'مشتریان انتخابی', find_c: 'جستجو با نام کاربری، موبایل یا تلگرام…', first: 'فقط اولین خرید',
    plans: 'پلن‌ها', all_p: 'همهٔ پلن‌ها', sel_p: 'پلن‌های انتخابی', for: 'برای', f_new: 'خرید جدید', f_renew: 'تمدید', f_both: 'هر دو',
    limits: 'محدودیت‌ها', max_uses: 'تعداد کل استفاده', per_c: 'استفاده برای هر مشتری', min: 'حداقل مبلغ سفارش (تومان)', empty_unl: 'خالی = نامحدود',
    note: 'یادداشت', save: 'ذخیره', cancel: 'انصراف', create: 'ساخت کد', saved: 'ذخیره شد', created: 'کد ساخته شد',
    disable: 'غیرفعال کن', enable: 'فعال کن', report: 'گزارش', close: 'بستن', owner: 'مشتری', uses: 'استفاده', customers: 'مشتری', disc: 'تخفیف', rev: 'درآمد',
    held: 'رزرو / در انتظار', no_codes: 'هنوز کدی ساخته نشده است.', upto: 'تا سقف', off: 'تخفیف', of: 'از', unl: 'نامحدود', per: 'هر مشتری',
    wb_note: 'کد بازگشت مشتری: فقط روشن/خاموش، تاریخ پایان، نام و یادداشت قابل تغییر است.',
    o_order: 'سفارش', o_customer: 'مشتری', o_plan: 'پلن', o_orig: 'قیمت', o_final: 'مبلغ نهایی', o_paid: 'پرداخت‌شده', o_status: 'وضعیت', o_none: 'هنوز سفارشی با این کد نیست.',
    ost: { pending_payment: 'در انتظار پرداخت', paid: 'پرداخت‌شده', completed: 'تکمیل', rejected: 'ردشده', expired: 'منقضی', failed: 'ناموفق', cancelled: 'لغوشده' },
    tehran: 'به وقت تهران', need_customer: 'حداقل یک مشتری انتخاب کنید.', check: 'قوانین', first_only: 'اولین خرید', minimum: 'حداقل',
  },
  en: {
    title: 'Discount codes', sub: 'Codes for the site, Mini App and bot — plus the customer win-back codes (CRM).',
    new: 'New discount code', edit: 'Edit code', k_active: 'Active codes', k_sched: 'Scheduled', k_uses: 'Uses (paid)', k_disc: 'Total discount', k_rev: 'Revenue with codes',
    all: 'All', campaign: 'Discount code', winback: 'Win-back', search: 'Search code or name…',
    st_active: 'Active', st_scheduled: 'Scheduled', st_expired: 'Expired', st_disabled: 'Disabled', st_used_up: 'Used up',
    code: 'Code', name: 'Name (internal)', random: 'Random', active: 'Active', start: 'Starts', end: 'Ends', none: 'No limit', pick_date: 'Pick a date', time: 'Time',
    type: 'Discount type', percent: 'Percent', fixed: 'Fixed amount', pct: 'Percent', max: 'Max discount (Toman, optional)', amount: 'Discount (Toman)',
    who: 'Who', all_c: 'All customers', sel_c: 'Selected customers', find_c: 'Search username, phone or Telegram…', first: 'First purchase only',
    plans: 'Plans', all_p: 'All plans', sel_p: 'Selected plans', for: 'For', f_new: 'New purchase', f_renew: 'Renewal', f_both: 'Both',
    limits: 'Limits', max_uses: 'Total uses', per_c: 'Uses per customer', min: 'Minimum order (Toman)', empty_unl: 'empty = unlimited',
    note: 'Note', save: 'Save', cancel: 'Cancel', create: 'Create code', saved: 'Saved', created: 'Code created',
    disable: 'Disable', enable: 'Enable', report: 'Report', close: 'Close', owner: 'Customer', uses: 'uses', customers: 'customers', disc: 'Discount', rev: 'Revenue',
    held: 'reserved / pending', no_codes: 'No codes yet.', upto: 'up to', off: 'off', of: 'of', unl: 'unlimited', per: 'per customer',
    wb_note: 'Win-back code: only on/off, end date, name and note can be changed.',
    o_order: 'Order', o_customer: 'Customer', o_plan: 'Plan', o_orig: 'Price', o_final: 'Final', o_paid: 'Paid', o_status: 'Status', o_none: 'No orders with this code yet.',
    ost: { pending_payment: 'Pending payment', paid: 'Paid', completed: 'Completed', rejected: 'Rejected', expired: 'Expired', failed: 'Failed', cancelled: 'Cancelled' },
    tehran: 'Tehran time', need_customer: 'Pick at least one customer.', check: 'Rules', first_only: 'First purchase', minimum: 'Min',
  },
}
const useS = () => { const { lang } = useI18n(); return [T[lang] || T.fa, lang] }
const N = ({ children }) => <bdi dir="ltr" className="dc-num">{children}</bdi>

// ISO (any zone) → Tehran "YYYY-MM-DD" + "HH:MM"; and back with the +03:30 offset
const tehranParts = (iso) => {
  if (!iso) return { date: '', time: '' }
  const f = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Tehran', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })
  const p = Object.fromEntries(f.formatToParts(new Date(iso)).map((x) => [x.type, x.value]))
  return { date: `${p.year}-${p.month}-${p.day}`, time: `${p.hour === '24' ? '00' : p.hour}:${p.minute}` }
}
const toIso = (date, time) => (date ? `${date}T${time || '00:00'}:00+03:30` : null)

function DateTimeField({ label, value, onChange, s, lang, endOfDay }) {
  const [open, setOpen] = useState(false)
  const v = tehranParts(value)
  return (
    <div className="dc-fld">
      <span className="dc-l">{label} <small>({s.tehran})</small></span>
      <div className="dc-dt">
        <button type="button" className="input dc-dt-btn" onClick={() => setOpen(true)}>{value ? jalali(value, false, lang) : s.none}</button>
        <input className="input dc-dt-time" type="time" dir="ltr" aria-label={s.time} value={v.time} disabled={!value}
          onChange={(e) => onChange(toIso(v.date, e.target.value))} />
      </div>
      <DateRangeModal open={open} single initial={v.date} title={label} clearLabel={s.none} onClose={() => setOpen(false)}
        onApply={({ from }) => onChange(from ? toIso(from, v.time || (endOfDay ? '23:59' : '00:00')) : null)} />
    </div>
  )
}

function CustomerPicker({ value, onChange, s }) {
  const [q, setQ] = useState('')
  const [res, setRes] = useState([])
  useEffect(() => {
    if (q.trim().length < 2) { setRes([]); return undefined }
    const id = setTimeout(() => api.get('/admin/discounts/customers/', { params: { q } }).then((r) => setRes(r.data.results)).catch(() => setRes([])), 250)
    return () => clearTimeout(id)
  }, [q])
  const has = (u) => value.some((x) => x.id === u.id)
  return (
    <div className="dc-cust">
      <input className="input" value={q} placeholder={s.find_c} onChange={(e) => setQ(e.target.value)} />
      {res.length > 0 && (
        <ul className="dc-res">{res.map((u) => (
          <li key={u.id}><button type="button" disabled={has(u)} onClick={() => { onChange([...value, u]); setQ('') }}>
            <b dir="ltr">{u.username}</b><small>{[u.name, u.phone, u.telegram_username && '@' + u.telegram_username].filter(Boolean).join(' · ')}</small>
          </button></li>
        ))}</ul>
      )}
      <div className="dc-chips">{value.map((u) => (
        <span key={u.id} className="dc-chip"><bdi dir="ltr">{u.username}</bdi>
          <button type="button" aria-label="×" onClick={() => onChange(value.filter((x) => x.id !== u.id))}>×</button></span>
      ))}</div>
    </div>
  )
}

const blank = { code: '', name: '', is_active: true, starts_at: null, expires_at: null, discount_type: 'percent', percent: 10, max_discount: '',
  amount_off: '', audience: 'all', customers: [], first_purchase_only: false, plan_ids: [], applies_to: 'both', max_uses: '',
  max_uses_per_customer: 1, min_order_amount: '', note: '' }

function Editor({ row, plans, s, lang, onClose, onSaved }) {
  const wb = row?.kind === 'winback'
  const [f, setF] = useState(() => (row ? {
    ...blank, ...row, customers: row.customers || [], plan_ids: (row.plans || []).map((p) => p.id),
    max_discount: row.max_discount ?? '', amount_off: row.amount_off ?? '', max_uses: row.max_uses ?? '',
    max_uses_per_customer: row.max_uses_per_customer ?? '', min_order_amount: row.min_order_amount ?? '',
  } : { ...blank }))
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  const set = (k) => (e) => setF({ ...f, [k]: e?.target ? e.target.value : e })
  const num = (k) => (e) => setF({ ...f, [k]: e.target.value.replace(/[^\d]/g, '') })
  const rnd = () => { const a = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; const r = new Uint32Array(8); crypto.getRandomValues(r); setF({ ...f, code: Array.from(r, (x) => a[x % a.length]).join('') }) }
  const submit = async (e) => {
    e.preventDefault(); setErr('')
    if (!wb && f.audience === 'selected' && !f.customers.length) { setErr(s.need_customer); return }
    const nz = (v) => (v === '' || v == null ? null : v)
    const body = wb ? { is_active: f.is_active, expires_at: f.expires_at, name: f.name, note: f.note } : {
      code: f.code, name: f.name, is_active: f.is_active, starts_at: f.starts_at, expires_at: f.expires_at,
      discount_type: f.discount_type, percent: f.discount_type === 'percent' ? Number(f.percent || 0) : 0,
      max_discount: f.discount_type === 'percent' ? nz(f.max_discount) : null, amount_off: f.discount_type === 'fixed' ? nz(f.amount_off) : null,
      audience: f.audience, customer_ids: f.audience === 'selected' ? f.customers.map((u) => u.id) : [],
      first_purchase_only: f.first_purchase_only, plan_ids: f.plan_ids, applies_to: f.applies_to,
      max_uses: nz(f.max_uses), max_uses_per_customer: nz(f.max_uses_per_customer), min_order_amount: nz(f.min_order_amount), note: f.note,
    }
    setBusy(true)
    try {
      if (row) await api.patch(`/admin/discounts/${row.id}/`, body); else await api.post('/admin/discounts/', body)
      toast.success(row ? s.saved : s.created); onSaved()
    } catch (e2) { setErr(apiError(e2)) } finally { setBusy(false) }
  }
  const Seg = ({ k, opts }) => (
    <div className="dc-seg" role="radiogroup">{opts.map(([v, t]) => (
      <button key={v} type="button" role="radio" aria-checked={f[k] === v} className={f[k] === v ? 'on' : ''} onClick={() => setF({ ...f, [k]: v })}>{t}</button>
    ))}</div>
  )
  return (
    <div className="dc-back" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form className="dc-modal card" role="dialog" aria-modal="true" onSubmit={submit}>
        <div className="dc-mh"><h2>{row ? `${s.edit}: ${row.code}` : s.new}</h2><button type="button" className="dc-x" onClick={onClose} aria-label={s.close}>✕</button></div>
        <div className="dc-mb">
          <Alert>{err}</Alert>
          {wb && <Alert kind="warning">{s.wb_note}</Alert>}
          <div className="dc-grid">
            <label className="dc-fld"><span className="dc-l">{s.code}</span>
              <span className="dc-code-in"><input className="input" dir="ltr" maxLength={32} disabled={wb || !!row?.stats?.uses} value={f.code}
                placeholder={row ? '' : s.random} onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase().replace(/[^A-Z0-9_-]/g, '') })} />
                {!row && <button type="button" className="btn-ghost text-sm" onClick={rnd}>{s.random}</button>}</span></label>
            <label className="dc-fld"><span className="dc-l">{s.name}</span><input className="input" maxLength={100} value={f.name} onChange={set('name')} /></label>
          </div>
          <label className="dc-row"><Toggle checked={f.is_active} onChange={(v) => setF({ ...f, is_active: v })} label={s.active} /> {s.active}</label>
          <div className="dc-grid">
            {!wb && <DateTimeField label={s.start} value={f.starts_at} onChange={(v) => setF({ ...f, starts_at: v })} s={s} lang={lang} />}
            <DateTimeField label={s.end} value={f.expires_at} onChange={(v) => setF({ ...f, expires_at: v })} s={s} lang={lang} endOfDay />
          </div>
          {!wb && <>
            <div className="dc-sec"><span className="dc-l">{s.type}</span><Seg k="discount_type" opts={[['percent', s.percent], ['fixed', s.fixed]]} /></div>
            {f.discount_type === 'percent' ? (
              <div className="dc-grid">
                <label className="dc-fld"><span className="dc-l">{s.pct}</span><input className="input" dir="ltr" inputMode="numeric" value={f.percent} onChange={num('percent')} /></label>
                <label className="dc-fld"><span className="dc-l">{s.max}</span><input className="input" dir="ltr" inputMode="numeric" value={f.max_discount} onChange={num('max_discount')} /></label>
              </div>
            ) : (
              <label className="dc-fld"><span className="dc-l">{s.amount}</span><input className="input" dir="ltr" inputMode="numeric" value={f.amount_off} onChange={num('amount_off')} /></label>
            )}
            <div className="dc-sec"><span className="dc-l">{s.who}</span><Seg k="audience" opts={[['all', s.all_c], ['selected', s.sel_c]]} /></div>
            {f.audience === 'selected' && <CustomerPicker value={f.customers} onChange={(v) => setF({ ...f, customers: v })} s={s} />}
            <label className="dc-row"><Toggle checked={f.first_purchase_only} onChange={(v) => setF({ ...f, first_purchase_only: v })} label={s.first} /> {s.first}</label>
            <div className="dc-sec"><span className="dc-l">{s.plans}</span>
              <div className="dc-plans">
                <label className="dc-chk"><input type="checkbox" checked={!f.plan_ids.length} onChange={() => setF({ ...f, plan_ids: [] })} /> {s.all_p}</label>
                {plans.map((p) => (
                  <label key={p.id} className="dc-chk" data-off={!p.is_active || undefined}><input type="checkbox" checked={f.plan_ids.includes(p.id)}
                    onChange={() => setF({ ...f, plan_ids: f.plan_ids.includes(p.id) ? f.plan_ids.filter((x) => x !== p.id) : [...f.plan_ids, p.id] })} />
                    {lang === 'en' ? (p.name_en || p.name_fa) : p.name_fa}</label>
                ))}
              </div>
            </div>
            <div className="dc-sec"><span className="dc-l">{s.for}</span><Seg k="applies_to" opts={[['new', s.f_new], ['renew', s.f_renew], ['both', s.f_both]]} /></div>
            <div className="dc-sec"><span className="dc-l">{s.limits} <small>({s.empty_unl})</small></span>
              <div className="dc-grid dc-grid3">
                <label className="dc-fld"><span className="dc-s">{s.max_uses}</span><input className="input" dir="ltr" inputMode="numeric" value={f.max_uses} onChange={num('max_uses')} /></label>
                <label className="dc-fld"><span className="dc-s">{s.per_c}</span><input className="input" dir="ltr" inputMode="numeric" value={f.max_uses_per_customer} onChange={num('max_uses_per_customer')} /></label>
                <label className="dc-fld"><span className="dc-s">{s.min}</span><input className="input" dir="ltr" inputMode="numeric" value={f.min_order_amount} onChange={num('min_order_amount')} /></label>
              </div>
            </div>
          </>}
          <label className="dc-fld"><span className="dc-l">{s.note}</span><input className="input" maxLength={255} value={f.note} onChange={set('note')} /></label>
        </div>
        <div className="dc-mf">
          <button type="button" className="btn-ghost text-sm" onClick={onClose}>{s.cancel}</button>
          <button className="btn-primary text-sm" disabled={busy}>{busy ? '…' : (row ? s.save : s.create)}</button>
        </div>
      </form>
    </div>
  )
}

function Report({ id, s, lang, onClose }) {
  const [d, setD] = useState(null)
  useEffect(() => { api.get(`/admin/discounts/${id}/report/`).then((r) => setD(r.data)).catch(() => setD(false)) }, [id])
  return (
    <div className="dc-back" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dc-modal card" role="dialog" aria-modal="true">
        <div className="dc-mh"><h2>{s.report}{d && <>: <bdi dir="ltr">{d.code.code}</bdi></>}</h2><button type="button" className="dc-x" onClick={onClose} aria-label={s.close}>✕</button></div>
        <div className="dc-mb">
          {d === null ? <Spinner /> : !d ? <Alert>{s.o_none}</Alert> : <>
            <dl className="dc-kpis dc-kpis--sm">
              <div><dt>{s.k_uses}</dt><dd><N>{digits(d.stats.uses, lang)}</N></dd></div>
              <div><dt>{s.customers}</dt><dd><N>{digits(d.stats.customers, lang)}</N></dd></div>
              <div><dt>{s.k_disc}</dt><dd>{toman(d.stats.discount, lang)}</dd></div>
              <div><dt>{s.k_rev}</dt><dd>{toman(d.stats.revenue, lang)}</dd></div>
            </dl>
            {d.orders.length === 0 ? <p className="text-sm text-muted">{s.o_none}</p> : (
              <ul className="dc-orders">{d.orders.map((o) => (
                <li key={o.id}>
                  <div className="dc-o-h"><b>#{o.id}</b><bdi dir="ltr">{o.user}</bdi><span className="dc-o-st" data-st={o.status}>{s.ost[o.status] || o.status}</span></div>
                  <div className="dc-o-b">
                    <span>{lang === 'en' ? (o.plan_en || o.plan) : o.plan}</span>
                    <span><s>{toman(o.original, lang)}</s> → <b>{toman(o.final, lang)}</b> <small>(−{toman(o.discount, lang)})</small></span>
                    <span>{jalali(o.created_at, true, lang)}</span>
                  </div>
                </li>
              ))}</ul>
            )}
          </>}
        </div>
      </div>
    </div>
  )
}

function rule(c, s, lang) {
  const off = c.discount_type === 'fixed' ? toman(c.amount_off, lang)
    : `${digits(c.percent, lang)}%${c.max_discount ? ` (${s.upto} ${toman(c.max_discount, lang)})` : ''}`
  const bits = [off]
  if (c.kind === 'winback' && c.owner) bits.push(`${s.owner}: ${c.owner.username}`)
  else if (c.audience === 'selected') bits.push(`${digits(c.customers.length, lang)} ${s.customers}`)
  if (c.plans?.length) bits.push(c.plans.map((p) => (lang === 'en' ? p.name_en || p.name_fa : p.name_fa)).join('، '))
  if (c.applies_to !== 'both') bits.push(c.applies_to === 'new' ? s.f_new : s.f_renew)
  if (c.first_purchase_only) bits.push(s.first_only)
  if (c.min_order_amount) bits.push(`${s.minimum} ${toman(c.min_order_amount, lang)}`)
  return bits
}

export default function Discounts() {
  const [s, lang] = useS()
  const { can } = useAuth()
  const manage = can('discounts.manage')
  const toast = useToast()
  const [kind, setKind] = useState('')
  const [status, setStatus] = useState('')
  const [q, setQ] = useState('')
  const [rows, setRows] = useState(null)
  const [sum, setSum] = useState(null)
  const [plans, setPlans] = useState([])
  const [err, setErr] = useState('')
  const [edit, setEdit] = useState(null)
  const [rep, setRep] = useState(null)
  const load = () => {
    api.get('/admin/discounts/', { params: { limit: 200, ...(kind ? { kind } : {}), ...(status ? { status } : {}), ...(q.trim() ? { search: q.trim() } : {}) } })
      .then((r) => { setRows(r.data.results); setErr('') }).catch((e) => { setErr(apiError(e)); setRows([]) })
    api.get('/admin/discounts/summary/').then((r) => setSum(r.data)).catch(() => {})
  }
  useEffect(() => { const id = setTimeout(load, q ? 300 : 0); return () => clearTimeout(id) }, [kind, status, q])
  useEffect(() => { if (manage) api.get('/admin/discounts/options/').then((r) => setPlans(r.data.plans)).catch(() => {}) }, [manage])
  const toggle = async (c) => {
    try { await api.patch(`/admin/discounts/${c.id}/`, { is_active: !c.is_active }); toast.success(s.saved); load() } catch (e) { toast.error(apiError(e)) }
  }
  const usesText = (c) => `${digits(c.stats.uses, lang)}${c.max_uses ? ` ${s.of} ${digits(c.max_uses, lang)}` : ''}`
  const Actions = ({ c }) => (
    <div className="dc-acts">
      <button type="button" className="dc-btn" onClick={() => setRep(c.id)}>{s.report}</button>
      {manage && <button type="button" className="dc-btn" onClick={() => setEdit({ row: c })}>{s.edit}</button>}
      {manage && <button type="button" className={'dc-btn' + (c.is_active ? ' dc-btn--off' : '')} onClick={() => toggle(c)}>{c.is_active ? s.disable : s.enable}</button>}
    </div>
  )
  const Validity = ({ c }) => <>{c.starts_at ? jalali(c.starts_at, true, lang) : '—'} → {c.expires_at ? jalali(c.expires_at, true, lang) : s.unl}</>
  return (
    <div className="dc space-y-4">
      <style>{CSS + DRP_CSS}</style>
      <div className="dc-head">
        <div><h1 className="text-lg font-bold">{s.title}</h1><p className="text-sm text-muted">{s.sub}</p></div>
        {manage && <button type="button" className="btn-primary text-sm" onClick={() => setEdit({ row: null })}>+ {s.new}</button>}
      </div>
      {sum && (
        <dl className="dc-kpis">
          <div><dt>{s.k_active}</dt><dd><N>{digits(sum.active, lang)}</N>{sum.scheduled > 0 && <small> · {digits(sum.scheduled, lang)} {s.k_sched}</small>}</dd></div>
          <div><dt>{s.k_uses}</dt><dd><N>{digits(sum.uses, lang)}</N></dd></div>
          <div><dt>{s.k_disc}</dt><dd>{toman(sum.discount, lang)}</dd></div>
          <div><dt>{s.k_rev}</dt><dd>{toman(sum.revenue, lang)}</dd></div>
        </dl>
      )}
      <div className="dc-filters">
        <div className="dc-seg">{[['', s.all], ['campaign', s.campaign], ['winback', s.winback]].map(([v, t]) => (
          <button key={v} type="button" className={kind === v ? 'on' : ''} onClick={() => setKind(v)}>{t}</button>))}</div>
        <select className="input dc-sel" value={status} onChange={(e) => setStatus(e.target.value)} aria-label={s.o_status}>
          <option value="">{s.all}</option>{['active', 'scheduled', 'expired', 'disabled'].map((v) => <option key={v} value={v}>{s['st_' + v]}</option>)}
        </select>
        <input className="input dc-q" value={q} placeholder={s.search} onChange={(e) => setQ(e.target.value)} />
      </div>
      <Alert>{err}</Alert>
      {rows === null ? <div className="grid place-items-center py-10"><Spinner /></div> : rows.length === 0 ? <div className="card text-sm text-muted">{s.no_codes}</div> : <>
        <div className="card p-0 dc-table-wrap dc-desk">
          <table className="dc-table">
            <thead><tr><th>{s.code}</th><th>{s.check}</th><th>{s.start} / {s.end}</th><th>{s.uses}</th><th>{s.disc}</th><th>{s.rev}</th><th /></tr></thead>
            <tbody>{rows.map((c) => (
              <tr key={c.id} data-off={!c.is_active || undefined}>
                <td><b className="dc-code" dir="ltr">{c.code}</b><div className="dc-tags"><span className="dc-kind" data-k={c.kind}>{s[c.kind]}</span><span className="dc-st" data-st={c.status}>{s['st_' + c.status]}</span></div>{c.name && <small className="dc-name">{c.name}</small>}</td>
                <td className="dc-rule">{rule(c, s, lang).map((b, i) => <span key={i}>{b}</span>)}</td>
                <td className="dc-small"><Validity c={c} /></td>
                <td><N>{usesText(c)}</N>{c.stats.held > c.stats.uses && <small className="dc-held"> · {digits(c.stats.held - c.stats.uses, lang)} {s.held}</small>}</td>
                <td>{toman(c.stats.discount, lang)}</td>
                <td>{toman(c.stats.revenue, lang)}</td>
                <td><Actions c={c} /></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <div className="dc-cards dc-mob">{rows.map((c) => (
          <article key={c.id} className="card dc-card" data-off={!c.is_active || undefined}>
            <div className="dc-card-h"><b className="dc-code" dir="ltr">{c.code}</b><span className="dc-st" data-st={c.status}>{s['st_' + c.status]}</span></div>
            <div className="dc-tags"><span className="dc-kind" data-k={c.kind}>{s[c.kind]}</span>{c.name && <span className="dc-name">{c.name}</span>}</div>
            <div className="dc-rule">{rule(c, s, lang).map((b, i) => <span key={i}>{b}</span>)}</div>
            <div className="dc-small"><Validity c={c} /></div>
            <dl className="dc-card-n">
              <div><dt>{s.uses}</dt><dd><N>{usesText(c)}</N></dd></div>
              <div><dt>{s.disc}</dt><dd>{toman(c.stats.discount, lang)}</dd></div>
              <div><dt>{s.rev}</dt><dd>{toman(c.stats.revenue, lang)}</dd></div>
            </dl>
            <Actions c={c} />
          </article>
        ))}</div>
      </>}
      {edit && <Editor row={edit.row} plans={plans} s={s} lang={lang} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load() }} />}
      {rep && <Report id={rep} s={s} lang={lang} onClose={() => setRep(null)} />}
    </div>
  )
}

const CSS = `
.dc-head { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 10px; }
.dc-num { font-variant-numeric: tabular-nums; }
.dc-kpis { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 160px), 1fr)); }
.dc-kpis > div { padding: 12px 14px; border-radius: 14px; border: 1px solid var(--c-border); background: var(--c-surface); min-width: 0; }
.dc-kpis dt { font-size: 11.5px; font-weight: 700; color: var(--c-text-muted); }
.dc-kpis dd { font-size: 16px; font-weight: 800; margin-top: 2px; overflow-wrap: anywhere; }
.dc-kpis--sm dd { font-size: 14px; }
.dc-kpis small { font-size: 11px; font-weight: 600; color: var(--c-text-muted); }
.dc-filters { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.dc-q { flex: 1 1 180px; min-width: 0; } .dc-sel { width: auto; flex: 0 0 auto; }
.dc-seg { display: inline-flex; flex-wrap: wrap; gap: 3px; padding: 3px; border-radius: 11px; border: 1px solid var(--c-border); }
.dc-seg button { min-height: 34px; padding: 5px 12px; border-radius: 8px; font-size: 13px; font-weight: 700; color: var(--c-text-muted); background: transparent; border: 0; cursor: pointer; }
.dc-seg button.on { color: #fff; background: var(--c-primary); }
.dc-table-wrap { overflow-x: auto; }
.dc-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.dc-table th { text-align: start; font-size: 12px; color: var(--c-text-muted); padding: 10px 12px; border-bottom: 1px solid var(--c-border); white-space: nowrap; }
.dc-table td { padding: 10px 12px; border-bottom: 1px solid var(--c-border); vertical-align: top; }
.dc-table tr[data-off] td, .dc-card[data-off] { opacity: .6; }
.dc-code { font-family: ui-monospace, monospace; font-size: 14px; letter-spacing: .03em; overflow-wrap: anywhere; }
.dc-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.dc-kind, .dc-st { font-size: 11px; font-weight: 700; padding: 1px 8px; border-radius: 999px; border: 1px solid var(--c-border); color: var(--c-text-muted); white-space: nowrap; }
.dc-kind[data-k="winback"] { color: #7C3AED; border-color: color-mix(in srgb, #7C3AED 35%, transparent); }
.dc-st[data-st="active"] { color: var(--c-success); border-color: color-mix(in srgb, var(--c-success) 40%, transparent); }
.dc-st[data-st="scheduled"] { color: var(--c-primary); border-color: color-mix(in srgb, var(--c-primary) 40%, transparent); }
.dc-st[data-st="expired"], .dc-st[data-st="used_up"] { color: var(--c-warning); border-color: color-mix(in srgb, var(--c-warning) 40%, transparent); }
.dc-st[data-st="disabled"] { color: var(--c-danger); border-color: color-mix(in srgb, var(--c-danger) 40%, transparent); }
.dc-name { display: block; font-size: 12px; color: var(--c-text-muted); margin-top: 2px; }
.dc-rule { display: flex; flex-wrap: wrap; gap: 4px 10px; font-size: 12.5px; }
.dc-rule span:first-child { font-weight: 800; }
.dc-small { font-size: 12px; color: var(--c-text-muted); }
.dc-held { color: var(--c-warning); }
.dc-acts { display: flex; flex-wrap: wrap; gap: 6px; }
.dc-btn { min-height: 34px; padding: 5px 12px; border-radius: 9px; font-size: 12.5px; font-weight: 700; border: 1px solid var(--c-border); background: transparent; color: var(--c-text); cursor: pointer; white-space: nowrap; }
.dc-btn--off { color: var(--c-danger); border-color: color-mix(in srgb, var(--c-danger) 35%, transparent); }
.dc-cards { display: flex; flex-direction: column; gap: 10px; }
.dc-card { display: flex; flex-direction: column; gap: 8px; padding: 14px; min-width: 0; }
.dc-card-h { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-width: 0; }
.dc-card-n { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; }
.dc-card-n > div { min-width: 0; } .dc-card-n dt { font-size: 11px; color: var(--c-text-muted); font-weight: 700; } .dc-card-n dd { font-size: 13px; font-weight: 800; overflow-wrap: anywhere; }
.dc-mob { display: none; }
@media (max-width: 767px) { .dc-desk { display: none; } .dc-mob { display: flex; } }
.dc-back { position: fixed; inset: 0; z-index: 80; background: rgb(0 0 0 / .45); display: grid; place-items: end center; }
@media (min-width: 640px) { .dc-back { place-items: center; padding: 16px; } }
.dc-modal { width: min(100%, 720px); max-height: 92vh; display: flex; flex-direction: column; padding: 0; border-radius: 18px 18px 0 0; overflow: hidden; }
.dc .dc-modal { background: var(--c-surface, #fff); -webkit-backdrop-filter: none; backdrop-filter: none; box-shadow: 0 24px 64px rgb(0 0 0 / .35); }
.dark .dc .dc-modal, .dark .dc-modal { background: #11151f; }
@media (min-width: 640px) { .dc-modal { border-radius: 18px; } }
.dc-mh { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 14px 16px; border-bottom: 1px solid var(--c-border); }
.dc-mh h2 { font-weight: 800; font-size: 15px; min-width: 0; overflow-wrap: anywhere; }
.dc-x { width: 34px; height: 34px; border-radius: 10px; border: 1px solid var(--c-border); background: transparent; color: var(--c-text); flex-shrink: 0; }
.dc-mb { padding: 14px 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; }
.dc-mf { display: flex; justify-content: flex-end; gap: 8px; padding: 12px 16px; border-top: 1px solid var(--c-border); }
.dc-grid { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); }
.dc-grid3 { grid-template-columns: repeat(auto-fit, minmax(min(100%, 150px), 1fr)); }
.dc-fld { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.dc-l { font-size: 12.5px; font-weight: 700; } .dc-l small { font-weight: 500; color: var(--c-text-muted); }
.dc-s { font-size: 12px; color: var(--c-text-muted); font-weight: 600; }
.dc-sec { display: flex; flex-direction: column; gap: 6px; }
.dc-row { display: flex; align-items: center; gap: 10px; font-size: 13px; font-weight: 600; }
.dc-code-in { display: flex; gap: 6px; } .dc-code-in .input { flex: 1 1 auto; min-width: 0; font-family: ui-monospace, monospace; }
.dc-dt { display: flex; gap: 6px; } .dc-dt-btn { flex: 1 1 auto; min-width: 0; text-align: start; cursor: pointer; } .dc-dt-time { flex: 0 0 110px; }
.dc-cust { display: flex; flex-direction: column; gap: 6px; position: relative; }
.dc-res { border: 1px solid var(--c-border); border-radius: 12px; overflow: hidden; max-height: 220px; overflow-y: auto; }
.dc-res button { width: 100%; display: flex; flex-direction: column; align-items: flex-start; padding: 8px 12px; background: transparent; border: 0; border-bottom: 1px solid var(--c-border); color: var(--c-text); text-align: start; cursor: pointer; }
.dc-res button:disabled { opacity: .45; } .dc-res small { font-size: 11.5px; color: var(--c-text-muted); }
.dc-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.dc-chip { display: inline-flex; align-items: center; gap: 6px; padding: 3px 4px 3px 10px; border-radius: 999px; font-size: 12.5px; background: color-mix(in srgb, var(--c-primary) 12%, transparent); }
[dir="rtl"] .dc-chip { padding: 3px 10px 3px 4px; }
.dc-chip button { width: 22px; height: 22px; border-radius: 999px; border: 0; background: transparent; color: inherit; cursor: pointer; }
.dc-plans { display: flex; flex-wrap: wrap; gap: 6px; }
.dc-chk { display: inline-flex; align-items: center; gap: 6px; padding: 6px 10px; border-radius: 10px; border: 1px solid var(--c-border); font-size: 13px; cursor: pointer; }
.dc-chk[data-off] { opacity: .6; }
.dc-orders { display: flex; flex-direction: column; gap: 8px; }
.dc-orders li { padding: 10px 12px; border: 1px solid var(--c-border); border-radius: 12px; display: flex; flex-direction: column; gap: 4px; font-size: 13px; }
.dc-o-h { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.dc-o-b { display: flex; flex-wrap: wrap; gap: 4px 14px; color: var(--c-text-muted); font-size: 12.5px; } .dc-o-b b { color: var(--c-text); }
.dc-o-st { margin-inline-start: auto; font-size: 11.5px; font-weight: 700; }
.dc-o-st[data-st="completed"], .dc-o-st[data-st="paid"] { color: var(--c-success); }
.dc-o-st[data-st="rejected"], .dc-o-st[data-st="cancelled"] { color: var(--c-danger); }
`
