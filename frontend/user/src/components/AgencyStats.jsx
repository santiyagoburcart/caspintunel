import { useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { jalali, relTime } from '../lib/format'

// v1.36 full reseller numbers for group managers (permission agency.gm.full_stats). Every value comes from
// the server (same PAMP formulas as the staff Agency page — apps/agency/api.py); this file only labels them.
export const ST = {
  fa: {
    sold: 'فروخته‌شده', used: 'مصرف', remaining: 'باقی‌مانده', sold_limit: 'سقف فروش باقی‌مانده', hidden: 'ترافیک پنهان',
    deleted: 'مصرف کاربران حذف‌شده', users: 'کاربران', total: 'کل', active: 'فعال', online: 'آنلاین', expired: 'منقضی',
    limited: 'حجم تمام', on_hold: 'در انتظار اتصال', disabled: 'غیرفعال', last: 'آخرین فعالیت', never: 'هنوز نه', unl: 'نامحدود',
    usage: 'درصد مصرف', online_h: 'آنلاین الان', limit: 'سقف', details: 'جزئیات', stats_h: 'آمار کامل', live_na: 'آمار زنده در دسترس نیست', info: 'توضیح',
    t_sold: 'جمع سقف حجم همهٔ کاربران دارای محدودیتِ این ادمین (کاربران نامحدود حساب نمی‌شوند).',
    t_used: 'مصرف واقعی همهٔ کاربران این ادمین، طبق پاسارگارد.',
    t_remaining: 'حجمی که این ادمین هنوز از سقف خودش دارد، طبق پاسارگارد.',
    t_sold_limit: 'باقی‌مانده − فروخته‌شده + مصرف. یعنی چقدر دیگر می‌تواند به کاربران تازه حجم بفروشد؛ منفی یعنی بیشتر از سقف فروخته است.',
    t_hidden: 'فروخته‌شده − مصرف − باقی‌مانده: ترافیکی که در هیچ‌کدام دیده نمی‌شود (مثلاً کاربران نامحدود یا حذف‌شده).',
    t_deleted: 'حجمی که کاربرانِ حذف‌شدهٔ این ادمین قبل از حذف مصرف کرده بودند (از آخرین صفرکردن).',
    t_users: 'تعداد کاربران بر اساس وضعیت، زنده از پاسارگارد (هر ۱ دقیقه تازه می‌شود).',
    t_online: 'کاربرانی که همین الان به سرور وصل‌اند.',
    t_last: 'آخرین باری که یکی از کاربران این ادمین آنلاین بوده است.',
    t_usage: 'مصرف ÷ سقف ادمین.',
    t_limit: 'حداکثر حجمی که این ادمین می‌تواند به کاربرانش بدهد (روی پاسارگارد).',
  },
  en: {
    sold: 'Sold', used: 'Used', remaining: 'Remaining', sold_limit: 'Sell limit left', hidden: 'Hidden traffic',
    deleted: 'Deleted users’ traffic', users: 'Users', total: 'total', active: 'active', online: 'online', expired: 'expired',
    limited: 'limited', on_hold: 'on hold', disabled: 'disabled', last: 'Last activity', never: 'not yet', unl: 'Unlimited',
    usage: 'Usage', online_h: 'Online now', limit: 'Limit', details: 'Details', stats_h: 'Full stats', live_na: 'Live numbers unavailable', info: 'About',
    t_sold: 'Sum of the data caps of this admin’s limited users (unlimited users are not counted).',
    t_used: 'Real traffic of all this admin’s users, from PasarGuard.',
    t_remaining: 'What this admin still has of its own limit, from PasarGuard.',
    t_sold_limit: 'Remaining − sold + used: how much more it can sell to new users; negative = sold beyond its limit.',
    t_hidden: 'Sold − used − remaining: traffic that shows up nowhere else (e.g. unlimited or deleted users).',
    t_deleted: 'Traffic the admin’s deleted users had used before they were deleted (since the last reset).',
    t_users: 'Users by status, live from PasarGuard (refreshed every minute).',
    t_online: 'Users connected right now.',
    t_last: 'The last time one of this admin’s users was online.',
    t_usage: 'Used ÷ the admin’s limit.',
    t_limit: 'The most this admin can give its users in total (set on PasarGuard).',
  },
}
export const useST = (lang) => ST[lang] || ST.fa
const N = ({ children }) => <bdi dir="ltr" className="ap-num">{children}</bdi>
const vol = (v, s) => (!v || v === 'Unlimited' ? s.unl : v)

/** «(i)»: tap / click to show the explanation (title tooltips do not work on phones). */
export function InfoTip({ text, label }) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState(null)
  const id = useId()
  const ref = useRef(null)
  const toggle = (e) => {
    e.stopPropagation()
    if (open) { setOpen(false); return }
    const r = e.currentTarget.getBoundingClientRect()
    const w = Math.min(260, window.innerWidth - 24)
    const left = Math.max(12, Math.min(r.left + r.width / 2 - w / 2, window.innerWidth - w - 12))
    setPos({ top: r.bottom + 6, left, width: w }); setOpen(true)
  }
  useEffect(() => {
    if (!open) return undefined
    const off = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    const esc = (e) => { if (e.key === 'Escape') setOpen(false) }
    const shut = () => setOpen(false)
    document.addEventListener('pointerdown', off); document.addEventListener('keydown', esc); window.addEventListener('scroll', shut, true)
    return () => { document.removeEventListener('pointerdown', off); document.removeEventListener('keydown', esc); window.removeEventListener('scroll', shut, true) }
  }, [open])
  return (
    <span className="st-tip" ref={ref}>
      <button type="button" className="st-tip-b" aria-label={label} aria-expanded={open} aria-describedby={open ? id : undefined}
        onClick={toggle}>i</button>
      {open && pos && createPortal(<span role="tooltip" id={id} className="st-tip-t" style={{ top: pos.top, left: pos.left, maxWidth: pos.width }}>{text}</span>, document.body)}
    </span>
  )
}

