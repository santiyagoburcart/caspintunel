import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { useTheme } from '../theme/ThemeProvider'

const nav = [
  ['/', 'dashboard', null],
  ['/users', 'users', 'users.view'],
  ['/plans', 'plans', 'plans.manage'],
  ['/payments', 'payments', 'payment.view'],
  ['/accounting', 'accounting', 'accounting.view'],
  ['/cards', 'cards', 'payment.view'],
  ['/monitoring', 'monitoring', 'monitoring.view'],
  ['/panel-link', 'panel_link', 'settings.manage'],
  ['/bots', 'bots', 'bots.manage'],
  ['/branding', 'branding', 'settings.manage'],
  ['/pages', 'pages', 'pages.manage'],
  ['/themes', 'themes', 'themes.manage'],
  ['/roles', 'roles', 'roles.manage'],
]

export default function Layout() {
  const { staff, logout, can } = useAuth()
  const { t, lang, setLang } = useI18n()
  const { mode, toggle, config } = useTheme()
  const go = useNavigate()
  const [open, setOpen] = useState(false)

  const items = nav.filter(([, , p]) => !p || can(p))

  return (
    <div className="min-h-full aurora md:flex">
      {/* backdrop (mobile only, when the menu is open) */}
      {open && (
        <div className="fixed inset-0 z-20 bg-black/40 md:hidden" onClick={() => setOpen(false)} />
      )}

      <aside
        className={`glass fixed inset-y-0 start-0 z-30 w-64 overflow-y-auto p-3 transition-transform
          ${open ? 'translate-x-0' : 'ltr:-translate-x-full rtl:translate-x-full'}
          md:static md:z-auto md:m-3 md:w-56 md:shrink-0 md:translate-x-0`}
      >
        <div className="mb-3 flex items-center gap-2 font-bold">
          {config?.logo && <img src={config.logo} className="h-6 w-6 rounded" alt="" />}
          <span>{config?.site_name_fa || 'کسپین'} · پنل</span>
          <button className="btn-ghost ms-auto md:hidden" onClick={() => setOpen(false)} aria-label="close">✕</button>
        </div>
        <nav className="flex flex-col gap-1">
          {items.map(([to, key]) => (
            <NavLink key={to} to={to} end onClick={() => setOpen(false)}
              className={({ isActive }) => `btn-ghost whitespace-nowrap text-sm ${isActive ? 'text-primary' : ''}`}>
              {t(key)}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="flex-1">
        <header className="glass m-3 flex items-center gap-2 px-4 py-2 text-sm">
          <button className="btn-ghost md:hidden" onClick={() => setOpen(true)} aria-label="menu">☰</button>
          <button className="btn-ghost" onClick={toggle}>{mode === 'dark' ? '☀️' : '🌙'}</button>
          <button className="btn-ghost" onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}>{lang === 'fa' ? 'EN' : 'فا'}</button>
          <span className="ms-auto truncate text-muted">{staff?.username} · {staff?.role || (staff?.is_superadmin ? 'superadmin' : '')}</span>
          <button className="btn-ghost" onClick={() => { logout(); go('/login') }}>{t('logout')}</button>
        </header>
        <main className="mx-auto max-w-6xl p-3"><Outlet /></main>
      </div>
    </div>
  )
}
