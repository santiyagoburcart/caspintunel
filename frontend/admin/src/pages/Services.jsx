import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n, enumLabel } from '../lib/i18n'
import { jalali, relTime, digits, gb } from '../lib/format'
import { Alert, Spinner, Toggle } from '../components/ui'
import { useServiceActions } from '../lib/serviceActions'
import { useToast } from '../components/Toast'

function Ico({ d, w = 16 }) {
  return (
    <svg viewBox="0 0 24 24" width={w} height={w} fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{d}</svg>
  )
}
const ICONS = {
  plus: <path d="M12 5v14M5 12h14" />,
  sync: <><path d="M23 4v6h-6M1 20v-6h6" /><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" /></>,
  reset: <><path d="M1 4v6h6" /><path d="M3.51 15a9 9 0 102.13-9.36L1 10" /></>,
  revoke: <><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71" /><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71" /></>,
  detail: <><circle cx="12" cy="12" r="10" /><path d="M12 16v-4M12 8h.01" /></>,
  edit: <><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" /><path d="M18.5 2.5a2.12 2.12 0 013 3L12 15l-4 1 1-4 9.5-9.5z" /></>,
  trash: <><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" /></>,
  close: <path d="M18 6L6 18M6 6l12 12" />,
  search: <><circle cx="11" cy="11" r="7" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></>,
  clock: <><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></>,
  check: <polyline points="20 6 9 17 4 12" />,
  user: <><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" /><circle cx="12" cy="7" r="4" /></>,
}

const T = {
  fa: {
    h1: 'سرویس‌های فروخته‌شده', sub: 'مدیریت و همگام‌سازی سرویس‌های کاربران روی پنل‌ها',
    create_btn: 'ایجاد سرویس دستی', sync_btn: 'همگام‌سازی', syncing: 'در حال ارسال…',
    last_synced: 'آخرین همگام‌سازی', never: 'هرگز',
    all: 'همه', active: 'فعال', on_hold: 'در انتظار اتصال', disabled: 'غیرفعال',
    search_ph: 'جستجوی نام اکانت یا کاربر…',
    col_account: 'نام اکانت', col_user: 'کاربر', col_plan: 'پلن', col_panel: 'پنل',
    col_status: 'وضعیت', col_usage: 'مصرف', col_expire: 'انقضا', col_online: 'اتصال', col_actions: 'عملیات',
    online: 'آنلاین', offline: 'آفلاین', unlimited: 'نامحدود', no_expiry: 'بدون انقضا', on_first_conn: 'با اولین اتصال',
    none_found: 'سرویسی یافت نشد', sync_dispatched: 'درخواست همگام‌سازی ارسال شد',
    act_reset: 'ریست حجم', act_revoke: 'تغییر لینک ساب', act_delete: 'حذف سرویس', act_details: 'جزئیات / ویرایش',
    create_title: 'ایجاد سرویس دستی', create_sub: 'بدون پرداخت — مستقیماً روی پنل ساخته می‌شود',
    f_user: 'کاربر', f_user_ph: 'جستجوی نام کاربری، نام یا تلگرام…', f_user_none: 'کاربری یافت نشد',
    f_panel: 'پنل', f_plan: 'پلن', f_plan_none: 'این پنل پلنی ندارد',
    f_groups: 'گروه‌های پنل', f_groups_hint: 'خالی = گروه‌های پیش‌فرض پلن/پنل', f_groups_fetch: 'دریافت گروه‌ها',
    f_account_name: 'نام کاربری سرویس در پنل (اختیاری)', f_account_name_hint: 'خالی بگذارید تا خودکار ساخته شود',
    submit: 'ایجاد سرویس', cancel: 'انصراف', created_ok: 'سرویس با موفقیت ایجاد شد',
    change_user: 'تغییر کاربر', select_plan_ph: '— انتخاب پلن —', select_panel_ph: '— انتخاب پنل —',
    group_word: 'گروه',
    tab_create: 'ساخت سرویس جدید', tab_link: 'اتصال سرویس موجود پنل',
    link_sub: 'اکانتی که از قبل روی پنل وجود دارد به یکی از کاربران ما وصل می‌شود — روی پنل چیزی تغییر نمی‌کند',
    l_search: 'جستجوی اکانت در پنل', l_search_ph: 'نام کاربری سرویس در پنل…', l_pick_panel: 'ابتدا پنل را انتخاب کنید',
    l_searching: 'در حال جستجو در پنل…', l_none: 'اکانتی با این نام روی پنل یافت نشد', l_change: 'تغییر اکانت',
    l_linked: 'قبلاً به کاربر {u} متصل است', l_deleted: 'کاربر حذف‌شده',
    l_plan: 'پلن برای تمدیدهای بعدی (اختیاری)', l_no_plan: '— بدون پلن —', l_plan_hint: 'فقط برای تمدید؛ روی اکانت فعلی اعمال نمی‌شود',
    l_note: 'یک سفارش «اتصال سرویس موجود» بدون پرداخت ثبت می‌شود و مشخصات سرویس از پنل همگام‌سازی می‌شود.',
    l_submit: 'اتصال', linked_ok: 'سرویس موجود با موفقیت متصل شد', user_deleted: 'حذف‌شده',
  },
  en: {
    h1: 'Sold services', sub: "Manage and sync users' services on the panels",
    create_btn: 'Create manual service', sync_btn: 'Sync', syncing: 'Dispatching…',
    last_synced: 'Last synced', never: 'Never',
    all: 'All', active: 'Active', on_hold: 'On-hold', disabled: 'Disabled',
    search_ph: 'Search by account name or user…',
    col_account: 'Account', col_user: 'User', col_plan: 'Plan', col_panel: 'Panel',
    col_status: 'Status', col_usage: 'Usage', col_expire: 'Expiry', col_online: 'Online', col_actions: 'Actions',
    online: 'Online', offline: 'Offline', unlimited: 'unlimited', no_expiry: 'No expiry', on_first_conn: 'on first connection',
    none_found: 'No services found', sync_dispatched: 'Sync request dispatched',
    act_reset: 'Reset usage', act_revoke: 'Revoke subscription', act_delete: 'Delete service', act_details: 'Details / edit',
    create_title: 'Create a manual service', create_sub: 'No payment — provisioned directly on the panel',
    f_user: 'User', f_user_ph: 'Search username, name or Telegram…', f_user_none: 'No user found',
    f_panel: 'Panel', f_plan: 'Plan', f_plan_none: 'This panel has no plans',
    f_groups: 'Panel groups', f_groups_hint: 'Empty = the plan/panel default groups', f_groups_fetch: 'Fetch groups',
    f_account_name: 'Panel service username (optional)', f_account_name_hint: 'Leave empty to auto-generate',
    submit: 'Create service', cancel: 'Cancel', created_ok: 'Service created successfully',
    change_user: 'Change user', select_plan_ph: '— select a plan —', select_panel_ph: '— select a panel —',
    group_word: 'group',
    tab_create: 'Create new service', tab_link: 'Link existing panel service',
    link_sub: 'Attach an account that already exists on the panel to one of our users — nothing changes on the panel',
    l_search: 'Find the account on the panel', l_search_ph: 'Panel service username…', l_pick_panel: 'Select a panel first',
    l_searching: 'Searching the panel…', l_none: 'No account with that name on the panel', l_change: 'Change account',
    l_linked: 'Already linked to user {u}', l_deleted: 'deleted user',
    l_plan: 'Plan for future renewals (optional)', l_no_plan: '— no plan —', l_plan_hint: 'Only used for renewals; not applied to the account now',
    l_note: 'A no-payment "linked existing" order is recorded and the service details are synced from the panel.',
    l_submit: 'Link', linked_ok: 'Existing service linked', user_deleted: 'deleted',
  },
}

