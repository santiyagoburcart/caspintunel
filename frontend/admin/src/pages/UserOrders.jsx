import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n, enumLabel } from '../lib/i18n'
import { jalali, toman, digits } from '../lib/format'
import { Alert, Spinner } from '../components/ui'
import { useAuth } from '../lib/auth'
import { useUserActions } from '../lib/userActions'

const T = {
  fa: {
    back: 'بازگشت به کاربران',
    title: 'سوابق خرید', uid: 'شناسه',
    f_all: 'همه', f_success: 'موفق', f_failed: 'ناموفق', f_pending: 'در انتظار',
    col_order: 'شماره سفارش', col_date: 'تاریخ', col_plan: 'پلن', col_amount: 'مبلغ',
    col_method: 'روش پرداخت', col_status: 'وضعیت', col_confirmer: 'تأییدکننده',
    col_account: 'نام اکانت', col_invoice: 'فاکتور',
    invoice_link: 'جزئیات فاکتور', no_invoice: '—',
    confirmer_system: 'سامانه پیامک', confirmer_admin: 'ادمین',
    none: 'این کاربر هنوز سفارشی ثبت نکرده است', load_error: 'خطا در دریافت اطلاعات',
    renew_tag: 'تمدید', new_tag: 'خرید جدید', addon_tag: 'افزایش حجم',
    manual_tag: 'دستی', imported_tag: 'اتصال سرویس موجود',
    delete_user: 'حذف کاربر', deleted_badge: 'حذف‌شده',
    deleted_note: 'این کاربر در {d} حذف شده است. دلیل: {r}', view_archive: 'مشاهده در بایگانی',
  },
  en: {
    back: 'Back to users',
    title: 'Purchase history', uid: 'ID',
    f_all: 'All', f_success: 'Successful', f_failed: 'Failed', f_pending: 'Pending',
    col_order: 'Order #', col_date: 'Date', col_plan: 'Plan', col_amount: 'Amount',
    col_method: 'Payment method', col_status: 'Status', col_confirmer: 'Confirmed by',
    col_account: 'Account name', col_invoice: 'Invoice',
    invoice_link: 'Invoice details', no_invoice: '—',
    confirmer_system: 'SMS system', confirmer_admin: 'Admin',
    none: 'This user has not placed any orders yet', load_error: 'Failed to load data',
    renew_tag: 'Renewal', new_tag: 'New purchase', addon_tag: 'Add-on volume',
    manual_tag: 'Manual', imported_tag: 'Linked existing',
    delete_user: 'Delete user', deleted_badge: 'Deleted',
    deleted_note: 'This user was deleted on {d}. Reason: {r}', view_archive: 'View in archive',
  },
}

const AV_TONES = ['#1464BA', '#11AB53', '#7C3AED', '#D97706', '#0891B2', '#DB2777']
const initials = (r) => {
  const name = String(r?.name || '').normalize('NFKC').trim()
  if (name) {
    const parts = name.split(/\s+/).filter(Boolean)
    const a = [...parts[0]]
    const b = parts[1] ? [...parts[1]] : a
    return ((a[0] || '') + (parts[1] ? b[0] : a[1] || '')).toUpperCase()
  }
  if (r?.source === 'bot') return 'TG'
  return (String(r?.username || '?').replace(/[^a-zA-Z0-9]/g, '').slice(0, 2) || '?').toUpperCase()
}

const ST_TONE = {
  completed: 'success', paid: 'warning', pending_payment: 'warning',
  rejected: 'danger', failed: 'danger', expired: 'muted',
}
const TYPE_TAG = { new: 'new_tag', renew: 'renew_tag', addon_volume: 'addon_tag', manual: 'manual_tag', imported: 'imported_tag' }

const FILTERS = [
  ['all', 'f_all', () => true],
  ['success', 'f_success', (o) => o.status === 'completed'],
  ['failed', 'f_failed', (o) => ['rejected', 'failed', 'expired'].includes(o.status)],
  ['pending', 'f_pending', (o) => ['pending_payment', 'paid'].includes(o.status)],
]

