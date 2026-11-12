import { SoundButton } from './NotifySound'
import { fmtCount, useActionCounts } from '../lib/actionCounts'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { api } from '../lib/api'
import { useLivePayments } from '../lib/livePayments'
import { useLiveTickets } from '../lib/liveTickets'
import { useLiveApprovals } from '../lib/liveApprovals'
import { useI18n } from '../lib/i18n'
import { useTheme } from '../theme/ThemeProvider'
import { CASPIAN_BOTNAV, CASPIAN_GROUPS, GM_BOTNAV, GM_GROUPS, NAV_ICONS, STORE_BOTNAV, STORE_GROUPS, isGroupManager, isStoreMode } from './adminNav'
import { GmBell } from './GmBell'
import LogoutButton, { LOGOUT_CSS } from './LogoutButton'

// Aurora / Royal Frost — the original flat nav (kept exactly as-is).
const nav = [
  ['/', 'dashboard', null],
  ['/users', 'users', 'users.view'],
  ['/agency', 'agency', 'agency.view'],
  ['/tickets', 'tickets', 'tickets.view'],
  ['/crm', 'crm', 'crm.view'],
  ['/services', 'services', 'monitoring.view'],
  ['/plans', 'plans', 'plans.manage'],
  ['/payments', 'payments', 'payment.view'],
  ['/transactions', 'transactions', 'payment.view'],
  ['/sms-log', 'sms_log', 'payment.view'],
  ['/accounting', 'accounting', 'accounting.view'],
  ['/analytics', 'analytics', ['accounting.view', 'crm.view']],
  ['/cards', 'cards', 'payment.view'],
  ['/monitoring', 'monitoring', 'monitoring.view'],
  ['/panel-link', 'panel_link', 'settings.manage'],
  ['/bots', 'bots', 'bots.manage'],
  ['/apps', 'apps', 'settings.manage'],
  ['/branding', 'branding', 'settings.manage'],
  ['/settings', 'settings', 'settings.manage'],
  ['/settings/email', 'email_settings', 'settings.email'],
  ['/settings/paths', 'paths', 'settings.manage'],
  ['/settings/domain', 'domain_cf', 'superadmin'],
  ['/notifications', 'notifications', 'broadcast.send'],
  ['/pages', 'pages', 'pages.manage'],
  ['/themes', 'themes', 'themes.manage'],
  ['/roles', 'roles', 'roles.manage'],
  ['/tickets/topics', 'ticket_topics', ['tickets.view', 'tickets.manage_topics']],
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
  const n = useActionCounts()[to] || 0
  if (!n) return null
  return <span className="nav-pending-badge" aria-label={`${n}`}>{fmtCount(n)}</span>
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
    const phone = window.matchMedia('(max-width: 767px)')
    const on = () => { setWide(mq.matches); setDrawer(false) }
    for (const q of [mq, phone]) q.addEventListener ? q.addEventListener('change', on) : q.addListener(on)
    return () => { for (const q of [mq, phone]) q.removeEventListener ? q.removeEventListener('change', on) : q.removeListener(on) }
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

// signed-in account + theme / language / logout — bottom of the desktop sidebar.
// On Caspian phones the same block lives in the Settings tab (staff: pages/Settings.jsx,
// group managers: GroupManager.jsx settings tab).
const roleLabel = (staff, lang) => (staff?.role ? ((lang === 'fa' && staff.role_fa) || staff.role)
  : staff?.is_superadmin ? (lang === 'fa' ? 'ابرمدیر' : 'superadmin') : '')

function SideAccount({ className = '' }) {
  const { staff, logout } = useAuth()
  const { t, lang, setLang } = useI18n()
  const { mode, toggle, locked } = useTheme()
  const go = useNavigate()
  return (
    <div className={'side-acc ' + className} data-testid="side-account">
      <div className="side-acc-who">
        <span className="side-acc-av">{(staff?.username || '?').charAt(0).toUpperCase()}</span>
        <span className="side-acc-txt"><b dir="ltr">{staff?.username}</b><small>{roleLabel(staff, lang)}</small></span>
      </div>
      <div className="side-acc-row">
        {!locked && (
          <button type="button" className="side-acc-btn" onClick={toggle} aria-label={mode === 'dark' ? t('light_mode') : t('dark_mode')}>
            <SideIcon name={mode === 'dark' ? 'sun' : 'moon'} /><span>{mode === 'dark' ? t('light_mode') : t('dark_mode')}</span>
          </button>
        )}
        <button type="button" className="side-acc-btn" onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}>
          <span>{lang === 'fa' ? 'English' : 'فارسی'}</span>
        </button>
      </div>
      <button type="button" className="side-acc-btn side-acc-out" onClick={() => { logout(); go('/login') }}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" /></svg>
        <span>{t('logout')}</span>
      </button>
    </div>
  )
}

