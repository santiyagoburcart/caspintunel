import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { jalali, toman } from '../lib/format'
import { Alert, Spinner } from './ui'
import { useConfirm } from './ConfirmDialog'
import { useToast } from './Toast'
import { apiError } from '../lib/api'
import { usePaymentsEvents } from '../lib/livePayments'

// Blu Bank deposits pushed by the Iran-side collector (backend payments_sms/blu.py).
const T = {
  fa: {
    health_on: 'جمع‌کننده متصل است', health_off: 'جمع‌کننده آفلاین است', health_never: 'هنوز دسته‌ای از جمع‌کننده نرسیده',
    health_disabled: 'وب‌هوک بلو پیکربندی نشده (BLU_PUSH_SECRET)', last_batch: 'آخرین دسته',
    offline_hint: 'بیش از {m} دقیقه خبری نیست — تأیید خودکار بلو متوقف است؛ پیامک آیفون همچنان کار می‌کند.',
    f_all: 'همه', f_unmatched: 'تطبیق‌نشده', f_matched: 'تأییدشده', f_duplicate: 'تکراری', f_ignored: 'نادیده',
    st_unmatched: 'تطبیق‌نشده', st_matched: 'تأییدشده', st_duplicate: 'تکراری', st_ignored: 'نادیده',
    payer: 'واریزکننده', card: 'کارت', receipt: 'شماره پیگیری', reference: 'شماره مرجع', order: 'سفارش',
    open_tx: 'مشاهدهٔ تراکنش', none: 'واریزی ثبت نشده است', none_f: 'موردی در این دسته نیست',
    attach: 'اتصال به سفارش', order_ph: 'شماره سفارش', load_fail: 'دریافت واریزهای بلو ناموفق بود',
    a_title: 'اتصال واریز به سفارش', a_btn: 'بله، تأیید و تحویل سرویس',
    a_msg: 'واریز {amount} به سفارش #{id} وصل می‌شود؛ پرداخت تأیید و سرویس تحویل داده می‌شود.',
    a_audit: 'این عملیات با نام کاربری شما در گزارش ممیزی ثبت می‌شود.',
    svc: 'سرویس روی سرور ایران', svc_active: 'فعال', svc_inactive: 'غیرفعال', svc_unknown: 'نامعلوم',
    svc_check: 'آخرین بررسی', svc_never: 'هنوز بررسی نشده', svc_err: 'آخرین خطا',
    svc_ssh: 'اتصال SSH {n} بار پشت سر هم ناموفق', svc_errs: '{n} خطا در 10 دقیقهٔ اخیر',
    rounded: 'تأیید خودکار – مبلغ گرد شده', shortfall: 'کسری',
    set_h: 'تنظیمات پایش جمع‌کننده', set_sub: 'در پایگاه داده ذخیره می‌شود، بر .env مقدم است و بدون ری‌استارت اعمال می‌شود.',
    set_ssh: 'فاصلهٔ بررسی SSH (دقیقه)', set_ssh_h: 'پیش‌فرض 5 — کمینه 1',
    set_stale: 'آستانهٔ قطع‌شدن (دقیقه)', set_stale_h: 'پیش‌فرض 360 — بدون دسته در این مدت = هشدار آفلاین',
    set_grace: 'مهلت واریز دیرهنگام (دقیقه)', set_grace_h: 'پیش‌فرض 30 — پس از پایان رزرو مبلغ',
    set_poll: 'خود جمع‌کننده حدوداً هر {n} ثانیه حساب بلو را می‌خواند (روی سرور ایران؛ فقط نمایش).',
    set_src_env: 'از .env', set_src_panel: 'از پنل', set_save: 'ذخیره', set_super: 'فقط سوپرادمین می‌تواند تغییر دهد.',
    set_saved: 'تنظیمات بلو ذخیره شد',
  },
  en: {
    health_on: 'Collector connected', health_off: 'Collector offline', health_never: 'No batch from the collector yet',
    health_disabled: 'Blu webhook is not configured (BLU_PUSH_SECRET)', last_batch: 'Last batch',
    offline_hint: 'Silent for more than {m} min — Blu auto-confirm is paused; the iPhone SMS still works.',
    f_all: 'All', f_unmatched: 'Unmatched', f_matched: 'Approved', f_duplicate: 'Duplicate', f_ignored: 'Ignored',
    st_unmatched: 'Unmatched', st_matched: 'Approved', st_duplicate: 'Duplicate', st_ignored: 'Ignored',
    payer: 'Payer', card: 'Card', receipt: 'Tracking no.', reference: 'Reference no.', order: 'Order',
    open_tx: 'Open transaction', none: 'No deposits yet', none_f: 'Nothing in this filter',
    attach: 'Attach to order', order_ph: 'Order number', load_fail: 'Failed to load Blu deposits',
    a_title: 'Attach deposit to order', a_btn: 'Yes, approve and deliver',
    a_msg: 'The {amount} deposit will be attached to order #{id}; the payment is approved and the service delivered.',
    a_audit: 'This action is recorded under your username in the audit log.',
    svc: 'Service on the Iran server', svc_active: 'active', svc_inactive: 'inactive', svc_unknown: 'unknown',
    svc_check: 'Last check', svc_never: 'not checked yet', svc_err: 'Last error',
    svc_ssh: 'SSH failed {n} times in a row', svc_errs: '{n} errors in the last 10 min',
    rounded: 'Auto-approved — rounded amount', shortfall: 'short',
    set_h: 'Collector monitoring settings', set_sub: 'Stored in the database, override .env, apply without a restart.',
    set_ssh: 'SSH check interval (min)', set_ssh_h: 'default 5 — minimum 1',
    set_stale: 'Offline threshold (min)', set_stale_h: 'default 360 — no batch for this long = offline alert',
    set_grace: 'Late deposit grace (min)', set_grace_h: 'default 30 — after the amount reservation ends',
    set_poll: 'The collector itself reads the Blu account about every {n} s (on the Iran server; information only).',
    set_src_env: 'from .env', set_src_panel: 'from the panel', set_save: 'Save', set_super: 'Only a Super Admin can change these.',
    set_saved: 'Blu settings saved',
  },
}

