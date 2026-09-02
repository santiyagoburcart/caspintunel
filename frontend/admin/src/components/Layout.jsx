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
  ['/settings', 'settings', 'settings.manage'],
  ['/pages', 'pages', 'pages.manage'],
  ['/themes', 'themes', 'themes.manage'],
  ['/roles', 'roles', 'roles.manage'],
]

function NavLinks({ items, t, onNavigate }) {
  return (
    <nav className="flex flex-col gap-1">
      {items.map(([to, key]) => (
        <NavLink key={to} to={to} end onClick={onNavigate}
          className={({ isActive }) => `btn-ghost whitespace-nowrap text-sm ${isActive ? 'text-primary' : ''}`}>
          {t(key)}
        </NavLink>
      ))}
    </nav>
  )
}

export default function Layout() {
  const { staff, logout, can } = useAuth()
  const { t, lang, setLang } = useI18n()
  const { mode, toggle, config } = useTheme()
  const go = useNavigate()
  const [open, setOpen] = useState(false)

  const items = nav.filter(([, , p]) => !p || can(p))
  const brand = (lang === 'fa' ? config?.site_name_fa : config?.site_name_en) || (lang === 'fa' ? 'کسپین' : 'caspin')

  const Brand = ({ children }) => (
    <div className="mb-3 flex items-center gap-2 font-bold">
      {config?.logo && <img src={config.logo} className="h-6 w-6 rounded" alt="" />}
      <span className="truncate">{brand} · {t('panel_word')}</span>
      {children}
    </div>
  )

  return (
    <div className="min-h-full aurora md:flex">
      {/* desktop sidebar — always visible from md up */}
      <aside className="glass m-3 hidden w-56 shrink-0 self-start overflow-y-auto p-3 md:block">
        <Brand />
        <NavLinks items={items} t={t} />
      </aside>

      {/* mobile drawer */}
      {open && (
        <div className="fixed inset-0 z-30 md:hidden" onClick={() => setOpen(false)}>
          <div className="absolute inset-0 bg-black/40" />
          <aside
            className="glass absolute inset-y-0 start-0 w-64 max-w-[80vw] overflow-y-auto p-3"
            onClick={(e) => e.stopPropagation()}
          >
            <Brand>
              <button className="btn-ghost ms-auto shrink-0" onClick={() => setOpen(false)} aria-label="close">✕</button>
            </Brand>
            <NavLinks items={items} t={t} onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}

      <div className="min-w-0 flex-1">
        <header className="glass m-3 flex items-center gap-2 px-3 py-2 text-sm sm:px-4">
          <button className="btn-ghost shrink-0 md:hidden" onClick={() => setOpen(true)} aria-label="menu">☰</button>
          <button className="btn-ghost shrink-0" onClick={toggle}>{mode === 'dark' ? '☀️' : '🌙'}</button>
          <button className="btn-ghost shrink-0" onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}>{lang === 'fa' ? 'EN' : 'فا'}</button>
          <span className="ms-auto truncate text-muted">
            {staff?.username}{staff?.role ? ` · ${staff.role}` : staff?.is_superadmin ? ' · superadmin' : ''}
          </span>
          <button className="btn-ghost shrink-0" onClick={() => { logout(); go('/login') }}>{t('logout')}</button>
        </header>
        <main className="mx-auto max-w-6xl p-3"><Outlet /></main>
      </div>
    </div>
  )
}
