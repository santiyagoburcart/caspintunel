import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { useLivePayments } from '../lib/livePayments'
import { useI18n } from '../lib/i18n'
import { useTheme } from '../theme/ThemeProvider'
import { CASPIAN_BOTNAV, CASPIAN_GROUPS, NAV_ICONS } from './adminNav'

// Aurora / Royal Frost — the original flat nav (kept exactly as-is).
const nav = [
  ['/', 'dashboard', null],
  ['/users', 'users', 'users.view'],
  ['/agency', 'agency', 'agency.view'],
  ['/services', 'services', 'monitoring.view'],
  ['/plans', 'plans', 'plans.manage'],
  ['/payments', 'payments', 'payment.view'],
  ['/transactions', 'transactions', 'payment.view'],
  ['/sms-log', 'sms_log', 'payment.view'],
  ['/accounting', 'accounting', 'accounting.view'],
  ['/cards', 'cards', 'payment.view'],
  ['/monitoring', 'monitoring', 'monitoring.view'],
  ['/panel-link', 'panel_link', 'settings.manage'],
  ['/bots', 'bots', 'bots.manage'],
  ['/apps', 'apps', 'settings.manage'],
  ['/branding', 'branding', 'settings.manage'],
  ['/settings', 'settings', 'settings.manage'],
  ['/settings/email', 'email_settings', 'settings.email'],
  ['/settings/paths', 'paths', 'settings.manage'],
  ['/notifications', 'notifications', 'broadcast.send'],
  ['/pages', 'pages', 'pages.manage'],
  ['/themes', 'themes', 'themes.manage'],
  ['/roles', 'roles', 'roles.manage'],
  ['/docs', 'docs', 'settings.manage'],
]

function SideIcon({ name }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.7"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={NAV_ICONS[name] || NAV_ICONS.dashboard} />
    </svg>
  )
}

// ---- Aurora / Frost sidebar (unchanged) ----
/** live pending-payments count on the Payments nav entry */
function PendingBadge({ to }) {
  const { pendingCount } = useLivePayments()
  if (to !== '/payments' || !pendingCount) return null
  return <span className="nav-pending-badge" aria-label={`${pendingCount}`}>{pendingCount > 99 ? '99+' : pendingCount}</span>
}

function NavLinks({ items, t, onNavigate }) {
  return (
    <nav className="flex flex-col gap-1">
      {items.map(([to, key]) => (
        <NavLink key={to} to={to} end onClick={onNavigate}
          className={({ isActive }) =>
            `admin-nav-link btn-ghost whitespace-nowrap text-sm flex items-center justify-between gap-2 ${isActive ? 'active-nav text-primary' : ''}`}>
          {t(key)}
          <PendingBadge to={to} />
        </NavLink>
      ))}
    </nav>
  )
}

// ---- collapsible desktop sidebar (≥768px; phones keep the bottom nav) -----------------
// ≥1280px: docked, toggled by ☰, remembered per browser. 768–1279px: starts closed and
// opens as an overlay drawer (tap outside / Esc / picking a page closes it).
const NAV_KEY = 'cta_nav_open'
const WIDE_Q = '(min-width: 1280px)'
function useSideNav() {
  const [wide, setWide] = useState(() => typeof window !== 'undefined' && window.matchMedia(WIDE_Q).matches)
  const [docked, setDocked] = useState(() => { try { return localStorage.getItem(NAV_KEY) !== '0' } catch { return true } })
  const [drawer, setDrawer] = useState(false)
  useEffect(() => {
    const mq = window.matchMedia(WIDE_Q)
    const on = () => { setWide(mq.matches); setDrawer(false) }
    mq.addEventListener ? mq.addEventListener('change', on) : mq.addListener(on)
    return () => { mq.removeEventListener ? mq.removeEventListener('change', on) : mq.removeListener(on) }
  }, [])
  const open = wide ? docked : drawer
  const toggle = useCallback(() => {
    if (wide) setDocked((v) => { const n = !v; try { localStorage.setItem(NAV_KEY, n ? '1' : '0') } catch { /* private mode */ } return n })
    else setDrawer((v) => !v)
  }, [wide])
  const closeDrawer = useCallback(() => setDrawer(false), [])
  useEffect(() => {                      // Esc closes the overlay drawer
    if (wide || !drawer) return undefined
    const k = (e) => { if (e.key === 'Escape') setDrawer(false) }
    document.addEventListener('keydown', k)
    return () => document.removeEventListener('keydown', k)
  }, [wide, drawer])
  return { wide, open, overlay: !wide && drawer, toggle, closeDrawer }
}

// hidden sidebar must not be reachable with Tab / screen readers
function useInert(ref, inert) {
  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (inert) el.setAttribute('inert', ''); else el.removeAttribute('inert')
  }, [ref, inert])
}

function MenuButton({ open, onClick, t, className }) {
  return (
    <button type="button" className={className} onClick={onClick} aria-expanded={open} aria-controls="admin-sidebar"
      aria-label={open ? t('menu_close') : t('menu_open')} title={open ? t('menu_close') : t('menu_open')}>
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
        <path d="M4 6h16M4 12h16M4 18h16" />
      </svg>
    </button>
  )
}

