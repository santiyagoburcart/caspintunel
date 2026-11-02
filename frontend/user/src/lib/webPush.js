// v1.33 Web Push (browser notifications while the page is closed). The worker `push-sw.js`
// only shows notifications: it is registered with a scope no page uses (`<base>push-sw/`),
// so it never controls, serves or caches pages (the v1.28 cleanup of old caching workers stays).
// (identical file in both SPAs; `base` = the app's root path ending in "/")
export const pushSupported = () => typeof window !== 'undefined' && 'serviceWorker' in navigator
  && 'PushManager' in window && 'Notification' in window

export const isIOS = () => typeof navigator !== 'undefined'
  && (/iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1))

export const isStandalone = () => typeof window !== 'undefined'
  && (window.matchMedia?.('(display-mode: standalone)').matches || window.navigator.standalone === true)

/** iPhone / iPad: push works only for a site added to the Home Screen (iOS 16.4+). */
export const needsHomeScreen = () => isIOS() && !isStandalone()

const scopeOf = (base) => `${base}push-sw/`

function keyBytes(b64) {
  const pad = '='.repeat((4 - (b64.length % 4)) % 4)
  const raw = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/'))
  return Uint8Array.from(raw, (c) => c.charCodeAt(0))
}

function activated(reg) {
  if (reg.active) return Promise.resolve(reg)
  const w = reg.installing || reg.waiting
  return new Promise((resolve) => {
    if (!w) { resolve(reg); return }
    w.addEventListener('statechange', () => { if (w.state === 'activated') resolve(reg) })
  })
}

export async function currentSubscription(base) {
  if (!pushSupported()) return null
  const reg = await navigator.serviceWorker.getRegistration(scopeOf(base))
  return reg ? reg.pushManager.getSubscription() : null
}

/** Asks for permission, registers the worker, subscribes. Returns the subscription JSON. */
export async function subscribePush(base, publicKey) {
  if (!pushSupported()) throw new Error('unsupported')
  const perm = await Notification.requestPermission()
  if (perm !== 'granted') throw new Error('denied')
  const reg = await activated(await navigator.serviceWorker.register(`${base}push-sw.js`, { scope: scopeOf(base) }))
  const sub = (await reg.pushManager.getSubscription())
    || (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(publicKey) }))
  return sub.toJSON()
}

export async function unsubscribePush(base) {
  const sub = await currentSubscription(base)
  if (!sub) return null
  const endpoint = sub.endpoint
  await sub.unsubscribe()
  return endpoint
}
