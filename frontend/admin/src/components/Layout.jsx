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

  return (
    <div className="min-h-full aurora md:flex">
      <aside className="glass m-3 p-3 md:w-56 md:shrink-0">
        <div className="mb-3 flex items-center gap-2 font-bold">
          {config?.logo && <img src={config.logo} className="h-6 w-6 rounded" alt="" />}
          <span>{config?.site_name_fa || 'کسپین'} · پنل</span>
        </div>
        <nav className="flex gap-1 overflow-x-auto md:flex-col">
          {nav.filter(([, , p]) => !p || can(p)).map(([to, key]) => (
            <NavLink key={to} to={to} end
              className={({ isActive }) => `btn-ghost whitespace-nowrap text-sm ${isActive ? 'text-primary' : ''}`}>
              {t(key)}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="flex-1">
        <header className="glass m-3 flex items-center gap-2 px-4 py-2 text-sm">
          <button className="btn-ghost" onClick={toggle}>{mode === 'dark' ? '☀️' : '🌙'}</button>
          <button className="btn-ghost" onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}>{lang === 'fa' ? 'EN' : 'فا'}</button>
          <span className="ms-auto text-muted">{staff?.username} · {staff?.role || (staff?.is_superadmin ? 'superadmin' : '')}</span>
          <button className="btn-ghost" onClick={() => { logout(); go('/login') }}>{t('logout')}</button>
        </header>
        <main className="mx-auto max-w-6xl p-3"><Outlet /></main>
      </div>
    </div>
  )
}
