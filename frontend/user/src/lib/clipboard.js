/**
 * The one copy-to-clipboard helper every copy button uses.
 *
 * 1. `navigator.clipboard.writeText` (secure contexts, modern browsers).
 * 2. If that is missing or rejects — older Android Chrome / Samsung Internet,
 *    in-app WebViews, Telegram — a hidden <textarea> + select() +
 *    `document.execCommand('copy')`, with setSelectionRange for mobile.
 * 3. If both fail, a small sheet opens with the text pre-selected so the user
 *    can long-press → Copy themselves.
 *
 * Resolves `true` only when a method actually reported success, so callers
 * show "copied" only then. Call it straight from the click handler (before
 * any other await) so the browser still treats it as a user gesture.
 */
export async function copyToClipboard(text) {
  const value = String(text ?? '')
  if (!value) return false

  if (navigator.clipboard?.writeText && window.isSecureContext !== false) {
    try {
      await navigator.clipboard.writeText(value)
      return true
    } catch { /* fall through to the legacy path */ }
  }
  if (legacyCopy(value)) return true

  showManualCopy(value)
  return false
}

function legacyCopy(value) {
  const active = document.activeElement
  const ta = document.createElement('textarea')
  ta.value = value
  ta.setAttribute('readonly', '')           // no on-screen keyboard on mobile
  ta.setAttribute('aria-hidden', 'true')
  // 16px stops iOS zooming in; kept in-viewport (but invisible) because some
  // Android builds refuse to select text in an off-screen element
  ta.style.cssText = 'position:fixed;top:0;left:0;width:1px;height:1px;padding:0;border:0;'
    + 'opacity:0;font-size:16px;pointer-events:none;z-index:-1;'
  document.body.appendChild(ta)
  let ok = false
  try {
    ta.focus({ preventScroll: true })
    ta.select()
    ta.setSelectionRange(0, value.length)
    ok = document.execCommand('copy')
  } catch { ok = false }
  ta.remove()
  try { active?.focus?.({ preventScroll: true }) } catch { /* ignore */ }
  return !!ok
}

function isFa() {
  const html = document.documentElement
  return (html.getAttribute('lang') || '').startsWith('fa') || html.getAttribute('dir') === 'rtl'
}

/** Last resort: the text in a selectable field, pre-selected, plus a close button. */
function showManualCopy(value) {
  document.getElementById('cp-manual')?.remove()
  const fa = isFa()
  const wrap = document.createElement('div')
  wrap.id = 'cp-manual'
  wrap.setAttribute('role', 'dialog')
  wrap.setAttribute('aria-modal', 'true')
  wrap.dir = fa ? 'rtl' : 'ltr'
  wrap.innerHTML = `
    <style>
      #cp-manual { position: fixed; inset: 0; z-index: 10000; display: flex; align-items: flex-end;
        justify-content: center; background: rgba(0,0,0,.45); padding: 16px; }
      @media (min-width: 768px) { #cp-manual { align-items: center; } }
      #cp-manual .cpm-box { width: 100%; max-width: 420px; border-radius: 18px; padding: 16px;
        background: var(--c-bg, #fff); color: var(--c-text, #111); border: 1px solid var(--c-border, #ddd);
        box-shadow: 0 12px 40px rgba(0,0,0,.35); font-family: inherit; }
      #cp-manual .cpm-t { font-weight: 700; font-size: 15px; margin-bottom: 4px; }
      #cp-manual .cpm-d { font-size: 12.5px; opacity: .75; margin-bottom: 10px; line-height: 1.7; }
      #cp-manual textarea { width: 100%; min-height: 64px; resize: none; border-radius: 10px; padding: 10px;
        font: 600 15px/1.5 ui-monospace, monospace; direction: ltr; text-align: left;
        background: color-mix(in srgb, var(--c-text, #111) 6%, transparent); color: inherit;
        border: 1px solid var(--c-border, #ccc); user-select: all; -webkit-user-select: all; }
      #cp-manual button { margin-top: 12px; width: 100%; border: 0; border-radius: 12px; padding: 11px;
        font: inherit; font-weight: 700; color: #fff; background: var(--c-primary, #6d48f0); cursor: pointer; }
    </style>
    <div class="cpm-box">
      <div class="cpm-t">${fa ? 'کپی خودکار ممکن نشد' : 'Couldn’t copy automatically'}</div>
      <div class="cpm-d">${fa
        ? 'متن زیر انتخاب شده است؛ انگشت خود را روی آن نگه دارید و «کپی» را بزنید.'
        : 'The text below is selected — long-press it and choose “Copy”.'}</div>
      <textarea readonly></textarea>
      <button type="button">${fa ? 'بستن' : 'Close'}</button>
    </div>`
  const ta = wrap.querySelector('textarea')
  ta.value = value
  const close = () => { wrap.remove(); document.removeEventListener('keydown', onKey) }
  const onKey = (e) => { if (e.key === 'Escape') close() }
  wrap.addEventListener('mousedown', (e) => { if (e.target === wrap) close() })
  wrap.querySelector('button').addEventListener('click', close)
  document.addEventListener('keydown', onKey)
  document.body.appendChild(wrap)
  const select = () => { try { ta.focus(); ta.select(); ta.setSelectionRange(0, value.length) } catch { /* ignore */ } }
  select()
  ta.addEventListener('focus', select)
}