// group managers' avatar (v1.38.1): just a link to their Settings — no dropdown; «خروج» lives at the bottom of
// the sidebar (desktop) and of the Settings tab (phones), behind a confirm (components/LogoutButton.jsx).
function AvatarLink({ to, compact = false }) {
  const { staff } = useAuth()
  const { t } = useI18n()
  return (
    <Link to={to} className="avm-btn" aria-label={t('settings')} title={t('settings')} data-testid="avatar-menu">
      <span className="side-acc-av">{(staff?.username || '?').charAt(0).toUpperCase()}</span>
      {!compact && <span className="avm-name" dir="ltr">{staff?.username}</span>}
    </Link>
  )
}

const SIDE_ACC_CSS = `
.avm { position: relative; }
.gm-side-out { margin-top: auto; padding: 12px; border-top: 1px solid var(--c-border); }
.avm-btn { text-decoration: none; }
.avm-btn { display: flex; align-items: center; gap: 8px; padding: 3px 10px 3px 3px; border-radius: 999px; border: 1px solid var(--c-border); background: transparent; color: var(--c-text); cursor: pointer; }
[dir="rtl"] .avm-btn { padding: 3px 3px 3px 10px; }
.avm-btn .side-acc-av { width: 28px; height: 28px; font-size: 12px; }
.csp-mtop .avm-btn { padding: 2px !important; }
/* phones: the menu spans the top bar (an avatar near the edge would push a 220px menu off screen) */
.csp-mtop .avm, .csp-mtop .csp-mtop-end { position: static; }
.csp-mtop .avm-btn .side-acc-av { width: 32px; height: 32px; font-size: 13px; }
.avm-name { font-size: 13px; font-weight: 600; max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.side-acc { margin-top: auto; padding: 12px; display: flex; flex-direction: column; gap: 8px; border-top: 1px solid var(--c-border); }
.side-acc-who { display: flex; align-items: center; gap: 10px; min-width: 0; }
.side-acc-av { width: 32px; height: 32px; flex-shrink: 0; border-radius: 999px; display: grid; place-items: center;
  font-weight: 800; font-size: 13px; color: #fff; background: var(--c-primary); }
.side-acc-txt { display: flex; flex-direction: column; min-width: 0; line-height: 1.2; }
.side-acc-txt b { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: start; }
.side-acc-txt small { font-size: 11px; color: var(--c-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.side-acc-row { display: flex; gap: 6px; }
.side-acc-row .side-acc-btn { flex: 1 1 0; justify-content: center; }
.side-acc-btn { display: flex; align-items: center; gap: 8px; min-height: 38px; padding: 7px 10px; border-radius: 10px;
  border: 1px solid var(--c-border); background: transparent; color: var(--c-text); font-size: 12.5px; font-weight: 600; cursor: pointer; }
.side-acc-btn svg { width: 16px; height: 16px; flex-shrink: 0; }
.side-acc-btn:hover { background: color-mix(in srgb, var(--c-primary) 8%, transparent); }
.side-acc-out { color: var(--c-danger); border-color: color-mix(in srgb, var(--c-danger) 35%, transparent); }
.side-acc-out:hover { background: color-mix(in srgb, var(--c-danger) 10%, transparent); }
`