function LegacyLayout() {
  const { staff, logout, can } = useAuth()
  const { t, lang, setLang } = useI18n()
  const { mode, toggle, locked, config } = useTheme()
  const go = useNavigate()
  const [open, setOpen] = useState(false)
  const side = useSideNav()
  const closeAll = () => { setOpen(false); side.closeDrawer() }

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
      <aside id="admin-sidebar" className={`admin-side glass m-3 hidden w-56 shrink-0 self-start overflow-y-auto p-3 ${side.wide && side.open ? 'md:block' : ''}`}>
        <Brand />
        <NavLinks items={items} t={t} />
      </aside>

      {/* mobile drawer */}
      {(open || side.overlay) && (
        <div className={`fixed inset-0 z-30 ${side.overlay ? '' : 'md:hidden'}`} onClick={closeAll}>
          <div className="absolute inset-0 bg-black/40" />
          <aside
            className="admin-side glass absolute inset-y-0 start-0 w-64 max-w-[80vw] overflow-y-auto p-3"
            onClick={(e) => e.stopPropagation()}
          >
            <Brand>
              <button className="btn-ghost ms-auto shrink-0" onClick={closeAll} aria-label={t('menu_close')}>✕</button>
            </Brand>
            <NavLinks items={items} t={t} onNavigate={closeAll} />
          </aside>
        </div>
      )}

      <div className="min-w-0 flex-1">
        <header className="glass m-3 flex items-center gap-2 px-3 py-2 text-sm sm:px-4">
          <button className="btn-ghost shrink-0 md:hidden" onClick={() => setOpen(true)} aria-label={t('menu_open')} aria-expanded={open}>☰</button>
          <MenuButton className="btn-ghost shrink-0 hidden md:inline-flex" open={side.open} onClick={side.toggle} t={t} />
          {/* the active theme can lock the whole site to one mode (e.g. Royal Frost is light-only) */}
          {!locked && (
            <button className="btn-ghost shrink-0 hidden md:inline-flex" onClick={toggle}>{mode === 'dark' ? '☀️' : '🌙'}</button>
          )}
          <button className="btn-ghost shrink-0" onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}>{lang === 'fa' ? 'EN' : 'فا'}</button>
          <span className="ms-auto truncate text-muted">
            {staff?.username}{staff?.role ? ` · ${staff.role}` : staff?.is_superadmin ? ' · superadmin' : ''}
          </span>
          <button className="btn-ghost shrink-0" onClick={() => { logout(); go('/login') }}>{t('logout')}</button>
        </header>
        <main className={`admin-main mx-auto max-w-6xl p-3`}><Outlet /></main>
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

