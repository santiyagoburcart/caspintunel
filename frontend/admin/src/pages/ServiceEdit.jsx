// /panel/services/:id — full service edit & details (Stitch: "ویرایش کامل
// سرویس - دسکتاپ" / "- نسخه موبایل"). Live PasarGuard data; edits go to the
// panel first (PATCH /admin/services/<id>/ → panel → our DB → re-sync).
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useAuth } from '../lib/auth'
import { digits, gb, jalali, relTime } from '../lib/format'
import { copyToClipboard } from '../lib/clipboard'
import { useServiceActions } from '../lib/serviceActions'
import { Spinner } from '../components/ui'
import { useToast } from '../components/Toast'
import { useConfirm } from '../components/ConfirmDialog'
import { DateRangeModal, DRP_CSS } from '../components/DateRangePicker'

const GB = 1024 ** 3
const DAY = 86400

const T = {
  fa: {
    crumbs_services: 'سرویس‌ها', title: 'ویرایش کامل مشخصات سرویس', m_title: 'ویرایش مشخصات سرویس',
    srv_id: 'شناسه سرویس', last_sync: 'آخرین همگام‌سازی', never: 'هرگز',
    reset_form: 'بازنشانی به مقادیر اولیه', save: 'ذخیره تغییرات سرویس', save_final: 'ذخیره تغییرات نهایی', cancel: 'انصراف و بازگشت', m_cancel: 'انصراف',
    saved: 'تغییرات روی پنل اعمال و همگام‌سازی شد', nothing: 'تغییری برای ذخیره وجود ندارد',
    live_down: 'دریافت اطلاعات زنده از پنل ممکن نشد؛ آخرین داده‌های همگام‌شده نمایش داده می‌شود و ویرایش غیرفعال است.',
    username: 'نام کاربری سرویس (Username)', username_hint: 'شناسهٔ کانفیگ ساب برای اتصال کلاینت — روی پنل قابل تغییر نیست',
    buyer: 'کاربر خریدار (Purchaser Account)', buyer_hint: 'حساب سایت / ربات خریدار', buyer_orders: 'سفارش‌ها',
    plan: 'نام پلن خریداری‌شده (Plan Name)', plan_hint: 'پلنی که این اکانت بر اساس آن ساخته/تمدید شده', manual: 'دستی',
    panel: 'نام پنل متصل (Connected Core Panel)', panel_hint: 'سرور PasarGuard و ادمین سازندهٔ اکانت',
    expiry: 'تاریخ انقضا / مدت اعتبار (Expiry Date)', expiry_hint: 'تاریخ جلالی — پایان همان روز به وقت تهران',
    pick_date: 'انتخاب تاریخ', no_expiry: 'بدون انقضا', days_left: '{n} روز باقی‌مانده', expired_ago: 'منقضی شده',
    plus30: '+۳۰ روز', clear_expiry: 'بدون انقضا',
    onhold_days: 'مدت اعتبار پس از اولین اتصال (روز)', onhold_hint: 'زمان از اولین اتصال کاربر شروع می‌شود',
    onhold_deadline: 'مهلت اولین اتصال',
    status: 'وضعیت سرویس (Status & Connection)', status_hint: 'با غیرفعال کردن، اتصال کاربر بلافاصله قطع می‌شود',
    st_active: 'فعال', st_on_hold: 'در انتظار اتصال', st_disabled: 'غیرفعال', st_expired: 'منقضی', st_limited: 'اتمام حجم', st_pending: 'در حال ساخت',
    online: 'متصل به شبکه', offline: 'آفلاین',
    quota: 'سقف حجم ترافیک (Data Limit & Traffic Quota)', quota_sub: 'مقدار کل مجاز برای دانلود و آپلود کاربر',
    gb_unit: 'گیگابایت (GB)', gb_short: 'گیگابایت', unlimited: 'نامحدود', used_of: 'مصرف: {u} از {l}', pct: '٪',
    groups: 'گروه‌های نود / سطح دسترسی تانل (Node & Tunnel Groups)', select_all: 'انتخاب همه گروه‌ها', clear_all: 'حذف همه',
    groups_loading: 'دریافت گروه‌های پنل…', groups_fail: 'فهرست گروه‌ها در دسترس نیست — فقط شناسه‌ها نمایش داده می‌شود', group_n: 'گروه #{id}',
    note: 'یادداشت پنل (Note)', note_hint: 'فقط برای ادمین‌ها روی پنل PasarGuard نمایش داده می‌شود',
    sub: 'لینک فعال سابسکریپشن کاربر (Subscription URL)', copy: 'کپی', copied: 'کپی شد',
    live_h: 'اطلاعات زندهٔ پنل', f_online: 'آخرین اتصال', f_created: 'ساخت روی پنل', f_edit: 'آخرین ویرایش روی پنل',
    f_lifetime: 'مصرف کل عمر اکانت', f_reset: 'بازنشانی خودکار حجم', f_hwid: 'محدودیت دستگاه (HWID)', f_ours: 'ثبت در سیستم ما',
    f_source: 'منبع', none: '—',
    actions_h: 'عملیات سرویس', act_reset: 'ریست حجم مصرفی', act_revoke: 'تغییر لینک اشتراک', act_delete: 'حذف دائمی سرویس',
    raw_h: 'پاسخ خام پنل (PasarGuard)', foot: 'تمامی تغییرات ابتدا روی پنل PasarGuard اعمال و سپس در سیستم ما همگام‌سازی می‌شود.',
    not_found: 'سرویس پیدا نشد', back: 'بازگشت به سرویس‌ها', owner: 'مالک و خریدار سرویس',
    plan_short: 'نام پلن خریداری‌شده', panel_short: 'پنل و میزبان سرور', usage_short: 'مصرف پهنای باند',
    settings_h: 'تنظیمات اصلی سرویس', limit_short: 'محدودیت حجم (GB)', status_short: 'وضعیت سرویس',
    expiry_short: 'تاریخ انقضا و مهلت', groups_short: 'گروه‌ها و پروتکل‌های مجاز', sub_short: 'لینک اتصال مستقیم سابسکریپشن',
    disable_t: 'غیرفعال کردن سرویس', disable_btn: 'بله، ذخیره و غیرفعال کن',
    disable_m: 'با ذخیرهٔ این تغییرات، سرویس غیرفعال می‌شود و اتصال کاربر بلافاصله قطع خواهد شد.',
    changes_h: 'تغییرات:', src_site: 'سایت', src_bot: 'ربات', src_admin: 'ادمین',
  },
  en: {
    crumbs_services: 'Services', title: 'Full service edit', m_title: 'Edit service',
    srv_id: 'Service ID', last_sync: 'Last sync', never: 'never',
    reset_form: 'Reset to initial values', save: 'Save service changes', save_final: 'Save final changes', cancel: 'Cancel & go back', m_cancel: 'Cancel',
    saved: 'Changes applied on the panel and synced', nothing: 'Nothing to save',
    live_down: 'Live panel data is unavailable; showing the last synced data — editing is disabled.',
    username: 'Service username', username_hint: 'Subscription config id used by clients — cannot be renamed on the panel',
    buyer: 'Purchaser account', buyer_hint: 'Site / bot account that owns it', buyer_orders: 'Orders',
    plan: 'Purchased plan', plan_hint: 'The plan this account was created/renewed from', manual: 'manual',
    panel: 'Connected core panel', panel_hint: 'PasarGuard server and the admin that created the account',
    expiry: 'Expiry date', expiry_hint: 'Jalali date — end of that day, Tehran time',
    pick_date: 'Pick a date', no_expiry: 'No expiry', days_left: '{n} days left', expired_ago: 'Expired',
    plus30: '+30 days', clear_expiry: 'No expiry',
    onhold_days: 'Validity after first connection (days)', onhold_hint: 'The clock starts on the user’s first connection',
    onhold_deadline: 'First-connection deadline',
    status: 'Service status', status_hint: 'Disabling cuts the user’s connection immediately',
    st_active: 'Active', st_on_hold: 'On hold', st_disabled: 'Disabled', st_expired: 'Expired', st_limited: 'Data used up', st_pending: 'Provisioning',
    online: 'Online', offline: 'Offline',
    quota: 'Data limit & traffic quota', quota_sub: 'Total upload + download allowed for the user',
    gb_unit: 'Gigabytes (GB)', gb_short: 'GB', unlimited: 'Unlimited', used_of: 'Used {u} of {l}', pct: '%',
    groups: 'Node & tunnel groups', select_all: 'Select all groups', clear_all: 'Clear',
    groups_loading: 'Loading panel groups…', groups_fail: 'Group list unavailable — showing ids only', group_n: 'Group #{id}',
    note: 'Panel note', note_hint: 'Only visible to admins on the PasarGuard panel',
    sub: 'Active subscription URL', copy: 'Copy', copied: 'Copied',
    live_h: 'Live panel data', f_online: 'Last seen', f_created: 'Created on panel', f_edit: 'Last edited on panel',
    f_lifetime: 'Lifetime usage', f_reset: 'Data reset strategy', f_hwid: 'Device limit (HWID)', f_ours: 'Created in our system',
    f_source: 'Source', none: '—',
    actions_h: 'Service actions', act_reset: 'Reset usage', act_revoke: 'Revoke subscription link', act_delete: 'Delete service permanently',
    raw_h: 'Raw panel response (PasarGuard)', foot: 'Every change is applied on the PasarGuard panel first, then synced into our system.',
    not_found: 'Service not found', back: 'Back to services', owner: 'Owner & purchaser',
    plan_short: 'Purchased plan', panel_short: 'Panel & host', usage_short: 'Bandwidth usage',
    settings_h: 'Main service settings', limit_short: 'Data limit (GB)', status_short: 'Service status',
    expiry_short: 'Expiry & validity', groups_short: 'Allowed groups', sub_short: 'Direct subscription link',
    disable_t: 'Disable service', disable_btn: 'Yes, save and disable',
    disable_m: 'Saving these changes disables the service and cuts the user’s connection immediately.',
    changes_h: 'Changes:', src_site: 'site', src_bot: 'bot', src_admin: 'admin',
  },
}

