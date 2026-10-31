// /panel/users/deleted — read-only archive of soft-deleted users (full snapshot
// taken at delete time) + restore through the shared ConfirmDialog.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n, enumLabel } from '../lib/i18n'
import { digits, gb, jalali, toman } from '../lib/format'
import { copyToClipboard } from '../lib/clipboard'
import { USER_ACTION_STRINGS, conflictText, useUserActions } from '../lib/userActions'
import { Alert, Spinner } from '../components/ui'
import { useConfirm } from '../components/ConfirmDialog'
import { DateRangeModal, DRP_CSS } from '../components/DateRangePicker'

const T = {
  fa: {
    title: 'کاربران حذف‌شده', sub: 'بایگانی فقط‌خواندنی کاربران حذف‌شده با تصویر کامل اطلاعات آن‌ها در لحظهٔ حذف',
    back_users: 'بازگشت به کاربران', back_list: 'بازگشت به بایگانی',
    search_ph: 'جستجو (نام کاربری، نام، موبایل، ایمیل، تلگرام، دلیل)…', search: 'جستجو',
    dates: 'بازهٔ تاریخ حذف', st_all: 'همه', st_deleted: 'حذف‌شده', st_restored: 'بازگردانی‌شده',
    col_user: 'نام کاربری اصلی', col_name: 'نام', col_phone: 'موبایل', col_tg: 'تلگرام',
    col_at: 'تاریخ حذف', col_by: 'حذف توسط', col_reason: 'دلیل', col_orders: 'سفارش‌ها', col_paid: 'مجموع پرداخت',
    col_state: 'وضعیت', restored: 'بازگردانی شد', deleted: 'حذف‌شده', none: 'موردی در بایگانی یافت نشد',
    rows_of: 'نمایش {a} از {b} مورد', prev: 'قبلی', next: 'بعدی', details: 'جزئیات',
    restore: 'بازگردانی', restored_at: 'بازگردانی در {d} توسط {by}',
    conflicts_h: 'بازگردانی فعلاً ممکن نیست', not_restorable: 'این مورد قابل بازگردانی نیست (قبلاً بازگردانی شده یا حذف جدیدتری وجود دارد).',
    sec_profile: 'مشخصات حساب', sec_delete: 'اطلاعات حذف', sec_orders: 'سفارش‌ها و پرداخت‌ها', sec_services: 'سرویس‌ها',
    sec_note: 'یادداشت داخلی ادمین', sec_misc: 'سایر',
    f_username: 'نام کاربری', f_name: 'نام', f_phone: 'موبایل', f_email: 'ایمیل', f_tg_id: 'شناسه تلگرام',
    f_tg_user: 'نام کاربری تلگرام', f_ref_code: 'کد معرف', f_ref_by: 'معرفی‌شده توسط', f_ref_count: 'تعداد معرفی‌ها',
    f_source: 'منبع ثبت‌نام', f_joined: 'تاریخ عضویت', f_lang: 'زبان', f_card: 'کارت بانکی کاربر',
    f_at: 'تاریخ حذف', f_by: 'حذف توسط', f_reason: 'دلیل', f_disabled: 'سرویس‌های غیرفعال‌شده روی پنل',
    f_notifs: 'اعلان‌های اختصاصی', f_deliveries: 'اعلان‌های تحویل‌شده', live_hist: 'سوابق خرید زنده',
    o_id: 'سفارش', o_date: 'تاریخ', o_type: 'نوع', o_plan: 'پلن', o_amount: 'مبلغ', o_status: 'وضعیت سفارش',
    o_pay: 'پرداخت', o_card: 'کارت مقصد', o_confirmer: 'تأییدکننده', no_orders: 'سفارشی ثبت نشده بود',
    s_panel: 'پنل', s_account: 'اکانت', s_plan: 'پلن', s_before: 'وضعیت قبل از حذف', s_now: 'اکنون',
    s_usage: 'مصرف', s_expiry: 'انقضا', s_sub: 'لینک ساب', no_services: 'سرویسی نداشت',
    unlimited: 'نامحدود', no_expiry: 'بدون انقضا', copy: 'کپی', copied: 'کپی شد', missing: 'روی پنل وجود نداشت',
    t_new: 'خرید جدید', t_renew: 'تمدید', t_addon_volume: 'افزایش حجم', t_manual: 'دستی', t_imported: 'اتصال سرویس موجود',
    p_approved: 'تأییدشده', p_pending: 'در انتظار', p_rejected: 'ردشده', system: 'سامانه پیامک', blu: 'سامانه بلو',
    lang_fa: 'فارسی', lang_en: 'انگلیسی',
    purge: 'حذف دائمی', purge_n: 'حذف دائمی ({n})', select_all: 'انتخاب همه', select: 'انتخاب',
    ap_on: 'حذف دائمی خودکار روشن است: کاربرانی که بیش از {d} روز در سطل مانده‌اند، روزی یک بار برای همیشه حذف می‌شوند (همراه حساب پاسارگارد).',
    ap_off: 'حذف دائمی خودکار خاموش است — کاربران حذف‌شده تا وقتی دستی پاک نشوند، می‌مانند.',
    ap_next_run: 'اجرای بعدی', ap_next_purge: 'نزدیک‌ترین حذف', ap_due: '{n} کاربر در اجرای بعدی', ap_settings: 'تنظیمات ›',
    purge_at: 'حذف دائمی',
    pg_title: 'حذف دائمی کاربر', pg_title_n: 'حذف دائمی {n} کاربر', pg_btn: 'بله، برای همیشه حذف کن',
    pg_intro: 'این کار برگشت‌پذیر نیست. موارد زیر برای همیشه پاک می‌شوند:',
    pg_users: 'کاربر', pg_services: 'سرویس', pg_tickets: 'تیکت ({m} پیام، {a} پیوست)',
    pg_crm: 'دادهٔ CRM (پروفایل {p}، یادداشت {n}، پرونده {c}، رویداد {e}، کد تخفیف {d})',
    pg_notifs: 'اعلان', pg_tokens: 'نشست / توکن ورود', pg_tg: 'اتصال تلگرام', pg_tg_yes: 'قطع و پاک می‌شود', pg_tg_no: 'متصل نبود',
    pg_archive: 'بایگانی حذف (تصویر کامل مشخصات)',
    pg_keep: 'می‌ماند (برای حسابداری): {o} سفارش و {p} پرداخت — ناشناس با نام «کاربر حذف‌شده #شناسه»، بدون موبایل، ایمیل و تلگرام. جمع‌ها و گزارش‌ها تغییر نمی‌کنند.',
    pg_panel: 'حساب‌ها روی PasarGuard هم حذف شوند ({n} حساب هنوز وجود دارد)',
    pg_panel_none: 'هیچ حسابی از این کاربر روی PasarGuard باقی نمانده است.',
    pg_panel_unknown: 'وضعیت {n} حساب روی PasarGuard معلوم نیست (پنل در دسترس نیست) — با تیک روشن، حذف انجام نمی‌شود.',
    pg_panel_fail: 'اگر حذف روی PasarGuard ناموفق باشد، هیچ چیز حذف نمی‌شود و دلیل نمایش داده می‌شود.',
    pg_audit: 'در گزارش ممیزی با نام کاربری شما ثبت می‌شود (بدون اطلاعات شخصی).',
    pg_failed: 'حذف نشد', pg_loading: 'در حال بررسی…',
  },
  en: {
    title: 'Deleted users', sub: 'Read-only archive of deleted users with a full snapshot taken at deletion time',
    back_users: 'Back to users', back_list: 'Back to archive',
    search_ph: 'Search (username, name, phone, email, Telegram, reason)…', search: 'Search',
    dates: 'Deletion date range', st_all: 'All', st_deleted: 'Deleted', st_restored: 'Restored',
    col_user: 'Original username', col_name: 'Name', col_phone: 'Phone', col_tg: 'Telegram',
    col_at: 'Deleted at', col_by: 'Deleted by', col_reason: 'Reason', col_orders: 'Orders', col_paid: 'Total paid',
    col_state: 'State', restored: 'Restored', deleted: 'Deleted', none: 'Nothing in the archive',
    rows_of: 'Showing {a} of {b}', prev: 'Prev', next: 'Next', details: 'Details',
    restore: 'Restore', restored_at: 'Restored on {d} by {by}',
    conflicts_h: 'Cannot be restored right now', not_restorable: 'This entry cannot be restored (already restored, or a newer deletion exists).',
    sec_profile: 'Account profile', sec_delete: 'Deletion', sec_orders: 'Orders & payments', sec_services: 'Services',
    sec_note: 'Internal admin note', sec_misc: 'Other',
    f_username: 'Username', f_name: 'Name', f_phone: 'Phone', f_email: 'Email', f_tg_id: 'Telegram id',
    f_tg_user: 'Telegram username', f_ref_code: 'Referral code', f_ref_by: 'Referred by', f_ref_count: 'Referrals',
    f_source: 'Signed up via', f_joined: 'Joined', f_lang: 'Language', f_card: "User's bank card",
    f_at: 'Deleted at', f_by: 'Deleted by', f_reason: 'Reason', f_disabled: 'Services disabled on panel',
    f_notifs: 'Targeted notifications', f_deliveries: 'Notification deliveries', live_hist: 'Live purchase history',
    o_id: 'Order', o_date: 'Date', o_type: 'Type', o_plan: 'Plan', o_amount: 'Amount', o_status: 'Order status',
    o_pay: 'Payment', o_card: 'Card', o_confirmer: 'Confirmed by', no_orders: 'No orders',
    s_panel: 'Panel', s_account: 'Account', s_plan: 'Plan', s_before: 'Status before delete', s_now: 'Now',
    s_usage: 'Usage', s_expiry: 'Expiry', s_sub: 'Sub link', no_services: 'No services',
    unlimited: 'unlimited', no_expiry: 'No expiry', copy: 'Copy', copied: 'Copied', missing: 'not found on the panel',
    t_new: 'New purchase', t_renew: 'Renewal', t_addon_volume: 'Add-on volume', t_manual: 'Manual', t_imported: 'Linked existing',
    p_approved: 'Approved', p_pending: 'Pending', p_rejected: 'Rejected', system: 'SMS system', blu: 'Blu system',
    lang_fa: 'Persian', lang_en: 'English',
    purge: 'Delete permanently', purge_n: 'Delete permanently ({n})', select_all: 'Select all', select: 'Select',
    ap_on: 'Auto-purge is on: users that sat in the trash for more than {d} days are permanently deleted once a day (PasarGuard accounts too).',
    ap_off: 'Auto-purge is off — deleted users stay until someone deletes them permanently.',
    ap_next_run: 'Next run', ap_next_purge: 'Next purge', ap_due: '{n} user(s) on the next run', ap_settings: 'Settings ›',
    purge_at: 'Purged on',
    pg_title: 'Delete user permanently', pg_title_n: 'Delete {n} users permanently', pg_btn: 'Yes, delete forever',
    pg_intro: 'This cannot be undone. Permanently removed:',
    pg_users: 'user(s)', pg_services: 'service(s)', pg_tickets: 'ticket(s) ({m} messages, {a} attachments)',
    pg_crm: 'CRM data (profile {p}, notes {n}, cases {c}, events {e}, discount codes {d})',
    pg_notifs: 'notification(s)', pg_tokens: 'session / login token(s)', pg_tg: 'Telegram link', pg_tg_yes: 'removed', pg_tg_no: 'not linked',
    pg_archive: 'deletion archive(s) (full profile snapshot)',
    pg_keep: 'Kept for Accounting: {o} order(s) and {p} payment(s) — anonymized as “deleted user #id”, no phone, email or Telegram. Totals and reports do not change.',
    pg_panel: 'Also delete the accounts on PasarGuard ({n} still exist)',
    pg_panel_none: 'No PasarGuard account of this user is left.',
    pg_panel_unknown: '{n} PasarGuard account(s) could not be checked (panel unreachable) — with the box ticked nothing will be deleted.',
    pg_panel_fail: 'If PasarGuard fails, nothing is deleted and the reason is shown.',
    pg_audit: 'Recorded in the audit log under your username (no personal data).',
    pg_failed: 'Not deleted', pg_loading: 'Checking…',
  },
}