function Ico({ d, w = 16 }) {
  return (
    <svg viewBox="0 0 24 24" width={w} height={w} fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{d}</svg>
  )
}
const I = {
  back: <path d="M19 12H5m7-7l-7 7 7 7" />,
  bag: <><path d="M6 2l1.5 5M18 2l-1.5 5M3.5 7h17l-1.2 12.2a2 2 0 01-2 1.8H6.7a2 2 0 01-2-1.8L3.5 7z" /><path d="M8 11a4 4 0 008 0" /></>,
  bot: <><rect x="3" y="11" width="18" height="10" rx="2" /><circle cx="12" cy="5" r="2" /><path d="M12 7v4M8 16h.01M16 16h.01" /></>,
  globe: <><circle cx="12" cy="12" r="10" /><path d="M2 12h20M12 2a15.3 15.3 0 010 20 15.3 15.3 0 010-20z" /></>,
  invoice: <><path d="M6 3h12v18l-3-2-3 2-3-2-3 2V3z" /><path d="M9 7h6M9 11h6M9 15h4" /></>,
  trash: <><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" /></>,
}

function StatusPill({ status, t }) {
  const tone = ST_TONE[status] || 'muted'
  const color = `var(--c-${tone === 'muted' ? 'text-muted' : tone})`
  return (
    <span className="uo-pill" style={{ background: `color-mix(in srgb, ${color} 16%, transparent)`, color }}>
      {enumLabel(t, 'os_', status)}
    </span>
  )
}

function confirmerLabel(row, s) {
  if (!row.confirmer) return '—'
  if (row.confirmer === 'SMS system') return s.confirmer_system
  if (row.confirmer === 'admin') return s.confirmer_admin
  return row.confirmer
}