function LegacyLayout() {
  const { staff, logout, can } = useAuth()
  const { t, lang, setLang } = useI18n()
  const { mode, toggle, locked, config } = useTheme()
  const go = useNavigate()
  const [open, setOpen] = useState(false)
  const side = useSideNav()
  const closeAll = () => { setOpen(false); side.closeDrawer() }

  // v1.51: a store's panel shows only the store's pages in every theme (the Caspian layout already did, since v1.44)
  const items = isGroupManager(staff) ? GM_GROUPS[0][1].filter(([, , p]) => !p || can(p))
    : isStoreMode(staff) ? STORE_GROUPS.flatMap(([, list]) => list).filter(([, , p]) => !p || can(p))
      : nav.filter(([, , p]) => !p || can(p))
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
      <style>{SIDE_ACC_CSS + LOGOUT_CSS}</style>
      {/* desktop sidebar — always visible from md up */}
      <aside id="admin-sidebar" className={`admin-side glass m-3 hidden w-56 shrink-0 self-start overflow-y-auto p-3 ${side.wide && side.open ? 'md:block' : ''}`}>
        <Brand />
        <NavLinks items={items} t={t} />
        {!isGroupManager(staff) && <SideAccount className="mt-3" />}
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
            {!isGroupManager(staff) && <SideAccount className="mt-3" />}
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
          {!isGroupManager(staff) && <SoundButton className="btn-ghost shrink-0" />}
          <span className="ms-auto min-w-0 truncate text-muted">
            {staff?.username}{staff?.role ? ` · ${(lang === 'fa' && staff.role_fa) || staff.role}` : staff?.is_superadmin ? ` · ${lang === 'fa' ? 'ابرمدیر' : 'superadmin'}` : ''}
          </span>
          <button className="btn-ghost shrink-0" onClick={() => { logout(); go('/login') }}>{t('logout')}</button>
        </header>
        <main className={`admin-main mx-auto max-w-6xl p-3`}><Outlet /></main>
      </div>
    </div>
  )
}

// v1.57 desktop sidebar accordion: only the section of the current page is open at first; each open / closed choice is
// remembered per staff member (server: auth/me/prefs `nav_open`; localStorage only for an instant first paint) and the section
// you navigate into always opens. A collapsed header shows the sum of its pages' badges. Phones never see this rail.
function sectionOf(groups, path) {
  const hit = groups.find(([, items]) => items.some(([to]) => to === path || (to !== '/' && path.startsWith(to + '/'))))
  return hit ? hit[0] : null
}
function useNavAccordion(groups, withPrefs) {
  const { staff } = useAuth()
  const { pathname } = useLocation()
  const key = `ct_nav_open:${staff?.id ?? 'x'}`
  const enabled = groups.filter(([, items]) => items.length > 0).length > 1
  const [saved, setSaved] = useState(() => { try { return JSON.parse(localStorage.getItem(key) || 'null') } catch { return null } })
  const active = sectionOf(groups, pathname)
  useEffect(() => {
    if (!withPrefs || !staff) return
    api.get('/admin/auth/me/prefs/').then((r) => {
      const v = r.data?.nav_open
      if (v && typeof v === 'object') { setSaved(v); try { localStorage.setItem(key, JSON.stringify(v)) } catch { /* private mode */ } }
    }).catch(() => {})
  }, [staff?.id])
  const store = (v) => {
    setSaved(v)
    try { localStorage.setItem(key, JSON.stringify(v)) } catch { /* private mode */ }
    if (withPrefs) api.patch('/admin/auth/me/prefs/', { nav_open: v }, { quiet: true }).catch(() => {})
  }
  // navigating into a section opens it (and remembers that)
  useEffect(() => {
    if (enabled && active && saved && saved[active] === false) store({ ...saved, [active]: true })
  }, [active])
  const isOpen = (g) => (saved && g in saved ? !!saved[g] : g === active)
  const toggle = (g) => {
    const base = saved || Object.fromEntries(groups.map(([k]) => [k, k === active]))
    store({ ...base, [g]: !isOpen(g) })
  }
  return { enabled, isOpen, toggle }
}

