import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useAuth } from '../lib/auth'
import { jalali } from '../lib/format'
import { Toggle } from './ui'
import { useToast } from './Toast'
import { useConfirm } from './ConfirmDialog'

// Super Admin cards on the Settings page (v1.32). They save only their own keys to
// /admin/settings/ (the server refuses these keys for anyone but a Super Admin).
const T = {
  fa: {
    save: 'ذخیره', saving: '…', super: 'فقط سوپرادمین', saved: 'ذخیره شد',
    ap_h: 'حذف دائمی خودکار کاربران حذف‌شده',
    ap_sub: 'کاربرانی که بیش از N روز در سطل حذف‌شده‌ها مانده‌اند، روزی یک بار برای همیشه حذف می‌شوند.',
    ap_on: 'حذف دائمی خودکار', ap_on_h: 'پیش‌فرض: خاموش',
    ap_days: 'پس از چند روز', ap_days_h: 'پیش‌فرض: 30 روز',
    ap_info: 'همان «حذف دائمی» دستی اجرا می‌شود: حساب‌های پاسارگارد هم حذف می‌شوند؛ اگر پاسارگارد خطا بدهد، آن کاربر حذف نمی‌شود و فردا دوباره امتحان می‌شود. سفارش‌ها و پرداخت‌ها بی‌نام می‌مانند و جمع حسابداری تغییر نمی‌کند. هر حذف در گزارش ممیزی ثبت می‌شود.',
    ap_next: 'اجرای بعدی', ap_page: 'صفحهٔ کاربران حذف‌شده ›',
    ap_c_title: 'روشن کردن حذف دائمی خودکار؟',
    ap_c_msg: 'از این پس هر روز کاربرانی که بیش از {d} روز پیش حذف شده‌اند، همراه حساب پاسارگارد، برای همیشه حذف می‌شوند. این کار برگشت‌پذیر نیست.',
    ap_c_now: 'در اجرای بعدی: {n} کاربر', ap_c_btn: 'بله، روشن شود',
    r_h: 'تأیید خودکار مبلغ گرد شده',
    r_sub: 'واریزی که کمی کمتر از مبلغ فاکتور است (بلو و پیامک)، فقط با همهٔ شرط‌های زیر خودکار تأیید می‌شود.',
    r_on: 'تأیید خودکار مبلغ گرد شده', r_on_h: 'پیش‌فرض: روشن',
    r_toman: 'حداکثر کسری (تومان)', r_toman_h: 'پیش‌فرض: 2000',
    r_pct: 'یا حداکثر درصد از فاکتور', r_pct_h: 'پیش‌فرض: 1 — هر کدام بیشتر باشد',
    r_rules: [
      'واریز کمتر از فاکتور است (هرگز بیشتر) و کسری از سقف بالا بیشتر نیست؛',
      'در بازهٔ زمانی سفارش است (همان شرط تطبیق دقیق)؛',
      'فقط یک سفارش در انتظار با این شرایط جور است — اگر دو یا بیشتر، به صف می‌رود؛',
      'مشتری رسید همین سفارش را آپلود کرده، یا ۴ رقم آخر کارت واریزکننده با کارتی که قبلاً از آن پرداخت کرده یکی است.',
    ],
    r_after: 'پرداخت با برچسب «تأیید خودکار – مبلغ گرد شده» و مبلغ واقعی واریز ثبت می‌شود (کسری در حسابداری دیده می‌شود)، هشدار تلگرام و پنل می‌رود و سوپرادمین می‌تواند از صفحهٔ تراکنش «لغو تأیید» بزند. بقیه مثل قبل با «مبلغ نامطابق» به صف می‌روند.',
  },
  en: {
    save: 'Save', saving: '…', super: 'Super Admin only', saved: 'Saved',
    ap_h: 'Auto-purge deleted users',
    ap_sub: 'Users that sat in the trash for more than N days are permanently deleted, once a day.',
    ap_on: 'Auto-purge', ap_on_h: 'default: off',
    ap_days: 'After how many days', ap_days_h: 'default: 30 days',
    ap_info: 'It runs the same “Delete permanently” as the button: PasarGuard accounts are deleted too; if PasarGuard fails, that user is kept and retried the next day. Orders and payments stay, anonymized, so Accounting totals do not change. Every purge is audit-logged.',
    ap_next: 'Next run', ap_page: 'Deleted users page ›',
    ap_c_title: 'Turn on the auto-purge?',
    ap_c_msg: 'From now on, every day, users deleted more than {d} days ago are permanently deleted together with their PasarGuard accounts. This cannot be undone.',
    ap_c_now: 'On the next run: {n} user(s)', ap_c_btn: 'Yes, turn it on',
    r_h: 'Rounded-amount auto-approve',
    r_sub: 'A deposit a little below the invoice (Blu and SMS) is approved automatically only when ALL of these hold.',
    r_on: 'Rounded-amount auto-approve', r_on_h: 'default: on',
    r_toman: 'Max shortfall (toman)', r_toman_h: 'default: 2000',
    r_pct: 'or max % of the invoice', r_pct_h: 'default: 1 — whichever is larger',
    r_rules: [
      'the deposit is below the invoice (never above) and the shortfall is within the limit above;',
      'it is inside the order’s time window (same guard as exact matching);',
      'exactly one pending order fits — with two or more it goes to the queue;',
      'the customer uploaded a receipt for that order, or the payer card’s last 4 digits match a card they paid from before.',
    ],
    r_after: 'The payment is recorded as “Auto-approved — rounded amount” with the amount actually paid (the shortfall shows in Accounting), staff get a Telegram + panel alert, and a Super Admin can “Undo approval” on the transaction page. Anything else goes to the queue as “Amount mismatch”, as before.',
  },
}

