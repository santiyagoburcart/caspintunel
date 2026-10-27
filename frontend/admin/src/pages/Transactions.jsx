import { Fragment, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useConfirm } from '../components/ConfirmDialog'
import { useToast } from '../components/Toast'
import { useI18n, enumLabel } from '../lib/i18n'
import { jalali, toman, digits } from '../lib/format'
import { Alert, Spinner } from '../components/ui'
import { ReceiptThumb } from '../components/ReceiptThumb'
import { DateRangeModal, DRP_CSS } from '../components/DateRangePicker'
import { BankFilterSheet, BFS_CSS } from '../components/BankFilterSheet'

const TXS = {
  fa: { month: 'واریزی‌های این ماه', today: 'واریزی‌های امروز', queue: 'در صف بررسی', rejected: 'رد شده',
    tx_n: '{n} تراکنش', pending_n: '{n} مورد نیازمند تأیید', rej_n: '{n} مورد' },
  en: { month: "This month's deposits", today: "Today's deposits", queue: 'In review queue', rejected: 'Rejected',
    tx_n: '{n} transactions', pending_n: '{n} awaiting approval', rej_n: '{n} items' },
}

const TF = {
  fa: { filter_dates: 'بازهٔ تاریخ', filter_banks: 'بانک‌ها و روش‌ها' },
  en: { filter_dates: 'Date range', filter_banks: 'Banks & methods' },
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

function TxStats({ lang, version }) {
  const x = TXS[lang] || TXS.fa
  const [d, setD] = useState({})
  useEffect(() => {
    const acc = (p) => api.get(`/admin/accounting/?period=${p}`).then((r) => r.data).catch(() => null)
    const cnt = (st) => api.get(`/admin/transactions/?status=${st}&limit=1`).then((r) => r.data.count).catch(() => null)
    Promise.all([acc('monthly'), acc('daily'), cnt('pending'), cnt('rejected')])
      .then(([m, t, pend, rej]) => setD({ m, t, pend, rej }))
  }, [version])
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

export const T = {
  fa: {
    title: 'تراکنش‌ها',
    all: 'همه', pending: 'در انتظار', approved: 'تأییدشده', rejected: 'ردشده',
    amount: 'مبلغ', user: 'کاربر', method: 'روش', card: 'کارت', confirmer: 'تأییدکننده',
    date: 'تاریخ', receipt: 'رسید', status: 'وضعیت', none: 'تراکنشی نیست', reason: 'دلیل رد',
    by_admin: 'ادمین', by_system: 'سیستم پیامک', src_site: 'سایت', src_bot: 'ربات',
    type_col: 'نوع', src_col: 'منبع',
    type_new: 'خرید جدید', type_renew: 'تمدید', type_addon_volume: 'افزودن حجم',
    not_delivered: 'پرداخت تأییدشده ولی سرویس تحویل نشده — به‌صورت خودکار تلاش مجدد می‌شود',
    details: 'جزئیات',
    tx_col: 'شماره تراکنش', search: 'جستجو: TX-000123، کاربر، اکانت…', show_deleted: 'نمایش حذف‌شده‌ها', csv: 'خروجی CSV',
    del: 'حذف', restore: 'بازگردانی', deleted: 'حذف‌شده', sel_n: '{n} انتخاب‌شده', del_sel: 'حذف انتخاب‌شده‌ها', restore_sel: 'بازگردانی انتخاب‌شده‌ها',
    del_title: 'حذف تراکنش', del_bulk_title: 'حذف {n} تراکنش',
    del_msg: 'تراکنش از فهرست و از همهٔ جمع‌ها (کارت‌های این صفحه، حسابداری، تحلیل‌ها و گزارش‌ها) حذف می‌شود. تا ۳۰ روز قابل بازگردانی است.',
    reason: 'دلیل حذف (الزامی)', order: 'سفارش', service: 'سرویس', no_service: 'این سفارش سرویسی ندارد.',
    pending_note: 'این پرداخت هنوز در انتظار است؛ سفارشش بسته (لغو) می‌شود تا هیچ پیامکی آن را تأیید نکند.',
    act_keep: 'سرویس بماند (پیش‌فرض)', act_disable: 'سفارش لغو و سرویس روی PasarGuard غیرفعال شود', act_delete: 'سفارش لغو و سرویس روی PasarGuard حذف شود (برگشت‌ناپذیر)',
    bulk_act_note: 'گزینهٔ سرویس برای هر تراکنشی که سرویس دارد اعمال می‌شود.',
    restore_title: 'بازگردانی تراکنش', restore_msg: 'تراکنش دوباره در فهرست و جمع‌ها حساب می‌شود و وضعیت سفارش برمی‌گردد. تغییرات PasarGuard برنمی‌گردد.',
    done_del: 'حذف شد', done_restore: 'بازگردانده شد', will: 'آنچه انجام می‌شود',
    res_kept: 'سرویس دست‌نخورده ماند', res_no_service: 'سرویسی نداشت', res_disabled: 'سرویس {u} روی PasarGuard غیرفعال شد',
    res_deleted: 'سرویس {u} از PasarGuard حذف شد', res_missing_on_panel: 'سرویس {u} روی PasarGuard نبود؛ اینجا غیرفعال شد', bulk_res: '{ok} انجام شد، {failed} ناموفق', until: 'قابل بازگردانی تا',
  },
  en: {
    title: 'Transactions',
    all: 'All', pending: 'Pending', approved: 'Approved', rejected: 'Rejected',
    amount: 'Amount', user: 'User', method: 'Method', card: 'Card', confirmer: 'Confirmed by',
    date: 'Date', receipt: 'Receipt', status: 'Status', none: 'No transactions', reason: 'Reject reason',
    by_admin: 'admin', by_system: 'SMS system', src_site: 'Website', src_bot: 'Bot',
    type_col: 'Type', src_col: 'Source',
    type_new: 'New purchase', type_renew: 'Renewal', type_addon_volume: 'Add-on volume',
    not_delivered: 'Payment approved but service not delivered — auto-retrying',
    details: 'Details',
    tx_col: 'Transaction', search: 'Search: TX-000123, user, account…', show_deleted: 'Show deleted', csv: 'Export CSV',
    del: 'Delete', restore: 'Restore', deleted: 'Deleted', sel_n: '{n} selected', del_sel: 'Delete selected', restore_sel: 'Restore selected',
    del_title: 'Delete transaction', del_bulk_title: 'Delete {n} transactions',
    del_msg: 'The transaction leaves the list and every total (this page’s cards, Accounting, Analytics and reports). It can be restored for 30 days.',
    reason: 'Reason (required)', order: 'Order', service: 'Service', no_service: 'This order has no service.',
    pending_note: 'This payment is still pending; its order is closed (cancelled) so no SMS can approve it.',
    act_keep: 'Keep the service (default)', act_disable: 'Cancel the order and disable the service on PasarGuard', act_delete: 'Cancel the order and delete the service on PasarGuard (cannot be undone)',
    bulk_act_note: 'The service choice applies to each transaction that has a service.',
    restore_title: 'Restore transaction', restore_msg: 'The transaction counts again in the list and totals and its order status comes back. PasarGuard changes are not undone.',
    done_del: 'Deleted', done_restore: 'Restored', will: 'What will happen',
    res_kept: 'service left as it was', res_no_service: 'it had no service', res_disabled: 'service {u} disabled on PasarGuard',
    res_deleted: 'service {u} deleted from PasarGuard', res_missing_on_panel: 'service {u} was not on PasarGuard; disabled here', bulk_res: '{ok} done, {failed} failed', until: 'Restorable until',
  },
}

const FILTERS = ['', 'pending', 'approved', 'rejected']
const ST_TONE = { pending: 'warning', approved: 'success', rejected: 'danger' }

const groupCard = (raw) => {
  const s = String(raw || '').replace(/\D/g, '')
  return s.length >= 12 ? s.replace(/(.{4})(?=.)/g, '$1 ') : (raw || '—')
}

function Pill({ tone, children }) {
  const c = `var(--c-${tone || 'text-muted'})`
  const fg = `var(--c-${!tone || tone === 'text-muted' ? 'muted' : tone}-fg)`   // contrast-safe text
  return (
    <span className="tx-pill" style={{ background: `color-mix(in srgb, ${c} 16%, transparent)`, color: fg }}>{children}</span>
  )
}

export default function Transactions() {
  const { lang, t } = useI18n()
  const s = T[lang] || T.fa

  return (
    <div className="tx space-y-3">
      <style>{DRP_CSS}{BFS_CSS}{CSS}</style>
      <h1 className="text-lg font-bold">{s.title}</h1>
      <TxTable s={s} t={t} lang={lang} />
    </div>
  )
}

// Super Admin: delete = void (soft delete) with a reason; order / service choice (default keep)
function ServiceChoice({ box, s, actions }) {
  const [v, setV] = useState(box.v)
  const pick = (x) => { box.v = x; setV(x) }
  return (
    <div className="tx-choice" role="radiogroup">
      {actions.map((a) => (
        <label key={a} className="tx-choice-i" data-on={v === a || undefined} data-danger={a === 'delete' || undefined}>
          <input type="radio" name="tx-svc" value={a} checked={v === a} onChange={() => pick(a)} />
          <span>{s['act_' + a]}</span>
        </label>
      ))}
      <p className="tx-will" data-danger={v === 'delete' || undefined}>{s.will}: <b>{s['act_' + v]}</b></p>
    </div>
  )
}

// the option the person SEES checked is the one sent (v1.25.1: a lost choice once became "keep")
const chosen = (box) => document.querySelector('input[name="tx-svc"]:checked')?.value || box.v

const resultText = (s, r, svcName) => (r && s['res_' + r] ? s['res_' + r].replace('{u}', svcName || '') : '')

function DeleteDetails({ p, s, t, lang }) {
  return (
    <dl className="tx-dl">
      <div><dt>{s.tx_col}</dt><dd className="tx-mono">{p.tx_number}</dd></div>
      <div><dt>{s.amount}</dt><dd>{toman(p.amount, lang)}</dd></div>
      <div><dt>{s.order}</dt><dd className="tx-mono">#{p.order.id} · {p.order.user} · {enumLabel(t, 'os_', p.order.status)}</dd></div>
      <div><dt>{s.service}</dt><dd className="tx-mono">{p.service ? `${p.service.panel_username} · ${p.service.status}${p.service.panel ? ' · ' + p.service.panel : ''}` : s.no_service}</dd></div>
    </dl>
  )
}

export function useTxDelete(s, t, lang, done) {
  const confirm = useConfirm()
  const toast = useToast()
  const del = async (r) => {
    let p
    try { p = (await api.get(`/admin/transactions/${r.id}/delete-preview/`)).data } catch (e) { toast.error(apiError(e)); return }
    const box = { v: p.default_action }
    let res
    const ok = await confirm({
      tone: 'danger', title: s.del_title, message: s.del_msg, confirmLabel: s.del,
      reason: { label: s.reason, required: true },
      content: (
        <div className="tx-del">
          <DeleteDetails p={p} s={s} t={t} lang={lang} />
          {p.pending && <p className="tx-note-warn">{s.pending_note}</p>}
          <ServiceChoice box={box} s={s} actions={p.actions} />
        </div>
      ),
      action: async (reason) => { res = (await api.post(`/admin/transactions/${r.id}/delete/`, { reason, service_action: chosen(box) })).data },
    })
    if (ok) { toast.success(`${s.done_del} · ${resultText(s, res?.service_result, p.service?.panel_username)}`); done() }
  }
  const restore = async (r) => {
    const ok = await confirm({
      tone: 'primary', title: s.restore_title, message: s.restore_msg, confirmLabel: s.restore,
      targetLabel: s.tx_col, targetId: r.tx_number,
      action: async () => { await api.post(`/admin/transactions/${r.id}/restore/`) },
    })
    if (ok) { toast.success(s.done_restore); done() }
  }
  const bulk = async (rows, restoring) => {
    const box = { v: 'keep' }
    let res
    const ok = await confirm(restoring ? {
      tone: 'primary', title: s.restore_sel, message: s.restore_msg, confirmLabel: s.restore,
      badge: s.sel_n.replace('{n}', digits(rows.length, lang)),
      action: async () => { res = (await api.post('/admin/transactions/bulk-restore/', { ids: rows.map((r) => r.id) })).data },
    } : {
      tone: 'danger', title: s.del_bulk_title.replace('{n}', digits(rows.length, lang)), message: s.del_msg, confirmLabel: s.del,
      reason: { label: s.reason, required: true },
      content: (
        <div className="tx-del">
          <ul className="tx-bulk-list">{rows.slice(0, 12).map((r) => <li key={r.id} className="tx-mono">{r.tx_number} · {toman(r.amount, lang)} · {r.user}</li>)}{rows.length > 12 && <li>…</li>}</ul>
          <p className="text-xs text-muted">{s.bulk_act_note}</p>
          <ServiceChoice box={box} s={s} actions={['keep', 'disable', 'delete']} />
        </div>
      ),
      action: async (reason) => { res = (await api.post('/admin/transactions/bulk-delete/', { ids: rows.map((r) => r.id), reason, service_action: chosen(box) })).data },
    })
    if (ok && res) {
      const msg = s.bulk_res.replace('{ok}', digits(res.ok, lang)).replace('{failed}', digits(res.failed, lang))
      res.failed ? toast.error(msg + ' — ' + res.results.filter((x) => !x.ok).map((x) => x.detail).join(' · ')) : toast.success(msg)
      done()
    }
  }
  return { del, restore, bulk }
}

function TxTable({ s, t, lang }) {
  const navigate = useNavigate()
  const { staff } = useAuth()
  const superadmin = !!staff?.is_superadmin
  const toast = useToast()
  const [q, setQ] = useState('')
  const [search, setSearch] = useState('')
  const [showDeleted, setShowDeleted] = useState(false)
  const [sel, setSel] = useState(() => new Set())
  const [version, setVersion] = useState(0)
  const timer = useRef(null)
  const onSearch = (v) => { setQ(v); clearTimeout(timer.current); timer.current = setTimeout(() => setSearch(v.trim()), 350) }
  const reload = () => { setSel(new Set()); setVersion((x) => x + 1) }
  const { del, restore, bulk } = useTxDelete(s, t, lang, reload)
  const f = TF[lang] || TF.fa
  const [rows, setRows] = useState(null)
  const [status, setStatus] = useState('')
  const [range, setRange] = useState({ from: '', to: '' })
  const [dateOpen, setDateOpen] = useState(false)
  const [bankOpen, setBankOpen] = useState(false)
  const [bankFilter, setBankFilter] = useState({ banks: [], methods: [] })
  const [err, setErr] = useState('')

  const load = () => {
    setRows(null); setErr('')
    const p = new URLSearchParams()
    if (status) p.set('status', status)
    if (range.from) p.set('from', range.from)
    if (range.to) p.set('to', range.to)
    if (search) p.set('search', search)
    if (superadmin && showDeleted) p.set('deleted', '1')
    api.get(`/admin/transactions/?${p}`)
      .then((r) => setRows(r.data.results ?? r.data))
      .catch(() => { setRows([]); setErr(lang === 'fa' ? 'خطا در دریافت' : 'Failed to load') })
  }
  useEffect(() => { load() }, [status, range.from, range.to, search, showDeleted, version])

  const exportCsv = async () => {
    const p = new URLSearchParams({ export: 'csv', lang })
    if (status) p.set('status', status)
    if (range.from) p.set('from', range.from)
    if (range.to) p.set('to', range.to)
    if (search) p.set('search', search)
    if (superadmin && showDeleted) p.set('deleted', '1')
    try {
      const r = await api.get(`/admin/transactions/?${p}`, { responseType: 'blob' })
      const name = (r.headers['content-disposition'] || '').match(/filename="([^"]+)"/)?.[1] || 'transactions.csv'
      const a = document.createElement('a')
      a.href = URL.createObjectURL(r.data); a.download = name
      document.body.appendChild(a); a.click(); a.remove()
      setTimeout(() => URL.revokeObjectURL(a.href), 2000)
    } catch (e) { toast.error(apiError(e)) }
  }

  const confirmer = (r) => {
    if (!r.confirmer) return '—'
    if (r.confirmer === 'admin') return s.by_admin
    if (r.confirmer === 'SMS system') return s.by_system
    return r.confirmer
  }

  const bankActive = bankFilter.banks.length + bankFilter.methods.length
  const filtered = (rows || []).filter((r) => (
    (bankFilter.banks.length === 0 || bankFilter.banks.includes(r.card_bank))
    && (bankFilter.methods.length === 0 || bankFilter.methods.includes(r.method))
  ))

  return (
    <>
      <TxStats lang={lang} version={version} />
      <Alert>{err}</Alert>
      <div className="tx-filter-row">
        <div className="flex flex-wrap gap-2">
          {FILTERS.map((ft) => (
            <button key={ft || 'all'} type="button" onClick={() => setStatus(ft)}
              className={`btn-ghost text-sm ${status === ft ? 'tx-filter-on' : ''}`}>
              {ft ? s[ft] : s.all}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="tx-tool-btn" onClick={() => setDateOpen(true)}>
            {f.filter_dates}{range.from && <span className="acc-tool-badge" dir="ltr">{range.from}→{range.to}</span>}
          </button>
          <button type="button" className="tx-tool-btn" onClick={() => setBankOpen(true)}>
            {f.filter_banks}{bankActive > 0 && <span className="bfs-count-badge">{digits(bankActive, lang)}</span>}
          </button>
          <button type="button" className="tx-tool-btn" onClick={exportCsv}>{s.csv}</button>
        </div>
      </div>
      <div className="tx-filter-row">
        <input className="input tx-search" type="search" value={q} onChange={(e) => onSearch(e.target.value)} placeholder={s.search} aria-label={s.search} />
        {superadmin && (
          <label className="tx-show-del"><input type="checkbox" checked={showDeleted} onChange={(e) => { setShowDeleted(e.target.checked); setSel(new Set()) }} />{s.show_deleted}</label>
        )}
      </div>
      {superadmin && sel.size > 0 && (() => {
        const picked = filtered.filter((r) => sel.has(r.id))
        const live = picked.filter((r) => !r.voided)
        const gone = picked.filter((r) => r.voided)
        return (
          <div className="card tx-bulk">
            <span>{s.sel_n.replace('{n}', digits(sel.size, lang))}</span>
            {live.length > 0 && <button type="button" className="tx-del-btn" onClick={() => bulk(live, false)}>{s.del_sel} ({digits(live.length, lang)})</button>}
            {gone.length > 0 && <button type="button" className="tx-detail-btn" onClick={() => bulk(gone, true)}>{s.restore_sel} ({digits(gone.length, lang)})</button>}
          </div>
        )
      })()}

      <DateRangeModal open={dateOpen} onClose={() => setDateOpen(false)} onApply={setRange} />
      <BankFilterSheet open={bankOpen} onClose={() => setBankOpen(false)} value={bankFilter} onApply={setBankFilter} />

      {rows === null ? (
        <div className="grid place-items-center py-16"><Spinner /></div>
      ) : filtered.length === 0 ? (
        <div className="card text-center text-muted">{s.none}</div>
      ) : (
        <div className="card p-0 tx-wrap">
          <table className="tx-table">
            <thead>
              <tr>
                {superadmin && <th className="tx-c"><input type="checkbox" aria-label={s.sel_n.replace('{n}', '')}
                  checked={filtered.length > 0 && filtered.every((r) => sel.has(r.id))}
                  onChange={(e) => setSel(e.target.checked ? new Set(filtered.map((r) => r.id)) : new Set())} /></th>}
                <th>{s.tx_col}</th><th>{s.amount}</th><th>{s.user}</th><th>{s.type_col}</th><th>{s.src_col}</th>
                <th>{s.method}</th><th>{s.card}</th>
                <th>{s.confirmer}</th><th>{s.date}</th><th>{s.status}</th>
                <th className="tx-c">{s.receipt}</th><th className="tx-c" aria-label="actions" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => {
                const note = r.status === 'rejected' && r.reject_reason
                  ? `${s.reason}: ${r.reject_reason}`
                  : (r.status === 'approved' && r.order_status === 'paid' ? `⚠ ${s.not_delivered}` : null)
                return (
                  <Fragment key={r.id}>
                    <tr className={'tx-row' + (note ? ' tx-row--note' : '') + (r.voided ? ' tx-row--void' : '')}>
                      {superadmin && <td className="tx-c"><input type="checkbox" checked={sel.has(r.id)} aria-label={r.tx_number}
                        onChange={(e) => setSel((old) => { const n = new Set(old); e.target.checked ? n.add(r.id) : n.delete(r.id); return n })} /></td>}
                      <td className="tx-mono tx-num" data-label={s.tx_col}>{r.tx_number}{r.voided && <Pill tone="danger">{s.deleted}</Pill>}</td>
                      <td className="tx-amt" data-label={s.amount}>{toman(r.amount, lang)}</td>
                      <td data-label={s.user}>
                        <span className="tx-user">{r.user}</span>
                        {r.plan_name && <span className="tx-sub">{r.plan_name}</span>}
                      </td>
                      <td data-label={s.type_col}>{s['type_' + r.order_type] || r.order_type || '—'}</td>
                      <td data-label={s.src_col}>{r.order_source === 'bot' ? s.src_bot : s.src_site}</td>
                      <td data-label={s.method}>{r.method ? enumLabel(t, 'm_', r.method) : '—'}</td>
                      <td dir="ltr" className="tx-mono tx-card" data-label={s.card}>{groupCard(r.card)}</td>
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
                        {superadmin && !r.voided && <button type="button" className="tx-del-btn" onClick={() => del(r)}>{s.del}</button>}
                        {superadmin && r.voided && r.restorable_until && new Date(r.restorable_until) > new Date() && (
                          <button type="button" className="tx-detail-btn" onClick={() => restore(r)}>{s.restore}</button>
                        )}
                      </td>
                    </tr>
                    {(note || r.voided) && (
                      <tr className="tx-note-row">
                        <td colSpan={superadmin ? 13 : 12}>
                          {r.voided
                            ? <span className="tx-note-bad">{s.deleted}: {r.void_reason} · {r.voided_by || '—'} · {jalali(r.voided_at, true, lang)} · {s.until} {jalali(r.restorable_until, false, lang)}</span>
                            : <span className={r.status === 'rejected' ? 'tx-note-bad' : 'tx-note-warn'}>{note}</span>}
                        </td>
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


const CSS = `
.tx-search { flex: 1 1 260px; max-width: 420px; }
.tx-show-del { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; }
.tx-num { white-space: nowrap; font-weight: 700; }
.tx-num .tx-pill { margin-inline-start: 6px; }
.tx-row--void td { opacity: .6; }
.tx-row--void td.tx-c { opacity: 1; }
.tx-del-btn { display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; border-radius: 8px; font-size: 12px; font-weight: 700;
  border: 1px solid color-mix(in srgb, var(--c-danger) 40%, transparent); color: var(--c-danger-fg); background: transparent; margin-inline-start: 6px; }
.tx-del-btn:hover { background: color-mix(in srgb, var(--c-danger) 10%, transparent); }
.tx-bulk { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; padding: 10px 14px; font-size: 13px; font-weight: 600; }
.tx-del { display: flex; flex-direction: column; gap: 10px; margin-top: 8px; text-align: start; }
.tx-dl { display: grid; gap: 6px; font-size: 13px; }
.tx-dl > div { display: flex; justify-content: space-between; gap: 10px; }
.tx-dl dt { color: var(--c-text-muted); font-weight: 600; }
.tx-dl dd { overflow-wrap: anywhere; text-align: end; }
.tx-choice { display: flex; flex-direction: column; gap: 6px; }
.tx-choice-i { display: flex; align-items: flex-start; gap: 8px; padding: 8px 10px; border-radius: 10px; border: 1px solid var(--c-border); font-size: 13px; cursor: pointer; }
.tx-choice-i[data-on] { border-color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 8%, transparent); }
.tx-choice-i[data-on][data-danger] { border-color: var(--c-danger); background: color-mix(in srgb, var(--c-danger) 8%, transparent); }
.tx-choice-i input { margin-top: 3px; }
.tx-will { font-size: 12.5px; margin-top: 2px; }
.tx-will[data-danger] b { color: var(--c-danger-fg); }
.tx-bulk-list { font-size: 12px; max-height: 140px; overflow: auto; }
.tx-filter-row { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: space-between; }
.tx-tool-btn { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 10px; font-size: 12.5px; font-weight: 600;
  border: 1px solid var(--c-border); background: transparent; color: var(--c-text-muted); }
.tx-tool-btn:hover { color: var(--c-primary); border-color: var(--c-primary); }
.acc-tool-badge { font-family: 'JetBrains Mono', monospace; font-size: 10.5px; color: var(--c-primary); }

.tx-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 4px; }
@media (min-width: 900px) { .tx-stats { grid-template-columns: repeat(4, 1fr); } }
.tx-stat { position: relative; overflow: hidden; padding: 14px 16px; }
.tx-stat-label { font-size: 11.5px; font-weight: 600; color: var(--c-text-muted); }
.tx-stat-val { font-size: 19px; font-weight: 800; margin-top: 5px; letter-spacing: -.01em; }
.tx-stat-sub { font-size: 11px; color: var(--c-text-muted); margin-top: 4px; }
.tx-stat-accent { position: absolute; inset-inline: 0; bottom: 0; height: 3px; opacity: .85; }

.tx-filter-on { color: var(--c-primary); border-color: var(--c-primary); }
.tx-wrap { overflow-x: auto; }
@media (min-width: 768px) { .tx-table tr.tx-row > td { white-space: nowrap; } .tx-card { white-space: nowrap; } }
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

/* mobile: table -> stacked cards */
@media (max-width: 767px) {
  .tx-wrap { overflow-x: visible; }
  .tx-table, .tx-table tbody { display: block; width: 100%; }
  .tx-table { min-width: 0; }
  .tx-table thead { display: none; }
  .tx-table tr.tx-row {
    display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); align-items: start;
    border: 1px solid var(--c-border); border-radius: 12px; margin: 8px; padding: 2px 0; width: auto;
  }
  .tx-table tr.tx-row:hover > td { background: none; }
  .tx-table tr.tx-row > td { grid-column: span 2; border: 0 !important; padding: 3px 12px; display: flex; flex-direction: column;
    align-items: flex-start; gap: 1px; min-width: 0; text-align: start; font-size: 13px; overflow-wrap: anywhere; white-space: normal; }
  .tx-table tr.tx-row > td::before { content: attr(data-label); font-size: 12px; line-height: 16px; font-weight: 600; color: var(--c-text-muted); white-space: nowrap; }
  /* [amount ······ status] / user · date / type · source · method / card · confirmer / receipt · details */
  .tx-table tr.tx-row > td:nth-child(1) { grid-column: 1 / 5; grid-row: 1; font-size: 15px; font-weight: 800; padding-block: 7px; }
  .tx-table tr.tx-row > td:nth-child(9) { grid-column: 5 / 7; grid-row: 1; align-items: flex-end; padding-block: 7px; }
  .tx-table tr.tx-row > td:nth-child(1)::before, .tx-table tr.tx-row > td:nth-child(9)::before, .tx-table tr.tx-row > td:nth-child(11)::before { display: none; }
  /* DOM order packs into even rows of 6: user 3 + type 3 / source 2 + method 2 + card 2 / confirmer 2 + date 4 / receipt 2 + details 4 */
  .tx-table tr.tx-row > td:nth-child(2), .tx-table tr.tx-row > td:nth-child(3) { grid-column: span 3; }
  .tx-table tr.tx-row > td:nth-child(8), .tx-table tr.tx-row > td:nth-child(11) { grid-column: span 4; }
  .tx-table tr.tx-row > td:nth-child(11) { align-items: flex-end; justify-content: center; }
  .tx-table tr.tx-row > td:nth-child(10) img { width: 44px; height: 44px; }
  .tx-table tr.tx-note-row { display: block; margin: -4px 8px 8px; border: 0; padding: 0; }
  .tx-table tr.tx-note-row > td { display: block; padding: 0 12px 6px !important; border: 0 !important; }
  .tx-table tr.tx-note-row > td::before { display: none; }
  .tx-detail-btn { min-height: 44px; }
}
`
