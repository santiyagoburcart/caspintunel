import { Fragment, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useI18n, enumLabel } from '../lib/i18n'
import { jalali, toman, gb, digits } from '../lib/format'
import { Alert, Spinner } from '../components/ui'
import { ReceiptThumb } from '../components/ReceiptThumb'

const TXS = {
  fa: { month: 'واریزی‌های این ماه', today: 'واریزی‌های امروز', queue: 'در صف بررسی', rejected: 'رد شده',
    tx_n: '{n} تراکنش', pending_n: '{n} مورد نیازمند تأیید', rej_n: '{n} مورد' },
  en: { month: "This month's deposits", today: "Today's deposits", queue: 'In review queue', rejected: 'Rejected',
    tx_n: '{n} transactions', pending_n: '{n} awaiting approval', rej_n: '{n} items' },
}

function TxStat({ label, value, sub, tone, lang }) {
  return (
    <div className="card tx-stat">
      <span className="tx-stat-label">{label}</span>
      <div className="tx-stat-val">{value == null ? '—' : value}</div>
      {sub ? <div className="tx-stat-sub" style={tone ? { color: tone } : undefined}>{sub}</div> : null}
      <span className="tx-stat-accent" style={{ background: tone || 'var(--c-primary)' }} />
    </div>
  )
}

function TxStats({ lang }) {
  const x = TXS[lang] || TXS.fa
  const [d, setD] = useState({})
  useEffect(() => {
    const acc = (p) => api.get(`/admin/accounting/?period=${p}`).then((r) => r.data).catch(() => null)
    const cnt = (st) => api.get(`/admin/transactions/?status=${st}&limit=1`).then((r) => r.data.count).catch(() => null)
    Promise.all([acc('monthly'), acc('daily'), cnt('pending'), cnt('rejected')])
      .then(([m, t, pend, rej]) => setD({ m, t, pend, rej }))
  }, [])
  return (
    <div className="tx-stats">
      <TxStat label={x.month} value={d.m ? toman(d.m.revenue, lang) : null}
        sub={d.m ? x.tx_n.replace('{n}', digits(d.m.transactions, lang)) : ''} tone="#1464BA" lang={lang} />
      <TxStat label={x.today} value={d.t ? toman(d.t.revenue, lang) : null}
        sub={d.t ? x.tx_n.replace('{n}', digits(d.t.transactions, lang)) : ''} tone="#11AB53" lang={lang} />
      <TxStat label={x.queue} value={d.pend == null ? null : digits(d.pend, lang)}
        sub={d.pend == null ? '' : x.pending_n.replace('{n}', digits(d.pend, lang))} tone="#D97706" lang={lang} />
      <TxStat label={x.rejected} value={d.rej == null ? null : digits(d.rej, lang)}
        sub={d.rej == null ? '' : x.rej_n.replace('{n}', digits(d.rej, lang))} tone="#EF4444" lang={lang} />
    </div>
  )
}

