import { digits, gb, jalali } from '../lib/format'

// v1.51.1: a paid renewal still waiting on a service (backend AdminServiceSerializer.pending_renewal) — the panel shows
// what it will set and when, instead of only the new plan's name next to the current volume.
const T = {
  fa: {
    title: 'تمدید پرداخت‌شده در صف', gb: 'گیگ', days: 'روز', unlimited: 'نامحدود',
    soon: 'اعمال: ظرف چند دقیقه (دورهٔ فعلی تمام شده)', by: 'اعمال: با تمام شدن حجم فعلی یا در {d}، هرکدام زودتر',
    vol: 'اعمال: با تمام شدن حجم فعلی', paid: 'پرداخت: {d} · سفارش #{o}', carry: 'باقی‌ماندهٔ دورهٔ فعلی منتقل می‌شود',
    note: 'حجم و انقضای نمایش‌داده‌شده مال دورهٔ فعلی است؛ پلن تمدید از لحظهٔ اعمال حساب می‌شود.',
  },
  en: {
    title: 'Paid renewal queued', gb: 'GB', days: 'days', unlimited: 'unlimited',
    soon: 'Applies: within a few minutes (the current cycle ended)', by: 'Applies: when the current volume runs out or on {d}, whichever comes first',
    vol: 'Applies: when the current volume runs out', paid: 'Paid: {d} · order #{o}', carry: 'what is left of the current cycle carries over',
    note: 'The volume and expiry shown are the current cycle; the renewal plan counts from the moment it applies.',
  },
}

export default function PendingRenewal({ p, lang, compact = false }) {
  if (!p) return null
  const s = T[lang] || T.fa
  const name = (lang === 'fa' ? p.plan : p.plan_en) || p.plan
  const vol = p.data_limit ? `${digits(gb(p.data_limit), lang)} ${s.gb}` : s.unlimited
  const days = p.duration_days ? ` · ${digits(p.duration_days, lang)} ${s.days}` : ''
  const when = p.applies_soon ? s.soon : p.applies_by ? s.by.replace('{d}', jalali(p.applies_by, true, lang)) : s.vol
  if (compact) {
    return (
      <span className="prn-chip" title={`${s.title}: ${name} · ${vol}${days}\n${when}`} data-testid="pending-renewal">
        ⏳ {name} · {vol}{days}
      </span>
    )
  }
  return (
    <div className="prn-box" role="status" data-testid="pending-renewal">
      <style>{CSS}</style>
      <b>⏳ {s.title}</b>
      <span className="prn-plan">{name} · {vol}{days}{p.mode === 'carry_over' ? ` · ${s.carry}` : ''}</span>
      <span>{when}</span>
      <span className="prn-dim">{s.paid.replace('{d}', jalali(p.paid_at, true, lang)).replace('{o}', digits(p.order_id, lang))}</span>
      <span className="prn-dim">{s.note}</span>
    </div>
  )
}

export const PENDING_RENEWAL_CSS = `
.prn-chip { display: inline-block; margin-top: 3px; font-size: 11px; font-weight: 700; padding: 1px 8px; border-radius: 999px;
  color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 12%, transparent); max-width: 100%;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
`
const CSS = `
.prn-box { display: flex; flex-direction: column; gap: 4px; padding: 12px 14px; border-radius: 14px; font-size: 13px; line-height: 1.7;
  border: 1px solid color-mix(in srgb, var(--c-primary) 35%, transparent); background: color-mix(in srgb, var(--c-primary) 8%, var(--c-bg)); }
.prn-box b { font-size: 13.5px; }
.prn-plan { font-weight: 800; }
.prn-dim { font-size: 12px; color: var(--c-text-muted); }
`