const P = {
  edit: 'M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10',
  user: 'M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z',
  users: 'M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94 3.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971 5.971 0 00-.94 3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zm-13.5 0a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z',
  lock: 'M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z',
  cal: 'M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5',
  copy: 'M15.75 17.25v3.375c0 .621-.504 1.125-1.125 1.125h-9.75a1.125 1.125 0 01-1.125-1.125V7.875c0-.621.504-1.125 1.125-1.125H6.75a9.06 9.06 0 011.5.124m7.5 10.376h3.375c.621 0 1.125-.504 1.125-1.125V11.25c0-4.46-3.243-8.161-7.5-8.876a9.06 9.06 0 00-1.5-.124H9.375c-.621 0-1.125.504-1.125 1.125v3.5m7.5 10.375H9.375a1.125 1.125 0 01-1.125-1.125v-9.25m12 6.625v-1.875a3.375 3.375 0 00-3.375-3.375h-1.5a1.125 1.125 0 01-1.125-1.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25',
  check: 'M4.5 12.75l6 6 9-13.5',
  back: 'M8.25 4.5l7.5 7.5-7.5 7.5',
  refresh: 'M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99',
  link: 'M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244',
  trash: 'M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0',
  server: 'M21.75 17.25v-.228a4.5 4.5 0 00-.12-1.03l-2.268-9.64a3.375 3.375 0 00-3.285-2.602H7.923a3.375 3.375 0 00-3.285 2.602l-2.268 9.64a4.5 4.5 0 00-.12 1.03v.228m19.5 0a3 3 0 01-3 3H5.25a3 3 0 01-3-3m19.5 0a3 3 0 00-3-3H5.25a3 3 0 00-3 3m16.5 0h.008v.008h-.008v-.008zm-3 0h.008v.008h-.008v-.008z',
  tag: 'M9.568 3H5.25A2.25 2.25 0 003 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 005.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 009.568 3z',
  warn: 'M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z',
}
function Ico({ d, w = 18, sw = 1.8 }) {
  return (
    <svg viewBox="0 0 24 24" width={w} height={w} fill="none" stroke="currentColor" strokeWidth={sw}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>
  )
}

const EDITABLE = ['active', 'on_hold', 'disabled']
const QUICK_GB = [5, 50, 100, 200, 250, 500]
const tone = (st) => ({ active: 'success', on_hold: 'warning', disabled: 'danger', expired: 'danger', limited: 'warning' }[st] || 'text-muted')

