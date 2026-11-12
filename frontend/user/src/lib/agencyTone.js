// v1.57 agency colour system — IDENTICAL in both SPAs (admin: our staff + group managers · user: the /agency/ portal).
// One meaning per colour everywhere in the agency pages (styles: agency-tones.css):
//   success = active / paid / approved / credit / low usage · warning = limited / waiting / 70–90 % usage
//   danger  = disabled / blocked / unpaid / rejected / debt / > 90 % usage · muted = archived / voided / expired / zero
//   info    = neutral facts (sales, invoiced) · adjust = «اصلاحیه» (a corrected mistake, information only)
// Text always uses the theme's contrast-safe --c-*-fg tokens (light + dark).

export function usageTone(pct) {
  const p = Number(pct) || 0
  return p > 90 ? 'danger' : p >= 70 ? 'warning' : 'success'
}

export function moneyTone(v) {
  const n = Number(v) || 0
  return n > 0 ? 'danger' : n < 0 ? 'success' : 'muted'          // + owes (debt) · − credit · 0 neutral
}

const STATUS = {
  // agency admins (backend PanelAdmin.status_code) + archive
  active: 'success', pamp_limited: 'warning', limited: 'warning', panel_disabled: 'danger', disabled: 'danger',
  blocked: 'danger', archived: 'muted', on_hold: 'info', expired: 'muted',
  // invoices
  unpaid: 'danger', pending: 'warning', paid: 'success', partial: 'warning', voided: 'muted',
  // payments
  pending_payment: 'warning', pending_review: 'warning', approved: 'success', rejected: 'danger', cancelled: 'muted', superseded: 'muted',
  // requests / sync / stores
  ok: 'success', error: 'danger', failed: 'danger', draft: 'muted', suspended: 'warning', closed: 'danger',
}

export function statusTone(code) {
  return STATUS[code] || 'info'
}

export function kindTone(kind, signed) {
  if (kind === 'payment') return 'success'
  if (kind === 'adjustment') return 'adjust'
  if (kind === 'pending') return 'warning'
  return Number(signed) < 0 ? 'success' : 'info'
}