const PAGE = 20
const STATES = ['', 'deleted', 'restored']

function Ico({ d, w = 16 }) {
  return (
    <svg viewBox="0 0 24 24" width={w} height={w} fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}</svg>
  )
}
const I = {
  back: <path d="M19 12H5m7-7l-7 7 7 7" />,
  search: <><circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" /></>,
  cal: <><rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" /></>,
  restore: <><path d="M1 4v6h6" /><path d="M3.51 15a9 9 0 102.13-9.36L1 10" /></>,
  archive: <><rect x="2" y="3" width="20" height="5" rx="1" /><path d="M4 8v11a2 2 0 002 2h12a2 2 0 002-2V8M10 12h4" /></>,
  warn: <><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" /><path d="M12 9v4M12 17h.01" /></>,
  bag: <><path d="M6 2l1.5 5M18 2l-1.5 5M3.5 7h17l-1.2 12.2a2 2 0 01-2 1.8H6.7a2 2 0 01-2-1.8L3.5 7z" /><path d="M8 11a4 4 0 008 0" /></>,
  trash: <><path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6" /><path d="M10 11v6M14 11v6" /></>,
  copy: <><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" /></>,
}

function StatePill({ restored, s }) {
  const c = restored ? 'var(--c-success)' : 'var(--c-danger)'
  return <span className="du-pill" style={{ color: restored ? 'var(--c-success-fg)' : 'var(--c-danger-fg)', background: `color-mix(in srgb, ${c} 14%, transparent)` }}>{restored ? s.restored : s.deleted}</span>
}

