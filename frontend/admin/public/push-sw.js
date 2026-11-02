// v1.33 Web Push worker — shows notifications only. No fetch handler and no caches: it is
// registered with the scope "<base>push-sw/" (no page lives there), so it never serves pages.
// The payload {title, body, url, tag} comes from the server (apps/notifications/webpush.py);
// `url` is a route of this app, put after the app's base path.
self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()))

const appBase = () => new URL('..', self.registration.scope).pathname          // "/panel/" or "/"

self.addEventListener('push', (e) => {
  let d = {}
  try { d = e.data ? e.data.json() : {} } catch (_) { d = { body: e.data ? e.data.text() : '' } }
  const base = appBase()
  const url = d.url ? base.replace(/\/$/, '') + d.url : base
  e.waitUntil(self.registration.showNotification(d.title || 'caspintunel', {
    body: d.body || '', tag: d.tag || undefined, renotify: !!d.tag, data: { url },
  }))
})

self.addEventListener('notificationclick', (e) => {
  e.notification.close()
  const target = new URL((e.notification.data && e.notification.data.url) || appBase(), self.location.origin).href
  e.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    for (const w of wins) {
      // the customer site lives at "/" (which also prefixes the panel): there, only reuse a tab
      // already on that page; the panel reuses any of its own tabs
      const mine = appBase() === '/' ? new URL(w.url).pathname === new URL(target).pathname
        : w.url.startsWith(self.location.origin + appBase())
      if (mine) {
        try { await w.focus(); return w.navigate ? w.navigate(target) : undefined } catch (_) { /* fall through */ }
      }
    }
    return self.clients.openWindow(target)
  })())
})
