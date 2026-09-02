// Telegram Mini App helpers. Everything degrades to a no-op outside Telegram.

export function tgWebApp() {
  if (typeof window === 'undefined') return null
  return (window.Telegram && window.Telegram.WebApp) || null
}

// True only when Telegram actually handed us a signed initData string.
export function isTelegramMiniApp() {
  const wa = tgWebApp()
  return !!(wa && typeof wa.initData === 'string' && wa.initData.length > 0)
}

export function tgInitData() {
  const wa = tgWebApp()
  return (wa && wa.initData) || ''
}

// A deep-link target passed as ?startapp=<route> on the t.me link.
export function tgStartParam() {
  const wa = tgWebApp()
  const p = wa && wa.initDataUnsafe && wa.initDataUnsafe.start_param
  return typeof p === 'string' ? p : ''
}

// Tell Telegram we're ready, use the full height, and match the site's dark ground.
export function initTelegramUi() {
  const wa = tgWebApp()
  if (!wa) return
  try {
    wa.ready()
    wa.expand()
    const bg = getComputedStyle(document.documentElement).getPropertyValue('--c-bg').trim() || '#0b0e14'
    wa.setHeaderColor && wa.setHeaderColor(bg)
    wa.setBackgroundColor && wa.setBackgroundColor(bg)
    wa.enableClosingConfirmation && wa.enableClosingConfirmation()
  } catch {
    /* older Telegram clients may not have every method */
  }
}
