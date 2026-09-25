import { useEffect, useRef } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { useAuth } from './lib/auth'
import { isTelegramMiniApp, tgStartParam } from './lib/telegram'
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

function Private({ children }) {
  const { user, loading, tgError } = useAuth()
  if (loading) return <div className="grid min-h-full place-items-center"><Spinner /></div>
  if (tgError && isTelegramMiniApp()) {
    return (
      <div className="mx-auto grid min-h-full max-w-sm place-items-center p-6">
        <div className="card space-y-3 text-center">
          <div className="text-lg font-bold">⚠️</div>
          <Alert>{tgError}</Alert>
          <button className="btn-primary w-full" onClick={() => window.location.reload()}>
            تلاش دوباره / Retry
          </button>
        </div>
      </div>
    )
  }
  return user ? children : <Navigate to="/login" replace />
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
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/reset" element={<ResetPassword />} />
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
