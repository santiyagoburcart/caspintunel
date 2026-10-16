import { useEffect, useMemo, useState } from 'react'
import { Link, NavLink, useNavigate, useParams } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useAuth } from '../lib/auth'
import { jalali, digits } from '../lib/format'
import { copyToClipboard } from '../lib/clipboard'
import { Toggle } from '../components/ui'
import { useConfirm } from '../components/ConfirmDialog'
import { useToast } from '../components/Toast'
import { AGK_CSS, Btn, Empty, Icon, Menu, Money, Qty, Skeleton, SortTh, Status, Usage, useDensity } from '../components/agency/kit'
import { AgencyLedgerOverview, LedgerCard, LT } from './AgencyLedger'

// Agency panel (PAMP port). Every number comes from the backend (PAMP's own
// formulas, apps/agency); this file only lays out and formats. Sorting uses the
// raw values the server sends in `row.sort`.

const T = {
  fa: {
    title: 'پنل نمایندگی', sub: 'نماینده‌ها روی پنل پاسارگاد — محاسبات عیناً مانند PAMP',
    tab_dash: 'نمای کلی', tab_admins: 'نماینده‌ها', tab_groups: 'گروه‌ها', tab_logs: 'همگام‌سازی', tab_settings: 'تنظیمات',
    cutover: 'فعال پس از انتقال نهایی', cutover_note: 'PAMP فنلاند هنوز نسخهٔ اصلی است؛ تغییرات روی پنل فعلاً غیرفعال است.',
    total_sold: 'حجم فروخته‌شده', used: 'مصرف‌شده', remaining: 'باقی‌مانده', hidden: 'ترافیک پنهان', admins: 'نماینده', admins_n: 'نماینده‌ها',
    sold_limit: 'Sold Limit', limit: 'سقف', usage: 'مصرف', status: 'وضعیت', group: 'گروه', users_total: 'کل کاربران', users_active: 'فعال',
    balance: 'بدهی', deleted: 'از کاربران حذف‌شده', hidden_clamped: 'پنهان (حداقل صفر)',
    near_title: 'نزدیک یا بیش از سقف', near_sub: 'نماینده‌هایی که دست‌کم 80% سقف خود را مصرف کرده‌اند', near_none: 'هیچ نماینده‌ای به 80% سقف نرسیده است.',
    at_risk: 'نزدیک سقف', over: 'بیش از سقف',
    used_of: '{u} از {l}', last_sync: 'آخرین همگام‌سازی', never: 'هنوز انجام نشده', every: 'هر {n} دقیقه', sync_now: 'همگام‌سازی اکنون', synced: 'همگام‌سازی انجام شد',
    st_active: 'فعال', st_panel_disabled: 'غیرفعال (پنل)', st_pamp_limited: 'محدود', s_success: 'موفق', s_partial: 'ناقص', s_failed: 'ناموفق',
    search: 'جستجوی نماینده', clear: 'پاک کردن', all: 'همه', limited: 'سقف‌دار', unlimited: 'نامحدود', any_group: 'همهٔ گروه‌ها',
    n_admins: '{n} نماینده', none: 'نماینده‌ای با این فیلترها نیست.', reset_filters: 'حذف فیلترها',
    density: 'تراکم جدول', comfortable: 'معمولی', compact: 'فشرده', open: 'باز کردن', more: 'عملیات بیشتر',
    unl: 'نامحدود', back: 'نماینده‌ها',
    sec_numbers: 'اعداد PAMP', sec_users: 'کاربران', sec_send: 'ارسال به نماینده', sec_snap: 'آخرین مصرف کاربران', sec_syncs: 'همگام‌سازی‌های اخیر',
    c_total: 'کل', c_active: 'فعال', c_on_hold: 'در انتظار اتصال', c_limited: 'اتمام حجم', c_disabled: 'غیرفعال', c_expired: 'منقضی',
    warn80: 'به {p}% سقف رسیده است', blocked_pamp: 'به‌خاطر اتمام سقف محدود شده است', blocked_panel: 'روی پنل غیرفعال است',
    a_set: 'تغییر سقف', a_remove: 'حذف سقف (نامحدود)', a_disable: 'غیرفعال کردن ادمین', a_enable: 'فعال کردن ادمین',
    a_disable_users: 'غیرفعال کردن همهٔ کاربران', a_enable_users: 'فعال کردن همهٔ کاربران', a_reset: 'صفر کردن ترافیک حذف‌شده‌ها',
    a_copy_msg: 'کپی پیام برای نماینده', a_statement: 'صورت‌حساب',
    m_set: 'تنظیم روی', m_add: 'افزودن', m_reduce: 'کاهش', gb: 'حجم (گیگابایت)', mode: 'نوع تغییر',
    v_required: 'یک عدد مثبت وارد کنید', p_limit: 'سقف', p_remaining: 'باقی‌مانده پس از تغییر', p_charge: 'شارژ حساب',
    p_no_charge: 'بدون شارژ (افزایش نیست)', p_no_price: 'قیمتی برای امروز ثبت نشده — شارژ با مبلغ 0 ثبت می‌شود',
    p_panel: 'روی پنل پاسارگاد اعمال می‌شود', confirm: 'اعمال', done: 'انجام شد',
    d_disable: 'دسترسی ادمین به پنل بسته می‌شود؛ کاربرانش دست نمی‌خورند.', d_enable: 'دسترسی ادمین به پنل باز می‌شود.',
    d_disable_users: 'همهٔ {n} کاربر این ادمین روی پنل غیرفعال می‌شوند.', d_enable_users: 'همهٔ کاربران این ادمین روی پنل فعال می‌شوند.',
    d_reset: 'شمارندهٔ «از کاربران حذف‌شده» صفر می‌شود؛ حجم فروخته‌شده در همگام‌سازی بعدی کم می‌شود.',
    send_hint: 'این پیام را برای نماینده بفرستید؛ با نام کاربری و رمز پنل خودش وارد می‌شود.',
    copy_link: 'کپی لینک', copy_msg: 'کپی پیام', show_qr: 'نمایش QR', hide_qr: 'بستن QR', copied: 'کپی شد',
    msg_tpl: 'پرتال نمایندگی:\n{url}\nنام کاربری: {u}\nرمز عبور: همان رمز پنل پاسارگاد شما',
    portal_link: 'لینک پرتال نماینده‌ها',
    user: 'کاربر', last_seen: 'آخرین بررسی', snap_n: '{n} کاربر', load_more: 'بیشتر',
    groups_none: 'گروهی تعریف نشده است.', owner: 'مالک', note: 'یادداشت', missing: 'روی پنل نیست',
    logs_none: 'هنوز همگام‌سازی‌ای ثبت نشده است.', admins_synced: '{n} ادمین',
    set_sync: 'همگام‌سازی خودکار', set_sync_d: 'اعداد را هر چند دقیقه از پنل می‌گیرد. روشن کردن آن یعنی انتقال نهایی.',
    set_enf: 'اعمال خودکار سقف', set_enf_d: 'ادمینی که به 100% سقف برسد روی پنل غیرفعال و پس از افزایش سقف دوباره فعال می‌شود.',
    set_portal: 'پرتال نماینده‌ها', set_portal_d: 'نماینده‌ها با نام کاربری و رمز پنل خود وارد می‌شوند و فقط اعداد خودشان را می‌بینند.',
    set_interval: 'فاصلهٔ همگام‌سازی', minutes: 'دقیقه', save: 'ذخیره', saved: 'ذخیره شد', interval_err: 'عددی بین 1 تا 1440',
    cut_title: 'روشن کردن همگام‌سازی = انتقال نهایی', cut_msg: 'از این لحظه این سرور اعداد را از پنل می‌گیرد. دو همگام‌سازی هم‌زمان روی یک پنل اعداد را خراب می‌کند.',
    cut_reason: 'برای تأیید بنویسید: FINLAND-STOPPED', sync_off_title: 'همگام‌سازی خاموش شود؟', enf_title: 'اعمال خودکار سقف روشن شود؟',
    sec_switches: 'کلیدها',
  },
  en: {
    title: 'Agency Panel', sub: 'Reseller admins on the PasarGuard panel — calculated exactly like PAMP',
    tab_dash: 'Overview', tab_admins: 'Admins', tab_groups: 'Groups', tab_logs: 'Sync', tab_settings: 'Settings',
    cutover: 'Available after the final cut-over', cutover_note: 'The Finland PAMP is still the live instance; panel changes are off for now.',
    total_sold: 'Total Sold', used: 'Used', remaining: 'Remaining', hidden: 'Hidden traffic', admins: 'Admin', admins_n: 'Admins',
    sold_limit: 'Sold Limit', limit: 'Limit', usage: 'Usage', status: 'Status', group: 'Group', users_total: 'Total users', users_active: 'Active',
    balance: 'Balance', deleted: 'From deleted users', hidden_clamped: 'Hidden (min 0)',
    near_title: 'At or near the limit', near_sub: 'Admins who have used at least 80% of their limit', near_none: 'No admin has reached 80% of their limit.',
    at_risk: 'Near limit', over: 'Over limit',
    used_of: '{u} of {l}', last_sync: 'Last sync', never: 'not yet', every: 'every {n} min', sync_now: 'Sync now', synced: 'Sync finished',
    st_active: 'Active', st_panel_disabled: 'Disabled (panel)', st_pamp_limited: 'Limited', s_success: 'Success', s_partial: 'Partial', s_failed: 'Failed',
    search: 'Search admins', clear: 'Clear', all: 'All', limited: 'Limited', unlimited: 'Unlimited', any_group: 'All groups',
    n_admins: '{n} admins', none: 'No admin matches these filters.', reset_filters: 'Clear filters',
    density: 'Table density', comfortable: 'Comfortable', compact: 'Compact', open: 'Open', more: 'More actions',
    unl: 'Unlimited', back: 'Admins',
    sec_numbers: 'PAMP numbers', sec_users: 'Users', sec_send: 'Send to reseller', sec_snap: 'Last known user usage', sec_syncs: 'Recent syncs',
    c_total: 'Total', c_active: 'Active', c_on_hold: 'On hold', c_limited: 'Limited', c_disabled: 'Disabled', c_expired: 'Expired',
    warn80: 'reached {p}% of the limit', blocked_pamp: 'Limited — the limit is used up', blocked_panel: 'Disabled on the panel',
    a_set: 'Change limit', a_remove: 'Remove limit (unlimited)', a_disable: 'Disable admin', a_enable: 'Enable admin',
    a_disable_users: 'Disable all users', a_enable_users: 'Enable all users', a_reset: 'Reset deleted-users traffic',
    a_copy_msg: 'Copy message for reseller', a_statement: 'Statement',
    m_set: 'Set to', m_add: 'Add', m_reduce: 'Reduce', gb: 'Volume (GB)', mode: 'Change',
    v_required: 'Enter a positive number', p_limit: 'Limit', p_remaining: 'Remaining after', p_charge: 'Account charge',
    p_no_charge: 'No charge (not an increase)', p_no_price: 'No price set for today — the charge is recorded at 0',
    p_panel: 'Applied on the PasarGuard panel', confirm: 'Apply', done: 'Done',
    d_disable: 'The admin loses panel access; their users keep working.', d_enable: 'The admin gets panel access back.',
    d_disable_users: 'All {n} users of this admin are disabled on the panel.', d_enable_users: 'All users of this admin are enabled on the panel.',
    d_reset: 'The "from deleted users" counter goes to 0; Total Sold drops at the next sync.',
    send_hint: 'Send this to the reseller; they sign in with their own panel username and password.',
    copy_link: 'Copy link', copy_msg: 'Copy message', show_qr: 'Show QR', hide_qr: 'Hide QR', copied: 'Copied',
    msg_tpl: 'Reseller portal:\n{url}\nUsername: {u}\nPassword: your PasarGuard panel password',
    portal_link: 'Reseller portal link',
    user: 'User', last_seen: 'Last seen', snap_n: '{n} users', load_more: 'Load more',
    groups_none: 'No groups defined.', owner: 'Owner', note: 'Note', missing: 'not on the panel',
    logs_none: 'No sync logged yet.', admins_synced: '{n} admins',
    set_sync: 'Automatic sync', set_sync_d: 'Pulls the numbers from the panel every few minutes. Turning it on IS the final cut-over.',
    set_enf: 'Automatic limit enforcement', set_enf_d: 'An admin at 100% of their limit is disabled on the panel and re-enabled once the limit is raised.',
    set_portal: 'Reseller portal', set_portal_d: 'Resellers sign in with their panel username and password and see only their own numbers.',
    set_interval: 'Sync interval', minutes: 'min', save: 'Save', saved: 'Saved', interval_err: 'A number from 1 to 1440',
    cut_title: 'Turning sync on = the final cut-over', cut_msg: 'From now on this server pulls the numbers from the panel. Two syncs against one panel corrupt the numbers.',
    cut_reason: 'Type FINLAND-STOPPED to confirm', sync_off_title: 'Turn the sync off?', enf_title: 'Turn on automatic enforcement?',
    sec_switches: 'Switches',
  },
}
const useT = () => { const { lang } = useI18n(); return [T[lang] || T.fa, lang] }
const enc = encodeURIComponent
const arrow = (lang) => (lang === 'fa' ? '←' : '→')
const logCode = (st) => (st === 'success' ? 'active' : st === 'failed' ? 'panel_disabled' : 'pamp_limited')

