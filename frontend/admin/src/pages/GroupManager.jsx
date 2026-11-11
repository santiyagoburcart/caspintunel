import AgencyHistory from '../components/AgencyHistory'
import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Navigate, useParams } from 'react-router-dom'
import { api, tokens } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useTheme } from '../theme/ThemeProvider'
import { genAdminPassword, passwordProblem, PW_RULE } from '../lib/adminPassword'
import { gmHome } from '../components/adminNav'
import { useI18n } from '../lib/i18n'
import { jalali, toman } from '../lib/format'
import { presetRanges, toJalaliStr } from '../lib/jalaliCalendar'
import { copyToClipboard } from '../lib/clipboard'
import { ACCENT_CSS, Ic } from '../components/AgencyIcons'
import { useToast } from '../components/Toast'
import { GroupStatement as StaffGroupStatement } from './AgencyManagers'
import { ManagerInvoices } from '../components/AgencyBilling'
import { Toggle } from '../components/ui'
import { ADMIN_BASE } from '../lib/base'
import { playChime, unlockSound } from '../lib/notifySound'
import { currentSubscription, needsHomeScreen, pushSupported, subscribePush, unsubscribePush } from '../lib/webPush'
import { StatGrid, ST_CSS, useST } from '../components/AgencyStats'
import { GmNotificationsPage } from '../components/GmBell'
import LogoutButton, { LOGOUT_CSS } from '../components/LogoutButton'

// Group-manager pages inside the main panel (v1.25). A group manager signs in at
// /panel/ like any staff (role "Group manager") and sees only this menu
// (components/adminNav.js → GM_GROUPS). Every rule (own groups only, increase only,
// allowed admin roles, cap, approvals) is enforced by the server — apps/agency/managers.py
// behind /api/v1/agency/manager/ — and every other admin API answers 403.
// Moved here from the old <portal>/manager page; the group statement reuses the staff
// Agency component (pages/AgencyManagers.jsx → GroupStatement).

const BASE = '/agency/manager'
const PUSH_BASE = `${ADMIN_BASE.replace(/\/$/, '')}/`
const http = {
  get: (u, cfg) => api.get(BASE + u, cfg),
  post: (u, body, cfg) => api.post(BASE + u, body, cfg),
}

const T = {
  fa: {
    title: 'گروه‌های من', sub: 'با نام کاربری و رمزی که پشتیبانی برای شما ساخته وارد شوید', username: 'نام کاربری', password: 'رمز عبور',
    login: 'ورود', logout: 'خروج', wrong: 'نام کاربری یا رمز عبور اشتباه است.', locked: 'به‌دلیل تلاش‌های ناموفق، ورود موقتاً بسته شده است.', error: 'خطا در ارتباط با سرور',
    net: 'ارتباط با سرور برقرار نشد — اینترنت را بررسی کنید.', expired: 'نشست شما تمام شده — دوباره وارد شوید.', welcome: 'خوش آمدید', bye: 'خارج شدید', reseller: 'ورود نمایندگان',
    t_admins: 'ادمین‌ها', t_acc: 'حسابداری', t_act: 'فعالیت', no_groups: 'هنوز گروهی به شما سپرده نشده است.',
    limit: 'سقف', used: 'مصرف', remaining: 'باقی‌مانده', users: 'کاربران', active_u: 'فعال', unl: 'نامحدود', role_l: 'نقش ادمین (Role)', balance: 'بدهی', pend: 'در انتظار تأیید',
    st_active: 'فعال', st_panel_disabled: 'غیرفعال', st_pamp_limited: 'محدود‌شده', owner: 'مالک گروه', sudo: 'فقط پشتیبانی',
    add: 'افزودن حجم', pw: 'تغییر رمز', inb: 'تغییر نقش', pw_l: 'تغییر رمز', inb_l: 'تغییر نقش', more: 'کارهای بیشتر', new_admin: 'ادمین جدید', group_debt: 'بدهی کل گروه',
    cap: 'حجم تأییدنشدهٔ شما', cap_of: 'از سقف', cap_reached: 'به سقف حجم تأییدنشده رسیده‌اید — تا تأیید پشتیبانی، حجم تازه نمی‌توانید بدهید.', no_cap: 'بدون سقف',
    gb_in: 'حجم (گیگابایت)', add_note: 'فقط افزایش. بلافاصله روی پنل اعمال می‌شود و تا تأیید پشتیبانی «در انتظار» می‌ماند.', confirm_add: 'تأیید و اعمال', new_limit: 'سقف جدید',
    cur: 'فعلی', pw_new: 'رمز جدید', gen: 'رمز تصادفی', save: 'ذخیره', cancel: 'انصراف', pick_inb: 'نقش ادمین (Role) را انتخاب کنید', no_roles: 'نقشی برای این گروه در دسترس نیست — با پشتیبانی تماس بگیرید.',
    n_user: 'نام کاربری ادمین', n_gb: 'حجم اولیه (گیگابایت)', create: 'ساخت ادمین', created: 'ادمین ساخته شد', cred: 'اطلاعات ورود ادمین (فقط همین یک بار)', copy: 'کپی', copied: 'کپی شد', close: 'بستن',
    added: 'حجم اضافه شد — در انتظار تأیید', pw_done: 'رمز ادمین تغییر کرد', inb_done: 'نقش ادمین تغییر کرد', unl_no: 'این ادمین نامحدود است؛ فقط پشتیبانی آن را تغییر می‌دهد.',
    from: 'از تاریخ', to: 'تا تاریخ', apply: 'اعمال', clear: 'همهٔ زمان‌ها', csv: 'CSV', xlsx: 'Excel', print: 'چاپ', date_ph: '۱۴۰۵/۰۷/۰۱',
    date: 'تاریخ', type: 'نوع', amount: 'مبلغ', charges: 'شارژ', payments: 'پرداخت', admin: 'ادمین', statement: 'صورت‌حساب', group_st: 'صورت‌حساب گروه', hide: 'بستن', pending_sep: 'در انتظار تأیید (جدا از مانده)',
    opening: 'مانده از قبل', closing: 'مانده پایان بازه', none: 'گردشی نیست.', running: 'مانده', voided: 'باطل‌شده', no_price: 'بی‌قیمت', total: 'جمع',
    k_quota_charge: 'شارژ حجم', k_manual_charge: 'بدهکاری', k_adjustment: 'اصلاحیه', k_payment: 'پرداخت', act_none: 'فعالیتی نیست.',
    disable: 'غیرفعال‌کردن', enable: 'فعال‌کردن', dis_q: 'ادمین {u} غیرفعال شود؟ تا فعال‌شدن دوباره نمی‌تواند وارد پنل شود (کاربرانش دست نمی‌خورند).', en_q: 'ادمین {u} دوباره فعال شود؟',
    dis_done: 'ادمین غیرفعال شد', en_done: 'ادمین فعال شد', confirm: 'تأیید', blocked: 'به‌خاطر تمام‌شدن حجم بسته شده — فقط پشتیبانی',
    u_title: 'کاربران {u}', u_search: 'جستجوی نام کاربر…', u_all: 'همه', u_none: 'کاربری پیدا نشد.', u_exp: 'انقضا', u_never: 'هرگز', u_online: 'آنلاین', u_last: 'آخرین اتصال',
    u_noexp: 'بدون انقضا', prev: 'قبلی', next: 'بعدی', page: 'صفحهٔ {p} از {n}', u_total: '{n} کاربر',
    period: 'بازه', per_page: 'در هر صفحه', sort_by: 'مرتب‌سازی', sort_name: 'نام', sort_usage: 'بیشترین مصرف', sort_debt: 'بیشترین بدهی', count_admins: '{n} ادمین', no_admins: 'ادمینی نیست.', pages: 'صفحه‌ها',
    us_active: 'فعال', us_disabled: 'غیرفعال', us_limited: 'حجم تمام', us_expired: 'منقضی', us_on_hold: 'در انتظار اتصال',
    a_settings: 'تنظیمات', support_url: 'لینک پشتیبانی', profile_title: 'عنوان پروفایل', profile_hint: 'در صفحهٔ اشتراک کاربران این ادمین نمایش داده می‌شود. لینک پشتیبانی: لینک کامل یا نام‌کاربری تلگرام با @ — فاصله و نویسه‌های نامرئی (مثلاً هنگام کپی از تلگرام) خودکار حذف می‌شوند.',
    prof_done: 'تنظیمات ادمین ذخیره شد', group: 'گروه', search_admins: 'جستجوی نام ادمین…', no_match: 'ادمینی با این نام نیست.',
    set_profile: 'حساب من', set_role: 'نقش', set_groups: 'گروه‌های سپرده‌شده', set_cap: 'سقف حجم تأییدنشده', set_display: 'نام نمایشی',
    set_pw: 'تغییر رمز عبور من', set_pw_cur: 'رمز فعلی', set_pw_new: 'رمز جدید (حداقل ۸ نویسه)', set_pw_rep: 'تکرار رمز جدید', set_pw_mismatch: 'رمز جدید و تکرار آن یکی نیستند.',
    set_pw_done: 'رمز شما تغییر کرد — نشست‌های دیگر بسته شدند.', set_pw_note: 'بعد از تغییر، همهٔ نشست‌های دیگر شما (دستگاه‌های دیگر) بسته می‌شوند.',
    set_prefs: 'نمایش', set_lang: 'زبان', set_theme: 'پوسته', light: 'روشن', dark: 'تاریک', set_logout: 'خروج از حساب', set_notify: 'اعلان‌ها', set_sound: 'صدای اعلان', set_sound_d: 'با رسیدن اعلان تازه (فاکتور، پرداخت، تأیید درخواست) یک صدای کوتاه پخش می‌شود.', set_volume: 'بلندی صدا', set_test: 'پخش آزمایشی', set_push: 'اعلان مرورگر', set_push_d: 'حتی وقتی پنل بسته است، اعلان روی این دستگاه نشان داده می‌شود.', set_push_test: 'ارسال اعلان آزمایشی', push_off: 'اعلان مرورگر روی سرور فعال نیست.', push_ios: 'در آیفون اول پنل را به صفحهٔ اصلی (Add to Home Screen) اضافه کنید.', push_unsupported: 'این مرورگر اعلان مرورگر را پشتیبانی نمی‌کند.', push_denied: 'اجازهٔ اعلان در مرورگر داده نشد.', note: 'توضیح',
    acts: { admin_created: 'ساخت ادمین', volume_added: 'افزودن حجم', password_changed: 'تغییر رمز ادمین', role_changed: 'تغییر نقش ادمین', login: 'ورود', approved: 'تأیید پشتیبانی', rejected: 'رد پشتیبانی', admin_enabled: 'فعال‌کردن ادمین', admin_disabled: 'غیرفعال‌کردن ادمین', profile_changed: 'تغییر تنظیمات ادمین', pay_created: 'شروع پرداخت', pay_pay_all: 'پرداخت کل بدهی', pay_receipt: 'ارسال رسید پرداخت', pay_approved: 'پرداخت تأیید شد', pay_rejected: 'پرداخت رد شد', pay_amount_mismatch: 'واریز با مبلغ متفاوت', request_created: 'درخواست شارژ' },
    act_types: { create: 'ساخت', volume: 'حجم', status: 'فعال / غیرفعال', password: 'رمز', role: 'نقش', profile: 'تنظیمات', payment: 'پرداخت', request: 'درخواست', login: 'ورود' },
  },
  en: {
    title: 'My groups', sub: 'Sign in with the username and password support made for you', username: 'Username', password: 'Password',
    login: 'Sign in', logout: 'Sign out', wrong: 'Wrong username or password.', locked: 'Too many failed attempts — sign-in is paused for a few minutes.', error: 'Could not reach the server',
    net: 'Could not reach the server — check your connection.', expired: 'Your session ended — please sign in again.', welcome: 'Welcome', bye: 'Signed out', reseller: 'Reseller sign-in',
    t_admins: 'Admins', t_acc: 'Accounting', t_act: 'Activity', no_groups: 'No group is assigned to you yet.',
    limit: 'Limit', used: 'Used', remaining: 'Remaining', users: 'Users', active_u: 'active', unl: 'Unlimited', role_l: 'Admin role', balance: 'Owes', pend: 'Pending approval',
    st_active: 'Active', st_panel_disabled: 'Disabled', st_pamp_limited: 'Limited', owner: 'Group owner', sudo: 'support only',
    add: 'Add volume', pw: 'Password', inb: 'Role', pw_l: 'Change password', inb_l: 'Change role', more: 'More actions', new_admin: 'New admin', group_debt: 'Group total debt',
    cap: 'Your unapproved volume', cap_of: 'of', cap_reached: 'You reached your unapproved-volume cap — new volume is blocked until support approves.', no_cap: 'no cap',
    gb_in: 'Volume (GB)', add_note: 'Increase only. Applied on the panel at once; pending until support approves.', confirm_add: 'Confirm and apply', new_limit: 'New limit',
    cur: 'Current', pw_new: 'New password', gen: 'Random', save: 'Save', cancel: 'Cancel', pick_inb: 'Pick the admin role', no_roles: 'No admin role is available for this group — contact support.',
    n_user: 'Admin username', n_gb: 'Initial volume (GB)', create: 'Create admin', created: 'Admin created', cred: 'Admin sign-in (shown only once)', copy: 'Copy', copied: 'Copied', close: 'Close',
    added: 'Volume added — pending approval', pw_done: 'Admin password changed', inb_done: 'Admin role changed', unl_no: 'This admin is unlimited; only support can change it.',
    from: 'From', to: 'To', apply: 'Apply', clear: 'All time', csv: 'CSV', xlsx: 'Excel', print: 'Print', date_ph: '1405/07/01',
    date: 'Date', type: 'Type', amount: 'Amount', charges: 'Charges', payments: 'Payments', admin: 'Admin', statement: 'Statement', group_st: 'Group statement', hide: 'Hide', pending_sep: 'Pending approval (not in the balance)',
    opening: 'Opening balance', closing: 'Closing balance', none: 'No entries.', running: 'Balance', voided: 'voided', no_price: 'no price', total: 'Total',
    k_quota_charge: 'Quota charge', k_manual_charge: 'Charge', k_adjustment: 'Adjustment', k_payment: 'Payment', act_none: 'No activity yet.',
    disable: 'Disable', enable: 'Enable', dis_q: 'Disable admin {u}? They cannot sign in to the panel until enabled again (their users are not touched).', en_q: 'Enable admin {u} again?',
    dis_done: 'Admin disabled', en_done: 'Admin enabled', confirm: 'Confirm', blocked: 'Blocked for using up its volume — support only',
    u_title: 'Users of {u}', u_search: 'Search user…', u_all: 'All', u_none: 'No users found.', u_exp: 'Expires', u_never: 'never', u_online: 'Online', u_last: 'Last seen',
    u_noexp: 'no expiry', prev: 'Previous', next: 'Next', page: 'Page {p} of {n}', u_total: '{n} users',
    period: 'Period', per_page: 'Per page', sort_by: 'Sort', sort_name: 'Name', sort_usage: 'Highest usage', sort_debt: 'Highest debt', count_admins: '{n} admins', no_admins: 'No admins.', pages: 'Pages',
    us_active: 'Active', us_disabled: 'Disabled', us_limited: 'Limited', us_expired: 'Expired', us_on_hold: 'On hold',
    a_settings: 'Settings', support_url: 'Support link', profile_title: 'Profile title', profile_hint: "Shown on the subscription page of this admin's users. Support link: https://… or a Telegram @username — spaces and invisible characters (e.g. copied from Telegram) are removed automatically.",
    prof_done: 'Admin settings saved', group: 'Group', search_admins: 'Search admin name…', no_match: 'No admin with this name.',
    set_profile: 'My account', set_role: 'Role', set_groups: 'Assigned groups', set_cap: 'Max unapproved volume', set_display: 'Display name',
    set_pw: 'Change my password', set_pw_cur: 'Current password', set_pw_new: 'New password (8+ characters)', set_pw_rep: 'Repeat the new password', set_pw_mismatch: 'The new password and its repeat differ.',
    set_pw_done: 'Your password changed — other sessions were signed out.', set_pw_note: 'After the change, all your other sessions (other devices) are signed out.',
    set_prefs: 'Display', set_lang: 'Language', set_theme: 'Theme', light: 'Light', dark: 'Dark', set_logout: 'Log out', set_notify: 'Notifications', set_sound: 'Notification sound', set_sound_d: 'A short sound plays when a new notification arrives (invoice, payment, request decision).', set_volume: 'Volume', set_test: 'Play a test', set_push: 'Browser notifications', set_push_d: 'Shown on this device even while the panel is closed.', set_push_test: 'Send a test notification', push_off: 'Browser notifications are not configured on the server.', push_ios: 'On iPhone, add the panel to the Home Screen first.', push_unsupported: 'This browser does not support browser notifications.', push_denied: 'Notification permission was not given.', note: 'Note',
    acts: { admin_created: 'Admin created', volume_added: 'Volume added', password_changed: 'Admin password changed', role_changed: 'Admin role changed', login: 'Signed in', approved: 'Approved by support', rejected: 'Rejected by support', admin_enabled: 'Admin enabled', admin_disabled: 'Admin disabled', profile_changed: 'Admin settings changed', pay_created: 'Payment started', pay_pay_all: 'Paid the whole debt', pay_receipt: 'Payment receipt sent', pay_approved: 'Payment approved', pay_rejected: 'Payment rejected', pay_amount_mismatch: 'Deposit with another amount', request_created: 'Volume requested' },
    act_types: { create: 'Create', volume: 'Volume', status: 'Enable / disable', password: 'Password', role: 'Role', profile: 'Settings', payment: 'Payment', request: 'Request', login: 'Sign-in' },
  },
}
const GIB = 1024 ** 3
const N = ({ children }) => <bdi dir="ltr" className="ap-num">{children}</bdi>
const gbText = (v) => `${Number(v || 0).toLocaleString('en-US', { maximumFractionDigits: 2 })} GB`
const bText = (b) => gbText(Number(b || 0) / GIB)
const money = (v, lang) => (Number(v) < 0 ? '−' : '') + toman(Math.abs(Number(v || 0)), lang)
const errText = (e, s) => (!e?.response ? s.net : (s === T.fa && e.response.data?.detail_fa) || e.response.data?.detail || s.error)
const faDigits = (v) => String(v).replace(/[۰-۹]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d)).replace(/[٠-٩]/g, (d) => '٠١٢٣٤٥٦٧٨٩'.indexOf(d))
const roleLabel = (r) => (r ? r.name || `#${r.id}` : '—')
const pwCheck = (pw, username, s) => (passwordProblem(pw, username) ? PW_RULE[s === T.fa ? 'fa' : 'en'] : '')

