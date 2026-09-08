import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { useTheme } from '../theme/ThemeProvider'
import { isTelegramMiniApp } from '../lib/telegram'

const links = [
  ['/', 'dashboard'],
  ['/store', 'store'],
  ['/history', 'history'],
  ['/rules', 'rules'],
  ['/profile', 'profile'],
  ['/help', 'pages'],
]

// brand-mark fallback when no logo is uploaded
function BrandMark() {
  return (
    <span className="grid h-7 w-7 place-items-center rounded-lg text-white"
      style={{ background: 'linear-gradient(135deg, var(--c-primary), var(--c-secondary))' }}>
      <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2.4"
        strokeLinecap="round" strokeLinejoin="round"><path d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
    </span>
  )
}

export default function Layout() {
  const { user, logout } = useAuth()
  const { t, lang, setLang } = useI18n()
  const { mode, toggle, locked, config } = useTheme()
  const nav = useNavigate()
  const [open, setOpen] = useState(false)
  const inTelegram = isTelegramMiniApp()

  return (
    <div className="min-h-full aurora">
      <header className="glass sticky top-0 z-20 m-3 flex items-center gap-3 px-4 py-3">
        <button className="btn-ghost text-sm md:hidden" onClick={() => setOpen(true)} aria-label="menu">☰</button>

        <div className="flex items-center gap-2 font-bold">
          {config?.logo
            ? <img src={config.logo} alt="" className="h-7 w-7 rounded object-contain" />
            : <BrandMark />}
          <span>{lang === 'fa' ? config?.site_name_fa || 'کسپین تانل' : config?.site_name_en || 'caspintunel'}</span>
        </div>

        <nav className="hidden gap-1 md:flex">
          {links.map(([to, key]) => (
            <NavLink key={to} to={to} end
              className={({ isActive }) => `btn-ghost text-sm ${isActive ? 'text-primary' : ''}`}>
              {t(key)}
            </NavLink>
          ))}
        </nav>

        <div className="ms-auto flex items-center gap-2">
          {/* the active theme can lock the whole site to one mode (e.g. Royal Frost is light-only) */}
          {!locked && (
            <button className="btn-ghost text-sm" onClick={toggle}>{mode === 'dark' ? '☀️' : '🌙'}</button>
          )}
          <button className="btn-ghost text-sm" onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}>
            {lang === 'fa' ? 'EN' : 'فا'}
          </button>
          <span className="hidden text-sm text-muted sm:inline">{user?.name || user?.username}</span>
          {/* In Telegram the identity is the Telegram account — no password to log back in with. */}
          {!inTelegram && (
            <button className="btn-ghost text-sm" onClick={() => logout().then(() => nav('/login'))}>{t('logout')}</button>
          )}
        </div>
      </header>

      {/* mobile drawer */}
      {open && (
        <div className="fixed inset-0 z-30 md:hidden" onClick={() => setOpen(false)}>
          <div className="absolute inset-0 bg-black/40" />
          <nav
            className="glass absolute inset-y-0 start-0 flex w-64 flex-col gap-1 overflow-y-auto p-3"
            onClick={(e) => e.stopPropagation()}
          >
            <button className="btn-ghost mb-2 self-end" onClick={() => setOpen(false)} aria-label="close">✕</button>
            {links.map(([to, key]) => (
              <NavLink key={to} to={to} end onClick={() => setOpen(false)}
                className={({ isActive }) => `btn-ghost text-sm ${isActive ? 'text-primary' : ''}`}>
                {t(key)}
              </NavLink>
            ))}
          </nav>
        </div>
      )}

      <main className="mx-auto max-w-4xl p-3">
        <Outlet />
      </main>
    </div>
  )
}