function useLoad(url, deps = []) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const load = () => api.get(url).then((r) => { setData(r.data); setErr('') }).catch((e) => { setErr(apiError(e)); setData((d) => d || false) })
  useEffect(() => { load() }, deps)
  return [data, err, load]
}

function Header({ s, switches, actions }) {
  const { can } = useAuth()
  const { lang } = useI18n()
  const tabs = [['/agency', s.tab_dash, true], ['/agency/admins', s.tab_admins], ['/agency/groups', s.tab_groups],
    ...(can('agency.accounting') ? [['/agency/ledger', (LT[lang] || LT.fa).tab]] : []),
    ['/agency/sync-logs', s.tab_logs], ['/agency/settings', s.tab_settings]]
  return (
    <>
      <style>{AGK_CSS + CSS}</style>
      <header className="ag-head">
        <div><h1>{s.title}</h1><p>{s.sub}</p></div>
        {actions && <div className="ag-head-a">{actions}</div>}
      </header>
      <nav className="ag-tabs" aria-label={s.title}>
        {tabs.map(([to, label, end]) => (
          <NavLink key={to} to={to} end={!!end} className={({ isActive }) => 'ag-tab' + (isActive ? ' on' : '')}>{label}</NavLink>
        ))}
      </nav>
      {switches && !switches.writes_enabled && <p className="ag-note" role="note"><b>{s.cutover}</b> — {s.cutover_note}</p>}
    </>
  )
}

const Err = ({ children }) => (children ? <p className="ag-err" role="alert">{children}</p> : null)
const N = ({ v }) => <bdi dir="ltr" className="agk-qty">{v}</bdi>