const genPw = () => genAdminPassword()

async function download(url, params, name) {
  const r = await http.get(url, { params, responseType: 'blob' })
  const fn = (r.headers['content-disposition'] || '').match(/filename="([^"]+)"/)?.[1] || name
  const a = document.createElement('a')
  a.href = URL.createObjectURL(r.data); a.download = fn
  document.body.appendChild(a); a.click(); a.remove()
  setTimeout(() => URL.revokeObjectURL(a.href), 2000)
}

const TABS = { undefined: 'admins', new: 'admins', accounting: 'acc', activity: 'act', settings: 'set', invoices: 'inv', notifications: 'notif' }
// v1.27: each page needs its own permission of the manager's role (server answers 403 too)
const TAB_PERM = { admins: 'agency.gm.view_admins', acc: 'agency.gm.accounting', act: 'agency.gm.activity', inv: 'agency.gm.invoices' }

export default function GroupManager() {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const { tab: seg } = useParams()
  const tab = TABS[seg]
  const { can } = useAuth()
  const [me, setMe] = useState(null)
  const [err, setErr] = useState('')
  const toast = useToast()
  // v1.37: groups only (lite) — the admins page pages its rows from GET manager/admins/
  const load = () => http.get('/me/', { params: { lite: 1 } }).then((r) => { setMe(r.data); setErr('') }).catch((e) => {
    const m = errText(e, s); setErr(m); toast.error(m)
  })
  useEffect(() => { load() }, [])
  if (!tab) return <Navigate to={gmHome(can)} replace />
  if (seg === 'new') return <Navigate to="/my-groups" replace />          // v1.37: the old page is a dialog now
  if (TAB_PERM[tab] && !can(TAB_PERM[tab])) {
    const home = gmHome(can)
    return home === `/my-groups${seg ? '/' + seg : ''}` ? null : <Navigate to={home} replace />
  }
  return (
    <div className="ap am-in" dir={lang === 'fa' ? 'rtl' : 'ltr'}>
      <style>{ACCENT_CSS + PORTAL_CSS + CSS + ST_CSS + LOGOUT_CSS}</style>
      <h1 className="am-h1">{s.title}{me && <small className="am-who"> · <bdi>{me.manager.display_name || me.manager.username}</bdi></small>}</h1>
      {err && <div className="ap-alert" role="alert">{err}</div>}
      {!me && !err && <div className="ap-spin" aria-busy="true" />}
      {me && (
        <>
          {me.groups.length === 0 && <div className="ap-card ap-empty">{s.no_groups}</div>}
          {tab === 'admins' && <Admins me={me} s={s} lang={lang} reload={load} can={can} />}
          {tab === 'acc' && me.groups.length > 0 && <Accounting me={me} s={s} lang={lang} />}
          {tab === 'act' && <Activity s={s} lang={lang} />}
          {tab === 'set' && <SettingsTab me={me} s={s} />}
          {tab === 'inv' && <ManagerInvoices http={http} lang={lang} canRequest={can('agency.gm.request_volume')} />}
          {tab === 'notif' && <GmNotificationsPage />}
        </>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ dialogs
function Modal({ title, children, onClose }) {
  useEffect(() => {
    const k = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', k)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', k); document.body.style.overflow = prev }
  }, [])
  return (
    <div className="am-back" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="am-dlg" role="dialog" aria-modal="true" aria-label={title}>
        <div className="am-dlg-h"><b>{title}</b><button type="button" className="am-x" onClick={onClose} aria-label="×"><Ic n="x" /></button></div>
        {children}
      </div>
    </div>
  )
}

function useAction(s, done) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const toast = useToast()
  const run = async (fn, okMsg) => {
    setBusy(true); setErr('')
    try { const r = await fn(); if (okMsg) toast.success(okMsg); done(r); return r } catch (e) { const m = errText(e, s); setErr(m); toast.error(m); return null } finally { setBusy(false) }
  }
  return { busy, err, run }
}

function AddVolume({ a, s, cap, onClose, reload }) {
  const [gb, setGb] = useState('')
  const [step, setStep] = useState(1)
  const { busy, err, run } = useAction(s, () => { reload(); onClose() })
  const v = Number(faDigits(gb))
  const valid = v > 0
  const newB = Number(a.admin_limit_bytes) + v * GIB
  const over = cap.max_gb != null && Number(cap.pending_gb) + v > Number(cap.max_gb)
  return (
    <Modal title={`${s.add} — ${a.username}`} onClose={onClose}>
      {step === 1 ? (
        <form className="am-form" onSubmit={(e) => { e.preventDefault(); if (valid && !over) setStep(2) }}>
          <label>{s.gb_in}<input className="ap-input" dir="ltr" inputMode="decimal" autoFocus value={gb} onChange={(e) => setGb(e.target.value.replace(/[^\d.۰-۹]/g, ''))} /></label>
          <p className="am-hint">{s.add_note}</p>
          {over && <div className="ap-alert">{s.cap_reached}</div>}
          <div className="am-row"><button type="button" className="ap-link" onClick={onClose}>{s.cancel}</button><button className="ap-btn am-btn" disabled={!valid || over}><Ic n="plus" />{s.add}</button></div>
        </form>
      ) : (
        <div className="am-form">
          <dl className="am-cmp">
            <div><dt>{s.cur}</dt><dd><N>{bText(a.admin_limit_bytes)}</N></dd></div>
            <div><dt>+</dt><dd><N>{gbText(v)}</N></dd></div>
            <div data-strong><dt>{s.new_limit}</dt><dd><N>{bText(newB)}</N></dd></div>
          </dl>
          <p className="am-hint">{s.add_note}</p>
          {err && <div className="ap-alert">{err}</div>}
          <div className="am-row"><button type="button" className="ap-link" onClick={() => setStep(1)}>{s.cancel}</button>
            <button type="button" className="ap-btn am-btn" disabled={busy} onClick={() => run(() => http.post(`/admins/${encodeURIComponent(a.username)}/add-volume/`, { gb: v }), s.added)}>{busy ? <span className="ap-btn-spin" /> : <Ic n="check" />}{s.confirm_add}</button></div>
        </div>
      )}
    </Modal>
  )
}

function Password({ a, s, onClose }) {
  const [pw, setPw] = useState('')
  const [localErr, setLocalErr] = useState('')
  const { busy, err, run } = useAction(s, () => {})
  const [done, setDone] = useState(false)
  return (
    <Modal title={`${s.pw} — ${a.username}`} onClose={onClose}>
      {done ? <Cred s={s} username={a.username} password={pw} onClose={onClose} /> : (
        <form className="am-form" onSubmit={async (e) => {
          e.preventDefault()
          const bad = pwCheck(pw, a.username, s); setLocalErr(bad); if (bad) return
          if (await run(() => http.post(`/admins/${encodeURIComponent(a.username)}/password/`, { password: pw }), s.pw_done)) setDone(true)
        }}>
          <label>{s.pw_new}<span className="am-pw"><input className="ap-input" dir="ltr" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} autoFocus />
            <button type="button" className="ap-link" onClick={() => setPw(genPw())}><Ic n="reset" />{s.gen}</button></span></label>
          {(localErr || err) && <div className="ap-alert" role="alert">{localErr || err}</div>}
          <div className="am-row"><button type="button" className="ap-link" onClick={onClose}>{s.cancel}</button><button className="ap-btn am-btn" disabled={busy || !pw}>{s.save}</button></div>
        </form>
      )}
    </Modal>
  )
}

function RolePick({ roles, value, onChange, s }) {
  return (
    <div className="am-roles" role="radiogroup" aria-label={s.pick_inb}>
      {roles.length === 0 && <p className="am-hint">{s.no_roles}</p>}
      {roles.map((r) => (
        <label key={r.id} className="am-rolei" data-on={value === r.id || undefined}>
          <input type="radio" name="role" checked={value === r.id} onChange={() => onChange(r.id)} />
          <span><b>{roleLabel(r)}</b></span>
        </label>
      ))}
    </div>
  )
}

