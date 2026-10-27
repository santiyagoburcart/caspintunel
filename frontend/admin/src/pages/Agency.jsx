import { useEffect, useMemo, useState } from 'react'
import { Link, NavLink, useNavigate, useParams } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useAuth } from '../lib/auth'
import { jalali, digits } from '../lib/format'
import { Alert, Spinner, Toggle } from '../components/ui'
import { copyToClipboard } from '../lib/clipboard'
import { useConfirm } from '../components/ConfirmDialog'
import { useToast } from '../components/Toast'
import AgencyLimitHistory from './AgencyLimitHistory'
import { ACCENT_CSS, Ic } from '../components/AgencyIcons'
import { AgencyLedgerOverview, BalanceText, LedgerCard, LT } from './AgencyLedger'
import { AdminSettingsTab, AgencyAdminCreate } from './AgencyAdminForms'
import { AgencyApprovalsView, AgencyGroupStatementView, AgencyLedgerGroupsView, AgencyManagersView, GroupActivity, LedgerSubNav } from './AgencyManagers'
import { useLiveApprovals } from '../lib/liveApprovals'

// Agency panel (PAMP port). Every number on these pages comes from the backend
// (apps/agency: PAMP's own formulas); this file only formats and lays out.

const T = {
  fa: {
    title: 'پنل نمایندگی', sub: 'ادمین‌های نماینده روی پنل پاسارگاد',
    tab_dash: 'داشبورد', tab_admins: 'نماینده‌ها', tab_groups: 'گروه‌ها', tab_managers: 'مدیران گروه', tab_approvals: 'تأییدها', tab_logs: 'لاگ همگام‌سازی', tab_settings: 'تنظیمات',
    cutover: 'فعال پس از انتقال نهایی',
    cutover_note: 'همگام‌سازی این بخش هنوز روشن نشده است؛ این بخش فعلاً فقط‌خواندنی است و هیچ تغییری روی پنل اعمال نمی‌شود. داده‌ها از آخرین درون‌ریزی هستند.',
    balance: 'بدهی', portal_set: 'پرتال نماینده‌ها', portal_set_d: 'نماینده‌ها با نام کاربری و رمز پنل پاسارگاد خود در /agency/ وارد می‌شوند و فقط اعداد خودشان را می‌بینند. تا انتقال نهایی، اعداد از آخرین درون‌ریزی است.',
    total_sold: 'حجم فروخته‌شده', used: 'مصرف‌شده', remaining: 'باقی‌مانده', hidden: 'ترافیک پنهان', admins: 'نماینده‌ها',
    sold_limit: 'Sold Limit', limit: 'سقف ادمین', usage: 'مصرف', users: 'کاربران', status: 'وضعیت', group: 'گروه',
    over_title: 'نزدیک یا بیش از سقف (≥80%)', over_none: 'هیچ نماینده‌ای به 80% سقف نرسیده است.',
    st_active: 'فعال', st_panel_disabled: 'غیرفعال (پنل)', st_pamp_limited: 'محدود‌شده', at_risk: 'در خطر', over: 'بیش از سقف',
    last_sync: 'آخرین همگام‌سازی', never: 'هرگز', active_n: 'فعال', disabled_n: 'غیرفعال', limited_n: 'محدود', near_n: 'نزدیک سقف',
    search: 'جستجوی نام نماینده…', clear: 'پاک کردن جستجو', all: 'همه', f_status: 'وضعیت', f_limit: 'سقف', limited: 'سقف‌دار', unlimited: 'نامحدود',
    any_group: 'همهٔ گروه‌ها', n_admins: '{n} نماینده', none: 'نماینده‌ای پیدا نشد.', back: 'بازگشت به فهرست', unl: 'نامحدود',
    detail_numbers: 'سقف ادمین', deleted: 'از کاربران حذف‌شده', hidden_clamped: 'پنهان (حداقل صفر)', counts: 'کاربران بر اساس وضعیت',
    c_active: 'فعال', c_on_hold: 'در انتظار', c_limited: 'اتمام حجم', c_disabled: 'غیرفعال', c_expired: 'منقضی', c_total: 'کل',
    warn80: 'به {p}% سقف رسیده است', blocked_pamp: 'به‌دلیل رسیدن به سقف محدود شده', blocked_panel: 'روی پنل غیرفعال است',
    actions: 'محدودیت‌ها و عملیات', a_set: 'تعیین / تغییر سقف', a_remove: 'حذف سقف', a_disable: 'غیرفعال‌سازی ادمین', a_enable: 'فعال‌سازی ادمین',
    a_disable_users: 'غیرفعال‌سازی همه کاربران', a_enable_users: 'فعال‌سازی همه کاربران', a_reset: 'ریست ترافیک حذف‌شده‌ها',
    cur_limit: 'سقف فعلی', statement_link: 'صورت‌حساب این نماینده', unit: 'واحد', amount: 'مقدار', p_old_new: 'سقف', p_base: 'آخرین سقف (مبنا)', p_base_hint: '— ادمین الان نامحدود است؛ «افزایش» و شارژ از این مقدار حساب می‌شود', p_base_none: 'سقفی ثبت نشده — شارژ از صفر حساب می‌شود', p_remaining: 'باقی‌مانده پس از تغییر', p_charge: 'شارژ حساب', p_no_charge: 'بدون شارژ (افزایش نیست)', p_no_price: 'برای امروز قیمتی ثبت نشده — شارژ با مبلغ 0 ثبت می‌شود', p_wait: 'در حال محاسبه…', v_positive: 'یک عدد مثبت وارد کنید', d_reset: 'شمارندهٔ «از کاربران حذف‌شده» صفر می‌شود و حجم فروخته‌شده در همگام‌سازی بعدی کم می‌شود.', d_disable_users: 'همهٔ کاربران این ادمین روی پنل غیرفعال می‌شوند.', d_disable: 'دسترسی این ادمین به پنل بسته می‌شود؛ کاربرانش دست نمی‌خورند.', d_remove: 'سقف این ادمین برداشته می‌شود (نامحدود).',
    gb: 'گیگابایت', mode: 'نوع', m_set: 'تنظیم روی', m_add: 'افزودن', m_reduce: 'کاهش', confirm_go: 'تأیید',
    snapshots: 'آخرین مصرف کاربران (اسنپ‌شات)', snap_n: '{n} کاربر', user: 'کاربر', last_seen: 'آخرین بررسی', recent_syncs: 'همگام‌سازی‌های اخیر',
    support: 'پشتیبانی', groups_none: 'گروهی تعریف نشده است.', owner: 'مالک', members: 'اعضا', note: 'یادداشت', missing: 'روی پنل نیست',
    logs_none: 'لاگی ثبت نشده است.', s_success: 'موفق', s_partial: 'ناقص', s_failed: 'ناموفق', synced: 'ادمین', duration: 'مدت', error: 'خطا', more: 'بیشتر',
    set_sync: 'همگام‌سازی خودکار', set_sync_d: 'هر چند دقیقه اعداد را از پنل می‌گیرد. روشن کردن آن یعنی انتقال نهایی — اول همگام‌سازی قبلی را متوقف کنید.',
    set_enf: 'اعمال سقف خودکار', set_enf_d: 'ادمینی که به 100% سقف برسد روی پنل غیرفعال و پس از افزایش سقف دوباره فعال می‌شود. فقط وقتی همگام‌سازی روشن است.',
    set_interval: 'فاصلهٔ همگام‌سازی (دقیقه)', save: 'ذخیره', saved: 'ذخیره شد',
    cut_title: 'روشن کردن همگام‌سازی = انتقال نهایی', cut_msg: 'از این لحظه این سرور اعداد را از پنل می‌گیرد و عملیات‌ها فعال می‌شوند. دو همگام‌سازی هم‌زمان روی یک پنل اعداد را خراب می‌کند.',
    cut_reason: 'برای تأیید بنویسید: FINLAND-STOPPED', sync_off_title: 'خاموش کردن همگام‌سازی؟', enf_title: 'اعمال خودکار سقف روشن شود؟',
    users_col: 'کاربران', users_on: 'فعال', users_sec: 'کاربران', sort_by: 'مرتب‌سازی بر اساس {c}',
    portal_link: 'لینک پرتال نماینده‌ها', send_to: 'ارسال به نماینده', copy_link: 'کپی لینک', copy_msg: 'کپی پیام', show_qr: 'نمایش QR', hide_qr: 'بستن QR', copied: 'کپی شد', copy_fail: 'کپی نشد',
    send_hint: 'این پیام را برای نماینده بفرستید؛ با نام کاربری و رمز پنل خودش وارد می‌شود.',
    msg_tpl: 'پرتال نمایندگی:\n{url}\nنام کاربری: {u}\nرمز عبور: همان رمز پنل پاسارگاد شما',
    g_intro: 'مالک گروه در پرتال نماینده‌ها حساب‌های همهٔ اعضا را می‌بیند (فقط‌خواندنی)؛ اعضا فقط حساب خودشان را.', g_create: 'گروه جدید', g_edit: 'ویرایش', g_delete: 'حذف گروه',
    g_group: 'گروه', g_name: 'نام گروه', g_name_ph: 'اختیاری — مثلاً شعبهٔ شمال', g_owner: 'ادمین اصلی (مالک)', g_owner_hint: 'این ادمین در پرتال همهٔ حساب‌های گروه را می‌بیند.',
    g_member: 'عضو', g_search: 'جستجوی ادمین برای افزودن…', g_add_members: 'افزودن عضو', g_remove_member: 'حذف از گروه', g_remove: 'حذف', g_accounts: 'حساب‌ها',
    g_delete_msg: 'فقط گروه حذف می‌شود؛ حساب‌ها روی پنل دست نمی‌خورند. مالک از این پس در پرتال فقط حساب خودش را می‌بیند.',
    g_created: 'گروه ساخته شد', g_saved: 'گروه ذخیره شد', g_deleted: 'گروه حذف شد',
    new_admin: 'ساخت ادمین', t_overview: 'نمای کلی', t_limits: 'محدودیت‌ها و عملیات', t_history: 'تاریخچهٔ سقف', t_settings: 'تنظیمات', t_accounting: 'حسابداری', t_send: 'ارسال به نماینده',
    history: 'سوابق', send_pw_note: 'رمز ورود همان رمز پنل این ادمین است. برای رمز تازه از تب «تنظیمات» → تغییر رمز عبور استفاده کنید؛ رمز جدید همان‌جا یک بار نمایش داده می‌شود.',
  },
  en: {
    title: 'Agency Panel', sub: 'Reseller admins on the PasarGuard panel',
    tab_dash: 'Dashboard', tab_admins: 'Admins', tab_groups: 'Groups', tab_managers: 'Group managers', tab_approvals: 'Approvals', tab_logs: 'Sync logs', tab_settings: 'Settings',
    cutover: 'Available after the final cut-over',
    cutover_note: 'Sync for this section is not on yet; it is read-only for now and changes nothing on the panel. Data is from the last import.',
    balance: 'Balance', portal_set: 'Reseller portal', portal_set_d: 'Resellers sign in at /agency/ with their PasarGuard admin username and password and see only their own numbers. Until the cut-over the numbers are from the last import.',
    total_sold: 'Total Sold', used: 'Used', remaining: 'Remaining', hidden: 'Hidden traffic', admins: 'Admins',
    sold_limit: 'Sold Limit', limit: 'Admin limit', usage: 'Usage', users: 'Users', status: 'Status', group: 'Group',
    over_title: 'At or over the limit (≥80%)', over_none: 'No admin has reached 80% of their limit.',
    st_active: 'Active', st_panel_disabled: 'Disabled (panel)', st_pamp_limited: 'Limited', at_risk: 'At risk', over: 'Over limit',
    last_sync: 'Last sync', never: 'never', active_n: 'active', disabled_n: 'disabled', limited_n: 'limited', near_n: 'near limit',
    search: 'Search admin name…', clear: 'Clear search', all: 'All', f_status: 'Status', f_limit: 'Limit', limited: 'Limited', unlimited: 'Unlimited',
    any_group: 'All groups', n_admins: '{n} admins', none: 'No admin found.', back: 'Back to the list', unl: 'Unlimited',
    detail_numbers: 'Admin limit', deleted: 'From deleted users', hidden_clamped: 'Hidden (min 0)', counts: 'Users by status',
    c_active: 'Active', c_on_hold: 'On hold', c_limited: 'Data used up', c_disabled: 'Disabled', c_expired: 'Expired', c_total: 'Total',
    warn80: 'reached {p}% of the limit', blocked_pamp: 'Limited: the admin limit was reached', blocked_panel: 'Disabled on the panel',
    actions: 'Limits & actions', a_set: 'Set / change limit', a_remove: 'Remove limit', a_disable: 'Disable admin', a_enable: 'Enable admin',
    a_disable_users: 'Disable all users', a_enable_users: 'Enable all users', a_reset: 'Reset deleted traffic',
    cur_limit: 'Current limit', statement_link: "This admin's statement", unit: 'Unit', amount: 'Amount', p_old_new: 'Limit', p_base: 'Last limit (base)', p_base_hint: '— the admin is unlimited now; "Add" and the charge start from this', p_base_none: 'no previous limit — charged from 0', p_remaining: 'Remaining after', p_charge: 'Account charge', p_no_charge: 'No charge (not an increase)', p_no_price: 'No price set for today — the charge is recorded at 0', p_wait: 'Calculating…', v_positive: 'Enter a positive number', d_reset: 'The "from deleted users" counter goes to 0; Total Sold drops at the next sync.', d_disable_users: "All of this admin's users are disabled on the panel.", d_disable: 'This admin loses panel access; their users keep working.', d_remove: "This admin's limit is removed (unlimited).",
    gb: 'GB', mode: 'Mode', m_set: 'Set to', m_add: 'Add', m_reduce: 'Reduce', confirm_go: 'Confirm',
    snapshots: 'Last known user usage (snapshot)', snap_n: '{n} users', user: 'User', last_seen: 'Last seen', recent_syncs: 'Recent syncs',
    support: 'Support', groups_none: 'No groups defined.', owner: 'Owner', members: 'Members', note: 'Note', missing: 'not on the panel',
    logs_none: 'No sync logged yet.', s_success: 'Success', s_partial: 'Partial', s_failed: 'Failed', synced: 'admins', duration: 'Duration', error: 'Error', more: 'Load more',
    set_sync: 'Automatic sync', set_sync_d: 'Pulls the numbers from the panel every few minutes. Turning it on IS the final cut-over — stop the previous sync first.',
    set_enf: 'Automatic limit enforcement', set_enf_d: 'An admin at 100% of their limit is disabled on the panel and re-enabled once the limit is raised. Only while sync is on.',
    set_interval: 'Sync interval (minutes)', save: 'Save', saved: 'Saved',
    cut_title: 'Turning sync on = the final cut-over', cut_msg: 'From now on this server pulls the numbers from the panel and actions are enabled. Two syncs against one panel corrupt the numbers.',
    cut_reason: 'Type FINLAND-STOPPED to confirm', sync_off_title: 'Turn the sync off?', enf_title: 'Turn on automatic enforcement?',
    users_col: 'Users', users_on: 'on', users_sec: 'Users', sort_by: 'Sort by {c}',
    portal_link: 'Reseller portal link', send_to: 'Send to reseller', copy_link: 'Copy link', copy_msg: 'Copy message', show_qr: 'Show QR', hide_qr: 'Hide QR', copied: 'Copied', copy_fail: 'Could not copy',
    send_hint: 'Send this to the reseller; they sign in with their own panel username and password.',
    msg_tpl: 'Reseller portal:\n{url}\nUsername: {u}\nPassword: your PasarGuard panel password',
    g_intro: "The group owner sees every member account in the reseller portal (read-only); members see only their own.", g_create: 'New group', g_edit: 'Edit', g_delete: 'Delete group',
    g_group: 'Group', g_name: 'Group name', g_name_ph: 'Optional — e.g. North branch', g_owner: 'Main admin (owner)', g_owner_hint: 'This admin sees all the group accounts in the portal.',
    g_member: 'member', g_search: 'Search admins to add…', g_add_members: 'Add members', g_remove_member: 'Remove from group', g_remove: 'Remove', g_accounts: 'Accounts',
    g_delete_msg: 'Only the group is deleted; the accounts on the panel are untouched. From now on the owner sees only their own account in the portal.',
    g_created: 'Group created', g_saved: 'Group saved', g_deleted: 'Group deleted',
    new_admin: 'New admin', t_overview: 'Overview', t_limits: 'Limits & actions', t_history: 'Limit history', t_settings: 'Settings', t_accounting: 'Accounting', t_send: 'Send to reseller',
    history: 'History', send_pw_note: "The password is the admin's panel password. For a fresh one use Settings → Change password; the new password is shown there once.",
  },
}