const pad = (n) => String(n).padStart(2, '0')
/** local calendar date (YYYY-MM-DD) of an ISO datetime */
const isoDay = (v) => {
  if (!v) return ''
  const d = new Date(v)
  return Number.isNaN(d.getTime()) ? '' : `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
const roundGb = (bytes) => (bytes ? String(Math.round((bytes / GB) * 100) / 100) : '0')

/** form state from the live panel user (falls back to our row) */
function formFrom(d) {
  const raw = d.panel_raw || {}
  const limit = raw.data_limit ?? d.data_limit ?? 0
  const hold = raw.on_hold_expire_duration ?? d.on_hold_duration
  return {
    status: raw.status || d.status,
    unlimited: !limit,
    limitGb: limit ? roundGb(limit) : '',
    expire: isoDay(raw.expire !== undefined ? raw.expire : d.expire_at),
    onHoldDays: hold ? String(Math.round(hold / DAY)) : '',
    groupIds: [...(raw.group_ids || [])].sort((a, b) => a - b),
    note: raw.note || '',
  }
}

/** PATCH body with only what changed */
function diff(init, f) {
  const out = {}
  if (f.status !== init.status && EDITABLE.includes(f.status)) out.status = f.status
  const lim = f.unlimited ? 0 : Number(f.limitGb || 0)
  const lim0 = init.unlimited ? 0 : Number(init.limitGb || 0)
  if (lim !== lim0) out.data_limit_gb = lim
  if (f.status === 'on_hold') {
    if (f.onHoldDays !== init.onHoldDays || out.status) out.on_hold_days = Number(f.onHoldDays || 0)
  } else if (f.expire !== init.expire) {
    out.expire_date = f.expire || null
  }
  if (JSON.stringify(f.groupIds) !== JSON.stringify(init.groupIds)) out.group_ids = f.groupIds
  if (f.note !== init.note) out.note = f.note
  return out
}

export default function ServiceEdit() {
  const { id } = useParams()
  const { t, lang } = useI18n()
  const s = T[lang] || T.fa
  const { can } = useAuth()
  const toast = useToast()
  const confirm = useConfirm()
  const navigate = useNavigate()
  const actions = useServiceActions()

  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [notFound, setNotFound] = useState(false)
  const [init, setInit] = useState(null)
  const [f, setF] = useState(null)
  const [groups, setGroups] = useState(null) // [{id,name}] | 'fail'
  const [saving, setSaving] = useState(false)
  const [pickOpen, setPickOpen] = useState(false)
  const [copied, setCopied] = useState(false)

  const applyData = (data) => {
    setD(data)
    const fi = formFrom(data)
    setInit(fi); setF(fi)
  }

  useEffect(() => {
    api.get(`/admin/services/${id}/panel-detail/`)
      .then((r) => applyData(r.data))
      .catch((e) => { if (e?.response?.status === 404) setNotFound(true); else setErr(apiError(e)) })
  }, [id])

  useEffect(() => {
    if (!d?.panel_id) return
    api.get(`/admin/panels/${d.panel_id}/groups/`)
      .then((r) => setGroups(r.data.groups || []))
      .catch(() => setGroups('fail'))
  }, [d?.panel_id])

  const canEdit = can('services.manage') && !!d?.panel_raw
  const changes = useMemo(() => (init && f ? diff(init, f) : {}), [init, f])
  const dirty = Object.keys(changes).length > 0

  if (notFound) {
    return (
      <div className="sed"><style>{CSS}</style>
        <div className="card sed-empty">{s.not_found}<Link to="/services" className="btn-ghost text-sm">{s.back}</Link></div>
      </div>
    )
  }
  if (!d || !f) {
    return err
      ? <div className="sed"><style>{CSS}</style><div className="card sed-empty sed-err">{err}</div></div>
      : <div className="grid place-items-center py-16"><Spinner /></div>
  }

  const raw = d.panel_raw || {}
  const set = (k) => (v) => setF((p) => ({ ...p, [k]: v }))
  const used = raw.used_traffic ?? d.data_used ?? 0
  const limitBytes = f.unlimited ? 0 : Number(f.limitGb || 0) * GB
  const pct = limitBytes ? Math.min(100, Math.round((used / limitBytes) * 100)) : 0
  const statusLabel = (st) => s[`st_${st}`] || st
  const expireMs = f.expire ? new Date(`${f.expire}T23:59:59`).getTime() : null
  const daysLeft = expireMs ? Math.ceil((expireMs - Date.now()) / (DAY * 1000)) : null
  const planName = (lang === 'fa' ? d.plan : d.plan_en) || d.plan
  const groupList = Array.isArray(groups)
    ? [...groups, ...f.groupIds.filter((g) => !groups.some((x) => x.id === g)).map((g) => ({ id: g, name: s.group_n.replace('{id}', g) }))]
    : f.groupIds.map((g) => ({ id: g, name: s.group_n.replace('{id}', g) }))
  const toggleGroup = (gid) => set('groupIds')(
    f.groupIds.includes(gid) ? f.groupIds.filter((x) => x !== gid) : [...f.groupIds, gid].sort((a, b) => a - b))
  const addDays = (n) => {
    const base = f.expire && expireMs > Date.now() ? new Date(`${f.expire}T12:00:00`) : new Date()
    base.setDate(base.getDate() + n)
    set('expire')(`${base.getFullYear()}-${pad(base.getMonth() + 1)}-${pad(base.getDate())}`)
  }

  const save = async () => {
    if (!dirty) { toast.success(s.nothing); return }
    const run = async () => {
      const { data } = await api.patch(`/admin/services/${d.id}/`, changes)
      applyData(data)
    }
    if (changes.status === 'disabled') {
      const ok = await confirm({
        tone: 'danger', icon: 'ban', badge: 'services.manage', title: s.disable_t,
        targetLabel: `${s.srv_id}:`, targetId: `SRV-${d.id}`, message: <>{s.disable_m} <strong>{d.panel_username}</strong></>,
        confirmLabel: s.disable_btn, action: run,
      })
      if (ok) toast.success(s.saved)
      return
    }
    setSaving(true)
    try { await run(); toast.success(s.saved) } catch (e) { toast.error(apiError(e)) } finally { setSaving(false) }
  }
  const doAction = async (kind) => {
    try {
      const res = await actions[kind](d)
      if (!res) return
      if (kind === 'remove') { navigate('/services'); return }
      const r = await api.get(`/admin/services/${d.id}/panel-detail/`)
      applyData(r.data)
    } catch (e) { toast.error(apiError(e)) }
  }
  const copySub = async () => {
    if (await copyToClipboard(d.subscription_url)) { setCopied(true); setTimeout(() => setCopied(false), 1500) }
  }

  /* ---------------- shared field blocks ---------------- */
  const StatusSeg = (
    <div className="sed-seg" role="radiogroup" aria-label={s.status}>
      {EDITABLE.map((st) => (
        <button key={st} type="button" role="radio" aria-checked={f.status === st} disabled={!canEdit}
          className={'sed-seg-btn' + (f.status === st ? ` on sed-tone-${tone(st)}` : '')}
          onClick={() => set('status')(st)}>
          <i />{statusLabel(st)}
        </button>
      ))}
      {!EDITABLE.includes(f.status) && (
        <span className={`sed-seg-btn on sed-tone-${tone(f.status)}`} aria-current="true"><i />{statusLabel(f.status)}</span>
      )}
    </div>
  )
  const ExpiryField = f.status === 'on_hold' ? (
    <div className="sed-row2">
      <input className="input sed-mono" dir="ltr" type="number" min="1" max="3650" value={f.onHoldDays}
        disabled={!canEdit} onChange={(e) => set('onHoldDays')(e.target.value)} aria-label={s.onhold_days} />
      <span className="sed-chip">{f.onHoldDays ? `${digits(f.onHoldDays, lang)} ${lang === 'fa' ? 'روز' : 'days'}` : '—'}</span>
    </div>
  ) : (
    <div className="sed-row2">
      <button type="button" className="input sed-date" disabled={!canEdit} onClick={() => setPickOpen(true)}>
        <Ico d={P.cal} w={16} />
        <span className="sed-mono">{f.expire ? jalali(`${f.expire}T12:00:00`, false, lang) : s.no_expiry}</span>
      </button>
      <span className={'sed-chip' + (daysLeft != null && daysLeft < 0 ? ' sed-chip--bad' : '')}>
        {daysLeft == null ? s.no_expiry : daysLeft < 0 ? s.expired_ago : s.days_left.replace('{n}', digits(daysLeft, lang))}
      </span>
    </div>
  )
  const ExpiryTools = f.status !== 'on_hold' && canEdit && (
    <div className="sed-mini-acts">
      <button type="button" onClick={() => addDays(30)}>{s.plus30}</button>
      {f.expire && <button type="button" onClick={() => set('expire')('')}>{s.clear_expiry}</button>}
    </div>
  )
  const LimitInput = (
    <div className="sed-limit-in">
      <input className="input sed-mono sed-gb" dir="ltr" type="number" min="0" step="0.5"
        value={f.unlimited ? '' : f.limitGb} placeholder={f.unlimited ? '∞' : '0'} disabled={!canEdit || f.unlimited}
        onChange={(e) => set('limitGb')(e.target.value)} aria-label={s.gb_unit} />
      <label className="sed-unl">
        <input type="checkbox" checked={f.unlimited} disabled={!canEdit}
          onChange={(e) => setF((p) => ({ ...p, unlimited: e.target.checked, limitGb: e.target.checked ? '' : (init.limitGb || '50') }))} />
        {s.unlimited}
      </label>
    </div>
  )
  const UsageBar = (
    <div className="sed-usage">
      <div className="sed-usage-top">
        <span>{s.used_of.replace('{u}', `${digits(gb(used), lang)} GB`).replace('{l}', limitBytes ? `${digits(gb(limitBytes), lang)} GB` : s.unlimited)}</span>
        {limitBytes > 0 && <b className="sed-mono">{digits(pct, lang)}{s.pct}</b>}
      </div>
      <div className="sed-bar"><i style={{ width: `${limitBytes ? Math.max(pct, 2) : 0}%` }} /></div>
    </div>
  )
  const Groups = (
    <div className="sed-groups">
      {groups === null && <span className="sed-hint">{s.groups_loading}</span>}
      {groups === 'fail' && <span className="sed-hint">{s.groups_fail}</span>}
      {groupList.map((g) => {
        const on = f.groupIds.includes(g.id)
        return (
          <button key={g.id} type="button" disabled={!canEdit} aria-pressed={on}
            className={'sed-group' + (on ? ' on' : '')} onClick={() => toggleGroup(g.id)}>
            <i />{g.name}
          </button>
        )
      })}
    </div>
  )
  const SubField = (
    <div className="sed-sub">
      <button type="button" className="sed-copy" onClick={copySub} disabled={!d.subscription_url} aria-label={s.copy}>
        {copied ? <Ico d={P.check} w={16} /> : <Ico d={P.copy} w={16} />}<span className="sed-copy-t">{copied ? s.copied : s.copy}</span>
      </button>
      <code dir="ltr">{d.subscription_url || '—'}</code>
    </div>
  )

  const onlineNow = d.is_online
  const liveRows = [
    [s.f_online, raw.online_at || d.online_at ? relTime(raw.online_at || d.online_at, lang) : s.none],
    [s.last_sync, d.last_synced_at ? relTime(d.last_synced_at, lang) : s.never],
    [s.f_created, raw.created_at ? jalali(raw.created_at, true, lang) : s.none],
    [s.f_edit, raw.edit_at ? jalali(raw.edit_at, true, lang) : s.none],
    [s.f_lifetime, raw.lifetime_used_traffic != null ? `${digits(gb(raw.lifetime_used_traffic), lang)} GB` : s.none],
    [s.f_reset, raw.data_limit_reset_strategy || s.none],
    [s.f_hwid, raw.hwid_limit ?? s.unlimited],
    [s.onhold_deadline, raw.on_hold_timeout ? jalali(raw.on_hold_timeout, true, lang) : s.none],
    [s.f_ours, `${jalali(d.created_at, true, lang)} · ${s[`src_${d.source}`] || d.source}`],
  ]

  const actionBtns = can('services.manage') && (
    <div className="sed-actions">
      <button type="button" className="sed-act sed-act--success" onClick={() => doAction('reset')}><Ico d={P.refresh} w={16} />{s.act_reset}</button>
      <button type="button" className="sed-act sed-act--warning" onClick={() => doAction('revoke')}><Ico d={P.link} w={16} />{s.act_revoke}</button>
      {can('services.delete') && (
        <button type="button" className="sed-act sed-act--danger" onClick={() => doAction('remove')}><Ico d={P.trash} w={16} />{s.act_delete}</button>
      )}
    </div>
  )

  return (
    <div className="sed">
      <style>{CSS + DRP_CSS}</style>

      {/* ---------- mobile header (Stitch mobile) ---------- */}
      <div className="sed-mhead">
        <button type="button" className="sed-mback" onClick={() => navigate('/services')} aria-label={s.back}>
          <span className="sed-flip"><Ico d={P.back} w={18} sw={2.2} /></span>
        </button>
        <div className="sed-mhead-txt">
          <div className="sed-mhead-row"><b>{s.m_title}</b><span className="sed-idchip">SRV-{d.id}#</span></div>
          <span>{d.panel_name || '—'} · {d.panel_username}</span>
        </div>
      </div>

      {/* ---------- mobile summary card ---------- */}
      <div className="card sed-msum">
        <div className="sed-msum-top">
          <span className="sed-avatar">{(d.user || '?').slice(0, 2).toUpperCase()}</span>
          <div className="min-w-0">
            <span className="sed-lbl">{s.owner}</span>
            <b className="block truncate">{d.user}</b>
            {d.user_telegram && <span className="sed-hint" dir="ltr">@{d.user_telegram}</span>}
          </div>
          <span className={`sed-pill sed-tone-${tone(d.status)}`}><i className={onlineNow ? 'blink' : ''} />{statusLabel(d.status)}</span>
        </div>
        <div className="sed-msum-grid">
          <div><span className="sed-lbl">{s.plan_short}</span><b>{planName || s.manual}</b></div>
          <div><span className="sed-lbl">{s.panel_short}</span><b>{d.panel_name || '—'}</b></div>
        </div>
        {UsageBar}
      </div>

      <div className="card sed-card">
        {/* ---------- desktop header ---------- */}
        <div className="sed-head">
          <div className="sed-head-l">
            <span className="sed-head-ico"><Ico d={P.edit} w={22} /></span>
            <div className="min-w-0">
              <div className="sed-head-title">
                <h1>{s.title}</h1>
                <span className={`sed-pill sed-tone-${tone(d.status)}`}>
                  <i className={onlineNow ? 'blink' : ''} />{statusLabel(d.status)} / {onlineNow ? s.online : s.offline}
                </span>
              </div>
              <p className="sed-head-sub">
                <Link to="/services" className="sed-crumb">{s.crumbs_services}</Link> · {s.srv_id}: <span className="sed-mono" dir="ltr">SRV-{d.id}</span>
                {' | '}{s.last_sync}: {d.last_synced_at ? relTime(d.last_synced_at, lang) : s.never}
              </p>
            </div>
          </div>
          <div className="sed-head-acts">
            <button type="button" className="btn-ghost text-sm" onClick={() => setF(init)} disabled={!dirty || saving}>{s.reset_form}</button>
            <button type="button" className="btn-primary text-sm sed-save" onClick={save} disabled={!canEdit || !dirty || saving}>
              {saving ? <span className="sed-spin" /> : <Ico d={P.check} w={16} sw={2.2} />}{s.save}
            </button>
          </div>
        </div>

        {!d.panel_raw && <div className="sed-warn"><Ico d={P.warn} w={16} />{s.live_down}</div>}

        <div className="sed-body">
          <h2 className="sed-mobile-h">{s.settings_h}</h2>

          {/* row 1: username · buyer · plan */}
          <div className="sed-grid3">
            <label className="sed-fld">
              <span className="sed-lbl">{s.username} <span className="sed-req">*</span></span>
              <div className="sed-ro"><Ico d={P.user} w={16} /><span className="sed-mono" dir="ltr">{d.panel_username}</span><span className="sed-lock"><Ico d={P.lock} w={14} /></span></div>
              <span className="sed-hint">{s.username_hint}</span>
            </label>
            <div className="sed-fld sed-desk">
              <span className="sed-lbl">{s.buyer}</span>
              <div className="sed-ro"><Ico d={P.users} w={16} />
                <span className="truncate">{d.user}{d.user_telegram ? <span className="sed-muted" dir="ltr"> (@{d.user_telegram})</span> : null}</span>
                {d.user_id && <Link to={`/users/${d.user_id}/orders`} className="sed-ro-link">{s.buyer_orders}</Link>}
              </div>
              <span className="sed-hint">{s.buyer_hint}{d.user_phone ? <> · <span dir="ltr">{d.user_phone}</span></> : null}</span>
            </div>
            <div className="sed-fld sed-desk">
              <span className="sed-lbl">{s.plan}</span>
              <div className="sed-ro"><Ico d={P.tag} w={16} /><span className="truncate">{planName || s.manual}</span></div>
              <span className="sed-hint">{s.plan_hint}</span>
            </div>
          </div>

          {/* row 2: panel · expiry · status */}
          <div className="sed-grid3">
            <div className="sed-fld sed-desk">
              <span className="sed-lbl">{s.panel}</span>
              <div className="sed-ro"><Ico d={P.server} w={16} /><span className="truncate">{d.panel_name || '—'}{raw.admin?.username ? <span className="sed-muted"> · {raw.admin.username}</span> : null}</span></div>
              <span className="sed-hint">{s.panel_hint}</span>
            </div>
            <div className="sed-fld sed-order-expiry">
              <span className="sed-lbl">{f.status === 'on_hold' ? s.onhold_days : s.expiry}</span>
              {ExpiryField}
              <span className="sed-hint">{f.status === 'on_hold' ? s.onhold_hint : s.expiry_hint}</span>
              {ExpiryTools}
            </div>
            <div className="sed-fld">
              <span className="sed-lbl">{s.status}</span>
              {StatusSeg}
              <span className="sed-hint">{s.status_hint}</span>
            </div>
          </div>

          {/* data limit */}
          <div className="sed-quota">
            <div className="sed-quota-head">
              <div><b>{s.quota}</b><span className="sed-hint">{s.quota_sub}</span></div>
            </div>
            <div className="sed-quota-body">
              <div className="sed-quota-in"><span className="sed-lbl">{s.gb_unit}</span>{LimitInput}</div>
              <div className="sed-ticks">
                {QUICK_GB.map((g) => (
                  <button key={g} type="button" disabled={!canEdit}
                    className={'sed-tick' + (!f.unlimited && Number(f.limitGb) === g ? ' on' : '')}
                    onClick={() => setF((p) => ({ ...p, unlimited: false, limitGb: String(g) }))}>
                    {digits(g, lang)} {s.gb_short}
                  </button>
                ))}
              </div>
            </div>
            <div className="sed-desk">{UsageBar}</div>
          </div>

          {/* groups */}
          <div className="sed-fld">
            <div className="sed-groups-head">
              <span className="sed-lbl">{s.groups}</span>
              {canEdit && Array.isArray(groups) && groups.length > 0 && (
                f.groupIds.length === groups.length
                  ? <button type="button" className="sed-link" onClick={() => set('groupIds')([])}>{s.clear_all}</button>
                  : <button type="button" className="sed-link" onClick={() => set('groupIds')(groups.map((g) => g.id).sort((a, b) => a - b))}>{s.select_all}</button>
              )}
            </div>
            {Groups}
          </div>

          {/* note */}
          <label className="sed-fld">
            <span className="sed-lbl">{s.note}</span>
            <textarea className="input sed-note" rows={2} value={f.note} disabled={!canEdit} maxLength={500}
              onChange={(e) => set('note')(e.target.value)} />
            <span className="sed-hint">{s.note_hint}</span>
          </label>

          {/* subscription url */}
          <div className="sed-fld sed-sep">
            <span className="sed-lbl">{s.sub}</span>
            {SubField}
          </div>

          {/* live panel info + actions */}
          <div className="sed-two">
            <div className="sed-box">
              <b className="sed-box-h">{s.live_h}</b>
              <div className="sed-kv">
                {liveRows.map(([k, v]) => <div key={k}><span>{k}</span><b>{v}</b></div>)}
              </div>
            </div>
            <div className="sed-box">
              <b className="sed-box-h">{s.actions_h}</b>
              {actionBtns}
            </div>
          </div>

          {d.panel_raw && (
            <details className="sed-raw">
              <summary>{s.raw_h}</summary>
              <pre dir="ltr">{JSON.stringify(d.panel_raw, null, 2)}</pre>
            </details>
          )}
        </div>

        {/* desktop footer */}
        <div className="sed-foot">
          <span className="sed-hint">{s.foot}</span>
          <div className="sed-foot-acts">
            <button type="button" className="btn-ghost text-sm" onClick={() => navigate('/services')}>{s.cancel}</button>
            <button type="button" className="btn-primary text-sm sed-save" onClick={save} disabled={!canEdit || !dirty || saving}>
              {saving ? <span className="sed-spin" /> : null}{s.save_final}
            </button>
          </div>
        </div>
      </div>

      {/* mobile sticky save bar */}
      <div className="sed-mbar">
        <button type="button" className="btn-primary sed-mbar-save" onClick={save} disabled={!canEdit || !dirty || saving}>
          {saving ? <span className="sed-spin" /> : <Ico d={P.check} w={18} sw={2.2} />}{s.save}
        </button>
        <button type="button" className="btn-ghost sed-mbar-cancel" onClick={() => (dirty ? setF(init) : navigate('/services'))}>{s.m_cancel}</button>
      </div>

      {pickOpen && (
        <DateRangeModal open single initial={f.expire} clearLabel={s.clear_expiry}
          onClose={() => setPickOpen(false)}
          onApply={({ from }) => set('expire')(from || '')} />
      )}
    </div>
  )
}

const CSS = `
.sed { display: flex; flex-direction: column; gap: 14px; padding-bottom: 8px; }
.sed-mono { font-family: 'JetBrains Mono', ui-monospace, monospace; }
.sed-muted { color: var(--c-text-muted); font-weight: 400; }
.sed-empty { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 40px 16px; color: var(--c-text-muted); }
.sed-err { color: var(--c-danger); }
.sed-card { padding: 0; overflow: hidden; }

/* header */
.sed-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap;
  padding: 22px 24px; border-bottom: 1px solid var(--c-border);
  background: color-mix(in srgb, var(--c-text-muted) 4%, transparent); }