const AP_KEYS = ['deleted_purge_enabled', 'deleted_purge_days']
const R_KEYS = ['rounded_auto_enabled', 'rounded_max_toman', 'rounded_max_percent']

function useSettings(keys) {
  const [vals, setVals] = useState(null)
  const load = () => api.get('/admin/settings/').then((r) => {
    const all = Object.fromEntries(r.data.settings.map((x) => [x.key, x.value]))
    setVals(Object.fromEntries(keys.map((k) => [k, all[k]])))
  }).catch(() => setVals({}))
  useEffect(() => { load() }, [])
  return [vals, load]
}

function Card({ id, title, sub, children, onSave, busy, dirty, canEdit, s }) {
  return (
    <form id={id} className="card st-card sup-card" onSubmit={onSave} data-testid={id}>
      <div className="st-card-head">
        <div className="min-w-0">
          <h3 className="font-bold text-sm">{title} <span className="sup-badge">{s.super}</span></h3>
          <p className="text-xs text-muted mt-0.5">{sub}</p>
        </div>
        {canEdit && <button className="btn-primary text-xs sup-save" disabled={busy || !dirty}>{busy ? s.saving : s.save}</button>}
      </div>
      <div className="sup-body">{children}</div>
    </form>
  )
}

function Num({ label, hint, value, onChange, min, max, step, disabled }) {
  return (
    <label className="st-fld">
      <span className="st-fld-top"><span className="label">{label}</span><span className="st-hint">{hint}</span></span>
      <input className="input mono-num" dir="ltr" type="number" min={min} max={max} step={step || 1} disabled={disabled}
        value={value ?? ''} onChange={(e) => onChange(e.target.value)} />
    </label>
  )
}

function Switch({ label, hint, checked, onChange, disabled }) {
  return (
    <div className="st-toggle-row">
      <span className="min-w-0"><span className="block text-sm">{label}</span><span className="block text-xs text-muted mt-0.5">{hint}</span></span>
      <Toggle checked={!!checked} onChange={onChange} disabled={disabled} label={label} />
    </div>
  )
}