// ---- Caspian sidebar (Stitch _9 dark "Caspian Tunnel" / _10 light "Azure Telemetry") ----
function CaspianNav({ groups, t, brand, logo, onNavigate, account = true, gmLogout = false, store = false }) {
  const acc = useNavAccordion(groups, !gmLogout)
  const counts = useActionCounts()
  return (
    <div className="csp-side">
      <div className="csp-brand">
        <span className="csp-brand-ico">
          {logo ? <img src={logo} alt="" /> : <SideIcon name="brand" />}
        </span>
        <div className="csp-brand-txt">
          <span className="csp-brand-name"><b>{brand}</b></span>
          <span className="csp-brand-sub">{t(store ? 'brand_store' : 'brand_core')}</span>
        </div>
      </div>
      <nav className="csp-nav">
        {groups.map(([gkey, items]) => {
          if (items.length === 0) return null
          const on = !acc.enabled || acc.isOpen(gkey)
          const sum = items.reduce((n, [to]) => n + (counts[to] || 0), 0)
          const id = `nav-sec-${gkey}`
          return (
            <div className="csp-group" key={gkey} data-open={on || undefined}>
              {acc.enabled ? (
                <button type="button" className="csp-group-h csp-group-btn" aria-expanded={on} aria-controls={id}
                  onClick={() => acc.toggle(gkey)} data-testid={`nav-sec-${gkey}`}>
                  <span>{t(gkey)}</span>
                  {!on && sum > 0 && <span className="nav-pending-badge csp-group-badge" aria-label={`${sum}`}>{fmtCount(sum)}</span>}
                  <svg className="csp-group-chev" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2"
                    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
                </button>
              ) : <div className="csp-group-h">{t(gkey)}</div>}
              {on && (
                <div className="csp-group-items" id={id}>
                  {items.map(([to, key, , icon]) => (
                    <NavLink key={to} to={to} end onClick={onNavigate}
                      className={({ isActive }) => 'csp-link' + (isActive ? ' csp-active' : '')}>
                      <SideIcon name={icon} />
                      <span className="csp-link-t">{t(key)}</span>
                      <PendingBadge to={to} />
                    </NavLink>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </nav>
      {account && <SideAccount className="csp-acc" />}
      {gmLogout && <div className="csp-acc gm-side-out"><LogoutButton testId="gm-side-logout" /></div>}
    </div>
  )
}

// inner-page titles for the mobile top bar (first match wins, so sub-paths go first)
const MOBILE_TITLES = [
  ['/settings/email', 'email_settings'], ['/settings/paths', 'paths'], ['/settings/domain', 'domain_short'],
  ['/tickets/topics', 'ticket_topics'], ['/tickets', 'tickets'], ['/crm', 'crm'], ['/analytics', 'analytics'],
  ['/users/deleted', 'deleted_users'], ['/users', 'users'], ['/agency', 'agency'], ['/services', 'services'], ['/plans', 'plans'],
  ['/payments', 'nav_pay_queue'], ['/transactions', 'transactions'], ['/sms-log', 'sms_log'], ['/accounting', 'accounting'],
  ['/cards', 'cards'], ['/discounts', 'discounts'], ['/monitoring', 'monitoring'], ['/panel-link', 'panel_link'], ['/bots', 'bots'],
  ['/branding', 'branding'], ['/apps', 'apps'], ['/settings', 'settings'], ['/notifications', 'notifications'],
  ['/pages', 'pages'], ['/themes', 'themes'], ['/roles', 'roles'], ['/docs', 'docs'], ['/backup', 'store_backup'],
  ['/my-groups/notifications', 'gm_notifications'],
]
const TAB_ROOTS = new Set(['/', '/users', '/payments', '/services', '/settings',
  '/my-groups', '/my-groups/accounting', '/my-groups/invoices', '/my-groups/activity', '/my-groups/settings'])   // group-manager tabs

/** which bottom tab a path belongs to — pages reached from the Settings index light up Settings */
function activeTab(path) {
  if (path === '/') return '/'
  if (path.startsWith('/my-groups')) return GM_BOTNAV.find(([to]) => to === path)?.[0] || '/my-groups'
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
  const { badge: ticketBadge } = useLiveTickets()
  const { pending: approvals } = useLiveApprovals()
  const go = useNavigate()
  const { pathname } = useLocation()
  const side = useSideNav()
  const railRef = useRef(null)
  useInert(railRef, !side.open)

  const gm = isGroupManager(staff)
  const store = isStoreMode(staff)
  const groups = (gm ? GM_GROUPS : store ? STORE_GROUPS : CASPIAN_GROUPS).map(([g, items]) => [g, items.filter(([, , p]) => !p || can(p))])
  const botnav = (gm ? GM_BOTNAV : store ? STORE_BOTNAV : CASPIAN_BOTNAV).filter(([, , p]) => !p || can(p))
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
      <style>{SIDE_ACC_CSS}</style>

      {/* desktop rail — start side (right for fa/RTL, left for en/LTR); collapsible with ☰ */}
      <aside className="csp-rail" id="admin-sidebar" ref={railRef} aria-label={t('menu_open')}>
        <CaspianNav groups={groups} t={t} brand={brand} logo={config?.logo} onNavigate={side.wide ? undefined : side.closeDrawer} account={!gm} gmLogout={gm} store={store} />
      </aside>
      {side.overlay && <div className="csp-backdrop" onClick={side.closeDrawer} aria-hidden="true" />}

      <div className="csp-main">
        {/* mobile top bar (≤767px): brand on tab roots, back + page title on
            inner pages; language + dark/light toggle always reachable. No ☰ on phones
            (v1.30.4): navigation = bottom tabs + the Settings tab; the avatar opens it. */}
        <header className="csp-mtop">
          <div className="csp-mtop-end">
            {!locked && (
              <button type="button" className="csp-mtop-lang csp-mtop-ico" onClick={toggle}
                aria-label={mode === 'dark' ? t('light_mode') : t('dark_mode')}>
                <SideIcon name={mode === 'dark' ? 'sun' : 'moon'} />
              </button>
            )}
            {!gm && <SoundButton className="csp-mtop-lang csp-mtop-ico" />}
            <button type="button" className="csp-mtop-lang" onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}>
              {lang === 'fa' ? 'EN' : 'فا'}
            </button>
            {gm && <GmBell />}
            {gm ? <AvatarLink to="/my-groups/settings" compact /> : (
              <Link to="/settings" className="csp-mtop-avatar" aria-label={t('settings')} data-testid="avatar">
                {(staff?.username || '?').charAt(0).toUpperCase()}
              </Link>
            )}
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
                <span data-testid={store ? 'store-badge-m' : undefined}>{store ? (lang === 'fa' ? 'پنل فروشگاه' : 'STORE ADMIN') : 'ADMIN CONTROL'}</span>
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
          {!gm && <SoundButton className="csp-tb-btn csp-tb-ico" />}
          {gm && <GmBell />}
          {store && (
            <span data-testid="store-badge" title={staff.store.slug}
              style={{ fontSize: 12, fontWeight: 800, padding: '4px 10px', borderRadius: 999, color: 'var(--c-primary)',
                background: 'color-mix(in srgb, var(--c-primary) 12%, transparent)', whiteSpace: 'nowrap' }}>
              {lang === 'fa' ? 'فروشگاه' : 'Store'} · {staff.store.name}
            </span>
          )}
          {gm ? <AvatarLink to="/my-groups/settings" /> : (
            <>
              <span className="csp-tb-user">
                {staff?.username}{staff?.role ? ` · ${(lang === 'fa' && staff.role_fa) || staff.role}` : staff?.is_superadmin ? ` · ${lang === 'fa' ? 'ابرمدیر' : 'superadmin'}` : ''}
              </span>
              <button className="csp-tb-btn" onClick={() => { logout(); go('/login') }}>{t('logout')}</button>
            </>
          )}
        </header>

        <main className={`csp-content admin-main mx-auto max-w-6xl p-3`}><Outlet /></main>
      </div>

      {/* mobile bottom nav (≤767px) — 5 tabs, the payments queue is the raised
          centre button with the live pending count */}
      <nav className="csp-botnav" style={{ '--csp-bn-n': botnav.length }}>
        {botnav.map(([to, key, , icon, centre]) => {
          const on = tab === to
          // tickets live in the Settings index on phones — its tab carries the ticket badge
          const badge = to === '/payments' && pendingCount > 0 ? pendingCount
            : to === '/settings' && ticketBadge + approvals > 0 ? ticketBadge + approvals : null
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
.csp-group-btn { display: flex; align-items: center; gap: 8px; width: 100%; min-height: 34px; border: 0; border-radius: 8px; background: transparent;
  cursor: pointer; text-align: start; }
.csp-group-btn > span:first-child { flex: 1; }
.csp-group-btn:hover { background: color-mix(in srgb, var(--c-primary) 8%, transparent); }
.csp-group-btn:focus-visible { outline: 2px solid var(--c-primary); outline-offset: 1px; }
.csp-group-chev { flex-shrink: 0; transition: transform .15s; }
.csp-group[data-open] .csp-group-chev { transform: rotate(180deg); }
.csp-group-badge { font-family: inherit; letter-spacing: 0; text-transform: none; }
.csp-group-items { display: flex; flex-direction: column; gap: 4px; }
.csp-nav:has(.csp-group-btn) { gap: 6px; }
/* v1.58 comfortable sizes (the rail is desktop-only): headers + links match the main content */
.csp-group-h { font-family: inherit; font-size: 13px; font-weight: 800; letter-spacing: .01em; padding: 8px 12px 4px; }
[dir="ltr"] .csp-group-h { font-size: 12px; letter-spacing: .06em; }
.csp-group-btn { min-height: 42px; padding: 8px 12px; }
.csp-group-items { gap: 2px; padding-bottom: 6px; }
.csp-link { font-size: 15px; padding: 11px 14px; }
.csp-link svg { width: 21px; height: 21px; }
.csp-nav:has(.csp-group-btn) { gap: 8px; }
.csp-group-chev { width: 16px; height: 16px; }

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
/* phones: no rail / drawer at all (v1.30.4) — bottom tabs + the Settings tab only */
@media (max-width: 767px) { .csp-rail, .csp-backdrop { display: none !important; } }
.csp-acc { padding: 12px 16px 16px; }

@media (max-width: 767px) {
  /* --- top bar: brand / back + title · theme · language · avatar (→ Settings tab) --- */
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
    text-decoration: none;
    width: 36px; height: 36px; flex-shrink: 0; border-radius: 999px;
    display: grid; place-items: center; font-weight: 700; font-size: 13px;
    color: var(--c-text);
    background: color-mix(in srgb, var(--c-text-muted) 16%, transparent);
    border: 1px solid var(--c-border);
  }

  /* --- bottom nav (Stitch f10ea6b9): grid of 5, active = DOT above the icon --- */
  .csp-botnav {
    position: fixed; inset-inline: 0; bottom: 0; z-index: 55;
    display: grid; grid-template-columns: repeat(var(--csp-bn-n, 5), minmax(0, 1fr)); align-items: center;
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