.sed-head-l { display: flex; align-items: center; gap: 14px; min-width: 0; }
.sed-head-ico { width: 48px; height: 48px; flex-shrink: 0; border-radius: 14px; display: grid; place-items: center;
  color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 12%, transparent); }
.sed-head-title { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.sed-head-title h1 { font-size: 18px; font-weight: 800; }
.sed-head-sub { margin-top: 4px; font-size: 12px; color: var(--c-text-muted); }
.sed-crumb { color: var(--c-primary); font-weight: 600; }
.sed-crumb:hover { text-decoration: underline; }
.sed-head-acts, .sed-foot-acts { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.sed-save { display: inline-flex; align-items: center; gap: 8px; box-shadow: 0 6px 16px -6px color-mix(in srgb, var(--c-primary) 60%, transparent); }
.sed-save:disabled { opacity: .55; box-shadow: none; cursor: not-allowed; }
.sed-spin { width: 16px; height: 16px; border-radius: 50%; border: 2px solid rgba(255,255,255,.35); border-top-color: #fff; animation: sed-spin .7s linear infinite; }
@keyframes sed-spin { to { transform: rotate(360deg); } }
.sed-warn { display: flex; align-items: center; gap: 8px; margin: 16px 24px 0; padding: 10px 12px; border-radius: 10px; font-size: 12.5px;
  color: var(--c-warning); background: color-mix(in srgb, var(--c-warning) 10%, transparent); }

/* pills / tones */
.sed-pill { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 999px; font-size: 11.5px; font-weight: 700; white-space: nowrap; }
.sed-pill i, .sed-seg-btn i { width: 7px; height: 7px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
.sed-pill i.blink { animation: sed-blink 1.6s ease-in-out infinite; }
@keyframes sed-blink { 50% { opacity: .3; } }
.sed-tone-success { color: var(--c-success); background: color-mix(in srgb, var(--c-success) 13%, transparent); border-color: color-mix(in srgb, var(--c-success) 35%, transparent) !important; }
.sed-tone-warning { color: var(--c-warning); background: color-mix(in srgb, var(--c-warning) 13%, transparent); border-color: color-mix(in srgb, var(--c-warning) 35%, transparent) !important; }
.sed-tone-danger { color: var(--c-danger); background: color-mix(in srgb, var(--c-danger) 12%, transparent); border-color: color-mix(in srgb, var(--c-danger) 35%, transparent) !important; }
.sed-tone-text-muted { color: var(--c-text-muted); background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); }

/* body + fields */
.sed-body { padding: 24px; display: flex; flex-direction: column; gap: 22px; }
.sed-mobile-h { display: none; }
.sed-grid3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px 20px; }
.sed-fld { display: flex; flex-direction: column; gap: 7px; min-width: 0; }
.sed-lbl { font-size: 12.5px; font-weight: 700; color: var(--c-text); }
.sed-req { color: var(--c-danger); }
.sed-hint { font-size: 11.5px; color: var(--c-text-muted); line-height: 1.6; }
.sed-ro { display: flex; align-items: center; gap: 8px; min-height: 42px; padding: 0 12px; border-radius: 12px; font-size: 13.5px;
  border: 1px solid var(--c-border); background: color-mix(in srgb, var(--c-text-muted) 5%, transparent); color: var(--c-text); min-width: 0; }
.sed-ro > svg { color: var(--c-text-muted); flex-shrink: 0; }
.sed-ro .truncate { flex: 1; min-width: 0; }
.sed-lock { margin-inline-start: auto; color: var(--c-text-muted); opacity: .7; display: grid; }
.sed-ro-link { margin-inline-start: auto; flex-shrink: 0; font-size: 11.5px; font-weight: 700; color: var(--c-primary); }
.sed-row2 { display: flex; gap: 8px; align-items: stretch; }
.sed-row2 > .input { flex: 1; min-width: 0; }
.sed-date { display: flex; align-items: center; gap: 8px; text-align: start; cursor: pointer; }
.sed-date:disabled { cursor: not-allowed; opacity: .7; }
.sed-date svg { color: var(--c-text-muted); flex-shrink: 0; }
.sed-chip { display: inline-flex; align-items: center; justify-content: center; padding: 0 12px; border-radius: 12px; font-size: 12px; font-weight: 700;
  white-space: nowrap; color: var(--c-text-muted); background: color-mix(in srgb, var(--c-text-muted) 10%, transparent); min-width: 104px; }
.sed-chip--bad { color: var(--c-danger); background: color-mix(in srgb, var(--c-danger) 10%, transparent); }
.sed-mini-acts { display: flex; gap: 6px; flex-wrap: wrap; }
.sed-mini-acts button, .sed-link { font-size: 11.5px; font-weight: 700; color: var(--c-primary); padding: 3px 10px; border-radius: 999px;
  background: color-mix(in srgb, var(--c-primary) 10%, transparent); }
.sed-link { background: none; padding: 0; }
.sed-link:hover { text-decoration: underline; }

/* status segmented control */
.sed-seg { display: flex; gap: 4px; padding: 4px; border-radius: 12px; border: 1px solid var(--c-border); flex-wrap: wrap;
  background: color-mix(in srgb, var(--c-text-muted) 5%, transparent); }
.sed-seg-btn { flex: 1; display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 32px; padding: 4px 8px;
  border-radius: 9px; font-size: 12px; font-weight: 600; color: var(--c-text-muted); border: 1px solid transparent; white-space: nowrap; }
.sed-seg-btn i { opacity: .45; }
.sed-seg-btn.on i { opacity: 1; }
.sed-seg-btn.on { font-weight: 800; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.sed-seg-btn:disabled { cursor: not-allowed; }

/* quota box */
.sed-quota { display: flex; flex-direction: column; gap: 16px; padding: 20px; border-radius: 16px; border: 1px solid var(--c-border);
  background: color-mix(in srgb, var(--c-text-muted) 4%, transparent); }
.sed-quota-head b { display: block; font-size: 13.5px; font-weight: 800; margin-bottom: 2px; }
.sed-quota-body { display: flex; align-items: flex-end; gap: 20px; flex-wrap: wrap; }
.sed-quota-in { display: flex; flex-direction: column; gap: 7px; flex: 0 1 360px; min-width: 220px; }
.sed-limit-in { display: flex; align-items: center; gap: 10px; }
.sed-gb { flex: 1; text-align: center; font-size: 17px; font-weight: 800; min-height: 46px; }
.sed-unl { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 600; white-space: nowrap; cursor: pointer; }
.sed-unl input { accent-color: var(--c-primary); width: 16px; height: 16px; }
.sed-ticks { flex: 1; display: flex; justify-content: space-between; gap: 6px; flex-wrap: wrap; min-width: 260px; }
.sed-tick { font-size: 11.5px; color: var(--c-text-muted); padding: 6px 10px; border-radius: 999px; border: 1px dashed var(--c-border); white-space: nowrap; }
.sed-tick:hover:not(:disabled) { color: var(--c-primary); border-color: var(--c-primary); }
.sed-tick.on { color: #fff; background: var(--c-primary); border: 1px solid var(--c-primary); font-weight: 700; }
.sed-usage { display: flex; flex-direction: column; gap: 6px; }
.sed-usage-top { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; color: var(--c-text-muted); }
.sed-usage-top b { color: var(--c-primary); }
.sed-bar { height: 8px; border-radius: 999px; overflow: hidden; background: color-mix(in srgb, var(--c-text-muted) 16%, transparent); }
.sed-bar i { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--c-secondary), var(--c-primary)); transition: width .3s; }

/* groups */
.sed-groups-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.sed-groups { display: flex; flex-wrap: wrap; gap: 8px; }
.sed-group { display: inline-flex; align-items: center; gap: 7px; padding: 7px 14px; border-radius: 999px; font-size: 12.5px; font-weight: 600;
  color: var(--c-text-muted); border: 1px solid var(--c-border); background: transparent; transition: .15s; }
.sed-group i { width: 7px; height: 7px; border-radius: 50%; background: currentColor; opacity: .5; }
.sed-group.on { color: var(--c-primary); border-color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 8%, transparent); }
.sed-group.on i { background: var(--c-success); opacity: 1; }
.sed-group:disabled { cursor: not-allowed; }
.sed-note { resize: vertical; min-height: 60px; }

/* subscription url */
.sed-sep { padding-top: 20px; border-top: 1px solid var(--c-border); }
.sed-sub { display: flex; align-items: center; gap: 10px; min-height: 44px; padding: 0 12px; border-radius: 12px; border: 1px solid var(--c-border);
  background: color-mix(in srgb, var(--c-text-muted) 5%, transparent); min-width: 0; }
.sed-sub code { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12.5px; color: var(--c-text-muted); }
.sed-copy { display: inline-flex; align-items: center; gap: 6px; color: var(--c-text-muted); flex-shrink: 0; font-size: 12px; font-weight: 700; }
.sed-copy:hover { color: var(--c-primary); }
.sed-copy-t { display: none; }

/* live info + actions */
.sed-two { display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; }
.sed-box { display: flex; flex-direction: column; gap: 12px; padding: 16px; border-radius: 14px; border: 1px solid var(--c-border); }
.sed-box-h { font-size: 13px; font-weight: 800; }
.sed-kv { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 16px; }
.sed-kv > div { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.sed-kv span { font-size: 11px; color: var(--c-text-muted); }
.sed-kv b { font-size: 12.5px; font-weight: 700; overflow-wrap: anywhere; }
.sed-actions { display: flex; flex-direction: column; gap: 8px; }
.sed-act { display: flex; align-items: center; gap: 10px; min-height: 42px; padding: 0 14px; border-radius: 12px; font-size: 13px; font-weight: 700; border: 1px solid; transition: .15s; }
.sed-act--success { color: #0E9447; border-color: color-mix(in srgb, #11AB53 35%, transparent); background: color-mix(in srgb, #11AB53 7%, transparent); }
.sed-act--warning { color: #B45309; border-color: color-mix(in srgb, #D97706 35%, transparent); background: color-mix(in srgb, #D97706 7%, transparent); }
.sed-act--danger { color: #E11D48; border-color: color-mix(in srgb, #E11D48 35%, transparent); background: color-mix(in srgb, #E11D48 6%, transparent); }
.dark .sed-act--success { color: #34d399; } .dark .sed-act--warning { color: #fbbf24; } .dark .sed-act--danger { color: #fb7185; }
.sed-act:hover { filter: brightness(1.05); transform: translateY(-1px); }
.sed-raw summary { cursor: pointer; font-size: 12.5px; font-weight: 700; color: var(--c-text-muted); }
.sed-raw pre { margin-top: 10px; max-height: 320px; overflow: auto; padding: 12px; border-radius: 12px; font-size: 11.5px;
  background: color-mix(in srgb, var(--c-text-muted) 8%, transparent); }

.sed-foot { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; padding: 18px 24px; border-top: 1px solid var(--c-border); }

/* mobile-only blocks hidden on desktop */
.sed-mhead, .sed-msum, .sed-mbar { display: none; }

/* ================= mobile (Stitch: ویرایش کامل سرویس - نسخه موبایل) ================= */
@media (max-width: 767px) {
  .sed { gap: 12px; }
  .sed-head, .sed-foot, .sed-desk { display: none !important; }
  .sed-mhead { display: flex; align-items: center; gap: 10px; margin: -12px -12px 0; padding: 12px;
    background: color-mix(in srgb, var(--c-bg) 92%, transparent); -webkit-backdrop-filter: blur(12px); backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--c-border); }
  .sed-mback { width: 38px; height: 38px; flex-shrink: 0; border-radius: 12px; display: grid; place-items: center; border: 1px solid var(--c-border); color: var(--c-text); }
  [dir="ltr"] .sed-flip { display: grid; transform: scaleX(-1); }
  .sed-flip { display: grid; }
  .sed-mhead-txt { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .sed-mhead-row { display: flex; align-items: center; gap: 8px; }
  .sed-mhead-row b { font-size: 15.5px; font-weight: 800; }
  .sed-mhead-txt > span { font-size: 11.5px; color: var(--c-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .sed-idchip { font: 700 10.5px 'JetBrains Mono', monospace; padding: 2px 6px; border-radius: 6px; color: var(--c-primary);
    border: 1px solid color-mix(in srgb, var(--c-primary) 40%, transparent); background: color-mix(in srgb, var(--c-primary) 8%, transparent); }
  .sed-msum { display: flex; flex-direction: column; gap: 14px; padding: 16px; border-radius: 20px; }
  .sed-msum-top { display: flex; align-items: center; gap: 12px; padding-bottom: 14px; border-bottom: 1px solid var(--c-border); }
  .sed-msum-top .min-w-0 { flex: 1; display: flex; flex-direction: column; gap: 1px; }
  .sed-msum-top .sed-lbl { font-size: 11px; font-weight: 500; color: var(--c-text-muted); }
  .sed-avatar { width: 44px; height: 44px; flex-shrink: 0; border-radius: 14px; display: grid; place-items: center; font-weight: 800; font-size: 14px;
    color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 14%, transparent); }
  .sed-msum-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .sed-msum-grid > div { display: flex; flex-direction: column; gap: 4px; padding: 12px; border-radius: 14px; border: 1px solid var(--c-border); min-width: 0; }
  .sed-msum-grid .sed-lbl { font-size: 11px; font-weight: 500; color: var(--c-text-muted); }
  .sed-msum-grid b { font-size: 13px; overflow-wrap: anywhere; }
  .sed-card { border-radius: 20px; }
  .sed-warn { margin: 14px 14px 0; }
  .sed-body { padding: 18px 16px; gap: 18px; }
  .sed-mobile-h { display: block; font-size: 13px; font-weight: 700; color: var(--c-text-muted); }
  .sed-grid3 { grid-template-columns: 1fr 1fr; gap: 16px 12px; }
  .sed-grid3 > .sed-fld:not(.sed-desk) { grid-column: 1 / -1; }
  .sed-seg-btn { min-height: 36px; }
  .sed-quota { padding: 14px; border-radius: 14px; }
  .sed-quota-in { flex: 1 1 100%; min-width: 0; }
  .sed-ticks { min-width: 0; justify-content: flex-start; }
  .sed-row2 { flex-wrap: wrap; } .sed-row2 > .input { flex: 1 1 100%; } .sed-chip { min-height: 32px; }
  .sed-groups { padding: 12px; border-radius: 14px; border: 1px dashed var(--c-border); }
  .sed-sep { padding-top: 0; border-top: 0; }
  .sed-copy { order: 2; padding: 6px 12px; border-radius: 10px; color: var(--c-text); background: color-mix(in srgb, var(--c-text-muted) 14%, transparent); }
  .sed-copy-t { display: inline; }
  .sed-two { grid-template-columns: 1fr; }
  .sed-kv { grid-template-columns: 1fr 1fr; }
  .sed-mbar { display: flex; gap: 10px; position: sticky; bottom: 0; z-index: 30; margin: 0 -12px -12px; padding: 12px 12px calc(12px + env(safe-area-inset-bottom, 0px));
    background: color-mix(in srgb, var(--c-bg) 94%, transparent); -webkit-backdrop-filter: blur(12px); backdrop-filter: blur(12px); border-top: 1px solid var(--c-border); }
  [data-theme-style="caspian"] .sed-mbar { bottom: 74px; margin-bottom: 0; border-radius: 16px; border: 1px solid var(--c-border); }
  .sed-mbar-save { flex: 1; display: inline-flex; align-items: center; justify-content: center; gap: 8px; min-height: 48px; border-radius: 14px; font-weight: 800; }
  .sed-mbar-save:disabled { opacity: .55; }
  .sed-mbar-cancel { min-height: 48px; padding: 0 18px; border-radius: 14px; font-weight: 700; }
}
`
