// Telegram Mini App SDK first (bundled, no CDN): it reads #tgWebAppData before
// the router can touch the URL and exposes window.Telegram.WebApp
import '@twa-dev/sdk'
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { AuthProvider } from './lib/auth'
import { I18nProvider } from './lib/i18n'
import { ThemeProvider } from './theme/ThemeProvider'
import { ToastProvider } from './components/Toast'
import { ConfirmProvider } from './components/ConfirmDialog'
// Fonts are bundled at build time (@fontsource) — nothing is fetched from a
// CDN, so the site works on an offline / Iran-only server. Persian UI uses
// Vazirmatn everywhere, English uses Inter; JetBrains Mono only for code/links.
import '@fontsource/vazirmatn/400.css'
import '@fontsource/vazirmatn/500.css'
import '@fontsource/vazirmatn/600.css'
import '@fontsource/vazirmatn/700.css'
import '@fontsource/vazirmatn/800.css'
import '@fontsource/inter/400.css'
import '@fontsource/inter/500.css'
import '@fontsource/inter/600.css'
import '@fontsource/inter/700.css'
import '@fontsource/inter/800.css'
import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/600.css'
import './index.css'
import './agency-tones.css'   // v1.57 agency colour system (identical in both SPAs)

// No caching service worker on this site: remove any left by an older build, with its caches,
// so every entry point (browser, Telegram in-app browser, Mini App) shows the current site.
// v1.33: the only worker kept is the push one (lib/webPush.js) — scope "/push-sw/", no page
// lives there, it serves and caches nothing.
try {
  navigator.serviceWorker?.getRegistrations?.().then((rs) => rs.forEach((r) => {
    if (!String(r.scope || '').endsWith('/push-sw/')) r.unregister()
  })).catch(() => {})
  if (window.caches?.keys) caches.keys().then((ks) => ks.forEach((k) => caches.delete(k))).catch(() => {})
} catch { /* not supported */ }

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <I18nProvider>
        <ThemeProvider>
          <ToastProvider>
            <ConfirmProvider>
            <AuthProvider>
              <App />
            </AuthProvider>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeProvider>
      </I18nProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