const useT = () => { const { lang } = useI18n(); return [T[lang] || T.fa, lang] }
// backend strings are PAMP's ("1.23 TB", "Unlimited") — only translate the word
const fmt = (v, s) => (v === 'Unlimited' ? s.unl : v)
const B = ({ children }) => <bdi dir="ltr" className="ag-num">{children}</bdi>
// the GB figure next to a TB value (1 TB = 1024 GB, PAMP's units), from the raw bytes
// the server sends; nothing under 1 TB or for Unlimited. `block` = on its own small line.
const TB_BYTES = 1024 ** 4
const gbOf = (b, signed) => { const n = Math.round(Number(b) / 1024 ** 3); return `${signed && n > 0 ? '+' : ''}${n.toLocaleString('en-US')} GB` }
const GB = ({ b, block, signed }) => (b == null || Math.abs(Number(b)) < TB_BYTES ? null
  : <bdi dir="ltr" className={'ag-gb' + (block ? ' ag-gb--block' : '')}>{gbOf(b, signed)}</bdi>)
// an admin limit reads in exact GB ("5,200 GB"); the server's TB figure ("5.08 TB") is the
// small secondary text from 1 TB up. b = limit bytes (null/0 = Unlimited), tb = its *_fmt.
const gbExact = (b) => `${(Number(b) / 1024 ** 3).toLocaleString('en-US', { maximumFractionDigits: 2 })} GB`
const limitText = (b, tb, s) => (!(Number(b) > 0) ? s.unl : gbExact(b) + (Number(b) >= TB_BYTES && tb ? ` (${tb})` : ''))
const Lim = ({ b, tb, s, block, strong }) => {
  if (!(Number(b) > 0)) return <B>{s.unl}</B>
  const main = <B>{gbExact(b)}</B>
  return <>{strong ? <b>{main}</b> : main}{Number(b) >= TB_BYTES && tb && <bdi dir="ltr" className={'ag-gb' + (block ? ' ag-gb--block' : '')}>{tb}</bdi>}</>
}

function Header({ s, switches }) {
  const { can } = useAuth()
  const { lang } = useI18n()
  const { pending } = useLiveApprovals()
  const tabs = [['/agency', s.tab_dash, true], ['/agency/admins', s.tab_admins], ['/agency/groups', s.tab_groups],
    ['/agency/managers', s.tab_managers], ['/agency/approvals', s.tab_approvals, false, pending],
    ...(can('agency.accounting') ? [['/agency/ledger', (LT[lang] || LT.fa).tab]] : []),
    ['/agency/sync-logs', s.tab_logs], ['/agency/settings', s.tab_settings]]
  return (
    <>
      <style>{ACCENT_CSS + CSS}</style>
      <div className="ag-head">
        <h1 className="text-lg font-bold">{s.title}</h1>
        <p className="text-sm text-muted mt-1">{s.sub}</p>
      </div>
      <nav className="ag-tabs" aria-label={s.title}>
        {tabs.map(([to, label, end, badge]) => (
          <NavLink key={to} to={to} end={!!end} className={({ isActive }) => 'ag-tab' + (isActive ? ' on' : '')}>
            {label}{badge > 0 && <span className="ag-tab-badge" aria-label={`${badge}`}>{badge > 99 ? '99+' : badge}</span>}
          </NavLink>
        ))}
      </nav>
      {switches && !switches.writes_enabled && (
        <div className="ag-cutover" role="note"><b>{s.cutover}</b><span>{s.cutover_note}</span></div>
      )}
    </>
  )
}

function useLoad(url, deps = []) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const load = () => api.get(url).then((r) => { setData(r.data); setErr('') }).catch((e) => { setErr(apiError(e)); setData((d) => d || false) })
  useEffect(() => { load() }, deps)
  return [data, err, load]
}

// table header with a small coloured icon
const TH = ({ i, ac, children, className }) => <th className={className}><span className="ag-th" data-ac={ac}><Ic n={i} size={13} />{children}</span></th>
// section header with a small coloured icon
const SecH = ({ i, ac, children, style }) => <h3 className="ag-sec-h ag-sh" data-ac={ac} style={style}><Ic n={i} size={15} />{children}</h3>

function StatusPill({ code, s }) {
  return <span className="ag-pill" data-st={code}>{s['st_' + code] || code}</span>
}

function UsageBar({ pct }) {
  // pct is PAMP's usage_percent (backend); the bar only caps its WIDTH at 100%
  const w = Math.min(Number(pct) || 0, 100)
  const tone = pct >= 100 ? 'danger' : pct >= 80 ? 'warning' : 'primary'
  return <span className="ag-bar" data-tone={tone}><i style={{ width: `${w}%` }} /></span>
}