const T = {
  fa: {
    title: 'تراکنش‌ها', services_tab: 'سرویس‌های فروخته‌شده',
    all: 'همه', pending: 'در انتظار', approved: 'تأییدشده', rejected: 'ردشده',
    amount: 'مبلغ', user: 'کاربر', method: 'روش', card: 'کارت', confirmer: 'تأییدکننده',
    date: 'تاریخ', receipt: 'رسید', status: 'وضعیت', none: 'تراکنشی نیست', reason: 'دلیل رد',
    by_admin: 'ادمین', by_system: 'سیستم پیامک', src_site: 'سایت', src_bot: 'ربات',
    type_col: 'نوع', src_col: 'منبع',
    type_new: 'خرید جدید', type_renew: 'تمدید', type_addon_volume: 'افزودن حجم',
    scheduled_renewal: 'تمدید زمان‌بندی‌شده',
    not_delivered: 'پرداخت تأییدشده ولی سرویس تحویل نشده — به‌صورت خودکار تلاش مجدد می‌شود',
    details: 'جزئیات',
    account: 'نام کاربری', plan: 'پلن', usage: 'مصرف', expiry: 'انقضا', conn: 'اتصال',
    online: 'آنلاین', offline: 'آفلاین', unlimited: 'نامحدود', no_services: 'سرویسی فروخته نشده',
    on_first_conn: 'با اولین اتصال', timeless: 'بدون انقضا',
  },
  en: {
    title: 'Transactions', services_tab: 'Purchased services',
    all: 'All', pending: 'Pending', approved: 'Approved', rejected: 'Rejected',
    amount: 'Amount', user: 'User', method: 'Method', card: 'Card', confirmer: 'Confirmed by',
    date: 'Date', receipt: 'Receipt', status: 'Status', none: 'No transactions', reason: 'Reject reason',
    by_admin: 'admin', by_system: 'SMS system', src_site: 'Website', src_bot: 'Bot',
    type_col: 'Type', src_col: 'Source',
    type_new: 'New purchase', type_renew: 'Renewal', type_addon_volume: 'Add-on volume',
    scheduled_renewal: 'Scheduled renewal',
    not_delivered: 'Payment approved but service not delivered — auto-retrying',
    details: 'Details',
    account: 'Account', plan: 'Plan', usage: 'Usage', expiry: 'Expiry', conn: 'Connection',
    online: 'Online', offline: 'Offline', unlimited: 'unlimited', no_services: 'No services sold yet',
    on_first_conn: 'on first connection', timeless: 'no expiry',
  },
}

const FILTERS = ['', 'pending', 'approved', 'rejected']
const ST_TONE = { pending: 'warning', approved: 'success', rejected: 'danger' }
const SVC_TONE = { active: 'success', on_hold: 'warning', pending: 'warning', limited: 'warning', expired: 'danger', disabled: 'danger' }

const groupCard = (raw) => {
  const s = String(raw || '').replace(/\D/g, '')
  return s.length >= 12 ? s.replace(/(.{4})(?=.)/g, '$1 ') : (raw || '—')
}

function Pill({ tone, children }) {
  const c = `var(--c-${tone || 'text-muted'})`
  return (
    <span className="tx-pill" style={{ background: `color-mix(in srgb, ${c} 16%, transparent)`, color: c }}>{children}</span>
  )
}

export default function Transactions() {
  const { lang, t } = useI18n()
  const s = T[lang] || T.fa
  const [tab, setTab] = useState('tx')

  return (
    <div className="tx space-y-3">
      <style>{CSS}</style>
      <div className="tx-tabs">
        <button type="button" className={tab === 'tx' ? 'on' : ''} onClick={() => setTab('tx')}>{s.title}</button>
        <button type="button" className={tab === 'services' ? 'on' : ''} onClick={() => setTab('services')}>{s.services_tab}</button>
      </div>
      {tab === 'tx' ? <TxTable s={s} t={t} lang={lang} /> : <ServicesTable s={s} t={t} lang={lang} />}
    </div>
  )
}