function RoleChange({ a, roles, s, onClose, reload }) {
  const [rid, setRid] = useState(a.role?.id ?? null)
  const { busy, err, run } = useAction(s, () => { reload(); onClose() })
  return (
    <Modal title={`${s.inb} — ${a.username}`} onClose={onClose}>
      <form className="am-form" onSubmit={(e) => { e.preventDefault(); run(() => http.post(`/admins/${encodeURIComponent(a.username)}/role/`, { role_id: rid }), s.inb_done) }}>
        <p className="am-hint">{s.cur}: <b>{roleLabel(a.role)}</b></p>
        <RolePick roles={roles} value={rid} onChange={setRid} s={s} />
        {err && <div className="ap-alert">{err}</div>}
        <div className="am-row"><button type="button" className="ap-link" onClick={onClose}>{s.cancel}</button><button className="ap-btn am-btn" disabled={busy || rid == null || rid === a.role?.id}>{s.save}</button></div>
      </form>
    </Modal>
  )
}

function NewAdminForm({ groups, g0, s, cap, onClose, reload }) {
  const [gid, setGid] = useState(g0?.id ?? (groups.length === 1 ? groups[0].id : null))
  const g = groups.find((x) => x.id === gid) || null
  const [v, setV] = useState({ username: '', password: genPw(), role_id: g?.roles[0]?.id ?? null, gb: '', support_url: '', profile_title: '' })
  const [made, setMade] = useState(null)
  const [localErr, setLocalErr] = useState('')
  const { busy, err, run } = useAction(s, () => reload())
  const gbv = Number(faDigits(v.gb))
  const over = cap.max_gb != null && Number(cap.pending_gb) + gbv > Number(cap.max_gb)
  const pickGroup = (id) => { const ng = groups.find((x) => x.id === Number(id)); setGid(ng?.id ?? null); setV({ ...v, role_id: ng?.roles[0]?.id ?? null }) }
  const submit = async (e) => {
    e.preventDefault()
    const bad = pwCheck(v.password, v.username.trim(), s); setLocalErr(bad); if (bad || !g) return
    const r = await run(() => http.post('/admins/', { group_id: g.id, username: v.username.trim(), password: v.password, role_id: v.role_id, initial_gb: gbv,
      support_url: v.support_url.trim(), profile_title: v.profile_title.trim() }), s.created)
    if (r) setMade(r.data)
  }
  if (made) return <Cred s={s} username={made.username} password={made.password} onClose={onClose} />
  return (
    <form className="am-form" onSubmit={submit}>
      {groups.length > 1 && (
        <label>{s.group}<select className="ap-input" value={gid ?? ''} onChange={(e) => pickGroup(e.target.value)} required>
          <option value="" disabled>—</option>{groups.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
      )}
      <div className="am-pair">
      <label>{s.n_user}<input className="ap-input" dir="ltr" autoComplete="off" required minLength={3} maxLength={32} value={v.username} onChange={(e) => setV({ ...v, username: e.target.value })} autoFocus /></label>
      <label>{s.n_gb}<input className="ap-input" dir="ltr" inputMode="decimal" required value={v.gb} onChange={(e) => setV({ ...v, gb: e.target.value.replace(/[^\d.۰-۹]/g, '') })} /></label>
      </div>
      <label>{s.password}<span className="am-pw"><input className="ap-input" dir="ltr" autoComplete="new-password" required value={v.password} onChange={(e) => setV({ ...v, password: e.target.value })} />
        <button type="button" className="ap-link" onClick={() => setV({ ...v, password: genPw() })}><Ic n="reset" />{s.gen}</button></span></label>
      {g && <><span className="am-l">{s.role_l}</span>
        <RolePick roles={g.roles} value={v.role_id} onChange={(id) => setV({ ...v, role_id: id })} s={s} /></>}
      <div className="am-pair">
      <label>{s.support_url}<input className="ap-input" dir="ltr" type="text" inputMode="url" autoComplete="off" spellCheck={false} placeholder="https://t.me/… / @support" value={v.support_url} onChange={(e) => setV({ ...v, support_url: e.target.value })} /></label>
      <label>{s.profile_title}<input className="ap-input" maxLength={255} value={v.profile_title} onChange={(e) => setV({ ...v, profile_title: e.target.value })} /></label>
      </div>
      <p className="am-hint">{s.profile_hint} {s.add_note}</p>
      {over && <div className="ap-alert">{s.cap_reached}</div>}
      {(localErr || err) && <div className="ap-alert" role="alert">{localErr || err}</div>}
      <div className="am-row"><button type="button" className="ap-link" onClick={onClose}>{s.cancel}</button><button className="ap-btn am-btn" disabled={busy || !g || !(gbv > 0) || v.role_id == null || over}>{busy ? <span className="ap-btn-spin" /> : <Ic n="plus" />}{s.create}</button></div>
    </form>
  )
}

function NewAdmin({ g, groups, s, cap, onClose, reload }) {
  return (
    <Modal title={g ? `${s.new_admin} — ${g.name}` : s.new_admin} onClose={onClose}>
      <NewAdminForm groups={groups || [g]} g0={g} s={s} cap={cap} onClose={onClose} reload={reload} />
    </Modal>
  )
}

// enable / disable (confirm), users (read-only), support link + profile title — v1.27
function Confirm({ title, text, s, onClose, onYes, tone }) {
  const [busy, setBusy] = useState(false)
  return (
    <Modal title={title} onClose={onClose}>
      <div className="am-form">
        <p className="am-hint am-confirm">{text}</p>
        <div className="am-row"><button type="button" className="ap-link" onClick={onClose}>{s.cancel}</button>
          <button type="button" className="ap-btn am-btn" data-tone={tone} disabled={busy} onClick={async () => { setBusy(true); await onYes(); setBusy(false) }}>{busy ? <span className="ap-btn-spin" /> : null}{s.confirm}</button></div>
      </div>
    </Modal>
  )
}

function AdminSettings({ a, s, onClose }) {
  const [v, setV] = useState(null)
  const [loadErr, setLoadErr] = useState('')
  const { busy, err, run } = useAction(s, () => onClose())
  useEffect(() => { http.get(`/admins/${encodeURIComponent(a.username)}/profile/`).then((r) => setV(r.data)).catch((e) => setLoadErr(errText(e, s))) }, [])
  return (
    <Modal title={`${s.a_settings} — ${a.username}`} onClose={onClose}>
      {loadErr ? <div className="ap-alert">{loadErr}</div> : !v ? <div className="ap-spin" /> : (
        <form className="am-form" onSubmit={(e) => { e.preventDefault(); run(() => http.post(`/admins/${encodeURIComponent(a.username)}/profile/`, { support_url: v.support_url.trim(), profile_title: v.profile_title.trim() }), s.prof_done) }}>
          <label>{s.support_url}<input className="ap-input" dir="ltr" type="text" inputMode="url" autoComplete="off" spellCheck={false} placeholder="https://t.me/… / @support" value={v.support_url} onChange={(e) => setV({ ...v, support_url: e.target.value })} autoFocus /></label>
          <label>{s.profile_title}<input className="ap-input" maxLength={255} value={v.profile_title} onChange={(e) => setV({ ...v, profile_title: e.target.value })} /></label>
          <p className="am-hint">{s.profile_hint}</p>
          {err && <div className="ap-alert" role="alert">{err}</div>}
          <div className="am-row"><button type="button" className="ap-link" onClick={onClose}>{s.cancel}</button><button className="ap-btn am-btn" disabled={busy}>{s.save}</button></div>
        </form>
      )}
    </Modal>
  )
}

const USER_STATUSES = ['active', 'on_hold', 'limited', 'expired', 'disabled']
function AdminUsers({ a, s, lang, onClose }) {
  const [q, setQ] = useState('')
  const [st, setSt] = useState('')
  const [page, setPage] = useState(0)
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const LIMIT = 20
  useEffect(() => { setPage(0) }, [q, st])
  useEffect(() => {
    const id = setTimeout(() => {
      setD(null)
      http.get(`/admins/${encodeURIComponent(a.username)}/users/`, { params: { search: q.trim() || undefined, status: st || undefined, offset: page * LIMIT, limit: LIMIT } })
        .then((r) => { setD(r.data); setErr('') }).catch((e) => { setErr(errText(e, s)); setD({ results: [], total: 0 }) })
    }, q ? 300 : 0)
    return () => clearTimeout(id)
  }, [q, st, page])
  const pages = d ? Math.max(1, Math.ceil(d.total / LIMIT)) : 1
  const online = (u) => u.online_at && Date.now() - new Date(u.online_at).getTime() < 3 * 60 * 1000
  return (
    <Modal title={s.u_title.replace('{u}', a.username)} onClose={onClose}>
      <div className="am-form am-users">
        <div className="am-ufilter">
          <input className="ap-input" type="search" value={q} placeholder={s.u_search} onChange={(e) => setQ(e.target.value)} aria-label={s.u_search} />
          <select className="ap-input" value={st} onChange={(e) => setSt(e.target.value)} aria-label={s.users}>
            <option value="">{s.u_all}</option>{USER_STATUSES.map((x) => <option key={x} value={x}>{s['us_' + x]}</option>)}
          </select>
        </div>
        {err && <div className="ap-alert">{err}</div>}
        {!d ? <div className="ap-spin" /> : d.results.length === 0 ? <p className="ap-foot">{s.u_none}</p> : (
          <ul className="am-ulist">{d.results.map((u) => (
            <li key={u.username}>
              <div className="am-u-h"><b dir="ltr">{u.username}</b><span className="am-u-st" data-st={u.status}>{s['us_' + u.status] || u.status}</span></div>
              <div className="am-u-b">
                <span><N>{bText(u.used_traffic)}</N> / <N>{Number(u.data_limit) > 0 ? bText(u.data_limit) : s.unl}</N></span>
                <span>{s.u_exp}: {u.expire ? jalali(u.expire, false, lang) : s.u_noexp}</span>
                <span>{online(u) ? <b className="am-u-on">● {s.u_online}</b> : <>{s.u_last}: {u.online_at ? jalali(u.online_at, true, lang) : s.u_never}</>}</span>
              </div>
            </li>
          ))}</ul>
        )}
        {d && (
          <>
            <p className="am-count am-count--c"><N>{s.u_total.replace('{n}', d.total)}</N></p>
            <Pager page={page + 1} pages={pages} onPage={(n) => setPage(n - 1)} s={s} />
          </>
        )}
      </div>
    </Modal>
  )
}

function Cred({ s, username, password, onClose }) {
  const toast = useToast()
  return (
    <div className="am-form">
      <p className="am-hint">{s.cred}</p>
      <dl className="am-cmp"><div><dt>{s.username}</dt><dd><N>{username}</N></dd></div><div><dt>{s.password}</dt><dd><N>{password}</N></dd></div></dl>
      <div className="am-row">
        <button type="button" className="ap-link" onClick={async () => { if (await copyToClipboard(`${s.username}: ${username}\n${s.password}: ${password}`)) toast.success(s.copied) }}><Ic n="copy" />{s.copy}</button>
        <button type="button" className="ap-btn am-btn" onClick={onClose}>{s.close}</button>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ admins tab
// v1.36: live user counts / online / last activity for the shown admins (agency.gm.full_stats), 60 per call
function useLive(names, on) {
  const [live, setLive] = useState({})
  const key = names.join('|')
  useEffect(() => {
    if (!on || !names.length) return undefined
    let stop = false
    const chunks = []
    for (let i = 0; i < names.length; i += 60) chunks.push(names.slice(i, i + 60))
    chunks.forEach((c) => {
      const qs = c.map((u) => `u=${encodeURIComponent(u)}`).join('&')
      http.get(`/admins/live/?${qs}`).then((r) => { if (!stop) setLive((cur) => ({ ...cur, ...r.data.results })) }).catch(() => {})
    })
    return () => { stop = true }
  }, [key, on])
  return live
}

function AdminStats({ a, lang, s, onClose }) {
  const st = useST(lang)
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { http.get(`/admins/${encodeURIComponent(a.username)}/stats/`).then((r) => setD(r.data)).catch((e) => setErr(errText(e, s))) }, [])
  return (
    <Modal title={`${st.stats_h} — ${a.username}`} onClose={onClose}>
      {err ? <div className="ap-alert">{err}</div> : !d ? <div className="ap-spin" /> : (
        <div data-testid="gm-stats"><StatGrid a={d} live={d.live} lang={lang} full /></div>
      )}
    </Modal>
  )
}

const SORTS = ['name', 'usage', 'debt']

function Admins({ me, s, lang, reload, can }) {
  const [dlg, setDlg] = useState(null)
  const [q, setQ] = useState('')
  const [term, setTerm] = useState('')
  const [sort, setSort] = useState('name')
  const [arch, setArch] = useState(false)          // v1.54 «بایگانی»: deleted admins of my groups (kept with their accounting)
  const [gid, setGid] = useState('')
  const [page, setPage] = useState(1)
  const [d, setD] = useState(null)
  const [tick, setTick] = useState(0)
  const toast = useToast()
  const cap = me.cap
  const full = can('agency.gm.full_stats')
  const seeDebt = can('agency.gm.accounting')
  const live = useLive((d?.results || []).map((a) => a.username), full)
  useEffect(() => { const t = setTimeout(() => { setTerm(q.trim()); setPage(1) }, 300); return () => clearTimeout(t) }, [q])
  useEffect(() => {
    let stop = false
    http.get('/admins/', { params: { q: term || undefined, sort, group: gid || undefined, page, page_size: 20, archived: arch ? 1 : undefined } })
      .then((r) => { if (!stop) setD(r.data) }).catch((e) => { if (!stop) { setD({ results: [], count: 0, page: 1, pages: 1 }); toast.error(errText(e, s)) } })
    return () => { stop = true }
  }, [term, sort, gid, page, tick, arch])
  const close = () => setDlg(null)
  const refresh = () => { setTick((t) => t + 1); reload() }
  const setStatus = async (a, enable) => {
    try {
      await http.post(`/admins/${encodeURIComponent(a.username)}/${enable ? 'enable' : 'disable'}/`, {})
      toast.success(enable ? s.en_done : s.dis_done); close(); refresh()
    } catch (e) { toast.error(errText(e, s)) }
  }
  const creatable = me.groups.filter((g) => g.roles.length)
  const groupOf = (a) => me.groups.find((g) => g.id === a.group_id) || { roles: [] }
  return (
    <>
      {(cap.max_gb != null || Number(cap.pending_gb) > 0) && (
        <div className={cap.reached ? 'ap-alert' : 'ap-warn am-cap'} role="status">
          {s.cap}: <N>{gbText(cap.pending_gb)}</N> {cap.max_gb != null ? <>{s.cap_of} <N>{gbText(cap.max_gb)}</N></> : `(${s.no_cap})`}
          {cap.reached && <> — {s.cap_reached}</>}
        </div>
      )}
      <div className="am-gsum">
        {me.groups.map((g) => (
          <button key={g.id} type="button" className={'am-gchip' + (String(gid) === String(g.id) ? ' on' : '')} aria-pressed={String(gid) === String(g.id)}
            onClick={() => { setGid(String(gid) === String(g.id) ? '' : g.id); setPage(1) }}>
            <Ic n="users" size={14} /><bdi>{g.name}</bdi>
            {g.total_debt != null && <small>{s.group_debt}: <N>{money(g.total_debt, lang)}</N></small>}
          </button>
        ))}
        {can('agency.gm.create_admin') && (
          <button type="button" className="ap-btn am-btn am-new" data-testid="gm-new-admin" disabled={!me.writes_enabled || cap.reached || !creatable.length}
            onClick={() => setDlg({ k: 'new' })}><Ic n="plus" />{s.new_admin}</button>
        )}
      </div>
      <div className="am-tools">
        <input className="ap-input am-search" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={s.search_admins} aria-label={s.search_admins} data-testid="gm-search" />
        <label className="am-sort"><span>{s.sort_by}</span>
          <select className="ap-input" value={sort} onChange={(e) => { setSort(e.target.value); setPage(1) }} data-testid="gm-sort">
            {SORTS.filter((k) => k !== 'debt' || seeDebt).map((k) => <option key={k} value={k}>{s['sort_' + k]}</option>)}
          </select></label>
        <div className="am-chips" role="group" aria-label={lang === 'fa' ? 'فهرست' : 'List'}>
          <button type="button" className={'am-tab' + (!arch ? ' on' : '')} onClick={() => { setArch(false); setPage(1) }}>{lang === 'fa' ? 'فعال' : 'Active'}</button>
          <button type="button" className={'am-tab' + (arch ? ' on' : '')} onClick={() => { setArch(true); setPage(1) }} data-testid="gm-archived">
            {lang === 'fa' ? 'بایگانی' : 'Archive'}{d?.archived_count > 0 ? ` (${d.archived_count})` : ''}</button>
        </div>
      </div>
      {d === null ? <div className="ap-spin" /> : d.results.length === 0 ? <p className="ap-foot">{term ? s.no_match : s.no_admins}</p> : (
        <>
          <p className="am-count">{s.count_admins.replace('{n}', d.count)}</p>
          <div className="am-gridw"><div className="am-grid">
            {d.results.map((a) => <AdminCard key={a.username} a={a} s={s} lang={lang} can={can} full={full} live={live[a.username]} showGroup={me.groups.length > 1}
              writable={me.writes_enabled} capReached={cap.reached} onAct={(k) => setDlg({ k, a, g: groupOf(a) })} />)}
          </div></div>
          <Pager page={d.page} pages={d.pages} onPage={setPage} s={s} />
        </>
      )}
      {dlg?.k === 'add' && <AddVolume a={dlg.a} s={s} cap={cap} onClose={close} reload={refresh} />}
      {dlg?.k === 'pw' && <Password a={dlg.a} s={s} onClose={close} />}
      {dlg?.k === 'inb' && <RoleChange a={dlg.a} roles={dlg.g.roles} s={s} onClose={close} reload={refresh} />}
      {dlg?.k === 'new' && <NewAdmin groups={creatable} g={creatable.length === 1 ? creatable[0] : null} s={s} cap={cap} onClose={close} reload={refresh} />}
      {dlg?.k === 'users' && <AdminUsers a={dlg.a} s={s} lang={lang} onClose={close} />}
      {dlg?.k === 'settings' && <AdminSettings a={dlg.a} s={s} onClose={close} />}
      {dlg?.k === 'stats' && <AdminStats a={dlg.a} s={s} lang={lang} onClose={close} />}
      {(dlg?.k === 'disable' || dlg?.k === 'enable') && (
        <Confirm s={s} title={`${dlg.k === 'disable' ? s.disable : s.enable} — ${dlg.a.username}`} tone={dlg.k === 'disable' ? 'danger' : undefined}
          text={(dlg.k === 'disable' ? s.dis_q : s.en_q).replace('{u}', dlg.a.username)} onClose={close} onYes={() => setStatus(dlg.a, dlg.k === 'enable')} />
      )}
    </>
  )
}

// v1.38.1 compact card: name · status · role, usage bar, cap / used / remaining in one row, debt, user chips,
// actions = one row of primary buttons + «⋯». Sold / hidden / deleted / last activity / online → «جزئیات».
function CardUsers({ a, live, s, st }) {
  const ok = live && live.ok
  const c = ok ? live : { total: a.user_count, active: a.active_user_count, ...(a.user_counts || {}) }
  const chips = [['active', c.active], ...(ok ? [['online', c.online]] : []), ['expired', c.expired], ['limited', c.limited]]
    .filter(([k, v]) => v != null && (k === 'active' || Number(v) > 0))
  return (
    <div className="am-uc" aria-label={s.users}>
      <span className="am-uc-t"><Ic n="users" size={13} /><b><N>{c.total ?? 0}</N></b> {s.users}</span>
      {chips.map(([k, v]) => <span key={k} className="st-chip" data-k={k}><N>{v}</N> {st[k]}</span>)}
    </div>
  )
}

function MoreMenu({ label, items }) {
  const [pos, setPos] = useState(null)
  const btn = useRef(null)
  const pop = useRef(null)
  const close = () => setPos(null)
  useEffect(() => {
    if (!pos) return undefined
    const off = (e) => { if (!pop.current?.contains(e.target) && !btn.current?.contains(e.target)) close() }
    const key = (e) => {
      if (e.key === 'Escape') { close(); btn.current?.focus() }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault()
        const els = [...(pop.current?.querySelectorAll('button:not(:disabled)') || [])]
        const k = els.indexOf(document.activeElement)
        els[(k + (e.key === 'ArrowDown' ? 1 : -1) + els.length) % els.length]?.focus()
      }
    }
    document.addEventListener('pointerdown', off); document.addEventListener('keydown', key); window.addEventListener('scroll', close, true); window.addEventListener('resize', close)
    pop.current?.querySelector('button:not(:disabled)')?.focus()
    return () => { document.removeEventListener('pointerdown', off); document.removeEventListener('keydown', key); window.removeEventListener('scroll', close, true); window.removeEventListener('resize', close) }
  }, [pos])
  if (!items.length) return null
  const toggle = () => {
    if (pos) { close(); return }
    const r = btn.current.getBoundingClientRect()
    const w = Math.min(230, window.innerWidth - 24)
    const rtl = document.documentElement.dir === 'rtl' || btn.current.closest('[dir="rtl"]')
    const left = Math.max(12, Math.min(rtl ? r.left : r.right - w, window.innerWidth - w - 12))
    const h = 52 * items.length + 12
    const top = r.bottom + 6 + h > window.innerHeight && r.top - h - 6 > 0 ? r.top - h - 6 : r.bottom + 6
    setPos({ top, left, width: w })
  }
  return (
    <>
      <button ref={btn} type="button" className="ap-link am-more" aria-haspopup="menu" aria-expanded={!!pos} aria-label={label} title={label} onClick={toggle} data-testid="gm-more"><svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.9" /><circle cx="12" cy="12" r="1.9" /><circle cx="19" cy="12" r="1.9" /></svg></button>
      {pos && createPortal(
        <div ref={pop} className="am-menu" role="menu" style={{ top: pos.top, left: pos.left, width: pos.width }} dir={btn.current?.closest('[dir]')?.getAttribute('dir') || undefined} data-testid="gm-more-menu">
          {items.map((it) => (
            <button key={it.k} type="button" role="menuitem" className="am-menu-i" data-tone={it.tone} disabled={it.disabled} title={it.title}
              onClick={() => { close(); it.onClick() }}><Ic n={it.icon} />{it.label}{it.note && <small>{it.note}</small>}</button>
          ))}
        </div>, document.body)}
    </>
  )
}

function AdminCard({ a, s, lang, can, full, live, showGroup, writable, capReached, onAct }) {
  const st = useST(lang)
  const unl = !(Number(a.admin_limit_bytes) > 0)
  const pct = Math.min(Number(a.usage_percent) || 0, 100)
  const tone = a.usage_percent >= 100 ? 'danger' : a.usage_percent >= 80 ? 'warning' : 'primary'
  const locked = a.is_sudo
  const more = []
  if (!locked) {
    if (can('agency.gm.admin_password')) more.push({ k: 'pw', icon: 'key', label: s.pw_l, disabled: !writable, onClick: () => onAct('pw') })
    if (can('agency.gm.admin_role')) more.push({ k: 'inb', icon: 'sliders', label: s.inb_l, disabled: !writable, onClick: () => onAct('inb') })
    if (can('agency.gm.create_admin')) more.push({ k: 'settings', icon: 'edit', label: s.a_settings, disabled: !writable, onClick: () => onAct('settings') })
    if (can('agency.gm.toggle_admin')) {
      more.push(a.status_code === 'active' ? { k: 'disable', icon: 'power', label: s.disable, tone: 'danger', disabled: !writable, onClick: () => onAct('disable') }
        : a.status_code === 'pamp_limited' ? { k: 'blocked', icon: 'power', label: s.enable, disabled: true, note: s.blocked, onClick: () => {} }
          : { k: 'enable', icon: 'check', label: s.enable, disabled: !writable, onClick: () => onAct('enable') })
    }
  }
  return (
    <article className="ap-card am-card" data-testid="gm-card">
      <header className="am-ch">
        <div className="am-ch-n">
          <h3><bdi>{a.username}</bdi></h3>
          <div className="am-ch-tags">
            {a.member_role === 'owner' && <small className="am-tag">{s.owner}</small>}
            {showGroup && a.group && <small className="am-tag am-tag--g"><bdi>{a.group}</bdi></small>}
            <small className="am-tag am-tag--r" title={s.role_l}><Ic n="sliders" size={11} />{roleLabel(a.role)}</small>
          </div>
        </div>
        <span className="ap-pill" data-st={a.status_code}>{s['st_' + a.status_code] || a.status_code}</span>
      </header>
      {unl ? <p className="am-unl"><Ic n="infinity" size={14} />{s.unl}<small> · {s.unl_no}</small></p> : (
        <div className="am-use"><span className="ap-bar" data-tone={tone}><i style={{ width: `${pct}%` }} /></span><N>{a.usage_percent}%</N></div>
      )}
      <dl className="am-row3">
        <div><dt>{s.limit}</dt><dd><N>{unl ? s.unl : bText(a.admin_limit_bytes)}</N></dd></div>
        <div><dt>{s.used}</dt><dd><N>{a.used_fmt}</N></dd></div>
        <div><dt>{s.remaining}</dt><dd><N>{unl || a.remaining_fmt === 'Unlimited' ? s.unl : a.remaining_fmt}</N></dd></div>
      </dl>
      {(a.balance != null || Number(a.pending?.gb) > 0) && (
        <div className="am-debt">
          {a.balance != null && <span>{s.balance}: <b className="am-bal" data-sign={Number(a.balance) > 0 ? 'owes' : 'zero'}><N>{money(a.balance, lang)}</N></b></span>}
          {Number(a.pending?.gb) > 0 && <span className="am-pend"><Ic n="clock" size={13} />{s.pend}: <N>{gbText(a.pending.gb)}</N></span>}
        </div>
      )}
      <CardUsers a={a} live={full ? live : null} s={s} st={st} />
      {locked ? <p className="am-hint am-foot">{s.sudo}</p> : (
        <div className="am-acts">
          {can('agency.gm.add_volume') && <button type="button" className="ap-link am-pa" disabled={!writable || unl || capReached} title={unl ? s.unl_no : undefined} onClick={() => onAct('add')}><Ic n="plus" />{s.add}</button>}
          {can('agency.gm.view_users') && <button type="button" className="ap-link am-pa" onClick={() => onAct('users')}><Ic n="users" />{s.users}</button>}
          {full && <button type="button" className="ap-link am-pa" onClick={() => onAct('stats')} data-testid="gm-details"><Ic n="gauge" />{st.details}</button>}
          <MoreMenu label={s.more} items={more} />
        </div>
      )}
    </article>
  )
}

/** v1.38.1 compact centred pager: ‹ 1 … 4 5 6 … 12 › */
function Pager({ page, pages, onPage, s }) {
  if (pages <= 1) return null
  const nums = []
  const add = (n) => { if (!nums.includes(n)) nums.push(n) }
  add(1)
  for (let n = Math.max(2, page - 1); n <= Math.min(pages - 1, page + 1); n += 1) add(n)
  add(pages)
  const out = []
  nums.forEach((n, k) => { if (k && n - nums[k - 1] > 1) out.push('gap' + n); out.push(n) })
  return (
    <nav className="am-pg" aria-label={s.pages}>
      <button type="button" className="am-pg-b" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label={s.prev} title={s.prev} data-testid="gm-prev"><span aria-hidden="true">‹</span></button>
      {out.map((n) => (typeof n === 'string' ? <span key={n} className="am-pg-gap" aria-hidden="true">…</span> : (
        <button key={n} type="button" className="am-pg-b" aria-current={n === page ? 'page' : undefined} onClick={() => n !== page && onPage(n)}><N>{n}</N></button>
      )))}
      <button type="button" className="am-pg-b" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label={s.next} title={s.next} data-testid="gm-next"><span aria-hidden="true">›</span></button>
    </nav>
  )
}

// ------------------------------------------------------------------ accounting tab
// v1.37 compact filter bar: period chips + from / to + search + export, one block
const jStr = (c) => toJalaliStr(c.jy, c.jm, c.jd)

function FilterBar({ s, lang, range, setRange, q, setQ, onExport }) {
  const [f, setF] = useState(range.from)
  const [t, setT] = useState(range.to)
  const presets = presetRanges(lang).filter((p) => ['month', 'prevMonth', 'd30'].includes(p.key))
  const norm = (v) => faDigits(v).replace(/-/g, '/').trim()
  const pick = (from, to) => { setF(from); setT(to); setRange({ from, to }) }
  const active = (p) => range.from === jStr(p.from) && range.to === jStr(p.to)
  return (
    <div className="am-fbar am-noprint" data-testid="gm-fbar">
      <div className="am-chips" role="group" aria-label={s.period}>
        {presets.map((p) => <button key={p.key} type="button" className={'am-chip' + (active(p) ? ' on' : '')} aria-pressed={active(p)} onClick={() => pick(jStr(p.from), jStr(p.to))}>{p.label}</button>)}
        <button type="button" className={'am-chip' + (!range.from && !range.to ? ' on' : '')} aria-pressed={!range.from && !range.to} onClick={() => pick('', '')}>{s.clear}</button>
      </div>
      <form className="am-frow" onSubmit={(e) => { e.preventDefault(); setRange({ from: norm(f), to: norm(t) }) }}>
        <input className="ap-input am-in-sm" dir="ltr" placeholder={`${s.from} ${s.date_ph}`} aria-label={s.from} value={f} onChange={(e) => setF(e.target.value)} />
        <input className="ap-input am-in-sm" dir="ltr" placeholder={`${s.to} ${s.date_ph}`} aria-label={s.to} value={t} onChange={(e) => setT(e.target.value)} />
        <button className="ap-link am-btn-sm">{s.apply}</button>
      </form>
      <div className="am-frow">
        <input className="ap-input am-in-sm am-grow" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={s.search_admins} aria-label={s.search_admins} />
        <button type="button" className="ap-link am-btn-sm" onClick={() => onExport('csv')}><Ic n="download" size={14} />{s.csv}</button>
        <button type="button" className="ap-link am-btn-sm" onClick={() => onExport('xlsx')}><Ic n="download" size={14} />{s.xlsx}</button>
      </div>
    </div>
  )
}

function Accounting({ me, s, lang }) {
  const [gid, setGid] = useState(me.groups[0]?.id)
  const [range, setRange] = useState({ from: '', to: '' })
  const [d, setD] = useState(null)
  const [open, setOpen] = useState(null)
  const [q, setQ] = useState('')
  const [size, setSize] = useState(20)
  const [page, setPage] = useState(1)
  const toast = useToast()
  const params = useMemo(() => ({ ...(range.from ? { from: range.from } : {}), ...(range.to ? { to: range.to } : {}) }), [range])
  useEffect(() => { if (!gid) return; setD(null); http.get('/accounting/', { params: { group: gid, ...params } }).then((r) => setD(r.data.groups[0])).catch((e) => toast.error(errText(e, s))) }, [gid, params])
  useEffect(() => { setPage(1) }, [q, size, gid, params])
  const exp = (url, fmt, extra = {}) => download(url, { ...params, ...extra, export: fmt, lang }, `export.${fmt}`).catch((e) => toast.error(errText(e, s)))
  if (!gid) return null
  const rows = d ? d.admins.filter((r) => !q.trim() || r.username.toLowerCase().includes(q.trim().toLowerCase())) : []
  const pages = Math.max(1, Math.ceil(rows.length / size))
  const shown = rows.slice((page - 1) * size, page * size)
  return (
    <>
      {me.groups.length > 1 && (
        <div className="am-seg am-noprint">{me.groups.map((g) => <button key={g.id} type="button" className={'am-tab' + (gid === g.id ? ' on' : '')} onClick={() => { setGid(g.id); setOpen(null) }}><bdi>{g.name}</bdi></button>)}</div>
      )}
      <section className="ap-card am-noprint am-accw">
        <FilterBar s={s} lang={lang} range={range} setRange={setRange} q={q} setQ={setQ} onExport={(fmt) => exp('/accounting/', fmt, { group: gid })} />
        {!d ? <div className="ap-spin" /> : (
          <>
            <div className="am-kpis" data-testid="gm-kpis">
              <div data-strong><span>{s.group_debt}</span><b className="am-bal" data-sign={Number(d.total_debt) > 0 ? 'owes' : 'zero'}><N>{money(d.total_debt, lang)}</N></b></div>
              <div><span>{s.pending_sep}</span><b><N>{gbText(d.pending_gb)}</N> · <N>{toman(d.pending_amount, lang)}</N></b></div>
            </div>
            <ul className="am-acc" data-testid="gm-acc-list">
              {shown.map((r) => (
                <li key={r.username}>
                  <div className="am-acc-r">
                    <b><bdi>{r.username}</bdi></b>
                    <span>{s.charges}: <N>{toman(r.charges, lang)}</N></span>
                    {Number(r.adjustments || 0) !== 0 && <span>{lang === 'fa' ? 'اصلاحیه‌ها' : 'Adjustments'}: <N>{toman(r.adjustments, lang)}</N></span>}
                    {r.archived && <span className="am-pend">{lang === 'fa' ? 'بایگانی (حذف‌شده)' : 'Archived (deleted)'}</span>}
                    <span>{s.payments}: <N>{toman(r.payments, lang)}</N></span>
                    <span>{s.balance}: <span className="am-bal" data-sign={Number(r.balance) > 0 ? 'owes' : 'zero'}><N>{money(r.balance, lang)}</N></span></span>
                    {Number(r.pending.gb) > 0 && <span className="am-pend">{s.pend}: <N>{gbText(r.pending.gb)}</N> · <N>{toman(r.pending.amount, lang)}</N></span>}
                    <button type="button" className="ap-link am-btn-sm" aria-expanded={open === r.username} onClick={() => setOpen(open === r.username ? null : r.username)}><Ic n="doc" size={14} />{open === r.username ? s.hide : s.statement}</button>
                  </div>
                  {open === r.username && <AdminStatement username={r.username} params={params} s={s} lang={lang} exp={exp} />}
                </li>
              ))}
            </ul>
            {rows.length === 0 && <p className="ap-foot">{s.no_match}</p>}
            <div className="am-pager am-pager--acc">
              <label className="am-psize"><span>{s.per_page}</span>
                <select className="ap-input am-in-sm" value={size} onChange={(e) => setSize(Number(e.target.value))} data-testid="gm-psize">
                  {[20, 50, 100].map((n) => <option key={n} value={n}>{n}</option>)}</select></label>
              <Pager page={page} pages={pages} onPage={setPage} s={s} />
            </div>
          </>
        )}
      </section>
      <StaffGroupStatement url={`${BASE}/groups/${gid}/statement/`} />
      {/* v1.54 «تاریخچه»: my groups' admins + group totals, never reset by a settlement / payments / adjustments */}
      <AgencyHistory http={http} base="/history/" lang={lang} />
    </>
  )
}

const Kind = ({ k, s }) => <span className="ap-st-k" data-kind={k}>{s['k_' + k] || k}</span>

function AdminStatement({ username, params, s, lang, exp }) {
  const [st, setSt] = useState(null)
  const url = `/admins/${encodeURIComponent(username)}/statement/`
  useEffect(() => { http.get(url, { params }).then((r) => setSt(r.data)).catch(() => setSt(false)) }, [username, params])
  if (st === null) return <div className="ap-spin" />
  if (!st) return <div className="ap-alert">{s.error}</div>
  return (
    <div className="am-st">
      <div className="am-row am-exp">
        <button type="button" className="ap-link" onClick={() => exp(url, 'csv')}><Ic n="download" />{s.csv}</button>
        <button type="button" className="ap-link" onClick={() => exp(url, 'xlsx')}><Ic n="download" />{s.xlsx}</button>
      </div>
      {!st.entries.length ? <p className="ap-foot">{s.none}</p> : (
        <ul className="ap-st">
          {[...st.entries].reverse().map((e) => (
            <li key={e.id} data-voided={e.voided || undefined}>
              <Kind k={e.kind} s={s} />
              <span className="ap-st-d">{jalali(e.date, false, lang)}</span>
              <span className="ap-st-a" data-sign={e.voided ? 'zero' : Number(e.signed) < 0 ? 'credit' : 'owes'}><N>{Number(e.signed) < 0 ? '−' : '+'}{toman(Math.abs(Number(e.amount)), lang)}</N></span>
              <span className="ap-st-r">{s.running}: <N>{money(e.balance, lang)}</N>{e.gb && <> · <N>{gbText(e.gb)}</N></>}{e.voided && ` · ${s.voided}`}</span>
              {e.note && <span className="ap-st-n">{(lang === 'fa' && e.note_fa) || e.note}</span>}
            </li>
          ))}
        </ul>
      )}
      {st.pending?.length > 0 && <Pending rows={st.pending} s={s} lang={lang} />}
    </div>
  )
}

function Pending({ rows, s, lang }) {
  return (
    <div className="am-pendbox">
      <h4>{s.pending_sep}</h4>
      <ul>{rows.map((p) => <li key={p.id}><span>{jalali(p.date, false, lang)}</span><bdi>{p.admin}</bdi><N>+{gbText(p.gb)}</N><N>{p.price_per_gb != null ? toman(p.amount, lang) : s.no_price}</N></li>)}</ul>
    </div>
  )
}

// ------------------------------------------------------------------ settings tab (v1.25.5)
/** v1.37: sound on a new notification + browser push (the manager's own browsers). */
function NotifyCard({ s }) {
  const { refreshMe } = useAuth()
  const toast = useToast()
  const [p, setP] = useState(null)
  const [push, setPush] = useState(null)
  const [sub, setSub] = useState(false)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    http.get('/prefs/').then((r) => setP(r.data)).catch(() => setP({ sound: true, volume: 60 }))
    http.get('/push/').then((r) => setPush(r.data)).catch(() => setPush({ enabled: false }))
    currentSubscription(PUSH_BASE).then((x) => setSub(!!x)).catch(() => {})
  }, [])
  const save = async (next) => {
    setP(next)
    try { await api.patch(BASE + '/prefs/', next, { quiet: true }); refreshMe?.() } catch (e) { toast.error(errText(e, s)) }
  }
  const togglePush = async (on) => {
    setBusy(true)
    try {
      if (on) { const json = await subscribePush(PUSH_BASE, push.public_key); await http.post('/push/subscribe/', { subscription: json }); setSub(true) }
      else { const ep = await unsubscribePush(PUSH_BASE); if (ep) await http.post('/push/unsubscribe/', { endpoint: ep }); setSub(false) }
    } catch (e) {
      toast.error(e?.message === 'denied' ? s.push_denied : e?.message === 'unsupported' ? s.push_unsupported : errText(e, s))
    } finally { setBusy(false) }
  }
  if (!p) return null
  return (
    <section className="ap-card am-set-card" data-testid="gm-notify">
      <h2><Ic n="bell" size={16} />{s.set_notify}</h2>
      <div className="am-set-pref"><span><b>{s.set_sound}</b><small>{s.set_sound_d}</small></span>
        <Toggle checked={!!p.sound} onChange={(v) => save({ ...p, sound: v })} label={s.set_sound} /></div>
      <label className="am-vol"><span>{s.set_volume} <N>{p.volume}%</N></span>
        <input type="range" min="0" max="100" step="5" value={p.volume} disabled={!p.sound} onChange={(e) => setP({ ...p, volume: Number(e.target.value) })}
          onPointerUp={() => save(p)} onKeyUp={() => save(p)} aria-label={s.set_volume} /></label>
      <button type="button" className="ap-link am-btn-sm" disabled={!p.sound} onClick={async () => { await unlockSound(); playChime(p.volume, 'default') }}>▶ {s.set_test}</button>
      <div className="am-set-sep" />
      {push === null ? null : !push.enabled ? <p className="am-hint">{s.push_off}</p> : !pushSupported() ? <p className="am-hint">{needsHomeScreen() ? s.push_ios : s.push_unsupported}</p> : (
        <>
          <div className="am-set-pref"><span><b>{s.set_push}</b><small>{s.set_push_d}</small></span>
            <Toggle checked={sub} onChange={busy ? () => {} : togglePush} label={s.set_push} /></div>
          {sub && <button type="button" className="ap-link am-btn-sm" onClick={() => http.post('/push/test/', {})}>{s.set_push_test}</button>}
        </>
      )}
    </section>
  )
}