const FILTERS = ['all', 'unmatched', 'matched', 'duplicate', 'ignored']
const TONE = { unmatched: 'warning', matched: 'success', duplicate: 'muted', ignored: 'muted' }

export default function BluDeposits() {
  const { lang } = useI18n()
  const { can, staff } = useAuth()
  const s = T[lang] || T.fa
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [filter, setFilter] = useState('all')
  const timer = useRef(null)

  const load = () =>
    api.get('/admin/payments/blu-transactions/', { params: filter === 'all' ? {} : { status: filter } })
      .then((r) => { setData(r.data); setErr('') })
      .catch(() => { setData((cur) => cur || { results: [], counts: {}, collector: null }); setErr(s.load_fail) })

  useEffect(() => { load() }, [filter])
  // new deposits / approvals arrive over the payments socket; also refresh the health line every minute
  usePaymentsEvents(() => { clearTimeout(timer.current); timer.current = setTimeout(load, 300) })
  useEffect(() => {
    const id = setInterval(load, 60000)
    return () => { clearInterval(id); clearTimeout(timer.current) }
  }, [filter])

  if (data === null) return <div className="grid place-items-center py-16"><Spinner /></div>
  const counts = data.counts || {}
  const total = Object.values(counts).reduce((a, b) => a + b, 0)

  return (
    <div className="space-y-3">
      <style>{CSS}</style>
      <Health c={data.collector} s={s} lang={lang} />
      {data.collector?.settings && (
        <BluSettings v={data.collector.settings} s={s} lang={lang} canEdit={!!staff?.is_superadmin} onSaved={load} />
      )}
      <Alert>{err}</Alert>
      <div className="pq-tabs">
        {FILTERS.map((f) => (
          <button key={f} type="button" onClick={() => setFilter(f)} className={'pq-tab' + (filter === f ? ' on' : '')}>
            {s['f_' + f]}
            <span className="pq-tab-n">{f === 'all' ? total : counts[f] || 0}</span>
          </button>
        ))}
      </div>
      {data.results.length === 0 && !err && (
        <div className="card text-center text-muted">{total ? s.none_f : s.none}</div>
      )}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {data.results.map((tx) => (
          <Deposit key={tx.id} tx={tx} s={s} lang={lang} canAttach={can('payment.approve')} onDone={load} />
        ))}
      </div>
    </div>
  )
}

