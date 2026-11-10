import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { jalali } from '../lib/format'
import { Alert, Spinner } from './ui'
import { useConfirm } from './ConfirmDialog'
import { Ic } from './AgencyIcons'
import StoreDomains from './StoreDomains'
import StoreBot from './StoreBot'
import StoreStaff from './StoreStaff'
import FailedOrders from './FailedOrders'
import StoreExports from './StoreExports'
import StoreFee from './StoreFee'

// v1.43 (multi-tenant Phase 2, D5) «فروشگاه» on an agency admin's page — OUR staff open and manage a reseller's store.
// v1.45: domains + TLS (StoreDomains); v1.49: the store's Telegram bot (StoreBot). Until a domain is active the store is not reachable.
const T = {
  fa: {
    title: 'فروشگاه', none: 'این ادمین هنوز فروشگاه ندارد.', open: 'ساخت فروشگاه', name: 'نام فروشگاه', slug: 'شناسه',
    status: 'وضعیت', st_draft: 'پیش‌نویس', st_active: 'فعال', st_suspended: 'معلق', st_closed: 'بسته',
    export: 'اجازهٔ دریافت پشتیبان توسط نماینده (پنل فروشگاه)', save: 'ذخیره', created: 'ساخته شده در',
    rpm: 'سقف درخواست در دقیقه (کل فروشگاه)', rpm_hint: 'خالی یا ۰ = بدون سقف؛ بیشتر از آن ۴۲۹ می‌گیرد و به ما خبر داده می‌شود.',
    reachable: 'در دسترس روی دامنهٔ فعال', unreachable: 'در دسترس نیست (فروشگاه فعال با دامنهٔ فعال لازم است)',
    o_title: 'ساخت فروشگاه', o_msg: 'برای {u} یک فروشگاه پیش‌نویس ساخته می‌شود با برندینگ خودش و یک نسخه از صفحه‌های ما (قوانین، راهنما). تا دامنه فعال نشود کسی آن را نمی‌بیند.',
    o_btn: 'بله، بساز', s_title: 'تغییر وضعیت فروشگاه', s_msg: 'وضعیت فروشگاه {n} به «{st}» تغییر می‌کند.', s_btn: 'بله، تغییر بده',
    branding: 'نام در سایت', manage_note: 'برندینگ، صفحه‌ها، پوسته و تنظیمات فروشگاه از پنل همین فروشگاه روی دامنهٔ خودش مدیریت می‌شود.',
  },
  en: {
    title: 'Store', none: 'This admin has no store yet.', open: 'Open a store', name: 'Store name', slug: 'Slug',
    status: 'Status', st_draft: 'Draft', st_active: 'Active', st_suspended: 'Suspended', st_closed: 'Closed',
    export: 'The reseller may download a backup (store panel)', save: 'Save', created: 'Created',
    rpm: 'Requests per minute (whole store)', rpm_hint: 'Empty or 0 = no cap; above it requests get 429 and we are alerted.',
    reachable: 'Reachable on its active domain', unreachable: 'Not reachable (needs an active store with an active domain)',
    o_title: 'Open a store', o_msg: 'A draft store is created for {u} with its own branding and a copy of our pages (rules, help). Nobody sees it until a domain is active.',
    o_btn: 'Yes, open it', s_title: 'Change store status', s_msg: 'Store {n} becomes “{st}”.', s_btn: 'Yes, change it',
    branding: 'Name on the site', manage_note: 'Branding, pages, theme and store settings are managed in the store’s own panel on its domain.',
  },
}
const STATUSES = ['draft', 'active', 'suspended', 'closed']

