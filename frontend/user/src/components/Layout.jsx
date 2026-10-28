import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { useTheme } from '../theme/ThemeProvider'
import { isTelegramMiniApp } from '../lib/telegram'
import { CaspianBrand } from './caspian'
import NotificationBell from './NotificationBell'

const links = [
  ['/', 'dashboard'],
  ['/store', 'store'],
  ['/history', 'history'],
  ['/tickets', 'tickets'],
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
  return <CaspianLayout />
}

/* ---- Caspian: sticky glass top-nav shell (Stitch redesign) ---- */
const MENU_ICON = 'M4 6h16M4 12h16M4 18h16'
const CLOSE_ICON = 'M6 18L18 6M6 6l12 12'
const SUN_ICON = ['M12 3v2M12 19v2M5 5l1.5 1.5M17.5 17.5L19 19M3 12h2M19 12h2M5 19l1.5-1.5M17.5 6.5L19 5', 'M12 8a4 4 0 100 8 4 4 0 000-8z']
const MOON_ICON = 'M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z'
const OUT_ICON = 'M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9'

function CaspianLayout() {
  const { user, logout } = useAuth()
  const { t, lang, setLang } = useI18n()
  const { mode, toggle, locked, config } = useTheme()
  const nav = useNavigate()
  const [open, setOpen] = useState(false)
  const inTelegram = isTelegramMiniApp()
  const brand = lang === 'fa' ? (config?.site_name_fa || 'کسپین تانل') : (config?.site_name_en || 'caspintunel')

  const NavItems = ({ onClick }) => links.map(([to, key]) => (
    <NavLink key={to} to={to} end={to !== '/tickets'} onClick={onClick}
      className={({ isActive }) => 'csp-nav-link' + (isActive ? ' csp-nav-link--on' : '')}>
      {t(key)}
    </NavLink>
  ))

  return (
    <div className="csp-shell">
      <style>{CSP_LAYOUT_CSS}</style>

      <header className="csp-topbar">
        <div className="csp-topbar-inner">
          <div className="csp-topbar-l">
            <button className="csp-icon-btn csp-menu-btn" onClick={() => setOpen(true)} aria-label={t('menu')}>
              <LIco d={MENU_ICON} />
            </button>
            <NavLink to="/" className="csp-topbar-brand">
              <CaspianBrand logo={config?.logo} size={34} />
              <span className="csp-topbar-brand-txt">
                <span className="csp-topbar-brand-name csp-headline">{brand}</span>
                <span className="csp-topbar-brand-sub">{lang === 'fa' ? 'پورتال کاربران' : 'user portal'}</span>
              </span>
            </NavLink>
            <nav className="csp-nav">
              <NavItems />
            </nav>
          </div>

          <div className="csp-topbar-r">
            <NotificationBell />
            {!locked && (
              <button className="csp-icon-btn csp-hide-phone" onClick={toggle} aria-label={t('theme')}>
                <LIco d={mode === 'dark' ? SUN_ICON : MOON_ICON} />
              </button>
            )}
            <button className="csp-lang csp-hide-phone" onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}>
              {lang === 'fa' ? 'EN' : 'فا'}
            </button>
            <div className="csp-user">
              <span className="csp-user-av">{(user?.name || user?.username || '?').slice(0, 1).toUpperCase()}</span>
              <span className="csp-user-name">{user?.name || user?.username}</span>
              {!inTelegram && (
                <button className="csp-icon-btn csp-logout csp-hide-phone" onClick={() => logout().then(() => nav('/login'))}
                  aria-label={t('logout')} title={t('logout')}>
                  <LIco d={OUT_ICON} />
                </button>
              )}
            </div>
          </div>
        </div>
      </header>

      {open && (
        <div className="csp-drawer-wrap" onClick={() => setOpen(false)}>
          <div className="csp-drawer-scrim" />
          <nav className="csp-drawer" onClick={(e) => e.stopPropagation()}>
            <div className="csp-drawer-head">
              <CaspianBrand logo={config?.logo} size={30} />
              <span className="csp-headline">{brand}</span>
              <button className="csp-icon-btn" onClick={() => setOpen(false)} aria-label={t('close')}>
                <LIco d={CLOSE_ICON} />
              </button>
            </div>
            <NavItems onClick={() => setOpen(false)} />
            {/* phones: theme, language and logout live here so the top bar stays clean */}
            <div className="csp-drawer-foot">
              {!locked && (
                <button type="button" className="csp-drawer-act" onClick={toggle}>
                  <LIco d={mode === 'dark' ? SUN_ICON : MOON_ICON} />{t('theme')}: {mode === 'dark' ? t('dark') : t('light')}
                </button>
              )}
              <button type="button" className="csp-drawer-act" onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}>
                <span className="csp-drawer-lang">{lang === 'fa' ? 'EN' : 'فا'}</span>{lang === 'fa' ? 'English' : 'فارسی'}
              </button>
              {!inTelegram && (
                <button type="button" className="csp-drawer-act csp-drawer-out" onClick={() => { setOpen(false); logout().then(() => nav('/login')) }}>
                  <LIco d={OUT_ICON} />{t('logout')}
                </button>
              )}
            </div>
          </nav>
        </div>
      )}

      <main className="csp-main">
        <Outlet />
      </main>
    </div>
  )
}

