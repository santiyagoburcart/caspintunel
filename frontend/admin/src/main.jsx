import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import FeedbackBridge from './components/FeedbackBridge'
import { ADMIN_BASE } from './lib/base'
import { AuthProvider } from './lib/auth'
import { LivePaymentsProvider } from './lib/livePayments'
import { LiveTicketsProvider } from './lib/liveTickets'
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

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter basename={ADMIN_BASE}>
      <I18nProvider>
        <ThemeProvider>
          <ToastProvider>
            <FeedbackBridge />
            <ConfirmProvider>
            <AuthProvider>
              <LivePaymentsProvider>
                <LiveTicketsProvider>
                  <App />
                </LiveTicketsProvider>
              </LivePaymentsProvider>
            </AuthProvider>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeProvider>
      </I18nProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