function Stat({ k, s, children, tone, wide, label }) {
  return (
    <div className="st-c" data-tone={tone || undefined} data-wide={wide || undefined}>
      <dt>{label || s[k]}<InfoTip text={s['t_' + k]} label={`${s.info}: ${label || s[k]}`} /></dt>
      <dd>{children}</dd>
    </div>
  )
}

export function LastSeen({ v, s, lang }) {
  if (!v) return <span className="st-muted">{s.never}</span>
  return <span title={jalali(v, true, lang)}><N>{relTime(v, lang)}</N></span>
}

/** Users by status: live counts when available, else the synced ones. */
export function UserCounts({ a, live, s }) {
  const ok = live && live.ok
  const c = ok ? live : { total: a.user_count, ...(a.user_counts || {}) }
  const keys = ['active', ...(ok ? ['online'] : []), 'expired', 'limited', 'on_hold', 'disabled']
  return (
    <span className="st-users">
      <b><N>{c.total ?? 0}</N></b><small> {s.total}</small>
      {keys.map((k) => (c[k] ? <span key={k} className="st-chip" data-k={k}><N>{c[k]}</N> {s[k]}</span> : null))}
    </span>
  )
}

/** The extra numbers on an admin card (compact) or in the detail dialog (all). */
export function StatGrid({ a, live, lang, full = false }) {
  const s = useST(lang)
  const neg = !a.is_unlimited && Number(a.sold_limit_value) < 0
  return (
    <dl className="st-grid" data-full={full || undefined}>
      {full && <Stat k="used" s={s}><N>{a.used_fmt}</N></Stat>}
      {full && <Stat k="remaining" s={s}><N>{vol(a.remaining_fmt, s)}</N></Stat>}
      <Stat k="sold" s={s}><N>{a.total_sold_fmt}</N></Stat>
      <Stat k="sold_limit" s={s} tone={neg ? 'danger' : undefined}><N>{a.is_unlimited ? s.unl : a.sold_limit_fmt}</N></Stat>
      <Stat k="hidden" s={s}><N>{a.hidden_fmt}</N></Stat>
      <Stat k="deleted" s={s}><N>{a.deleted_used_fmt}</N></Stat>
      {full && !a.is_unlimited && <Stat k="usage" s={s}><N>{a.usage_percent}%</N></Stat>}
      <Stat k="users" s={s} wide><UserCounts a={a} live={live} s={s} />{live && !live.ok && <small className="st-muted"> · {s.live_na}</small>}</Stat>
      <Stat k="last" s={s}>{live?.ok ? <LastSeen v={live.last_online} s={s} lang={lang} /> : <span className="st-muted">—</span>}</Stat>
      {live?.ok && <Stat k="online" s={s} tone="success" label={s.online_h}><N>{live.online}</N></Stat>}
    </dl>
  )
}

export const ST_CSS = `
/* v1.38.1: tiles wrap and GROW, so a short last row fills the width (no empty cell next to a lone tile) */
.st-grid { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.st-c { flex: 1 1 calc(50% - 8px); padding: 8px 10px; border-radius: 12px; border: 1px solid var(--c-border); min-width: 0; background: color-mix(in srgb, var(--c-text-muted) 4%, transparent); }
.st-grid[data-full] .st-c { flex-basis: 150px; }
.st-c[data-wide], .st-grid[data-full] .st-c[data-wide] { flex-basis: 100%; }
.st-c[data-tone="danger"] dd { color: var(--c-danger-fg); }
.st-c[data-tone="success"] dd { color: var(--c-success-fg); }
.st-c dt { display: flex; align-items: center; gap: 4px; font-size: 11.5px; font-weight: 700; color: var(--c-muted-fg); }
.st-c dd { font-size: 14px; font-weight: 800; margin-top: 2px; overflow-wrap: anywhere; }
.st-muted { color: var(--c-muted-fg); font-weight: 600; font-size: 12px; }
.st-users { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 6px; }
.st-users small { font-size: 11.5px; color: var(--c-muted-fg); font-weight: 600; }
.st-chip { font-size: 11.5px; font-weight: 700; padding: 1px 8px; border-radius: 999px; background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); white-space: nowrap; }
.st-chip[data-k="active"] { color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 13%, transparent); }
.st-chip[data-k="online"] { color: #fff; background: #11AB53; }
.st-chip[data-k="expired"], .st-chip[data-k="disabled"] { color: var(--c-muted-fg); }
.st-chip[data-k="limited"] { color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 14%, transparent); }
.st-tip { position: relative; display: inline-flex; }
.st-tip-b { position: relative; width: 18px; height: 18px; border-radius: 999px; border: 1px solid currentColor; background: transparent; color: var(--c-muted-fg);
  font: 700 11px/1 Georgia, serif; font-style: italic; display: inline-grid; place-items: center; padding: 0; cursor: pointer; }
.st-tip-b::after { content: ''; position: absolute; inset: -13px; }
.st-tip-b[aria-expanded="true"] { color: var(--c-primary); }
.st-tip-t { position: fixed; z-index: 90; width: max-content;
  padding: 8px 10px; border-radius: 10px; font-size: 12px; font-weight: 600; line-height: 1.7; color: var(--c-text); background: var(--c-bg);
  border: 1px solid var(--c-border); box-shadow: 0 10px 30px rgba(0,0,0,.18); white-space: normal; }
`