function Health({ c, s, lang }) {
  if (!c) return null
  const state = !c.enabled ? 'disabled' : c.connected ? 'on' : c.last_batch_at ? 'off' : 'never'
  const label = { disabled: s.health_disabled, on: s.health_on, off: s.health_off, never: s.health_never }[state]
  return (
    <div className="blu-health card" data-state={state} role="status">
      <span className="blu-dot" />
      <div className="min-w-0 flex-1">
        <b>{label}</b>
        {c.last_batch_at && (
          <div className="text-xs text-muted">{s.last_batch}: {jalali(c.last_batch_at, true, lang)}</div>
        )}
        {state === 'off' && <div className="blu-hint">{s.offline_hint.replace('{m}', c.stale_minutes)}</div>}
        <Service v={c.service} s={s} lang={lang} />
      </div>
    </div>
  )
}

/* Super Admin: SSH check interval, offline threshold, late grace (Setting rows; win over .env) */
const SET_FIELDS = [['ssh_check_minutes', 'blu_ssh_check_minutes', 'set_ssh', 1, 1440],
  ['stale_minutes', 'blu_stale_minutes', 'set_stale', 1, 10080], ['late_grace_minutes', 'blu_late_grace_minutes', 'set_grace', 0, 1440]]

function BluSettings({ v, s, lang, canEdit, onSaved }) {
  const toast = useToast()
  const init = Object.fromEntries(SET_FIELDS.map(([k]) => [k, String(v[k] ?? '')]))
  const [form, setForm] = useState(init)
  const [busy, setBusy] = useState(false)
  const key = SET_FIELDS.map(([k]) => v[k]).join('|')
  useEffect(() => { setForm(init) }, [key])
  const dirty = SET_FIELDS.some(([k]) => String(v[k]) !== form[k])
  const save = async (e) => {
    e.preventDefault(); setBusy(true)
    try {
      await api.put('/admin/settings/', Object.fromEntries(SET_FIELDS.map(([k, sk]) => [sk, Number(form[k])])))
      toast.success(s.set_saved); onSaved()
    } catch (e2) { toast.error(apiError(e2)) } finally { setBusy(false) }
  }
  return (
    <form className="card blu-set" onSubmit={save} data-testid="blu-settings">
      <div className="blu-set-head">
        <div className="min-w-0">
          <b className="text-sm">{s.set_h}</b>
          <p className="text-xs text-muted mt-0.5">{canEdit ? s.set_sub : s.set_super}</p>
        </div>
        {canEdit && <button className="btn-primary text-sm blu-set-save" disabled={busy || !dirty}>{busy ? '…' : s.set_save}</button>}
      </div>
      <div className="blu-set-grid">
        {SET_FIELDS.map(([k, , label, lo, hi]) => (
          <label key={k} className="blu-set-f">
            <span className="text-xs font-semibold">{s[label]}
              {v.source?.[k] && <span className="blu-src">{v.source[k] === 'panel' ? s.set_src_panel : s.set_src_env}</span>}
            </span>
            <input className="input mono-num" dir="ltr" type="number" min={lo} max={hi} disabled={!canEdit}
              value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
            <span className="text-xs text-muted">{s[label + '_h']}</span>
          </label>
        ))}
      </div>
      <p className="blu-poll">{s.set_poll.replace('{n}', v.collector_poll_seconds)}</p>
    </form>
  )
}