const FILTERS = ['', 'active', 'on_hold', 'disabled']

function fmtData(used, limit, s, lang) {
  const u = digits(gb(used), lang)
  if (!limit) return `${u} / ${s.unlimited}`
  return `${u} / ${digits(gb(limit), lang)} GB`
}
const dataPct = (used, limit) => (limit ? Math.min(100, Math.round((used / limit) * 100)) : 0)

export default function Services() {
  const { t, lang } = useI18n()
  const s = T[lang] || T.fa
  const toast = useToast()

  const [rows, setRows] = useState(null)
  const [filter, setFilter] = useState('')
  const [search, setSearch] = useState('')
  const [lastSynced, setLastSynced] = useState(null)
  const [stats, setStats] = useState(null)
  const [err, setErr] = useState('')
  const [syncing, setSyncing] = useState(false)
  const [busyId, setBusyId] = useState(null)
  const [createOpen, setCreateOpen] = useState(false)
  const navigate = useNavigate()
  const actions = useServiceActions()

  const load = () => {
    setErr('')
    const p = new URLSearchParams()
    if (filter) p.set('filter', filter)
    if (search) p.set('search', search)
    p.set('limit', '200')
    api.get(`/admin/services/?${p}`)
      .then((r) => { setRows(r.data.results ?? r.data); setLastSynced(r.data.last_synced_at); setStats(r.data.stats) })
      .catch((e) => { setRows([]); setErr(apiError(e, t('load_error'))) })
  }
  useEffect(load, [filter, search])

  const syncNow = async () => {
    setSyncing(true)
    try {
      await api.post('/admin/services/sync-now/')
      toast.success(s.sync_dispatched)
      setTimeout(load, 1500)
    } catch (e) { toast.error(apiError(e)) } finally { setSyncing(false) }
  }

  const merge = (row, data) => { if (data && data !== true) setRows((cur) => cur.map((r) => (r.id === row.id ? { ...r, ...data } : r))) }
  // every action goes through the shared ConfirmDialog (lib/serviceActions)
  const guarded = (row, fn) => async (...args) => {
    setBusyId(row.id)
    try { return await fn(...args) } catch (e) { toast.error(apiError(e)) } finally { setBusyId(null) }
  }
  const changeStatus = (row, status) => (status === row.status ? null
    : guarded(row, async () => merge(row, await actions.setStatus(row, status)))())
  const resetUsage = (row) => guarded(row, async () => merge(row, await actions.reset(row)))()
  const revoke = (row) => guarded(row, async () => merge(row, await actions.revoke(row)))()
  const deleteService = (row) => guarded(row, async () => {
    if (await actions.remove(row)) setRows((cur) => cur.filter((r) => r.id !== row.id))
  })()

  const expiry = (r) => {
    if (r.expire_strategy === 'never') return s.no_expiry
    if (r.status === 'on_hold' || !r.expire_at) return r.status === 'on_hold' ? s.on_first_conn : '—'
    return jalali(r.expire_at, false, lang)
  }

  return (
    <div className="svc space-y-4">
      <style>{CSS}</style>

      <div className="svc-head">
        <div>
          <h1 className="text-lg font-bold">{s.h1}</h1>
          <p className="text-sm text-muted mt-1">{s.sub}</p>
        </div>
        <div className="svc-head-acts">
          <button type="button" className="btn-ghost text-sm inline-flex items-center gap-1.5" onClick={syncNow} disabled={syncing}>
            <Ico d={ICONS.sync} w={14} />{syncing ? s.syncing : s.sync_btn}
          </button>
          <button type="button" className="btn-primary text-sm inline-flex items-center gap-1.5" onClick={() => setCreateOpen(true)}>
            <Ico d={ICONS.plus} w={14} />{s.create_btn}
          </button>
        </div>
      </div>

      <div className="svc-sync-line">
        <Ico d={ICONS.clock} w={13} />
        {s.last_synced}: {lastSynced ? relTime(lastSynced, lang) : s.never}
        {stats && (
          <span className="svc-stats-inline">
            · {s.active}: {digits(stats.active, lang)} · {s.on_hold}: {digits(stats.on_hold, lang)} · {s.disabled}: {digits(stats.disabled, lang)}
          </span>
        )}
      </div>

      <div className="card svc-toolbar">
        <div className="svc-filters">
          {FILTERS.map((f) => (
            <button key={f || 'all'} type="button" className={'svc-filter-btn' + (filter === f ? ' on' : '')} onClick={() => setFilter(f)}>
              {f ? s[f] : s.all}
            </button>
          ))}
        </div>
        <div className="svc-search">
          <Ico d={ICONS.search} w={14} />
          <input className="input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={s.search_ph} />
        </div>
      </div>

      <Alert>{err}</Alert>

      {rows === null ? (
        <div className="grid place-items-center py-16"><Spinner /></div>
      ) : rows.length === 0 ? (
        <div className="card text-center text-muted">{s.none_found}</div>
      ) : (
        <div className="card p-0 svc-wrap">
          <table className="svc-table">
            <thead>
              <tr>
                <th>{s.col_account}</th><th>{s.col_user}</th><th>{s.col_plan}</th><th>{s.col_panel}</th>
                <th>{s.col_status}</th><th>{s.col_usage}</th><th>{s.col_expire}</th>
                <th className="svc-c">{s.col_online}</th><th className="svc-c">{s.col_actions}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="svc-row">
                  <td data-label={s.col_account} dir="ltr" className="svc-mono">{r.panel_username}</td>
                  <td data-label={s.col_user}>
                    <span className="svc-user">{r.user}{r.user_deleted && <span className="svc-deleted-tag">{s.user_deleted}</span>}</span>
                    {r.user_telegram ? <span className="svc-sub" dir="ltr">@{r.user_telegram}</span> : (r.user_name ? <span className="svc-sub">{r.user_name}</span> : null)}
                  </td>
                  <td data-label={s.col_plan}>{(lang === 'fa' ? r.plan : r.plan_en) || r.plan || '—'}</td>
                  <td data-label={s.col_panel}>{r.panel_name || '—'}</td>
                  <td data-label={s.col_status}>
                    <select className="svc-status-select" value={r.status} disabled={busyId === r.id}
                      onChange={(e) => changeStatus(r, e.target.value)}>
                      <option value="active">{s.active}</option>
                      <option value="on_hold">{s.on_hold}</option>
                      <option value="disabled">{s.disabled}</option>
                      {!['active', 'on_hold', 'disabled'].includes(r.status) && (
                        <option value={r.status} disabled>{enumLabel(t, 'st_', r.status)}</option>
                      )}
                    </select>
                  </td>
                  <td data-label={s.col_usage}>
                    <div className="svc-usage">
                      <span className="svc-mono">{fmtData(r.data_used, r.data_limit, s, lang)}</span>
                      {r.data_limit ? <div className="svc-usage-bar"><i style={{ width: `${dataPct(r.data_used, r.data_limit)}%` }} /></div> : null}
                    </div>
                  </td>
                  <td data-label={s.col_expire} className="svc-mono svc-date">{expiry(r)}</td>
                  <td data-label={s.col_online} className="svc-c">
                    <span className={'svc-conn ' + (r.is_online ? 'on' : 'off')}><i />{r.is_online ? s.online : s.offline}</span>
                  </td>
                  <td data-label={s.col_actions} className="svc-c">
                    <div className="svc-acts">
                      <button type="button" className="svc-icon-btn" title={s.act_reset} disabled={busyId === r.id} onClick={() => resetUsage(r)}>
                        <Ico d={ICONS.reset} w={15} />
                      </button>
                      <button type="button" className="svc-icon-btn" title={s.act_revoke} disabled={busyId === r.id} onClick={() => revoke(r)}>
                        <Ico d={ICONS.revoke} w={15} />
                      </button>
                      <button type="button" className="svc-icon-btn svc-icon-btn--edit" title={s.act_details} onClick={() => navigate(`/services/${r.id}`)}>
                        <Ico d={ICONS.edit} w={15} />
                      </button>
                      <button type="button" className="svc-icon-btn svc-icon-btn--del" title={s.act_delete} disabled={busyId === r.id} onClick={() => deleteService(r)}>
                        <Ico d={ICONS.trash} w={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {createOpen && (
        <ManualCreateModal s={s} t={t} lang={lang}
          onClose={() => setCreateOpen(false)}
          onCreated={(msg) => { setCreateOpen(false); toast.success(msg || s.created_ok); load() }} />
      )}
    </div>
  )
}

function UserPicker({ s, user, setUser }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  useEffect(() => {
    if (!q.trim()) { setResults([]); return undefined }
    const id = setTimeout(() => {
      api.get(`/admin/users/?search=${encodeURIComponent(q)}&limit=8`)
        .then((r) => setResults(r.data.results ?? r.data))
        .catch(() => setResults([]))
    }, 300)
    return () => clearTimeout(id)
  }, [q])

  return (
    <div className="svc-fld">
      <span className="label">{s.f_user}</span>
      {user ? (
        <div className="svc-user-picked">
          <span className="svc-user-picked-ico"><Ico d={ICONS.user} w={14} /></span>
          <span className="min-w-0 flex-1">
            <b>{user.username}</b>{user.name ? <span className="svc-sub"> · {user.name}</span> : null}
          </span>
          <button type="button" className="btn-ghost text-xs" onClick={() => { setUser(null); setQ('') }}>{s.change_user}</button>
        </div>
      ) : (
        <>
          <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder={s.f_user_ph} />
          {q.trim() && (
            <div className="svc-user-results">
              {results.length === 0 ? (
                <div className="svc-user-empty">{s.f_user_none}</div>
              ) : results.map((u) => (
                <button type="button" key={u.id} className="svc-user-result" onClick={() => { setUser(u); setResults([]) }}>
                  <b>{u.username}</b>{u.name ? <span className="svc-sub"> · {u.name}</span> : null}
                  {u.telegram_username ? <span className="svc-sub" dir="ltr"> · @{u.telegram_username}</span> : null}
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

const LINK_TONE = { active: 'success', on_hold: 'warning', disabled: 'danger', expired: 'danger', limited: 'warning' }

function PanelAccountRow({ a, s, t, lang, picked, onPick }) {
  const tone = `var(--c-${LINK_TONE[a.status] || 'text-muted'})`
  const exp = a.expire ? jalali(a.expire, false, lang) : (a.status === 'on_hold' ? s.on_first_conn : s.no_expiry)
  return (
    <button type="button" className={'svc-acc' + (picked ? ' on' : '') + (a.linked ? ' linked' : '')}
      disabled={!!a.linked} onClick={() => onPick(a)} aria-pressed={picked}>
      <span className="svc-acc-top">
        <b dir="ltr" className="svc-mono">{a.username}</b>
        <span className="svc-pill" style={{ color: tone, background: `color-mix(in srgb, ${tone} 14%, transparent)` }}>
          {enumLabel(t, 'st_', a.status)}
        </span>
      </span>
      <span className="svc-acc-meta">
        <span dir="ltr" className="svc-mono">{fmtData(a.used_traffic, a.data_limit, s, lang)}</span>
        <span>· {s.col_expire}: {exp}</span>
      </span>
      {a.linked && (
        <span className="svc-acc-linked">{s.l_linked.replace('{u}', a.linked.username)}{a.linked.user_deleted ? ` (${s.l_deleted})` : ''}</span>
      )}
    </button>
  )
}

function ManualCreateModal({ s, t, lang, onClose, onCreated }) {
  const [mode, setMode] = useState('create') // 'create' | 'link'
  const [user, setUser] = useState(null)
  const [panels, setPanels] = useState([])
  const [panelId, setPanelId] = useState('')
  const [plans, setPlans] = useState([])
  const [planId, setPlanId] = useState('')
  const [groups, setGroups] = useState(null)
  const [fetchingGroups, setFetchingGroups] = useState(false)
  const [selectedGroups, setSelectedGroups] = useState([])
  const [accountName, setAccountName] = useState('')
  // link mode
  const [accQuery, setAccQuery] = useState('')
  const [accResults, setAccResults] = useState(null) // null = not searched yet
  const [accLoading, setAccLoading] = useState(false)
  const [accErr, setAccErr] = useState('')
  const [picked, setPicked] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    api.get('/admin/panels/?limit=200').then((r) => setPanels((r.data.results || r.data || []).filter((p) => p.is_active))).catch(() => setPanels([]))
    api.get('/admin/plans/?limit=200').then((r) => setPlans(r.data.results || r.data || [])).catch(() => setPlans([]))
  }, [])

  // live, debounced search of the selected panel's accounts
  useEffect(() => {
    if (mode !== 'link' || !panelId) { setAccResults(null); return undefined }
    setAccLoading(true); setAccErr('')
    const id = setTimeout(() => {
      api.get(`/admin/services/panel-users/?panel=${panelId}&search=${encodeURIComponent(accQuery.trim())}`)
        .then((r) => setAccResults(r.data.results || []))
        .catch((e) => { setAccResults([]); setAccErr(apiError(e)) })
        .finally(() => setAccLoading(false))
    }, 350)
    return () => clearTimeout(id)
  }, [mode, panelId, accQuery])

  const panelPlans = useMemo(() => plans.filter((p) => String(p.panel) === String(panelId) && p.is_active), [plans, panelId])

  const fetchGroups = async () => {
    if (!panelId) return
    setFetchingGroups(true); setGroups(null)
    try {
      const r = await api.get(`/admin/panels/${panelId}/groups/`)
      setGroups(r.data.groups || [])
    } catch (e) { setErr(apiError(e)) } finally { setFetchingGroups(false) }
  }

  const toggleGroup = (id) => setSelectedGroups((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]))
  const switchMode = (m) => { setMode(m); setErr(''); setPlanId(''); setPicked(null) }
  const changePanel = (v) => { setPanelId(v); setPlanId(''); setGroups(null); setSelectedGroups([]); setPicked(null); setAccQuery('') }

  const submit = async (e) => {
    e.preventDefault(); setErr(''); setBusy(true)
    try {
      if (mode === 'link') {
        await api.post('/admin/services/link/', {
          panel: Number(panelId), panel_username: picked.username, user: user.id,
          plan: planId ? Number(planId) : null,
        })
        onCreated(s.linked_ok)
      } else {
        await api.post('/admin/services/', {
          user: user.id, plan: Number(planId), panel: panelId ? Number(panelId) : undefined,
          group_ids: selectedGroups.length ? selectedGroups : undefined,
          account_name: accountName.trim() || undefined,
        })
        onCreated(s.created_ok)
      }
    } catch (e2) {
      const d = e2?.response?.data
      setErr(e2?.response?.status === 409 && d?.username ? s.l_linked.replace('{u}', d.username) : apiError(e2))
    } finally { setBusy(false) }
  }

  const canSubmit = mode === 'link' ? !!(user && panelId && picked) : !!(user && planId)

  return (
    <div className="svc-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form className="svc-modal card" onSubmit={submit} role="dialog" aria-modal="true">
        <div className="svc-modal-head">
          <div>
            <h2 className="font-bold">{s.create_title}</h2>
            <p className="text-xs text-muted mt-0.5">{mode === 'link' ? s.link_sub : s.create_sub}</p>
          </div>
          <button type="button" className="svc-icon-btn" onClick={onClose} aria-label={s.cancel}><Ico d={ICONS.close} w={16} /></button>
        </div>
        <div className="svc-mode-tabs" role="tablist">
          {[['create', s.tab_create, ICONS.plus], ['link', s.tab_link, ICONS.revoke]].map(([m, label, icon]) => (
            <button key={m} type="button" role="tab" aria-selected={mode === m}
              className={'svc-mode-tab' + (mode === m ? ' on' : '')} onClick={() => switchMode(m)}>
              <Ico d={icon} w={14} />{label}
            </button>
          ))}
        </div>
        <div className="svc-modal-body">
          <Alert>{err}</Alert>

          {mode === 'create' && <UserPicker s={s} user={user} setUser={setUser} />}

          <div className={mode === 'create' ? 'svc-grid2' : ''}>
            <label className="svc-fld">
              <span className="label">{s.f_panel}</span>
              <select className="input" value={panelId} onChange={(e) => changePanel(e.target.value)}>
                <option value="">{s.select_panel_ph}</option>
                {panels.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </label>
            {mode === 'create' && (
              <label className="svc-fld">
                <span className="label">{s.f_plan}</span>
                <select className="input" value={planId} required disabled={!panelId}
                  onChange={(e) => {
                    setPlanId(e.target.value)
                    const p = panelPlans.find((x) => String(x.id) === e.target.value)
                    if (p?.group_ids?.length) setSelectedGroups(p.group_ids)
                  }}>
                  <option value="">{panelId ? (panelPlans.length ? s.select_plan_ph : s.f_plan_none) : s.select_plan_ph}</option>
                  {panelPlans.map((p) => <option key={p.id} value={p.id}>{lang === 'fa' ? p.name_fa : (p.name_en || p.name_fa)}</option>)}
                </select>
              </label>
            )}
          </div>

          {mode === 'create' && panelId && (
            <div className="svc-fld">
              <div className="svc-groups-head">
                <span className="label mb-0">{s.f_groups}</span>
                <button type="button" className="btn-ghost text-xs" onClick={fetchGroups} disabled={fetchingGroups}>
                  {fetchingGroups ? '…' : s.f_groups_fetch}
                </button>
              </div>
              <p className="svc-hint">{s.f_groups_hint}</p>
              {groups && (
                <div className="svc-groups-grid">
                  {groups.map((g) => (
                    <label key={g.id} className="svc-group-chip">
                      <Toggle checked={selectedGroups.includes(g.id)} onChange={() => toggleGroup(g.id)} label={g.name} />
                      <span className="truncate">{g.name}</span>
                    </label>
                  ))}
                  {groups.length === 0 && <p className="text-xs text-muted">—</p>}
                </div>
              )}
            </div>
          )}

          {mode === 'create' && (
            <label className="svc-fld">
              <span className="label">{s.f_account_name}</span>
              <input className="input" dir="ltr" value={accountName} onChange={(e) => setAccountName(e.target.value)} />
              <span className="svc-hint">{s.f_account_name_hint}</span>
            </label>
          )}

          {mode === 'link' && (
            <>
              <div className="svc-fld">
                <span className="label">{s.l_search}</span>
                {picked ? (
                  <div className="svc-user-picked">
                    <span className="svc-user-picked-ico"><Ico d={ICONS.revoke} w={14} /></span>
                    <span className="min-w-0 flex-1">
                      <b dir="ltr" className="svc-mono">{picked.username}</b>
                      <span className="svc-sub" dir="ltr">{fmtData(picked.used_traffic, picked.data_limit, s, lang)} · {enumLabel(t, 'st_', picked.status)}</span>
                    </span>
                    <button type="button" className="btn-ghost text-xs" onClick={() => setPicked(null)}>{s.l_change}</button>
                  </div>
                ) : (
                  <>
                    <div className="svc-search svc-search--full">
                      <Ico d={ICONS.search} w={14} />
                      <input className="input" dir="ltr" value={accQuery} disabled={!panelId}
                        onChange={(e) => setAccQuery(e.target.value)}
                        placeholder={panelId ? s.l_search_ph : s.l_pick_panel} />
                    </div>
                    {panelId && (
                      <div className="svc-acc-list" aria-busy={accLoading}>
                        {accLoading && accResults === null ? (
                          <div className="svc-user-empty">{s.l_searching}</div>
                        ) : accErr ? (
                          <div className="svc-user-empty svc-err">{accErr}</div>
                        ) : (accResults || []).length === 0 ? (
                          <div className="svc-user-empty">{s.l_none}</div>
                        ) : accResults.map((a) => (
                          <PanelAccountRow key={a.username} a={a} s={s} t={t} lang={lang}
                            picked={picked?.username === a.username} onPick={setPicked} />
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>

              <UserPicker s={s} user={user} setUser={setUser} />

              <label className="svc-fld">
                <span className="label">{s.l_plan}</span>
                <select className="input" value={planId} disabled={!panelId} onChange={(e) => setPlanId(e.target.value)}>
                  <option value="">{s.l_no_plan}</option>
                  {panelPlans.map((p) => <option key={p.id} value={p.id}>{lang === 'fa' ? p.name_fa : (p.name_en || p.name_fa)}</option>)}
                </select>
                <span className="svc-hint">{s.l_plan_hint}</span>
              </label>
              <p className="svc-hint svc-link-note">{s.l_note}</p>
            </>
          )}
        </div>
        <div className="svc-modal-foot">
          <button type="button" className="btn-ghost text-sm" onClick={onClose}>{s.cancel}</button>
          <button type="submit" className="btn-primary text-sm" disabled={busy || !canSubmit}>
            {busy ? '…' : (mode === 'link' ? s.l_submit : s.submit)}
          </button>
        </div>
      </form>
    </div>
  )
}

const CSS = `
.svc-head { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-start; justify-content: space-between; }
.svc-head-acts { display: flex; flex-wrap: wrap; gap: 8px; }
.svc-sync-line { display: flex; align-items: center; gap: 6px; font-size: 11.5px; color: var(--c-text-muted); flex-wrap: wrap; }
.svc-stats-inline { white-space: nowrap; }

.svc-toolbar { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between; }
.svc-filters { display: inline-flex; gap: 4px; padding: 4px; border-radius: 12px; background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); }
.svc-filter-btn { padding: 6px 14px; border-radius: 9px; font-size: 13px; font-weight: 600; color: var(--c-text-muted); }
.svc-filter-btn.on { background: var(--c-primary); color: #fff; }
.svc-search { position: relative; display: flex; align-items: center; min-width: 220px; flex: 1; max-width: 340px; }
.svc-search svg { position: absolute; inset-inline-start: 12px; color: var(--c-text-muted); pointer-events: none; }
.svc-search .input { padding-inline-start: 34px; }

.svc-wrap { overflow-x: auto; }
.svc-table { width: 100%; min-width: 900px; border-collapse: collapse; font-size: 13px; }
.svc-table thead th { text-align: start; font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: .03em;
  color: var(--c-text-muted); padding: 12px 14px; white-space: nowrap; border-bottom: 1px solid var(--c-border); }
.svc-table td { padding: 10px 14px; vertical-align: middle; border-bottom: 1px solid var(--c-border); }
.svc-table tr:last-child td { border-bottom: 0; }
.svc-table tr:hover td { background: color-mix(in srgb, var(--c-primary) 4%, transparent); }
.svc-c { text-align: center; }
.svc-mono { font-family: 'JetBrains Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }
.svc-user { display: block; font-weight: 600; }
.svc-sub { display: block; font-size: 11px; color: var(--c-text-muted); margin-top: 1px; }
.svc-date { white-space: nowrap; color: var(--c-text-muted); font-size: 12px; }

.svc-pill { display: inline-block; border-radius: 999px; padding: 3px 10px; font-size: 11.5px; font-weight: 600; white-space: nowrap; }
.svc-status-select { border: 1px solid var(--c-border); border-radius: 8px; padding: 4px 8px; font-size: 12px; background: transparent; color: var(--c-text); }

.svc-usage { display: flex; flex-direction: column; gap: 4px; min-width: 120px; }
.svc-usage-bar { height: 5px; border-radius: 999px; overflow: hidden; background: color-mix(in srgb, var(--c-text-muted) 20%, transparent); }
.svc-usage-bar > i { display: block; height: 100%; background: var(--c-primary); border-radius: 999px; }

.svc-conn { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; white-space: nowrap; }
.svc-conn i { width: 7px; height: 7px; border-radius: 50%; }
.svc-conn.on { color: var(--c-success); } .svc-conn.on i { background: var(--c-success); }
.svc-conn.off { color: var(--c-text-muted); } .svc-conn.off i { background: var(--c-text-muted); }

.svc-acts { display: inline-flex; gap: 4px; }
.svc-icon-btn { padding: 6px; border-radius: 8px; color: var(--c-text-muted); }
.svc-icon-btn:hover:not(:disabled) { color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 12%, transparent); }
.svc-icon-btn:disabled { opacity: .4; }
.svc-icon-btn--del:hover:not(:disabled) { color: var(--c-danger); background: color-mix(in srgb, var(--c-danger) 12%, transparent); }

/* modal */
.svc-backdrop { position: fixed; inset: 0; z-index: 60; background: color-mix(in srgb, #0b1220 62%, transparent); backdrop-filter: blur(3px);
  display: flex; align-items: flex-start; justify-content: center; padding: 24px 16px; overflow-y: auto; }
.svc-modal { width: 100%; max-width: 560px; padding: 0; overflow: hidden; }
.svc-modal-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 18px 20px; border-bottom: 1px solid var(--c-border); }
.svc-modal-body { padding: 20px; display: flex; flex-direction: column; gap: 16px; max-height: 70vh; overflow-y: auto; }
.svc-modal-foot { display: flex; justify-content: flex-end; gap: 10px; padding: 14px 20px; border-top: 1px solid var(--c-border); }

.svc-detail-h { font-weight: 700; font-size: 13px; margin-bottom: 8px; }
.svc-kv-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.svc-kv { display: flex; flex-direction: column; gap: 2px; font-size: 12.5px; }
.svc-kv span { color: var(--c-text-muted); font-size: 11px; }
.svc-sub-url { margin-top: 10px; padding: 10px 12px; border-radius: 10px; background: color-mix(in srgb, var(--c-text-muted) 6%, transparent); font-size: 11.5px; }
.svc-sub-url span { display: block; color: var(--c-text-muted); margin-bottom: 3px; }
.svc-sub-url code { word-break: break-all; }
.svc-raw { max-height: 260px; overflow: auto; font-size: 11px; padding: 10px 12px; border-radius: 10px;
  background: color-mix(in srgb, var(--c-text-muted) 6%, transparent); direction: ltr; text-align: left; }

.svc-fld { display: flex; flex-direction: column; gap: 6px; position: relative; }
.svc-grid2 { display: grid; grid-template-columns: 1fr; gap: 14px; }
@media (min-width: 480px) { .svc-grid2 { grid-template-columns: 1fr 1fr; } }
.svc-hint { font-size: 11px; color: var(--c-text-muted); }

.svc-user-picked { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-radius: 10px; border: 1px solid var(--c-border); }
.svc-user-picked-ico { width: 28px; height: 28px; border-radius: 8px; flex-shrink: 0; display: grid; place-items: center;
  background: color-mix(in srgb, var(--c-primary) 12%, transparent); color: var(--c-primary); }
.svc-user-results { border: 1px solid var(--c-border); border-radius: 10px; max-height: 180px; overflow-y: auto; }
.svc-user-result { display: block; width: 100%; text-align: start; padding: 8px 12px; font-size: 12.5px; border-bottom: 1px solid var(--c-border); }
.svc-user-result:last-child { border-bottom: 0; }
.svc-user-result:hover { background: color-mix(in srgb, var(--c-primary) 6%, transparent); }
.svc-user-empty { padding: 10px 12px; font-size: 12px; color: var(--c-text-muted); }

.svc-mode-tabs { display: flex; gap: 4px; margin: 14px 20px 0; padding: 4px; border-radius: 12px; background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); }
.svc-mode-tab { flex: 1 1 0; display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 8px 10px; border-radius: 9px;
  font-size: 12.5px; font-weight: 700; color: var(--c-text-muted); text-align: center; }
.svc-mode-tab.on { background: var(--c-primary); color: #fff; }
.svc-search--full { max-width: none; min-width: 0; }
.svc-acc-list { border: 1px solid var(--c-border); border-radius: 10px; max-height: 260px; overflow-y: auto; }
.svc-acc { display: flex; flex-direction: column; gap: 4px; width: 100%; text-align: start; padding: 9px 12px; font-size: 12.5px; border-bottom: 1px solid var(--c-border); }
.svc-acc:last-child { border-bottom: 0; }
.svc-acc:hover:not(:disabled) { background: color-mix(in srgb, var(--c-primary) 6%, transparent); }
.svc-acc.on { background: color-mix(in srgb, var(--c-primary) 12%, transparent); }
.svc-acc.linked { opacity: .65; cursor: not-allowed; }
.svc-acc-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.svc-acc-meta { display: flex; flex-wrap: wrap; gap: 6px; font-size: 11.5px; color: var(--c-text-muted); }
.svc-acc-linked { font-size: 11px; font-weight: 700; color: var(--c-danger); }
.svc-err { color: var(--c-danger); }
.svc-link-note { padding: 8px 10px; border-radius: 8px; background: color-mix(in srgb, var(--c-primary) 7%, transparent); line-height: 1.7; }
.svc-deleted-tag { margin-inline-start: 6px; font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 5px; color: var(--c-danger);
  background: color-mix(in srgb, var(--c-danger) 13%, transparent); }
.svc-groups-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.svc-groups-grid { display: grid; grid-template-columns: 1fr; gap: 6px; }
@media (min-width: 480px) { .svc-groups-grid { grid-template-columns: 1fr 1fr; } }
.svc-group-chip { display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-radius: 8px; border: 1px solid var(--c-border); font-size: 12px; }

/* mobile: table -> stacked cards */
@media (max-width: 900px) {
  .svc-wrap { overflow-x: visible; }
  .svc-table, .svc-table tbody, .svc-table tr, .svc-table td { display: block; width: 100%; }
  .svc-table { min-width: 0; }
  .svc-table thead { display: none; }
  .svc-table tr.svc-row { border: 1px solid var(--c-border); border-radius: 12px; margin: 12px; padding: 4px 0; }
  .svc-table tr.svc-row > td { border-bottom: 0; }
  .svc-table tr:hover td { background: none; }
  .svc-table td { padding: 8px 14px; display: flex; align-items: center; justify-content: space-between; gap: 12px; text-align: end; }
  .svc-table td::before { content: attr(data-label); font-size: 11px; font-weight: 600; color: var(--c-text-muted); text-align: start; white-space: nowrap; }
  .svc-table td.svc-c { justify-content: space-between; }
}
`
