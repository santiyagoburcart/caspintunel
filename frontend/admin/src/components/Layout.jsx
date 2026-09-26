import { useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  Lightning, Sun, Moon, CaretRight, DeviceMobile, SquaresFour, Pulse, UsersThree, Tag, PlugsConnected,
  Robot, Wallet, ArrowsLeftRight, ChartBar, CreditCard, Stack, PaintBrush, SlidersHorizontal, FileText,
  Palette, ShieldCheck, EnvelopeSimple, Bell, List, X, SignOut,
} from '@phosphor-icons/react'
import { useAuth } from '../lib/auth'
import { useLivePayments } from '../lib/livePayments'
import { useI18n } from '../lib/i18n'
import { useTheme } from '../theme/ThemeProvider'

// Aurora / Royal Frost — the original flat nav (kept exactly as-is).
const nav = [
  ['/', 'dashboard', null],
  ['/users', 'users', 'users.view'],
  ['/services', 'services', 'monitoring.view'],
  ['/plans', 'plans', 'plans.manage'],
  ['/payments', 'payments', 'payment.view'],
  ['/transactions', 'transactions', 'payment.view'],
  ['/accounting', 'accounting', 'accounting.view'],
  ['/cards', 'cards', 'payment.view'],
  ['/monitoring', 'monitoring', 'monitoring.view'],
  ['/panel-link', 'panel_link', 'settings.manage'],
  ['/bots', 'bots', 'bots.manage'],
  ['/apps', 'apps', 'settings.manage'],
  ['/branding', 'branding', 'settings.manage'],
  ['/settings', 'settings', 'settings.manage'],
  ['/settings/email', 'email_settings', 'settings.email'],
  ['/notifications', 'notifications', 'broadcast.send'],
  ['/pages', 'pages', 'pages.manage'],
  ['/themes', 'themes', 'themes.manage'],
  ['/roles', 'roles', 'roles.manage'],
]

// Caspian — the same 16 real routes, arranged into the Stitch reference's
// grouped sections ([route, i18n-key, permission, icon]).
const CASPIAN_GROUPS = [
  ['nav_group_core', [
    ['/', 'dashboard', null, 'dashboard'],
    ['/monitoring', 'monitoring', 'monitoring.view', 'monitoring'],
    ['/panel-link', 'panel_link', 'settings.manage', 'panel'],
  ]],
  ['nav_group_users', [
    ['/users', 'users', 'users.view', 'users'],
    ['/services', 'services', 'monitoring.view', 'services'],
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
    ['/settings/email', 'email_settings', 'settings.email', 'mail'],
    ['/bots', 'bots', 'bots.manage', 'bots'],
    ['/apps', 'apps', 'settings.manage', 'apps'],
    ['/notifications', 'notifications', 'broadcast.send', 'notifications'],
    ['/pages', 'pages', 'pages.manage', 'pages'],
    ['/themes', 'themes', 'themes.manage', 'themes'],
    ['/roles', 'roles', 'roles.manage', 'roles'],
  ]],
]

// Phosphor Icons (MIT, bundled — no icon font / CDN), one family everywhere.
const NAV_ICONS = {
  brand: Lightning, sun: Sun, moon: Moon, back: CaretRight, apps: DeviceMobile, dashboard: SquaresFour,
  monitoring: Pulse, users: UsersThree, plans: Tag, panel: PlugsConnected, bots: Robot, payments: Wallet,
  transactions: ArrowsLeftRight, accounting: ChartBar, cards: CreditCard, services: Stack, branding: PaintBrush,
  settings: SlidersHorizontal, pages: FileText, themes: Palette, roles: ShieldCheck, mail: EnvelopeSimple,
  notifications: Bell,
}

function SideIcon({ name, weight = 'regular', size = 20 }) {
  const Icon = NAV_ICONS[name] || SquaresFour
  return <Icon size={size} weight={weight} aria-hidden="true" />
}