/* systemctl is-active + recent journal errors, read over SSH every few minutes (backend blu_service.py) */
function Service({ v, s, lang }) {
  if (!v?.configured) return null
  const st = !v.checked_at ? 'never' : v.ssh_failures > 0 && !v.state ? 'unknown' : v.state === 'active' ? 'active' : 'inactive'
  const word = { active: s.svc_active, inactive: `${s.svc_inactive}${v.state && v.state !== 'inactive' ? ` (${v.state})` : ''}`, unknown: s.svc_unknown, never: s.svc_never }[st]
  return (
    <div className="blu-svc" data-state={st} data-alert={v.alert || undefined} data-testid="blu-service">
      <div><span className="blu-svc-dot" />{s.svc}: <b>{word}</b>
        {v.checked_at && <span className="text-muted"> · {s.svc_check}: {jalali(v.checked_at, true, lang)}</span>}</div>
      {v.ssh_failures > 0 && <div className="blu-svc-warn">{s.svc_ssh.replace('{n}', v.ssh_failures)}{v.ssh_error ? ` — ${v.ssh_error}` : ''}</div>}
      {v.error_count > 0 && <div className="blu-svc-warn">{s.svc_errs.replace('{n}', v.error_count)}</div>}
      {v.error_line && <div className="blu-note">{s.svc_err}: <bdi dir="ltr">{v.error_line}</bdi></div>}
    </div>
  )
}