// ───────────────────────────────────────────────────────────── dashboard
export function AgencyDashboard() {
  const [s, lang] = useT()
  const { can } = useAuth()
  const toast = useToast()
  const [d, err, load] = useLoad('/admin/agency/')
  const [busy, setBusy] = useState(false)
  const syncNow = async () => {
    setBusy(true)
    try { const r = await api.post('/admin/agency/sync-now/'); toast.success(r.data.message || s.synced); load() } catch (e) { toast.error(apiError(e)) } finally { setBusy(false) }
  }
  const canSync = d?.switches?.writes_enabled && can('agency.manage')
  return (
    <div className="ag">
      <Header s={s} switches={d?.switches}
        actions={canSync && <Btn variant="tonal" icon="sync" loading={busy} onClick={syncNow}>{s.sync_now}</Btn>} />
      <Err>{err}</Err>
      {d === null ? <Skeleton rows={4} cols={5} /> : d && (
        <>
          <section className="ag-stats" aria-label={s.title}>
            {[[s.total_sold, d.total_sold_fmt], [s.used, d.total_used_fmt], [s.remaining, d.total_remaining_fmt], [s.hidden, d.total_hidden_fmt]].map(([k, v]) => (
              <div key={k} className="ag-stat"><span className="ag-stat-k">{k}</span><span className="ag-stat-v"><Qty v={v} unl={s.unl} /></span></div>
            ))}
            <div className="ag-stat">
              <span className="ag-stat-k">{s.admins_n}</span>
              <span className="ag-stat-v"><N v={digits(d.admin_count, lang)} /></span>
              <span className="ag-stat-s">
                <Status code="active" label={`${digits(d.active_count, lang)} ${s.st_active}`} />
                {d.pamp_limited_count > 0 && <Status code="pamp_limited" label={`${digits(d.pamp_limited_count, lang)} ${s.st_pamp_limited}`} />}
                {d.disabled_count > 0 && <Status code="panel_disabled" label={`${digits(d.disabled_count, lang)} ${s.st_panel_disabled}`} />}
              </span>
            </div>
          </section>

          <section className="ag-sec">
            <div className="ag-sec-h">
              <div><h2>{s.near_title}</h2><p>{s.near_sub}</p></div>
              <span className="ag-count">{digits(d.near_limit_count, lang)}</span>
            </div>
            {d.over_limit.length === 0 ? <Empty title={s.near_none} /> : (
              <div className="ag-tablewrap">
                <table className="ag-table ag-near">
                  <thead><tr><th>{s.admins}</th><th>{s.usage}</th><th className="num">{s.used}</th><th className="num">{s.limit}</th><th>{s.status}</th></tr></thead>
                  <tbody>
                    {d.over_limit.map((o) => (
                      <tr key={o.username}>
                        <td className="ag-name"><Link to={`/agency/admins/${enc(o.username)}`}>{o.username}</Link></td>
                        <td className="c-usage"><Usage pct={o.pct} /></td>
                        <td className="num" data-label={s.used}><Qty v={o.used_fmt} /></td>
                        <td className="num" data-label={s.limit}><Qty v={o.limit_fmt} /></td>
                        <td className="c-status"><Status code={o.state === 'over' ? 'panel_disabled' : 'pamp_limited'} label={o.state === 'over' ? s.over : s.at_risk} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
          <p className="ag-meta">
            {s.last_sync}: {d.last_sync ? <>{jalali(d.last_sync.created_at, true, lang)} <Status code={logCode(d.last_sync.status)} label={s['s_' + d.last_sync.status]} /></> : s.never}
            {d.switches?.sync_enabled && <> · {s.every.replace('{n}', digits(d.switches.sync_interval_minutes, lang))}</>}
          </p>
        </>
      )}
    </div>
  )
}

// ───────────────────────────────────────────────────────────── admins list
const COLS = [
  ['status', 'status'], ['usage', 'usage'], ['total_sold', 'total_sold', true], ['sold_limit', 'sold_limit', true],
  ['hidden', 'hidden', true], ['remaining', 'remaining', true], ['used', 'used', true], ['users', 'users_total', true], ['active', 'users_active', true],
]
export function AgencyAdmins() {
  const [s, lang] = useT()
  const toast = useToast()
  const nav = useNavigate()
  const [q, setQ] = useState('')
  const [term, setTerm] = useState('')
  const [st, setSt] = useState('')
  const [lim, setLim] = useState('')
  const [grp, setGrp] = useState('')
  const [sort, setSort] = useState({ k: 'usage', dir: -1 })
  const [density, setDensity] = useDensity()
  useEffect(() => { const h = setTimeout(() => setTerm(q.trim()), 250); return () => clearTimeout(h) }, [q])
  const qs = new URLSearchParams(Object.entries({ search: term, status: st, limit: lim, group: grp }).filter(([, v]) => v)).toString()
  const [d, err] = useLoad(`/admin/agency/admins/${qs ? '?' + qs : ''}`, [qs])
  const [dash] = useLoad('/admin/agency/')
  const [link] = useLoad('/admin/agency/portal-link/')
  const hasBal = d?.results?.[0]?.balance !== undefined
  const rows = useMemo(() => {
    if (!d) return []
    const key = (r) => (sort.k === 'name' ? r.username.toLowerCase() : sort.k === 'status' ? r.status_code : sort.k === 'balance' ? Number(r.balance || 0) : (r.sort || {})[sort.k] ?? 0)
    return [...d.results].sort((a, b) => { const x = key(a), y = key(b); return (x > y ? 1 : x < y ? -1 : 0) * sort.dir })
  }, [d, sort])
  const filtered = !!(term || st || lim || grp)
  const copyMsg = async (u) => { (await copyToClipboard(s.msg_tpl.replace('{url}', link?.url || '').replace('{u}', u))) ? toast.success(s.copied) : toast.error('—') }
  const chip = (v, cur, set, label) => (
    <button type="button" key={v || 'all'} className={'ag-chip' + (cur === v ? ' on' : '')} aria-pressed={cur === v} onClick={() => set(v)}>{label}</button>
  )
  return (
    <div className="ag">
      <Header s={s} switches={dash?.switches} />
      <div className="ag-toolbar">
        <label className="ag-search">
          <Icon name="search" size={17} />
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={s.search} aria-label={s.search} />
          {q && <button type="button" className="ag-search-x" onClick={() => setQ('')} aria-label={s.clear}><Icon name="x" size={16} /></button>}
        </label>
        <div className="ag-chips" role="group" aria-label={s.status}>
          {chip('', st, setSt, s.all)}{chip('active', st, setSt, s.st_active)}{chip('pamp_limited', st, setSt, s.st_pamp_limited)}{chip('panel_disabled', st, setSt, s.st_panel_disabled)}
        </div>
        <div className="ag-chips" role="group" aria-label={s.limit}>
          {chip('', lim, setLim, s.all)}{chip('limited', lim, setLim, s.limited)}{chip('unlimited', lim, setLim, s.unlimited)}
        </div>
        {d?.groups?.length > 0 && (
          <select className="ag-select" value={grp} onChange={(e) => setGrp(e.target.value)} aria-label={s.group}>
            <option value="">{s.any_group}</option>
            {d.groups.map((g) => <option key={g.id} value={g.id}>{g.owner}</option>)}
          </select>
        )}
        <div className="ag-toolbar-end">
          {d && <span className="ag-total" aria-live="polite">{s.n_admins.replace('{n}', digits(d.count, lang))}</span>}
          <div className="ag-seg" role="group" aria-label={s.density}>
            <button type="button" aria-pressed={density === 'comfortable'} title={s.comfortable} aria-label={s.comfortable} onClick={() => setDensity('comfortable')}><Icon name="rows" size={16} /></button>
            <button type="button" aria-pressed={density === 'compact'} title={s.compact} aria-label={s.compact} onClick={() => setDensity('compact')}><Icon name="rowsTight" size={16} /></button>
          </div>
        </div>
      </div>
      <Err>{err}</Err>
      {d === null ? <Skeleton rows={8} cols={7} /> : d && (
        rows.length === 0 ? (
          <Empty title={s.none} action={filtered && <Btn variant="tonal" onClick={() => { setQ(''); setSt(''); setLim(''); setGrp('') }}>{s.reset_filters}</Btn>} />
        ) : (
          <div className="ag-tablewrap ag-tablewrap--main">
            <table className={'ag-table ag-admins' + (density === 'compact' ? ' dense' : '')}>
              <thead>
                <tr>
                  <SortTh k="name" sort={sort} setSort={setSort}>{s.admins}</SortTh>
                  {COLS.map(([k, label, num]) => <SortTh key={k} k={k} sort={sort} setSort={setSort} num={num}>{s[label]}</SortTh>)}
                  {hasBal && <SortTh k="balance" sort={sort} setSort={setSort} num>{s.balance}</SortTh>}
                  <th className="ag-act-col"><span className="sr-only">{s.more}</span></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.username} onClick={(e) => { if (!e.target.closest('a,button')) nav(`/agency/admins/${enc(r.username)}`) }}>
                    <td className="ag-name">
                      <Link to={`/agency/admins/${enc(r.username)}`}>{r.username}</Link>
                      {r.groups.length > 0 && <span className="ag-grp">{r.groups.map((g) => g.owner).join('، ')}</span>}
                    </td>
                    <td className="c-status"><Status code={r.status_code} label={s['st_' + r.status_code]} /></td>
                    <td className="c-usage">{r.is_unlimited ? <span className="agk-muted">{s.unl}</span> : <Usage pct={r.usage_percent} />}</td>
                    <td className="num c-sold" data-label={s.total_sold}><Qty v={r.total_sold_fmt} /></td>
                    <td className="num c-sl"><Qty v={r.sold_limit_fmt} /></td>
                    <td className="num c-hid"><Qty v={r.hidden_fmt} /></td>
                    <td className="num c-rem" data-label={s.remaining}><Qty v={r.remaining_fmt} unl={s.unl} /></td>
                    <td className="num c-used"><Qty v={r.used_fmt} /></td>
                    <td className="num c-users" data-label={s.users_total}><N v={r.user_count} /></td>
                    <td className="num c-active"><N v={r.active_user_count} /></td>
                    {hasBal && <td className="num c-bal"><Money n={r.balance} lang={lang} signed /></td>}
                    <td className="ag-act-col">
                      <Menu label={`${s.more} — ${r.username}`} items={[
                        { label: s.open, icon: 'open', onClick: () => nav(`/agency/admins/${enc(r.username)}`) },
                        { label: s.a_copy_msg, icon: 'copy', onClick: () => copyMsg(r.username) },
                        hasBal ? { label: s.a_statement, icon: 'wallet', onClick: () => nav(`/agency/admins/${enc(r.username)}#accounting`) } : undefined,
                      ].filter((x) => x !== undefined)} />
                    </td>
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

// ───────────────────────────────────────────────────────────── admin detail
function SetLimitForm({ s, lang, username, box }) {
  const [mode, setMode] = useState('add')
  const [gb, setGb] = useState('')
  const [p, setP] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    box.ready = false
    const v = gb.replace(/[۰-۹]/g, (c) => '۰۱۲۳۴۵۶۷۸۹'.indexOf(c)).replace(/[٠-٩]/g, (c) => '٠١٢٣٤٥٦٧٨٩'.indexOf(c))
    if (!v) { setP(null); setErr(''); return }
    if (!/^\d+(\.\d+)?$/.test(v) || Number(v) <= 0) { setP(null); setErr(s.v_required); return }
    const h = setTimeout(() => {
      api.post(`/admin/agency/admins/${enc(username)}/set-limit/preview/`, { action: mode, value_gb: v })
        .then((r) => { setP(r.data); setErr(''); Object.assign(box, { mode, gb: v, ready: true }) })
        .catch((e) => { setP(null); setErr(apiError(e)) })
    }, 250)
    return () => clearTimeout(h)
  }, [mode, gb])
  return (
    <div className="ag-form">
      <div className="ag-seg ag-seg--text" role="radiogroup" aria-label={s.mode}>
        {['add', 'set', 'reduce'].map((m) => (
          <button key={m} type="button" role="radio" aria-checked={mode === m} onClick={() => setMode(m)}>{s['m_' + m]}</button>
        ))}
      </div>
      <label className="ag-field">
        <span>{s.gb}</span>
        <input dir="ltr" inputMode="decimal" value={gb} onChange={(e) => setGb(e.target.value.trim())} aria-invalid={!!err} aria-describedby="ag-limit-err" autoFocus />
        {err && <small id="ag-limit-err" className="ag-field-err">{err}</small>}
      </label>
      {p && (
        <dl className="ag-preview" aria-live="polite">
          <div><dt>{s.p_limit}</dt><dd><Qty v={p.old_limit_fmt} unl={s.unl} /> <span aria-hidden="true">{arrow(lang)}</span> <b><Qty v={p.new_limit_fmt} unl={s.unl} /></b></dd></div>
          <div><dt>{s.p_remaining}</dt><dd><Qty v={p.remaining_after_fmt} unl={s.unl} /></dd></div>
          <div><dt>{s.p_charge}</dt><dd>{!p.charge ? <span className="agk-muted">{s.p_no_charge}</span> : (
            <><bdi dir="ltr" className="agk-qty">{p.charge.gb}<span className="agk-unit"> GB</span></bdi> × {p.charge.price_per_gb != null ? <Money n={p.charge.price_per_gb} lang={lang} /> : '—'} = <b><Money n={p.charge.amount} lang={lang} /></b>
              {p.charge.price_per_gb == null && <small className="ag-field-err">{s.p_no_price}</small>}</>
          )}</dd></div>
        </dl>
      )}
    </div>
  )
}

function PortalLinkCard({ s, username }) {
  const toast = useToast()
  const [link] = useLoad('/admin/agency/portal-link/')
  const [qr, setQr] = useState(null)
  useEffect(() => () => { if (qr) URL.revokeObjectURL(qr) }, [qr])
  const msg = username ? s.msg_tpl.replace('{url}', link?.url || '').replace('{u}', username) : link?.url || ''
  const copy = async (text) => { (await copyToClipboard(text)) ? toast.success(s.copied) : toast.error('—') }
  const toggleQr = async () => {
    if (qr) { setQr(null); return }
    try { const r = await api.get('/admin/agency/portal-link/qr.png', { responseType: 'blob' }); setQr(URL.createObjectURL(r.data)) } catch (e) { toast.error(apiError(e)) }
  }
  return (
    <div className="ag-link">
      <div className="ag-link-main">
        <code dir="ltr" className="ag-link-url">{link?.url || '…'}</code>
        {username && <p className="ag-link-user">{s.user}: <N v={username} /></p>}
        {username && <p className="ag-hint">{s.send_hint}</p>}
        <div className="ag-link-acts">
          <Btn variant="tonal" icon="copy" onClick={() => copy(msg)} disabled={!link}>{username ? s.copy_msg : s.copy_link}</Btn>
          {username && <Btn variant="ghost" icon="link" onClick={() => copy(link.url)} disabled={!link}>{s.copy_link}</Btn>}
          <Btn variant="ghost" icon="qr" onClick={toggleQr} disabled={!link} aria-expanded={!!qr}>{qr ? s.hide_qr : s.show_qr}</Btn>
        </div>
      </div>
      {qr && <img className="ag-link-qr" src={qr} alt={`QR — ${link?.url}`} width="148" height="148" />}
    </div>
  )
}

export function AgencyAdminDetail() {
  const [s, lang] = useT()
  const { username } = useParams()
  const { can } = useAuth()
  const confirm = useConfirm()
  const toast = useToast()
  const [d, err, load] = useLoad(`/admin/agency/admins/${enc(username)}/`, [username])
  const [link] = useLoad('/admin/agency/portal-link/')
  const writable = d?.switches?.writes_enabled && can('agency.manage')
  useEffect(() => { if (d && window.location.hash === '#accounting') document.getElementById('accounting')?.scrollIntoView() }, [!!d])

  const run = async ({ title, tone = 'primary', path, body, rows, message, content }) => {
    await confirm({
      tone, title, targetLabel: s.admins, targetId: username, confirmLabel: s.confirm, message,
      details: rows ? { title: s.p_panel, rows } : undefined, content,
      action: async () => {
        const b = typeof body === 'function' ? body() : body
        if (b === false) throw new Error(s.v_required)
        const r = await api.post(`/admin/agency/admins/${enc(username)}/${path}/`, b)
        toast.success(r.data.message || s.done); load()
      },
    })
  }
  const setLimit = () => {
    const box = {}
    run({ title: s.a_set, path: 'set-limit', content: <SetLimitForm s={s} lang={lang} username={username} box={box} />,
      body: () => (box.ready ? { action: box.mode, value_gb: box.gb } : false) })
  }
  if (d === null) return <div className="ag"><Header s={s} /><Skeleton rows={6} cols={4} /></div>
  if (!d) return <div className="ag"><Header s={s} /><Err>{err}</Err></div>
  const p = d.portal
  const copyMsg = async () => { (await copyToClipboard(s.msg_tpl.replace('{url}', link?.url || '').replace('{u}', d.username))) ? toast.success(s.copied) : toast.error('—') }
  const disabled = !writable
  const hint = disabled ? s.cutover : undefined
  const menu = [
    { label: s.a_remove, icon: 'infinity', disabled, hint, onClick: () => run({ title: s.a_remove, tone: 'warning', path: 'remove-limit', body: {}, rows: [[s.p_limit, `${d.admin_limit_fmt === 'Unlimited' ? s.unl : d.admin_limit_fmt} ${arrow(lang)} ${s.unl}`]] }) },
    d.status === 'disabled'
      ? { label: s.a_enable, icon: 'power', disabled, hint, onClick: () => run({ title: s.a_enable, tone: 'success', path: 'admin-action', body: { action: 'enable_admin' }, message: s.d_enable }) }
      : { label: s.a_disable, icon: 'power', danger: true, disabled, hint, onClick: () => run({ title: s.a_disable, tone: 'danger', path: 'admin-action', body: { action: 'disable_admin' }, message: s.d_disable }) },
    { label: s.a_enable_users, icon: 'users', disabled, hint, onClick: () => run({ title: s.a_enable_users, tone: 'success', path: 'admin-action', body: { action: 'enable_users' }, message: s.d_enable_users }) },
    { label: s.a_disable_users, icon: 'users', danger: true, disabled, hint, onClick: () => run({ title: s.a_disable_users, tone: 'danger', path: 'admin-action', body: { action: 'disable_users' }, message: s.d_disable_users.replace('{n}', d.counts.total) }) },
    null,
    { label: s.a_reset, icon: 'reset', danger: true, disabled, hint, onClick: () => run({ title: s.a_reset, tone: 'danger', path: 'reset-deleted-traffic', body: {}, message: s.d_reset, rows: [[s.deleted, `${d.deleted_used_fmt} ${arrow(lang)} 0`]] }) },
    null,
    { label: s.a_copy_msg, icon: 'copy', onClick: copyMsg },
  ]
  const nums = [[s.total_sold, d.total_sold_fmt], [s.used, d.used_fmt], [s.remaining, d.remaining_fmt], [s.limit, d.admin_limit_fmt],
    [s.sold_limit, d.sold_limit_fmt], [s.hidden, d.hidden_fmt], [s.hidden_clamped, d.hidden_traffic_clamped_fmt], [s.deleted, d.deleted_used_fmt]]
  const [uo, rest] = s.used_of.split('{u}'); const [mid, end] = rest.split('{l}')
  return (
    <div className="ag">
      <Header s={s} switches={d.switches} />
      <Link to="/agency/admins" className="ag-back"><Icon name="chevron" size={15} />{s.back}</Link>
      <section className="ag-detail-h">
        <div className="ag-detail-id">
          <h2><bdi>{d.username}</bdi></h2>
          <Status code={d.status_code} label={s['st_' + d.status_code]} />
          {d.groups.map((g) => <span key={g.id} className="ag-grp">{g.owner}</span>)}
        </div>
        <div className="ag-detail-a">
          {can('agency.manage') && <Btn variant="primary" icon="gauge" onClick={setLimit} disabled={!writable} title={hint}>{s.a_set}</Btn>}
          <Menu label={s.more} items={menu} />
        </div>
      </section>
      {(p.is_blocked || p.show_warning) && (
        <p className="ag-flag" data-tone={p.is_blocked ? 'high' : 'mid'} role="status">
          {p.is_blocked ? (p.block_reason === 'disabled' ? s.blocked_panel : s.blocked_pamp) : s.warn80.replace('{p}', p.warning_pct)}
        </p>
      )}
      {!d.is_unlimited && (
        <div className="ag-usage-big">
          <Usage pct={d.usage_percent} />
          <span>{uo}<Qty v={d.used_fmt} />{mid}<Qty v={d.admin_limit_fmt} />{end}</span>
        </div>
      )}

      <section className="ag-sec">
        <div className="ag-sec-h"><h2>{s.sec_numbers}</h2></div>
        <dl className="ag-dl">
          {nums.map(([k, v]) => <div key={k}><dt>{k}</dt><dd><Qty v={v} unl={s.unl} /></dd></div>)}
        </dl>
      </section>

      <div className="ag-two">
        <section className="ag-sec">
          <div className="ag-sec-h"><h2>{s.sec_users}</h2></div>
          <dl className="ag-dl ag-dl--users">
            {['total', 'active', 'on_hold', 'limited', 'disabled', 'expired'].map((k) => (
              <div key={k}><dt>{s['c_' + k]}</dt><dd><N v={digits(d.counts[k], lang)} /></dd></div>
            ))}
          </dl>
        </section>
        <section className="ag-sec">
          <div className="ag-sec-h"><h2>{s.sec_send}</h2></div>
          <PortalLinkCard s={s} username={d.username} />
        </section>
      </div>

      {can('agency.accounting') && <div id="accounting"><LedgerCard username={d.username} /></div>}

      <section className="ag-sec">
        <div className="ag-sec-h"><h2>{s.sec_snap}</h2><span className="ag-count">{s.snap_n.replace('{n}', digits(d.snapshots.count, lang))}</span></div>
        {d.snapshots.rows.length === 0 ? <Empty title="—" /> : (
          <div className="ag-tablewrap ag-tablewrap--scroll">
            <table className="ag-table dense">
              <thead><tr><th>{s.user}</th><th className="num">{s.used}</th><th>{s.last_seen}</th></tr></thead>
              <tbody>{d.snapshots.rows.map((r) => (
                <tr key={r.user}><td><bdi>{r.user}</bdi></td><td className="num"><Qty v={r.used_fmt} /></td><td className="agk-muted">{jalali(r.last_seen, true, lang)}</td></tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </section>
      <section className="ag-sec">
        <div className="ag-sec-h"><h2>{s.sec_syncs}</h2></div>
        <SyncList rows={d.recent_syncs} s={s} lang={lang} />
      </section>
    </div>
  )
}

// ───────────────────────────────────────────────────────────── accounting overview
export function AgencyLedger() {
  const [s] = useT()
  const [dash] = useLoad('/admin/agency/')
  return <AgencyLedgerOverview Header={<Header s={s} switches={dash?.switches} />} />
}

// ───────────────────────────────────────────────────────────── groups
export function AgencyGroups() {
  const [s] = useT()
  const [d, err] = useLoad('/admin/agency/groups/')
  const [dash] = useLoad('/admin/agency/')
  return (
    <div className="ag">
      <Header s={s} switches={dash?.switches} />
      <Err>{err}</Err>
      {d === null ? <Skeleton rows={3} cols={3} /> : d && (
        d.results.length === 0 ? <Empty title={s.groups_none} /> : (
          <div className="ag-list">
            {d.results.map((g) => (
              <section key={g.id} className="ag-list-item">
                <div className="ag-list-h"><span className="agk-muted">{s.owner}</span> <Link to={`/agency/admins/${enc(g.owner)}`} className="ag-strong"><bdi>{g.owner}</bdi></Link>
                  <span className="ag-count">{g.members.length}</span></div>
                <div className="ag-members">
                  {g.members.map((m) => (
                    <Link key={m} to={`/agency/admins/${enc(m)}`} className="ag-member" data-missing={g.missing.includes(m) || undefined}>
                      <bdi>{m}</bdi>{g.missing.includes(m) && <em> · {s.missing}</em>}
                    </Link>
                  ))}
                </div>
                {g.note && <p className="ag-hint">{s.note}: {g.note}</p>}
              </section>
            ))}
          </div>
        )
      )}
    </div>
  )
}

// ───────────────────────────────────────────────────────────── sync logs
function SyncList({ rows, s, lang }) {
  if (!rows.length) return <Empty title={s.logs_none} />
  return (
    <ul className="ag-logs">
      {rows.map((l) => (
        <li key={l.id}>
          <Status code={logCode(l.status)} label={s['s_' + l.status] || l.status} />
          <span className="agk-muted">{jalali(l.created_at, true, lang)}</span>
          <span>{s.admins_synced.replace('{n}', digits(l.admins_synced, lang))}</span>
          <bdi dir="ltr" className="agk-qty agk-muted">{l.duration_seconds}s</bdi>
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
  const [busy, setBusy] = useState(false)
  const [dash] = useLoad('/admin/agency/')
  const load = (offset = 0) => { setBusy(true); return api.get(`/admin/agency/sync-logs/?limit=50&offset=${offset}${st ? '&status=' + st : ''}`)
    .then((r) => { setMeta(r.data); setRows((cur) => (offset ? [...(cur || []), ...r.data.results] : r.data.results)) })
    .catch((e) => { setErr(apiError(e)); setRows((c) => c || []) }).finally(() => setBusy(false)) }
  useEffect(() => { setRows(null); load(0) }, [st])
  return (
    <div className="ag">
      <Header s={s} switches={dash?.switches} />
      <div className="ag-chips" role="group" aria-label={s.status}>
        {[['', s.all], ['success', s.s_success], ['partial', s.s_partial], ['failed', s.s_failed]].map(([k, label]) => (
          <button key={k || 'all'} type="button" className={'ag-chip' + (st === k ? ' on' : '')} aria-pressed={st === k} onClick={() => setSt(k)}>
            {label}{meta && k && <bdi dir="ltr" className="ag-chip-n">{meta.summary[k]}</bdi>}
          </button>
        ))}
      </div>
      <Err>{err}</Err>
      {rows === null ? <Skeleton rows={6} cols={4} /> : (
        <section className="ag-sec">
          <SyncList rows={rows} s={s} lang={lang} />
          {meta?.next != null && <div className="ag-center"><Btn variant="ghost" loading={busy} onClick={() => load(meta.next)}>{s.load_more}</Btn></div>}
        </section>
      )}
    </div>
  )
}

// ───────────────────────────────────────────────────────────── settings
export function AgencySettings() {
  const [s] = useT()
  const { can } = useAuth()
  const confirm = useConfirm()
  const toast = useToast()
  const [d, err, load] = useLoad('/admin/agency/settings/')
  const [interval, setIntervalV] = useState('')
  const [ierr, setIerr] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { if (d) setIntervalV(String(d.sync_interval_minutes)) }, [d])
  const manage = can('agency.manage')
  const patch = async (body) => {
    try { await api.patch('/admin/agency/settings/', body); toast.success(s.saved); load() } catch (e) { toast.error(apiError(e)) }
  }
  const toggleSync = async (on) => {
    if (on) {
      await confirm({ tone: 'danger', title: s.cut_title, message: s.cut_msg, confirmLabel: s.confirm,
        reason: { label: s.cut_reason, required: true, placeholder: 'FINLAND-STOPPED' },
        action: async (typed) => { await api.patch('/admin/agency/settings/', { sync_enabled: true, confirm: typed }); toast.success(s.saved); load() } })
    } else if (await confirm({ tone: 'warning', title: s.sync_off_title, confirmLabel: s.confirm })) patch({ sync_enabled: false, enforcement_enabled: false })
  }
  const toggleEnf = async (on) => {
    if (!on) return patch({ enforcement_enabled: false })
    if (await confirm({ tone: 'warning', title: s.enf_title, message: s.set_enf_d, confirmLabel: s.confirm })) patch({ enforcement_enabled: true })
  }
  const saveInterval = async (e) => {
    e.preventDefault()
    const n = Number(interval)
    if (!Number.isInteger(n) || n < 1 || n > 1440) { setIerr(s.interval_err); return }
    setIerr(''); setBusy(true); await patch({ sync_interval_minutes: n }); setBusy(false)
  }
  return (
    <div className="ag">
      <Header s={s} switches={d || undefined} />
      <Err>{err}</Err>
      {d === null ? <Skeleton rows={4} cols={2} /> : d && (
        <>
          <section className="ag-sec">
            <div className="ag-sec-h"><h2>{s.sec_switches}</h2></div>
            <div className="ag-rows">
              {[[s.set_sync, s.set_sync_d, d.sync_enabled, toggleSync, false], [s.set_enf, s.set_enf_d, d.enforcement_enabled, toggleEnf, !d.sync_enabled],
                [s.set_portal, s.set_portal_d, !!d.portal_enabled, (v) => patch({ portal_enabled: v }), false]].map(([t, desc, val, fn, dis]) => (
                <div key={t} className="ag-row">
                  <div><b>{t}</b><p>{desc}</p></div>
                  <Toggle checked={val} disabled={!manage || dis} onChange={(v) => fn(v)} label={t} />
                </div>
              ))}
              <form className="ag-row" onSubmit={saveInterval} noValidate>
                <label htmlFor="ag-int"><b>{s.set_interval}</b></label>
                <div className="ag-int">
                  <input id="ag-int" dir="ltr" inputMode="numeric" value={interval} disabled={!manage}
                    onChange={(e) => setIntervalV(e.target.value)} aria-invalid={!!ierr} aria-describedby="ag-int-err" />
                  <span className="agk-muted">{s.minutes}</span>
                  <Btn variant="primary" type="submit" loading={busy} disabled={!manage}>{s.save}</Btn>
                </div>
                {ierr && <small id="ag-int-err" className="ag-field-err">{ierr}</small>}
              </form>
            </div>
          </section>
          <section className="ag-sec">
            <div className="ag-sec-h"><h2>{s.portal_link}</h2></div>
            <PortalLinkCard s={s} />
          </section>
        </>
      )}
    </div>
  )
}

const CSS = `
.ag { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.ag-head { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: 8px 16px; }
.ag-head h1 { font-size: 20px; font-weight: 800; letter-spacing: -.01em; }
.ag-head p { font-size: 13px; color: var(--c-muted-fg); margin-top: 2px; }
.ag-tabs { display: flex; gap: 4px; overflow-x: auto; scrollbar-width: none; border-bottom: 1px solid var(--c-border); margin-top: -4px; }
.ag-tabs::-webkit-scrollbar { display: none; }
.ag-tab { position: relative; padding: 10px 12px; font-size: 13.5px; font-weight: 650; color: var(--c-muted-fg); text-decoration: none; white-space: nowrap; border-radius: 8px 8px 0 0; }
.ag-tab:hover, .ag-tab.on { color: var(--c-text); }
.ag-tab:focus-visible { outline: 2px solid var(--c-primary); outline-offset: -2px; }
.ag-tab.on::after { content: ''; position: absolute; inset-inline: 10px; bottom: -1px; height: 2px; border-radius: 2px; background: var(--c-primary); }
.ag-note { font-size: 13px; padding: 10px 12px; border-radius: 10px; color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 10%, transparent); }
.ag-err { font-size: 13px; color: var(--c-danger-fg); }

.ag-stats { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); border: 1px solid var(--c-border); border-radius: 14px;
  background: linear-gradient(var(--c-surface), var(--c-surface)), var(--c-bg); }
.ag-stat { display: flex; flex-direction: column; gap: 4px; padding: 16px 18px; min-width: 0; }
.ag-stat + .ag-stat { border-inline-start: 1px solid var(--c-border); }
.ag-stat-k { font-size: 12.5px; color: var(--c-muted-fg); font-weight: 600; }
.ag-stat-v { font-size: 24px; font-weight: 750; line-height: 1.2; }
.ag-stat-s { display: flex; flex-wrap: wrap; gap: 4px 10px; margin-top: 2px; }
.ag-stat-s .agk-status { font-size: 12px; }

.ag-sec { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.ag-sec-h { display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; }
.ag-sec-h h2 { font-size: 15px; font-weight: 750; }
.ag-sec-h p { font-size: 12.5px; color: var(--c-muted-fg); margin-top: 2px; }
.ag-count { font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 700; padding: 2px 8px; border-radius: 999px;
  color: var(--c-muted-fg); background: color-mix(in srgb, var(--c-text) 7%, transparent); }
.ag-meta { font-size: 12.5px; color: var(--c-muted-fg); display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; }
.ag-center { display: flex; justify-content: center; padding-top: 8px; }
.ag-hint { font-size: 12.5px; color: var(--c-muted-fg); line-height: 1.7; }
.ag-strong { font-weight: 700; color: var(--c-text); text-decoration: none; }

.ag-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; }
.ag-toolbar-end { display: flex; align-items: center; gap: 10px; margin-inline-start: auto; }
.ag-search { display: flex; align-items: center; flex: 1 1 220px; max-width: 320px; height: 36px; gap: 6px; padding-inline: 10px;
  border: 1px solid var(--c-border); border-radius: 10px; background: var(--c-surface); color: var(--c-muted-fg); }
.ag-search:focus-within { border-color: var(--c-primary); box-shadow: 0 0 0 3px color-mix(in srgb, var(--c-primary) 18%, transparent); }
.ag-search input { flex: 1; min-width: 0; height: 100%; border: 0; background: transparent; color: var(--c-text); font: inherit; font-size: 13.5px; outline: none; }
.ag-search input::-webkit-search-cancel-button { -webkit-appearance: none; appearance: none; }
.ag-search-x { display: grid; place-items: center; width: 26px; height: 26px; border-radius: 6px; border: 0; background: none; color: var(--c-muted-fg); cursor: pointer; }
.ag-search-x:hover { background: color-mix(in srgb, var(--c-text) 7%, transparent); color: var(--c-text); }
.ag-chips, .ag-seg { display: inline-flex; padding: 3px; gap: 2px; border-radius: 10px; background: color-mix(in srgb, var(--c-text) 6%, transparent); }
.ag-chip { height: 30px; padding: 0 11px; border-radius: 8px; border: 0; background: transparent; color: var(--c-muted-fg);
  font: inherit; font-size: 12.5px; font-weight: 650; cursor: pointer; white-space: nowrap; display: inline-flex; align-items: center; gap: 6px; }
.ag-chip:hover { color: var(--c-text); }
.ag-chip.on, .ag-seg button[aria-pressed="true"], .ag-seg button[aria-checked="true"] {
  background: linear-gradient(var(--c-surface), var(--c-surface)), var(--c-bg); color: var(--c-text); box-shadow: 0 1px 2px rgb(0 0 0 / .1); }
.ag-chip:focus-visible, .ag-seg button:focus-visible { outline: 2px solid var(--c-primary); outline-offset: 1px; }
.ag-chip-n { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--c-muted-fg); }
.ag-select { height: 36px; border-radius: 10px; border: 1px solid var(--c-border); background: var(--c-surface); color: var(--c-text); padding: 0 10px; font: inherit; font-size: 13px; }
.ag-total { font-size: 12.5px; color: var(--c-muted-fg); white-space: nowrap; }
.ag-seg button { display: grid; place-items: center; min-width: 30px; height: 30px; padding: 0 10px; border: 0; border-radius: 8px; background: transparent;
  color: var(--c-muted-fg); cursor: pointer; font: inherit; font-size: 12.5px; font-weight: 650; }

.ag-tablewrap { border: 1px solid var(--c-border); border-radius: 14px; overflow: auto; background: linear-gradient(var(--c-surface), var(--c-surface)), var(--c-bg); }
.ag-tablewrap--main { max-height: calc(100vh - 230px); }
.ag-tablewrap--scroll { max-height: 380px; }
.ag-table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13.5px; }
.ag-table th { position: sticky; top: 0; z-index: 1; text-align: start; font-size: 12px; font-weight: 650; color: var(--c-muted-fg); padding: 10px 12px;
  background: linear-gradient(var(--c-surface), var(--c-surface)), var(--c-bg); border-bottom: 1px solid var(--c-border); white-space: nowrap; }
.ag-table td { padding: 12px 12px; border-bottom: 1px solid color-mix(in srgb, var(--c-border) 70%, transparent); white-space: nowrap; vertical-align: middle; }
.ag-table tbody tr:last-child td { border-bottom: 0; }
.ag-table.dense td { padding-block: 7px; } .ag-table.dense th { padding-block: 8px; }
.ag-table .num { text-align: end; }
.ag-admins tbody tr { cursor: pointer; }
.ag-admins tbody tr:hover td { background: color-mix(in srgb, var(--c-text) 3.5%, transparent); }
.ag-name a { font-weight: 700; color: var(--c-text); text-decoration: none; }
.ag-name a:hover { text-decoration: underline; text-underline-offset: 3px; }
.ag-name a:focus-visible { outline: 2px solid var(--c-primary); outline-offset: 2px; border-radius: 4px; }
.ag-grp { display: inline-block; margin-inline-start: 8px; font-size: 11.5px; font-weight: 600; color: var(--c-muted-fg); }
.ag-act-col { width: 44px; text-align: end; padding-inline: 6px !important; }
.ag-table .c-usage { min-width: 132px; }
.ag-admins .agk-usage { min-width: 112px; }
@media (max-width: 1500px) { .ag-admins th, .ag-admins td { padding-inline: 9px; } }
@media (max-width: 1600px) { .ag-admins th:nth-child(6), .ag-admins td.c-hid { display: none; } }

.ag-back { display: inline-flex; align-items: center; gap: 4px; font-size: 13px; font-weight: 600; color: var(--c-muted-fg); text-decoration: none; margin-bottom: -6px; align-self: flex-start; }
.ag-back:hover { color: var(--c-text); }
[dir="ltr"] .ag-back svg { transform: rotate(180deg); }
.ag-detail-h { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px 16px; }
.ag-detail-id { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; min-width: 0; }
.ag-detail-id h2 { font-size: 22px; font-weight: 800; overflow-wrap: anywhere; }
.ag-detail-a { display: flex; align-items: center; gap: 6px; }
.ag-flag { font-size: 13px; font-weight: 600; padding: 9px 12px; border-radius: 10px; color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 10%, transparent); }
.ag-flag[data-tone="high"] { color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 9%, transparent); }
.ag-usage-big { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 16px; font-size: 13px; color: var(--c-muted-fg); }
.ag-usage-big .agk-usage { flex: 1 1 320px; }

.ag-dl { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border-top: 1px solid var(--c-border); }
.ag-dl > div { padding: 12px 16px; border-bottom: 1px solid var(--c-border); border-inline-start: 1px solid var(--c-border); min-width: 0; }
.ag-dl > div:nth-child(4n+1) { padding-inline-start: 2px; border-inline-start: 0; }
.ag-dl dt { font-size: 12px; color: var(--c-muted-fg); font-weight: 600; }
.ag-dl dd { font-size: 17px; font-weight: 700; margin-top: 3px; }
.ag-dl--users { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.ag-dl--users > div:nth-child(n) { padding-inline-start: 16px; border-inline-start: 1px solid var(--c-border); }
.ag-dl--users > div:nth-child(3n+1) { padding-inline-start: 2px; border-inline-start: 0; }
.ag-two { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 24px; }

.ag-link { display: flex; gap: 16px; align-items: flex-start; }
.ag-link-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.ag-link-url { font-family: 'JetBrains Mono', monospace; font-size: 13.5px; font-weight: 600; padding: 9px 12px; border-radius: 10px;
  background: color-mix(in srgb, var(--c-text) 6%, transparent); overflow-wrap: anywhere; }
.ag-link-user { font-size: 13px; }
.ag-link-acts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
.ag-link-qr { border-radius: 10px; background: #fff; padding: 6px; border: 1px solid var(--c-border); }

.ag-form { display: flex; flex-direction: column; gap: 12px; margin-top: 8px; text-align: start; }
.ag-seg--text { align-self: flex-start; }
.ag-field { display: flex; flex-direction: column; gap: 5px; font-size: 12.5px; font-weight: 650; }
.ag-field input { height: 40px; border-radius: 10px; border: 1px solid var(--c-border); background: var(--c-surface); color: var(--c-text);
  padding: 0 12px; font-family: 'JetBrains Mono', monospace; font-size: 15px; outline: none; }
.ag-field input:focus { border-color: var(--c-primary); box-shadow: 0 0 0 3px color-mix(in srgb, var(--c-primary) 18%, transparent); }
.ag-field input[aria-invalid="true"] { border-color: var(--c-danger); }
.ag-field-err { display: block; font-size: 12px; font-weight: 600; color: var(--c-danger-fg); }
.ag-preview { display: flex; flex-direction: column; border-top: 1px solid var(--c-border); }
.ag-preview > div { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 4px 12px; padding: 8px 0; border-bottom: 1px solid var(--c-border); font-size: 13px; }
.ag-preview dt { color: var(--c-muted-fg); }

.ag-list, .ag-logs, .ag-rows { display: flex; flex-direction: column; border-top: 1px solid var(--c-border); }
.ag-list-item { padding: 14px 2px; border-bottom: 1px solid var(--c-border); display: flex; flex-direction: column; gap: 8px; }
.ag-list-h { display: flex; align-items: center; gap: 8px; font-size: 14px; }
.ag-members { display: flex; flex-wrap: wrap; gap: 6px; }
.ag-member { font-size: 12.5px; font-weight: 600; padding: 3px 9px; border-radius: 7px; color: var(--c-text); text-decoration: none; background: color-mix(in srgb, var(--c-text) 6%, transparent); }
.ag-member[data-missing] { color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 8%, transparent); }
.ag-logs li { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 14px; padding: 10px 2px; border-bottom: 1px solid var(--c-border); font-size: 13px; }
.ag-log-err { flex-basis: 100%; white-space: pre-wrap; font-size: 12px; color: var(--c-danger-fg); margin: 0; }
.ag-row { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 24px; padding: 14px 2px; border-bottom: 1px solid var(--c-border); }
.ag-row p { font-size: 12.5px; color: var(--c-muted-fg); margin-top: 2px; line-height: 1.7; max-width: 62ch; }
.ag-int { display: flex; align-items: center; gap: 8px; }
.ag-int input { width: 84px; height: 36px; border-radius: 10px; border: 1px solid var(--c-border); background: var(--c-surface); color: var(--c-text); padding: 0 10px; font-family: 'JetBrains Mono', monospace; }
.ag-int input:focus { outline: none; border-color: var(--c-primary); box-shadow: 0 0 0 3px color-mix(in srgb, var(--c-primary) 18%, transparent); }

@media (max-width: 1100px) {
  .ag-stats { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .ag-stat:nth-child(4) { border-inline-start: 0; } .ag-stat:nth-child(n+4) { border-top: 1px solid var(--c-border); }
  .ag-two { grid-template-columns: minmax(0, 1fr); }
  .ag-dl { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .ag-dl > div:nth-child(n) { padding-inline-start: 16px; border-inline-start: 1px solid var(--c-border); }
  .ag-dl > div:nth-child(2n+1) { padding-inline-start: 2px; border-inline-start: 0; }
}
@media (max-width: 767px) {
  .ag { gap: 14px; }
  .ag-head p { display: none; }
  .ag-tab { padding: 12px 10px; }
  .ag-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .ag-stat { padding: 12px 14px; } .ag-stat-v { font-size: 19px; }
  .ag-stat:nth-child(n) { border-inline-start: 1px solid var(--c-border); border-top: 1px solid var(--c-border); }
  .ag-stat:nth-child(2n+1) { border-inline-start: 0; } .ag-stat:nth-child(-n+2) { border-top: 0; }
  .ag-stat:last-child { grid-column: 1 / -1; border-inline-start: 0; }
  .ag-search { max-width: none; flex-basis: 100%; height: 44px; } .ag-search input { font-size: 16px; }
  .ag-chips { overflow-x: auto; max-width: 100%; } .ag-chip { height: 38px; }
  .ag-select { height: 44px; font-size: 16px; }
  .ag-toolbar-end { margin-inline-start: 0; width: 100%; justify-content: space-between; }
  .ag-toolbar-end .ag-seg { display: none; }
  .ag-tablewrap--main { max-height: none; overflow: visible; }
  /* phones: compact rows — name, usage, 2-3 key numbers; tap = details */
  .ag-admins thead, .ag-near thead { display: none; }
  .ag-admins, .ag-admins tbody, .ag-near, .ag-near tbody { display: block; }
  .ag-admins tr, .ag-near tr { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)) auto; gap: 6px 10px;
    padding: 12px 14px; border-bottom: 1px solid color-mix(in srgb, var(--c-border) 70%, transparent); }
  .ag-admins td, .ag-near td { padding: 0; border: 0; min-width: 0; text-align: start !important; }
  .ag-admins td.ag-name, .ag-near td.ag-name { grid-column: 1 / 4; display: flex; flex-wrap: wrap; align-items: center; gap: 2px 8px; white-space: normal; }
  .ag-admins td.c-status { display: none; }
  .ag-admins td.ag-act-col { grid-column: 4; grid-row: 1; width: auto; }
  .ag-near td.c-status { grid-column: 4; grid-row: 1; }
  .ag-admins td.c-usage, .ag-near td.c-usage { grid-column: 1 / -1; min-width: 0; }
  .ag-admins td.c-usage .agk-usage, .ag-near td.c-usage .agk-usage { display: flex; width: 100%; } .c-usage .agk-usage-track { flex: 1; width: auto; }
  .ag-admins td[data-label]::before, .ag-near td[data-label]::before { content: attr(data-label); display: block; font-size: 11px; color: var(--c-muted-fg); font-weight: 600; }
  .ag-admins td.c-sl, .ag-admins td.c-hid, .ag-admins td.c-used, .ag-admins td.c-active, .ag-admins td.c-bal { display: none; }
  .ag-dl dd { font-size: 15px; }
  .ag-link { flex-direction: column; } .ag-link-acts .agk-btn { flex: 1 1 auto; }
  .ag-field input, .ag-int input { height: 44px; font-size: 16px; }
  .ag-detail-id h2 { font-size: 19px; }
}
`
