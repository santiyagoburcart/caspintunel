import { useCallback, useEffect, useState } from 'react'
import { Link, NavLink, useNavigate, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { jalali, toman, gb, relTime } from '../lib/format'
import { Spinner, Toggle } from '../components/ui'
import { useConfirm } from '../components/ConfirmDialog'

// CRM (backend: apps/crm). Follow-up queue · case · customer 360 · leads · reports · settings.
const T = {
  fa: {
    title: 'CRM', sub: 'مشتریان، پیگیری عدم استفاده و سرنخ‌ها',
    t_queue: 'نیاز به پیگیری', t_leads: 'سرنخ‌ها', t_reports: 'گزارش‌ها', t_settings: 'تنظیمات',
    open: 'باز', closed: 'بسته', all_kinds: 'همهٔ انواع', all_reasons: 'همهٔ دلایل', no_reason: 'بدون دلیل', anyone: 'همه', me: 'سپرده به من', none: 'بدون مسئول',
    search: 'جستجو: کاربر، تلفن، سرویس…', empty: 'موردی نیست.', more: 'بیشتر', back: 'بازگشت',
    k: { no_connection: 'بدون اتصال', never_connected: 'هرگز وصل نشده', lead: 'سرنخ', manual: 'دستی' },
    oc: { resolved: 'حل شد', still_inactive: 'هنوز غیرفعال', lost: 'از دست رفت' },
    stg: { lead: 'سرنخ', new: 'جدید', active: 'فعال', at_risk: 'در خطر', expired: 'منقضی', churned: 'ریزش', won_back: 'بازگشته' },
    svc: { active: 'فعال', on_hold: 'در انتظار اتصال', limited: 'حجم تمام', expired: 'منقضی', disabled: 'غیرفعال', pending: 'در حال ساخت' },
    last_conn: 'آخرین اتصال', never: 'هرگز', since: 'غیرفعال از', opened: 'باز شده', service: 'سرویس', customer: 'مشتری', c360: 'نمای کامل مشتری',
    reason: 'دلیل', notes: 'یادداشت پیگیری', assigned: 'مسئول', save: 'ذخیره', outcome: 'نتیجه', close_case: 'بستن پرونده',
    msg: 'ارسال پیام', template: 'قالب', custom: 'متن دلخواه', via_site: 'سایت', via_bot: 'ربات', via_email: 'ایمیل', send: 'ارسال',
    ticket: 'تیکت', open_ticket: 'باز کردن تیکت برای مشتری', subject: 'عنوان', body: 'متن', linked_ticket: 'تیکت مرتبط', history: 'سوابق پرونده',
    auto_sent: 'پیام خودکار ارسال شد', by_system: 'توسط سامانه (اتصال دوباره)', closed_by: 'بسته شده توسط',
    profile: 'مشخصات', phone: 'تلفن', email: 'ایمیل', source: 'منبع', signup: 'ثبت‌نام', last_login: 'آخرین ورود', referrer: 'معرف', telegram: 'تلگرام',
    stage: 'مرحله', auto: 'خودکار', override: 'تعیین دستی', owner: 'مالک', tags: 'برچسب‌ها', services: 'سرویس‌ها', money: 'خرید و پرداخت',
    ltv: 'مجموع پرداخت (LTV)', orders: 'سفارش‌ها', first_buy: 'اولین خرید', last_buy: 'آخرین خرید', payments: 'پرداخت‌ها', no_pay_perm: 'دسترسی مشاهدهٔ پرداخت ندارید',
    tickets: 'تیکت‌ها', notifs: 'اعلان‌های ارسالی', cases: 'پرونده‌های پیگیری', new_case: 'پرونده جدید', note_add: 'افزودن یادداشت', note_ph: 'یادداشت داخلی…',
    timeline: 'فعالیت‌ها', online: 'آنلاین', last_activity: 'آخرین فعالیت', pre_tickets: 'تیکت قبل از خرید', follow: 'پیگیری', lead_case: 'ایجاد پیگیری',
    with_tickets: 'فقط با تیکت', days: 'بازه', d7: '7 روز', d30: '30 روز', d90: '90 روز', dall: 'همه',
    r_open: 'پرونده‌های باز', r_opened: 'باز شده در بازه', r_reasons: 'دلایل', r_outcomes: 'نتیجه‌ها', r_time: 'زمان حل', r_avg: 'میانگین', r_median: 'میانه',
    hours: 'ساعت', r_stages: 'مشتریان بر اساس مرحله', r_system: 'حل خودکار (اتصال دوباره)',
    s_thresholds: 'آستانه‌ها', s_inactive: 'روزهای بدون اتصال (سرویس فعال)', s_never: 'ساعت‌های بدون اولین اتصال پس از خرید', s_new: 'مشتری جدید تا (روز)',
    s_risk_days: 'در خطر: روز مانده به انقضا', s_risk_pct: 'در خطر: درصد مصرف حجم', s_churn: 'ریزش پس از (روز بدون سرویس)', s_won: 'بازگشته تا (روز)',
    s_auto: 'پیام دوستانهٔ خودکار', s_auto_d: 'پس از چند روز بی‌اتصالی برای پرونده‌های باز (یک بار)', s_auto_days: 'پس از (روز)', s_auto_tpl: 'قالب پیام',
    s_guide: 'لینک راهنمای اتصال ({guide})', reasons: 'دلایل', templates: 'قالب‌های پیام', tags_h: 'برچسب‌ها', add: 'افزودن', del: 'حذف', active: 'فعال',
    vars: 'متغیرها: {name} {username} {service} {site} {guide}', ev: 'رویداد',
    tl: { signup: 'ثبت‌نام', order: 'سفارش', payment: 'پرداخت', ticket: 'تیکت', ticket_closed: 'بسته شدن تیکت', notification: 'اعلان',
      crm_stage: 'تغییر مرحله', crm_owner: 'تغییر مالک', crm_tags: 'برچسب‌ها', crm_note: 'یادداشت', crm_case_opened: 'پرونده باز شد',
      crm_case_updated: 'پرونده به‌روز شد', crm_case_closed: 'پرونده بسته شد', crm_message: 'پیام ارسال شد', crm_ticket: 'تیکت مرتبط' },
  },
  en: {
    title: 'CRM', sub: 'Customers, inactivity follow-up and leads',
    t_queue: 'Needs follow-up', t_leads: 'Leads', t_reports: 'Reports', t_settings: 'Settings',
    open: 'Open', closed: 'Closed', all_kinds: 'All kinds', all_reasons: 'All reasons', no_reason: 'No reason', anyone: 'Anyone', me: 'Assigned to me', none: 'Unassigned',
    search: 'Search: user, phone, service…', empty: 'Nothing here.', more: 'More', back: 'Back',
    k: { no_connection: 'No connection', never_connected: 'Never connected', lead: 'Lead', manual: 'Manual' },
    oc: { resolved: 'Resolved', still_inactive: 'Still inactive', lost: 'Lost' },
    stg: { lead: 'Lead', new: 'New', active: 'Active', at_risk: 'At risk', expired: 'Expired', churned: 'Churned', won_back: 'Won back' },
    svc: { active: 'Active', on_hold: 'Waiting for first connection', limited: 'Used up', expired: 'Expired', disabled: 'Disabled', pending: 'Creating' },
    last_conn: 'Last connection', never: 'never', since: 'Inactive since', opened: 'Opened', service: 'Service', customer: 'Customer', c360: 'Customer 360',
    reason: 'Reason', notes: 'Follow-up notes', assigned: 'Assignee', save: 'Save', outcome: 'Outcome', close_case: 'Close case',
    msg: 'Send a message', template: 'Template', custom: 'Custom text', via_site: 'Site', via_bot: 'Bot', via_email: 'Email', send: 'Send',
    ticket: 'Ticket', open_ticket: 'Open a ticket for the customer', subject: 'Subject', body: 'Text', linked_ticket: 'Linked ticket', history: 'Case history',
    auto_sent: 'Automatic message sent', by_system: 'by the system (connected again)', closed_by: 'Closed by',
    profile: 'Profile', phone: 'Phone', email: 'Email', source: 'Source', signup: 'Signed up', last_login: 'Last login', referrer: 'Referred by', telegram: 'Telegram',
    stage: 'Stage', auto: 'Automatic', override: 'Manual stage', owner: 'Owner', tags: 'Tags', services: 'Services', money: 'Purchases & payments',
    ltv: 'Total paid (LTV)', orders: 'Orders', first_buy: 'First purchase', last_buy: 'Last purchase', payments: 'Payments', no_pay_perm: 'No permission to view payments',
    tickets: 'Tickets', notifs: 'Notifications sent', cases: 'Follow-up cases', new_case: 'New case', note_add: 'Add note', note_ph: 'Internal note…',
    timeline: 'Activity', online: 'Online', last_activity: 'Last activity', pre_tickets: 'Pre-purchase tickets', follow: 'Follow-up', lead_case: 'Start follow-up',
    with_tickets: 'With tickets only', days: 'Period', d7: '7 days', d30: '30 days', d90: '90 days', dall: 'All',
    r_open: 'Open cases', r_opened: 'Opened in period', r_reasons: 'Reasons', r_outcomes: 'Outcomes', r_time: 'Time to resolve', r_avg: 'Average', r_median: 'Median',
    hours: 'h', r_stages: 'Customers by stage', r_system: 'Auto-resolved (connected again)',
    s_thresholds: 'Thresholds', s_inactive: 'Days without a connection (active service)', s_never: 'Hours without a first connection after purchase', s_new: 'New customer for (days)',
    s_risk_days: 'At risk: days before expiry', s_risk_pct: 'At risk: % of volume used', s_churn: 'Churned after (days without a service)', s_won: 'Won back for (days)',
    s_auto: 'Automatic friendly message', s_auto_d: 'Sent once for open cases after N days without a connection', s_auto_days: 'After (days)', s_auto_tpl: 'Template',
    s_guide: 'Connection guide link ({guide})', reasons: 'Reasons', templates: 'Message templates', tags_h: 'Tags', add: 'Add', del: 'Delete', active: 'Active',
    vars: 'Variables: {name} {username} {service} {site} {guide}', ev: 'Event',
    tl: { signup: 'Signed up', order: 'Order', payment: 'Payment', ticket: 'Ticket', ticket_closed: 'Ticket closed', notification: 'Notification',
      crm_stage: 'Stage changed', crm_owner: 'Owner changed', crm_tags: 'Tags', crm_note: 'Note', crm_case_opened: 'Case opened',
      crm_case_updated: 'Case updated', crm_case_closed: 'Case closed', crm_message: 'Message sent', crm_ticket: 'Ticket linked' },
  },
}
const STAGE_TONE = { lead: 'muted', new: 'primary', active: 'success', at_risk: 'warning', expired: 'danger', churned: 'danger', won_back: 'success' }
const useT = () => { const { lang } = useI18n(); return [T[lang] || T.fa, lang] }
const rname = (r, lang) => (r ? (lang === 'en' ? r.name_en : r.name_fa) : '')

function useGet(url, deps = []) {
  const [d, setD] = useState(null)
  const load = useCallback(() => (url ? api.get(url).then((r) => setD(r.data)).catch(() => setD(false)) : null), [url])
  useEffect(() => { load() }, [load, ...deps])
  return [d, load]
}
function Chip({ tone = 'muted', children }) { return <span className={`cr-chip cr-chip--${tone}`}>{children}</span> }

export function CrmHeader() {
  const [s] = useT()
  const { can } = useAuth()
  const tabs = [['/crm', s.t_queue, true], ['/crm/leads', s.t_leads], ['/crm/reports', s.t_reports], ...(can('crm.manage') ? [['/crm/settings', s.t_settings]] : [])]
  return (
    <>
      <style>{CSS}</style>
      <div><h1 className="text-lg font-bold">{s.title}</h1><p className="text-sm text-muted mt-1">{s.sub}</p></div>
      <nav className="cr-tabs">{tabs.map(([to, l, end]) => <NavLink key={to} to={to} end={!!end} className={({ isActive }) => 'cr-tab' + (isActive ? ' on' : '')}>{l}</NavLink>)}</nav>
    </>
  )
}

function lastConn(svc, s, lang) {
  if (!svc) return '—'
  return svc.online_at ? relTime(svc.online_at, lang) : s.never
}

// ================================ queue ========================================
export function CrmQueue() {
  const [s, lang] = useT()
  const go = useNavigate()
  const [f, setF] = useState({ status: 'open', kind: '', reason: '', assigned: '', q: '' })
  const [q, setQ] = useState('')
  useEffect(() => { const t = setTimeout(() => setF((x) => ({ ...x, q })), 300); return () => clearTimeout(t) }, [q])
  const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v)).toString()
  const [d] = useGet(`/admin/crm/cases/?${qs}`, [qs])
  const [reasons] = useGet('/admin/crm/reasons/')
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }))
  return (
    <div className="cr space-y-4">
      <CrmHeader />
      {d?.open_counts && (
        <div className="cr-kpis">
          {Object.entries(d.open_counts).map(([k, n]) => (
            <button key={k} type="button" className={'cr-kpi' + (f.kind === k ? ' on' : '')} onClick={() => set('kind', f.kind === k ? '' : k)}>
              <b dir="ltr">{n}</b><span>{s.k[k]}</span></button>
          ))}
        </div>
      )}
      <div className="card cr-filters">
        <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder={s.search} />
        <select className="input" value={f.status} onChange={(e) => set('status', e.target.value)}><option value="open">{s.open}</option><option value="closed">{s.closed}</option></select>
        <select className="input" value={f.reason} onChange={(e) => set('reason', e.target.value)}>
          <option value="">{s.all_reasons}</option><option value="none">{s.no_reason}</option>
          {(reasons || []).map((r) => <option key={r.id} value={r.id}>{rname(r, lang)}</option>)}
        </select>
        <select className="input" value={f.assigned} onChange={(e) => set('assigned', e.target.value)}>
          <option value="">{s.anyone}</option><option value="me">{s.me}</option><option value="none">{s.none}</option>
        </select>
      </div>
      {d === null ? <div className="grid place-items-center py-12"><Spinner /></div> : !d || d.results.length === 0 ? <div className="card text-center text-muted py-8">{s.empty}</div> : (
        <div className="cr-cards">
          {d.results.map((c) => (
            <button key={c.id} type="button" className="card cr-case" onClick={() => go(`/crm/cases/${c.id}`)}>
              <span className="cr-case-top">
                <b className="truncate">{c.user.name || c.user.username}</b>
                <Chip tone={c.kind === 'never_connected' ? 'warning' : c.kind === 'no_connection' ? 'danger' : 'primary'}>{s.k[c.kind]}</Chip>
              </span>
              <span className="cr-case-meta" dir="ltr">{c.user.username}{c.service ? ` · ${c.service.panel_username}` : ''}</span>
              <span className="cr-case-row">
                {c.service && <span>{s.last_conn}: <b>{lastConn(c.service, s, lang)}</b></span>}
                <span>{s.opened}: {relTime(c.opened_at, lang)}</span>
              </span>
              <span className="cr-case-row">
                {c.reason ? <Chip>{rname(c.reason, lang)}</Chip> : <span className="text-muted">{s.no_reason}</span>}
                {c.outcome && <Chip tone={c.outcome === 'resolved' ? 'success' : c.outcome === 'lost' ? 'danger' : 'warning'}>{s.oc[c.outcome]}</Chip>}
                {c.ticket && <Chip tone="primary">#{c.ticket.number}</Chip>}
                {c.assigned_to && <span className="cr-who">{c.assigned_to.display_name || c.assigned_to.username}</span>}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ================================ case ==========================================
function MessageBox({ s, lang, userId, post }) {
  const [tpls] = useGet('/admin/crm/templates/')
  const [tpl, setTpl] = useState('')
  const [body, setBody] = useState('')
  const [ch, setCh] = useState({ via_site: true, via_bot: true, via_email: false })
  const pick = async (id) => {
    setTpl(id)
    if (!id) return
    const r = await api.get(`/admin/crm/customers/${userId}/templates/${id}/preview/`)
    setBody(lang === 'en' ? r.data.body_en : r.data.body_fa)
  }
  return (
    <div className="cr-box">
      <h4>{s.msg}</h4>
      <select className="input" value={tpl} onChange={(e) => pick(e.target.value)}>
        <option value="">{s.custom}</option>
        {(tpls || []).filter((t) => t.is_active).map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
      </select>
      <textarea className="input" rows={5} value={body} onChange={(e) => setBody(e.target.value)} />
      <div className="cr-checks">
        {['via_site', 'via_bot', 'via_email'].map((k) => <label key={k}><Toggle checked={ch[k]} onChange={(v) => setCh({ ...ch, [k]: v })} label={s[k]} />{s[k]}</label>)}
      </div>
      <button type="button" className="btn-primary text-sm" disabled={!body.trim()} onClick={async () => { await post({ body_fa: body, body_en: body, ...ch }); setBody(''); setTpl('') }}>{s.send}</button>
    </div>
  )
}

export function CrmCase() {
  const [s, lang] = useT()
  const { id } = useParams()
  const { can } = useAuth()
  const confirm = useConfirm()
  const [c, load] = useGet(`/admin/crm/cases/${id}/`, [id])
  const [reasons] = useGet('/admin/crm/reasons/')
  const [staff] = useGet('/admin/crm/staff/')
  const [topics] = useGet(can('tickets.view') ? '/admin/tickets/topics/' : null)
  const [notes, setNotes] = useState(null)
  const [tk, setTk] = useState({ subject: '', body: '', topic: '' })
  const manage = can('crm.manage')
  useEffect(() => { if (c) setNotes(c.notes) }, [c?.id])
  const patch = async (body) => { await api.patch(`/admin/crm/cases/${id}/`, body); load() }
  const closeCase = () => {
    let outcome = 'resolved'
    confirm({ tone: 'primary', title: s.close_case, confirmLabel: s.close_case,
      content: <label className="cr-fld"><span className="label">{s.outcome}</span>
        <select className="input" defaultValue="resolved" onChange={(e) => { outcome = e.target.value }}>
          {Object.entries(s.oc).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>,
      action: async () => { await api.post(`/admin/crm/cases/${id}/close/`, { outcome }); await load() } })
  }
  if (c === null) return <div className="cr"><CrmHeader /><div className="grid place-items-center py-12"><Spinner /></div></div>
  if (!c) return <div className="cr"><CrmHeader /><p className="card">—</p></div>
  const open = c.status === 'open'
  return (
    <div className="cr space-y-4">
      <CrmHeader />
      <Link to="/crm" className="cr-back">← {s.back}</Link>
      <div className="card cr-head">
        <div className="min-w-0 flex-1">
          <b className="text-base">{c.user.name || c.user.username}</b>
          <span className="cr-case-meta" dir="ltr"> {c.user.username} {c.user.phone || ''}</span>
          <div className="cr-case-row mt-1"><Chip tone={open ? 'warning' : 'muted'}>{open ? s.open : s.closed}</Chip><Chip tone="primary">{s.k[c.kind]}</Chip>
            {c.outcome && <Chip tone={c.outcome === 'resolved' ? 'success' : 'danger'}>{s.oc[c.outcome]}</Chip>}
            {c.closed_by_system && <span className="text-xs text-muted">{s.by_system}</span>}</div>
        </div>
        <Link className="btn-ghost text-sm" to={`/crm/customers/${c.user.id}`}>{s.c360} →</Link>
      </div>
      <div className="cr-grid2">
        <section className="card space-y-3">
          {c.service && (
            <dl className="cr-kv">
              <dt>{s.service}</dt><dd dir="ltr">{c.service.panel_username}</dd>
              <dt>{s.stage}</dt><dd>{s.svc[c.service.status] || c.service.status}</dd>
              <dt>{s.last_conn}</dt><dd>{c.service.online_at ? jalali(c.service.online_at, true, lang) : s.never}</dd>
              <dt>{s.since}</dt><dd>{c.inactive_since ? jalali(c.inactive_since, true, lang) : '—'}</dd>
              <dt>{s.opened}</dt><dd>{jalali(c.opened_at, true, lang)}</dd>
              {c.auto_message_at && <><dt>{s.auto_sent}</dt><dd>{jalali(c.auto_message_at, true, lang)}</dd></>}
            </dl>
          )}
          <label className="cr-fld"><span className="label">{s.reason}</span>
            <select className="input" value={c.reason?.id || ''} disabled={!manage} onChange={(e) => patch({ reason: e.target.value || null })}>
              <option value="">{s.no_reason}</option>
              {(reasons || []).filter((r) => r.is_active || r.id === c.reason?.id).map((r) => <option key={r.id} value={r.id}>{rname(r, lang)}</option>)}
            </select></label>
          <label className="cr-fld"><span className="label">{s.assigned}</span>
            <select className="input" value={c.assigned_to?.id || ''} disabled={!manage} onChange={(e) => patch({ assigned_to: e.target.value || null })}>
              <option value="">{s.none}</option>
              {(staff || []).map((x) => <option key={x.id} value={x.id}>{x.display_name || x.username}</option>)}
            </select></label>
          <label className="cr-fld"><span className="label">{s.notes}</span>
            <textarea className="input" rows={4} value={notes ?? ''} disabled={!manage} onChange={(e) => setNotes(e.target.value)} /></label>
          {manage && <div className="cr-actions">
            <button type="button" className="btn-ghost text-sm" disabled={notes === c.notes} onClick={() => patch({ notes })}>{s.save}</button>
            {open && <button type="button" className="btn-primary text-sm" onClick={closeCase}>{s.close_case}</button>}
          </div>}
        </section>
        <section className="space-y-3">
          {manage && open && <div className="card"><MessageBox s={s} lang={lang} userId={c.user.id} post={(b) => api.post(`/admin/crm/cases/${id}/message/`, b).then(load)} /></div>}
          <div className="card cr-box">
            <h4>{s.ticket}</h4>
            {c.ticket ? <Link className="btn-ghost text-sm" to={`/tickets/${c.ticket.id}`}>{s.linked_ticket}: #{c.ticket.number}</Link>
              : manage && open && can('tickets.view') ? <>
                <select className="input" value={tk.topic} onChange={(e) => setTk({ ...tk, topic: e.target.value })}>
                  <option value="">—</option>{(topics || []).map((tp) => <option key={tp.id} value={tp.id}>{lang === 'en' ? tp.name_en : tp.name_fa}</option>)}</select>
                <input className="input" placeholder={s.subject} value={tk.subject} onChange={(e) => setTk({ ...tk, subject: e.target.value })} />
                <textarea className="input" rows={3} placeholder={s.body} value={tk.body} onChange={(e) => setTk({ ...tk, body: e.target.value })} />
                <button type="button" className="btn-primary text-sm" disabled={!tk.subject.trim() || !tk.body.trim()}
                  onClick={() => api.post(`/admin/crm/cases/${id}/ticket/`, { ...tk, topic: tk.topic || undefined }).then(load)}>{s.open_ticket}</button>
              </> : <span className="text-muted text-sm">—</span>}
          </div>
          <div className="card cr-box">
            <h4>{s.history}</h4>
            <ul className="cr-tl">{c.events.map((e) => (
              <li key={e.id}><b>{s.tl['crm_' + e.kind] || e.kind}</b> <span className="text-muted">· {e.actor.replace('staff:', '')} · {jalali(e.created_at, true, lang)}</span></li>
            ))}</ul>
          </div>
        </section>
      </div>
    </div>
  )
}

// ============================== customer 360 =====================================
function tlText(x, s, lang) {
  switch (x.kind) {
    case 'order': return `#${x.order} · ${lang === 'en' ? x.plan_en || x.plan || '' : x.plan || ''} · ${toman(x.amount, lang)} · ${x.status}`
    case 'payment': return `${toman(x.amount, lang)} · ${x.status} · ${x.method}`
    case 'ticket': case 'ticket_closed': return `#${x.number}${x.subject ? ' · ' + x.subject : ''}`
    case 'notification': return lang === 'en' ? x.title_en || x.title : x.title
    case 'crm_stage': return `${s.stg[x.old] || x.old || '—'} → ${s.stg[x.new] || x.new}`
    case 'crm_owner': return x.owner || '—'
    case 'crm_tags': return (x.tags || []).join('، ')
    case 'crm_note': return x.preview
    case 'crm_message': return x.preview
    case 'crm_case_opened': return s.k[x.case_kind] || ''
    case 'crm_case_closed': return s.oc[x.outcome] || ''
    case 'crm_ticket': return `#${x.ticket}`
    default: return x.source || ''
  }
}

export function Customer360() {
  const [s, lang] = useT()
  const { id } = useParams()
  const { can } = useAuth()
  const go = useNavigate()
  const [d, load] = useGet(`/admin/crm/customers/${id}/`, [id])
  const [tl, loadTl] = useGet(`/admin/crm/customers/${id}/timeline/`, [id])
  const [staff] = useGet('/admin/crm/staff/')
  const [tags] = useGet('/admin/crm/tags/')
  const [note, setNote] = useState('')
  const manage = can('crm.manage')
  const patch = async (b) => { await api.patch(`/admin/crm/customers/${id}/`, b); load(); loadTl() }
  if (d === null) return <div className="cr"><CrmHeader /><div className="grid place-items-center py-12"><Spinner /></div></div>
  if (!d) return <div className="cr"><CrmHeader /><p className="card">—</p></div>
  const u = d.user, p = d.profile
  const tagIds = p.tags.map((t) => t.id)
  return (
    <div className="cr space-y-4">
      <CrmHeader />
      <div className="card cr-head">
        <span className="cr-av">{(u.name || u.username).slice(0, 1).toUpperCase()}</span>
        <div className="min-w-0 flex-1">
          <b className="text-base">{u.name || u.username}</b> <span className="cr-case-meta" dir="ltr">{u.username}</span>
          <div className="cr-case-row mt-1"><Chip tone={STAGE_TONE[p.effective_stage]}>{s.stg[p.effective_stage]}</Chip>
            {p.stage_override && <span className="text-xs text-muted">({s.override}; {s.auto}: {s.stg[p.stage]})</span>}
            {p.tags.map((t) => <span key={t.id} className="cr-tag" style={{ '--tag': t.color }}>{t.name}</span>)}</div>
        </div>
        {manage && <button type="button" className="btn-ghost text-sm" onClick={() => api.post(`/admin/crm/customers/${id}/cases/`, { kind: d.money.orders ? 'manual' : 'lead' }).then((r) => go(`/crm/cases/${r.data.id}`))}>+ {s.new_case}</button>}
      </div>
      <div className="cr-grid3">
        <section className="card space-y-2">
          <h4>{s.profile}</h4>
          <dl className="cr-kv">
            <dt>{s.phone}</dt><dd dir="ltr">{u.phone || '—'}</dd>
            <dt>{s.email}</dt><dd dir="ltr">{u.email || '—'}</dd>
            <dt>{s.telegram}</dt><dd dir="ltr">{u.telegram_username ? '@' + u.telegram_username : u.telegram_id ? '✓' : '—'}</dd>
            <dt>{s.source}</dt><dd>{u.source}</dd>
            <dt>{s.signup}</dt><dd>{jalali(u.created_at, false, lang)}</dd>
            <dt>{s.last_login}</dt><dd>{u.last_login ? relTime(u.last_login, lang) : '—'}</dd>
            <dt>{s.referrer}</dt><dd>{u.referred_by ? <Link to={`/crm/customers/${u.referred_by.id}`}>{u.referred_by.username}</Link> : '—'}</dd>
          </dl>
          {manage && <>
            <label className="cr-fld"><span className="label">{s.override}</span>
              <select className="input" value={p.stage_override} onChange={(e) => patch({ stage_override: e.target.value })}>
                <option value="">{s.auto} ({s.stg[p.stage]})</option>
                {Object.entries(s.stg).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
            <label className="cr-fld"><span className="label">{s.owner}</span>
              <select className="input" value={p.owner?.id || ''} onChange={(e) => patch({ owner: e.target.value || null })}>
                <option value="">—</option>{(staff || []).map((x) => <option key={x.id} value={x.id}>{x.display_name || x.username}</option>)}</select></label>
            <div className="cr-fld"><span className="label">{s.tags}</span>
              <div className="cr-tagpick">{(tags || []).map((t) => {
                const on = tagIds.includes(t.id)
                return <button key={t.id} type="button" className={'cr-tag' + (on ? ' on' : '')} style={{ '--tag': t.color }}
                  onClick={() => patch({ tags: on ? tagIds.filter((x) => x !== t.id) : [...tagIds, t.id] })}>{on ? '✓ ' : ''}{t.name}</button>
              })}</div></div>
          </>}
        </section>
        <section className="card space-y-2">
          <h4>{s.money}</h4>
          <dl className="cr-kv">
            <dt>{s.ltv}</dt><dd><b>{toman(d.money.ltv, lang)}</b></dd>
            <dt>{s.orders}</dt><dd>{d.money.orders}</dd>
            <dt>{s.first_buy}</dt><dd>{d.money.first_purchase ? jalali(d.money.first_purchase, false, lang) : '—'}</dd>
            <dt>{s.last_buy}</dt><dd>{d.money.last_purchase ? jalali(d.money.last_purchase, false, lang) : '—'}</dd>
          </dl>
          <h4>{s.services} ({d.services.length})</h4>
          {d.services.map((x) => (
            <div key={x.id} className="cr-item">
              <span dir="ltr" className="truncate">{x.panel_username}</span><Chip tone={x.status === 'active' ? 'success' : x.status === 'on_hold' ? 'primary' : 'muted'}>{s.svc[x.status] || x.status}</Chip>
              <span className="cr-sub w-full">{gb(x.data_used)} / {x.data_limit ? gb(x.data_limit) : '∞'} GB · {x.expire_at ? jalali(x.expire_at, false, lang) : '—'} · {s.last_conn}: {x.online_at ? relTime(x.online_at, lang) : s.never}</span>
            </div>
          ))}
          <h4>{s.payments}</h4>
          {d.payments === null ? <p className="cr-sub">{s.no_pay_perm}</p> : d.payments.map((x) => (
            <div key={x.id} className="cr-item"><span>{toman(x.amount, lang)}</span><Chip tone={x.status === 'approved' ? 'success' : 'muted'}>{x.status}</Chip><span className="cr-sub w-full">{jalali(x.created_at, true, lang)}</span></div>
          ))}
        </section>
        <section className="card space-y-2">
          <h4>{s.cases}</h4>
          {d.cases.length === 0 ? <p className="cr-sub">—</p> : d.cases.map((c) => (
            <Link key={c.id} to={`/crm/cases/${c.id}`} className="cr-item cr-link"><span>{s.k[c.kind]}</span><Chip tone={c.status === 'open' ? 'warning' : 'muted'}>{c.status === 'open' ? s.open : s.oc[c.outcome] || s.closed}</Chip></Link>
          ))}
          <h4>{s.tickets} ({d.tickets.count})</h4>
          {d.tickets.rows.map((t) => <Link key={t.id} to={`/tickets/${t.id}`} className="cr-item cr-link"><span className="truncate">#{t.number} {t.subject}</span><Chip>{t.status}</Chip></Link>)}
          <h4>{s.notifs}</h4>
          {d.notifications.map((n) => <div key={n.id} className="cr-item"><span className="truncate">{lang === 'en' ? n.title_en || n.title : n.title}</span><span className="cr-sub">{relTime(n.created_at, lang)}</span></div>)}
        </section>
      </div>
      <div className="cr-grid2">
        <section className="card space-y-2">
          <h4>{s.note_add}</h4>
          {manage && <div className="cr-actions"><textarea className="input" rows={2} value={note} placeholder={s.note_ph} onChange={(e) => setNote(e.target.value)} />
            <button type="button" className="btn-primary text-sm" disabled={!note.trim()} onClick={async () => { await api.post(`/admin/crm/customers/${id}/notes/`, { body: note }); setNote(''); load(); loadTl() }}>{s.add}</button></div>}
          {d.notes.map((n) => <div key={n.id} className="cr-note"><p>{n.body}</p><span className="cr-sub">{n.staff} · {jalali(n.created_at, true, lang)}</span></div>)}
          {manage && <MessageBox s={s} lang={lang} userId={u.id} post={(b) => api.post(`/admin/crm/customers/${id}/message/`, b).then(loadTl)} />}
        </section>
        <section className="card space-y-2">
          <h4>{s.timeline}</h4>
          <ul className="cr-tl">{(tl || []).map((x, i) => (
            <li key={i}><b>{s.tl[x.kind] || x.kind}</b> <span>{tlText(x, s, lang)}</span>
              <span className="text-muted"> · {jalali(x.at, true, lang)}{x.actor && x.actor !== 'system' ? ` · ${x.actor.replace('staff:', '')}` : ''}</span></li>
          ))}</ul>
        </section>
      </div>
    </div>
  )
}

// ================================= leads ===========================================
export function CrmLeads() {
  const [s, lang] = useT()
  const { can } = useAuth()
  const go = useNavigate()
  const [q, setQ] = useState('')
  const [term, setTerm] = useState('')
  const [onlyT, setOnlyT] = useState(false)
  useEffect(() => { const t = setTimeout(() => setTerm(q), 300); return () => clearTimeout(t) }, [q])
  const [d] = useGet(`/admin/crm/leads/?q=${encodeURIComponent(term)}${onlyT ? '&with_tickets=1' : ''}`, [term, onlyT])
  return (
    <div className="cr space-y-4">
      <CrmHeader />
      <div className="card cr-filters">
        <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder={s.search} />
        <label className="cr-checks"><Toggle checked={onlyT} onChange={setOnlyT} label={s.with_tickets} />{s.with_tickets}</label>
      </div>
      {d === null ? <div className="grid place-items-center py-12"><Spinner /></div> : !d || d.results.length === 0 ? <div className="card text-center text-muted py-8">{s.empty}</div> : (
        <div className="cr-cards">
          {d.results.map((r) => (
            <div key={r.id} className="card cr-case">
              <span className="cr-case-top"><b className="truncate">{r.name || r.username}</b><Chip tone={STAGE_TONE[r.stage]}>{s.stg[r.stage]}</Chip></span>
              <span className="cr-case-meta" dir="ltr">{r.username}{r.phone ? ` · ${r.phone}` : ''} · {r.source}</span>
              <span className="cr-case-row"><span>{s.signup}: {jalali(r.created_at, false, lang)}</span><span>{s.last_activity}: {relTime(r.last_activity, lang)}</span></span>
              <span className="cr-case-row">{r.pre_tickets > 0 && <Chip tone="primary">{s.pre_tickets}: {r.pre_tickets}</Chip>}{r.open_cases > 0 && <Chip tone="warning">{s.follow}: {r.open_cases}</Chip>}</span>
              <span className="cr-actions">
                <Link className="btn-ghost text-sm" to={`/crm/customers/${r.id}`}>{s.c360}</Link>
                {can('crm.manage') && !r.open_cases && <button type="button" className="btn-primary text-sm"
                  onClick={() => api.post(`/admin/crm/customers/${r.id}/cases/`, { kind: 'lead' }).then((x) => go(`/crm/cases/${x.data.id}`))}>{s.lead_case}</button>}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ================================ reports ===========================================
export function CrmReports() {
  const [s, lang] = useT()
  const [days, setDays] = useState(30)
  const [d] = useGet(`/admin/crm/reports/?days=${days}`, [days])
  const bar = (n, max) => <span className="cr-bar"><i style={{ width: `${max ? Math.round((n / max) * 100) : 0}%` }} /></span>
  const reasonMax = Math.max(1, ...(d?.by_reason || []).map((x) => x.count))
  const stageMax = Math.max(1, ...Object.values(d?.stages || { a: 1 }))
  return (
    <div className="cr space-y-4">
      <CrmHeader />
      <div className="cr-seg">{[[7, s.d7], [30, s.d30], [90, s.d90], [0, s.dall]].map(([v, l]) => <button key={v} type="button" className={days === v ? 'on' : ''} onClick={() => setDays(v)}>{l}</button>)}</div>
      {!d ? <div className="grid place-items-center py-12"><Spinner /></div> : <>
        <div className="cr-kpis">
          <div className="cr-kpi"><b dir="ltr">{Object.values(d.open_now).reduce((a, b) => a + b, 0)}</b><span>{s.r_open}</span></div>
          <div className="cr-kpi"><b dir="ltr">{d.opened}</b><span>{s.r_opened}</span></div>
          <div className="cr-kpi"><b dir="ltr">{d.resolve_hours.avg ?? '—'}</b><span>{s.r_avg} ({s.hours})</span></div>
          <div className="cr-kpi"><b dir="ltr">{d.resolve_hours.median ?? '—'}</b><span>{s.r_median} ({s.hours})</span></div>
          <div className="cr-kpi"><b dir="ltr">{d.closed_by_system}</b><span>{s.r_system}</span></div>
        </div>
        <div className="cr-grid2">
          <section className="card space-y-2"><h4>{s.r_reasons}</h4>
            {d.by_reason.map((x, i) => <div key={i} className="cr-rep"><span>{x.reason ? rname(x.reason, lang) : s.no_reason}</span>{bar(x.count, reasonMax)}<b dir="ltr">{x.count}</b></div>)}</section>
          <section className="card space-y-2"><h4>{s.r_outcomes}</h4>
            {Object.entries(d.outcomes).map(([k, n]) => <div key={k} className="cr-rep"><span>{s.oc[k] || k}</span>{bar(n, Math.max(1, ...Object.values(d.outcomes)))}<b dir="ltr">{n}</b></div>)}
            <h4>{s.r_open}</h4>
            {Object.entries(d.open_now).map(([k, n]) => <div key={k} className="cr-rep"><span>{s.k[k]}</span><b dir="ltr">{n}</b></div>)}</section>
        </div>
        <section className="card space-y-2"><h4>{s.r_stages}</h4>
          {Object.entries(s.stg).map(([k, l]) => <div key={k} className="cr-rep"><span>{l}</span>{bar(d.stages[k] || 0, stageMax)}<b dir="ltr">{d.stages[k] || 0}</b></div>)}</section>
      </>}
    </div>
  )
}

// ================================ settings ==========================================
function SimpleList({ s, url, fields, title, render }) {
  const [rows, load] = useGet(url)
  const [f, setF] = useState(null)
  const confirm = useConfirm()
  const save = async (e) => { e.preventDefault(); if (f.id) await api.patch(`${url}${f.id}/`, f); else await api.post(url, f); setF(null); load() }
  return (
    <section className="card space-y-2">
      <div className="cr-case-top"><h4>{title}</h4><button type="button" className="btn-ghost text-sm" onClick={() => setF(Object.fromEntries(fields.map(([k, , d]) => [k, d])))}>+ {s.add}</button></div>
      {f && <form className="cr-box" onSubmit={save}>
        {fields.map(([k, label, d, kind]) => kind === 'bool'
          ? <label key={k} className="cr-checks"><Toggle checked={!!f[k]} onChange={(v) => setF({ ...f, [k]: v })} label={label} />{label}</label>
          : kind === 'text' ? <textarea key={k} className="input" rows={4} placeholder={label} value={f[k] ?? ''} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
            : <input key={k} className="input" type={kind === 'color' ? 'color' : 'text'} placeholder={label} value={f[k] ?? ''} onChange={(e) => setF({ ...f, [k]: e.target.value })} />)}
        <div className="cr-actions"><button type="button" className="btn-ghost text-sm" onClick={() => setF(null)}>×</button><button className="btn-primary text-sm">{s.save}</button></div>
      </form>}
      {(rows || []).map((r) => (
        <div key={r.id} className="cr-item">
          <span className="min-w-0 flex-1">{render(r)}</span>
          <button type="button" className="btn-ghost text-xs" onClick={() => setF(r)}>✎</button>
          <button type="button" className="btn-ghost text-xs" onClick={() => confirm({ tone: 'danger', title: s.del, action: async () => { await api.delete(`${url}${r.id}/`); load() } })}>{s.del}</button>
        </div>
      ))}
    </section>
  )
}

export function CrmSettings() {
  const [s, lang] = useT()
  const [cfg, load] = useGet('/admin/crm/settings/')
  const [tpls] = useGet('/admin/crm/templates/')
  const save = async (b) => { await api.patch('/admin/crm/settings/', b); load() }
  const num = (k, label) => (
    <label key={k} className="cr-fld"><span className="label">{label}</span>
      <input className="input" type="number" dir="ltr" defaultValue={cfg.settings[k]} onBlur={(e) => Number(e.target.value) !== cfg.settings[k] && save({ [k]: e.target.value })} /></label>
  )
  if (!cfg) return <div className="cr"><CrmHeader /><div className="grid place-items-center py-12"><Spinner /></div></div>
  const st = cfg.settings
  return (
    <div className="cr space-y-4">
      <CrmHeader />
      <section className="card space-y-3"><h4>{s.s_thresholds}</h4>
        <div className="cr-form">{num('crm_inactive_days', s.s_inactive)}{num('crm_never_connected_hours', s.s_never)}{num('crm_new_days', s.s_new)}
          {num('crm_at_risk_days', s.s_risk_days)}{num('crm_at_risk_usage_pct', s.s_risk_pct)}{num('crm_churn_days', s.s_churn)}{num('crm_won_back_days', s.s_won)}</div></section>
      <section className="card space-y-3"><h4>{s.s_auto}</h4><p className="cr-sub">{s.s_auto_d}</p>
        <label className="cr-checks"><Toggle checked={st.crm_auto_message} onChange={(v) => save({ crm_auto_message: v })} label={s.s_auto} />{s.s_auto}</label>
        <div className="cr-form">{num('crm_auto_message_days', s.s_auto_days)}
          <label className="cr-fld"><span className="label">{s.s_auto_tpl}</span>
            <select className="input" value={st.crm_auto_message_template || ''} onChange={(e) => save({ crm_auto_message_template: e.target.value || 0 })}>
              <option value="">—</option>{(tpls || []).map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}</select></label>
          <label className="cr-fld"><span className="label">{s.s_guide}</span>
            <input className="input" dir="ltr" defaultValue={st.crm_guide_url} placeholder="https://…/help" onBlur={(e) => e.target.value !== st.crm_guide_url && save({ crm_guide_url: e.target.value })} /></label></div>
      </section>
      <div className="cr-grid2">
        <SimpleList s={s} url="/admin/crm/reasons/" title={s.reasons}
          fields={[['name_fa', 'فارسی', ''], ['name_en', 'English', ''], ['is_active', s.active, true, 'bool']]}
          render={(r) => <>{lang === 'en' ? r.name_en : r.name_fa} {!r.is_active && <Chip>×</Chip>} <span className="cr-sub">({r.used})</span></>} />
        <SimpleList s={s} url="/admin/crm/tags/" title={s.tags_h} fields={[['name', 'name', ''], ['color', 'color', '#1464BA', 'color']]}
          render={(t) => <span className="cr-tag on" style={{ '--tag': t.color }}>{t.name}</span>} />
      </div>
      <SimpleList s={s} url="/admin/crm/templates/" title={`${s.templates} — ${s.vars}`}
        fields={[['title', s.subject, ''], ['body_fa', 'فارسی', '', 'text'], ['body_en', 'English', '', 'text'], ['is_active', s.active, true, 'bool']]}
        render={(t) => <><b>{t.title}</b><span className="cr-sub block">{(lang === 'en' ? t.body_en || t.body_fa : t.body_fa).slice(0, 140)}</span></>} />
    </div>
  )
}

const CSS = `
.cr-tabs { display: flex; gap: 6px; overflow-x: auto; }
.cr-tab { white-space: nowrap; padding: 7px 14px; border-radius: 999px; font-size: 13px; font-weight: 700; color: var(--c-text); border: 1px solid var(--c-border); text-decoration: none; }
.cr-tab.on { background: color-mix(in srgb, var(--c-primary) 85%, #000); border-color: transparent; color: #fff; }
.cr-kpis { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 150px), 1fr)); }
.cr-kpi { display: flex; flex-direction: column; gap: 2px; padding: 12px 14px; border-radius: 14px; border: 1px solid var(--c-border); background: var(--c-surface); color: var(--c-text); text-align: start; cursor: pointer; }
.cr-kpi b { font-size: 22px; font-family: 'JetBrains Mono', monospace; }
.cr-kpi span { font-size: 12px; color: var(--c-text-muted); }
.cr-kpi.on { border-color: var(--c-primary); box-shadow: inset 0 0 0 1px var(--c-primary); }
.cr-filters { display: grid; gap: 8px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 170px), 1fr)); align-items: center; }
.cr-cards { display: grid; gap: 10px; grid-template-columns: repeat(auto-fill, minmax(min(100%, 320px), 1fr)); }
.cr-case { display: flex; flex-direction: column; gap: 6px; text-align: start; color: var(--c-text); cursor: pointer; min-width: 0; }
.cr-case:hover { border-color: var(--c-primary); }
.cr-case-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-width: 0; }
.cr-case-meta { font-size: 12px; color: var(--c-text-muted); }
.cr-case-row { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; font-size: 12.5px; }
.cr-who { font-size: 11px; padding: 1px 7px; border-radius: 6px; background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); }
.cr-chip { display: inline-flex; padding: 1px 9px; border-radius: 999px; font-size: 11px; font-weight: 700; white-space: nowrap; }
.cr-chip--primary { color: var(--c-primary-fg, var(--c-primary)); background: color-mix(in srgb, var(--c-primary) 14%, transparent); }
.cr-chip--success { color: var(--c-success-fg, var(--c-success)); background: color-mix(in srgb, var(--c-success) 14%, transparent); }
.cr-chip--warning { color: var(--c-warning-fg, var(--c-warning)); background: color-mix(in srgb, var(--c-warning) 16%, transparent); }
.cr-chip--danger { color: var(--c-danger-fg, var(--c-danger)); background: color-mix(in srgb, var(--c-danger) 14%, transparent); }
.cr-chip--muted { color: var(--c-text-muted); background: color-mix(in srgb, var(--c-text-muted) 14%, transparent); }
.cr-back { font-size: 13px; color: var(--c-primary); }
.cr-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.cr-av { width: 46px; height: 46px; border-radius: 999px; display: grid; place-items: center; font-weight: 800; color: #fff; background: var(--c-primary); flex-shrink: 0; }
.cr-grid2 { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 380px), 1fr)); align-items: start; }
.cr-grid3 { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr)); align-items: start; }
.cr h4 { margin: 0; font-size: 13px; font-weight: 800; }
.cr-kv { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 5px 12px; margin: 0; font-size: 13px; }
.cr-kv dt { color: var(--c-text-muted); }
.cr-kv dd { margin: 0; overflow-wrap: anywhere; }
.cr-fld { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.cr-form { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); }
.cr-actions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; align-items: flex-end; }
.cr-actions textarea { flex: 1 1 240px; }
.cr-box { display: flex; flex-direction: column; gap: 8px; }
.cr-checks { display: flex; flex-wrap: wrap; gap: 14px; align-items: center; font-size: 13px; }
.cr-checks label { display: inline-flex; gap: 6px; align-items: center; }
.cr-item { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 4px 8px; padding: 8px 10px; border-radius: 10px; border: 1px solid var(--c-border); font-size: 12.5px; color: var(--c-text); text-decoration: none; }
.cr-link:hover { border-color: var(--c-primary); }
.cr-sub { font-size: 11.5px; color: var(--c-text-muted); }
.cr-tag { display: inline-flex; padding: 2px 9px; border-radius: 999px; font-size: 11.5px; font-weight: 700; border: 1px solid color-mix(in srgb, var(--tag) 45%, transparent);
  color: var(--tag); background: color-mix(in srgb, var(--tag) 10%, transparent); cursor: pointer; }
.cr-tag.on { background: var(--tag); color: #fff; }
.cr-tagpick { display: flex; flex-wrap: wrap; gap: 6px; }
.cr-note { padding: 8px 10px; border-radius: 10px; background: color-mix(in srgb, var(--c-warning) 9%, transparent); }
.cr-note p { margin: 0 0 2px; font-size: 13px; white-space: pre-wrap; }
.cr-tl { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; font-size: 12.5px; max-height: 520px; overflow-y: auto; }
.cr-tl li { padding-inline-start: 12px; border-inline-start: 2px solid color-mix(in srgb, var(--c-primary) 35%, transparent); overflow-wrap: anywhere; }
.cr-seg { display: inline-flex; gap: 4px; padding: 4px; border-radius: 999px; background: color-mix(in srgb, var(--c-text-muted) 10%, transparent); }
.cr-seg button { padding: 6px 14px; border-radius: 999px; border: 0; background: none; font-size: 12.5px; font-weight: 700; color: var(--c-text-muted); cursor: pointer; }
.cr-seg button.on { background: var(--c-primary); color: #fff; }
.cr-rep { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 2fr) 40px; gap: 8px; align-items: center; font-size: 12.5px; }
.cr-bar { height: 8px; border-radius: 999px; background: color-mix(in srgb, var(--c-text-muted) 14%, transparent); overflow: hidden; }
.cr-bar i { display: block; height: 100%; background: var(--c-primary); border-radius: 999px; }
`
