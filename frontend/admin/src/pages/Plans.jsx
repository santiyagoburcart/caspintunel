import { useEffect, useState } from 'react'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { toman } from '../lib/format'
import { DataTable } from '../components/DataTable'
import { Alert, Field, Spinner, Toggle } from '../components/ui'

const GB = 1024 ** 3

const blank = {
  type: 'fixed', name_fa: '', name_en: '', desc_fa: '', desc_en: '',
  category_fa: '', category_en: '',
  panel: '', price: 0, discount_percent: 0, data_limit_gb: '', duration_days: '',
  device_limit: '', min_gb: '', max_gb: '', price_per_gb: '', is_active: true,
  group_ids: [],
}

// API row (bytes / nullable) -> form model (GB / '')
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
  const [rows, setRows] = useState(null)
  const [edit, setEdit] = useState(null)
  const [err, setErr] = useState('')
  const [panels, setPanels] = useState([])               // [{id,name,default_group_ids}]
  const [panelGroups, setPanelGroups] = useState(null)    // [{id,name}] for the selected panel
  const [groupsErr, setGroupsErr] = useState('')

  const load = () => api.get('/admin/plans/').then((r) => setRows(r.data.results)).catch(() => setRows([]))
  useEffect(() => {
    load()
    api.get('/admin/panels/')
      .then((r) => setPanels(r.data.results || r.data || []))
      .catch(() => setPanels([]))
  }, [])

  const selectedPanel = panels.find((p) => String(p.id) === String(edit?.panel))
  const panelDefaultGroups = selectedPanel?.default_group_ids || []

  // (re)fetch the groups of whichever panel the plan is on
  const fetchGroupsFor = (panelId) => {
    setPanelGroups(null); setGroupsErr('')
    if (!panelId) return
    api.get(`/admin/panels/${panelId}/groups/`)
      .then((r) => setPanelGroups(r.data.groups || []))
      .catch((e) => { setPanelGroups([]); setGroupsErr(apiError(e)) })
  }
  useEffect(() => { if (edit?.panel) fetchGroupsFor(edit.panel) }, [edit?.panel])

  const setPanel = (panelId) =>
    setEdit((p) => ({ ...p, panel: panelId, group_ids: [] }))   // groups are panel-scoped

  const groupName = (id) => panelGroups?.find((g) => g.id === id)?.name || `group ${id}`
  const toggleGroup = (id) => setEdit((p) => {
    const has = p.group_ids.includes(id)
    return { ...p, group_ids: has ? p.group_ids.filter((x) => x !== id) : [...p.group_ids, id] }
  })
  const effectiveGroups = edit
    ? (edit.group_ids.length ? edit.group_ids : panelDefaultGroups)
    : []

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
      // Fixed: admin sets the volume (blank = unlimited).
      // Volume-based: the customer picks GB at checkout, so no fixed data_limit.
      data_limit: isVolume ? null : (edit.data_limit_gb === '' ? null : Math.round(Number(edit.data_limit_gb) * GB)),
      min_gb: isVolume ? numOrNull(edit.min_gb) : null,
      max_gb: isVolume ? numOrNull(edit.max_gb) : null,
      price_per_gb: isVolume ? numOrNull(edit.price_per_gb) : null,
    }
    try {
      if (edit.id) await api.patch(`/admin/plans/${edit.id}/`, body)
      else await api.post('/admin/plans/', body)
      setEdit(null); load()
    } catch (e2) { setErr(apiError(e2)) }
  }
  const del = async (id) => {
    if (confirm(lang === 'fa' ? 'حذف شود؟' : 'Delete this plan?')) {
      await api.delete(`/admin/plans/${id}/`); load()
    }
  }

  if (rows === null) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">{t('plans')}</h1>
        <button className="btn-primary text-sm" onClick={() => setEdit({ ...blank })}>{t('create')}</button>
      </div>
      <Alert>{err}</Alert>

      {edit && (
        <form onSubmit={save} className="card grid gap-4 sm:grid-cols-2">
          {/* -- plan type ------------------------------------------------ */}
          <div className="sm:col-span-2">
            <span className="label">{lang === 'fa' ? 'نوع پلن' : 'Plan type'}</span>
            <div className="grid gap-2 sm:grid-cols-2">
              <TypeOption
                active={edit.type === 'fixed'} onClick={() => setEdit({ ...edit, type: 'fixed' })}
                title={lang === 'fa' ? 'ثابت (Fixed)' : 'Fixed'}
                desc={lang === 'fa' ? 'حجم را ادمین تعیین می‌کند؛ قیمت ثابت است.'
                                    : 'Admin sets the GB. Fixed price.'} />
              <TypeOption
                active={edit.type === 'custom_volume'} onClick={() => setEdit({ ...edit, type: 'custom_volume' })}
                title={lang === 'fa' ? 'حجمی (Volume-based)' : 'Volume-based'}
                desc={lang === 'fa' ? 'کاربر مقدار گیگابایت را وارد می‌کند؛ قیمت به‌ازای هر گیگ.'
                                    : 'User enters GB at checkout. Priced per GB.'} />
            </div>
          </div>

          <Field label={lang === 'fa' ? 'نام (فارسی)' : 'Name (fa)'}>
            <input className="input" value={edit.name_fa} onChange={(e) => setEdit({ ...edit, name_fa: e.target.value })} required />
          </Field>
          <Field label={lang === 'fa' ? 'نام (انگلیسی)' : 'Name (en)'}>
            <input className="input" dir="ltr" value={edit.name_en} onChange={(e) => setEdit({ ...edit, name_en: e.target.value })} />
          </Field>

          {/* -- panel (required) ----------------------------------------- */}
          <Field label={lang === 'fa' ? 'پنل (روی کدام پنل ساخته شود؟)' : 'Panel (which panel this plan uses)'}>
            <select className="input" required value={edit.panel}
              onChange={(e) => setPanel(e.target.value)}>
              <option value="">{lang === 'fa' ? '— انتخاب پنل —' : '— select a panel —'}</option>
              {panels.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}{p.is_active ? '' : (lang === 'fa' ? ' (غیرفعال)' : ' (disabled)')}
                </option>
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

          {/* -- customer-facing description -------------------------------- */}
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

          {/* -- volume ---------------------------------------------------- */}
          {edit.type === 'fixed' ? (
            <Field label={lang === 'fa' ? 'حجم به گیگابایت (GB) — خالی = نامحدود'
                                       : 'Volume in gigabytes (GB) — empty = unlimited'}>
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
          <Field label={lang === 'fa' ? 'محدودیت دستگاه/کاربر — خالی = نامحدود'
                                     : 'Device / user limit — empty = unlimited'}>
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

          {/* -- panel groups (scoped to the selected panel) ------------- */}
          <div className="sm:col-span-2">
            <span className="label">
              {lang === 'fa' ? 'گروه‌های پنل' : 'Panel groups'}
              {selectedPanel ? ` — ${selectedPanel.name}` : ''}
            </span>
            <p className="mb-2 text-xs text-muted">
              {lang === 'fa'
                ? 'هیچ‌کدام انتخاب نشود = استفاده از گروه‌های پیش‌فرض همین پنل.'
                : "Select none = inherit this panel's default groups."}
            </p>
            {groupsErr && <Alert>{groupsErr}</Alert>}
            {!edit.panel ? (
              <p className="text-sm text-muted">
                {lang === 'fa' ? 'ابتدا پنل را انتخاب کنید.' : 'Select a panel first.'}
              </p>
            ) : panelGroups === null ? (
              <p className="text-sm text-muted">…</p>
            ) : panelGroups.length === 0 ? (
              <p className="text-sm text-muted">
                {lang === 'fa' ? 'گروه‌های این پنل در دسترس نیست.' : "This panel's groups are unavailable."}
              </p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {panelGroups.map((g) => {
                  const on = edit.group_ids.includes(g.id)
                  return (
                    <button type="button" key={g.id} onClick={() => toggleGroup(g.id)}
                      className="rounded-full border px-3 py-1 text-sm transition"
                      style={{
                        borderColor: on ? 'var(--c-primary)' : 'var(--c-border)',
                        background: on ? 'color-mix(in srgb, var(--c-primary) 14%, transparent)' : 'transparent',
                      }}>
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
              {!edit.group_ids.length && effectiveGroups.length
                ? (lang === 'fa' ? ' (از پیش‌فرض پنل)' : ' (from panel default)') : ''}
            </p>
          </div>

          <div className="col-span-full flex gap-2">
            <button className="btn-primary text-sm">{t('save')}</button>
            <button type="button" className="btn-ghost text-sm" onClick={() => setEdit(null)}>{t('cancel')}</button>
          </div>
        </form>
      )}

      <DataTable
        columns={[
          { key: 'name_fa', label: lang === 'fa' ? 'نام' : 'Name',
            render: (r) => (
              <span>
                {r.name_fa}
                {(r.category_fa || r.category_en) && (
                  <span className="ms-1 text-xs text-muted">· {r.category_fa || r.category_en}</span>
                )}
              </span>
            ) },
          { key: 'panel', label: lang === 'fa' ? 'پنل' : 'Panel',
            render: (r) => r.panel_name || panels.find((p) => p.id === r.panel)?.name || '—' },
          { key: 'type', label: lang === 'fa' ? 'نوع' : 'Type',
            render: (r) => (r.type === 'custom_volume'
              ? (lang === 'fa' ? 'حجمی' : 'Volume')
              : (lang === 'fa' ? 'ثابت' : 'Fixed')) },
          { key: 'data_limit', label: lang === 'fa' ? 'حجم' : 'Volume',
            render: (r) => (r.type === 'custom_volume'
              ? `${r.min_gb || 1}–${r.max_gb || '∞'} GB`
              : r.data_limit ? `${r.data_limit / GB} GB` : t('unlimited')) },
          { key: 'duration_days', label: lang === 'fa' ? 'مدت' : 'Duration', render: (r) => r.duration_days || '∞' },
          { key: 'price', label: lang === 'fa' ? 'قیمت' : 'Price',
            render: (r) => (r.type === 'custom_volume' ? `${toman(r.price_per_gb, lang)} / GB` : toman(r.price, lang)) },
          { key: 'is_active', label: lang === 'fa' ? 'فعال' : 'Active', render: (r) => (r.is_active ? '✓' : '—') },
          { key: 'act', label: '', render: (r) => (
            <span className="flex gap-1">
              <button className="btn-ghost text-xs" onClick={() => setEdit(toForm(r))}>✎</button>
              <button className="btn-ghost text-xs" onClick={() => del(r.id)}>🗑</button>
            </span>
          ) },
        ]}
        rows={rows}
      />
    </div>
  )
}

function TypeOption({ active, onClick, title, desc }) {
  return (
    <button type="button" onClick={onClick}
      className="rounded-xl border p-3 text-start transition"
      style={{
        borderColor: active ? 'var(--c-primary)' : 'var(--c-border)',
        background: active ? 'color-mix(in srgb, var(--c-primary) 12%, transparent)' : 'transparent',
      }}>
      <div className="text-sm font-bold">{title}</div>
      <div className="mt-0.5 text-xs text-muted">{desc}</div>
    </button>
  )
}