export default function UserOrders() {
  const { id } = useParams()
  const { t, lang } = useI18n()
  const s = T[lang] || T.fa
  const [user, setUser] = useState(null)
  const [rows, setRows] = useState(null)
  const [filter, setFilter] = useState('all')
  const [err, setErr] = useState('')
  const { can } = useAuth()
  const userActions = useUserActions()

  const loadUser = () => api.get(`/admin/users/${id}/`).then((r) => setUser(r.data)).catch((e) => setErr(apiError(e, s.load_error)))
  useEffect(() => {
    setUser(null); setRows(null); setErr('')
    loadUser()
    api.get(`/admin/users/${id}/orders/`).then((r) => setRows(r.data)).catch((e) => { setRows([]); setErr(apiError(e, s.load_error)) })
  }, [id])

  const removeUser = async () => {
    if (user && await userActions.remove(user)) loadUser()
  }

  const shown = useMemo(() => (rows || []).filter(FILTERS.find(([k]) => k === filter)[2]), [rows, filter])
  const fc = (fn) => (rows || []).filter(fn).length

  return (
    <div className="uo space-y-5">
      <style>{CSS}</style>

      <Link to="/users" className="uo-back"><Ico d={I.back} w={16} /> {s.back}</Link>

      <div className="uo-head">
        <div className="uo-idcell">
          <span className="uo-av" style={{ background: AV_TONES[Number(id) % AV_TONES.length] }}>{initials(user)}</span>
          <div>
            <div className="uo-uname">
              <span dir="ltr">{user?.username || '…'}</span>
              {user && (
                <span className={'uo-src-tag ' + (user.source === 'bot' ? 'bot' : 'site')}>
                  <Ico d={user.source === 'bot' ? I.bot : I.globe} w={11} />
                  {enumLabel(t, 'src_', user.source)}
                </span>
              )}
            </div>
            <span className="uo-sub">{user?.name || '—'} · {s.uid}: #{id}</span>
          </div>
        </div>
        <div className="uo-head-r">
          <h1 className="uo-title"><Ico d={I.bag} w={18} /> {s.title}</h1>
          {user && !user.deleted_at && can('users.delete') && (
            <button type="button" className="uo-del-btn" onClick={removeUser}><Ico d={I.trash} w={14} /> {s.delete_user}</button>
          )}
        </div>
      </div>

      {user?.deleted_at && (
        <div className="uo-deleted">
          <span className="uo-deleted-tag">{s.deleted_badge}</span>
          <span className="min-w-0 flex-1">{s.deleted_note.replace('{d}', jalali(user.deleted_at, true, lang)).replace('{r}', user.delete_reason || '—')}</span>
          <Link to="/users/deleted" className="uo-invoice-link">{s.view_archive}</Link>
        </div>
      )}

      <Alert>{err}</Alert>

      <div className="card p-0 uo-wrap">
        <div className="uo-tabs">
          {FILTERS.map(([k, key, fn]) => (
            <button key={k} type="button" className={'uo-tab' + (filter === k ? ' on' : '')} onClick={() => setFilter(k)}>
              {s[key]} <span className="uo-tab-n mono-num">{digits(fc(fn), lang)}</span>
            </button>
          ))}
        </div>

        {rows === null ? (
          <div className="grid place-items-center py-16"><Spinner /></div>
        ) : shown.length === 0 ? (
          <div className="py-12 text-center text-sm text-muted">{s.none}</div>
        ) : (
          <table className="uo-table">
            <thead>
              <tr>
                <th>{s.col_order}</th><th>{s.col_date}</th><th>{s.col_plan}</th>
                <th>{s.col_amount}</th><th>{s.col_method}</th><th>{s.col_status}</th>
                <th>{s.col_confirmer}</th><th>{s.col_account}</th><th className="uo-c">{s.col_invoice}</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((o) => (
                <tr key={o.id} className="uo-row">
                  <td data-label={s.col_order}>
                    <span className="uo-mono">#{digits(o.id, lang)}</span>
                    <span className="uo-type-tag">{s[TYPE_TAG[o.type]] || o.type}</span>
                  </td>
                  <td data-label={s.col_date} className="uo-mono uo-date">{jalali(o.created_at, true, lang)}</td>
                  <td data-label={s.col_plan}>{(lang === 'en' ? o.plan_name_en : o.plan_name) || o.plan_name || '—'}</td>
                  <td data-label={s.col_amount} className="uo-mono">{toman(o.amount_unique, lang)}</td>
                  <td data-label={s.col_method}>{o.payment_method ? enumLabel(t, 'm_', o.payment_method) : '—'}</td>
                  <td data-label={s.col_status}><StatusPill status={o.status} t={t} /></td>
                  <td data-label={s.col_confirmer}>{confirmerLabel(o, s)}</td>
                  <td data-label={s.col_account} className="uo-mono">{o.requested_account_name || '—'}</td>
                  <td data-label={s.col_invoice} className="uo-c">
                    {o.payment_id ? (
                      <Link to={`/transactions/${o.payment_id}`} className="uo-invoice-link">
                        <Ico d={I.invoice} w={13} /> {s.invoice_link}
                      </Link>
                    ) : s.no_invoice}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

const CSS = `
.uo-back { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 600; color: var(--c-text-muted); }
.uo-back:hover { color: var(--c-primary); }
.uo-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 14px; }
.uo-head-r { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.uo-del-btn {
  display: inline-flex; align-items: center; gap: 5px; padding: 6px 12px; border-radius: 9px;
  font-size: 12px; font-weight: 600; white-space: nowrap;
  color: var(--c-danger); border: 1px solid color-mix(in srgb, var(--c-danger) 32%, transparent);
  background: color-mix(in srgb, var(--c-danger) 7%, transparent);
}
.uo-del-btn:hover { background: color-mix(in srgb, var(--c-danger) 15%, transparent); }
.uo-deleted { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; padding: 12px 14px; border-radius: 12px; font-size: 13px;
  color: var(--c-text); border: 1px solid color-mix(in srgb, var(--c-danger) 30%, transparent);
  background: color-mix(in srgb, var(--c-danger) 7%, transparent); }
.uo-deleted-tag { font-size: 11px; font-weight: 700; padding: 2px 9px; border-radius: 999px; color: #fff; background: var(--c-danger); }
.uo-title { display: flex; align-items: center; gap: 8px; font-size: 16px; font-weight: 800; color: var(--c-text-muted); }
.uo-idcell { display: flex; align-items: center; gap: 12px; }
.uo-av {
  width: 44px; height: 44px; border-radius: 13px; flex-shrink: 0; color: #fff;
  display: grid; place-items: center; font-weight: 700; font-size: 14px; letter-spacing: .02em;
}
.uo-uname { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; font-family: 'JetBrains Mono', ui-monospace, monospace; font-weight: 700; font-size: 14.5px; }
.uo-sub { display: block; font-size: 12px; color: var(--c-text-muted); margin-top: 2px; }
.uo-src-tag {
  display: inline-flex; align-items: center; gap: 4px; font-family: var(--font-sans, inherit);
  font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 999px;
}
.uo-src-tag.bot { background: color-mix(in srgb, #0891B2 15%, transparent); color: #0891B2; }
.uo-src-tag.site { background: color-mix(in srgb, #7C3AED 15%, transparent); color: #7C3AED; }

.uo-wrap { overflow-x: auto; }
.uo-tabs { display: flex; gap: 3px; padding: 10px 12px; overflow-x: auto; border-bottom: 1px solid var(--c-border); }
.uo-tab {
  display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px; border-radius: 999px;
  font-size: 12.5px; font-weight: 600; color: var(--c-text-muted); background: transparent; border: 0;
  white-space: nowrap; cursor: pointer; transition: .15s;
}
.uo-tab:hover { color: var(--c-text); background: color-mix(in srgb, var(--c-text-muted) 8%, transparent); }
.uo-tab.on { background: var(--c-primary); color: #fff; }
.uo-tab-n { opacity: .8; }

.uo-table { width: 100%; min-width: 900px; border-collapse: collapse; font-size: 13px; }
.uo-table thead th {
  text-align: start; font-weight: 600; font-size: 11.5px; text-transform: uppercase; letter-spacing: .03em;
  color: var(--c-text-muted); padding: 12px 16px; white-space: nowrap; border-bottom: 1px solid var(--c-border);
}
.uo-table td { padding: 11px 16px; vertical-align: middle; border-bottom: 1px solid var(--c-border); white-space: nowrap; }
.uo-row:hover > td { background: color-mix(in srgb, var(--c-primary) 5%, transparent); }
.uo-c { text-align: center; }
.uo-mono { font-family: 'JetBrains Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }
.uo-date { color: var(--c-text-muted); font-size: 12px; }
.uo-type-tag { margin-inline-start: 8px; font-size: 10px; font-weight: 600; padding: 1px 7px; border-radius: 999px; color: var(--c-text-muted); background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); }
.uo-pill { display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 11.5px; font-weight: 700; white-space: nowrap; }
.uo-invoice-link { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; font-weight: 600; color: var(--c-primary); }
.uo-invoice-link:hover { text-decoration: underline; }

/* mobile: table -> stacked cards */
@media (max-width: 900px) {
  .uo-wrap { overflow-x: visible; }
  .uo-table, .uo-table tbody, .uo-table tr, .uo-table td { display: block; width: 100%; }
  .uo-table { min-width: 0; }
  .uo-table thead { display: none; }
  .uo-table tr.uo-row { border: 1px solid var(--c-border); border-radius: 12px; margin: 12px; padding: 4px 0; }
  .uo-table tr.uo-row:hover > td { background: none; }
  .uo-table td { border: 0 !important; padding: 9px 14px; display: flex; align-items: center; justify-content: space-between; gap: 12px; text-align: end; white-space: normal; }
  .uo-table td::before { content: attr(data-label); font-size: 11px; font-weight: 600; color: var(--c-text-muted); text-align: start; white-space: nowrap; }
  .uo-table td.uo-c { justify-content: space-between; text-align: end; }
}
`
