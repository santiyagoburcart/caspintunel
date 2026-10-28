// No service worker on this site. An old one (from an earlier build) fetches this
// file to update itself: this version removes itself, clears its caches and reloads
// open pages so they get the current site.
self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    try { for (const k of await caches.keys()) await caches.delete(k) } catch (_) {}
    try { await self.registration.unregister() } catch (_) {}
    try { for (const c of await self.clients.matchAll({ type: 'window' })) c.navigate(c.url) } catch (_) {}
  })())
})