function SettingsTab({ me, s }) {
  const { staff } = useAuth()
  const { lang, setLang } = useI18n()
  const { mode, toggle, locked } = useTheme()
  const toast = useToast()
  const [pw, setPw] = useState({ cur: '', neu: '', rep: '' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const m = me.manager
  const role = (lang === 'fa' && (m.role_fa || staff?.role_fa)) || m.role || staff?.role || ''
  const submit = async (e) => {
    e.preventDefault(); setErr('')
    if (pw.neu !== pw.rep) { setErr(s.set_pw_mismatch); return }
    setBusy(true)
    try {
      const r = await http.post('/password/', { current_password: pw.cur, new_password: pw.neu }, { quiet: true })
      tokens.set(r.data)                              // this session continues with fresh tokens
      setPw({ cur: '', neu: '', rep: '' }); toast.success(s.set_pw_done)
    } catch (e2) { const msg = errText(e2, s); setErr(msg) } finally { setBusy(false) }
  }
  const Seg = ({ value, opts, onPick, label }) => (
    <div className="am-seg2" role="radiogroup" aria-label={label}>
      {opts.map(([v, t]) => <button key={v} type="button" role="radio" aria-checked={value === v} className={value === v ? 'on' : ''} onClick={() => value !== v && onPick(v)}>{t}</button>)}
    </div>
  )
  return (
    <div className="am-set">
      <section className="ap-card am-set-card">
        <h2>{s.set_profile}</h2>
        <div className="am-set-who">
          <span className="am-set-av">{(m.username || '?').charAt(0).toUpperCase()}</span>
          <span><b dir="ltr">{m.username}</b>{m.display_name && <small>{m.display_name}</small>}</span>
        </div>
        <dl className="am-set-dl">
          <div><dt>{s.set_role}</dt><dd>{role || '—'}</dd></div>
          <div><dt>{s.set_cap}</dt><dd>{me.cap?.max_gb != null ? <N>{gbText(me.cap.max_gb)}</N> : s.no_cap}</dd></div>
          <div className="am-set-wide"><dt>{s.set_groups}</dt><dd>
            {me.groups.length === 0 ? s.no_groups : (
              <ul className="am-set-groups">{me.groups.map((g) => (
                <li key={g.id}><b><bdi>{g.name}</bdi></b><span className="am-set-roles">{g.roles.length ? g.roles.map((r) => <span key={r.id}><b>{roleLabel(r)}</b></span>) : '—'}</span></li>
              ))}</ul>
            )}
          </dd></div>
        </dl>
      </section>
      <section className="ap-card am-set-card">
        <h2>{s.set_pw}</h2>
        <form className="am-form" onSubmit={submit}>
          <label>{s.set_pw_cur}<input className="ap-input" type="password" dir="ltr" autoComplete="current-password" required value={pw.cur} onChange={(e) => setPw({ ...pw, cur: e.target.value })} /></label>
          <label>{s.set_pw_new}<input className="ap-input" type="password" dir="ltr" autoComplete="new-password" required minLength={8} value={pw.neu} onChange={(e) => setPw({ ...pw, neu: e.target.value })} /></label>
          <label>{s.set_pw_rep}<input className="ap-input" type="password" dir="ltr" autoComplete="new-password" required minLength={8} value={pw.rep} onChange={(e) => setPw({ ...pw, rep: e.target.value })} /></label>
          <p className="am-hint">{s.set_pw_note}</p>
          {err && <div className="ap-alert" role="alert">{err}</div>}
          <div className="am-row"><button className="ap-btn am-btn" disabled={busy || pw.neu.length < 8 || !pw.cur}>{busy ? <span className="ap-btn-spin" /> : <Ic n="check" />}{s.save}</button></div>
        </form>
      </section>
      <section className="ap-card am-set-card">
        <h2>{s.set_prefs}</h2>
        <div className="am-set-pref"><span>{s.set_lang}</span><Seg label={s.set_lang} value={lang} onPick={setLang} opts={[['fa', 'فارسی'], ['en', 'English']]} /></div>
        {!locked && <div className="am-set-pref"><span>{s.set_theme}</span><Seg label={s.set_theme} value={mode} onPick={() => toggle()} opts={[['light', s.light], ['dark', s.dark]]} /></div>}
      </section>
      <NotifyCard s={s} />
      <div className="am-set-out"><LogoutButton testId="gm-settings-logout" /></div>
    </div>
  )
}

// ------------------------------------------------------------------ activity tab (v1.37)
const ACT_KINDS = ['create', 'volume', 'status', 'password', 'role', 'profile', 'payment', 'request', 'login']
const ACT_ICON = { create: 'plus', volume: 'gauge', status: 'power', password: 'key', role: 'sliders', profile: 'edit', payment: 'money', request: 'clock', login: 'login', other: 'doc' }

function actLabel(a, s) {
  const k = a.action.split('.').pop()
  if (a.type === 'payment') return s.acts['pay_' + k] || s.acts.pay_created
  if (a.type === 'request') return s.acts.request_created
  return s.acts[k] || k
}

function Activity({ s, lang }) {
  const [kind, setKind] = useState('')
  const [admin, setAdmin] = useState('')
  const [page, setPage] = useState(1)
  const [d, setD] = useState(null)
  useEffect(() => {
    let stop = false
    http.get('/activity/', { params: { type: kind || undefined, admin: admin || undefined, page } })
      .then((r) => { if (!stop) setD(r.data) }).catch(() => { if (!stop) setD({ results: [], pages: 1, page: 1, admins: [] }) })
    return () => { stop = true }
  }, [kind, admin, page])
  return (
    <section className="ap-card am-actw" data-testid="gm-activity">
      <div className="am-chips am-chips--act" role="group" aria-label={s.type}>
        <button type="button" className={'am-chip' + (!kind ? ' on' : '')} aria-pressed={!kind} onClick={() => { setKind(''); setPage(1) }}>{s.u_all}</button>
        {ACT_KINDS.map((k) => (
          <button key={k} type="button" className={'am-chip am-chip--k' + (kind === k ? ' on' : '')} data-k={k} aria-pressed={kind === k} onClick={() => { setKind(kind === k ? '' : k); setPage(1) }}>
            <Ic n={ACT_ICON[k]} size={13} />{s.act_types[k]}</button>))}
      </div>
      <label className="am-sort am-sort--act"><span>{s.admin}</span>
        <select className="ap-input am-in-sm" value={admin} onChange={(e) => { setAdmin(e.target.value); setPage(1) }} data-testid="gm-act-admin">
          <option value="">{s.u_all}</option>{(d?.admins || []).map((u) => <option key={u} value={u}>{u}</option>)}
        </select></label>
      {d === null ? <div className="ap-spin" /> : d.results.length === 0 ? <p className="ap-empty">{s.act_none}</p> : (
        <ul className="am-act2">
          {d.results.map((a) => {
            const det = a.detail || {}
            return (
              <li key={a.id} data-k={a.type}>
                <span className="am-act2-ic" aria-hidden="true"><Ic n={ACT_ICON[a.type] || 'doc'} size={16} /></span>
                <div className="am-act2-b">
                  <div className="am-act2-t"><b>{actLabel(a, s)}</b>{a.admin && <bdi className="am-act2-who">{a.admin}</bdi>}</div>
                  <div className="am-act2-d">
                    {det.gb && <span><N>+{gbText(det.gb)}</N></span>}
                    {det.new_role && <span>{det.old_role ? `${det.old_role} → ` : ''}{det.new_role}</span>}
                    {det.amount && <span><N>{toman(det.total || det.amount, lang)}</N></span>}
                    {det.invoices && <span><N>{det.invoices.join('، ')}</N></span>}
                    {det.payment && <span><N>{det.payment}</N></span>}
                    {det.reason && <span className="am-act2-r">{det.reason}</span>}
                  </div>
                  <div className="am-act2-m">{a.group && <bdi>{a.group}</bdi>}{a.by && <> · <bdi dir="ltr">{a.by}</bdi></>} · <span title={jalali(a.at, true, lang)}>{jalali(a.at, true, lang)}</span></div>
                </div>
              </li>
            )
          })}
        </ul>
      )}
      {d && <Pager page={d.page} pages={d.pages} onPage={setPage} s={s} />}
    </section>
  )
}

const CSS = `
.am-search { width: 100%; max-width: 420px; }
.am-danger { color: var(--c-danger) !important; }
.ap-btn[data-tone="danger"] { background: var(--c-danger); }
.am-confirm { font-size: 14px; line-height: 1.8; color: var(--c-text); }
.am-users { min-width: 0; }
.am-ufilter { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; }
.am-ulist { display: flex; flex-direction: column; gap: 8px; max-height: 55vh; overflow-y: auto; }
.am-ulist li { padding: 10px 12px; border: 1px solid var(--c-border); border-radius: 12px; display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.am-u-h { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-width: 0; }
.am-u-h b { overflow-wrap: anywhere; min-width: 0; }
.am-u-st { font-size: 11px; font-weight: 700; padding: 1px 8px; border-radius: 999px; border: 1px solid var(--c-border); white-space: nowrap; }
.am-u-st[data-st="active"] { color: var(--c-success); } .am-u-st[data-st="disabled"], .am-u-st[data-st="expired"] { color: var(--c-danger); }
.am-u-st[data-st="limited"] { color: var(--c-warning); } .am-u-st[data-st="on_hold"] { color: var(--c-primary); }
.am-u-b { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 12.5px; color: var(--c-muted-fg); }
.am-u-on { color: var(--c-success); }
.am-pager { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 12.5px; flex-wrap: wrap; }
.am-set-roles { display: flex; flex-direction: column; gap: 4px; margin-top: 4px; }
.am-set-roles > span { display: flex; flex-direction: column; }
.am-set-roles small { font-size: 11.5px; font-weight: 500; color: var(--c-muted-fg); }
.am-pick .am-form { margin-top: 10px; }
.am-acc-r b, .am-acc-r bdi, .am-card h3 bdi, .ap-st bdi { overflow-wrap: anywhere; min-width: 0; }
.ap-st-n { flex-basis: 100%; font-size: 12px; color: var(--c-muted-fg); overflow-wrap: break-word; }
.am-set { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 320px), 1fr)); align-items: start; }
.am-set-card h2 { font-size: 15px; font-weight: 800; margin-bottom: 12px; }
.am-set-who { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.am-set-who span:last-child { display: flex; flex-direction: column; min-width: 0; }
.am-set-who b { font-size: 15px; text-align: start; overflow-wrap: anywhere; }
.am-set-who small { font-size: 12px; color: var(--c-muted-fg); }
.am-set-av { width: 44px; height: 44px; flex-shrink: 0; border-radius: 999px; display: grid; place-items: center; font-weight: 800; font-size: 17px; color: #fff; background: var(--c-primary); }
.am-set-dl { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.am-set-dl > div { padding: 9px 12px; border: 1px solid var(--c-border); border-radius: 12px; min-width: 0; }
.am-set-dl dt { font-size: 11.5px; font-weight: 700; color: var(--c-muted-fg); }
.am-set-dl dd { font-size: 14px; font-weight: 700; margin-top: 2px; overflow-wrap: anywhere; }
.am-set-wide { grid-column: 1 / -1; }
.am-set-groups li { display: flex; flex-direction: column; padding: 6px 0; border-top: 1px solid var(--c-border); }
.am-set-groups li:first-child { border-top: 0; padding-top: 0; }
.am-set-groups small { font-size: 12px; font-weight: 500; color: var(--c-muted-fg); }
.am-set-pref { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--c-border); }
.am-set-pref > span { font-size: 13px; font-weight: 700; }
.am-seg2 { display: inline-flex; padding: 3px; gap: 3px; border-radius: 11px; border: 1px solid var(--c-border); }
.am-seg2 button { min-height: 34px; padding: 5px 14px; border-radius: 8px; font-size: 13px; font-weight: 700; color: var(--c-muted-fg); background: transparent; border: 0; cursor: pointer; }
.am-seg2 button.on { color: #fff; background: var(--c-primary); }
.am-set-out { margin-top: 14px; width: 100%; display: flex; align-items: center; justify-content: center; gap: 8px; min-height: 44px; border-radius: 12px;
  font-weight: 700; font-size: 14px; color: var(--c-danger); background: transparent; border: 1px solid color-mix(in srgb, var(--c-danger) 40%, transparent); cursor: pointer; }
.am-set-out:hover { background: color-mix(in srgb, var(--c-danger) 10%, transparent); }
.am-set-out svg { width: 18px; height: 18px; }
.ap.am-in { min-height: auto; background: transparent; display: flex; flex-direction: column; gap: 14px; }
.am-h1 { font-size: 18px; font-weight: 800; }
.am-pick h2 { font-size: 15px; font-weight: 800; margin-bottom: 10px; }
.am-pick .am-btn { margin-top: 0; }
.am-main { max-width: 1100px; }
.am-who { font-weight: 600; color: var(--c-muted-fg); }
.am-tabs, .am-seg { display: flex; gap: 6px; flex-wrap: wrap; }
.am-tab { display: inline-flex; align-items: center; gap: 6px; min-height: 42px; padding: 0 16px; border-radius: 12px; border: 1px solid var(--c-border); background: transparent; color: var(--c-text); font-weight: 800; font-size: 14px; }
.am-tab.on { background: color-mix(in srgb, var(--c-primary) 82%, #000); border-color: transparent; color: #fff; }
.am-tabs .am-tab { flex: 1 1 0; justify-content: center; }
.am-cap { margin: 0; }
.am-group { display: flex; flex-direction: column; gap: 10px; }
.am-gh { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; }
.am-gh h2 { display: inline-flex; align-items: center; gap: 6px; font-size: 17px; font-weight: 800; }
.am-debt { font-size: 13px; font-weight: 700; color: var(--c-muted-fg); }
.am-btn { margin-top: 0; min-height: 44px; padding: 0 16px; display: inline-flex; align-items: center; gap: 6px; }
.am-new { margin-inline-start: auto; }
/* v1.38.1 cards: 1 / 2 / 3 columns by the list's own width; a short last row spans the free width (no empty slot) */
.am-gridw { container-type: inline-size; }
.am-grid { display: grid; gap: 12px; grid-template-columns: minmax(0, 1fr); align-items: stretch; }
@container (min-width: 600px) {
  .am-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .am-grid > :last-child:nth-child(odd) { grid-column: 1 / -1; }
}
@container (min-width: 1080px) {
  .am-grid { grid-template-columns: repeat(6, minmax(0, 1fr)); }
  .am-grid > * { grid-column: span 2; }
  .am-grid > :last-child:nth-child(odd) { grid-column: span 2; }
  .am-grid > :last-child:nth-child(3n+1) { grid-column: 1 / -1; }
  .am-grid > :nth-last-child(2):nth-child(3n+1), .am-grid > :nth-last-child(2):nth-child(3n+1) + * { grid-column: span 3; }
}
.am-card { display: flex; flex-direction: column; gap: 10px; padding: 14px; min-width: 0; }
.am-ch { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.am-ch-n { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.am-ch-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.am-card h3 { font-size: 15.5px; font-weight: 800; line-height: 1.3; }
.am-tag { display: inline-flex; align-items: center; gap: 4px; }
.am-tag--r { color: var(--c-text); background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); font-weight: 600; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.am-use { display: flex; align-items: center; gap: 10px; font-size: 12.5px; font-weight: 800; }
.am-use .ap-bar { flex: 1 1 auto; height: 8px; }
.am-unl { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: 12.5px; font-weight: 700; color: var(--c-primary-fg, var(--c-primary)); }
.am-unl small { font-weight: 600; color: var(--c-muted-fg); }
.am-row3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border: 1px solid var(--c-border); border-radius: 12px; }
.am-row3 > div { padding: 7px 10px; min-width: 0; }
.am-row3 > div + div { border-inline-start: 1px solid var(--c-border); }
.am-row3 dt { font-size: 11px; font-weight: 600; color: var(--c-muted-fg); }
.am-row3 dd { font-size: 13px; font-weight: 800; margin-top: 1px; overflow-wrap: anywhere; }
.am-debt { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 4px 12px; font-size: 12.5px; font-weight: 600; color: var(--c-muted-fg); }
.am-debt b { font-size: 13.5px; font-weight: 800; }
.am-uc { display: flex; flex-wrap: wrap; align-items: center; gap: 5px; }
.am-uc-t { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; font-weight: 600; color: var(--c-muted-fg); margin-inline-end: 2px; }
.am-uc-t b { color: var(--c-text); font-size: 13px; }
.am-card .am-acts { margin-top: auto; padding-top: 10px; border-top: 1px solid var(--c-border); flex-wrap: nowrap; }
.am-card { container-type: inline-size; }
.am-card .am-acts { gap: 5px; }
.am-card .am-acts .am-pa { flex: 1 1 auto; min-width: 0; padding: 0 8px; gap: 5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
/* narrow cards (phones, 3 columns): labels only, so «افزودن حجم» never gets cut */
@container (max-width: 400px) { .am-card .am-acts .am-pa svg { display: none; } .am-card .am-acts .am-pa { padding: 0 6px; font-size: 12.5px; } }
.am-card .am-acts .am-pa svg { flex-shrink: 0; }
.am-more { flex: 0 0 auto !important; width: 40px; padding: 0 !important; }
.am-foot { margin-top: auto; }
.am-menu { position: fixed; z-index: 95; padding: 6px; border-radius: 14px; background: var(--c-bg); border: 1px solid var(--c-border);
  box-shadow: 0 12px 40px rgb(0 0 0 / .22); display: flex; flex-direction: column; }
.am-menu-i { display: flex; align-items: center; flex-wrap: wrap; gap: 4px 10px; min-height: 44px; padding: 6px 10px; border-radius: 10px; border: 0; background: transparent;
  color: var(--c-text); font: inherit; font-size: 13.5px; font-weight: 700; text-align: start; cursor: pointer; }
.am-menu-i:hover:not(:disabled), .am-menu-i:focus-visible { background: color-mix(in srgb, var(--c-primary) 9%, transparent); outline: none; }
.am-menu-i[data-tone="danger"] { color: var(--c-danger-fg); }
.am-menu-i[data-tone="danger"]:hover:not(:disabled) { background: color-mix(in srgb, var(--c-danger) 10%, transparent); }
.am-menu-i:disabled { opacity: .55; cursor: not-allowed; }
.am-menu-i small { flex-basis: 100%; font-size: 11.5px; font-weight: 600; color: var(--c-muted-fg); padding-inline-start: 25px; }
.am-pg { display: flex; align-items: center; justify-content: center; gap: 4px; margin: 14px auto 0; flex-wrap: wrap; }
.am-pg-b { min-width: 36px; height: 36px; padding: 0 8px; border-radius: 10px; border: 1px solid var(--c-border); background: transparent; color: var(--c-text);
  font: inherit; font-size: 13px; font-weight: 700; cursor: pointer; display: inline-grid; place-items: center; }
.am-pg-b span { font-size: 18px; line-height: 1; }
.am-pg-b:hover:not(:disabled) { background: color-mix(in srgb, var(--c-primary) 8%, transparent); }
.am-pg-b[aria-current="page"] { background: var(--c-primary); border-color: var(--c-primary); color: #fff; }
.am-pg-b:disabled { opacity: .4; cursor: not-allowed; }
.am-pg-gap { min-width: 16px; text-align: center; color: var(--c-muted-fg); }
.am-count--c { text-align: center; margin-top: 10px; }
@media (max-width: 767px) { .am-pg-b { min-width: 44px; height: 44px; } .am-pg { gap: 3px; } .am-more { width: 44px; } .am-card .am-acts .ap-link { min-height: 44px; } }
.am-card h3 { font-size: 16px; font-weight: 800; overflow-wrap: anywhere; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.am-tag { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 999px; background: color-mix(in srgb, var(--c-primary) 12%, transparent); color: var(--c-primary-fg, var(--c-primary)); }
.am-nums { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 6px; }
.am-nums > div { padding: 8px 10px; border-radius: 12px; border: 1px solid var(--c-border); min-width: 0; }
.am-nums > div[data-strong] { border-color: color-mix(in srgb, var(--c-danger) 35%, var(--c-border)); }
.am-nums dt { font-size: 11.5px; font-weight: 600; color: var(--c-muted-fg); }
.am-nums dd { font-size: 14.5px; font-weight: 800; margin-top: 2px; overflow-wrap: anywhere; }
.am-nums dd small { font-weight: 600; color: var(--c-muted-fg); }
.am-sum { grid-template-columns: repeat(auto-fit, minmax(min(100%, 160px), 1fr)); }
.am-role { font-size: 12.5px !important; overflow-wrap: anywhere; }
.am-bal { font-weight: 800; }
.am-bal[data-sign="owes"] { color: var(--c-danger-fg); } .am-bal[data-sign="credit"] { color: var(--c-success-fg); } .am-bal[data-sign="zero"] { color: var(--c-muted-fg); }
.am-pend { display: inline-flex; align-items: center; gap: 5px; font-size: 12.5px; font-weight: 700; color: var(--c-warning-fg); }
.am-acts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.am-acts .ap-link { margin: 0; flex: 1 1 auto; }
.ap-link:disabled { opacity: .5; cursor: not-allowed; }
.am-hint { font-size: 12px; color: var(--c-muted-fg); line-height: 1.7; }
.am-back { position: fixed; inset: 0; z-index: 50; background: rgba(0,0,0,.45); display: grid; place-items: center; padding: 16px; }
.am-dlg { width: min(100%, 480px); max-height: 90vh; overflow: auto; background: var(--c-bg); border: 1px solid var(--c-border); border-radius: 18px; padding: 16px; }
.am-dlg-h { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 10px; font-size: 16px; }
.am-x { width: 40px; height: 40px; display: grid; place-items: center; border-radius: 10px; border: 0; background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); color: var(--c-text); }
.am-form { display: flex; flex-direction: column; gap: 10px; }
.am-form label { display: flex; flex-direction: column; gap: 5px; font-size: 12.5px; font-weight: 700; }
.am-l { font-size: 12.5px; font-weight: 700; }
.am-pw { display: flex; gap: 6px; align-items: center; }
.am-pw .ap-input { flex: 1; min-width: 0; }
.am-pw .ap-link { margin: 0; white-space: nowrap; }
.am-row { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; align-items: center; }
.am-row .ap-link { margin: 0; }
.am-exp { justify-content: flex-start; margin: 8px 0; }
.am-roles { display: flex; flex-direction: column; gap: 6px; }
.am-form .am-rolei { flex-direction: row; align-items: center; gap: 10px; padding: 9px 12px; border-radius: 12px; border: 1px solid var(--c-border); font-weight: 500; min-height: 44px; }
.am-rolei[data-on] { border-color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 8%, transparent); }
.am-rolei span { display: flex; flex-direction: column; }
.am-rolei small { color: var(--c-muted-fg); font-size: 11.5px; }
.am-cmp { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 8px; }
.am-cmp > div { padding: 10px; border-radius: 12px; border: 1px solid var(--c-border); }
.am-cmp > div[data-strong] { border-color: var(--c-primary); }
.am-cmp dt { font-size: 11.5px; color: var(--c-muted-fg); font-weight: 700; }
.am-cmp dd { font-size: 15px; font-weight: 800; overflow-wrap: anywhere; }
.am-range { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 8px; }
.am-range label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; font-weight: 700; flex: 1 1 calc(50% - 8px); min-width: 0; }
.am-range .ap-link { margin: 0; flex: 1 1 auto; }
.am-acc { display: flex; flex-direction: column; margin-top: 4px; }
.am-acc > li { border-top: 1px solid var(--c-border); padding: 10px 0; }
.am-acc-r { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 14px; font-size: 13px; }
.am-acc-r .ap-link { margin-inline-start: auto; }
.am-st { padding: 6px 0 0; }
.am-pendbox { margin-top: 10px; padding: 10px 12px; border-radius: 12px; background: color-mix(in srgb, var(--c-warning) 9%, transparent); }
.am-pendbox h4 { font-size: 13px; font-weight: 800; color: var(--c-warning-fg); margin-bottom: 4px; }
.am-pendbox li { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 12.5px; padding: 4px 0; }
.am-gst-h { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; }
.am-gst-h h2 { display: inline-flex; align-items: center; gap: 6px; font-size: 16px; font-weight: 800; }
.am-tw { overflow-x: auto; margin-top: 10px; }
.am-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.am-table th { text-align: start; font-size: 11.5px; color: var(--c-muted-fg); font-weight: 700; padding: 6px 8px; border-bottom: 1px solid var(--c-border); white-space: nowrap; }
.am-table td { padding: 8px; border-bottom: 1px solid var(--c-border); white-space: nowrap; }
.am-table tr[data-voided] { opacity: .5; }
.am-act { display: flex; flex-direction: column; }
.am-act li { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; padding: 9px 0; border-top: 1px solid var(--c-border); font-size: 13px; }
.am-act li:first-child { border-top: 0; }
.am-act-t { margin-inline-start: auto; font-size: 12px; color: var(--c-muted-fg); }
@media (max-width: 639px) {
  .am-table thead { display: none; }
  .am-table tr { display: grid; grid-template-columns: auto 1fr auto; gap: 2px 10px; padding: 8px 0; border-bottom: 1px solid var(--c-border); }
  .am-table td { padding: 0; border: 0; white-space: normal; }
  .am-new { margin-inline-start: 0; width: 100%; justify-content: center; }
  .am-acc-r .ap-link { margin-inline-start: 0; }
}
@media print {
  .am-noprint, .ap-top { display: none !important; }
  .am-gst { border: 0; }
}

/* v1.37 admins list */
.am-gsum { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.am-gchip { display: inline-flex; align-items: center; gap: 6px; min-height: 44px; padding: 0 14px; border-radius: 999px; border: 1px solid var(--c-border);
  background: transparent; color: var(--c-text); font-size: 13px; font-weight: 800; }
.am-gchip small { font-weight: 600; color: var(--c-muted-fg); font-size: 12px; }
.am-gchip.on { border-color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 10%, transparent); }
.am-gsum .am-new { margin-inline-start: auto; }
.am-tools { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; align-items: end; margin-top: 10px; }
.am-tools .am-search { margin: 0; }
.am-sort { display: flex; flex-direction: column; gap: 3px; font-size: 11.5px; font-weight: 700; color: var(--c-muted-fg); }
.am-sort select { min-width: 150px; }
.am-count { font-size: 12px; color: var(--c-muted-fg); margin: 8px 2px 4px; }
.am-tag--g { color: var(--c-primary-fg, var(--c-primary)); background: color-mix(in srgb, var(--c-primary) 10%, transparent); }
.am-pager { display: flex; align-items: center; justify-content: center; flex-wrap: wrap; gap: 10px; margin-top: 14px; font-size: 13px; }
.am-pager--acc { justify-content: space-between; }
.am-psize { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--c-muted-fg); font-weight: 700; }
.am-psize select { width: 84px; }
/* «خروج» at the bottom of Settings on phones only (desktop: bottom of the sidebar) */
.am-set-out { margin-top: 4px; }
@media (min-width: 768px) { .am-set-out { display: none; } }
.am-pager--acc .am-pg { margin: 0; }
.am-pair { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 190px), 1fr)); gap: 10px; }
/* v1.37 compact accounting */
.am-accw { display: flex; flex-direction: column; gap: 12px; }
.am-fbar { display: flex; flex-direction: column; gap: 8px; }
.am-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.am-chip { display: inline-flex; align-items: center; gap: 5px; min-height: 36px; padding: 0 12px; border-radius: 999px; border: 1px solid var(--c-border);
  background: transparent; color: var(--c-text); font-size: 12.5px; font-weight: 700; }
.am-chip.on { background: var(--c-primary); border-color: var(--c-primary); color: #fff; }
.am-frow { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.am-in-sm { height: 38px; min-height: 38px; padding: 0 10px; font-size: 13px; border-radius: 10px; width: 150px; }
.am-grow { flex: 1 1 160px; width: auto; }
.am-btn-sm { min-height: 38px; padding: 0 12px; font-size: 12.5px; display: inline-flex; align-items: center; gap: 5px; }
.am-kpis { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.am-kpis > div { display: flex; flex-direction: column; gap: 2px; padding: 10px 12px; border-radius: 12px; border: 1px solid var(--c-border); min-width: 0; }
.am-kpis > div[data-strong] { border-color: color-mix(in srgb, var(--c-danger) 35%, var(--c-border)); }
.am-kpis span { font-size: 11.5px; font-weight: 700; color: var(--c-muted-fg); }
.am-kpis b { font-size: 16px; font-weight: 900; overflow-wrap: anywhere; }
/* v1.37 activity */
.am-actw { display: flex; flex-direction: column; gap: 10px; }
.am-chip--k[data-k] svg { color: var(--k); }
.am-chip--k.on svg { color: #fff; }
.am-sort--act { flex-direction: row; align-items: center; gap: 8px; }
.am-sort--act select { width: auto; min-width: 160px; }
.am-act2 { display: flex; flex-direction: column; }
.am-act2 li { display: grid; grid-template-columns: 36px minmax(0, 1fr); gap: 10px; padding: 10px 0; border-top: 1px solid var(--c-border); }
.am-act2 li:first-child { border-top: 0; }
.am-act2-ic { width: 36px; height: 36px; border-radius: 11px; display: grid; place-items: center; color: var(--k); background: color-mix(in srgb, var(--k) 14%, transparent); }
.am-act2-b { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.am-act2-t { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px; font-size: 13.5px; }
.am-act2-who { font-weight: 700; color: var(--k); }
.am-act2-d { display: flex; flex-wrap: wrap; gap: 4px 10px; font-size: 12.5px; font-weight: 700; }
.am-act2-r { color: var(--c-danger-fg); font-weight: 600; }
.am-act2-m { font-size: 11.5px; color: var(--c-muted-fg); overflow-wrap: anywhere; }
[data-k="create"] { --k: #1464BA; } [data-k="volume"] { --k: #11AB53; } [data-k="status"] { --k: #D97706; } [data-k="password"] { --k: #7C3AED; }
[data-k="role"] { --k: #0891B2; } [data-k="profile"] { --k: #64748B; } [data-k="payment"] { --k: #059669; } [data-k="request"] { --k: #DB2777; }
[data-k="login"], [data-k="other"] { --k: #6B7280; }
.dark [data-k="create"] { --k: #60A5FA; } .dark [data-k="password"] { --k: #A78BFA; } .dark [data-k="request"] { --k: #F472B6; } .dark [data-k="role"] { --k: #22D3EE; }
/* v1.37 settings */
.am-set-pref span small { display: block; font-size: 11.5px; font-weight: 500; color: var(--c-muted-fg); margin-top: 2px; line-height: 1.6; }
.am-set-card h2 { display: flex; align-items: center; gap: 6px; }
.am-vol { display: flex; flex-direction: column; gap: 6px; font-size: 12.5px; font-weight: 700; margin: 8px 0; }
.am-vol input { width: 100%; }
.am-set-sep { height: 1px; background: var(--c-border); margin: 12px 0; }
.am-set-foot { text-align: center; }
@media (max-width: 767px) {
  .am-tools { grid-template-columns: minmax(0, 1fr); }
  .am-sort select { width: 100%; }
  .am-in-sm { height: 44px; min-height: 44px; font-size: 16px; flex: 1 1 130px; width: auto; }
  .am-btn-sm, .am-chip, .am-pager button { min-height: 44px; }
  .am-gsum .am-new { margin-inline-start: 0; width: 100%; justify-content: center; }
  .am-sort--act { flex-direction: column; align-items: stretch; }
  .am-sort--act select { width: 100%; flex: none; }
  .am-in-sm { flex-basis: 110px; }
  .am-grow { flex-basis: 100%; }
}
`

const PORTAL_CSS = `
.ap { min-height: 100vh; background: var(--c-bg); color: var(--c-text); font-family: Vazirmatn, Inter, sans-serif; }
.ap[dir="ltr"] { font-family: Inter, Vazirmatn, sans-serif; }
.ap-top { position: sticky; top: 0; z-index: 5; display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 10px 16px; background: color-mix(in srgb, var(--c-bg) 92%, transparent); backdrop-filter: blur(8px); border-bottom: 1px solid var(--c-border); }
.ap-top-r { display: flex; gap: 8px; }
.ap-lang { min-height: 40px; padding: 0 12px; border-radius: 10px; border: 1px solid transparent; background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); color: var(--c-text); font-weight: 700; font-size: 13px; }
.ap-lang:hover { background: color-mix(in srgb, var(--c-text-muted) 20%, transparent); }
.ap-main { max-width: 640px; margin: 0 auto; padding: 16px; display: flex; flex-direction: column; gap: 14px; }
.ap-card { background: linear-gradient(var(--c-surface), var(--c-surface)), var(--c-bg); border: 1px solid var(--c-border); border-radius: 16px; padding: 16px; }
.ap-login { display: flex; flex-direction: column; gap: 8px; margin-top: 8vh; }
.ap-login h1 { font-size: 20px; font-weight: 800; }
.ap-login p { font-size: 13px; color: var(--c-muted-fg); margin-bottom: 6px; }
.ap-login label { font-size: 12.5px; font-weight: 700; margin-top: 4px; }
.ap-input { height: 46px; border-radius: 12px; border: 1px solid var(--c-border); background: var(--c-surface); color: var(--c-text); padding: 0 12px; font-size: 16px; }
.ap-input:focus { outline: 2px solid color-mix(in srgb, var(--c-primary) 45%, transparent); }
.ap-btn { margin-top: 10px; min-height: 48px; border-radius: 12px; background: color-mix(in srgb, var(--c-primary) 82%, #000); color: #fff; font-weight: 800; font-size: 15px; border: 0; }
.ap-btn:disabled { opacity: .6; }
.ap-alert { padding: 10px 12px; border-radius: 12px; font-size: 13px; line-height: 1.7; color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 10%, transparent); margin: 6px 0; }
.ap-alert a { color: inherit; font-weight: 700; }
.ap-warn { padding: 10px 12px; border-radius: 12px; font-size: 13px; color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 12%, transparent); margin: 6px 0; }
.ap-empty { font-size: 14px; color: var(--c-muted-fg); }
.ap-group { font-size: 14px; font-weight: 800; color: var(--c-muted-fg); }
.ap-acc-h { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
.ap-acc-h h2 { font-size: 17px; font-weight: 800; overflow-wrap: anywhere; }
.ap-pill { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; font-weight: 700; padding: 3px 10px; border-radius: 999px; color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 14%, transparent); white-space: nowrap; }
.ap-pill[data-st="panel_disabled"] { color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 14%, transparent); }
.ap-pill[data-st="pamp_limited"] { color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 14%, transparent); }
.ap-num { font-family: 'JetBrains Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }
.ap-usage { margin: 10px 0; }
.ap-usage-l { display: flex; justify-content: space-between; font-size: 12.5px; font-weight: 700; color: var(--c-muted-fg); margin-bottom: 6px; }
.ap-bar { display: block; height: 10px; border-radius: 999px; background: color-mix(in srgb, var(--c-text-muted) 18%, transparent); overflow: hidden; }
.ap-usage-s { font-size: 12px; color: var(--c-muted-fg); margin-top: 6px; }
.ap-bar i { display: block; height: 100%; border-radius: inherit; background: var(--c-primary); }
.ap-bar[data-tone="warning"] i { background: var(--c-warning); } .ap-bar[data-tone="danger"] i { background: var(--c-danger); }
.ap-nums { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 10px; }
.ap-nums > div { padding: 10px 12px; border-radius: 12px; border: 1px solid var(--c-border); min-width: 0; border-top: 3px solid var(--ac, var(--c-border)); }
.ap-nums dt { font-size: 11.5px; font-weight: 600; color: var(--c-muted-fg); display: flex; align-items: center; gap: 5px; }
.ap-nums dt .agi { color: var(--ac); }
.ap-nums dd { font-size: 16px; font-weight: 800; margin-top: 2px; overflow-wrap: anywhere; }
.ap-bal { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--c-border); font-size: 13.5px; font-weight: 700; }
.ap-bal .ap-num { font-size: 16px; font-weight: 800; }
.ap-bal [data-sign="owes"] { color: var(--c-danger-fg); } .ap-bal [data-sign="credit"] { color: var(--c-success-fg); } .ap-bal [data-sign="zero"] { color: var(--c-muted-fg); }
.ap-link { margin-inline-start: auto; min-height: 40px; padding: 0 12px; border-radius: 10px; color: var(--c-text); font-weight: 700; font-size: 13px; background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); border: 1px solid transparent; }
.ap-link:hover { background: color-mix(in srgb, var(--c-text-muted) 20%, transparent); }
.ap-st { display: flex; flex-direction: column; margin-top: 8px; }
.ap-st li { display: grid; grid-template-columns: auto 1fr auto; gap: 2px 10px; align-items: center; padding: 9px 0; border-top: 1px solid var(--c-border); font-size: 13px; }
.ap-st li[data-voided] { opacity: .55; }
.ap-st-k { font-size: 11.5px; font-weight: 700; padding: 2px 9px; border-radius: 999px; color: var(--c-primary-fg); background: color-mix(in srgb, var(--c-primary) 12%, transparent); }
.ap-st-k[data-kind="payment"] { color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 14%, transparent); }
.ap-st-d { color: var(--c-muted-fg); font-size: 12.5px; }
.ap-st-a { font-weight: 800; }
.ap-st-a[data-sign="owes"] { color: var(--c-danger-fg); } .ap-st-a[data-sign="credit"] { color: var(--c-success-fg); } .ap-st-a[data-sign="zero"] { color: var(--c-muted-fg); }
.ap-st-r, .ap-st-n { grid-column: 1 / -1; font-size: 12px; color: var(--c-muted-fg); }
.ap-mgr-link { display: inline-flex; align-items: center; justify-content: center; gap: 6px; margin-top: 10px; font-size: 13px; font-weight: 700; color: var(--c-primary); min-height: 40px; }
.ap-foot { font-size: 12px; color: var(--c-muted-fg); margin-top: 10px; }
.ap-spin { width: 28px; height: 28px; margin: 24px auto; border-radius: 50%; border: 3px solid var(--c-border); border-top-color: var(--c-primary); animation: ap-r 0.8s linear infinite; }
@keyframes ap-r { to { transform: rotate(360deg); } }
@media (min-width: 640px) { .ap-nums { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
.ap-pill::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.ap-lang, .ap-link, .ap-btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; transition: background-color .15s, transform .08s; }
.ap-lang:active, .ap-link:active, .ap-btn:active:not(:disabled) { transform: translateY(1px) scale(.98); }
.ap-btn:hover:not(:disabled) { background: color-mix(in srgb, var(--c-primary) 70%, #000); }
.ap-btn:active:not(:disabled) { background: color-mix(in srgb, var(--c-primary) 60%, #000); }
.ap-btn:focus-visible, .ap-lang:focus-visible, .ap-link:focus-visible { outline: 2px solid var(--c-primary); outline-offset: 2px; }
.ap-btn-spin { width: 16px; height: 16px; border-radius: 50%; border: 2px solid currentColor; border-inline-end-color: transparent; animation: ap-r .7s linear infinite; }
.ap-st li:hover { background: color-mix(in srgb, var(--c-primary) 4%, transparent); }
.ap-gb { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: .74em; font-weight: 500; color: var(--c-muted-fg); margin: 0 6px; white-space: nowrap; }
.ap-nums dd .ap-gb { display: block; margin: 0; font-size: 11.5px; margin-top: 1px; }
`