function Deposit({ tx, s, lang, canAttach, onDone }) {
  const confirm = useConfirm()
  const navigate = useNavigate()
  const [orderId, setOrderId] = useState(tx.matched_order ? String(tx.matched_order) : '')
  const tone = TONE[tx.status] || 'muted'

  const attach = async () => {
    const id = orderId.replace(/\D/g, '')
    if (!id) return
    const ok = await confirm({
      tone: 'success', icon: 'check', badge: 'payment.approve',
      title: s.a_title, targetLabel: s.order, targetId: `#${id}`,
      message: s.a_msg.replace('{amount}', toman(tx.amount_toman, lang)).replace('{id}', id),
      confirmLabel: s.a_btn, footnote: s.a_audit,
      action: () => api.post(`/admin/payments/blu-transactions/${tx.id}/attach/`, { order_id: Number(id) }),
    })
    if (ok) onDone()
  }

  return (
    <div className={'card space-y-2 blu-card' + (tx.status === 'unmatched' ? ' blu-card--open' : '')} data-status={tx.status}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-bold">
          {tx.amount_toman != null ? toman(tx.amount_toman, lang)
            : <bdi dir="ltr" className="mono-num">{Number(tx.amount_irr).toLocaleString('en-US')} {lang === 'en' ? 'IRR' : 'ریال'}</bdi>}
        </span>
        <span className={`blu-pill blu-pill--${tone}`}>{s['st_' + tx.status] || tx.status}</span>
      </div>
      {tx.rounded && (
        <div className="blu-rounded" data-testid="blu-rounded">{s.rounded}
          {tx.shortfall != null && <span> · {s.shortfall} {toman(tx.shortfall, lang)}</span>}</div>
      )}
      <div className="blu-grid text-sm">
        <span className="text-muted">{jalali(tx.occurred_at, true, lang)}</span>
        {tx.payer_name && <span>{s.payer}: {tx.payer_name}</span>}
        {tx.payer_card && <span>{s.card}: <bdi dir="ltr" className="mono-num">{tx.payer_card}</bdi></span>}
        {tx.receipt && <span>{s.receipt}: <bdi dir="ltr" className="mono-num">{tx.receipt}</bdi></span>}
        {tx.reference && <span>{s.reference}: <bdi dir="ltr" className="mono-num">{tx.reference}</bdi></span>}
        {tx.matched_order && <span>{s.order} #{tx.matched_order}</span>}
      </div>
      {tx.match_note && <div className="blu-note" dir="ltr">{tx.match_note}</div>}
      {tx.status === 'unmatched' && canAttach && (
        <div className="blu-attach">
          <input className="input" dir="ltr" inputMode="numeric" aria-label={s.order_ph} placeholder={s.order_ph}
            value={orderId} onChange={(e) => setOrderId(e.target.value)} />
          <button type="button" className="btn-primary text-sm" disabled={!orderId.replace(/\D/g, '')} onClick={attach}>
            {s.attach}
          </button>
        </div>
      )}
      {tx.matched_payment && (
        <button type="button" className="btn-ghost text-sm blu-open" onClick={() => navigate(`/payments/${tx.matched_payment}`)}>
          {s.open_tx} ›
        </button>
      )}
    </div>
  )
}

const CSS = `
.blu-health { display: flex; align-items: flex-start; gap: 10px; padding: 12px 14px; }
.blu-dot { width: 10px; height: 10px; border-radius: 50%; margin-top: 6px; flex-shrink: 0; background: var(--c-text-muted); }
.blu-health[data-state="on"] .blu-dot { background: var(--c-success); animation: pq-blink 1.6s ease-in-out infinite; }
.blu-health[data-state="off"] { border-color: color-mix(in srgb, var(--c-danger) 40%, var(--c-border)); }
.blu-health[data-state="off"] .blu-dot { background: var(--c-danger); }
.blu-health[data-state="off"] b { color: var(--c-danger-fg); }
.blu-health[data-state="disabled"] .blu-dot, .blu-health[data-state="never"] .blu-dot { background: var(--c-warning); }
.blu-hint { font-size: 12px; margin-top: 2px; color: var(--c-danger-fg); }
.blu-svc { display: flex; flex-direction: column; gap: 4px; margin-top: 8px; padding-top: 8px; font-size: 12.5px;
  border-top: 1px solid var(--c-border); overflow-wrap: anywhere; }
.blu-svc-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-inline-end: 6px; background: var(--c-text-muted); }
.blu-svc[data-state="active"] .blu-svc-dot { background: var(--c-success); }
.blu-svc[data-state="inactive"] .blu-svc-dot { background: var(--c-danger); }
.blu-svc[data-state="inactive"] b { color: var(--c-danger-fg); }
.blu-svc[data-state="active"] b { color: var(--c-success-fg); }
.blu-svc-warn { color: var(--c-warning-fg); }
.blu-card--open { border-color: color-mix(in srgb, var(--c-warning) 55%, var(--c-border));
  background: linear-gradient(color-mix(in srgb, var(--c-warning) 7%, transparent), color-mix(in srgb, var(--c-warning) 7%, transparent)), var(--c-surface); }
.blu-pill { font-size: 11px; font-weight: 700; padding: 2px 9px; border-radius: 999px; white-space: nowrap; }
.blu-pill--warning { color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 16%, transparent); }
.blu-pill--success { color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 16%, transparent); }
.blu-pill--muted { color: var(--c-muted-fg); background: color-mix(in srgb, var(--c-text-muted) 16%, transparent); }
.blu-grid { display: flex; flex-direction: column; gap: 2px; overflow-wrap: anywhere; }
.blu-note { font-size: 11.5px; color: var(--c-muted-fg); background: color-mix(in srgb, var(--c-text-muted) 8%, transparent);
  border-radius: 8px; padding: 6px 10px; text-align: start; overflow-wrap: anywhere; }
.blu-attach { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 6px; align-items: center; }
.blu-attach .input { font-size: 13px; padding-block: 6px; min-width: 0; }
.blu-open { color: var(--c-primary); }
.blu-set { padding: 12px 14px; display: flex; flex-direction: column; gap: 10px; }
.blu-set-head { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 8px; }
.blu-set-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 180px), 1fr)); gap: 10px; }
.blu-set-f { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.blu-set-f .input { font-size: 13px; padding-block: 6px; }
.blu-src { margin-inline-start: 6px; font-weight: 600; font-size: 10.5px; padding: 1px 7px; border-radius: 999px;
  color: var(--c-muted-fg); background: color-mix(in srgb, var(--c-text-muted) 14%, transparent); }
.blu-poll { font-size: 12px; color: var(--c-muted-fg); border-top: 1px solid var(--c-border); padding-top: 8px; }
.blu-rounded { font-size: 12px; font-weight: 700; color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 10%, transparent);
  border-radius: 8px; padding: 4px 10px; }
@media (max-width: 767px) {
  .blu-attach .input { font-size: 16px; min-height: 44px; }
  .blu-attach button, .blu-open, .blu-set-save { min-height: 44px; }
  .blu-set-f .input { font-size: 16px; min-height: 44px; }
  .blu-set-save { width: 100%; }
  .blu-open { width: 100%; }
}
`