export default function DeletedUsers() {
  const { id } = useParams()
  return id ? <ArchiveDetail id={id} /> : <ArchiveList />
}

function ArchiveList() {
  const { t, lang } = useI18n()
  const s = T[lang] || T.fa
  const navigate = useNavigate()
  const [rows, setRows] = useState(null)
  const [count, setCount] = useState(0)
  const [offset, setOffset] = useState(0)
  const [q, setQ] = useState('')
  const [query, setQuery] = useState('')
  const [state, setState] = useState('')
  const [range, setRange] = useState({ from: '', to: '' })
  const [dateOpen, setDateOpen] = useState(false)
  const [err, setErr] = useState('')
  const { staff } = useAuth()
  const isSuper = !!staff?.is_superadmin
  const confirm = useConfirm()
  const [sel, setSel] = useState(() => new Set())
  const [busy, setBusy] = useState(false)
  const [fails, setFails] = useState([])

  const params = useMemo(() => {
    const p = new URLSearchParams({ limit: PAGE, offset })
    if (query) p.set('search', query)
    if (state) p.set('state', state)
    if (range.from) p.set('from', range.from)
    if (range.to) p.set('to', range.to)
    return p
  }, [query, state, range, offset])

  const load = useCallback(() => {
    setRows(null); setErr('')
    api.get(`/admin/deleted-users/?${params}`)
      .then((r) => { setRows(r.data.results ?? r.data); setCount(r.data.count ?? (r.data.results ?? r.data).length) })
      .catch((e) => { setRows([]); setErr(apiError(e, t('load_error'))) })
  }, [params, t])
  useEffect(load, [load])
  const [ap, setAp] = useState(null)
  useEffect(() => { api.get('/admin/deleted-users/auto-purge/').then((r) => setAp(r.data)).catch(() => {}) }, [rows === null])

  const doSearch = () => { setOffset(0); setQuery(q.trim()) }
  const page = Math.floor(offset / PAGE) + 1
  const pages = Math.max(1, Math.ceil(count / PAGE))
  const open = (r) => navigate(`/users/deleted/${r.id}`)
  const purgeable = (rows || []).filter((r) => !r.restored_at)
  const toggle = (rid) => setSel((cur) => { const n = new Set(cur); n.has(rid) ? n.delete(rid) : n.add(rid); return n })
  const allOn = purgeable.length > 0 && purgeable.every((r) => sel.has(r.id))

  // permanent delete: read what goes (+ PasarGuard accounts) first, then the shared dialog
  const purge = async (ids) => {
    setFails([]); setBusy(true)
    let pv
    try {
      pv = (await api.get('/admin/deleted-users/purge-preview/', { params: { ids: ids.join(',') } })).data.results
    } catch (e) { setErr(apiError(e)); setBusy(false); return }
    setBusy(false)
    const bad = pv.filter((x) => x.error)
    const okRows = pv.filter((x) => !x.error)
    if (!okRows.length) { setFails(bad.map((x) => ({ id: x.id, username: x.username, detail: x.error }))); return }
    const sum = (f) => okRows.reduce((a, x) => a + (f(x.removes) || 0), 0)
    const tot = {
      users: okRows.length, services: sum((r) => r.services), tickets: sum((r) => r.tickets),
      msgs: sum((r) => r.ticket_messages), atts: sum((r) => r.ticket_attachments),
      p: sum((r) => r.crm.profile), n: sum((r) => r.crm.notes), c: sum((r) => r.crm.cases), e: sum((r) => r.crm.events), d: sum((r) => r.crm.discount_codes),
      notifs: sum((r) => r.notifications), tokens: sum((r) => r.tokens), tg: sum((r) => (r.telegram_linked ? 1 : 0)),
      archives: sum((r) => r.archives), orders: sum((r) => r.kept_orders), payments: sum((r) => r.kept_payments),
      existing: okRows.reduce((a, x) => a + x.panel_existing, 0), unknown: okRows.reduce((a, x) => a + x.panel_unknown, 0),
    }
    const panelFlag = { current: tot.existing > 0 || tot.unknown > 0 }
    const one = okRows.length === 1
    const okIds = okRows.map((x) => x.id)
    let result = null
    const ok = await confirm({
      tone: 'danger', icon: 'trash', badge: 'users.purge',
      title: one ? s.pg_title : s.pg_title_n.replace('{n}', okRows.length),
      targetLabel: one ? s.col_user : s.pg_users,
      targetId: one ? (okRows[0].username.length > 22 ? `${okRows[0].username.slice(0, 21)}…` : okRows[0].username) : String(okRows.length),
      message: <PurgeSummary s={s} tot={tot} flag={panelFlag} skipped={bad} />,
      confirmLabel: s.pg_btn, footnote: s.pg_audit,
      action: async () => {
        const body = { delete_on_panel: panelFlag.current }
        if (one) { await api.post(`/admin/deleted-users/${okIds[0]}/purge/`, body); return }
        result = (await api.post('/admin/deleted-users/bulk-purge/', { ...body, ids: okIds })).data
      },
    })
    const failed = [...bad.map((x) => ({ id: x.id, username: x.username, detail: x.error })),
      ...((result?.results || []).filter((x) => !x.ok).map((x) => ({ id: x.id, username: pv.find((y) => y.id === x.id)?.username, detail: x.detail })))]
    setFails(failed)
    if (ok) { setSel(new Set()); load() }
  }

  return (
    <div className="du space-y-5">
      <style>{CSS + DRP_CSS}</style>
      <Link to="/users" className="du-back"><Ico d={I.back} /> {s.back_users}</Link>
      <div className="du-head">
        <span className="du-head-ico"><Ico d={I.archive} w={20} /></span>
        <div>
          <h1 className="text-lg font-bold">{s.title}</h1>
          <p className="text-sm text-muted mt-1">{s.sub}</p>
        </div>
      </div>

      <div className="card du-toolbar">
        <div className="du-search">
          <span className="du-search-ico"><Ico d={I.search} /></span>
          <input className="input" value={q} placeholder={s.search_ph}
            onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && doSearch()} />
        </div>
        <button type="button" className="btn-primary text-sm" onClick={doSearch}>{s.search}</button>
        <button type="button" className="du-tool-btn" onClick={() => setDateOpen(true)}>
          <Ico d={I.cal} w={15} /> {s.dates}
          {range.from && <span className="du-badge" dir="ltr">{range.from}→{range.to}</span>}
        </button>
        <div className="du-tabs">
          {STATES.map((st) => (
            <button key={st || 'all'} type="button" className={'du-tab' + (state === st ? ' on' : '')}
              onClick={() => { setState(st); setOffset(0) }}>{s[`st_${st || 'all'}`]}</button>
          ))}
        </div>
      </div>
      <DateRangeModal open={dateOpen} onClose={() => setDateOpen(false)} onApply={(r) => { setRange(r); setOffset(0) }} />

      <Alert>{err}</Alert>
      {ap && (
        <div className={'du-ap' + (ap.enabled ? ' on' : '')} data-testid="auto-purge-banner">
          <span>{ap.enabled ? s.ap_on.replace('{d}', digits(ap.days, lang)) : s.ap_off}</span>
          {ap.enabled && (
            <span className="du-ap-dates">
              {ap.next_run && <span>{s.ap_next_run}: <b className="du-mono">{jalali(ap.next_run, true, lang)}</b></span>}
              {ap.next_purge_at && <span>{s.ap_next_purge}: <b className="du-mono">{jalali(ap.next_purge_at, false, lang)}</b></span>}
              {ap.due_now > 0 && <span className="du-ap-due">{s.ap_due.replace('{n}', digits(ap.due_now, lang))}</span>}
            </span>
          )}
          {isSuper && <Link to="/settings/auto-purge" className="du-ap-link">{s.ap_settings}</Link>}
        </div>
      )}
      {fails.length > 0 && (
        <div className="du-fails" role="alert">
          {fails.map((f) => <div key={f.id}><b>{s.pg_failed}: <bdi dir="ltr">{f.username}</bdi></b> — <span dir="auto">{f.detail}</span></div>)}
        </div>
      )}
      {isSuper && sel.size > 0 && (
        <div className="du-bulk">
          <span>{digits(sel.size, lang)} ✓</span>
          <button type="button" className="du-purge-btn" disabled={busy} onClick={() => purge([...sel])}>
            <Ico d={I.trash} w={15} /> {busy ? s.pg_loading : s.purge_n.replace('{n}', digits(sel.size, lang))}
          </button>
        </div>
      )}

      {rows === null ? (
        <div className="grid place-items-center py-16"><Spinner /></div>
      ) : rows.length === 0 ? (
        <div className="card text-center text-muted">{s.none}</div>
      ) : (
        <div className="card p-0 du-wrap">
          {isSuper && purgeable.length > 0 && (
            <label className="du-selall">
              <input type="checkbox" checked={allOn}
                onChange={() => setSel(allOn ? new Set() : new Set(purgeable.map((r) => r.id)))} />
              <span>{s.select_all}</span>
            </label>
          )}
          <table className="du-table">
            <thead>
              <tr>
                {isSuper && <th className="du-sel"><input type="checkbox" aria-label={s.select_all} checked={allOn}
                  disabled={!purgeable.length}
                  onChange={() => setSel(allOn ? new Set() : new Set(purgeable.map((r) => r.id)))} /></th>}
                <th>{s.col_user}</th><th>{s.col_name}</th><th>{s.col_phone}</th><th>{s.col_tg}</th>
                <th>{s.col_at}</th><th>{s.col_by}</th><th>{s.col_reason}</th>
                <th className="du-c">{s.col_orders}</th><th>{s.col_paid}</th><th>{s.col_state}</th>
                {isSuper && <th />}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="du-row" tabIndex={0} onClick={() => open(r)}
                  onKeyDown={(e) => e.key === 'Enter' && open(r)}>
                  {isSuper && (
                    <td data-label={s.select} className="du-sel" onClick={(e) => e.stopPropagation()}>
                      {!r.restored_at && <input type="checkbox" aria-label={s.select} checked={sel.has(r.id)} onChange={() => toggle(r.id)} />}
                    </td>
                  )}
                  <td data-label={s.col_user}><b className="du-mono" dir="ltr">{r.original_username}</b></td>
                  <td data-label={s.col_name}>{r.original_name || '—'}</td>
                  <td data-label={s.col_phone} className="du-mono" dir="ltr">{r.original_phone || '—'}</td>
                  <td data-label={s.col_tg} className="du-mono" dir="ltr">
                    {r.original_telegram_username ? `@${r.original_telegram_username}` : (r.original_telegram_id || '—')}
                  </td>
                  <td data-label={s.col_at} className="du-mono du-muted">{jalali(r.deleted_at, true, lang)}</td>
                  <td data-label={s.col_by}>{r.deleted_by || '—'}</td>
                  <td data-label={s.col_reason} className="du-reason" title={r.reason}>{r.reason}</td>
                  <td data-label={s.col_orders} className="du-c du-mono">{digits(r.orders_count, lang)}</td>
                  <td data-label={s.col_paid} className="du-mono">{toman(r.total_paid, lang)}</td>
                  <td data-label={s.col_state}><StatePill restored={!!r.restored_at} s={s} />
                    {r.purge_at && <span className="du-purge-at">{s.purge_at}: <span className="du-mono">{jalali(r.purge_at, false, lang)}</span></span>}
                  </td>
                  {isSuper && (
                    <td className="du-act" onClick={(e) => e.stopPropagation()}>
                      {!r.restored_at && (
                        <button type="button" className="du-purge-btn" disabled={busy} onClick={() => purge([r.id])}>
                          <Ico d={I.trash} w={14} /> {s.purge}
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="du-foot">
            <span className="text-xs text-muted">
              {s.rows_of.replace('{a}', `${digits(count ? offset + 1 : 0, lang)}–${digits(Math.min(offset + PAGE, count), lang)}`).replace('{b}', digits(count, lang))}
            </span>
            <div className="du-pager">
              <button type="button" className="du-tool-btn" disabled={page <= 1} onClick={() => setOffset(Math.max(0, offset - PAGE))}>{s.prev}</button>
              <span className="text-xs du-mono">{digits(page, lang)} / {digits(pages, lang)}</span>
              <button type="button" className="du-tool-btn" disabled={page >= pages} onClick={() => setOffset(offset + PAGE)}>{s.next}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/* What a permanent delete removes / keeps (backend accounts/purge.py), with the PasarGuard choice. */
function PurgeSummary({ s, tot, flag, skipped }) {
  const [panel, setPanel] = useState(flag.current)
  const set = (v) => { flag.current = v; setPanel(v) }
  const n = (v) => Number(v || 0).toLocaleString('en-US')
  return (
    <div className="du-pg">
      <p>{s.pg_intro}</p>
      <ul>
        <li><b>{n(tot.users)}</b> {s.pg_users}</li>
        <li><b>{n(tot.services)}</b> {s.pg_services}</li>
        <li><b>{n(tot.tickets)}</b> {s.pg_tickets.replace('{m}', n(tot.msgs)).replace('{a}', n(tot.atts))}</li>
        <li>{s.pg_crm.replace('{p}', n(tot.p)).replace('{n}', n(tot.n)).replace('{c}', n(tot.c)).replace('{e}', n(tot.e)).replace('{d}', n(tot.d))}</li>
        <li><b>{n(tot.notifs)}</b> {s.pg_notifs}</li>
        <li><b>{n(tot.tokens)}</b> {s.pg_tokens}</li>
        <li>{s.pg_tg}: <b>{tot.tg ? `${s.pg_tg_yes} (${n(tot.tg)})` : s.pg_tg_no}</b></li>
        <li><b>{n(tot.archives)}</b> {s.pg_archive}</li>
      </ul>
      <p className="du-pg-keep">{s.pg_keep.replace('{o}', n(tot.orders)).replace('{p}', n(tot.payments))}</p>
      {tot.services > 0 && (tot.existing > 0 || tot.unknown > 0) ? (
        <label className="du-pg-panel">
          <input type="checkbox" checked={panel} onChange={(e) => set(e.target.checked)} />
          <span>{s.pg_panel.replace('{n}', n(tot.existing))}</span>
        </label>
      ) : tot.services > 0 && <p className="du-pg-note">{s.pg_panel_none}</p>}
      {tot.unknown > 0 && panel && <p className="du-pg-warn">{s.pg_panel_unknown.replace('{n}', n(tot.unknown))}</p>}
      {panel && tot.services > 0 && <p className="du-pg-note">{s.pg_panel_fail}</p>}
      {skipped.length > 0 && <p className="du-pg-warn">{skipped.map((x) => `${x.username}: ${x.error}`).join(' · ')}</p>}
    </div>
  )
}

function Kv({ rows }) {
  return (
    <div className="du-kv">
      {rows.map(([k, v]) => <div key={k}><span>{k}</span><b>{v === '' || v == null ? '—' : v}</b></div>)}
    </div>
  )
}

function ArchiveDetail({ id }) {
  const { t, lang } = useI18n()
  const s = T[lang] || T.fa
  const us = USER_ACTION_STRINGS[lang] || USER_ACTION_STRINGS.fa
  const { can } = useAuth()
  const userActions = useUserActions()
  const [a, setA] = useState(null)
  const [err, setErr] = useState('')
  const [copied, setCopied] = useState(null)

  const load = useCallback(() => {
    api.get(`/admin/deleted-users/${id}/`).then((r) => setA(r.data)).catch((e) => setErr(apiError(e, t('load_error'))))
  }, [id, t])
  useEffect(load, [load])

  if (!a) {
    return err
      ? <div className="du"><style>{CSS}</style><Link to="/users/deleted" className="du-back"><Ico d={I.back} /> {s.back_list}</Link><Alert>{err}</Alert></div>
      : <div className="grid place-items-center py-16"><Spinner /></div>
  }

  const snap = a.snapshot || {}
  const p = snap.profile || {}
  const orders = snap.orders || []
  const services = snap.services || []
  const conflicts = a.restore_conflicts || {}
  const hasConflicts = Object.keys(conflicts).length > 0
  const payLabel = (st) => s[`p_${st}`] || st
  const confirmer = (c) => (c === 'SMS system' ? s.system : c === 'Blu system' ? s.blu : c)

  const restore = async () => {
    const res = await userActions.restore(a)
    if (res) load()
  }
  const copy = async (key, text) => {
    if (await copyToClipboard(text)) { setCopied(key); setTimeout(() => setCopied(null), 1500) }
  }

  return (
    <div className="du space-y-5">
      <style>{CSS}</style>
      <Link to="/users/deleted" className="du-back"><Ico d={I.back} /> {s.back_list}</Link>

      <div className="card du-dhead">
        <div className="min-w-0">
          <div className="du-dtitle">
            <h1 className="du-mono" dir="ltr">{a.original_username}</h1>
            <StatePill restored={!!a.restored_at} s={s} />
          </div>
          <p className="text-sm text-muted mt-1">
            {a.original_name || '—'} · #{a.user ?? '—'} · {s.f_at}: {jalali(a.deleted_at, true, lang)}
          </p>
          {a.restored_at && (
            <p className="text-xs du-ok mt-1">{s.restored_at.replace('{d}', jalali(a.restored_at, true, lang)).replace('{by}', a.restored_by || '—')}</p>
          )}
        </div>
        <div className="du-dacts">
          {a.user && (
            <Link to={`/users/${a.user}/orders`} className="du-tool-btn"><Ico d={I.bag} w={15} /> {s.live_hist}</Link>
          )}
          {can('users.delete') && a.can_restore && (
            <button type="button" className="du-restore-btn" onClick={restore} disabled={hasConflicts}>
              <Ico d={I.restore} w={15} /> {s.restore}
            </button>
          )}
        </div>
      </div>

      {a.can_restore && hasConflicts && (
        <div className="du-warn"><Ico d={I.warn} w={16} /><div><b>{s.conflicts_h}</b><p>{conflictText(conflicts, us)}</p></div></div>
      )}
      {!a.can_restore && !a.restored_at && <div className="du-warn"><Ico d={I.warn} w={16} /><p>{s.not_restorable}</p></div>}

      <div className="du-grid2">
        <section className="card du-sec">
          <h2>{s.sec_profile}</h2>
          <Kv rows={[
            [s.f_username, <span dir="ltr">{p.username}</span>], [s.f_name, p.name],
            [s.f_phone, <span dir="ltr">{p.phone}</span>], [s.f_email, <span dir="ltr">{p.email}</span>],
            [s.f_tg_id, <span dir="ltr">{p.telegram_id ?? ''}</span>], [s.f_tg_user, p.telegram_username ? <span dir="ltr">@{p.telegram_username}</span> : ''],
            [s.f_ref_code, <span dir="ltr">{p.referral_code}</span>], [s.f_ref_by, p.referred_by?.username || ''],
            [s.f_ref_count, digits(p.referral_count ?? 0, lang)], [s.f_source, enumLabel(t, 'src_', p.source)],
            [s.f_lang, s[`lang_${p.language}`] || p.language], [s.f_card, p.bank_card_number ? <span dir="ltr">{p.bank_card_number}</span> : ''],
            [s.f_joined, jalali(p.created_at, true, lang)],
          ]} />
        </section>
        <section className="card du-sec">
          <h2>{s.sec_delete}</h2>
          <Kv rows={[
            [s.f_at, jalali(a.deleted_at, true, lang)], [s.f_by, a.deleted_by],
            [s.f_disabled, digits(snap.services_disabled ?? 0, lang)],
            [s.col_orders, digits(a.orders_count, lang)], [s.col_paid, toman(a.total_paid, lang)],
            [s.f_notifs, digits(snap.notifications?.targeted ?? 0, lang)],
            [s.f_deliveries, digits(snap.notifications?.deliveries ?? 0, lang)],
          ]} />
          <div className="du-reason-box"><span>{s.f_reason}</span><p>{a.reason}</p></div>
          {p.admin_note && <div className="du-reason-box"><span>{s.sec_note}</span><p>{p.admin_note}</p></div>}
        </section>
      </div>

      <section className="card p-0 du-sec du-wrap">
        <h2 className="du-sec-h">{s.sec_orders} <span className="du-count">{digits(orders.length, lang)}</span></h2>
        {orders.length === 0 ? <p className="du-empty">{s.no_orders}</p> : (
          <table className="du-table du-table--flat">
            <thead>
              <tr>
                <th>{s.o_id}</th><th>{s.o_date}</th><th>{s.o_type}</th><th>{s.o_plan}</th><th>{s.o_amount}</th>
                <th>{s.o_status}</th><th>{s.o_pay}</th><th>{s.o_card}</th><th>{s.o_confirmer}</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id} className="du-row du-row--static">
                  <td data-label={s.o_id} className="du-mono">#{digits(o.id, lang)}</td>
                  <td data-label={s.o_date} className="du-mono du-muted">{jalali(o.created_at, true, lang)}</td>
                  <td data-label={s.o_type}>{s[`t_${o.type}`] || o.type}</td>
                  <td data-label={s.o_plan}>{(o.plan && (lang === 'en' ? o.plan.name_en || o.plan.name_fa : o.plan.name_fa)) || o.requested_account_name || '—'}</td>
                  <td data-label={s.o_amount} className="du-mono">{toman(o.payment?.amount ?? o.amount_unique, lang)}</td>
                  <td data-label={s.o_status}>{enumLabel(t, 'os_', o.status)}</td>
                  <td data-label={s.o_pay}>{o.payment ? `${enumLabel(t, 'm_', o.payment.method)} · ${payLabel(o.payment.status)}` : '—'}</td>
                  <td data-label={s.o_card} className="du-mono" dir="ltr">{o.payment?.card ? `${o.payment.card.number}` : '—'}</td>
                  <td data-label={s.o_confirmer}>
                    {o.payment?.confirmer ? confirmer(o.payment.confirmer) : '—'}
                    {o.payment?.confirmed_at && <span className="du-sub du-mono">{jalali(o.payment.confirmed_at, true, lang)}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card du-sec">
        <h2 className="du-sec-h">{s.sec_services} <span className="du-count">{digits(services.length, lang)}</span></h2>
        {services.length === 0 ? <p className="du-empty">{s.no_services}</p> : (
          <div className="du-svcs">
            {services.map((v) => (
              <div key={v.id} className="du-svc">
                <div className="du-svc-top">
                  <b className="du-mono" dir="ltr">{v.panel_username}</b>
                  <span className="du-muted text-xs">{v.panel?.name}</span>
                </div>
                <Kv rows={[
                  [s.s_plan, (v.plan && (lang === 'en' ? v.plan.name_en || v.plan.name_fa : v.plan.name_fa)) || '—'],
                  [s.s_before, enumLabel(t, 'st_', v.status_before)],
                  [s.s_now, v.panel_result === 'missing' ? s.missing : enumLabel(t, 'st_', v.status)],
                  [s.s_usage, <span dir="ltr">{digits(gb(v.data_used), lang)} GB / {v.data_limit ? `${digits(gb(v.data_limit), lang)} GB` : s.unlimited}</span>],
                  [s.s_expiry, v.expire_at ? jalali(v.expire_at, false, lang) : s.no_expiry],
                ]} />
                {v.subscription_url && (
                  <div className="du-subl">
                    <button type="button" className="du-tool-btn" onClick={() => copy(v.id, v.subscription_url)}>
                      <Ico d={I.copy} w={14} /> {copied === v.id ? s.copied : s.copy}
                    </button>
                    <code dir="ltr">{v.subscription_url}</code>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

const CSS = `
.du-sel { width: 40px; } .du-sel input { width: 18px; height: 18px; accent-color: var(--c-danger); cursor: pointer; }
.du-act { width: 1%; white-space: nowrap; }
.du-selall { display: none; }
.du-table td b.du-mono { overflow-wrap: anywhere; min-width: 0; }
.du-purge-btn { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 9px; font-size: 12.5px; font-weight: 700;
  color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 10%, transparent); border: 1px solid color-mix(in srgb, var(--c-danger) 32%, transparent); }
.du-purge-btn:disabled { opacity: .6; }
.du-bulk { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 10px 14px; border-radius: 12px;
  background: color-mix(in srgb, var(--c-danger) 8%, var(--c-surface)); border: 1px solid color-mix(in srgb, var(--c-danger) 28%, var(--c-border)); }
.du-ap { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; padding: 10px 14px; border-radius: 12px; font-size: 12.5px;
  border: 1px solid var(--c-border); color: var(--c-text-muted); overflow-wrap: anywhere; }
.du-ap.on { color: var(--c-text); border-color: color-mix(in srgb, var(--c-danger) 35%, var(--c-border));
  background: color-mix(in srgb, var(--c-danger) 6%, transparent); }
.du-ap > span:first-child { flex: 1 1 260px; min-width: 0; }
.du-ap-dates { display: flex; flex-wrap: wrap; gap: 4px 12px; }
.du-ap-due { color: var(--c-danger-fg); font-weight: 700; }
.du-ap-link { color: var(--c-primary); font-weight: 700; min-height: 44px; display: inline-flex; align-items: center; }
.du-purge-at { display: block; margin-top: 3px; font-size: 11px; color: var(--c-danger-fg); }
.du-fails { display: flex; flex-direction: column; gap: 4px; padding: 10px 14px; border-radius: 12px; font-size: 12.5px; overflow-wrap: anywhere;
  color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 10%, transparent); border: 1px solid color-mix(in srgb, var(--c-danger) 30%, transparent); }
.du-fails span { color: var(--c-text); }
.du-pg { display: flex; flex-direction: column; gap: 8px; text-align: start; font-size: 13px; line-height: 1.7; }
.du-pg ul { margin: 0; padding-inline-start: 18px; list-style: disc; }
.du-pg-keep { padding: 8px 10px; border-radius: 10px; font-size: 12.5px; color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 10%, transparent); }
.du-pg-panel { display: flex; align-items: flex-start; gap: 8px; padding: 10px; border-radius: 10px; font-weight: 600; cursor: pointer;
  border: 1px solid color-mix(in srgb, var(--c-danger) 30%, var(--c-border)); }
.du-pg-panel input { width: 18px; height: 18px; margin-top: 3px; flex-shrink: 0; accent-color: var(--c-danger); }
.du-pg-note { font-size: 12px; color: var(--c-muted-fg); }
.du-pg-warn { font-size: 12px; color: var(--c-warning-fg); overflow-wrap: anywhere; }
@media (max-width: 767px) {
  .du-purge-btn { min-height: 44px; padding-inline: 14px; }
  .du-sel input { width: 22px; height: 22px; }
  .du-selall { display: flex; align-items: center; gap: 10px; min-height: 44px; padding: 8px 16px 0; font-size: 13px; font-weight: 600; cursor: pointer; }
  .du-selall input { width: 22px; height: 22px; accent-color: var(--c-danger); }
  .du-table td.du-sel, .du-table td.du-act { justify-content: flex-end; }
  .du-table td.du-act::before { content: none; }
  .du-table td.du-act .du-purge-btn { width: 100%; justify-content: center; }
  .du-bulk .du-purge-btn { flex: 1; justify-content: center; }
}
.du-back { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 600; color: var(--c-text-muted); }
.du-back:hover { color: var(--c-primary); }
.du-head { display: flex; align-items: flex-start; gap: 12px; }
.du-head-ico { width: 42px; height: 42px; border-radius: 12px; flex-shrink: 0; display: grid; place-items: center;
  color: var(--c-danger); background: color-mix(in srgb, var(--c-danger) 12%, transparent); }
.du-mono { font-family: 'JetBrains Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }
.du-muted { color: var(--c-text-muted); font-size: 12px; }
.du-ok { color: var(--c-success); }
.du-c { text-align: center; }
.du-sub { display: block; font-size: 11px; color: var(--c-text-muted); margin-top: 2px; }

.du-toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.du-search { position: relative; flex: 1 1 240px; min-width: 0; }
.du-search .input { width: 100%; padding-inline-start: 38px; }
.du-search-ico { position: absolute; inset-inline-start: 12px; top: 50%; transform: translateY(-50%); color: var(--c-text-muted); pointer-events: none; }
.du-tool-btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 12px; border-radius: 10px; font-size: 12px; font-weight: 600;
  color: var(--c-text-muted); border: 1px solid var(--c-border); background: transparent; white-space: nowrap; transition: .15s; }
.du-tool-btn:hover:not(:disabled) { color: var(--c-primary); border-color: var(--c-primary); }
.du-tool-btn:disabled { opacity: .4; cursor: not-allowed; }
.du-badge { font-size: 10.5px; padding: 1px 7px; border-radius: 6px; color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 12%, transparent); }
.du-tabs { display: inline-flex; gap: 3px; padding: 3px; border-radius: 11px; background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); }
.du-tab { padding: 6px 12px; border-radius: 8px; font-size: 12.5px; font-weight: 600; color: var(--c-text-muted); white-space: nowrap; }
.du-tab.on { background: var(--c-primary); color: #fff; }

.du-wrap { overflow-x: auto; }
.du-table { width: 100%; min-width: 1000px; border-collapse: collapse; font-size: 13px; }
.du-table thead th { text-align: start; font-weight: 600; font-size: 11.5px; letter-spacing: .03em; color: var(--c-text-muted);
  padding: 12px 14px; white-space: nowrap; border-bottom: 1px solid var(--c-border); }
.du-table td { padding: 11px 14px; vertical-align: middle; border-bottom: 1px solid var(--c-border); }
.du-row { cursor: pointer; }
.du-row--static { cursor: default; }
.du-row:hover > td { background: color-mix(in srgb, var(--c-primary) 5%, transparent); }
.du-row:focus-visible { outline: 2px solid var(--c-primary); outline-offset: -2px; }
.du-reason { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.du-pill { display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 11.5px; font-weight: 700; white-space: nowrap; }
.du-foot { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: space-between; padding: 13px 16px; border-top: 1px solid var(--c-border); }
.du-pager { display: flex; align-items: center; gap: 8px; }

.du-dhead { display: flex; flex-wrap: wrap; gap: 14px; align-items: flex-start; justify-content: space-between; }
.du-dtitle { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.du-dtitle h1 { font-size: 18px; font-weight: 800; overflow-wrap: anywhere; }
.du-dacts { display: flex; flex-wrap: wrap; gap: 8px; }
.du-restore-btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; border-radius: 10px; font-size: 13px; font-weight: 700;
  color: #fff; background: #11AB53; border: 0; }
.du-restore-btn:hover:not(:disabled) { background: #0E9447; }
.du-restore-btn:disabled { opacity: .45; cursor: not-allowed; }
.du-warn { display: flex; gap: 10px; align-items: flex-start; padding: 12px 14px; border-radius: 12px; font-size: 13px; line-height: 1.8;
  color: var(--c-text); border: 1px solid color-mix(in srgb, var(--c-warning) 40%, transparent); background: color-mix(in srgb, var(--c-warning) 10%, transparent); }
.du-warn > svg { color: var(--c-warning); flex-shrink: 0; margin-top: 4px; }
.du-warn p { overflow-wrap: anywhere; }

.du-grid2 { display: grid; grid-template-columns: 1fr; gap: 16px; }
@media (min-width: 1024px) { .du-grid2 { grid-template-columns: 1fr 1fr; } }
.du-sec h2, .du-sec-h { font-size: 14px; font-weight: 800; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
.du-sec-h { padding: 16px 16px 0; }
.card.du-sec:not(.p-0) .du-sec-h { padding: 0; }
.du-count { font-size: 11px; padding: 1px 8px; border-radius: 999px; color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 12%, transparent); }
.du-kv { display: grid; grid-template-columns: 1fr; gap: 0; }
@media (min-width: 560px) { .du-kv { grid-template-columns: 1fr 1fr; column-gap: 18px; } }
.du-kv > div { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 0; border-bottom: 1px dashed var(--c-border); font-size: 12.5px; }
.du-kv span { color: var(--c-text-muted); white-space: nowrap; }
.du-kv b { font-weight: 600; text-align: end; min-width: 0; overflow-wrap: anywhere; }
.du-reason-box { margin-top: 12px; padding: 10px 12px; border-radius: 10px; background: color-mix(in srgb, var(--c-text-muted) 7%, transparent); }
.du-reason-box span { display: block; font-size: 11px; color: var(--c-text-muted); margin-bottom: 4px; }
.du-reason-box p { font-size: 13px; line-height: 1.8; white-space: pre-wrap; overflow-wrap: anywhere; }
.du-empty { padding: 8px 16px 16px; font-size: 13px; color: var(--c-text-muted); }
.du-svcs { display: grid; grid-template-columns: 1fr; gap: 12px; }
@media (min-width: 1024px) { .du-svcs { grid-template-columns: 1fr 1fr; } }
.du-svc { min-width: 0; overflow: hidden; padding: 12px 14px; border-radius: 12px; border: 1px solid var(--c-border); }
.du-svcs > *, .du-grid2 > * { min-width: 0; }
.du-svc .du-kv { grid-template-columns: 1fr; }
.du-svc-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 4px; }
.du-subl { display: flex; align-items: center; gap: 8px; margin-top: 10px; }
.du-subl code { font-size: 11px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--c-text-muted); }

@media (max-width: 900px) {
  .du-wrap { overflow-x: visible; }
  .du-table, .du-table tbody, .du-table tr, .du-table td { display: block; width: 100%; }
  .du-table { min-width: 0; }
  .du-table thead { display: none; }
  .du-table tr.du-row { border: 1px solid var(--c-border); border-radius: 12px; margin: 12px; width: auto; padding: 4px 0; }
  .du-table tr.du-row:hover > td { background: none; }
  .du-table td { border: 0 !important; padding: 8px 14px; display: flex; align-items: center; justify-content: space-between; gap: 12px; text-align: end; }
  .du-table td::before { content: attr(data-label); font-family: 'Vazirmatn', ui-sans-serif, system-ui, sans-serif; font-size: 11px; font-weight: 600; color: var(--c-text-muted); text-align: start; white-space: nowrap; }
  .du-table td.du-c { justify-content: space-between; }
  .du-reason { max-width: none; white-space: normal; }
  .du-toolbar > .btn-primary { flex: 1 0 auto; }
}
`
