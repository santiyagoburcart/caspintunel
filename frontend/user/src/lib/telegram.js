// Telegram Mini App helpers. Everything degrades to a no-op outside Telegram.

// Telegram also hands initData to the page in the URL fragment
// (#tgWebAppData=…&tgWebAppVersion=…). Captured once at load, before the router
// rewrites the URL, so login works even if the SDK could not initialise.
const LAUNCH = (() => {
  try {
    const h = new URLSearchParams((window.location.hash || '').replace(/^#/, ''))
    return { data: h.get('tgWebAppData') || '', version: h.get('tgWebAppVersion') || '' }
  } catch {
    return { data: '', version: '' }
  }
})()

export function tgWebApp() {
  if (typeof window === 'undefined') return null
  return (window.Telegram && window.Telegram.WebApp) || null
}

// True only when Telegram actually handed us a signed initData string.
export function isTelegramMiniApp() {
  return tgInitData().length > 0
}

export function tgInitData() {
  const wa = tgWebApp()
  return (wa && typeof wa.initData === 'string' && wa.initData) || LAUNCH.data || ''
}

/** Opened inside Telegram's webview at all (even when initData is missing). */
export function isTelegramWebView() {
  const wa = tgWebApp()
  return isTelegramMiniApp() || !!LAUNCH.version || !!(wa && wa.platform && wa.platform !== 'unknown')
}

/** Ask Telegram to share the user's phone with the bot (Bot API 6.9+). */
export function tgRequestContact(cb) {
  const wa = tgWebApp()
  if (!wa || typeof wa.requestContact !== 'function') return false
  try { wa.requestContact((ok) => cb && cb(!!ok)); return true } catch { return false }
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
