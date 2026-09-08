import { useEffect, useMemo, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { toman, digits } from '../lib/format'
import { Alert, Field, Spinner, Toggle } from '../components/ui'

const GB = 1024 ** 3

const T = {
  fa: {
    title: 'مدیریت پلن‌ها',
    subtitle: 'مشاهده، فعال‌سازی، دسته‌بندی و تعریف تعرفه‌های فروش تانل',
    create: 'ایجاد پلن جدید',
    st_total: 'کل پلن‌های تعریف‌شده', st_total_u: 'پلن',
    st_active: 'پلن‌های فعال در فروشگاه', st_active_u: 'مورد فعال',
    st_fixed: 'پلن‌های حجم‌ثابت', st_volume: 'پلن‌های حجمی (به‌ازای گیگ)', st_unit: 'مورد',
    search_ph: 'جستجو نام پلن یا دسته‌بندی...',
    f_type_all: 'همه انواع', f_panel_all: 'تمام پنل‌ها', f_status_all: 'وضعیت: همه',
    only_active: 'فقط فعال', only_inactive: 'غیرفعال‌شده', reset: 'پاک‌سازی فیلترها',
    c_name: 'نام پلن', c_type: 'نوع', c_panel: 'پنل سرور', c_vol: 'حجم و مدت',
    c_devices: 'محدودیت کاربر', c_price: 'قیمت تعرفه', c_discount: 'تخفیف',
    c_status: 'وضعیت', c_actions: 'عملیات',
    fixed: 'ثابت', volume: 'حجمی',
    per_gb: 'تومان / هر گیگ', user_enters: 'ورود توسط کاربر', no_expiry: 'بدون انقضا',
    days_valid: '{n} روز اعتبار', devices_n: '{n} دستگاه', unlimited_short: 'نامحدود',
    discount_off: '{n}٪ تخفیف', none: 'پلنی یافت نشد',
    copy_link: 'کپی لینک مستقیم خرید', link_copied: 'لینک خرید کپی شد',
    edit: 'ویرایش', del: 'حذف', del_confirm: 'این پلن حذف شود؟',
    saved_ok: 'پلن ذخیره شد',
  },
  en: {
    title: 'Plans',
    subtitle: 'View, activate, categorize and price your tunnel plans',
    create: 'Create new plan',
    st_total: 'Total plans defined', st_total_u: 'plans',
    st_active: 'Active plans in the store', st_active_u: 'active',
    st_fixed: 'Fixed-volume plans', st_volume: 'Volume-based (pay per GB) plans', st_unit: '',
    search_ph: 'Search plan name or category…',
    f_type_all: 'All types', f_panel_all: 'All panels', f_status_all: 'Status: all',
    only_active: 'Active only', only_inactive: 'Disabled', reset: 'Reset filters',
    c_name: 'Plan name', c_type: 'Type', c_panel: 'Server panel', c_vol: 'Volume & duration',
    c_devices: 'User limit', c_price: 'Price', c_discount: 'Discount',
    c_status: 'Status', c_actions: 'Actions',
    fixed: 'Fixed', volume: 'Volume',
    per_gb: 'T / GB', user_enters: 'entered by user', no_expiry: 'no expiry',
    days_valid: '{n} days', devices_n: '{n} devices', unlimited_short: 'unlimited',
    discount_off: '{n}% off', none: 'No plans found',
    copy_link: 'Copy direct purchase link', link_copied: 'Purchase link copied',
    edit: 'Edit', del: 'Delete', del_confirm: 'Delete this plan?',
    saved_ok: 'Plan saved',
  },
}

const DOT = ['#1464BA', '#0891B2', '#D97706', '#7C3AED', '#11AB53', '#DB2777']

function Ico({ d, w = 16 }) {
  return (
    <svg viewBox="0 0 24 24" width={w} height={w} fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{d}</svg>
  )
}
const I = {
  layers: <><path d="M12 2L2 7l10 5 10-5-10-5z" /><path d="M2 17l10 5 10-5M2 12l10 5 10-5" /></>,
  check: <><path d="M22 11.08V12a10 10 0 11-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></>,
  pin: <path d="M12 2C8 2 5 5 5 9c0 5 7 13 7 13s7-8 7-13c0-4-3-7-7-7zm0 9.5a2.5 2.5 0 110-5 2.5 2.5 0 010 5z" />,
  bolt: <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />,
  search: <><circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" /></>,
  reset: <><path d="M23 4v6h-6M1 20v-6h6" /><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" /></>,
  edit: <path d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />,
  link: <><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71" /><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71" /></>,
  trash: <><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
}

function Stat({ label, value, unit, tone, icon, lang }) {
  return (
    <div className="card pl-stat">
      <div>
        <p className="pl-stat-label">{label}</p>
        <h3 className="pl-stat-val">
          {value == null ? '—' : digits(value, lang)}{unit ? <span className="pl-stat-unit"> {unit}</span> : null}
        </h3>
      </div>
      <span className="pl-stat-ico" style={{ background: `color-mix(in srgb, ${tone} 13%, transparent)`, color: tone }}>{icon}</span>
    </div>
  )
}

const blank = {
  type: 'fixed', name_fa: '', name_en: '', desc_fa: '', desc_en: '',
  category_fa: '', category_en: '',
  panel: '', price: 0, discount_percent: 0, data_limit_gb: '', duration_days: '',
  device_limit: '', min_gb: '', max_gb: '', price_per_gb: '', is_active: true,
  group_ids: [],
}

function toForm(r) {
  return {
    ...blank, ...r,
    panel: r.panel ?? '',
    category_fa: r.category_fa ?? '',
    category_en: r.category_en ?? '',
    data_limit_gb: r.data_limit ? String(r.data_limit / GB) : '',
    duration_days: r.duration_days ?? '',
    device_limit: r.device_limit ?? '',
    min_gb: r.min_gb ?? '',
    max_gb: r.max_gb ?? '',
    price_per_gb: r.price_per_gb ?? '',
    group_ids: Array.isArray(r.group_ids) ? r.group_ids : [],
  }
}

const numOrNull = (v) => (v === '' || v === null ? null : Number(v))

export default function Plans() {
  const { t, lang } = useI18n()
  const s = T[lang] || T.fa
  const [rows, setRows] = useState(null)
  const [edit, setEdit] = useState(null)
  const [err, setErr] = useState('')
  const [toast, setToast] = useState('')
  const [panels, setPanels] = useState([])
  const [panelGroups, setPanelGroups] = useState(null)
  const [groupsErr, setGroupsErr] = useState('')
  const [q, setQ] = useState('')
  const [fType, setFType] = useState('')
  const [fPanel, setFPanel] = useState('')
  const [fStatus, setFStatus] = useState('')

  const load = () => api.get('/admin/plans/').then((r) => setRows(r.data.results ?? r.data)).catch(() => setRows([]))
  useEffect(() => {
    load()
    api.get('/admin/panels/').then((r) => setPanels(r.data.results || r.data || [])).catch(() => setPanels([]))
  }, [])

  const selectedPanel = panels.find((p) => String(p.id) === String(edit?.panel))
  const panelDefaultGroups = selectedPanel?.default_group_ids || []

  const fetchGroupsFor = (panelId) => {
    setPanelGroups(null); setGroupsErr('')
    if (!panelId) return
    api.get(`/admin/panels/${panelId}/groups/`)
      .then((r) => setPanelGroups(r.data.groups || []))
      .catch((e) => { setPanelGroups([]); setGroupsErr(apiError(e)) })
  }
  useEffect(() => { if (edit?.panel) fetchGroupsFor(edit.panel) }, [edit?.panel])

  const setPanel = (panelId) => setEdit((p) => ({ ...p, panel: panelId, group_ids: [] }))
  const groupName = (id) => panelGroups?.find((g) => g.id === id)?.name || `group ${id}`
  const toggleGroup = (id) => setEdit((p) => {
    const has = p.group_ids.includes(id)
    return { ...p, group_ids: has ? p.group_ids.filter((x) => x !== id) : [...p.group_ids, id] }
  })
  const effectiveGroups = edit ? (edit.group_ids.length ? edit.group_ids : panelDefaultGroups) : []
  const isVolume = edit?.type === 'custom_volume'

  const save = async (e) => {
    e.preventDefault(); setErr('')
    if (!edit.panel) { setErr(lang === 'fa' ? 'انتخاب پنل الزامی است.' : 'Panel is required.'); return }
    const body = {
      type: edit.type,
      panel: Number(edit.panel),
      name_fa: edit.name_fa, name_en: edit.name_en,
      desc_fa: edit.desc_fa, desc_en: edit.desc_en,
      category_fa: edit.category_fa, category_en: edit.category_en,
      price: Number(edit.price) || 0,
      discount_percent: Number(edit.discount_percent) || 0,
      duration_days: numOrNull(edit.duration_days),
      device_limit: numOrNull(edit.device_limit),
      is_active: edit.is_active,
      group_ids: edit.group_ids,
      data_limit: isVolume ? null : (edit.data_limit_gb === '' ? null : Math.round(Number(edit.data_limit_gb) * GB)),
      min_gb: isVolume ? numOrNull(edit.min_gb) : null,
      max_gb: isVolume ? numOrNull(edit.max_gb) : null,
      price_per_gb: isVolume ? numOrNull(edit.price_per_gb) : null,
    }
    try {
      if (edit.id) await api.patch(`/admin/plans/${edit.id}/`, body)
      else await api.post('/admin/plans/', body)
      setEdit(null); load()
      setToast(s.saved_ok); setTimeout(() => setToast(''), 2200)
    } catch (e2) { setErr(apiError(e2)) }
  }
  const del = async (id) => {
    if (confirm(s.del_confirm)) { await api.delete(`/admin/plans/${id}/`); load() }
  }
  const quickToggleActive = async (r) => {
    setRows((cur) => cur.map((x) => (x.id === r.id ? { ...x, is_active: !r.is_active } : x)))
    try { await api.patch(`/admin/plans/${r.id}/`, { is_active: !r.is_active }) } catch { load() }
  }
  const copyLink = (r) => {
    const url = `${location.origin}/checkout?plan=${r.id}`
    navigator.clipboard?.writeText(url)
    setToast(s.link_copied); setTimeout(() => setToast(''), 2000)
  }

  const stats = useMemo(() => {
    if (!rows) return {}
    return {
      total: rows.length,
      active: rows.filter((r) => r.is_active).length,
      fixed: rows.filter((r) => r.type !== 'custom_volume').length,
      volume: rows.filter((r) => r.type === 'custom_volume').length,
    }
  }, [rows])

  const filtered = useMemo(() => {
    if (!rows) return []
    const needle = q.trim().toLowerCase()
    return rows.filter((r) => {
      if (fType === 'fixed' && r.type === 'custom_volume') return false
      if (fType === 'volume' && r.type !== 'custom_volume') return false
      if (fPanel && String(r.panel) !== String(fPanel)) return false
      if (fStatus === 'active' && !r.is_active) return false
      if (fStatus === 'inactive' && r.is_active) return false
      if (needle) {
        const hay = `${r.name_fa} ${r.name_en} ${r.category_fa} ${r.category_en}`.toLowerCase()
        if (!hay.includes(needle)) return false
      }
      return true
    })
  }, [rows, q, fType, fPanel, fStatus])

  const resetFilters = () => { setQ(''); setFType(''); setFPanel(''); setFStatus('') }
  const panelName = (r) => r.panel_name || panels.find((p) => p.id === r.panel)?.name || '—'
  const volLabel = (r) => {
    if (r.type === 'custom_volume') return s.user_enters
    return r.data_limit ? `${digits(r.data_limit / GB, lang)} GB` : t('unlimited')
  }
  const durLabel = (r) => (r.duration_days ? s.days_valid.replace('{n}', digits(r.duration_days, lang)) : s.no_expiry)

  if (rows === null) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="pl space-y-5">
      <style>{CSS}</style>

      <div className="pl-head">
        <div>
          <h1 className="text-lg font-bold">{s.title}</h1>
          <p className="text-sm text-muted mt-1">{s.subtitle}</p>
        </div>
        <button className="btn-primary text-sm pl-add" onClick={() => setEdit({ ...blank })}>
          <Ico d={I.plus} w={15} /> {s.create}
        </button>
      </div>

      <div className="pl-stats">
        <Stat label={s.st_total} value={stats.total} unit={s.st_total_u} tone="#1464BA" icon={<Ico d={I.layers} w={22} />} lang={lang} />
        <Stat label={s.st_active} value={stats.active} unit={s.st_active_u} tone="#11AB53" icon={<Ico d={I.check} w={22} />} lang={lang} />
        <Stat label={s.st_fixed} value={stats.fixed} unit={s.st_unit} tone="#0891B2" icon={<Ico d={I.pin} w={22} />} lang={lang} />
        <Stat label={s.st_volume} value={stats.volume} unit={s.st_unit} tone="#7C3AED" icon={<Ico d={I.bolt} w={22} />} lang={lang} />
      </div>

      <Alert>{err}</Alert>
      {toast && <Alert kind="success">{toast}</Alert>}

      {edit && (
        <form onSubmit={save} className="card pl-form grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <span className="label">{lang === 'fa' ? 'نوع پلن' : 'Plan type'}</span>
            <div className="grid gap-2 sm:grid-cols-2">
              <TypeOption active={edit.type === 'fixed'} onClick={() => setEdit({ ...edit, type: 'fixed' })}
                title={lang === 'fa' ? 'ثابت (Fixed)' : 'Fixed'}
                desc={lang === 'fa' ? 'حجم را ادمین تعیین می‌کند؛ قیمت ثابت است.' : 'Admin sets the GB. Fixed price.'} />
              <TypeOption active={edit.type === 'custom_volume'} onClick={() => setEdit({ ...edit, type: 'custom_volume' })}
                title={lang === 'fa' ? 'حجمی (Volume-based)' : 'Volume-based'}
                desc={lang === 'fa' ? 'کاربر مقدار گیگابایت را وارد می‌کند؛ قیمت به‌ازای هر گیگ.' : 'User enters GB at checkout. Priced per GB.'} />
            </div>
          </div>

          <Field label={lang === 'fa' ? 'نام (فارسی)' : 'Name (fa)'}>
            <input className="input" value={edit.name_fa} onChange={(e) => setEdit({ ...edit, name_fa: e.target.value })} required />
          </Field>
          <Field label={lang === 'fa' ? 'نام (انگلیسی)' : 'Name (en)'}>
            <input className="input" dir="ltr" value={edit.name_en} onChange={(e) => setEdit({ ...edit, name_en: e.target.value })} />
          </Field>

          <Field label={lang === 'fa' ? 'پنل (روی کدام پنل ساخته شود؟)' : 'Panel (which panel this plan uses)'}>
            <select className="input" required value={edit.panel} onChange={(e) => setPanel(e.target.value)}>
              <option value="">{lang === 'fa' ? '— انتخاب پنل —' : '— select a panel —'}</option>
              {panels.map((p) => (
                <option key={p.id} value={p.id}>{p.name}{p.is_active ? '' : (lang === 'fa' ? ' (غیرفعال)' : ' (disabled)')}</option>
              ))}
            </select>
          </Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label={lang === 'fa' ? 'دسته (فارسی)' : 'Category (fa)'}>
              <input className="input" placeholder={lang === 'fa' ? 'مثلاً وایرگارد' : ''}
                value={edit.category_fa} onChange={(e) => setEdit({ ...edit, category_fa: e.target.value })} />
            </Field>
            <Field label={lang === 'fa' ? 'دسته (انگلیسی)' : 'Category (en)'}>
              <input className="input" dir="ltr" placeholder="e.g. wireguard"
                value={edit.category_en} onChange={(e) => setEdit({ ...edit, category_en: e.target.value })} />
            </Field>
          </div>

          <Field label={lang === 'fa' ? 'توضیح برای مشتری (فارسی)' : 'Customer description (fa)'}>
            <textarea className="input" rows={2} value={edit.desc_fa}
              onChange={(e) => setEdit({ ...edit, desc_fa: e.target.value })}
              placeholder={lang === 'fa' ? 'در فروشگاه و صفحهٔ پرداخت به کاربر نمایش داده می‌شود' : ''} />
          </Field>
          <Field label={lang === 'fa' ? 'توضیح برای مشتری (انگلیسی)' : 'Customer description (en)'}>
            <textarea className="input" dir="ltr" rows={2} value={edit.desc_en}
              onChange={(e) => setEdit({ ...edit, desc_en: e.target.value })}
              placeholder="Shown to the customer in the store & checkout" />
          </Field>

          {edit.type === 'fixed' ? (
            <Field label={lang === 'fa' ? 'حجم به گیگابایت (GB) — خالی = نامحدود' : 'Volume in gigabytes (GB) — empty = unlimited'}>
              <input className="input" dir="ltr" type="number" min="0" step="0.5" placeholder={t('unlimited')}
                value={edit.data_limit_gb} onChange={(e) => setEdit({ ...edit, data_limit_gb: e.target.value })} />
            </Field>
          ) : (
            <>
              <Field label={lang === 'fa' ? 'حداقل گیگابایت (GB)' : 'Minimum GB'}>
                <input className="input" dir="ltr" type="number" min="1"
                  value={edit.min_gb} onChange={(e) => setEdit({ ...edit, min_gb: e.target.value })} />
              </Field>
              <Field label={lang === 'fa' ? 'حداکثر گیگابایت (GB)' : 'Maximum GB'}>
                <input className="input" dir="ltr" type="number" min="1"
                  value={edit.max_gb} onChange={(e) => setEdit({ ...edit, max_gb: e.target.value })} />
              </Field>
              <Field label={lang === 'fa' ? 'قیمت هر گیگابایت (تومان)' : 'Price per GB (toman)'}>
                <input className="input" dir="ltr" type="number" min="0"
                  value={edit.price_per_gb} onChange={(e) => setEdit({ ...edit, price_per_gb: e.target.value })} />
              </Field>
            </>
          )}

          <Field label={lang === 'fa' ? 'مدت به روز — خالی = بدون انقضا' : 'Duration in days — empty = no expiry'}>
            <input className="input" dir="ltr" type="number" min="0" placeholder="∞"
              value={edit.duration_days} onChange={(e) => setEdit({ ...edit, duration_days: e.target.value })} />
          </Field>
          <Field label={lang === 'fa' ? 'محدودیت دستگاه/کاربر — خالی = نامحدود' : 'Device / user limit — empty = unlimited'}>
            <input className="input" dir="ltr" type="number" min="0" placeholder={t('unlimited')}
              value={edit.device_limit} onChange={(e) => setEdit({ ...edit, device_limit: e.target.value })} />
          </Field>

          <Field label={lang === 'fa' ? (isVolume ? 'قیمت پایه (تومان)' : 'قیمت (تومان)') : (isVolume ? 'Base price (toman)' : 'Price (toman)')}>
            <input className="input" dir="ltr" type="number" min="0"
              value={edit.price} onChange={(e) => setEdit({ ...edit, price: e.target.value })} />
          </Field>
          <Field label={lang === 'fa' ? 'تخفیف (٪)' : 'Discount (%)'}>
            <input className="input" dir="ltr" type="number" min="0" max="100"
              value={edit.discount_percent} onChange={(e) => setEdit({ ...edit, discount_percent: e.target.value })} />
          </Field>

          <label className="flex items-center gap-2 text-sm">
            <Toggle checked={edit.is_active} onChange={(v) => setEdit({ ...edit, is_active: v })}
              label={lang === 'fa' ? 'فعال' : 'Active'} />
            {lang === 'fa' ? 'فعال' : 'Active'}
          </label>

          <div className="sm:col-span-2 pl-groups">
            <span className="label">
              {lang === 'fa' ? 'گروه‌های پنل' : 'Panel groups'}{selectedPanel ? ` — ${selectedPanel.name}` : ''}
            </span>
            <p className="mb-2 text-xs text-muted">
              {lang === 'fa' ? 'هیچ‌کدام انتخاب نشود = استفاده از گروه‌های پیش‌فرض همین پنل.'
                : "Select none = inherit this panel's default groups."}
            </p>
            {groupsErr && <Alert>{groupsErr}</Alert>}
            {!edit.panel ? (
              <p className="text-sm text-muted">{lang === 'fa' ? 'ابتدا پنل را انتخاب کنید.' : 'Select a panel first.'}</p>
            ) : panelGroups === null ? (
              <p className="text-sm text-muted">…</p>
            ) : panelGroups.length === 0 ? (
              <p className="text-sm text-muted">{lang === 'fa' ? 'گروه‌های این پنل در دسترس نیست.' : "This panel's groups are unavailable."}</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {panelGroups.map((g) => {
                  const on = edit.group_ids.includes(g.id)
                  return (
                    <button type="button" key={g.id} onClick={() => toggleGroup(g.id)}
                      className="pl-group-chip" data-on={on ? '1' : '0'}>
                      {on ? '✓ ' : ''}{g.name} <span className="text-xs text-muted">#{g.id}</span>
                    </button>
                  )
                })}
              </div>
            )}
            <p className="mt-2 text-xs" style={{ color: 'var(--c-primary)' }}>
              {lang === 'fa' ? 'اعمال‌شده روی کاربر جدید: ' : 'Applied to a new user: '}
              {effectiveGroups.length
                ? effectiveGroups.map(groupName).join('، ')
                : (lang === 'fa' ? '— (پنل هیچ گروه پیش‌فرضی ندارد)' : '— (panel has no default groups)')}
            </p>
          </div>

          <div className="col-span-full flex gap-2">
            <button className="btn-primary text-sm">{t('save')}</button>
            <button type="button" className="btn-ghost text-sm" onClick={() => setEdit(null)}>{t('cancel')}</button>
          </div>
        </form>
      )}

      <div className="card pl-toolbar">
        <div className="pl-search">
          <span className="pl-search-ico"><Ico d={I.search} w={16} /></span>
          <input className="input" placeholder={s.search_ph} value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <select className="input pl-sel" value={fType} onChange={(e) => setFType(e.target.value)}>
          <option value="">{s.f_type_all}</option>
          <option value="fixed">{s.fixed}</option>
          <option value="volume">{s.volume}</option>
        </select>
        <select className="input pl-sel" value={fPanel} onChange={(e) => setFPanel(e.target.value)}>
          <option value="">{s.f_panel_all}</option>
          {panels.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <select className="input pl-sel" value={fStatus} onChange={(e) => setFStatus(e.target.value)}>
          <option value="">{s.f_status_all}</option>
          <option value="active">{s.only_active}</option>
          <option value="inactive">{s.only_inactive}</option>
        </select>
        <button className="pl-icon-btn" onClick={resetFilters} title={s.reset} aria-label={s.reset}><Ico d={I.reset} w={15} /></button>
      </div>

      {filtered.length === 0 ? (
        <div className="card text-center text-muted">{s.none}</div>
      ) : (
        <div className="card p-0 pl-wrap">
          <table className="pl-table">
            <thead>
              <tr>
                <th>{s.c_name}</th><th>{s.c_type}</th><th>{s.c_panel}</th><th>{s.c_vol}</th>
                <th>{s.c_devices}</th><th>{s.c_price}</th><th>{s.c_discount}</th>
                <th className="pl-c">{s.c_status}</th><th className="pl-c">{s.c_actions}</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r, i) => {
                const vol = r.type === 'custom_volume'
                return (
                  <tr key={r.id} className={'pl-row' + (r.is_active ? '' : ' pl-row--off')}>
                    <td>
                      <div className="pl-name">
                        <span className="pl-dot" style={{ background: DOT[i % DOT.length] }} />
                        <div>
                          <div className="pl-name-fa">{lang === 'fa' ? r.name_fa : (r.name_en || r.name_fa)}</div>
                          {r.name_en && <div className="pl-name-en">{r.name_en}</div>}
                        </div>
                      </div>
                    </td>
                    <td><span className={'pl-type ' + (vol ? 'vol' : 'fix')}>{vol ? s.volume : s.fixed}</span></td>
                    <td className="pl-muted">{panelName(r)}</td>
                    <td>
                      <div className="pl-vol">{volLabel(r)}</div>
                      <div className="pl-sub">{durLabel(r)}</div>
                    </td>
                    <td className="pl-muted">
                      {r.device_limit ? s.devices_n.replace('{n}', digits(r.device_limit, lang)) : s.unlimited_short}
                    </td>
                    <td className="pl-price">
                      {vol ? (
                        <>{toman(r.price_per_gb, lang)} <span className="pl-sub">/ {lang === 'fa' ? 'گیگ' : 'GB'}</span></>
                      ) : r.discount_percent > 0 ? (
                        <>
                          <div>{toman(Math.round(r.price * (1 - r.discount_percent / 100)), lang)}</div>
                          <div className="pl-strike">{toman(r.price, lang)}</div>
                        </>
                      ) : toman(r.price, lang)}
                    </td>
                    <td>
                      {r.discount_percent > 0
                        ? <span className="pl-discount">{s.discount_off.replace('{n}', digits(r.discount_percent, lang))}</span>
                        : <span className="pl-muted">{digits(0, lang)}{lang === 'fa' ? '٪' : '%'}</span>}
                    </td>
                    <td className="pl-c">
                      <Toggle checked={r.is_active} onChange={() => quickToggleActive(r)} label={s.c_status} />
                    </td>
                    <td className="pl-c">
                      <div className="pl-acts">
                        <button type="button" className="pl-act" title={s.edit} aria-label={s.edit} onClick={() => setEdit(toForm(r))}><Ico d={I.edit} w={15} /></button>
                        <button type="button" className="pl-act" title={s.copy_link} aria-label={s.copy_link} onClick={() => copyLink(r)}><Ico d={I.link} w={15} /></button>
                        <button type="button" className="pl-act pl-act--del" title={s.del} aria-label={s.del} onClick={() => del(r.id)}><Ico d={I.trash} w={15} /></button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function TypeOption({ active, onClick, title, desc }) {
  return (
    <button type="button" onClick={onClick} className="pl-typeopt" data-on={active ? '1' : '0'}>
      <div className="text-sm font-bold">{title}</div>
      <div className="mt-0.5 text-xs text-muted">{desc}</div>
    </button>
  )
}

const CSS = `
.pl-head { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-start; justify-content: space-between; }
.pl-add { display: inline-flex; align-items: center; gap: 6px; }

.pl-stats { display: grid; grid-template-columns: 1fr; gap: 14px; }
@media (min-width: 640px) { .pl-stats { grid-template-columns: repeat(2, 1fr); } }
@media (min-width: 1024px) { .pl-stats { grid-template-columns: repeat(4, 1fr); } }
.pl-stat { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.pl-stat-label { font-size: 12px; font-weight: 600; color: var(--c-text-muted); }
.pl-stat-val { font-size: 24px; font-weight: 800; letter-spacing: -.02em; margin-top: 4px; font-family: 'JetBrains Mono', ui-monospace, monospace; }
.pl-stat-unit { font-size: 11px; font-weight: 500; color: var(--c-text-muted); font-family: inherit; }
.pl-stat-ico { width: 46px; height: 46px; border-radius: 13px; display: grid; place-items: center; flex-shrink: 0; }

.pl-form .pl-groups { border-top: 1px solid var(--c-border); padding-top: 14px; }
.pl-typeopt { border-radius: 12px; border: 1px solid var(--c-border); padding: 12px; text-align: start; transition: .15s; background: transparent; }
.pl-typeopt[data-on="1"] { border-color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 12%, transparent); }
.pl-group-chip { border-radius: 999px; border: 1px solid var(--c-border); padding: 4px 12px; font-size: 13px; transition: .15s; }
.pl-group-chip[data-on="1"] { border-color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 14%, transparent); }

.pl-toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.pl-search { position: relative; flex: 1 1 220px; min-width: 190px; }
.pl-search .input { padding-inline-start: 38px; width: 100%; }
.pl-search-ico { position: absolute; inset-inline-start: 12px; top: 50%; transform: translateY(-50%); color: var(--c-text-muted); pointer-events: none; }
.pl-sel { max-width: 190px; flex: 0 1 160px; }
.pl-icon-btn { display: inline-flex; align-items: center; padding: 9px 11px; border-radius: 10px; color: var(--c-text-muted); border: 1px solid var(--c-border); background: transparent; transition: .15s; }
.pl-icon-btn:hover { color: var(--c-text); border-color: var(--c-primary); }

.pl-wrap { overflow-x: auto; }
.pl-table { width: 100%; min-width: 900px; border-collapse: collapse; font-size: 13px; }
.pl-table thead th {
  text-align: start; font-weight: 600; font-size: 11.5px; text-transform: uppercase; letter-spacing: .03em;
  color: var(--c-text-muted); padding: 13px 16px; white-space: nowrap; border-bottom: 1px solid var(--c-border);
}
.pl-table td { padding: 13px 16px; vertical-align: middle; border-bottom: 1px solid var(--c-border); }
.pl-row:hover > td { background: color-mix(in srgb, var(--c-primary) 5%, transparent); }
.pl-row--off { opacity: .55; }
.pl-c { text-align: center; }
.pl-muted { color: var(--c-text-muted); font-size: 12px; }
.pl-sub { color: var(--c-text-muted); font-size: 11px; margin-top: 2px; }

.pl-name { display: flex; align-items: center; gap: 11px; }
.pl-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.pl-name-fa { font-weight: 700; }
.pl-name-en { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 11px; color: var(--c-text-muted); margin-top: 1px; }
.pl-vol { font-weight: 500; font-size: 12.5px; }

.pl-type { display: inline-block; padding: 2px 9px; border-radius: 7px; font-size: 11px; font-weight: 600; border: 1px solid transparent; }
.pl-type.fix { background: color-mix(in srgb, #1464BA 12%, transparent); color: #1464BA; border-color: color-mix(in srgb, #1464BA 22%, transparent); }
.pl-type.vol { background: color-mix(in srgb, #0891B2 12%, transparent); color: #0891B2; border-color: color-mix(in srgb, #0891B2 22%, transparent); }

.pl-price { font-weight: 700; white-space: nowrap; }
.pl-strike { font-size: 11px; font-weight: 400; color: var(--c-text-muted); text-decoration: line-through; margin-top: 1px; }
.pl-discount { display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 11px; font-weight: 700; white-space: nowrap; background: color-mix(in srgb, var(--c-danger) 12%, transparent); color: var(--c-danger); }

.pl-acts { display: inline-flex; align-items: center; gap: 4px; }
.pl-act { display: inline-flex; padding: 7px; border-radius: 9px; color: var(--c-text-muted); transition: .15s; }
.pl-act:hover { color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 12%, transparent); }
.pl-act--del:hover { color: var(--c-danger); background: color-mix(in srgb, var(--c-danger) 12%, transparent); }
`