// ------------------------------------------------------------------ dashboard
export function AgencyDashboard() {
  const [s, lang] = useT()
  const [d, err] = useLoad('/admin/agency/')
  return (
    <div className="ag space-y-4">
      <Header s={s} switches={d?.switches} />
      <Alert>{err}</Alert>
      {d === null ? <div className="grid place-items-center py-16"><Spinner /></div> : d && (
        <>
          <div className="ag-kpis">
            <Kpi label={s.total_sold} value={d.total_sold_fmt} b={d.bytes?.total_sold} ac="blue" icon="sold" />
            <Kpi label={s.used} value={d.total_used_fmt} b={d.bytes?.used} ac="purple" icon="used" />
            <Kpi label={s.remaining} value={d.total_remaining_fmt} b={d.bytes?.remaining} ac="green" icon="remaining" />
            <Kpi label={s.hidden} value={d.total_hidden_fmt} b={d.bytes?.hidden} ac="orange" icon="hidden" />
            <Kpi label={s.admins} value={digits(d.admin_count, lang)} ac="gray" icon="users"
              sub={`${digits(d.active_count, lang)} ${s.active_n} · ${digits(d.disabled_count, lang)} ${s.disabled_n} · ${digits(d.pamp_limited_count, lang)} ${s.limited_n}`} />
          </div>
          <div className="card ag-card">
            <div className="ag-card-h">
              <h3 className="ag-sh" data-ac="orange"><Ic n="alert" size={15} />{s.over_title}</h3>
              <span className="ag-count">{digits(d.near_limit_count, lang)}</span>
            </div>
            {d.over_limit.length === 0 ? <p className="ag-empty">{s.over_none}</p> : (
              <ul className="ag-over">
                {d.over_limit.map((o) => (
                  <li key={o.username}>
                    <Link to={`/agency/admins/${encodeURIComponent(o.username)}`} className="ag-over-name">{o.username}</Link>
                    <span className="ag-over-tag" data-state={o.state}>{o.state === 'over' ? s.over : s.at_risk}</span>
                    <UsageBar pct={o.pct} />
                    <span className="ag-over-pct"><B>{o.pct}%</B></span>
                    <span className="ag-over-sub"><B>{o.used_fmt}</B><GB b={o.used_bytes} /> / <Lim b={o.limit_bytes} tb={o.limit_fmt} s={s} /></span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <p className="text-xs text-muted">
            {s.last_sync}: {d.last_sync ? <>{jalali(d.last_sync.created_at, true, lang)} · {s['s_' + d.last_sync.status]}</> : s.never}
          </p>
        </>
      )}
    </div>
  )
}

function Kpi({ label, value, b, ac, icon, sub }) {
  return (
    <div className="card ag-kpi" data-ac={ac}>
      <span className="ag-kpi-ico"><Ic n={icon} size={16} /></span>
      <span className="ag-kpi-l">{label}</span>
      <span className="ag-kpi-val"><B>{value}</B><GB b={b} /></span>
      {sub && <span className="ag-kpi-sub">{sub}</span>}
    </div>
  )
}

// ------------------------------------------------------------------ admins list
export function AgencyAdmins() {
  const [s, lang] = useT()
  const { can } = useAuth()
  const [q, setQ] = useState('')
  const [st, setSt] = useState('')
  const [lim, setLim] = useState('')
  const [grp, setGrp] = useState('')
  const [term, setTerm] = useState('')
  useEffect(() => { const h = setTimeout(() => setTerm(q.trim()), 250); return () => clearTimeout(h) }, [q])
  const qs = new URLSearchParams(Object.entries({ search: term, status: st, limit: lim, group: grp }).filter(([, v]) => v)).toString()
  const [d, err] = useLoad(`/admin/agency/admins/${qs ? '?' + qs : ''}`, [qs])
  const [dash] = useLoad('/admin/agency/')
  const [sort, setSort] = useState({ k: '', dir: -1 })
  const rows = useMemo(() => (!d ? [] : !sort.k ? d.results : [...d.results].sort((a, b) => (a[sort.k] - b[sort.k]) * sort.dir)), [d, sort])
  const sortTh = (k, label) => {
    const on = sort.k === k
    return (
      <th aria-sort={on ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
        <button type="button" className="ag-sort ag-th" data-ac="blue" onClick={() => setSort({ k, dir: on ? -sort.dir : -1 })} title={s.sort_by.replace('{c}', label)}>
          <Ic n="users" size={13} />{label}<span aria-hidden="true">{on ? (sort.dir === 1 ? ' ▲' : ' ▼') : ' ↕'}</span>
        </button>
      </th>
    )
  }
  const chip = (v, cur, set, label) => (
    <button type="button" key={v || 'all'} className={'ag-chip' + (cur === v ? ' on' : '')} aria-pressed={cur === v} onClick={() => set(v)}>{label}</button>
  )
  return (
    <div className="ag space-y-4">
      <Header s={s} switches={dash?.switches} />
      {can('agency.manage') && (
        <div className="ag-listbar">
          <Link to="/agency/admins/new" className="ag-act ag-new" data-tone="primary"><Ic n="plus" />{s.new_admin}</Link>
        </div>
      )}
      <div className="card ag-toolbar">
        <div className="ag-search">
          <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></svg>
          <input className="input" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={s.search} aria-label={s.search} />
          {q && <button type="button" className="ag-x" onClick={() => setQ('')} aria-label={s.clear}>×</button>}
        </div>
        <div className="ag-filters" role="group">
          <span className="ag-fg"><span className="ag-fg-l">{s.f_status}</span>
            {chip('', st, setSt, s.all)}{chip('active', st, setSt, s.st_active)}{chip('panel_disabled', st, setSt, s.st_panel_disabled)}{chip('pamp_limited', st, setSt, s.st_pamp_limited)}
          </span>
          <span className="ag-fg"><span className="ag-fg-l">{s.f_limit}</span>
            {chip('', lim, setLim, s.all)}{chip('limited', lim, setLim, s.limited)}{chip('unlimited', lim, setLim, s.unlimited)}
          </span>
          {d?.groups?.length > 0 && (
            <select className="input ag-group" value={grp} onChange={(e) => setGrp(e.target.value)} aria-label={s.group}>
              <option value="">{s.any_group}</option>
              {d.groups.map((g) => <option key={g.id} value={g.id}>{g.owner}</option>)}
            </select>
          )}
        </div>
        {d && <span className="ag-total" aria-live="polite">{s.n_admins.replace('{n}', digits(d.count, lang))}</span>}
      </div>
      <Alert>{err}</Alert>
      {d === null ? <div className="grid place-items-center py-16"><Spinner /></div> : d && (
        d.results.length === 0 ? <div className="card text-sm text-muted">{s.none}</div> : (
          <div className="card ag-table-wrap">
            <table className="ag-table ag-admins">
              <thead>
                <tr>
                  <TH i="user" ac="blue">{s.admins}</TH><TH i="status" ac="green">{s.status}</TH><TH i="usage" ac="orange">{s.usage}</TH><TH i="sold" ac="blue">{s.total_sold}</TH><TH i="limit" ac="cyan">{s.sold_limit}</TH>
                  <TH className="ag-c-hid" i="hidden" ac="orange">{s.hidden}</TH><TH i="remaining" ac="green">{s.remaining}</TH><TH i="used" ac="purple">{s.used}</TH>{sortTh('user_count', s.users_col)}{d.results[0]?.balance !== undefined && <TH i="wallet" ac="red">{s.balance}</TH>}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.username}>
                    <td className="ag-t-name" data-label={s.admins}>
                      <Link to={`/agency/admins/${encodeURIComponent(r.username)}`} className="ag-t-nm" title={r.username}>{r.username}</Link>
                      {r.groups.length > 0 && <span className="ag-t-grp" title={r.groups.map((g) => g.owner).join('، ')}>{r.groups.map((g) => g.owner).join('، ')}</span>}
                    </td>
                    <td className="ag-t-st" data-label={s.status}><StatusPill code={r.status_code} s={s} /></td>
                    <td className="ag-t-usage" data-label={s.usage}>
                      {r.is_unlimited ? <span className="text-muted">{s.unl}</span> : <><UsageBar pct={r.usage_percent} /><B>{r.usage_percent}%</B><span className="ag-lim" title={s.limit}>/ <Lim b={r.bytes?.limit} tb={r.admin_limit_fmt} s={s} block /></span></>}
                    </td>
                    <td data-label={s.total_sold}><B>{r.total_sold_fmt}</B><GB b={r.bytes?.total_sold} block /></td>
                    <td data-label={s.sold_limit}><B><span data-sign={r.sold_limit_value > 0 ? 'pos' : r.sold_limit_value < 0 ? 'neg' : 'zero'} className="ag-sign">{r.sold_limit_fmt}</span></B><GB b={r.bytes?.sold_limit} block signed /></td>
                    <td className="ag-c-hid" data-label={s.hidden}><B>{r.hidden_fmt}</B><GB b={r.bytes?.hidden} block /></td>
                    <td data-label={s.remaining}><B>{fmt(r.remaining_fmt, s)}</B><GB b={r.bytes?.remaining} block /></td>
                    <td data-label={s.used}><B>{r.used_fmt}</B><GB b={r.bytes?.used} block /></td>
                    <td data-label={s.users_col}>
                      <span className="ag-users" title={['active', 'on_hold', 'limited', 'disabled', 'expired'].map((k) => `${s['c_' + k]}: ${digits(r.user_counts?.[k] ?? 0, lang)}`).join('\n')}>
                        <B>{digits(r.user_count, lang)}</B><span className="ag-users-on"> / <B>{digits(r.active_user_count, lang)}</B> {s.users_on}</span>
                      </span>
                    </td>
                    {r.balance !== undefined && <td data-label={s.balance}><BalanceText value={r.balance} lang={lang} /></td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  )
}

// ------------------------------------------------------------------ admin detail
const DETAIL_TABS = ['overview', 'limits', 'history', 'settings', 'accounting', 'send']

export function AgencyAdminNew() {
  const [s] = useT()
  const [dash] = useLoad('/admin/agency/')
  return <AgencyAdminCreate Header={<Header s={s} switches={dash?.switches} />} />
}

export function AgencyAdminDetail() {
  const [s, lang] = useT()
  const { username, tab: rawTab } = useParams()
  const go = useNavigate()
  const { can } = useAuth()
  const confirm = useConfirm()
  const [d, err, load] = useLoad(`/admin/agency/admins/${encodeURIComponent(username)}/`, [username])
  const writable = d?.switches?.writes_enabled && can('agency.manage')

  const act = async (title, path, body, tone = 'warning', content, message) => {
    const ok = await confirm({
      tone, title, targetLabel: username, confirmLabel: s.confirm_go, content, message,
      action: async () => {
        const b = typeof body === 'function' ? body() : body
        if (b === false) throw new Error(s.v_positive)
        await api.post(`/admin/agency/admins/${encodeURIComponent(username)}/${path}/`, b)   // result → toast (FeedbackBridge)
      },
    })
    if (ok) load()
  }
  const setLimit = () => {
    const box = {}
    act(s.a_set, 'set-limit', () => (box.ready ? { action: box.mode, value_gb: box.gb } : false), 'primary',
      <SetLimitForm s={s} lang={lang} username={username} current={d.admin_limit_fmt} currentBytes={d.bytes?.limit} box={box} />)
  }

  if (d === null) return <div className="ag"><Header s={s} /><div className="grid place-items-center py-16"><Spinner /></div></div>
  if (!d) return <div className="ag space-y-4"><Header s={s} /><Alert>{err}</Alert></div>
  const p = d.portal
  const usageAc = d.is_unlimited ? 'gray' : d.usage_percent >= 100 ? 'red' : d.usage_percent >= 80 ? 'orange' : 'green'   // same thresholds as the bar
  const nums = [
    [s.limit, <Lim b={d.bytes?.limit} tb={d.admin_limit_fmt} s={s} />, 'blue'], [s.total_sold, d.total_sold_fmt, 'blue', d.bytes?.total_sold], [s.used, d.used_fmt, 'purple', d.bytes?.used],
    [s.remaining, fmt(d.remaining_fmt, s), 'green', d.bytes?.remaining], [s.sold_limit, d.sold_limit_fmt, 'cyan', d.bytes?.sold_limit, true], [s.hidden, d.hidden_fmt, 'orange', d.bytes?.hidden],
    [s.hidden_clamped, d.hidden_traffic_clamped_fmt, 'orange', d.bytes?.hidden_clamped], [s.deleted, d.deleted_used_fmt, 'orange', d.bytes?.deleted], [s.usage, `${d.usage_percent}%`, usageAc],
  ]
  const ACTIONS = [
    [s.a_set, setLimit, 'primary', 'gauge'],
    [s.a_remove, () => act(s.a_remove, 'remove-limit', {}, 'warning', null, `${s.d_remove} ${s.cur_limit}: ${limitText(d.bytes?.limit, d.admin_limit_fmt, s)}`), 'warning', 'infinity'],
    d.status === 'disabled'
      ? [s.a_enable, () => act(s.a_enable, 'admin-action', { action: 'enable_admin' }, 'success'), 'success', 'power']
      : [s.a_disable, () => act(s.a_disable, 'admin-action', { action: 'disable_admin' }, 'danger', null, s.d_disable), 'danger', 'power'],
    [s.a_disable_users, () => act(s.a_disable_users, 'admin-action', { action: 'disable_users' }, 'danger', null, `${s.d_disable_users} (${digits(d.counts.total, lang)})`), 'danger', 'users'],
    [s.a_enable_users, () => act(s.a_enable_users, 'admin-action', { action: 'enable_users' }, 'success'), 'success', 'users'],
    [s.a_reset, () => act(s.a_reset, 'reset-deleted-traffic', {}, 'danger', null, `${s.d_reset} (${d.deleted_used_fmt} → 0 B)`), 'danger', 'reset'],
  ]
  const tabs = DETAIL_TABS.filter((k) => (k === 'settings' ? can('agency.manage') : k === 'accounting' ? can('agency.accounting') : true))
  const tab = tabs.includes(rawTab) ? rawTab : 'overview'
  const base = `/agency/admins/${encodeURIComponent(username)}`
  const label = { overview: s.t_overview, limits: s.t_limits, history: s.t_history, settings: s.t_settings, accounting: s.t_accounting, send: s.t_send }
  const icon = { overview: 'list', limits: 'gauge', history: 'clock', settings: 'sliders', accounting: 'wallet', send: 'link' }
  return (
    <div className="ag space-y-4">
      <Header s={s} switches={d.switches} />
      <Link to="/agency/admins" className="ag-back">← {s.back}</Link>
      <div className="ag-dhead">
        <h2 className="font-bold text-base"><bdi>{d.username}</bdi></h2>
        <StatusPill code={d.status_code} s={s} />
        <span className="ag-dhead-lim">{s.limit}: <Lim b={d.bytes?.limit} tb={d.admin_limit_fmt} s={s} />{!d.is_unlimited && <> · <B>{d.usage_percent}%</B></>}</span>
      </div>
      <nav className="ag-dtabs" role="tablist" aria-label={d.username}>
        {tabs.map((k) => (
          <NavLink key={k} to={k === 'overview' ? base : `${base}/${k}`} end role="tab" aria-selected={tab === k}
            className={'ag-dtab' + (tab === k ? ' on' : '')}><Ic n={icon[k]} size={14} />{label[k]}</NavLink>
        ))}
      </nav>

      {tab === 'overview' && <>
      <div className="card ag-card">
        {d.groups.length > 0 && <div className="ag-detail-h">{d.groups.map((g) => <span key={g.id} className="ag-t-grp">{g.owner}</span>)}</div>}
        {!d.is_unlimited && <div className="ag-detail-bar"><UsageBar pct={d.usage_percent} /><B>{d.usage_percent}%</B></div>}
        {p.show_warning && <Alert kind="warning">{s.warn80.replace('{p}', p.warning_pct)}</Alert>}
        {p.is_blocked && <Alert>{p.block_reason === 'disabled' ? s.blocked_panel : s.blocked_pamp}</Alert>}
        <SecH i="list" ac="blue">{s.detail_numbers}</SecH>
        <dl className="ag-nums">
          {nums.map(([k, v, ac, b, signed]) => <div key={k} data-ac={ac}><dt>{k}</dt><dd>{typeof v === 'string' ? <><B>{v}</B><GB b={b} signed={signed} /></> : v}</dd></div>)}
        </dl>
        <SecH i="users" ac="purple">{s.users_sec}</SecH>
        <dl className="ag-nums ag-nums--counts">
          {['total', 'active', 'on_hold', 'limited', 'disabled', 'expired'].map((k) => (
            <div key={k} data-k={k}><dt>{s['c_' + k]}</dt><dd><B>{digits(d.counts[k], lang)}</B></dd></div>
          ))}
        </dl>
        <p className="text-xs text-muted mt-2">{s.support}: <bdi dir="ltr">{p.support_telegram}</bdi> · {s.last_sync}: {d.last_synced_at ? jalali(d.last_synced_at, true, lang) : s.never}</p>
      </div>

      </>}

      {tab === 'limits' && <div className="card ag-card ag-limits">
        <div className="ag-card-h">
          <SecH i="gauge" ac="blue" style={{ margin: 0 }}>{s.actions}</SecH>
          {can('agency.accounting') && (
            <Link to={`${base}/accounting`} className="ag-act ag-act--sm" data-tone="neutral"><Ic n="doc" size={13} />{s.statement_link}</Link>
          )}
        </div>
        <p className="ag-limits-cur">{s.cur_limit}: <Lim b={d.bytes?.limit} tb={d.admin_limit_fmt} s={s} strong />{!d.is_unlimited && <> · {s.usage}: <B>{d.usage_percent}%</B></>}</p>
        {!writable && <p className="ag-locked">{s.cutover}</p>}
        <div className="ag-actions">
          {ACTIONS.map(([label, fn, tone, icon]) => (
            <button key={label} type="button" className="ag-act" data-tone={tone || 'neutral'} disabled={!writable}
              onClick={fn} title={!writable ? s.cutover : undefined}><Ic n={icon} />{label}</button>
          ))}
        </div>
      </div>}

      {tab === 'settings' && <AdminSettingsTab username={d.username} writable={writable} onDeleted={() => go('/agency/admins')} />}
      {tab === 'history' && <AgencyLimitHistory username={d.username} />}
      {tab === 'accounting' && <LedgerCard username={d.username} />}
      {tab === 'send' && <>
        <PortalLinkCard s={s} username={d.username} />
        <p className="ag-note card ag-card text-sm text-muted">{s.send_pw_note}</p>
      </>}

      {tab === 'overview' && <>
      <div className="card ag-card">
        <div className="ag-card-h"><h3 className="ag-sh" data-ac="cyan"><Ic n="clock" size={15} />{s.snapshots}</h3><span className="ag-count">{s.snap_n.replace('{n}', digits(d.snapshots.count, lang))}</span></div>
        <div className="ag-table-wrap ag-snap">
          <table className="ag-table ag-table--plain">
            <thead><tr><TH i="user" ac="blue">{s.user}</TH><TH i="used" ac="purple">{s.used}</TH><TH i="clock" ac="gray">{s.last_seen}</TH></tr></thead>
            <tbody>{d.snapshots.rows.map((r) => (
              <tr key={r.user}><td data-label={s.user}><bdi>{r.user}</bdi></td><td data-label={s.used}><B>{r.used_fmt}</B></td><td data-label={s.last_seen}>{jalali(r.last_seen, true, lang)}</td></tr>
            ))}</tbody>
          </table>
        </div>
      </div>
      <div className="card ag-card">
        <SecH i="sync" ac="green" style={{ marginTop: 0 }}>{s.recent_syncs}</SecH>
        <SyncRows rows={d.recent_syncs} s={s} lang={lang} />
      </div>
      </>}
    </div>
  )
}

function SetLimitForm({ s, lang, username, current, currentBytes, box }) {
  const [mode, setMode] = useState('set')
  const [unit, setUnit] = useState('GB')
  const [val, setVal] = useState('')
  const [p, setP] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    box.ready = false
    const raw = val.replace(/[۰-۹]/g, (c) => '۰۱۲۳۴۵۶۷۸۹'.indexOf(c)).replace(/[٠-٩]/g, (c) => '٠١٢٣٤٥٦٧٨٩'.indexOf(c)).replace(/[,٬\s]/g, '')
    setP(null)
    if (!raw) { setErr(''); return }
    if (!/^\d+(\.\d+)?$/.test(raw) || Number(raw) <= 0) { setErr(s.v_positive); return }
    const gb = unit === 'TB' ? Number(raw) * 1024 : Number(raw)
    setErr(''); setBusy(true)
    const h = setTimeout(() => {
      api.post(`/admin/agency/admins/${encodeURIComponent(username)}/set-limit/preview/`, { action: mode, value_gb: gb }, { quiet: true })
        .then((r) => { setP(r.data); Object.assign(box, { mode, gb, ready: true }) })
        .catch((e) => setErr(apiError(e)))
        .finally(() => setBusy(false))
    }, 300)
    return () => clearTimeout(h)
  }, [mode, unit, val])
  const money = (n) => `${Number(n || 0).toLocaleString('en-US')} ${lang === 'en' ? 'T' : 'تومان'}`
  const typed = Number(val.replace(/[۰-۹]/g, (c) => '۰۱۲۳۴۵۶۷۸۹'.indexOf(c)).replace(/[٠-٩]/g, (c) => '٠١٢٣٤٥٦٧٨٩'.indexOf(c)).replace(/[,٬\s]/g, '')) || 0
  return (
    <div className="ag-form ag-form--limit">
      <p className="ag-form-cur">{s.cur_limit}: <Lim b={currentBytes} tb={current} s={s} /></p>
      <label><span>{s.mode}</span>
        <select className="input" value={mode} onChange={(e) => setMode(e.target.value)}>
          <option value="set">{s.m_set}</option><option value="add">{s.m_add}</option><option value="reduce">{s.m_reduce}</option>
        </select>
      </label>
      <div className="ag-form-amt">
        <label><span>{s.amount}</span>
          <input className="input" dir="ltr" inputMode="decimal" value={val} onChange={(e) => setVal(e.target.value)} aria-invalid={!!err} autoFocus />
        </label>
        <label><span>{s.unit}</span>
          <select className="input" value={unit} onChange={(e) => setUnit(e.target.value)}><option>GB</option><option>TB</option></select>
        </label>
      </div>
      {typed > 0 && !err && <p className="ag-form-conv"><B>{unit === 'TB' ? `${typed.toLocaleString('en-US')} TB = ${(typed * 1024).toLocaleString('en-US', { maximumFractionDigits: 2 })} GB` : `${typed.toLocaleString('en-US')} GB = ${(typed / 1024).toLocaleString('en-US', { maximumFractionDigits: 3 })} TB`}</B></p>}
      {err && <p className="ag-form-err" role="alert">{err}</p>}
      {busy && !err && <p className="text-xs text-muted">{s.p_wait}</p>}
      {p && !err && (
        <dl className="ag-preview" aria-live="polite">
          <div><dt>{s.p_old_new}</dt><dd><Lim b={p.old_limit_bytes} tb={p.old_limit_fmt} s={s} /> {lang === 'fa' ? '←' : '→'} <Lim b={p.new_limit_bytes} tb={p.new_limit_fmt} s={s} strong /></dd></div>
          {p.unlimited_now && (
            <div className="ag-preview-base"><dt>{s.p_base}</dt><dd>{p.base_limit_bytes > 0
              ? <><Lim b={p.base_limit_bytes} tb={p.base_limit_fmt} s={s} strong /> <small className="text-muted">{s.p_base_hint}</small></>
              : <span className="text-muted">{s.p_base_none}</span>}</dd></div>
          )}
          <div><dt>{s.p_remaining}</dt><dd><B>{fmt(p.remaining_after_fmt, s)}</B><GB b={p.remaining_after_bytes} /></dd></div>
          <div><dt>{s.p_charge}</dt><dd>{!p.charge ? <span className="text-muted">{s.p_no_charge}</span> : (
            <><B>{Number(p.charge.gb).toLocaleString('en-US', { maximumFractionDigits: 2 })} GB</B> × <B>{p.charge.price_per_gb != null ? money(p.charge.price_per_gb) : '—'}</B> = <b><B>{money(p.charge.amount)}</B></b>
              {p.charge.price_per_gb == null && <small className="ag-form-err">{s.p_no_price}</small>}</>
          )}</dd></div>
        </dl>
      )}
    </div>
  )
}

function PortalLinkCard({ s, username }) {
  const [link] = useLoad('/admin/agency/portal-link/')
  const [qr, setQr] = useState(null)
  const [note, setNote] = useState('')
  useEffect(() => () => { if (qr) URL.revokeObjectURL(qr) }, [qr])
  const copy = async (text) => { setNote((await copyToClipboard(text)) ? s.copied : s.copy_fail) }
  const toggleQr = async () => {
    if (qr) { setQr(null); return }
    try { const r = await api.get('/admin/agency/portal-link/qr.png', { responseType: 'blob' }); setQr(URL.createObjectURL(r.data)) } catch (e) { setNote(apiError(e)) }
  }
  const url = link?.url || ''
  return (
    <div className="card ag-card">
      <SecH i="link" ac="blue" style={{ marginTop: 0 }}>{username ? s.send_to : s.portal_link}</SecH>
      <div className="ag-portal">
        <div className="ag-portal-main">
          <code dir="ltr" className="ag-portal-url">{url || '…'}</code>
          {username && <p className="text-xs text-muted mt-2">{s.user}: <bdi dir="ltr">{username}</bdi> · {s.send_hint}</p>}
          <div className="ag-actions mt-2">
            {username && <button type="button" className="ag-act" data-tone="neutral" disabled={!link} onClick={() => copy(s.msg_tpl.replace('{url}', url).replace('{u}', username))}><Ic n="copy" />{s.copy_msg}</button>}
            <button type="button" className="ag-act" data-tone="neutral" disabled={!link} onClick={() => copy(url)}><Ic n="link" />{s.copy_link}</button>
            <button type="button" className="ag-act" data-tone="neutral" disabled={!link} onClick={toggleQr} aria-expanded={!!qr}><Ic n="qr" />{qr ? s.hide_qr : s.show_qr}</button>
          </div>
          {note && <p className="text-xs text-muted mt-2" role="status">{note}</p>}
        </div>
        {qr && <img className="ag-portal-qr" src={qr} alt={`QR — ${url}`} width="140" height="140" />}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ accounting overview
export function AgencyLedger() {
  const [s] = useT()
  const [dash] = useLoad('/admin/agency/')
  return <AgencyLedgerOverview Header={<><Header s={s} switches={dash?.switches} /><LedgerSubNav /></>} />
}

function useHeader() {
  const [s] = useT()
  const [dash] = useLoad('/admin/agency/')
  return <Header s={s} switches={dash?.switches} />
}
export function AgencyManagers() { return <AgencyManagersView Header={useHeader()} /> }
export function AgencyApprovals() { return <AgencyApprovalsView Header={useHeader()} /> }
export function AgencyLedgerGroups() { return <AgencyLedgerGroupsView Header={useHeader()} /> }
export function AgencyGroupStatement() { return <AgencyGroupStatementView Header={useHeader()} /> }

// ------------------------------------------------------------------ groups
const GERR = {
  fa: { owner_required: 'ادمین اصلی (مالک) را انتخاب کنید.', unknown_owner: 'این ادمین روی پنل نیست.', owner_taken: 'این ادمین مالک گروه دیگری است.',
    unknown_member: 'این حساب‌ها روی پنل نیستند: {u}', not_found: 'این گروه دیگر وجود ندارد.' },
  en: { owner_required: 'Choose the main admin (owner).', unknown_owner: 'That admin is not on the panel.', owner_taken: 'That admin already owns another group.',
    unknown_member: 'These accounts are not on the panel: {u}', not_found: 'This group no longer exists.' },
}
const groupErr = (e, lang) => {
  const d = e?.response?.data
  const m = d?.code && (GERR[lang] || GERR.fa)[d.code]
  return m ? m.replace('{u}', (d.usernames || []).join('، ')) : apiError(e)
}

function GroupForm({ s, all, init, box }) {
  const [v, setV] = useState(() => ({ name: init?.name || '', owner: init?.owner || '', members: init?.members || [], note: init?.note || '' }))
  const [q, setQ] = useState('')
  useEffect(() => { Object.assign(box, v) }, [v])
  const toggle = (u) => setV((x) => ({ ...x, members: x.members.includes(u) ? x.members.filter((m) => m !== u) : [...x.members, u] }))
  const pool = [...new Set([...all, ...(init?.members || [])])].filter((u) => u !== v.owner && u.toLowerCase().includes(q.trim().toLowerCase()))
  return (
    <div className="ag-gform">
      <label><span>{s.g_name}</span>
        <input className="input" value={v.name} maxLength={100} onChange={(e) => setV({ ...v, name: e.target.value })} placeholder={s.g_name_ph} autoFocus />
      </label>
      <label><span>{s.g_owner} *</span>
        <select className="input" value={v.owner} onChange={(e) => setV({ ...v, owner: e.target.value, members: v.members.filter((m) => m !== e.target.value) })}>
          <option value="">—</option>
          {[...new Set([...all, ...(init?.owner ? [init.owner] : [])])].map((u) => <option key={u} value={u}>{u}</option>)}
        </select>
        <small>{s.g_owner_hint}</small>
      </label>
      <div className="ag-gform-m">
        <span className="ag-gform-l">{s.members} <b className="ag-count">{digits(v.members.length, 'en')}</b></span>
        {v.members.length > 0 && (
          <div className="ag-members">
            {v.members.map((m) => (
              <button key={m} type="button" className="ag-member ag-member--x" onClick={() => toggle(m)} title={s.g_remove_member} aria-label={`${s.g_remove_member}: ${m}`}>
                <bdi>{m}</bdi> <span aria-hidden="true">×</span>
              </button>
            ))}
          </div>
        )}
        <input className="input" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={s.g_search} aria-label={s.g_search} />
        <div className="ag-gpick" role="group" aria-label={s.g_add_members}>
          {pool.length === 0 ? <p className="text-xs text-muted">{s.none}</p> : pool.map((u) => (
            <label key={u} className="ag-gpick-i">
              <input type="checkbox" checked={v.members.includes(u)} onChange={() => toggle(u)} /> <bdi>{u}</bdi>
            </label>
          ))}
        </div>
      </div>
      <label><span>{s.note}</span>
        <input className="input" value={v.note} maxLength={200} onChange={(e) => setV({ ...v, note: e.target.value })} />
      </label>
    </div>
  )
}

export function AgencyGroups() {
  const [s, lang] = useT()
  const { can } = useAuth()
  const confirm = useConfirm()
  const [d, err, load] = useLoad('/admin/agency/groups/')
  const [dash] = useLoad('/admin/agency/')
  const [admins] = useLoad('/admin/agency/admins/')
  const toast = useToast()
  const writable = dash?.switches?.writes_enabled && can('agency.manage')
  const all = (admins?.results || []).map((r) => r.username).sort((a, b) => a.localeCompare(b))
  const title = (g) => g.name || g.owner

  const edit = async (g) => {
    const box = {}
    const ok = await confirm({
      tone: 'primary', title: g ? s.g_edit : s.g_create, targetLabel: g ? s.g_group : undefined, targetId: g ? title(g) : undefined,
      confirmLabel: s.save, content: <GroupForm s={s} all={all} init={g} box={box} />,
      action: async () => {
        if (!box.owner) throw new Error((GERR[lang] || GERR.fa).owner_required)
        const body = { name: box.name, owner: box.owner, members: box.members, note: box.note }
        try { g ? await api.put(`/admin/agency/groups/${g.id}/`, body) : await api.post('/admin/agency/groups/', body) } catch (e) { throw new Error(groupErr(e, lang)) }
      },
    })
    if (ok) { toast.success(g ? s.g_saved : s.g_created); load() }
  }
  const remove = async (g) => {
    const ok = await confirm({
      tone: 'danger', title: s.g_delete, targetLabel: s.g_group, targetId: title(g), confirmLabel: s.g_delete, message: s.g_delete_msg,
      details: { rows: [[s.g_owner, g.owner], [s.members, g.members.join('، ') || '—']] },
      action: async () => { try { await api.delete(`/admin/agency/groups/${g.id}/`) } catch (e) { throw new Error(groupErr(e, lang)) } },
    })
    if (ok) { toast.success(s.g_deleted); load() }
  }
  const dropMember = async (g, m) => {
    const ok = await confirm({
      tone: 'danger', title: s.g_remove_member, targetLabel: s.g_group, targetId: title(g), confirmLabel: s.g_remove_member,
      details: { rows: [[s.members, `${g.members.join('، ')} → ${g.members.filter((x) => x !== m).join('، ') || '—'}`]] },
      action: async () => {
        try { await api.put(`/admin/agency/groups/${g.id}/`, { name: g.name, owner: g.owner, note: g.note, members: g.members.filter((x) => x !== m) }) } catch (e) { throw new Error(groupErr(e, lang)) }
      },
    })
    if (ok) { toast.success(s.g_saved); load() }
  }

  return (
    <div className="ag space-y-4">
      <Header s={s} switches={dash?.switches} />
      <div className="ag-gbar">
        <p className="text-sm text-muted">{s.g_intro}</p>
        {can('agency.manage') && (
          <button type="button" className="ag-act" data-tone="primary" onClick={() => edit(null)} disabled={!writable || !admins} title={!writable ? s.cutover : undefined}><Ic n="plus" />{s.g_create}</button>
        )}
      </div>
      <Alert>{err}</Alert>
      {d === null ? <div className="grid place-items-center py-16"><Spinner /></div> : d && (
        d.results.length === 0 ? <div className="card text-sm text-muted">{s.groups_none}</div> : d.results.map((g) => (
          <section key={g.id} className="card ag-card">
            <div className="ag-card-h ag-gh">
              <div className="ag-gh-t">
                <h3 className="ag-sh" data-ac="purple"><Ic n="users" size={15} /><bdi>{title(g)}</bdi></h3>
                <span className="ag-gh-o">{s.g_owner}: <Link to={`/agency/admins/${encodeURIComponent(g.owner)}`}><bdi>{g.owner}</bdi></Link></span>
              </div>
              {can('agency.manage') && (
                <div className="ag-actions">
                  <button type="button" className="ag-act" data-tone="neutral" onClick={() => edit(g)} disabled={!writable}><Ic n="edit" />{s.g_edit}</button>
                  <button type="button" className="ag-act" data-tone="danger" onClick={() => remove(g)} disabled={!writable}><Ic n="trash" />{s.g_delete}</button>
                </div>
              )}
            </div>
            <dl className="ag-nums ag-nums--counts">
              <div><dt>{s.g_accounts}</dt><dd><B>{digits(g.totals.accounts, lang)}</B></dd></div>
              <div><dt>{s.total_sold}</dt><dd><B>{g.totals.total_sold_fmt}</B><GB b={g.totals.total_sold_bytes} /></dd></div>
              <div><dt>{s.used}</dt><dd><B>{g.totals.used_fmt}</B><GB b={g.totals.used_bytes} /></dd></div>
              <div><dt>{s.users_col}</dt><dd><B>{digits(g.totals.user_count, lang)}</B><span className="ag-users-on"> / <B>{digits(g.totals.active_user_count, lang)}</B> {s.users_on}</span></dd></div>
            </dl>
            {g.rows.length > 0 && (
              <div className="ag-table-wrap mt-3">
                <table className="ag-table ag-gtable">
                  <thead><tr><TH i="user" ac="blue">{s.admins}</TH><TH i="status" ac="green">{s.status}</TH><TH i="usage" ac="orange">{s.usage}</TH><TH i="sold" ac="blue">{s.total_sold}</TH><TH i="used" ac="purple">{s.used}</TH><TH i="users" ac="blue">{s.users_col}</TH>{can('agency.manage') && <th><span className="sr-only">{s.g_remove_member}</span></th>}</tr></thead>
                  <tbody>
                    {g.rows.map((r) => (
                      <tr key={r.username}>
                        <td className="ag-t-name" data-label={s.admins}>
                          <Link to={`/agency/admins/${encodeURIComponent(r.username)}`}>{r.username}</Link>
                          <span className="ag-t-grp" data-role={r.role}>{r.role === 'owner' ? s.owner : s.g_member}</span>
                        </td>
                        <td className="ag-t-st" data-label={s.status}><StatusPill code={r.status_code} s={s} /></td>
                        <td className="ag-t-usage" data-label={s.usage}>{r.is_unlimited ? <span className="text-muted">{s.unl}</span> : <><UsageBar pct={r.usage_percent} /><B>{r.usage_percent}%</B></>}</td>
                        <td data-label={s.total_sold}><B>{r.total_sold_fmt}</B><GB b={r.bytes?.total_sold} block /></td>
                        <td data-label={s.used}><B>{r.used_fmt}</B><GB b={r.bytes?.used} block /></td>
                        <td data-label={s.users_col}><span><B>{digits(r.user_count, lang)}</B><span className="ag-users-on"> / <B>{digits(r.active_user_count, lang)}</B> {s.users_on}</span></span></td>
                        {can('agency.manage') && (
                          <td className="ag-gtable-x">
                            {r.role === 'member' && <button type="button" className="ag-act ag-act--sm" data-tone="danger" disabled={!writable} onClick={() => dropMember(g, r.username)}><Ic n="x" size={13} />{s.g_remove}</button>}
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {g.missing.length > 0 && (
              <div className="ag-members mt-2">
                <span className="text-xs text-muted">{s.missing}:</span>
                {g.missing.map((m) => (
                  <span key={m} className="ag-member" data-missing>
                    <bdi>{m}</bdi>
                    {can('agency.manage') && g.members.includes(m) && <button type="button" className="ag-member-x" disabled={!writable} onClick={() => dropMember(g, m)} aria-label={`${s.g_remove_member}: ${m}`}>×</button>}
                  </span>
                ))}
              </div>
            )}
            {g.note && <p className="text-xs text-muted mt-2">{s.note}: {g.note}</p>}
            <div className="ag-g-foot">
              <GroupActivity groupId={g.id} />
              {can('agency.accounting') && <Link to={`/agency/ledger/groups/${g.id}`} className="ag-act ag-act--sm" data-tone="neutral"><Ic n="doc" size={13} />{(LT[lang] || LT.fa).tab}</Link>}
            </div>
          </section>
        ))
      )}
    </div>
  )
}

// ------------------------------------------------------------------ sync logs
function SyncRows({ rows, s, lang }) {
  if (!rows.length) return <p className="ag-empty">{s.logs_none}</p>
  return (
    <ul className="ag-logs">
      {rows.map((l) => (
        <li key={l.id}>
          <span className="ag-log-st" data-st={l.status}>{s['s_' + l.status] || l.status}</span>
          <span className="ag-log-t">{jalali(l.created_at, true, lang)}</span>
          <span className="ag-log-n"><B>{digits(l.admins_synced, lang)}</B> {s.synced} · <B>{l.duration_seconds}s</B></span>
          {l.error_message && <pre className="ag-log-err">{l.error_message}</pre>}
        </li>
      ))}
    </ul>
  )
}

export function AgencySyncLogs() {
  const [s, lang] = useT()
  const [st, setSt] = useState('')
  const [rows, setRows] = useState(null)
  const [meta, setMeta] = useState(null)
  const [err, setErr] = useState('')
  const [dash] = useLoad('/admin/agency/')
  const load = (offset = 0) => api.get(`/admin/agency/sync-logs/?limit=50&offset=${offset}${st ? '&status=' + st : ''}`)
    .then((r) => { setMeta(r.data); setRows((cur) => (offset ? [...(cur || []), ...r.data.results] : r.data.results)) })
    .catch((e) => { setErr(apiError(e)); setRows((c) => c || []) })
  useEffect(() => { setRows(null); load(0) }, [st])
  return (
    <div className="ag space-y-4">
      <Header s={s} switches={dash?.switches} />
      <div className="ag-filters">
        {[['', s.all], ['success', s.s_success], ['partial', s.s_partial], ['failed', s.s_failed]].map(([k, label]) => (
          <button key={k || 'all'} type="button" className={'ag-chip' + (st === k ? ' on' : '')} aria-pressed={st === k} onClick={() => setSt(k)}>
            {label}{meta && k && <span className="ag-chip-n"><B>{digits(meta.summary[k], lang)}</B></span>}
          </button>
        ))}
      </div>
      <Alert>{err}</Alert>
      {rows === null ? <div className="grid place-items-center py-16"><Spinner /></div> : (
        <div className="card ag-card">
          <SyncRows rows={rows} s={s} lang={lang} />
          {meta?.next != null && <div className="flex justify-center mt-3"><button type="button" className="ag-act" data-tone="neutral" onClick={() => load(meta.next)}><Ic n="more" />{s.more}</button></div>}
        </div>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ settings
export function AgencySettings() {
  const [s] = useT()
  const { can } = useAuth()
  const confirm = useConfirm()
  const [d, err, load] = useLoad('/admin/agency/settings/')
  const [interval, setIntervalV] = useState('')
  const toast = useToast()
  const [e2, setE2] = useState('')
  useEffect(() => { if (d) setIntervalV(String(d.sync_interval_minutes)) }, [d])
  const manage = can('agency.manage')

  const patch = async (body) => {
    setE2('')
    try { await api.patch('/admin/agency/settings/', body); toast.success(s.saved); load() } catch (e) { setE2(apiError(e)) }
  }
  const toggleSync = async (on) => {
    if (on) {
      await confirm({
        tone: 'danger', title: s.cut_title, message: s.cut_msg, confirmLabel: s.confirm_go,
        reason: { label: s.cut_reason, required: true, placeholder: 'FINLAND-STOPPED' },
        action: async (typed) => { await api.patch('/admin/agency/settings/', { sync_enabled: true, confirm: typed }); load() },
      })
    } else if (await confirm({ tone: 'warning', title: s.sync_off_title, confirmLabel: s.confirm_go })) {
      patch({ sync_enabled: false, enforcement_enabled: false })
    }
  }
  const toggleEnf = async (on) => {
    if (!on) return patch({ enforcement_enabled: false })
    if (await confirm({ tone: 'warning', title: s.enf_title, message: s.set_enf_d, confirmLabel: s.confirm_go })) patch({ enforcement_enabled: true })
  }
  return (
    <div className="ag space-y-4">
      <Header s={s} switches={d || undefined} />
      <Alert>{err || e2}</Alert>
      {d === null ? <div className="grid place-items-center py-16"><Spinner /></div> : d && (
        <div className="card ag-card ag-settings">
          <div className="ag-set-row">
            <div><b>{s.set_sync}</b><p>{s.set_sync_d}</p></div>
            <Toggle checked={d.sync_enabled} disabled={!manage} onChange={(v) => toggleSync(v)} label={s.set_sync} />
          </div>
          <div className="ag-set-row">
            <div><b>{s.set_enf}</b><p>{s.set_enf_d}</p></div>
            <Toggle checked={d.enforcement_enabled} disabled={!manage || !d.sync_enabled} onChange={(v) => toggleEnf(v)} label={s.set_enf} />
          </div>
          <div className="ag-set-row">
            <div><b>{s.portal_set}</b><p>{s.portal_set_d}</p></div>
            <Toggle checked={!!d.portal_enabled} disabled={!manage} onChange={(v) => patch({ portal_enabled: v })} label={s.portal_set} />
          </div>
          <form className="ag-set-row" onSubmit={(e) => { e.preventDefault(); patch({ sync_interval_minutes: interval }) }}>
            <label className="ag-set-int"><b>{s.set_interval}</b>
              <input className="input" dir="ltr" inputMode="numeric" value={interval} disabled={!manage}
                onChange={(e) => setIntervalV(e.target.value)} aria-label={s.set_interval} />
            </label>
            <button className="ag-act" data-tone="primary" disabled={!manage}><Ic n="check" />{s.save}</button>
          </form>
        </div>
      )}
      {d && <PortalLinkCard s={s} />}
    </div>
  )
}

const CSS = `
.ag-listbar { display: flex; justify-content: flex-end; }
.ag-new { min-height: 40px; padding-inline: 16px; font-size: 13.5px; text-decoration: none; }
.ag-dhead { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.ag-dhead-lim { font-size: 12.5px; color: var(--c-text-muted); margin-inline-start: auto; }
.ag-dtabs { display: flex; gap: 4px; overflow-x: auto; padding: 4px; border-radius: 14px; border: 1px solid var(--c-border); background: var(--c-surface); scrollbar-width: thin; }
.ag-dtab { flex-shrink: 0; display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; border-radius: 10px; font-size: 13px; font-weight: 700;
  color: var(--c-text-muted); text-decoration: none; white-space: nowrap; }
.ag-dtab:hover { color: var(--c-text); background: color-mix(in srgb, var(--c-primary) 6%, transparent); }
.ag-dtab.on { color: #fff; background: color-mix(in srgb, var(--c-primary) 85%, #000); }
@media (max-width: 767px) {
  .ag-dtabs { display: grid; grid-template-columns: repeat(auto-fit, minmax(0, 1fr)); overflow: visible; }
  .ag-dtab { justify-content: center; padding: 8px 6px; font-size: 12px; flex-direction: column; gap: 3px; text-align: center; white-space: normal; line-height: 1.3; }
  .ag-dhead-lim { margin-inline-start: 0; width: 100%; }
  .ag-listbar .ag-new { width: 100%; justify-content: center; }
}

.ag-head { margin-bottom: 2px; }
.ag-tabs { display: flex; gap: 6px; overflow-x: auto; scrollbar-width: none; padding-bottom: 2px; }
.ag-tabs::-webkit-scrollbar { display: none; }
/* phones: every sub-tab visible at once (a hidden-scrollbar strip pushed Sync logs / Settings off-screen) */
@media (max-width: 767px) {
  .ag-tabs { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); overflow: visible; }
  .ag-tabs .ag-tab { justify-content: center; text-align: center; padding: 8px 6px; min-width: 0; overflow: hidden; }
}
.ag-tab { white-space: nowrap; padding: 7px 14px; border-radius: 999px; font-size: 13px; font-weight: 700; color: var(--c-text);
  border: 1px solid var(--c-border); text-decoration: none; }
.ag-tab:hover { border-color: var(--c-primary); }
.ag-tab-badge { display: inline-grid; place-items: center; min-width: 18px; height: 18px; padding: 0 5px; margin-inline-start: 6px; border-radius: 999px;
  font-size: 11px; font-weight: 800; color: #fff; background: var(--c-danger); vertical-align: middle; }
.ag-g-foot { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 8px; }
.ag-g-foot > .ag-act { margin-top: 10px; }
.ag-g-foot .gm-activity { flex: 1 1 100%; order: 2; }
.ag-tab.on { background: color-mix(in srgb, var(--c-primary) 82%, #000); border-color: color-mix(in srgb, var(--c-primary) 82%, #000); color: #fff; }
.ag-cutover { display: flex; flex-direction: column; gap: 2px; padding: 10px 14px; border-radius: 12px; font-size: 13px; line-height: 1.7;
  color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 12%, transparent); border: 1px solid color-mix(in srgb, var(--c-warning) 30%, transparent); }
.ag-cutover span { color: var(--c-text); }
.ag-num { font-family: 'JetBrains Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }
.ag-kpis { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 170px), 1fr)); }
.ag-kpi { display: flex; flex-direction: column; gap: 6px; border-top: 3px solid var(--ac); padding: 14px 16px; min-width: 0; }
.ag-kpi-l { padding-inline-end: 34px; }
.ag-kpi-l { font-size: 12px; font-weight: 700; color: var(--c-muted-fg); }
.ag-kpi-val { font-size: 22px; font-weight: 800; line-height: 1.2; }
.ag-kpi-sub { font-size: 11.5px; color: var(--c-muted-fg); }
.ag-card { padding: 14px 16px; min-width: 0; }
.ag-card-h { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 10px; }
.ag-card-h h3 { font-size: 14px; font-weight: 800; }
.ag-count { font-size: 12px; font-weight: 700; padding: 2px 9px; border-radius: 999px; color: var(--c-primary-fg); background: color-mix(in srgb, var(--c-primary) 12%, transparent); }
.ag-empty { font-size: 13px; color: var(--c-text-muted); }
.ag-over { display: flex; flex-direction: column; }
.ag-over li { display: grid; grid-template-columns: minmax(0, 1.2fr) auto minmax(80px, 1fr) 64px minmax(0, 1fr); gap: 10px; align-items: center;
  padding: 9px 0; border-top: 1px solid var(--c-border); font-size: 13px; }
.ag-over li:first-child { border-top: 0; }
.ag-over-name { font-weight: 700; color: var(--c-text); text-decoration: none; overflow-wrap: anywhere; }
.ag-over-tag { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 999px; color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 14%, transparent); white-space: nowrap; }
.ag-over-tag[data-state="over"] { color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 14%, transparent); }
.ag-over-pct { font-weight: 700; text-align: end; }
.ag-over-sub { color: var(--c-muted-fg); font-size: 12px; text-align: end; }
.ag-bar { display: block; height: 7px; border-radius: 999px; background: color-mix(in srgb, var(--c-text-muted) 18%, transparent); overflow: hidden; min-width: 60px; }
.ag-bar i { display: block; height: 100%; border-radius: inherit; background: var(--c-primary); }
.ag-bar[data-tone="warning"] i { background: var(--c-warning); }
.ag-bar[data-tone="danger"] i { background: var(--c-danger); }
.ag-pill { display: inline-flex; align-items: center; gap: 5px; font-size: 11.5px; font-weight: 700; padding: 2px 9px; border-radius: 999px; white-space: nowrap;
  color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 14%, transparent); }
.ag-pill[data-st="panel_disabled"] { color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 14%, transparent); }
.ag-pill[data-st="pamp_limited"] { color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 14%, transparent); }
.ag-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; padding: 10px 12px; }
.ag-search { position: relative; display: flex; align-items: center; flex: 1 1 240px; max-width: 380px; min-width: 200px; }
.ag-search svg { position: absolute; inset-inline-start: 11px; color: var(--c-text-muted); pointer-events: none; }
.ag-search .input { width: 100%; height: 40px; padding-block: 0; padding-inline: 36px; }
.ag-search .input::-webkit-search-cancel-button { -webkit-appearance: none; appearance: none; }
.ag-x { position: absolute; inset-inline-end: 4px; width: 32px; height: 32px; border-radius: 999px; font-size: 20px; color: var(--c-text-muted); }
.ag-filters { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 14px; }
.ag-fg { display: inline-flex; align-items: center; gap: 5px; }
.ag-fg-l { font-size: 12px; font-weight: 700; color: var(--c-muted-fg); }
.ag-chip { height: 32px; padding: 0 12px; border-radius: 999px; font-size: 12.5px; font-weight: 600; white-space: nowrap; color: var(--c-text);
  border: 1px solid var(--c-border); background: transparent; display: inline-flex; align-items: center; gap: 6px; }
.ag-chip.on { background: color-mix(in srgb, var(--c-primary) 82%, #000); border-color: color-mix(in srgb, var(--c-primary) 82%, #000); color: #fff; }
.ag-chip-n { font-size: 11px; opacity: .85; }
.ag-group { height: 34px; padding-block: 0; width: auto; min-width: 140px; }
.ag-total { margin-inline-start: auto; font-size: 12.5px; font-weight: 600; color: var(--c-muted-fg); white-space: nowrap; }
.ag-table-wrap { padding: 0; overflow-x: auto; }
.ag-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.ag-table th { text-align: start; font-size: 12px; font-weight: 700; color: var(--c-muted-fg); padding: 10px 12px; border-bottom: 1px solid var(--c-border); white-space: nowrap; }
.ag-table td { padding: 9px 12px; border-bottom: 1px solid var(--c-border); white-space: nowrap; vertical-align: middle; }
.ag-table tr:last-child td { border-bottom: 0; }
.ag-t-name a { font-weight: 700; color: var(--c-text); text-decoration: none; }
.ag-t-name a:hover { color: var(--c-primary-fg); }
.ag-t-grp { display: inline-block; margin-inline-start: 6px; font-size: 11px; padding: 1px 7px; border-radius: 999px; color: var(--c-muted-fg); background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); }
.ag-t-usage { min-width: 150px; }
.ag-users { cursor: help; }
.ag-users-on { color: var(--c-muted-fg); font-size: 11px; }
/* admins list on desktop: fit the page without horizontal scroll */
@media (min-width: 768px) {
  .ag-admins th, .ag-admins td { padding: 9px 7px; }
  .ag-admins th:first-child, .ag-admins td:first-child { padding-inline-start: 12px; }
  .ag-admins th:last-child, .ag-admins td:last-child { padding-inline-end: 12px; }
  .ag-admins .ag-t-name { max-width: 210px; }
  .ag-admins .ag-t-nm { display: inline-block; max-width: 130px; overflow: hidden; text-overflow: ellipsis; vertical-align: bottom; }
  .ag-admins .ag-t-grp { margin-inline-start: 4px; font-size: 10px; padding: 0 5px; max-width: 64px; overflow: hidden; text-overflow: ellipsis; vertical-align: middle; }
  .ag-admins .ag-t-usage { min-width: 0; }
  .ag-admins .ag-t-usage .ag-bar { width: 48px; min-width: 48px; margin-inline-end: 6px; }
}
.ag-t-usage .ag-bar { display: inline-block; width: 80px; vertical-align: middle; margin-inline-end: 8px; }
.ag-sign[data-sign="pos"] { color: var(--c-success-fg); } .ag-sign[data-sign="neg"] { color: var(--c-danger-fg); }
.ag-back { font-size: 13px; color: var(--c-primary-fg); text-decoration: none; }
.ag-detail-h { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.ag-detail-bar { display: flex; align-items: center; gap: 10px; margin: 10px 0; }
.ag-detail-bar .ag-bar { flex: 1; height: 9px; }
.ag-sec-h { font-size: 13px; font-weight: 800; margin: 14px 0 8px; color: var(--c-muted-fg); }
.ag-nums { display: grid; gap: 8px; grid-template-columns: repeat(auto-fill, minmax(min(100%, 160px), 1fr)); }
.ag-nums > div { padding: 9px 11px; border-radius: 10px; border: 1px solid var(--c-border); min-width: 0; }
.ag-nums dt { font-size: 11.5px; color: var(--c-muted-fg); font-weight: 600; }
.ag-nums dd { font-size: 15px; font-weight: 800; margin-top: 2px; overflow-wrap: anywhere; }
.ag-nums--counts { grid-template-columns: repeat(auto-fill, minmax(min(100%, 110px), 1fr)); }
.ag-locked { font-size: 12.5px; font-weight: 700; color: var(--c-warning-fg); margin-bottom: 8px; }
.ag-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.ag-act { min-height: 38px; padding: 0 14px; border-radius: 10px; font-size: 13px; font-weight: 700; border: 1px solid var(--c-border); color: var(--c-text); background: transparent; }
.ag-act:hover:not(:disabled) { border-color: var(--c-primary); }
.ag-act.danger { color: var(--c-danger-fg); }
.ag-act:disabled { opacity: .5; cursor: not-allowed; }
/* meaning by colour: primary = filled brand blue, success = money in / enable, warning = caution,
   danger = destructive, neutral = soft gray. Text uses the contrast-safe --c-*-fg tokens. */
.ag-act[data-tone] { border-color: transparent; transition: background-color .15s, border-color .15s; }
.ag-act[data-tone="primary"] { background: color-mix(in srgb, var(--c-primary) 84%, #000); color: #fff; }
.ag-act[data-tone="primary"]:hover:not(:disabled) { background: color-mix(in srgb, var(--c-primary) 70%, #000); border-color: transparent; }
.ag-act[data-tone="success"] { color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 13%, transparent); border-color: color-mix(in srgb, var(--c-success) 30%, transparent); }
.ag-act[data-tone="warning"] { color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 14%, transparent); border-color: color-mix(in srgb, var(--c-warning) 32%, transparent); }
.ag-act[data-tone="danger"] { color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 11%, transparent); border-color: color-mix(in srgb, var(--c-danger) 30%, transparent); }
.ag-act[data-tone="neutral"] { color: var(--c-text); background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); }
.ag-act[data-tone="success"]:hover:not(:disabled) { background: color-mix(in srgb, var(--c-success) 22%, transparent); border-color: color-mix(in srgb, var(--c-success) 45%, transparent); }
.ag-act[data-tone="warning"]:hover:not(:disabled) { background: color-mix(in srgb, var(--c-warning) 24%, transparent); border-color: color-mix(in srgb, var(--c-warning) 48%, transparent); }
.ag-act[data-tone="danger"]:hover:not(:disabled) { background: color-mix(in srgb, var(--c-danger) 19%, transparent); border-color: color-mix(in srgb, var(--c-danger) 45%, transparent); }
.ag-act[data-tone="neutral"]:hover:not(:disabled) { background: color-mix(in srgb, var(--c-text-muted) 20%, transparent); border-color: transparent; }
.ag-act:focus-visible { outline: 2px solid var(--c-primary); outline-offset: 2px; }
.ag-form { display: grid; gap: 10px; grid-template-columns: 1fr 1fr; margin-top: 10px; }
.ag-form label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; font-weight: 700; }
.ag-snap { max-height: 360px; overflow-y: auto; border: 1px solid var(--c-border); border-radius: 10px; }
.ag-logs { display: flex; flex-direction: column; }
.ag-logs li { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; padding: 8px 0; border-top: 1px solid var(--c-border); font-size: 13px; }
.ag-logs li:first-child { border-top: 0; }
.ag-log-st { font-size: 11.5px; font-weight: 700; padding: 2px 9px; border-radius: 999px; color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 14%, transparent); }
.ag-log-st[data-st="partial"] { color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 14%, transparent); }
.ag-log-st[data-st="failed"] { color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 14%, transparent); }
.ag-log-t { color: var(--c-muted-fg); font-size: 12.5px; }
.ag-log-err { flex-basis: 100%; white-space: pre-wrap; font-size: 12px; color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 6%, transparent); padding: 6px 10px; border-radius: 8px; margin: 0; }
.ag-groups { display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(min(100%, 320px), 1fr)); }
.ag-members { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.ag-member { font-size: 12.5px; font-weight: 600; padding: 3px 10px; border-radius: 999px; border: 1px solid var(--c-border); color: var(--c-text); text-decoration: none; }
.ag-member[data-missing] { color: var(--c-danger-fg); border-color: color-mix(in srgb, var(--c-danger) 40%, transparent); }
.ag-settings { display: flex; flex-direction: column; gap: 4px; padding: 6px 16px; }
.ag-set-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 12px 0; border-top: 1px solid var(--c-border); }
.ag-set-row:first-child { border-top: 0; }
.ag-set-row p { font-size: 12.5px; color: var(--c-text-muted); margin-top: 2px; line-height: 1.7; }
.ag-set-int { display: flex; align-items: center; gap: 12px; }
.ag-set-int .input { width: 90px; }
.ag-sort { font: inherit; color: inherit; background: none; border: 0; padding: 0; cursor: pointer; white-space: nowrap; }
.ag-sort:hover { color: var(--c-text); }
.ag-portal { display: flex; gap: 14px; align-items: flex-start; }
.ag-portal-main { flex: 1; min-width: 0; }
.ag-portal-url { display: block; font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 13px; padding: 8px 11px; border-radius: 10px; border: 1px solid var(--c-border); overflow-wrap: anywhere; }
.ag-portal-qr { border-radius: 10px; background: #fff; padding: 6px; border: 1px solid var(--c-border); }
.ag-gbar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 16px; }
.ag-gh { flex-wrap: wrap; align-items: flex-start; }
.ag-gh-t { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.ag-gh-t h3 { overflow-wrap: anywhere; }
.ag-gh-o { font-size: 12px; color: var(--c-muted-fg); }
.ag-gh-o a { color: var(--c-text); font-weight: 700; text-decoration: none; }
.ag-t-grp[data-role="owner"] { color: var(--c-primary-fg); background: color-mix(in srgb, var(--c-primary) 12%, transparent); }
.ag-gtable-x { text-align: end; width: 1%; }
.ag-gh .ag-act, .ag-gbar .ag-act { white-space: nowrap; }
.ag-act--sm { min-height: 30px; padding: 0 10px; font-size: 12px; }
.ag-member--x { cursor: pointer; background: transparent; font: inherit; font-size: 12.5px; font-weight: 600; }
.ag-member--x:hover { border-color: var(--c-danger); color: var(--c-danger-fg); }
.ag-member-x { margin-inline-start: 4px; color: inherit; font-weight: 800; background: none; border: 0; cursor: pointer; }
.ag-gform { display: flex; flex-direction: column; gap: 12px; margin-top: 10px; text-align: start; }
.ag-gform label, .ag-gform-m { display: flex; flex-direction: column; gap: 5px; font-size: 12px; font-weight: 700; }
.ag-gform small { font-weight: 500; color: var(--c-muted-fg); }
.ag-gform-l { display: inline-flex; align-items: center; gap: 6px; }
.ag-gpick { max-height: 200px; overflow-y: auto; border: 1px solid var(--c-border); border-radius: 10px; padding: 4px; display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 150px), 1fr)); gap: 2px; }
.ag-gpick-i { flex-direction: row !important; align-items: center; gap: 6px !important; padding: 6px 8px; border-radius: 8px; font-weight: 600 !important; font-size: 12.5px !important; cursor: pointer; }
.ag-gpick-i:hover { background: color-mix(in srgb, var(--c-text-muted) 10%, transparent); }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }

/* v1.14 polish: accents, icons, dots, hover/pressed — layout and sizes unchanged */
.ag-kpi { position: relative; border-top-color: var(--ac) !important; }
.ag-kpi-ico { position: absolute; top: 12px; inset-inline-end: 12px; width: 28px; height: 28px; border-radius: 9px; display: grid; place-items: center;
  color: var(--ac); background: color-mix(in srgb, var(--ac) 13%, transparent); }
.ag-th { display: inline-flex; align-items: center; gap: 5px; }
.ag-th .agi { color: var(--ac); }
.ag-sh { display: flex; align-items: center; gap: 7px; }
.ag-sh .agi { color: var(--ac); }
.ag-pill::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
.ag-table tbody tr { transition: background-color .12s; }
.ag-table tbody tr:hover > td { background: color-mix(in srgb, var(--c-primary) 5%, transparent); }
.ag-nums--counts > div[data-k="active"] dd { color: var(--c-success-fg); }
.ag-nums--counts > div[data-k="on_hold"] dd { color: var(--c-primary-fg); }
.ag-nums--counts > div[data-k="limited"] dd { color: var(--c-warning-fg); }
.ag-nums--counts > div[data-k="disabled"] dd { color: var(--c-danger-fg); }
.ag-nums--counts > div[data-k="expired"] dd { color: var(--c-muted-fg); }
.ag-act { display: inline-flex; align-items: center; justify-content: center; gap: 6px; transition: background-color .15s, border-color .15s, transform .08s; }
.ag-act:active:not(:disabled) { transform: translateY(1px) scale(.98); }
.ag-act[data-tone="primary"]:active:not(:disabled) { background: color-mix(in srgb, var(--c-primary) 60%, #000); }

/* v1.15: limits section, limit form, tinted cards */
.ag-limits .ag-card-h { flex-wrap: wrap; }
.ag-limits-cur { font-size: 13px; color: var(--c-muted-fg); margin: -2px 0 10px; }
.ag-limits-cur b { color: var(--c-text); }
.ag-anchor { scroll-margin-top: 80px; }
.ag-form--limit { grid-template-columns: 1fr; }
.ag-form-cur { font-size: 12.5px; color: var(--c-muted-fg); }
.ag-form-amt { display: grid; grid-template-columns: minmax(0, 1fr) 96px; gap: 10px; }
.ag-form-err { display: block; font-size: 12px; font-weight: 600; color: var(--c-danger-fg); }
.ag-preview { display: flex; flex-direction: column; border-top: 1px solid var(--c-border); margin-top: 4px; }
.ag-preview > div { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 4px 12px; padding: 8px 0; border-bottom: 1px solid var(--c-border); font-size: 13px; }
.ag-preview dt { color: var(--c-muted-fg); }
.ag-preview-base { background: color-mix(in srgb, var(--c-warning) 10%, transparent); padding-inline: 8px !important; border-radius: 8px; }
.ag-kpi, .ag-nums > div[data-ac], .ag-nums--counts > div[data-k] {
  background-image: linear-gradient(color-mix(in srgb, var(--ac) 11%, transparent), color-mix(in srgb, var(--ac) 11%, transparent));
  border-color: color-mix(in srgb, var(--ac) 32%, var(--c-border)) !important; }
.ag-nums--counts > div[data-k="total"] { --ac: var(--ac-purple); } .ag-nums--counts > div[data-k="active"] { --ac: var(--ac-green); }
.ag-nums--counts > div[data-k="on_hold"] { --ac: var(--ac-blue); } .ag-nums--counts > div[data-k="limited"] { --ac: var(--ac-orange); }
.ag-nums--counts > div[data-k="disabled"] { --ac: var(--ac-red); } .ag-nums--counts > div[data-k="expired"] { --ac: var(--ac-gray); }
.ag-kpi { border-top-color: var(--ac) !important; }

/* v1.15.1: GB next to TB values */
.ag-gb { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: .72em; font-weight: 500; color: var(--c-muted-fg); margin: 0 6px; white-space: nowrap; }   /* dir=ltr span: margin on both sides works in RTL too */
.ag-gb--block { display: block; margin: 0; font-size: 11px; line-height: 1.3; }
.ag-kpi-val { white-space: nowrap; }
.ag-kpi-val .ag-gb { display: block; margin: 2px 0 0; font-size: 12.5px; font-weight: 600; line-height: 1.3; }
.ag-lim { display: block; font-size: 11px; color: var(--c-muted-fg); margin-top: 2px; white-space: nowrap; }
.ag-lim .ag-gb { font-size: 10.5px; }
.ag-form-conv { font-size: 12px; color: var(--c-muted-fg); margin-top: -4px; }
/* narrow desktops: Hidden traffic (mirror of Sold Limit, still on the detail page) makes room for the GB lines */
@media (min-width: 768px) and (max-width: 1365px) { .ag-admins .ag-c-hid { display: none; } }
@media (max-width: 767px) {
  .ag-portal { flex-direction: column; }
  .ag-gpick-i { min-height: 44px; } .ag-gform .input { font-size: 16px; height: 44px; } .ag-act--sm { min-height: 40px; }
  .ag-table td.ag-gtable-x { grid-column: 1 / -1; width: auto; }
  .ag-tab { min-height: 40px; display: inline-flex; align-items: center; }
  .ag-toolbar { flex-direction: column; align-items: stretch; flex-wrap: nowrap; padding: 10px; }
  .ag-search { flex: none; max-width: none; min-width: 0; }
  .ag-search .input, .ag-group, .ag-set-int .input, .ag-form .input { font-size: 16px; height: 44px; }
  .ag-filters { flex-wrap: nowrap; overflow-x: auto; scrollbar-width: none; margin-inline: -10px; padding-inline: 10px; }
  .ag-fg { flex-shrink: 0; } .ag-fg + .ag-fg { padding-inline-start: 6px; border-inline-start: 1px solid var(--c-border); }
  .ag-fg-l { display: none; }
  .ag-chip { height: 44px; padding: 0 14px; flex-shrink: 0; }
  .ag-total { margin-inline-start: 0; }
  .ag-act { min-height: 44px; flex: 1 1 calc(50% - 8px); }
  .ag-over li { grid-template-columns: minmax(0, 1fr) auto; gap: 4px 10px; }
  .ag-over li .ag-bar { grid-column: 1 / -1; }
  .ag-over-pct, .ag-over-sub { text-align: start; }
  /* record cards instead of the wide table */
  .ag-table thead { display: none; }
  .ag-table, .ag-table tbody { display: block; }
  .ag-table tr { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px 12px; padding: 10px 12px; border-bottom: 1px solid var(--c-border); }
  .ag-table td { display: flex; flex-direction: column; gap: 1px; padding: 0; border: 0; white-space: normal; min-width: 0; }
  .ag-table td::before { content: attr(data-label); font-size: 11px; font-weight: 600; color: var(--c-muted-fg); }
  .ag-table td.ag-t-name { grid-column: 1; flex-direction: row; flex-wrap: wrap; align-items: center; }
  .ag-table td.ag-t-st { grid-column: 2; align-items: flex-end; }
  .ag-table td.ag-t-name::before, .ag-table td.ag-t-st::before { display: none; }
  .ag-table td.ag-t-usage { grid-column: 1 / -1; flex-direction: row; align-items: center; gap: 8px; }
  .ag-table td.ag-t-usage::before { display: none; }
  .ag-table td.ag-t-usage .ag-bar { flex: 1; width: auto; }
  .ag-table--plain tr { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .ag-set-row { flex-wrap: wrap; }
}
`
