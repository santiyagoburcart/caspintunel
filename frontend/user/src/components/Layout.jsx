import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { useTheme } from '../theme/ThemeProvider'

const links = [
  ['/', 'dashboard'],
  ['/store', 'store'],
  ['/history', 'history'],
  ['/help', 'pages'],
  ['/profile', 'profile'],
]

export default function Layout() {
  const { user, logout } = useAuth()
  const { t, lang, setLang } = useI18n()
  const { mode, toggle, config } = useTheme()
  const nav = useNavigate()

  return (
    <div className="min-h-full aurora">
      <header className="glass sticky top-0 z-10 m-3 flex items-center gap-3 px-4 py-3">
        <div className="flex items-center gap-2 font-bold">
          {config?.logo && <img src={config.logo} alt="" className="h-7 w-7 rounded" />}
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
          <button className="btn-ghost text-sm" onClick={toggle}>{mode === 'dark' ? '☀️' : '🌙'}</button>
          <button className="btn-ghost text-sm" onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}>
            {lang === 'fa' ? 'EN' : 'فا'}
          </button>
          <span className="hidden text-sm text-muted sm:inline">{user?.name || user?.username}</span>
          <button className="btn-ghost text-sm" onClick={() => logout().then(() => nav('/login'))}>{t('logout')}</button>
        </div>
      </header>

      <nav className="mx-3 mb-2 flex gap-1 overflow-x-auto md:hidden">
        {links.map(([to, key]) => (
          <NavLink key={to} to={to} end
            className={({ isActive }) => `btn-ghost whitespace-nowrap text-sm ${isActive ? 'text-primary' : ''}`}>
            {t(key)}
          </NavLink>
        ))}
      </nav>

      <main className="mx-auto max-w-4xl p-3">
        <Outlet />
      </main>
    </div>
  )
}