// inner-page titles for the mobile top bar (first match wins, so sub-paths go first)
const MOBILE_TITLES = [
  ['/settings/email', 'email_settings'], ['/settings/paths', 'paths'],
  ['/users/deleted', 'deleted_users'], ['/users', 'users'], ['/agency', 'agency'], ['/services', 'services'], ['/plans', 'plans'],
  ['/payments', 'nav_pay_queue'], ['/transactions', 'transactions'], ['/sms-log', 'sms_log'], ['/accounting', 'accounting'],
  ['/cards', 'cards'], ['/monitoring', 'monitoring'], ['/panel-link', 'panel_link'], ['/bots', 'bots'],
  ['/branding', 'branding'], ['/apps', 'apps'], ['/settings', 'settings'], ['/notifications', 'notifications'],
  ['/pages', 'pages'], ['/themes', 'themes'], ['/roles', 'roles'], ['/docs', 'docs'],
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
  const side = useSideNav()
  const railRef = useRef(null)
  useInert(railRef, !side.open)

  const groups = CASPIAN_GROUPS.map(([g, items]) => [g, items.filter(([, , p]) => !p || can(p))])
  const botnav = CASPIAN_BOTNAV.filter(([, , p]) => !p || can(p))
  const brand = (lang === 'fa' ? config?.site_name_fa : config?.site_name_en)
    || (lang === 'fa' ? 'کسپین تانل' : 'Caspian Tunnel')
  const tab = activeTab(pathname)
  // inner page (anything that isn't a bottom-tab root, or a settings section) → back + title
  const inner = !TAB_ROOTS.has(pathname)
  const titleHit = MOBILE_TITLES.find(([pre]) => pathname === pre || pathname.startsWith(pre + '/')) || []
  // /settings/<form section> → that section's name; email & paths are their own pages
  const settingsSection = pathname.startsWith('/settings/') && !titleHit[0]?.startsWith('/settings/') ? pathname.slice(10) : ''
  const titleKey = settingsSection ? `sec_${settingsSection.replace(/-/g, '_')}` : titleHit[1]
  const back = () => {
    if (window.history.state?.idx > 0) go(-1)
    else go(tab === '/settings' && pathname !== '/settings' ? '/settings' : tab)
  }

  return (
    <div className={`csp-shell ${side.open ? 'nav-open' : 'nav-closed'}${side.wide ? '' : ' nav-overlay'}`}>
      <style>{CASPIAN_CSS}</style>

      {/* desktop rail — start side (right for fa/RTL, left for en/LTR); collapsible with ☰ */}
      <aside className="csp-rail" id="admin-sidebar" ref={railRef} aria-label={t('menu_open')}>
        <CaspianNav groups={groups} t={t} brand={brand} logo={config?.logo} onNavigate={side.wide ? undefined : side.closeDrawer} />
      </aside>
      {side.overlay && <div className="csp-backdrop" onClick={side.closeDrawer} aria-hidden="true" />}

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
          <MenuButton className="csp-tb-btn csp-tb-ico csp-tb-menu" open={side.open} onClick={side.toggle} t={t} />
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

        <main className={`csp-content admin-main mx-auto max-w-6xl p-3`}><Outlet /></main>
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
                <SideIcon name={icon} />
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
/* collapsible sidebar: closed = off-canvas (content takes the width); <1280px = overlay drawer */
@media (min-width: 768px) {
  .csp-rail { transition: transform .24s ease, visibility .24s; }
  .csp-main { transition: padding-inline-start .24s ease; }
  .csp-shell.nav-closed .csp-rail { transform: translateX(-100%); visibility: hidden; }
  [dir="rtl"] .csp-shell.nav-closed .csp-rail { transform: translateX(100%); }
  .csp-shell.nav-closed .csp-main, .csp-shell.nav-overlay .csp-main { padding-inline-start: 0; }
  .csp-shell.nav-overlay.nav-open .csp-rail { box-shadow: 0 12px 48px rgb(0 0 0 / .28); }
  .csp-backdrop { position: fixed; inset: 0; z-index: 39; background: rgb(0 0 0 / .35); }
  .csp-tb-menu:focus-visible { outline: 2px solid var(--c-primary); outline-offset: 2px; }
}
@media (prefers-reduced-motion: reduce) { .csp-rail, .csp-main { transition: none !important; } }

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
  .csp-mtop-lang {
    font-size: 11px; font-weight: 700; padding: 5px 9px; border-radius: 8px;
    border: 1px solid var(--c-border); background: transparent; color: var(--c-text-muted);
  }
  .csp-mtop-ico { display: grid; place-items: center; padding: 5px; width: 30px; height: 28px; }
  .csp-mtop-ico svg { width: 16px; height: 16px; }
  .csp-mtop-brand { text-decoration: none; }
  .csp-mtop-inner { gap: 6px; }
  .csp-mtop-title { font-size: 15px; font-weight: 800; color: var(--c-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .csp-mtop-back { width: 36px; height: 36px; flex-shrink: 0; display: grid; place-items: center; border-radius: 11px;
    border: 1px solid var(--c-border); background: transparent; color: var(--c-text); }
  .csp-mtop-back svg { width: 18px; height: 18px; }
  [dir="ltr"] .csp-mtop-back svg { transform: scaleX(-1); }
  .csp-mtop-lang:active { background: color-mix(in srgb, var(--c-primary) 10%, transparent); color: var(--c-primary); }
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
.csp-bn-ico { position: relative; display: grid; place-items: center; }
.csp-bn-badge { position: absolute; top: -6px; inset-inline-end: -10px; min-width: 18px; height: 18px; padding: 0 5px;
  border-radius: 999px; background: color-mix(in srgb, var(--c-danger) 70%, #000); color: #fff; font-size: 10px; font-weight: 800; line-height: 18px;
  text-align: center; box-shadow: 0 0 0 2px var(--c-surface); }
/* raised centre tab (payments queue) */
.csp-bn-centre .csp-bn-ico { width: 50px; height: 50px; margin-top: -26px; border-radius: 999px; color: #fff;
  background: linear-gradient(135deg, var(--c-primary), color-mix(in srgb, var(--c-primary) 60%, #7cc6ff));
  box-shadow: 0 8px 18px -6px color-mix(in srgb, var(--c-primary) 60%, transparent), 0 0 0 4px var(--c-surface); }
.csp-bn-centre .csp-bn-ico svg { width: 24px; height: 24px; }
.csp-bn-centre .csp-bn-dot { display: none; }
.csp-bn-centre.on .csp-bn-ico { box-shadow: 0 8px 18px -6px color-mix(in srgb, var(--c-primary) 70%, transparent), 0 0 0 4px var(--c-surface), 0 0 0 6px color-mix(in srgb, var(--c-primary) 35%, transparent); }
.csp-bn-centre .csp-bn-badge { top: -4px; inset-inline-end: -4px; }
.csp-bn-item.on { color: var(--c-primary); }
.csp-bn-item.on svg { stroke-width: 2.2; }
.csp-bn-item.on .csp-bn-t { font-weight: 800; }
.csp-bn-item.on .csp-bn-dot { opacity: 1; }
`
