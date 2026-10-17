import { useEffect, useMemo, useState } from 'react'
import { Link, NavLink, useParams } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useAuth } from '../lib/auth'
import { jalali, digits } from '../lib/format'
import { Alert, Spinner, Toggle } from '../components/ui'
import { copyToClipboard } from '../lib/clipboard'
import { useConfirm } from '../components/ConfirmDialog'
import { AgencyLedgerOverview, BalanceText, LedgerCard, LT } from './AgencyLedger'

// Agency panel (PAMP port). Every number on these pages comes from the backend
// (apps/agency: PAMP's own formulas); this file only formats and lays out.

const T = {
  fa: {
    title: 'پنل نمایندگی', sub: 'ادمین‌های نماینده روی پنل پاسارگاد — محاسبات عیناً مانند PAMP',
    tab_dash: 'داشبورد', tab_admins: 'نماینده‌ها', tab_groups: 'گروه‌ها', tab_logs: 'لاگ همگام‌سازی', tab_settings: 'تنظیمات',
    cutover: 'فعال پس از انتقال نهایی',
    cutover_note: 'PAMP فنلاند هنوز نسخهٔ اصلی است؛ این بخش فعلاً فقط‌خواندنی است و هیچ تغییری روی پنل اعمال نمی‌شود. داده‌ها از آخرین درون‌ریزی هستند.',
    balance: 'بدهی', portal_set: 'پرتال نماینده‌ها', portal_set_d: 'نماینده‌ها با نام کاربری و رمز پنل پاسارگاد خود در /agency/ وارد می‌شوند و فقط اعداد خودشان را می‌بینند. تا انتقال نهایی، اعداد از آخرین درون‌ریزی است.',
    total_sold: 'حجم فروخته‌شده', used: 'مصرف‌شده', remaining: 'باقی‌مانده', hidden: 'ترافیک پنهان', admins: 'نماینده‌ها',
    sold_limit: 'Sold Limit', limit: 'سقف ادمین', usage: 'مصرف', users: 'کاربران', status: 'وضعیت', group: 'گروه',
    over_title: 'نزدیک یا بیش از سقف (≥80%)', over_none: 'هیچ نماینده‌ای به 80% سقف نرسیده است.',
    st_active: 'فعال', st_panel_disabled: 'غیرفعال (پنل)', st_pamp_limited: 'محدود‌شده', at_risk: 'در خطر', over: 'بیش از سقف',
    last_sync: 'آخرین همگام‌سازی', never: 'هرگز', active_n: 'فعال', disabled_n: 'غیرفعال', limited_n: 'محدود', near_n: 'نزدیک سقف',
    search: 'جستجوی نام نماینده…', clear: 'پاک کردن جستجو', all: 'همه', f_status: 'وضعیت', f_limit: 'سقف', limited: 'سقف‌دار', unlimited: 'نامحدود',
    any_group: 'همهٔ گروه‌ها', n_admins: '{n} نماینده', none: 'نماینده‌ای پیدا نشد.', back: 'بازگشت به فهرست', unl: 'نامحدود',
    detail_numbers: 'اعداد PAMP', deleted: 'از کاربران حذف‌شده', hidden_clamped: 'پنهان (حداقل صفر)', counts: 'کاربران بر اساس وضعیت',
    c_active: 'فعال', c_on_hold: 'در انتظار', c_limited: 'اتمام حجم', c_disabled: 'غیرفعال', c_expired: 'منقضی', c_total: 'کل',
    warn80: 'به {p}% سقف رسیده است', blocked_pamp: 'توسط PAMP محدود شده', blocked_panel: 'روی پنل غیرفعال است',
    actions: 'عملیات', a_set: 'تنظیم سقف', a_remove: 'حذف سقف (نامحدود)', a_disable: 'غیرفعال کردن ادمین', a_enable: 'فعال کردن ادمین',
    a_disable_users: 'غیرفعال کردن همهٔ کاربرانش', a_enable_users: 'فعال کردن همهٔ کاربرانش', a_reset: 'صفر کردن ترافیک کاربران حذف‌شده',
    gb: 'گیگابایت', mode: 'نوع', m_set: 'تنظیم روی', m_add: 'افزودن', m_reduce: 'کاهش', confirm_go: 'تأیید',
    snapshots: 'آخرین مصرف کاربران (اسنپ‌شات)', snap_n: '{n} کاربر', user: 'کاربر', last_seen: 'آخرین بررسی', recent_syncs: 'همگام‌سازی‌های اخیر',
    support: 'پشتیبانی', groups_none: 'گروهی تعریف نشده است.', owner: 'مالک', members: 'اعضا', note: 'یادداشت', missing: 'روی پنل نیست',
    logs_none: 'لاگی ثبت نشده است.', s_success: 'موفق', s_partial: 'ناقص', s_failed: 'ناموفق', synced: 'ادمین', duration: 'مدت', error: 'خطا', more: 'بیشتر',
    set_sync: 'همگام‌سازی خودکار', set_sync_d: 'هر چند دقیقه اعداد را از پنل می‌گیرد. روشن کردن آن یعنی انتقال نهایی — اول همگام‌سازی PAMP فنلاند را متوقف کنید.',
    set_enf: 'اعمال سقف خودکار', set_enf_d: 'ادمینی که به 100% سقف برسد روی پنل غیرفعال و پس از افزایش سقف دوباره فعال می‌شود. فقط وقتی همگام‌سازی روشن است.',
    set_interval: 'فاصلهٔ همگام‌سازی (دقیقه)', save: 'ذخیره', saved: 'ذخیره شد',
    cut_title: 'روشن کردن همگام‌سازی = انتقال نهایی', cut_msg: 'از این لحظه این سرور اعداد را از پنل می‌گیرد و عملیات‌ها فعال می‌شوند. دو همگام‌سازی هم‌زمان روی یک پنل اعداد را خراب می‌کند.',
    cut_reason: 'برای تأیید بنویسید: FINLAND-STOPPED', sync_off_title: 'خاموش کردن همگام‌سازی؟', enf_title: 'اعمال خودکار سقف روشن شود؟',
    users_col: 'کاربران', users_on: 'فعال', users_sec: 'کاربران', sort_by: 'مرتب‌سازی بر اساس {c}',
    portal_link: 'لینک پرتال نماینده‌ها', send_to: 'ارسال به نماینده', copy_link: 'کپی لینک', copy_msg: 'کپی پیام', show_qr: 'نمایش QR', hide_qr: 'بستن QR', copied: 'کپی شد', copy_fail: 'کپی نشد',
    send_hint: 'این پیام را برای نماینده بفرستید؛ با نام کاربری و رمز پنل خودش وارد می‌شود.',
    msg_tpl: 'پرتال نمایندگی:\n{url}\nنام کاربری: {u}\nرمز عبور: همان رمز پنل پاسارگاد شما',
  },
  en: {
    title: 'Agency Panel', sub: 'Reseller admins on the PasarGuard panel — calculated exactly like PAMP',
    tab_dash: 'Dashboard', tab_admins: 'Admins', tab_groups: 'Groups', tab_logs: 'Sync logs', tab_settings: 'Settings',
    cutover: 'Available after the final cut-over',
    cutover_note: 'The Finland PAMP is still the live instance; this section is read-only for now and changes nothing on the panel. Data is from the last import.',
    balance: 'Balance', portal_set: 'Reseller portal', portal_set_d: 'Resellers sign in at /agency/ with their PasarGuard admin username and password and see only their own numbers. Until the cut-over the numbers are from the last import.',
    total_sold: 'Total Sold', used: 'Used', remaining: 'Remaining', hidden: 'Hidden traffic', admins: 'Admins',
    sold_limit: 'Sold Limit', limit: 'Admin limit', usage: 'Usage', users: 'Users', status: 'Status', group: 'Group',
    over_title: 'At or over the limit (≥80%)', over_none: 'No admin has reached 80% of their limit.',
    st_active: 'Active', st_panel_disabled: 'Disabled (panel)', st_pamp_limited: 'Limited', at_risk: 'At risk', over: 'Over limit',
    last_sync: 'Last sync', never: 'never', active_n: 'active', disabled_n: 'disabled', limited_n: 'limited', near_n: 'near limit',
    search: 'Search admin name…', clear: 'Clear search', all: 'All', f_status: 'Status', f_limit: 'Limit', limited: 'Limited', unlimited: 'Unlimited',
    any_group: 'All groups', n_admins: '{n} admins', none: 'No admin found.', back: 'Back to the list', unl: 'Unlimited',
    detail_numbers: 'PAMP numbers', deleted: 'From deleted users', hidden_clamped: 'Hidden (min 0)', counts: 'Users by status',
    c_active: 'Active', c_on_hold: 'On hold', c_limited: 'Data used up', c_disabled: 'Disabled', c_expired: 'Expired', c_total: 'Total',
    warn80: 'reached {p}% of the limit', blocked_pamp: 'Limited by PAMP', blocked_panel: 'Disabled on the panel',
    actions: 'Actions', a_set: 'Set limit', a_remove: 'Remove limit (unlimited)', a_disable: 'Disable admin', a_enable: 'Enable admin',
    a_disable_users: 'Disable all their users', a_enable_users: 'Enable all their users', a_reset: 'Reset deleted-users traffic',
    gb: 'GB', mode: 'Mode', m_set: 'Set to', m_add: 'Add', m_reduce: 'Reduce', confirm_go: 'Confirm',
    snapshots: 'Last known user usage (snapshot)', snap_n: '{n} users', user: 'User', last_seen: 'Last seen', recent_syncs: 'Recent syncs',
    support: 'Support', groups_none: 'No groups defined.', owner: 'Owner', members: 'Members', note: 'Note', missing: 'not on the panel',
    logs_none: 'No sync logged yet.', s_success: 'Success', s_partial: 'Partial', s_failed: 'Failed', synced: 'admins', duration: 'Duration', error: 'Error', more: 'Load more',
    set_sync: 'Automatic sync', set_sync_d: 'Pulls the numbers from the panel every few minutes. Turning it on IS the final cut-over — stop the Finland PAMP sync first.',
    set_enf: 'Automatic limit enforcement', set_enf_d: 'An admin at 100% of their limit is disabled on the panel and re-enabled once the limit is raised. Only while sync is on.',
    set_interval: 'Sync interval (minutes)', save: 'Save', saved: 'Saved',
    cut_title: 'Turning sync on = the final cut-over', cut_msg: 'From now on this server pulls the numbers from the panel and actions are enabled. Two syncs against one panel corrupt the numbers.',
    cut_reason: 'Type FINLAND-STOPPED to confirm', sync_off_title: 'Turn the sync off?', enf_title: 'Turn on automatic enforcement?',
    users_col: 'Users', users_on: 'on', users_sec: 'Users', sort_by: 'Sort by {c}',
    portal_link: 'Reseller portal link', send_to: 'Send to reseller', copy_link: 'Copy link', copy_msg: 'Copy message', show_qr: 'Show QR', hide_qr: 'Hide QR', copied: 'Copied', copy_fail: 'Could not copy',
    send_hint: 'Send this to the reseller; they sign in with their own panel username and password.',
    msg_tpl: 'Reseller portal:\n{url}\nUsername: {u}\nPassword: your PasarGuard panel password',
  },
}

