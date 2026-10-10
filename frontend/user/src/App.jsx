import { useEffect, useRef, useState } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { useAuth } from './lib/auth'
import { isTelegramMiniApp, isTelegramWebView, tgRequestContact, tgStartParam } from './lib/telegram'
import { useI18n } from './lib/i18n'
import { Alert, Spinner } from './components/ui'
import Layout from './components/Layout'
import Login from './pages/Login'
import Register from './pages/Register'
import ResetPassword from './pages/ResetPassword'
import VerifyEmail from './pages/VerifyEmail'
import Dashboard from './pages/Dashboard'
import Store from './pages/Store'
import Checkout from './pages/Checkout'
import History from './pages/History'
import Profile from './pages/Profile'
import Help from './pages/Help'
import Rules from './pages/Rules'

const TG_ROUTES = { store: '/store', dashboard: '/', history: '/history', help: '/help', rules: '/rules', profile: '/profile' }

/** Inside Telegram the session comes from initData: never a login form —
 *  a spinner, then the app, or a clear error with what to do. */
function TelegramGate() {
  const { tgError, retryTelegram } = useAuth()
  const { lang } = useI18n()
  const fa = lang !== 'en'
  const [asked, setAsked] = useState(false)
  if (tgError === 'phone_required') {
    const share = () => {
      const ok = tgRequestContact((shared) => { if (shared) setTimeout(retryTelegram, 1500) })
      setAsked(!ok)
    }
    return (
      <div className="mx-auto grid min-h-full max-w-sm place-items-center p-6">
        <div className="card space-y-3 text-center">
          <div className="text-3xl" aria-hidden="true">📱</div>
          <p className="text-sm leading-7">{fa
            ? 'برای ورود، شمارهٔ موبایل خود را با ربات به اشتراک بگذارید.'
            : 'To sign in, share your phone number with the bot.'}</p>
          <button className="btn-primary w-full" onClick={share}>{fa ? 'اشتراک‌گذاری شماره' : 'Share phone number'}</button>
          {asked && <p className="text-xs text-muted">{fa
            ? 'از دکمهٔ «اشتراک‌گذاری شماره» در خود ربات استفاده کنید، سپس «تلاش دوباره» را بزنید.'
            : 'Use the “Share phone number” button in the bot chat, then tap Retry.'}</p>}
          <button className="btn-ghost w-full" onClick={retryTelegram}>{fa ? 'تلاش دوباره' : 'Retry'}</button>
        </div>
      </div>
    )
  }
  if (tgError) {
    const missing = tgError === 'no_init_data'
    return (
      <div className="mx-auto grid min-h-full max-w-sm place-items-center p-6">
        <div className="card space-y-3 text-center">
          <div className="text-3xl" aria-hidden="true">⚠️</div>
          <p className="text-sm font-bold leading-7">{fa ? 'ورود خودکار انجام نشد' : 'Automatic sign-in failed'}</p>
          <p className="text-sm leading-7 text-muted">{fa
            ? 'این صفحه را از داخل ربات و با دکمهٔ «🌐 اپ» باز کنید.'
            : 'Open this page from the bot with the “🌐 App” button.'}</p>
          {!missing && <Alert>{tgError}</Alert>}
          <button className="btn-primary w-full" onClick={missing ? () => window.location.reload() : retryTelegram}>
            {fa ? 'تلاش دوباره' : 'Retry'}
          </button>
          <button className="btn-ghost w-full" onClick={() => { try { window.Telegram?.WebApp?.close() } catch { /* ignore */ } }}>
            {fa ? 'بستن' : 'Close'}
          </button>
        </div>
      </div>
    )
  }
  return <div className="grid min-h-full place-items-center"><Spinner /></div>
}

function Private({ children }) {
  const { user, loading, tgError } = useAuth()
  if (loading) return <div className="grid min-h-full place-items-center"><Spinner /></div>
  if (!user && isTelegramWebView()) return <TelegramGate />
  if (tgError && isTelegramWebView()) return <TelegramGate />
  return user ? children : <Navigate to="/login" replace />
}

/** /login, /register, /reset: inside Telegram there is no form — the mini app
 *  signs in by itself (or explains why it could not). */
function PublicOnly({ children }) {
  const { user, loading } = useAuth()
  if (!isTelegramWebView()) return children
  if (user) return <Navigate to="/" replace />
  if (loading) return <div className="grid min-h-full place-items-center"><Spinner /></div>
  return <TelegramGate />
}

// Honour a t.me/<bot>/<app>?startapp=<route> deep link, once, after login.
function TelegramStart() {
  const nav = useNavigate()
  const done = useRef(false)
  useEffect(() => {
    if (done.current || !isTelegramMiniApp()) return
    done.current = true
    const dest = TG_ROUTES[tgStartParam()]
    if (dest && dest !== window.location.pathname) nav(dest, { replace: true })
  }, [])
  return null
}

function PublicTerms() {
  return (
    <div className="mx-auto w-full max-w-3xl p-4 sm:p-6">
      <Rules />
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<PublicOnly><Login /></PublicOnly>} />
      <Route path="/register" element={<PublicOnly><Register /></PublicOnly>} />
      <Route path="/reset" element={<PublicOnly><ResetPassword /></PublicOnly>} />
      <Route path="/verify-email" element={<VerifyEmail />} />
      {/* public copy of the rules — the sign-up checkbox links here (/rules needs a login) */}
      <Route path="/terms" element={<PublicTerms />} />
      <Route element={<Private><><TelegramStart /><Layout /></></Private>}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/store" element={<Store />} />
        <Route path="/checkout" element={<Checkout />} />
        <Route path="/history" element={<History />} />
        <Route path="/rules" element={<Rules />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/help" element={<Help />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
