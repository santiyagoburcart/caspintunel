// Text-safe version of a role colour (the --c-*-fg tokens, ≥4.5:1 on the page
// and on cards in every theme). Accepts the CSS var form ('var(--c-success)')
// or one of the brand hex values some pages use for status tones.
const HEX = {
  '#11ab53': 'success', '#0e9447': 'success', '#16a34a': 'success', '#059669': 'success',
  '#1464ba': 'primary', '#2e56c8': 'primary', '#4c90d6': 'secondary', '#0891b2': 'secondary',
  '#d97706': 'warning', '#f59e0b': 'warning', '#b45309': 'warning',
  '#e11d48': 'danger', '#dc2626': 'danger', '#ef4444': 'danger', '#f43f5e': 'danger',
}
export function fg(color) {
  if (!color) return color
  const m = /^var\(--c-(primary|secondary|success|danger|warning)\)$/.exec(String(color).trim())
  if (m) return `var(--c-${m[1]}-fg)`
  const role = HEX[String(color).trim().toLowerCase()]
  return role ? `var(--c-${role}-fg)` : color
}