const useT = () => { const { lang } = useI18n(); return [T[lang] || T.fa, lang] }
// backend strings are PAMP's ("1.23 TB", "Unlimited") — only translate the word
const fmt = (v, s) => (v === 'Unlimited' ? s.unl : v)
const B = ({ children }) => <bdi dir="ltr" className="ag-num">{children}</bdi>

function Header({ s, switches }) {
  const { can } = useAuth()
  const { lang } = useI18n()
  const tabs = [['/agency', s.tab_dash, true], ['/agency/admins', s.tab_admins], ['/agency/groups', s.tab_groups],
    ...(can('agency.accounting') ? [['/agency/ledger', (LT[lang] || LT.fa).tab]] : []),
    ['/agency/sync-logs', s.tab_logs], ['/agency/settings', s.tab_settings]]
  return (
    <>
      <style>{CSS}</style>
      <div className="ag-head">
        <h1 className="text-lg font-bold">{s.title}</h1>
        <p className="text-sm text-muted mt-1">{s.sub}</p>
      </div>
      <nav className="ag-tabs" aria-label={s.title}>
        {tabs.map(([to, label, end]) => (
          <NavLink key={to} to={to} end={!!end} className={({ isActive }) => 'ag-tab' + (isActive ? ' on' : '')}>{label}</NavLink>
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
            <Kpi label={s.total_sold} value={d.total_sold_fmt} tone="#1464BA" />
            <Kpi label={s.used} value={d.total_used_fmt} tone="#7C3AED" />
            <Kpi label={s.remaining} value={d.total_remaining_fmt} tone="#11AB53" />
            <Kpi label={s.hidden} value={d.total_hidden_fmt} tone="#D97706" />
            <Kpi label={s.admins} value={digits(d.admin_count, lang)} tone="#0891B2"
              sub={`${digits(d.active_count, lang)} ${s.active_n} · ${digits(d.disabled_count, lang)} ${s.disabled_n} · ${digits(d.pamp_limited_count, lang)} ${s.limited_n}`} />
          </div>
          <div className="card ag-card">
            <div className="ag-card-h">
              <h3>{s.over_title}</h3>
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
                    <span className="ag-over-sub"><B>{o.used_fmt}</B> / <B>{o.limit_fmt}</B></span>
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

function Kpi({ label, value, tone, sub }) {
  return (
    <div className="card ag-kpi" style={{ '--tone': tone }}>
      <span className="ag-kpi-l">{label}</span>
      <span className="ag-kpi-val"><B>{value}</B></span>
      {sub && <span className="ag-kpi-sub">{sub}</span>}
    </div>
  )
}

// ------------------------------------------------------------------ admins list
export function AgencyAdmins() {
  const [s, lang] = useT()
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
        <button type="button" className="ag-sort" onClick={() => setSort({ k, dir: on ? -sort.dir : -1 })} title={s.sort_by.replace('{c}', label)}>
          {label}<span aria-hidden="true">{on ? (sort.dir === 1 ? ' ▲' : ' ▼') : ' ↕'}</span>
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
                  <th>{s.admins}</th><th>{s.status}</th><th>{s.usage}</th><th>{s.total_sold}</th><th>{s.sold_limit}</th>
                  <th className="ag-c-hid">{s.hidden}</th><th>{s.remaining}</th><th>{s.used}</th>{sortTh('user_count', s.users_col)}{d.results[0]?.balance !== undefined && <th>{s.balance}</th>}
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
                      {r.is_unlimited ? <span className="text-muted">{s.unl}</span> : <><UsageBar pct={r.usage_percent} /><B>{r.usage_percent}%</B></>}
                    </td>
                    <td data-label={s.total_sold}><B>{r.total_sold_fmt}</B></td>
                    <td data-label={s.sold_limit}><B><span data-sign={r.sold_limit_value > 0 ? 'pos' : r.sold_limit_value < 0 ? 'neg' : 'zero'} className="ag-sign">{r.sold_limit_fmt}</span></B></td>
                    <td className="ag-c-hid" data-label={s.hidden}><B>{r.hidden_fmt}</B></td>
                    <td data-label={s.remaining}><B>{fmt(r.remaining_fmt, s)}</B></td>
                    <td data-label={s.used}><B>{r.used_fmt}</B></td>
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
export function AgencyAdminDetail() {
  const [s, lang] = useT()
  const { username } = useParams()
  const { can } = useAuth()
  const confirm = useConfirm()
  const [d, err, load] = useLoad(`/admin/agency/admins/${encodeURIComponent(username)}/`, [username])
  const [msg, setMsg] = useState('')
  const writable = d?.switches?.writes_enabled && can('agency.manage')

  const act = async (title, path, body, tone = 'warning', content) => {
    setMsg('')
    const ok = await confirm({
      tone, title, targetLabel: username, confirmLabel: s.confirm_go, content,
      action: async () => {
        const b = typeof body === 'function' ? body() : body
        const r = await api.post(`/admin/agency/admins/${encodeURIComponent(username)}/${path}/`, b)
        setMsg(r.data.message)
      },
    })
    if (ok) load()
  }
  const setLimit = () => {
    const box = { mode: 'set', gb: '' }
    act(s.a_set, 'set-limit', () => ({ action: box.mode, value_gb: box.gb }), 'primary', <SetLimitForm s={s} box={box} />)
  }

  if (d === null) return <div className="ag"><Header s={s} /><div className="grid place-items-center py-16"><Spinner /></div></div>
  if (!d) return <div className="ag space-y-4"><Header s={s} /><Alert>{err}</Alert></div>
  const p = d.portal
  const nums = [
    [s.limit, fmt(d.admin_limit_fmt, s)], [s.total_sold, d.total_sold_fmt], [s.used, d.used_fmt],
    [s.remaining, fmt(d.remaining_fmt, s)], [s.sold_limit, d.sold_limit_fmt], [s.hidden, d.hidden_fmt],
    [s.hidden_clamped, d.hidden_traffic_clamped_fmt], [s.deleted, d.deleted_used_fmt], [s.usage, `${d.usage_percent}%`],
  ]
  const ACTIONS = [
    [s.a_set, setLimit, 'primary'],
    [s.a_remove, () => act(s.a_remove, 'remove-limit', {}, 'warning')],
    d.status === 'disabled'
      ? [s.a_enable, () => act(s.a_enable, 'admin-action', { action: 'enable_admin' }, 'success')]
      : [s.a_disable, () => act(s.a_disable, 'admin-action', { action: 'disable_admin' }, 'danger')],
    [s.a_disable_users, () => act(s.a_disable_users, 'admin-action', { action: 'disable_users' }, 'danger')],
    [s.a_enable_users, () => act(s.a_enable_users, 'admin-action', { action: 'enable_users' }, 'success')],
    [s.a_reset, () => act(s.a_reset, 'reset-deleted-traffic', {}, 'danger')],
  ]
  return (
    <div className="ag space-y-4">
      <Header s={s} switches={d.switches} />
      <Link to="/agency/admins" className="ag-back">← {s.back}</Link>
      <div className="card ag-card">
        <div className="ag-detail-h">
          <h2 className="font-bold text-base"><bdi>{d.username}</bdi></h2>
          <StatusPill code={d.status_code} s={s} />
          {d.groups.map((g) => <span key={g.id} className="ag-t-grp">{g.owner}</span>)}
        </div>
        {!d.is_unlimited && <div className="ag-detail-bar"><UsageBar pct={d.usage_percent} /><B>{d.usage_percent}%</B></div>}
        {p.show_warning && <Alert kind="warning">{s.warn80.replace('{p}', p.warning_pct)}</Alert>}
        {p.is_blocked && <Alert>{p.block_reason === 'disabled' ? s.blocked_panel : s.blocked_pamp}</Alert>}
        <h3 className="ag-sec-h">{s.detail_numbers}</h3>
        <dl className="ag-nums">
          {nums.map(([k, v]) => <div key={k}><dt>{k}</dt><dd><B>{v}</B></dd></div>)}
        </dl>
        <h3 className="ag-sec-h">{s.users_sec}</h3>
        <dl className="ag-nums ag-nums--counts">
          {['total', 'active', 'on_hold', 'limited', 'disabled', 'expired'].map((k) => (
            <div key={k}><dt>{s['c_' + k]}</dt><dd><B>{digits(d.counts[k], lang)}</B></dd></div>
          ))}
        </dl>
        <p className="text-xs text-muted mt-2">{s.support}: <bdi dir="ltr">{p.support_telegram}</bdi> · {s.last_sync}: {d.last_synced_at ? jalali(d.last_synced_at, true, lang) : s.never}</p>
      </div>

      <PortalLinkCard s={s} username={d.username} />

      <div className="card ag-card">
        <h3 className="ag-sec-h" style={{ marginTop: 0 }}>{s.actions}</h3>
        {!writable && <p className="ag-locked">{s.cutover}</p>}
        {msg && <Alert kind="success">{msg}</Alert>}
        <div className="ag-actions">
          {ACTIONS.map(([label, fn, tone]) => (
            <button key={label} type="button" className={'ag-act' + (tone === 'danger' ? ' danger' : '')} disabled={!writable}
              onClick={fn} title={!writable ? s.cutover : undefined}>{label}</button>
          ))}
        </div>
      </div>

      {can('agency.accounting') && <LedgerCard username={d.username} />}

      <div className="card ag-card">
        <div className="ag-card-h"><h3>{s.snapshots}</h3><span className="ag-count">{s.snap_n.replace('{n}', digits(d.snapshots.count, lang))}</span></div>
        <div className="ag-table-wrap ag-snap">
          <table className="ag-table ag-table--plain">
            <thead><tr><th>{s.user}</th><th>{s.used}</th><th>{s.last_seen}</th></tr></thead>
            <tbody>{d.snapshots.rows.map((r) => (
              <tr key={r.user}><td data-label={s.user}><bdi>{r.user}</bdi></td><td data-label={s.used}><B>{r.used_fmt}</B></td><td data-label={s.last_seen}>{jalali(r.last_seen, true, lang)}</td></tr>
            ))}</tbody>
          </table>
        </div>
      </div>
      <div className="card ag-card">
        <h3 className="ag-sec-h" style={{ marginTop: 0 }}>{s.recent_syncs}</h3>
        <SyncRows rows={d.recent_syncs} s={s} lang={lang} />
      </div>
    </div>
  )
}

function SetLimitForm({ s, box }) {
  const [mode, setMode] = useState(box.mode)
  const [gb, setGb] = useState('')
  return (
    <div className="ag-form">
      <label><span>{s.mode}</span>
        <select className="input" value={mode} onChange={(e) => { setMode(e.target.value); box.mode = e.target.value }}>
          <option value="set">{s.m_set}</option><option value="add">{s.m_add}</option><option value="reduce">{s.m_reduce}</option>
        </select>
      </label>
      <label><span>{s.gb}</span>
        <input className="input" dir="ltr" inputMode="decimal" value={gb} onChange={(e) => { setGb(e.target.value); box.gb = e.target.value }} />
      </label>
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
      <h3 className="ag-sec-h" style={{ marginTop: 0 }}>{username ? s.send_to : s.portal_link}</h3>
      <div className="ag-portal">
        <div className="ag-portal-main">
          <code dir="ltr" className="ag-portal-url">{url || '…'}</code>
          {username && <p className="text-xs text-muted mt-2">{s.user}: <bdi dir="ltr">{username}</bdi> · {s.send_hint}</p>}
          <div className="ag-actions mt-2">
            {username && <button type="button" className="ag-act" disabled={!link} onClick={() => copy(s.msg_tpl.replace('{url}', url).replace('{u}', username))}>{s.copy_msg}</button>}
            <button type="button" className="ag-act" disabled={!link} onClick={() => copy(url)}>{s.copy_link}</button>
            <button type="button" className="ag-act" disabled={!link} onClick={toggleQr} aria-expanded={!!qr}>{qr ? s.hide_qr : s.show_qr}</button>
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
  return <AgencyLedgerOverview Header={<Header s={s} switches={dash?.switches} />} />
}

// ------------------------------------------------------------------ groups
export function AgencyGroups() {
  const [s] = useT()
  const [d, err] = useLoad('/admin/agency/groups/')
  const [dash] = useLoad('/admin/agency/')
  return (
    <div className="ag space-y-4">
      <Header s={s} switches={dash?.switches} />
      <Alert>{err}</Alert>
      {d === null ? <div className="grid place-items-center py-16"><Spinner /></div> : d && (
        d.results.length === 0 ? <div className="card text-sm text-muted">{s.groups_none}</div> : (
          <div className="ag-groups">
            {d.results.map((g) => (
              <div key={g.id} className="card ag-card">
                <div className="ag-card-h"><h3>{s.owner}: <Link to={`/agency/admins/${encodeURIComponent(g.owner)}`}><bdi>{g.owner}</bdi></Link></h3></div>
                <div className="ag-members">
                  <span className="text-xs text-muted">{s.members}:</span>
                  {g.members.map((m) => (
                    <Link key={m} to={`/agency/admins/${encodeURIComponent(m)}`} className="ag-member" data-missing={g.missing.includes(m) || undefined}>
                      <bdi>{m}</bdi>{g.missing.includes(m) && <em> · {s.missing}</em>}
                    </Link>
                  ))}
                </div>
                {g.note && <p className="text-xs text-muted mt-2">{s.note}: {g.note}</p>}
              </div>
            ))}
          </div>
        )
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
          {meta?.next != null && <div className="flex justify-center mt-3"><button type="button" className="btn-ghost" onClick={() => load(meta.next)}>{s.more}</button></div>}
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
  const [msg, setMsg] = useState('')
  const [e2, setE2] = useState('')
  useEffect(() => { if (d) setIntervalV(String(d.sync_interval_minutes)) }, [d])
  const manage = can('agency.manage')

  const patch = async (body) => {
    setMsg(''); setE2('')
    try { await api.patch('/admin/agency/settings/', body); setMsg(s.saved); load() } catch (e) { setE2(apiError(e)) }
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
      {msg && <Alert kind="success">{msg}</Alert>}
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
            <button className="btn-primary text-sm" disabled={!manage}>{s.save}</button>
          </form>
        </div>
      )}
      {d && <PortalLinkCard s={s} />}
    </div>
  )
}

const CSS = `
.ag-head { margin-bottom: 2px; }
.ag-tabs { display: flex; gap: 6px; overflow-x: auto; scrollbar-width: none; padding-bottom: 2px; }
.ag-tabs::-webkit-scrollbar { display: none; }
.ag-tab { white-space: nowrap; padding: 7px 14px; border-radius: 999px; font-size: 13px; font-weight: 700; color: var(--c-text);
  border: 1px solid var(--c-border); text-decoration: none; }
.ag-tab:hover { border-color: var(--c-primary); }
.ag-tab.on { background: color-mix(in srgb, var(--c-primary) 82%, #000); border-color: color-mix(in srgb, var(--c-primary) 82%, #000); color: #fff; }
.ag-cutover { display: flex; flex-direction: column; gap: 2px; padding: 10px 14px; border-radius: 12px; font-size: 13px; line-height: 1.7;
  color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 12%, transparent); border: 1px solid color-mix(in srgb, var(--c-warning) 30%, transparent); }
.ag-cutover span { color: var(--c-text); }
.ag-num { font-family: 'JetBrains Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }
.ag-kpis { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 170px), 1fr)); }
.ag-kpi { display: flex; flex-direction: column; gap: 6px; border-top: 3px solid var(--tone); padding: 14px 16px; min-width: 0; }
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
.ag-pill { display: inline-block; font-size: 11.5px; font-weight: 700; padding: 2px 9px; border-radius: 999px; white-space: nowrap;
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
@media (max-width: 767px) {
  .ag-portal { flex-direction: column; }
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