export function AutoPurgeCard() {
  const { lang } = useI18n()
  const { staff } = useAuth()
  const s = T[lang] || T.fa
  const toast = useToast()
  const confirm = useConfirm()
  const [vals, reload] = useSettings(AP_KEYS)
  const [form, setForm] = useState(null)
  const [st, setSt] = useState(null)
  const [busy, setBusy] = useState(false)
  const canEdit = !!staff?.is_superadmin
  const loadStatus = () => api.get('/admin/deleted-users/auto-purge/').then((r) => setSt(r.data)).catch(() => {})
  useEffect(() => { if (vals) setForm(vals) }, [vals])
  useEffect(() => { loadStatus() }, [])
  if (!form) return null
  const dirty = JSON.stringify(form) !== JSON.stringify(vals)
  const put = async () => {
    await api.put('/admin/settings/', { deleted_purge_enabled: !!form.deleted_purge_enabled, deleted_purge_days: Number(form.deleted_purge_days) })
    reload(); loadStatus()
  }
  const save = async (e) => {
    e.preventDefault()
    if (form.deleted_purge_enabled && !vals.deleted_purge_enabled) {
      let n = null
      try { n = (await api.get('/admin/deleted-users/auto-purge/', { params: { days: Number(form.deleted_purge_days) } })).data.would_purge } catch { /* shown without the count */ }
      await confirm({
        tone: 'danger', icon: 'trash', badge: 'superadmin',
        title: s.ap_c_title, message: s.ap_c_msg.replace('{d}', form.deleted_purge_days),
        content: n != null ? <p className="sup-due">{s.ap_c_now.replace('{n}', n)}</p> : null,
        confirmLabel: s.ap_c_btn, action: put,
      })
      return
    }
    setBusy(true)
    try { await put(); toast.success(s.saved) } catch (e2) { toast.error(apiError(e2)) } finally { setBusy(false) }
  }
  return (
    <Card id="auto-purge" title={s.ap_h} sub={s.ap_sub} onSave={save} busy={busy} dirty={dirty} canEdit={canEdit} s={s}>
      <Switch label={s.ap_on} hint={s.ap_on_h} checked={form.deleted_purge_enabled} disabled={!canEdit}
        onChange={(v) => setForm({ ...form, deleted_purge_enabled: v })} />
      <div className="st-fields sup-fields">
        <Num label={s.ap_days} hint={s.ap_days_h} min={1} max={3650} disabled={!canEdit}
          value={form.deleted_purge_days} onChange={(v) => setForm({ ...form, deleted_purge_days: v })} />
      </div>
      {st?.enabled && st.next_run && (
        <p className="sup-next">{s.ap_next}: <b className="mono-num">{jalali(st.next_run, true, lang)}</b></p>
      )}
      <p className="sup-info">{s.ap_info}</p>
      <Link to="/users/deleted" className="sup-link">{s.ap_page}</Link>
    </Card>
  )
}

export function RoundedCard() {
  const { lang } = useI18n()
  const { staff } = useAuth()
  const s = T[lang] || T.fa
  const toast = useToast()
  const [vals, reload] = useSettings(R_KEYS)
  const [form, setForm] = useState(null)
  const [busy, setBusy] = useState(false)
  const canEdit = !!staff?.is_superadmin
  useEffect(() => { if (vals) setForm(vals) }, [vals])
  if (!form) return null
  const dirty = JSON.stringify(form) !== JSON.stringify(vals)
  const save = async (e) => {
    e.preventDefault(); setBusy(true)
    try {
      await api.put('/admin/settings/', { rounded_auto_enabled: !!form.rounded_auto_enabled,
        rounded_max_toman: Number(form.rounded_max_toman), rounded_max_percent: String(form.rounded_max_percent) })
      toast.success(s.saved); reload()
    } catch (e2) { toast.error(apiError(e2)) } finally { setBusy(false) }
  }
  return (
    <Card id="rounded-amount" title={s.r_h} sub={s.r_sub} onSave={save} busy={busy} dirty={dirty} canEdit={canEdit} s={s}>
      <Switch label={s.r_on} hint={s.r_on_h} checked={form.rounded_auto_enabled} disabled={!canEdit}
        onChange={(v) => setForm({ ...form, rounded_auto_enabled: v })} />
      <div className="st-fields sup-fields">
        <Num label={s.r_toman} hint={s.r_toman_h} min={0} max={1000000} disabled={!canEdit}
          value={form.rounded_max_toman} onChange={(v) => setForm({ ...form, rounded_max_toman: v })} />
        <Num label={s.r_pct} hint={s.r_pct_h} min={0} max={10} step="0.1" disabled={!canEdit}
          value={form.rounded_max_percent} onChange={(v) => setForm({ ...form, rounded_max_percent: v })} />
      </div>
      <ol className="sup-rules">{s.r_rules.map((r, i) => <li key={i}>{r}</li>)}</ol>
      <p className="sup-info">{s.r_after}</p>
    </Card>
  )
}

export const SUPER_CSS = `
.sup-body { padding: 8px 20px 18px; display: flex; flex-direction: column; gap: 10px; }
.sup-fields { padding: 0; }
.sup-badge { white-space: nowrap; display: inline-block; font-size: 10.5px; font-weight: 700; padding: 1px 8px; border-radius: 999px; margin-inline-start: 6px; vertical-align: middle;
  color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 16%, transparent); }
.sup-info { font-size: 12px; line-height: 1.8; color: var(--c-text-muted); }
.sup-next { font-size: 13px; }
.sup-due { font-weight: 700; color: var(--c-danger-fg); }
.sup-rules { font-size: 12.5px; line-height: 1.8; padding-inline-start: 20px; list-style: decimal; }
.sup-link { font-size: 13px; color: var(--c-primary); align-self: flex-start; min-height: 44px; display: inline-flex; align-items: center; }
@media (max-width: 767px) {
  .sup-body { padding: 8px 14px 16px; }
  .sup-card .input { font-size: 16px; min-height: 44px; }
  .sup-save { min-height: 44px; width: 100%; }
}
`