export default function AgencyStoreCard({ username }) {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const { can } = useAuth()
  const confirm = useConfirm()
  const [store, setStore] = useState(undefined)
  const [err, setErr] = useState('')
  const [form, setForm] = useState({ name: '', export_allowed: false, requests_per_minute: '' })
  const url = `/admin/agency/panel-admins/${encodeURIComponent(username)}/store/`
  const manage = can('agency.manage')

  const load = () => api.get(url).then((r) => {
    setStore(r.data.store)
    if (r.data.store) setForm({ name: r.data.store.name, export_allowed: r.data.store.export_allowed,
      requests_per_minute: r.data.store.limits?.requests_per_minute ?? '' })
  }).catch(() => { setStore(null); setErr(lang === 'fa' ? 'دریافت فروشگاه ناموفق بود' : 'Failed to load the store') })
  useEffect(() => { load() }, [username])

  const open = async () => {
    const ok = await confirm({ tone: 'primary', icon: 'cart', title: s.o_title, targetLabel: s.title, targetId: username,
      message: s.o_msg.replace('{u}', username), confirmLabel: s.o_btn, action: () => api.post(url, { name: username }) })
    if (ok) load()
  }
  const setStatus = async (st) => {
    if (st === store.status) return
    const ok = await confirm({ tone: st === 'active' ? 'success' : 'warning', icon: 'cart', title: s.s_title, targetLabel: s.title,
      targetId: store.name, message: s.s_msg.replace('{n}', store.name).replace('{st}', s['st_' + st]), confirmLabel: s.s_btn,
      action: () => api.patch(url, { status: st }) })
    if (ok) load()
  }
  const save = async (e) => {
    e.preventDefault()
    try { await api.patch(url, form); load() } catch { /* the toast shows why */ }
  }

  if (store === undefined) return <div className="card ag-card grid place-items-center py-8"><Spinner /></div>
  return (
    <div className="card ag-card space-y-3" data-testid="agency-store">
      <style>{CSS}</style>
      <h3 className="ag-sh" data-ac="blue"><Ic n="globe" size={15} />{s.title}</h3>
      <Alert>{err}</Alert>
      {!store && (
        <div className="ags-empty">
          <p className="text-sm text-muted">{s.none}</p>
          {manage && <button type="button" className="ag-act" data-tone="primary" onClick={open} data-testid="store-open"><Ic n="plus" />{s.open}</button>}
        </div>
      )}
      {store && <>
        <div className="ags-head">
          <span className="ags-pill" data-st={store.status}>{s['st_' + store.status]}</span>
          <span className="text-xs text-muted">{s.slug}: <bdi dir="ltr">{store.slug}</bdi> · {s.created}: {jalali(store.created_at, false, lang)}</span>
        </div>
        <p className={'ags-reach' + (store.reachable ? ' ok' : '')}>{store.reachable ? s.reachable : s.unreachable}</p>
        <div className="ags-st" role="radiogroup" aria-label={s.status}>
          {STATUSES.map((st) => (
            <button key={st} type="button" role="radio" aria-checked={store.status === st} disabled={!manage}
              className={'ags-st-b' + (store.status === st ? ' on' : '')} onClick={() => setStatus(st)}>{s['st_' + st]}</button>
          ))}
        </div>
        <form className="ags-form" onSubmit={save}>
          <label className="ags-f"><span>{s.name}</span>
            <input className="input" value={form.name} disabled={!manage} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label className="ags-f"><span>{s.rpm}</span>
            <input className="input" type="number" min="0" inputMode="numeric" dir="ltr" value={form.requests_per_minute} disabled={!manage}
              onChange={(e) => setForm({ ...form, requests_per_minute: e.target.value })} placeholder="0" />
            <small className="text-xs text-muted">{s.rpm_hint}</small></label>
          <label className="ags-chk"><input type="checkbox" checked={form.export_allowed} disabled={!manage}
            onChange={(e) => setForm({ ...form, export_allowed: e.target.checked })} />{s.export}</label>
          {manage && <button className="btn-primary text-sm ags-save" disabled={!form.name.trim()}>{s.save}</button>}
        </form>
        {store.branding && <p className="text-xs text-muted">{s.branding}: <bdi>{lang === 'fa' ? store.branding.site_name_fa : store.branding.site_name_en || store.branding.site_name_fa}</bdi></p>}
        <StoreDomains base={url} domains={store.domains || []} manage={manage} onChanged={load} />
        <StoreBot base={url} bot={store.bot} manage={manage} onChanged={load} />
        <StoreStaff base={url} store={store} manage={manage} onChanged={load} />
        {/* v1.52.1: the store's «ساخت ناموفق» orders — our staff retry them too (same paid order, never a new charge) */}
        <FailedOrders base={url + 'failed-orders/'} canRetry={manage} hideEmpty={false} onChanged={load} />
        {/* v1.53: the store's backups (ours: any time, links work on our panel only) + the monthly fee (off by default) */}
        {manage && <div className="ags-box"><StoreExports base={url + 'exports/'} platform /></div>}
        <div className="ags-box"><StoreFee base={url + 'fee/'} fee={store.fee} reseller={username} canEdit={can('agency.accounting')} onChanged={load} /></div>
        <p className="text-xs text-muted">{s.manage_note}</p>
      </>}
    </div>
  )
}

const CSS = `
.ags-empty { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px; }
.ags-head { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.ags-pill { font-size: 12px; font-weight: 800; padding: 2px 10px; border-radius: 999px; color: var(--c-muted-fg);
  background: color-mix(in srgb, var(--c-text-muted) 16%, transparent); }
.ags-pill[data-st="active"] { color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 16%, transparent); }
.ags-pill[data-st="suspended"] { color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 16%, transparent); }
.ags-pill[data-st="closed"] { color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 14%, transparent); }
.ags-reach { font-size: 12.5px; color: var(--c-warning-fg); margin: 0; }
.ags-reach.ok { color: var(--c-success-fg); }
.ags-st { display: flex; flex-wrap: wrap; gap: 6px; }
.ags-st-b { min-height: 44px; padding: 0 14px; border-radius: 12px; border: 1px solid var(--c-border); background: var(--c-bg);
  font-size: 13px; font-weight: 700; color: var(--c-text); cursor: pointer; }
.ags-st-b.on { border-color: var(--c-primary); color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 10%, var(--c-bg)); }
.ags-st-b:disabled { cursor: default; opacity: .7; }
.ags-form { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); gap: 10px; align-items: end; }
.ags-f { display: flex; flex-direction: column; gap: 4px; font-size: 12px; font-weight: 700; min-width: 0; }
.ags-chk { display: flex; align-items: center; gap: 8px; font-size: 13px; min-height: 44px; }
.ags-save { min-height: 44px; }
.ags-doms { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; font-size: 13px; }
.ags-box { padding: 12px 14px; border-radius: 14px; border: 1px solid var(--c-border); min-width: 0; }
@media (max-width: 767px) { .ags-f .input { font-size: 16px; min-height: 44px; } }
`
