import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { useTheme } from '../theme/ThemeProvider'

// Aurora / Royal Frost — the original flat nav (kept exactly as-is).
const nav = [
  ['/', 'dashboard', null],
  ['/users', 'users', 'users.view'],
  ['/plans', 'plans', 'plans.manage'],
  ['/payments', 'payments', 'payment.view'],
  ['/transactions', 'transactions', 'payment.view'],
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

// Caspian — the same 15 real routes, arranged into the Stitch reference's
// grouped sections ([route, i18n-key, permission, icon]).
const CASPIAN_GROUPS = [
  ['nav_group_core', [
    ['/', 'dashboard', null, 'dashboard'],
    ['/monitoring', 'monitoring', 'monitoring.view', 'monitoring'],
    ['/panel-link', 'panel_link', 'settings.manage', 'panel'],
  ]],
  ['nav_group_users', [
    ['/users', 'users', 'users.view', 'users'],
    ['/plans', 'plans', 'plans.manage', 'plans'],
  ]],
  ['nav_group_finance', [
    ['/payments', 'payments', 'payment.view', 'payments'],
    ['/transactions', 'transactions', 'payment.view', 'transactions'],
    ['/accounting', 'accounting', 'accounting.view', 'accounting'],
    ['/cards', 'cards', 'payment.view', 'cards'],
  ]],
  ['nav_group_config', [
    ['/branding', 'branding', 'settings.manage', 'branding'],
    ['/settings', 'settings', 'settings.manage', 'settings'],
    ['/bots', 'bots', 'bots.manage', 'bots'],
    ['/pages', 'pages', 'pages.manage', 'pages'],
    ['/themes', 'themes', 'themes.manage', 'themes'],
    ['/roles', 'roles', 'roles.manage', 'roles'],
  ]],
]

// Heroicons-style outline paths (self-hosted, no icon font / CDN) — chosen to
// echo the reference's Material Symbols intent.
const NAV_ICONS = {
  brand: 'M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z',
  menu: 'M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5',
  sun: 'M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z',
  moon: 'M21.752 15.002A9.72 9.72 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z',
  dashboard: 'M10.5 6a7.5 7.5 0 107.5 7.5h-7.5V6zM13.5 10.5H21A7.5 7.5 0 0013.5 3v7.5z',
  monitoring: 'M9.348 14.652a3.75 3.75 0 010-5.304m5.304 0a3.75 3.75 0 010 5.304m-7.425 2.121a6.75 6.75 0 010-9.546m9.546 0a6.75 6.75 0 010 9.546M5.106 18.894c-3.808-3.807-3.808-9.98 0-13.788m13.788 0c3.808 3.807 3.808 9.98 0 13.788M12 12h.008v.008H12V12z',
  users: 'M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z',
  plans: 'M9.568 3H5.25A2.25 2.25 0 003 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 005.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 009.568 3zM6 6h.008v.008H6V6z',
  panel: 'M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244',
  bots: 'M8.25 3v1.5M4.5 8.25H3m18 0h-1.5M4.5 12H3m18 0h-1.5m-15 3.75H3m18 0h-1.5M8.25 19.5V21M12 3v1.5m0 15V21m3.75-18v1.5m0 15V21m-9-1.5h10.5a2.25 2.25 0 002.25-2.25V6.75a2.25 2.25 0 00-2.25-2.25H6.75A2.25 2.25 0 004.5 6.75v10.5a2.25 2.25 0 002.25 2.25zm.75-12h9v9h-9v-9z',
  payments: 'M21 12a2.25 2.25 0 00-2.25-2.25H15a3 3 0 11-6 0H5.25A2.25 2.25 0 003 12m18 0v6a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 18v-6m18 0V9M3 12V9m18 0a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 9m18 0V6a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 6v3',
  transactions: 'M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5',
  accounting: 'M7.5 14.25v2.25m3-4.5v4.5m3-6.75v6.75m3-9v9M6 20.25h12A2.25 2.25 0 0020.25 18V6A2.25 2.25 0 0018 3.75H6A2.25 2.25 0 003.75 6v12A2.25 2.25 0 006 20.25z',
  cards: 'M2.25 8.25h19.5M2.25 9h19.5m-16.5 5.25h6m-6 2.25h3m-3.75 3h15a2.25 2.25 0 002.25-2.25V6.75A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25v10.5A2.25 2.25 0 004.5 19.5z',
  branding: 'M4.098 19.902a3.75 3.75 0 005.304 0l6.401-6.402M6.75 21A3.75 3.75 0 013 17.25V4.125C3 3.504 3.504 3 4.125 3h5.25c.621 0 1.125.504 1.125 1.125v4.072M6.75 21a3.75 3.75 0 003.75-3.75V8.197M6.75 21h13.125c.621 0 1.125-.504 1.125-1.125v-5.25c0-.621-.504-1.125-1.125-1.125h-4.072M10.5 8.197l2.88-2.88c.438-.439 1.15-.439 1.59 0l3.712 3.713c.44.44.44 1.152 0 1.59l-2.879 2.88M6.75 17.25h.008v.008H6.75v-.008z',
  settings: 'M10.5 6h9.75M10.5 6a1.5 1.5 0 11-3 0m3 0a1.5 1.5 0 10-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-9.75 0h9.75',
  pages: 'M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z',
  themes: 'M9.53 16.122a3 3 0 00-5.78 1.128 2.25 2.25 0 01-2.4 2.245 4.5 4.5 0 008.4-2.245c0-.399-.078-.78-.22-1.128zm0 0a15.998 15.998 0 003.388-1.62m-5.043-.025a15.994 15.994 0 011.622-3.395m3.42 3.42a15.995 15.995 0 004.764-4.648l3.876-5.814a1.151 1.151 0 00-1.597-1.597L14.146 6.32a15.996 15.996 0 00-4.649 4.763m3.42 3.42a6.776 6.776 0 00-3.42-3.42',
  roles: 'M9 12.75L11.25 15 15 9.75M21 12c0 5.591-3.824 10.29-9 11.622C6.824 22.29 3 17.591 3 12c0-1.933.204-3.44.596-4.996A11.943 11.943 0 0112 3c2.998 0 5.74 1.1 7.843 2.918A11.94 11.94 0 0121 12z',
}

function SideIcon({ name }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.7"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={NAV_ICONS[name] || NAV_ICONS.dashboard} />
    </svg>
  )
}