function LIco({ d }) {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {Array.isArray(d) ? d.map((p, i) => <path key={i} d={p} />) : <path d={d} />}
    </svg>
  )
}

const CSP_LAYOUT_CSS = `
.csp-shell { min-height: 100%; display: flex; flex-direction: column; background: var(--c-bg); }
.csp-topbar {
  position: sticky; top: 0; z-index: 40;
  background: color-mix(in srgb, var(--c-surface) 82%, transparent);
  -webkit-backdrop-filter: blur(14px); backdrop-filter: blur(14px);
  border-bottom: 1px solid var(--c-border);
}
.csp-topbar-inner {
  max-width: 1200px; margin: 0 auto; padding: 0 clamp(14px, 3vw, 28px);
  height: 66px; display: flex; align-items: center; justify-content: space-between; gap: 14px;
}
.csp-topbar-l { display: flex; align-items: center; gap: 14px; min-width: 0; }
.csp-topbar-brand { display: flex; align-items: center; gap: 10px; text-decoration: none; color: var(--c-text); }
.csp-topbar-brand-txt { display: flex; flex-direction: column; line-height: 1.15; }
.csp-topbar-brand-name { font-size: 14px; font-weight: 800; color: var(--c-primary); }
.csp-topbar-brand-sub {
  font-size: 10px; color: var(--c-text-muted); letter-spacing: .02em;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
}
.csp-nav {
  display: none; align-items: center; gap: 2px; padding: 4px; border-radius: 999px;
  background: color-mix(in srgb, var(--c-text-muted) 10%, transparent);
}
@media (min-width: 1000px) { .csp-nav { display: flex; } }
.csp-nav-link {
  padding: 7px 15px; border-radius: 999px; font-size: 13px; font-weight: 600;
  color: var(--c-text-muted); white-space: nowrap; transition: color .15s, background .15s;
}
.csp-nav-link:hover { color: var(--c-text); }
.csp-nav-link--on { background: var(--c-primary); color: #fff; }

.csp-topbar-r { display: flex; align-items: center; gap: 8px; }
.csp-icon-btn {
  width: 36px; height: 36px; flex-shrink: 0; display: grid; place-items: center; border-radius: 999px;
  color: var(--c-text-muted); background: color-mix(in srgb, var(--c-text-muted) 10%, transparent);
  border: 0; cursor: pointer; transition: color .15s, background .15s;
}
.csp-icon-btn:hover { color: var(--c-text); background: color-mix(in srgb, var(--c-text-muted) 16%, transparent); }
.csp-menu-btn { display: grid; }
@media (min-width: 1000px) { .csp-menu-btn { display: none; } }
.csp-lang {
  height: 36px; padding: 0 12px; border-radius: 999px; font-size: 12px; font-weight: 700; cursor: pointer;
  color: var(--c-text); background: color-mix(in srgb, var(--c-text-muted) 10%, transparent); border: 0;
}
.csp-lang:hover { color: var(--c-primary); }
.csp-user {
  display: flex; align-items: center; gap: 8px; padding: 4px 4px 4px 10px; border-radius: 999px;
  background: color-mix(in srgb, var(--c-text-muted) 10%, transparent);
}
[dir="rtl"] .csp-user { padding: 4px 10px 4px 4px; }
.csp-user-name { font-size: 12px; font-weight: 600; max-width: 90px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 640px) { .csp-user-name { display: none; } }
.csp-user-av {
  width: 28px; height: 28px; flex-shrink: 0; display: grid; place-items: center; border-radius: 50%;
  background: var(--c-primary); color: #fff; font-size: 12px; font-weight: 700;
}
.csp-logout { width: 30px; height: 30px; background: transparent; }
.csp-logout:hover { color: var(--c-danger); background: color-mix(in srgb, var(--c-danger) 12%, transparent); }

/* phones: a clean top bar — menu · brand ·········· bell · avatar */
.csp-drawer-foot { display: none; }
@media (max-width: 640px) {
  .csp-hide-phone { display: none !important; }
  .csp-topbar-inner { height: 58px; gap: 8px; padding: 0 12px; }
  .csp-topbar-l { gap: 8px; }
  .csp-topbar-r { gap: 6px; flex-shrink: 0; }
  .csp-topbar-brand { gap: 8px; min-width: 0; }
  .csp-topbar-brand-txt { min-width: 0; }
  .csp-topbar-brand-name { white-space: nowrap; font-size: 14px; }
  .csp-topbar-brand-sub { display: none; }
  .csp-user { padding: 3px !important; }
  .csp-drawer-foot { display: flex; flex-direction: column; gap: 6px; margin-top: auto; padding-top: 12px; border-top: 1px solid var(--c-border); }
  .csp-drawer-act { display: flex; align-items: center; gap: 10px; min-height: 44px; padding: 0 12px; border-radius: 12px; font-size: 14px; font-weight: 600;
    color: var(--c-text); background: color-mix(in srgb, var(--c-text-muted) 8%, transparent); text-align: start; }
  .csp-drawer-lang { width: 19px; text-align: center; font-size: 12px; font-weight: 800; color: var(--c-primary); }
  .csp-drawer-out { color: var(--c-danger); }
}
@media (max-width: 340px) { .csp-topbar-brand-name { font-size: 13px; } }

/* mobile drawer */
.csp-drawer-wrap { position: fixed; inset: 0; z-index: 60; }
.csp-drawer-scrim { position: absolute; inset: 0; background: rgba(2, 6, 16, .5); }
.csp-drawer {
  position: absolute; inset-block: 0; inset-inline-start: 0; width: 268px; max-width: 82vw;
  background: var(--c-surface); border-inline-end: 1px solid var(--c-border);
  display: flex; flex-direction: column; gap: 4px; padding: 14px; overflow-y: auto;
  animation: csp-drw .2s ease-out;
}
:root:not(.dark) .csp-drawer { background: #fff; }
@keyframes csp-drw { from { transform: translateX(-8%); opacity: .4; } }
[dir="rtl"] .csp-drawer { animation-name: csp-drw-r; }
@keyframes csp-drw-r { from { transform: translateX(8%); opacity: .4; } }
.csp-drawer-head {
  display: flex; align-items: center; gap: 10px; padding: 4px 4px 14px;
  margin-bottom: 6px; border-bottom: 1px solid var(--c-border);
}
.csp-drawer-head .csp-headline { flex: 1; font-size: 15px; font-weight: 800; }
.csp-drawer .csp-nav-link { display: block; }

.csp-main { flex: 1; width: 100%; max-width: 1200px; margin: 0 auto; padding: clamp(16px, 3vw, 28px); }
`