// ---- Aurora / Frost sidebar (unchanged) ----
/** live pending-payments count on the Payments nav entry */
function PendingBadge({ to }) {
  const { pendingCount } = useLivePayments()
  if (to !== '/payments' || !pendingCount) return null
  return <span className="nav-pending-badge" aria-label={`${pendingCount}`}>{pendingCount > 99 ? '99+' : pendingCount}</span>
}

// route → icon name, shared by the Aurora/Frost nav and the Caspian groups
const NAV_ICON_OF = {
  '/': 'dashboard', '/users': 'users', '/services': 'services', '/plans': 'plans', '/payments': 'payments',
  '/transactions': 'transactions', '/accounting': 'accounting', '/cards': 'cards', '/monitoring': 'monitoring',
  '/panel-link': 'panel', '/bots': 'bots', '/apps': 'apps', '/branding': 'branding', '/settings': 'settings',
  '/settings/email': 'mail', '/notifications': 'notifications', '/pages': 'pages', '/themes': 'themes', '/roles': 'roles',
}

function NavLinks({ items, t, onNavigate }) {
  return (
    <nav className="flex flex-col gap-1">
      {items.map(([to, key]) => (
        <NavLink key={to} to={to} end onClick={onNavigate}
          className={({ isActive }) =>
            `admin-nav-link btn-ghost whitespace-nowrap text-sm flex items-center justify-start gap-2 ${isActive ? 'active-nav text-primary' : ''}`}>
          <SideIcon name={NAV_ICON_OF[to] || 'dashboard'} size={18} />
          <span className="min-w-0 flex-1 truncate text-start">{t(key)}</span>
          <PendingBadge to={to} />
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
              <button className="icon-btn ms-auto shrink-0" onClick={() => setOpen(false)} aria-label={t('close')}><X size={20} aria-hidden="true" /></button>
            </Brand>
            <NavLinks items={items} t={t} onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}

      <div className="min-w-0 flex-1">
        <header className="glass m-3 flex items-center gap-2 px-3 py-2 text-sm sm:px-4">
          <button className="icon-btn shrink-0 md:hidden" onClick={() => setOpen(true)} aria-label={t('menu')}><List size={22} aria-hidden="true" /></button>
          {/* the active theme can lock the whole site to one mode (e.g. Royal Frost is light-only) */}
          {!locked && (
            <button className="icon-btn shrink-0 hidden md:inline-grid" onClick={toggle} aria-label={mode === 'dark' ? t('light_mode') : t('dark_mode')}>
              {mode === 'dark' ? <Sun size={20} aria-hidden="true" /> : <Moon size={20} aria-hidden="true" />}
            </button>
          )}
          <button className="btn-ghost shrink-0" onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}>{lang === 'fa' ? 'EN' : 'فا'}</button>
          <span className="ms-auto truncate text-muted">
            {staff?.username}{staff?.role ? ` · ${staff.role}` : staff?.is_superadmin ? ' · superadmin' : ''}
          </span>
          <button className="btn-ghost shrink-0" onClick={() => { logout(); go('/login') }}>
            <SignOut size={18} aria-hidden="true" mirrored={lang === 'fa'} />{t('logout')}
          </button>
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
                <PendingBadge to={to} />
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
    </div>
  )
}

// mobile bottom-nav — exactly these 5 route tabs, matches Stitch f10ea6b9
// (DOM order; RTL flips it to Settings · Roles · Cards · Users · Dashboard,
// right→left). Any other route (panel, bots, monitoring, branding, themes,
// pages, notifications) is desktop-sidebar-only — there is no mobile drawer
// or "More" tab to reach them from a phone.
// mobile bottom nav — exactly 5 tabs; the payments queue is the raised centre
// button with a live pending badge. Everything else lives in the Settings
// index (pages/Settings.jsx → SettingsHub). [route, i18n-key, permission, icon, centre?]
const CASPIAN_BOTNAV = [
  ['/', 'dashboard', null, 'dashboard'],
  ['/users', 'users', 'users.view', 'users'],
  ['/payments', 'nav_pay_queue', 'payment.view', 'payments', true],
  ['/services', 'services', 'monitoring.view', 'services'],
  ['/settings', 'settings', null, 'settings'],
]

// inner-page titles for the mobile top bar (longest prefix wins)
const MOBILE_TITLES = [
  ['/users/deleted', 'deleted_users'], ['/users', 'users'], ['/services', 'services'], ['/plans', 'plans'],
  ['/payments', 'nav_pay_queue'], ['/transactions', 'transactions'], ['/accounting', 'accounting'],
  ['/cards', 'cards'], ['/monitoring', 'monitoring'], ['/panel-link', 'panel_link'], ['/bots', 'bots'],
  ['/branding', 'branding'], ['/apps', 'apps'], ['/settings', 'settings'], ['/notifications', 'notifications'],
  ['/pages', 'pages'], ['/themes', 'themes'], ['/roles', 'roles'],
]
const TAB_ROOTS = new Set(['/', '/users', '/payments', '/services', '/settings'])

/** which bottom tab a path belongs to — pages reached from the Settings index light up Settings */
function activeTab(path) {
  if (path === '/') return '/'
  for (const root of ['/users', '/payments', '/services']) {
    if (path === root || path.startsWith(root + '/')) return root
  }
  return '/settings'
}

function CaspianLayout() {
  const { staff, logout, can } = useAuth()
  const { t, lang, setLang } = useI18n()
  const { mode, toggle, locked, config } = useTheme()
  const { pendingCount } = useLivePayments()
  const go = useNavigate()
  const { pathname } = useLocation()

  const groups = CASPIAN_GROUPS.map(([g, items]) => [g, items.filter(([, , p]) => !p || can(p))])
  const botnav = CASPIAN_BOTNAV.filter(([, , p]) => !p || can(p))
  const brand = (lang === 'fa' ? config?.site_name_fa : config?.site_name_en)
    || (lang === 'fa' ? 'کسپین تانل' : 'Caspian Tunnel')
  const tab = activeTab(pathname)
  // inner page (anything that isn't a bottom-tab root, or a settings section) → back + title
  const inner = !TAB_ROOTS.has(pathname)
  const settingsSection = pathname.startsWith('/settings/') ? pathname.slice(10) : ''
  const titleKey = settingsSection ? `sec_${settingsSection.replace(/-/g, '_')}`
    : (MOBILE_TITLES.find(([pre]) => pathname === pre || pathname.startsWith(pre + '/')) || [])[1]
  const back = () => {
    if (window.history.state?.idx > 0) go(-1)
    else go(tab === '/settings' && pathname !== '/settings' ? '/settings' : tab)
  }

  return (
    <div className="csp-shell">
      <style>{CASPIAN_CSS}</style>

      {/* desktop rail — start side (right for fa/RTL, left for en/LTR) */}
      <aside className="csp-rail">
        <CaspianNav groups={groups} t={t} brand={brand} logo={config?.logo} />
      </aside>

      <div className="csp-main">
        {/* mobile top bar (≤767px): brand on tab roots, back + page title on
            inner pages; language + dark/light toggle always reachable */}
        <header className="csp-mtop">
          <div className="csp-mtop-end">
            {!locked && (
              <button type="button" className="csp-mtop-lang csp-mtop-ico" onClick={toggle}
                aria-label={mode === 'dark' ? t('light_mode') : t('dark_mode')}>
                <SideIcon name={mode === 'dark' ? 'sun' : 'moon'} />
              </button>
            )}
            <button type="button" className="csp-mtop-lang" onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}>
              {lang === 'fa' ? 'EN' : 'فا'}
            </button>
            {!inner && <span className="csp-mtop-avatar">{(staff?.username || '?').charAt(0).toUpperCase()}</span>}
          </div>
          {inner ? (
            <div className="csp-mtop-brand csp-mtop-inner">
              <b className="csp-mtop-title">{titleKey ? t(titleKey) : brand}</b>
              <button type="button" className="csp-mtop-back" onClick={back} aria-label={t('back')}>
                <SideIcon name="back" />
              </button>
            </div>
          ) : (
            <Link to="/" className="csp-mtop-brand">
              <div className="csp-mtop-txt">
                <b>{brand}</b>
                <span>ADMIN CONTROL</span>
              </div>
              <span className="csp-mtop-logo">
                {config?.logo ? <img src={config.logo} alt="" /> : <b>C</b>}
              </span>
            </Link>
          )}
        </header>

        {/* desktop top bar (≥768px) */}
        <header className="csp-topbar">
          {!locked && (
            <button className="csp-tb-btn csp-tb-ico" onClick={toggle} aria-label={mode === 'dark' ? t('light_mode') : t('dark_mode')}>
              <SideIcon name={mode === 'dark' ? 'sun' : 'moon'} />
            </button>
          )}
          <button className="csp-tb-btn" onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}>
            {lang === 'fa' ? 'EN' : 'فا'}
          </button>
          <span className="csp-tb-user">
            {staff?.username}{staff?.role ? ` · ${staff.role}` : staff?.is_superadmin ? ' · superadmin' : ''}
          </span>
          <button className="csp-tb-btn" onClick={() => { logout(); go('/login') }}>
            <SignOut size={17} aria-hidden="true" mirrored={lang === 'fa'} />{t('logout')}
          </button>
        </header>

        <main className="csp-content mx-auto max-w-6xl p-3"><Outlet /></main>
      </div>

      {/* mobile bottom nav (≤767px) — 5 tabs, the payments queue is the raised
          centre button with the live pending count */}
      <nav className="csp-botnav" style={{ '--csp-bn-n': botnav.length }}>
        {botnav.map(([to, key, , icon, centre]) => {
          const on = tab === to
          const badge = to === '/payments' && pendingCount > 0 ? pendingCount : null
          return (
            <NavLink key={to} to={to} end={to === '/'} aria-current={on ? 'page' : undefined}
              className={'csp-bn-item' + (on ? ' on' : '') + (centre ? ' csp-bn-centre' : '')}>
              <span className="csp-bn-dot" />
              <span className="csp-bn-ico">
                <SideIcon name={icon} size={24} weight={on || centre ? 'fill' : 'regular'} />
                {badge != null && <span className="csp-bn-badge">{badge > 99 ? '99+' : badge}</span>}
              </span>
              <span className="csp-bn-t">{t(key)}</span>
            </NavLink>
          )
        })}
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
  background: var(--c-surface-solid);
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
  background: color-mix(in srgb, var(--c-primary) 12%, #ffffff); color: var(--c-primary-fg);
}
.csp-brand-ico img { width: 100%; height: 100%; object-fit: contain; }
.csp-brand-ico svg { width: 22px; height: 22px; }
.dark .csp-brand-ico {
  background: rgba(39,42,52,0.6); color: var(--c-secondary-fg);
  box-shadow: inset 1px 1px 1px rgba(255,255,255,0.1), 0 4px 12px color-mix(in srgb, var(--c-primary) 30%, transparent);
}
.csp-brand-txt { display: flex; flex-direction: column; min-width: 0; line-height: 1.35; }
.csp-brand-name b { font-size: 16px; font-weight: 800; letter-spacing: -.01em; color: var(--c-primary-fg); }
.dark .csp-brand-name b { color: #dfe2ee; }
.csp-brand-sub {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 12px; font-weight: 500; letter-spacing: .02em; color: var(--c-text-muted);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}


/* ---- grouped nav ---- */
.csp-nav { flex: 1 1 auto; padding: 4px 12px 16px; display: flex; flex-direction: column; gap: 18px; }
.csp-group { display: flex; flex-direction: column; gap: 4px; }
.csp-group-h {
  padding: 6px 12px 2px;
  font-size: 12px; font-weight: 700; letter-spacing: .04em;
  color: var(--c-text-muted);
}

.csp-link {
  display: flex; align-items: center; gap: 12px; min-height: 44px;
  padding: 10px 12px; border-radius: var(--r-md);
  color: var(--csp-text-2); font-size: 14px; font-weight: 500; text-decoration: none; white-space: nowrap;
  transition: background var(--dur-1), color var(--dur-1);
}
.csp-link svg { width: 20px; height: 20px; flex: 0 0 auto; color: var(--c-primary-fg); transition: transform var(--dur-2) var(--ease-out); }
.csp-link:hover { background: var(--c-primary-soft); color: var(--c-text); }
.csp-link:hover svg { transform: scale(1.1); }
/* finance / config group icons pick up the lighter blue accent */
.csp-group:not(:first-child) .csp-link svg { color: var(--c-secondary-fg); }

.dark .csp-link svg { color: var(--c-primary-fg); }
.dark .csp-link:hover { background: var(--c-hover); color: var(--c-text); }
.dark .csp-group:not(:first-child) .csp-link svg { color: currentColor; }

.csp-link.csp-active { background: var(--c-primary); color: #ffffff; font-weight: 600; }
.csp-link.csp-active svg { color: #ffffff; }
.dark .csp-link.csp-active {
  background: var(--c-primary); color: #ffffff; font-weight: 700;
  box-shadow: 0 0 24px color-mix(in srgb, var(--c-primary) 45%, transparent);
}
.dark .csp-link.csp-active svg { color: #ffffff; }

/* ---- desktop slim top bar (>=768px) ---- */
.csp-topbar {
  display: flex; align-items: center; gap: 8px; padding: 12px 16px; font-size: 13px;
  border-bottom: 1px solid var(--c-border);
}
@media (max-width: 767px) { .csp-topbar { display: none; } }
.dark .csp-topbar { border-bottom: 1px solid rgba(255,255,255,0.05); }
.csp-tb-btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 40px; min-width: 40px;
  padding: 7px 12px; border-radius: var(--r-md); cursor: pointer; font-weight: 600;
  border: 1px solid var(--c-border); background: var(--c-surface-solid); color: var(--csp-text-2);
}
.csp-tb-btn:hover { border-color: var(--c-primary); color: var(--c-primary-fg); }
.csp-tb-ico { padding: 0; }
.csp-tb-ico svg { width: 17px; height: 17px; }
.dark .csp-tb-btn { border-color: var(--c-border); }
.dark .csp-tb-btn:hover { border-color: var(--c-secondary); color: var(--c-secondary-fg); }
.csp-tb-user {
  margin-inline-start: auto; color: var(--c-text-muted);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}


/* ================================================================= *
 *  MOBILE ADMIN SHELL (<=767px) — Stitch f10ea6b9 / 0197c0c0        *
 * ================================================================= */
.csp-mtop { display: none; }
.csp-botnav { display: none; }

@media (max-width: 767px) {
  /* --- top bar: hamburger · brand · online + avatar --- */
  .csp-mtop {
    display: flex; align-items: center; justify-content: space-between; gap: 8px;
    position: sticky; top: var(--preview-h, 0px); z-index: 45;
    padding: 8px 12px;
    background: color-mix(in srgb, var(--c-surface-solid) 94%, transparent);
    -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px);
    border-bottom: 1px solid var(--c-border);
  }
  .dark .csp-mtop { border-bottom-color: rgba(255,255,255,0.06); }

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
    font-size: 12px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--c-primary-fg);
  }

  .csp-mtop-end { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
  .csp-mtop-lang {
    min-width: 44px; height: 44px; font-size: 13px; font-weight: 700; padding: 0 10px; border-radius: var(--r-md);
    border: 1px solid var(--c-border); background: transparent; color: var(--csp-text-2);
  }
  .csp-mtop-ico { display: grid; place-items: center; padding: 0; width: 44px; }
  .csp-mtop-ico svg { width: 20px; height: 20px; }
  .csp-mtop-brand { text-decoration: none; }
  .csp-mtop-inner { gap: 6px; }
  .csp-mtop-title { font-size: 15px; font-weight: 800; color: var(--c-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .csp-mtop-back { width: 44px; height: 44px; flex-shrink: 0; display: grid; place-items: center; border-radius: var(--r-md);
    border: 1px solid var(--c-border); background: transparent; color: var(--c-text); }
  .csp-mtop-back svg { width: 20px; height: 20px; }
  [dir="ltr"] .csp-mtop-back svg { transform: scaleX(-1); }
  .csp-mtop-lang:active { background: color-mix(in srgb, var(--c-primary) 10%, transparent); color: var(--c-primary-fg); }
  .csp-mtop-online {
    display: inline-flex; align-items: center; gap: 4px; white-space: nowrap;
    font-size: 12px; font-weight: 600; padding: 3px 8px; border-radius: 999px;
    background: color-mix(in srgb, var(--c-success) 14%, transparent); color: var(--c-success-fg);
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
    padding: 6px 6px calc(6px + env(safe-area-inset-bottom, 0px));
    background: color-mix(in srgb, var(--c-surface-solid) 94%, transparent);
    -webkit-backdrop-filter: blur(16px); backdrop-filter: blur(16px);
    border-top: 1px solid var(--c-border);
    box-shadow: 0 -8px 24px -10px rgba(15, 23, 42, .14);
  }
  .csp-content { padding-bottom: calc(84px + env(safe-area-inset-bottom, 0px)); }
  :root { --bottomnav-h: calc(68px + env(safe-area-inset-bottom, 0px)); }
}
.dark .csp-botnav { border-top-color: rgba(255,255,255,0.07); }

.csp-bn-item {
  position: relative; min-width: 0; min-height: 56px; justify-content: center;
  display: flex; flex-direction: column; align-items: center; gap: 3px;
  padding: 4px 2px; background: none; border: 0; cursor: pointer; border-radius: var(--r-md);
  color: var(--c-text-muted); text-decoration: none; transition: color .15s;
}
.csp-bn-item svg { width: 24px; height: 24px; color: currentColor; stroke-width: 1.8; transition: stroke-width .15s; }
.csp-bn-t { font-size: 12px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
.csp-bn-dot {
  position: absolute; top: -3px; left: 50%; transform: translateX(-50%);
  width: 6px; height: 6px; border-radius: 999px; background: var(--c-primary);
  opacity: 0; transition: opacity .15s;
}
.csp-bn-ico { position: relative; display: grid; place-items: center; }
.csp-bn-badge { position: absolute; top: -6px; inset-inline-end: -10px; min-width: 20px; height: 20px; padding: 0 5px;
  border-radius: 999px; background: var(--c-danger); color: #fff; font-size: 12px; font-weight: 800; line-height: 20px;
  text-align: center; box-shadow: 0 0 0 2px var(--c-surface); }
/* raised centre tab (payments queue) */
.csp-bn-centre .csp-bn-ico { width: 50px; height: 50px; margin-top: -26px; border-radius: 999px; color: #fff;
  background: var(--c-primary);
  box-shadow: 0 8px 18px -6px color-mix(in srgb, var(--c-primary) 60%, transparent), 0 0 0 4px var(--c-surface-solid); }
.csp-bn-centre .csp-bn-ico svg { width: 24px; height: 24px; }
.csp-bn-centre .csp-bn-dot { display: none; }
.csp-bn-centre.on .csp-bn-ico { box-shadow: 0 8px 18px -6px color-mix(in srgb, var(--c-primary) 70%, transparent), 0 0 0 4px var(--c-surface), 0 0 0 6px color-mix(in srgb, var(--c-primary) 35%, transparent); }
.csp-bn-centre .csp-bn-badge { top: -4px; inset-inline-end: -4px; }
.csp-bn-item.on { color: var(--c-primary-fg); }
.csp-bn-item:active { background: var(--c-hover); }
.csp-bn-item.on .csp-bn-t { font-weight: 800; }
.csp-bn-item.on .csp-bn-dot { opacity: 1; }
`