function TxTable({ s, t, lang }) {
  const navigate = useNavigate()
  const [rows, setRows] = useState(null)
  const [status, setStatus] = useState('')
  const [err, setErr] = useState('')

  const load = () => {
    setRows(null); setErr('')
    api.get(`/admin/transactions/${status ? `?status=${status}` : ''}`)
      .then((r) => setRows(r.data.results ?? r.data))
      .catch(() => { setRows([]); setErr(lang === 'fa' ? 'خطا در دریافت' : 'Failed to load') })
  }
  useEffect(load, [status])

  const confirmer = (r) => {
    if (!r.confirmer) return '—'
    if (r.confirmer === 'admin') return s.by_admin
    if (r.confirmer === 'SMS system') return s.by_system
    return r.confirmer
  }

  return (
    <>
      <TxStats lang={lang} />
      <Alert>{err}</Alert>
      <div className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button key={f || 'all'} type="button" onClick={() => setStatus(f)}
            className={`btn-ghost text-sm ${status === f ? 'tx-filter-on' : ''}`}>
            {f ? s[f] : s.all}
          </button>
        ))}
      </div>

      {rows === null ? (
        <div className="grid place-items-center py-16"><Spinner /></div>
      ) : rows.length === 0 ? (
        <div className="card text-center text-muted">{s.none}</div>
      ) : (
        <div className="card p-0 tx-wrap">
          <table className="tx-table">
            <thead>
              <tr>
                <th>{s.amount}</th><th>{s.user}</th><th>{s.type_col}</th><th>{s.src_col}</th>
                <th>{s.method}</th><th>{s.card}</th>
                <th>{s.confirmer}</th><th>{s.date}</th><th>{s.status}</th>
                <th className="tx-c">{s.receipt}</th><th className="tx-c" aria-label="actions" />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const note = r.status === 'rejected' && r.reject_reason
                  ? `${s.reason}: ${r.reject_reason}`
                  : (r.status === 'approved' && r.order_status === 'paid' ? `⚠ ${s.not_delivered}` : null)
                return (
                  <Fragment key={r.id}>
                    <tr className={'tx-row' + (note ? ' tx-row--note' : '')}>
                      <td className="tx-amt" data-label={s.amount}>{toman(r.amount, lang)}</td>
                      <td data-label={s.user}>
                        <span className="tx-user">{r.user}</span>
                        {r.plan_name && <span className="tx-sub">{r.plan_name}</span>}
                      </td>
                      <td data-label={s.type_col}>{s['type_' + r.order_type] || r.order_type || '—'}</td>
                      <td data-label={s.src_col}>{r.order_source === 'bot' ? s.src_bot : s.src_site}</td>
                      <td data-label={s.method}>{r.method ? enumLabel(t, 'm_', r.method) : '—'}</td>
                      <td dir="ltr" className="tx-mono" data-label={s.card}>{groupCard(r.card)}</td>
                      <td data-label={s.confirmer}>{confirmer(r)}</td>
                      <td className="tx-mono tx-date" data-label={s.date}>{jalali(r.created_at, true, lang)}</td>
                      <td data-label={s.status}><Pill tone={ST_TONE[r.status]}>{s[r.status] || r.status}</Pill></td>
                      <td className="tx-c" data-label={s.receipt}>{r.receipt_url ? <ReceiptThumb url={r.receipt_url} alt={s.receipt} /> : '—'}</td>
                      <td className="tx-c">
                        <button type="button" className="tx-detail-btn"
                          onClick={() => navigate(`/transactions/${r.id}`)}>
                          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor"
                            strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                          </svg>
                          {s.details}
                        </button>
                      </td>
                    </tr>
                    {note && (
                      <tr className="tx-note-row">
                        <td colSpan={11}><span className={r.status === 'rejected' ? 'tx-note-bad' : 'tx-note-warn'}>{note}</span></td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

const fmtData = (used, limit, s, lang) => {
  const u = `${digits(gb(used), lang)}`
  if (!limit) return `${u} / ${s.unlimited}`
  return `${u} / ${digits(gb(limit), lang)} GB`
}
const dataPct = (used, limit) => (limit ? Math.min(100, Math.round((used / limit) * 100)) : 0)

function ServicesTable({ s, t, lang }) {
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    api.get('/admin/services/')
      .then((r) => setRows(r.data.results ?? r.data))
      .catch(() => { setRows([]); setErr(lang === 'fa' ? 'خطا در دریافت' : 'Failed to load') })
  }, [])

  const expiry = (r) => {
    if (r.expire_strategy === 'never') return s.timeless
    if (r.status === 'on_hold' || !r.expire_at) return r.status === 'on_hold' ? s.on_first_conn : '—'
    return jalali(r.expire_at, false, lang)
  }

  return (
    <>
      <Alert>{err}</Alert>
      {rows === null ? (
        <div className="grid place-items-center py-16"><Spinner /></div>
      ) : rows.length === 0 ? (
        <div className="card text-center text-muted">{s.no_services}</div>
      ) : (
        <div className="card p-0 tx-wrap">
          <table className="tx-table">
            <thead>
              <tr>
                <th>{s.account}</th><th>{s.user}</th><th>{s.plan}</th><th>{s.status}</th>
                <th>{s.conn}</th><th>{s.usage}</th><th>{s.expiry}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr className="tx-row" key={r.id}>
                  <td dir="ltr" className="tx-mono" data-label={s.account}>{r.panel_username}</td>
                  <td data-label={s.user}>
                    <span className="tx-user">{r.user}</span>
                    {r.user_name ? <span className="tx-sub">{r.user_name}</span> : null}
                  </td>
                  <td data-label={s.plan}>
                    {(lang === 'fa' ? r.plan : r.plan_en) || r.plan || '—'}
                    {r.has_scheduled_renewal && <span className="tx-renewal-badge">{s.scheduled_renewal}</span>}
                  </td>
                  <td data-label={s.status}><Pill tone={SVC_TONE[r.status]}>{enumLabel(t, 'st_', r.status)}</Pill></td>
                  <td data-label={s.conn}>
                    <span className={'tx-conn ' + (r.is_online ? 'on' : 'off')}>
                      <i />{r.is_online ? s.online : s.offline}
                    </span>
                  </td>
                  <td data-label={s.usage}>
                    <div className="tx-usage">
                      <span className="tx-mono">{fmtData(r.data_used, r.data_limit, s, lang)}</span>
                      {r.data_limit ? (
                        <div className="tx-usage-bar"><i style={{ width: `${dataPct(r.data_used, r.data_limit)}%` }} /></div>
                      ) : null}
                    </div>
                  </td>
                  <td className="tx-mono tx-date" data-label={s.expiry}>{expiry(r)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

const CSS = `
.tx-renewal-badge {
  display: inline-block; margin-inline-start: 6px; padding: 1px 8px; border-radius: 999px;
  font-size: 10px; font-weight: 700; white-space: nowrap;
  color: var(--c-secondary); background: color-mix(in srgb, var(--c-secondary) 16%, transparent);
}
.tx-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 4px; }
@media (min-width: 900px) { .tx-stats { grid-template-columns: repeat(4, 1fr); } }
.tx-stat { position: relative; overflow: hidden; padding: 14px 16px; }
.tx-stat-label { font-size: 11.5px; font-weight: 600; color: var(--c-text-muted); }
.tx-stat-val { font-size: 19px; font-weight: 800; margin-top: 5px; letter-spacing: -.01em; }
.tx-stat-sub { font-size: 11px; color: var(--c-text-muted); margin-top: 4px; }
.tx-stat-accent { position: absolute; inset-inline: 0; bottom: 0; height: 3px; opacity: .85; }

.tx-tabs { display: inline-flex; gap: 4px; padding: 4px; border-radius: 12px; background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); }
.tx-tabs button { padding: 7px 16px; border-radius: 9px; font-size: 13px; font-weight: 600; color: var(--c-text-muted); }
.tx-tabs button.on { background: var(--c-primary); color: #fff; }

.tx-filter-on { color: var(--c-primary); border-color: var(--c-primary); }
.tx-wrap { overflow-x: auto; }
.tx-table { width: 100%; min-width: 760px; border-collapse: collapse; font-size: 13px; }
.tx-table thead th {
  text-align: start; font-weight: 600; font-size: 11.5px; text-transform: uppercase; letter-spacing: .03em;
  color: var(--c-text-muted); padding: 12px 14px; white-space: nowrap; border-bottom: 1px solid var(--c-border);
}
.tx-table td { padding: 11px 14px; vertical-align: middle; }
.tx-table tr.tx-row > td { border-bottom: 1px solid var(--c-border); }
.tx-table tr.tx-row--note > td { border-bottom: 0; }
.tx-table tr.tx-row:hover > td { background: color-mix(in srgb, var(--c-primary) 5%, transparent); }
.tx-detail-btn {
  display: inline-flex; align-items: center; gap: 5px; padding: 5px 11px; border-radius: 9px;
  font-size: 12px; font-weight: 600; white-space: nowrap;
  color: var(--c-primary); border: 1px solid color-mix(in srgb, var(--c-primary) 32%, transparent);
  background: color-mix(in srgb, var(--c-primary) 8%, transparent); transition: background .15s;
}
.tx-detail-btn:hover { background: color-mix(in srgb, var(--c-primary) 16%, transparent); }

.tx-amt { font-weight: 700; white-space: nowrap; }
.tx-user { display: block; font-weight: 500; }
.tx-sub { display: block; font-size: 11px; color: var(--c-text-muted); margin-top: 1px; }
.tx-mono { font-family: 'JetBrains Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }
.tx-date { white-space: nowrap; color: var(--c-text-muted); font-size: 12px; }
.tx-c { text-align: center; }
.tx-pill { display: inline-block; border-radius: 999px; padding: 3px 10px; font-size: 11.5px; font-weight: 600; white-space: nowrap; }

.tx-note-row > td { padding: 0 14px 10px !important; border-bottom: 1px solid var(--c-border) !important; }
.tx-note-warn, .tx-note-bad { font-size: 11.5px; }
.tx-note-warn { color: var(--c-warning); }
.tx-note-bad { color: var(--c-danger); }


.tx-conn { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; }
.tx-conn i { width: 7px; height: 7px; border-radius: 50%; }
.tx-conn.on { color: var(--c-success); } .tx-conn.on i { background: var(--c-success); }
.tx-conn.off { color: var(--c-text-muted); } .tx-conn.off i { background: var(--c-text-muted); }

.tx-usage { display: flex; flex-direction: column; gap: 4px; min-width: 120px; }
.tx-usage-bar { height: 5px; border-radius: 999px; overflow: hidden; background: color-mix(in srgb, var(--c-text-muted) 20%, transparent); }
.tx-usage-bar > i { display: block; height: 100%; background: var(--c-primary); border-radius: 999px; }

/* mobile: table -> stacked cards */
@media (max-width: 767px) {
  .tx-wrap { overflow-x: visible; }
  .tx-table, .tx-table tbody, .tx-table tr, .tx-table td { display: block; width: 100%; }
  .tx-table { min-width: 0; }
  .tx-table thead { display: none; }
  .tx-table tr.tx-row { border: 1px solid var(--c-border); border-radius: 12px; margin: 12px; padding: 4px 0; }
  .tx-table tr.tx-row > td { border-bottom: 0; }
  .tx-table tr.tx-row:hover > td { background: none; }
  .tx-table td { padding: 8px 14px; display: flex; align-items: center; justify-content: space-between; gap: 12px; text-align: end; }
  .tx-table td::before { content: attr(data-label); font-size: 11px; font-weight: 600; color: var(--c-text-muted); text-align: start; white-space: nowrap; }
  .tx-table td.tx-amt { border-bottom: 1px solid var(--c-border); font-size: 15px; }
  .tx-table td.tx-c { justify-content: space-between; }
  .tx-table tr.tx-note-row { margin: -6px 12px 12px; border: 0; padding: 0; }
  .tx-table tr.tx-note-row > td { display: block; padding: 0 14px 8px !important; border: 0 !important; }
  .tx-table tr.tx-note-row > td::before { display: none; }
  .tx-usage { min-width: 0; align-items: flex-end; }
  .tx-usage-bar { width: 100%; }
  .tx-detail-btn { width: 100%; justify-content: center; }
}
`
