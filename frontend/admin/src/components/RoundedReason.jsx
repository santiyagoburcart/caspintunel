import { useI18n } from '../lib/i18n'
import { digits, toman } from '../lib/format'

// Which conditions of the rounded-amount rule matched (backend payments_sms/rounded.py,
// Payment.auto_reason). Shown on the transaction page and in the review queue.
const T = {
  fa: {
    approved: 'تأیید خودکار – مبلغ گرد شده', not_applied: 'تأیید خودکار مبلغ گرد شده اعمال نشد',
    shortfall: 'کسری {s} (سقف {t})', window: 'در بازهٔ زمانی سفارش',
    one: 'فقط یک سفارش جور بود', many: '{n} سفارش جور بودند — به صف رفت',
    receipt: 'رسید همین سفارش آپلود شده', no_receipt: 'رسیدی آپلود نشده',
    card: 'کارت آشنا ****{c} (قبلاً از آن پرداخت کرده)', new_card: 'کارت واریزکننده جدید است',
    no_card: 'کارت واریزکننده معلوم نیست (پیامک)', used: 'این واریز قبلاً سفارش #{o} را تأیید کرده',
    src_blu: 'بلو', src_sms: 'پیامک',
  },
  en: {
    approved: 'Auto-approved — rounded amount', not_applied: 'Rounded-amount auto-approve not applied',
    shortfall: 'short {s} (limit {t})', window: 'inside the order’s time window',
    one: 'exactly one order fits', many: '{n} orders fit — sent to the queue',
    receipt: 'receipt uploaded for this order', no_receipt: 'no receipt uploaded',
    card: 'known card ****{c} (paid from it before)', new_card: 'the payer card is new',
    no_card: 'payer card unknown (SMS)', used: 'this deposit already approved order #{o}',
    src_blu: 'Blu', src_sms: 'SMS',
  },
}

export default function RoundedReason({ r, compact = false }) {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  if (!r || r.rule !== 'rounded') return null
  const items = []
  const ok = (good, text) => items.push([good, text])
  if (r.shortfall != null) ok(true, s.shortfall.replace('{s}', toman(r.shortfall, lang)).replace('{t}', toman(r.tolerance, lang)))
  ok(true, s.window)
  ok(r.candidates === 1, r.candidates === 1 ? s.one : s.many.replace('{n}', digits(r.candidates, lang)))
  if (r.why_not === 'deposit_already_used') ok(false, s.used.replace('{o}', r.used_order))
  if (r.candidates === 1 && r.why_not !== 'deposit_already_used') {
    ok(!!r.receipt, r.receipt ? s.receipt : s.no_receipt)
    if (r.card_last4) ok(!!r.card_known, r.card_known ? s.card.replace('{c}', r.card_last4) : s.new_card)
    else ok(false, s.no_card)
  }
  return (
    <div className={'rr' + (r.applied ? ' rr--ok' : '') + (compact ? ' rr--compact' : '')} data-testid="rounded-reason">
      <style>{CSS}</style>
      <b className="rr-h">{r.applied ? s.approved : s.not_applied}
        <span className="rr-src">{r.source === 'blu' ? s.src_blu : s.src_sms}</span></b>
      <ul>
        {items.map(([good, text], i) => (
          <li key={i} className={good ? 'is-ok' : 'is-no'}><span aria-hidden="true">{good ? '✓' : '✗'}</span> {text}</li>
        ))}
      </ul>
    </div>
  )
}

const CSS = `
.rr { border: 1px solid var(--c-border); border-radius: 12px; padding: 10px 12px; font-size: 12.5px; overflow-wrap: anywhere;
  background: color-mix(in srgb, var(--c-text-muted) 6%, transparent); }
.rr--ok { border-color: color-mix(in srgb, var(--c-primary) 40%, var(--c-border)); background: color-mix(in srgb, var(--c-primary) 7%, transparent); }
.rr-h { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; font-size: 13px; }
.rr--ok .rr-h { color: var(--c-primary); }
.rr-src { font-size: 10.5px; padding: 1px 7px; border-radius: 999px; color: var(--c-muted-fg); background: color-mix(in srgb, var(--c-text-muted) 14%, transparent); }
.rr ul { margin-top: 6px; display: flex; flex-direction: column; gap: 3px; }
.rr li.is-ok span { color: var(--c-success-fg); font-weight: 800; }
.rr li.is-no span { color: var(--c-danger-fg); font-weight: 800; }
.rr--compact { padding: 8px 10px; font-size: 12px; }
`
