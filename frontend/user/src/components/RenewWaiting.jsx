import { jalali } from '../lib/format'

/* A renewal that is paid (queued) or whose receipt is being reviewed — shown instead of
 * the renew button (service card, checkout): which plan, and when it applies. Only one
 * renewal at a time; the paid one applies when the current volume / time ends. */
export function RenewWaiting({ pr, t, lang }) {
  const review = pr.state === 'review'
  const plan = (lang === 'en' ? pr.plan_name_en : pr.plan_name) || pr.plan_name || '—'
  return (
    <div className="rnw-box" data-state={pr.state} role="status" data-testid="renew-waiting">
      <style>{CSS}</style>
      <b>{review ? t('renew_review_title') : t('renew_waiting_title')}</b>
      <span>{t('renew_queued_plan')}: {plan}</span>
      <small>{review ? t('renew_review_note')
        : pr.applies_by ? t('renew_applies', { date: jalali(pr.applies_by, false, lang) }) : t('renew_applies_novol')}</small>
    </div>
  )
}

const CSS = `
.rnw-box { display: flex; flex-direction: column; gap: 2px; padding: 10px 12px; border-radius: 12px; font-size: 12.5px; line-height: 1.7;
  color: var(--c-text); background: color-mix(in srgb, var(--c-success) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--c-success) 30%, transparent); overflow-wrap: anywhere; }
.rnw-box b { color: var(--c-success-fg); font-size: 13px; }
.rnw-box small { color: var(--c-muted-fg); font-size: 11.5px; }
.rnw-box[data-state="review"] { background: color-mix(in srgb, var(--c-warning) 10%, transparent);
  border-color: color-mix(in srgb, var(--c-warning) 32%, transparent); }
.rnw-box[data-state="review"] b { color: var(--c-warning-fg); }
`