// ---- Aurora / Frost sidebar (unchanged) ----
function NavLinks({ items, t, onNavigate }) {
  return (
    <nav className="flex flex-col gap-1">
      {items.map(([to, key]) => (
        <NavLink key={to} to={to} end onClick={onNavigate}
          className={({ isActive }) =>
            `admin-nav-link btn-ghost whitespace-nowrap text-sm ${isActive ? 'active-nav text-primary' : ''}`}>
          {t(key)}
        </NavLink>
      ))}
    </nav>
  )
}

function LegacyLayout() {
  const { staff, logout, can } = useAuth()
  const { t, lang, setLang } = useI18n()
  const { mode, toggle, locked, config } = useTheme()
  const go = useNavigate()
  const [open, setOpen] = useState(false)

  const items = nav.filter(([, , p]) => !p || can(p))
  const brand = (lang === 'fa' ? config?.site_name_fa : config?.site_name_en) || (lang === 'fa' ? 'کسپین' : 'caspin')

  const Brand = ({ children }) => (
    <div className="admin-brand mb-3 flex items-center gap-2 font-bold">
      {config?.logo
        ? <img src={config.logo} className="h-6 w-6 rounded object-contain" alt="" />
        : <span className="grid h-6 w-6 shrink-0 place-items-center rounded text-primary">
            <SideIcon name="brand" />
          </span>}
      <span className="truncate">{brand} · {t('panel_word')}</span>
      {children}
    </div>
  )

  return (
    <div className="min-h-full aurora md:flex">
      {/* desktop sidebar — always visible from md up */}
      <aside className="admin-side glass m-3 hidden w-56 shrink-0 self-start overflow-y-auto p-3 md:block">
        <Brand />
        <NavLinks items={items} t={t} />
      </aside>

      {/* mobile drawer */}
      {open && (
        <div className="fixed inset-0 z-30 md:hidden" onClick={() => setOpen(false)}>
          <div className="absolute inset-0 bg-black/40" />
          <aside
            className="admin-side glass absolute inset-y-0 start-0 w-64 max-w-[80vw] overflow-y-auto p-3"
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
          {/* the active theme can lock the whole site to one mode (e.g. Royal Frost is light-only) */}
          {!locked && (
            <button className="btn-ghost shrink-0" onClick={toggle}>{mode === 'dark' ? '☀️' : '🌙'}</button>
          )}
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

// ---- Caspian sidebar (Stitch _9 dark "Caspian Tunnel" / _10 light "Azure Telemetry") ----
function CaspianNav({ groups, t, brand, logo, onNavigate }) {
  return (
    <div className="csp-side">
      <div className="csp-brand">
        <span className="csp-brand-ico">
          {logo ? <img src={logo} alt="" /> : <SideIcon name="brand" />}
        </span>
        <div className="csp-brand-txt">
          <span className="csp-brand-name"><b>{brand}</b></span>
          <span className="csp-brand-sub">{t('brand_core')}</span>
        </div>
      </div>
      <nav className="csp-nav">
        {groups.map(([gkey, items]) => items.length > 0 && (
          <div className="csp-group" key={gkey}>
            <div className="csp-group-h">{t(gkey)}</div>
            {items.map(([to, key, , icon]) => (
              <NavLink key={to} to={to} end onClick={onNavigate}
                className={({ isActive }) => 'csp-link' + (isActive ? ' csp-active' : '')}>
                <SideIcon name={icon} />
                <span className="csp-link-t">{t(key)}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
    </div>
  )
}

// mobile bottom-nav — 5 tabs, matches Stitch f10ea6b9 (DOM order; RTL flips it
// to Settings · Roles · Cards · Users · Dashboard, right→left). Every other
// route stays reachable through the hamburger drawer in the mobile header.
const CASPIAN_BOTNAV = [
  ['/', 'dashboard', null, 'dashboard'],
  ['/users', 'users', 'users.view', 'users'],
  ['/cards', 'cards', 'payment.view', 'cards'],
  ['/roles', 'roles', 'roles.manage', 'roles'],
  ['/settings', 'settings', 'settings.manage', 'settings'],
]

function CaspianLayout() {
  const { staff, logout, can } = useAuth()
  const { t, lang, setLang } = useI18n()
  const { mode, toggle, locked, config } = useTheme()
  const go = useNavigate()
  const [open, setOpen] = useState(false)

  const groups = CASPIAN_GROUPS.map(([g, items]) => [g, items.filter(([, , p]) => !p || can(p))])
  const botnav = CASPIAN_BOTNAV.filter(([, , p]) => !p || can(p))
  const brand = (lang === 'fa' ? config?.site_name_fa : config?.site_name_en)
    || (lang === 'fa' ? 'کسپین تانل' : 'Caspian Tunnel')

  return (
    <div className="csp-shell">
      <style>{CASPIAN_CSS}</style>

      {/* desktop rail — start side (right for fa/RTL, left for en/LTR) */}
      <aside className="csp-rail">
        <CaspianNav groups={groups} t={t} brand={brand} logo={config?.logo} />
      </aside>

      {/* mobile drawer — slides in from the same start side */}
      <div className={'csp-drawer-wrap' + (open ? ' open' : '')} onClick={() => setOpen(false)}>
        <div className="csp-drawer-bg" />
        <aside className="csp-drawer" onClick={(e) => e.stopPropagation()}>
          <CaspianNav groups={groups} t={t} brand={brand} logo={config?.logo} onNavigate={() => setOpen(false)} />
          <div className="csp-drawer-foot">
            {!locked && (
              <button className="csp-df-btn" onClick={toggle}>
                <SideIcon name={mode === 'dark' ? 'sun' : 'moon'} />
                {mode === 'dark' ? (lang === 'fa' ? 'روشن' : 'Light') : (lang === 'fa' ? 'تیره' : 'Dark')}
              </button>
            )}
            <button className="csp-df-btn" onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}>
              {lang === 'fa' ? 'English' : 'فارسی'}
            </button>
            <button className="csp-df-btn csp-df-out" onClick={() => { logout(); go('/login') }}>{t('logout')}</button>
          </div>
        </aside>
      </div>

      <div className="csp-main">
        {/* mobile top bar (≤767px) — Stitch f10ea6b9: RTL renders as
            [online + avatar : RIGHT] · [brand : CENTER] · [hamburger : LEFT] */}
        <header className="csp-mtop">
          <div className="csp-mtop-end">
            <span className="csp-mtop-avatar">{(staff?.username || '?').charAt(0).toUpperCase()}</span>
            <span className="csp-mtop-online"><i />{lang === 'fa' ? 'آنلاین' : 'Online'}</span>
          </div>
          <div className="csp-mtop-brand">
            <div className="csp-mtop-txt">
              <b>{brand}</b>
              <span>ADMIN CONTROL</span>
            </div>
            <span className="csp-mtop-logo">
              {config?.logo ? <img src={config.logo} alt="" /> : <b>C</b>}
            </span>
          </div>
          <button className="csp-mtop-burger" onClick={() => setOpen(true)} aria-label="menu">
            <SideIcon name="menu" />
          </button>
        </header>

        {/* desktop top bar (≥768px) */}
        <header className="csp-topbar">
          {!locked && (
            <button className="csp-tb-btn csp-tb-ico" onClick={toggle} aria-label="theme">
              <SideIcon name={mode === 'dark' ? 'sun' : 'moon'} />
            </button>
          )}
          <button className="csp-tb-btn" onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}>
            {lang === 'fa' ? 'EN' : 'فا'}
          </button>
          <span className="csp-tb-user">
            {staff?.username}{staff?.role ? ` · ${staff.role}` : staff?.is_superadmin ? ' · superadmin' : ''}
          </span>
          <button className="csp-tb-btn" onClick={() => { logout(); go('/login') }}>{t('logout')}</button>
        </header>

        <main className="csp-content mx-auto max-w-6xl p-3"><Outlet /></main>
      </div>

      {/* mobile bottom nav (≤767px) — Stitch f10ea6b9: 5 tabs, active = dot
          above the icon + primary colour + bolder stroke (no pill) */}
      <nav className="csp-botnav" style={{ '--csp-bn-n': botnav.length }}>
        {botnav.map(([to, key, , icon]) => (
          <NavLink key={to} to={to} end
            className={({ isActive }) => 'csp-bn-item' + (isActive ? ' on' : '')}>
            <span className="csp-bn-dot" />
            <SideIcon name={icon} />
            <span className="csp-bn-t">{t(key)}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  )
}

export default function Layout() {
  const { styleKey } = useTheme()
  // Caspian's Monitoring page now renders inside the normal sidebar layout,
  // like every other admin screen (it keeps its own header/toolbar + cards).
  if (styleKey === 'caspian') return <CaspianLayout />
  return <LegacyLayout />
}

const CASPIAN_CSS = `
.csp-shell { min-height: 100vh; }
.csp-main { min-width: 0; }
@media (min-width: 768px) { .csp-main { padding-inline-start: 18rem; } }

/* ---- rail + drawer share .csp-side (the visual surface) ---- */
.csp-rail { position: fixed; inset-block: 0; inset-inline-start: 0; width: 18rem; z-index: 40; display: none; }
@media (min-width: 768px) { .csp-rail { display: block; } }

.csp-side {
  height: 100%; display: flex; flex-direction: column; overflow-y: auto;
  background: #ffffff;
  border-inline-end: 1px solid var(--c-border);
  box-shadow: 0 1px 8px rgba(0,0,0,0.04);
  scrollbar-width: none;
}
.csp-side::-webkit-scrollbar { display: none; }
.dark .csp-side {
  background: rgba(10,14,22,0.94);
  -webkit-backdrop-filter: blur(18px); backdrop-filter: blur(18px);
  border-inline-end: 1px solid rgba(255,255,255,0.05);
  box-shadow: 0 0 40px rgba(0,0,0,0.6);
}

/* ---- brand block ---- */
.csp-brand { display: flex; align-items: center; gap: 12px; padding: 14px 20px; min-height: 68px; flex: 0 0 auto; }
.csp-brand-ico {
  width: 40px; height: 40px; border-radius: 12px; flex: 0 0 auto;
  display: grid; place-items: center; overflow: hidden;
  background: color-mix(in srgb, var(--c-primary) 12%, #ffffff); color: var(--c-primary);
}
.csp-brand-ico img { width: 100%; height: 100%; object-fit: contain; }
.csp-brand-ico svg { width: 22px; height: 22px; }
.dark .csp-brand-ico {
  background: rgba(39,42,52,0.6); color: var(--c-secondary);
  box-shadow: inset 1px 1px 1px rgba(255,255,255,0.1), 0 4px 12px color-mix(in srgb, var(--c-primary) 30%, transparent);
}
.csp-brand-txt { display: flex; flex-direction: column; min-width: 0; line-height: 1.35; }
.csp-brand-name b { font-size: 16px; font-weight: 800; letter-spacing: -.01em; color: var(--c-primary); }
.dark .csp-brand-name b { color: #dfe2ee; }
.csp-brand-sub {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 10.5px; font-weight: 500; letter-spacing: .02em; color: #707881;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.dark .csp-brand-sub { color: #bdc8d1; }

/* ---- grouped nav ---- */
.csp-nav { flex: 1 1 auto; padding: 4px 12px 16px; display: flex; flex-direction: column; gap: 18px; }
.csp-group { display: flex; flex-direction: column; gap: 4px; }
.csp-group-h {
  padding: 6px 12px 2px;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .08em;
  color: #707881;
}
.dark .csp-group-h { color: #87929a; }

.csp-link {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 12px; border-radius: 12px;
  color: #3f4850; font-size: 14px; text-decoration: none; white-space: nowrap;
  transition: background .15s, color .15s;
}
.csp-link svg { width: 20px; height: 20px; flex: 0 0 auto; color: var(--c-primary); transition: transform .15s; }
.csp-link:hover { background: color-mix(in srgb, var(--c-primary) 8%, transparent); color: #131b2e; }
.csp-link:hover svg { transform: scale(1.1); }
/* finance / config group icons pick up the lighter blue accent */
.csp-group:not(:first-child) .csp-link svg { color: var(--c-secondary); }

.dark .csp-link { color: #bdc8d1; }
.dark .csp-link svg { color: currentColor; }
.dark .csp-link:hover { background: #272a34; color: #dfe2ee; }
.dark .csp-group:not(:first-child) .csp-link svg { color: currentColor; }

.csp-link.csp-active { background: var(--c-primary); color: #ffffff; font-weight: 600; }
.csp-link.csp-active svg { color: #ffffff; }
.dark .csp-link.csp-active {
  background: var(--c-primary); color: #ffffff; font-weight: 700;
  box-shadow: 0 0 24px color-mix(in srgb, var(--c-primary) 45%, transparent);
}
.dark .csp-link.csp-active svg { color: #ffffff; }

/* ---- mobile drawer ---- */
.csp-drawer-wrap { position: fixed; inset: 0; z-index: 60; visibility: hidden; }
.csp-drawer-wrap.open { visibility: visible; }
@media (min-width: 768px) { .csp-drawer-wrap { display: none; } }
.csp-drawer-bg { position: absolute; inset: 0; background: rgba(0,0,0,0.45); opacity: 0; transition: opacity .2s; }
.csp-drawer-wrap.open .csp-drawer-bg { opacity: 1; }
.csp-drawer {
  position: absolute; inset-block: 0; inset-inline-start: 0;
  width: 17rem; max-width: 82vw;
  display: flex; flex-direction: column;
  transform: translateX(-100%); transition: transform .25s ease;
}
.csp-drawer .csp-side { height: auto; flex: 1 1 auto; min-height: 0; }
[dir="rtl"] .csp-drawer { transform: translateX(100%); }
.csp-drawer-wrap.open .csp-drawer { transform: translateX(0); }

/* ---- desktop slim top bar (>=768px) ---- */
.csp-topbar {
  display: flex; align-items: center; gap: 8px; padding: 12px 16px; font-size: 13px;
  border-bottom: 1px solid var(--c-border);
}
@media (max-width: 767px) { .csp-topbar { display: none; } }
.dark .csp-topbar { border-bottom: 1px solid rgba(255,255,255,0.05); }
.csp-tb-btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  padding: 7px 11px; border-radius: 10px; cursor: pointer;
  border: 1px solid var(--c-border); background: #ffffff; color: #3f4850;
}
.csp-tb-btn:hover { border-color: var(--c-primary); color: var(--c-primary); }
.csp-tb-ico { padding: 7px; }
.csp-tb-ico svg { width: 17px; height: 17px; }
.dark .csp-tb-btn { border-color: rgba(255,255,255,0.08); background: #181c24; color: #bdc8d1; }
.dark .csp-tb-btn:hover { border-color: var(--c-secondary); color: var(--c-secondary); }
.csp-tb-user {
  margin-inline-start: auto; color: #707881;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.dark .csp-tb-user { color: #87929a; }

/* ---- drawer footer (theme / lang / logout — mobile only) ---- */
.csp-drawer-foot { padding: 12px; display: flex; flex-wrap: wrap; gap: 8px; border-top: 1px solid var(--c-border); background: #ffffff; }
.dark .csp-drawer-foot { border-top-color: rgba(255,255,255,0.06); background: rgba(10,14,22,0.94); }
.csp-df-btn {
  display: inline-flex; align-items: center; gap: 6px; padding: 8px 12px; border-radius: 10px; font-size: 13px; font-weight: 600;
  border: 1px solid var(--c-border); background: transparent; color: #3f4850; cursor: pointer;
}
.csp-df-btn svg { width: 16px; height: 16px; }
.csp-df-btn:hover { border-color: var(--c-primary); color: var(--c-primary); }
.dark .csp-df-btn { color: #bdc8d1; border-color: rgba(255,255,255,0.08); }
.csp-df-out { color: var(--c-danger); border-color: color-mix(in srgb, var(--c-danger) 30%, transparent); margin-inline-start: auto; }
.csp-df-out:hover { border-color: var(--c-danger); color: var(--c-danger); background: color-mix(in srgb, var(--c-danger) 10%, transparent); }

/* ================================================================= *
 *  MOBILE ADMIN SHELL (<=767px) — Stitch f10ea6b9 / 0197c0c0        *
 * ================================================================= */
.csp-mtop { display: none; }
.csp-botnav { display: none; }

@media (max-width: 767px) {
  /* --- top bar: hamburger · brand · online + avatar --- */
  .csp-mtop {
    display: flex; align-items: center; justify-content: space-between; gap: 8px;
    position: sticky; top: 0; z-index: 45;
    padding: 10px 14px;
    background: color-mix(in srgb, var(--c-surface) 96%, transparent);
    -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px);
    border-bottom: 1px solid var(--c-border);
  }
  .dark .csp-mtop { border-bottom-color: rgba(255,255,255,0.06); }

  .csp-mtop-burger {
    width: 38px; height: 38px; flex-shrink: 0; border-radius: 11px; cursor: pointer;
    display: grid; place-items: center; background: transparent; border: 0; color: var(--c-text);
  }
  .csp-mtop-burger svg { width: 22px; height: 22px; }
  .csp-mtop-burger:active { background: color-mix(in srgb, var(--c-primary) 10%, transparent); }

  .csp-mtop-brand { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .csp-mtop-logo {
    width: 34px; height: 34px; flex-shrink: 0; border-radius: 999px; overflow: hidden;
    display: grid; place-items: center; color: #fff; font-weight: 900; font-size: 14px;
    background: linear-gradient(135deg, var(--c-primary), color-mix(in srgb, var(--c-primary) 55%, #7cc6ff));
    box-shadow: 0 4px 12px -3px color-mix(in srgb, var(--c-primary) 45%, transparent);
  }
  .csp-mtop-logo img { width: 100%; height: 100%; object-fit: cover; }
  .csp-mtop-txt { display: flex; flex-direction: column; min-width: 0; line-height: 1.15; }
  .csp-mtop-txt b { font-size: 14px; font-weight: 800; color: var(--c-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .csp-mtop-txt span {
    font-family: 'JetBrains Mono', ui-monospace, monospace;
    font-size: 8.5px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: var(--c-primary);
  }

  .csp-mtop-end { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
  .csp-mtop-online {
    display: inline-flex; align-items: center; gap: 4px; white-space: nowrap;
    font-size: 10.5px; font-weight: 600; padding: 3px 8px; border-radius: 999px;
    background: color-mix(in srgb, var(--c-success) 14%, transparent); color: var(--c-success);
    border: 1px solid color-mix(in srgb, var(--c-success) 30%, transparent);
  }
  .csp-mtop-online i { width: 6px; height: 6px; border-radius: 50%; background: var(--c-success); }
  /* Stitch renders the avatar as a plain neutral circle, not a colour tile */
  .csp-mtop-avatar {
    width: 36px; height: 36px; flex-shrink: 0; border-radius: 999px;
    display: grid; place-items: center; font-weight: 700; font-size: 13px;
    color: var(--c-text);
    background: color-mix(in srgb, var(--c-text-muted) 16%, transparent);
    border: 1px solid var(--c-border);
  }

  /* --- bottom nav (Stitch f10ea6b9): grid of 5, active = DOT above the icon --- */
  .csp-botnav {
    position: fixed; inset-inline: 0; bottom: 0; z-index: 55;
    display: grid; grid-template-columns: repeat(var(--csp-bn-n, 5), 1fr); align-items: center;
    padding: 8px 8px calc(8px + env(safe-area-inset-bottom, 0px));
    background: color-mix(in srgb, var(--c-surface) 96%, transparent);
    -webkit-backdrop-filter: blur(16px); backdrop-filter: blur(16px);
    border-top: 1px solid var(--c-border);
    box-shadow: 0 -8px 24px -10px rgba(15, 23, 42, .14);
  }
  .csp-content { padding-bottom: 82px; }
}
.dark .csp-botnav { border-top-color: rgba(255,255,255,0.07); }

.csp-bn-item {
  position: relative; min-width: 0;
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding: 4px 2px; background: none; border: 0; cursor: pointer;
  color: var(--c-text-muted); text-decoration: none; transition: color .15s;
}
.csp-bn-item svg { width: 24px; height: 24px; color: currentColor; stroke-width: 1.8; transition: stroke-width .15s; }
.csp-bn-t { font-size: 10px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
.csp-bn-dot {
  position: absolute; top: -3px; left: 50%; transform: translateX(-50%);
  width: 6px; height: 6px; border-radius: 999px; background: var(--c-primary);
  opacity: 0; transition: opacity .15s;
}
.csp-bn-item.on { color: var(--c-primary); }
.csp-bn-item.on svg { stroke-width: 2.2; }
.csp-bn-item.on .csp-bn-t { font-weight: 800; }
.csp-bn-item.on .csp-bn-dot { opacity: 1; }
`
