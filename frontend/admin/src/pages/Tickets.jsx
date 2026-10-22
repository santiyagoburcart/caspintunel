import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { jalali, toman, gb } from '../lib/format'
import { useLiveTickets, useTicketEvents } from '../lib/liveTickets'
import { Spinner } from '../components/ui'
import { useToast } from '../components/Toast'
import { useConfirm } from '../components/ConfirmDialog'
import { copyToClipboard } from '../lib/clipboard'

// Staff ticket inbox: desktop split view (list · chat · customer), phones one pane at a time.
const T = {
  fa: {
    title: 'تیکت‌ها', search: 'جستجو: شماره، عنوان، کاربر، تلفن…', all_topics: 'همهٔ موضوعات', all_prio: 'همهٔ اولویت‌ها',
    f_active: 'فعال', f_all: 'همه', anyone: 'همه', me: 'سپرده به من', none: 'بدون مسئول', empty: 'تیکتی با این فیلترها نیست.',
    pick: 'یک تیکت را از فهرست انتخاب کنید.', more: 'بیشتر', back: 'بازگشت', you: 'شما',
    reply: 'پاسخ به کاربر', note: 'یادداشت داخلی', note_hint: 'فقط ادمین‌ها می‌بینند — برای کاربر ارسال نمی‌شود',
    reply_ph: 'پاسخ خود را بنویسید…', note_ph: 'یادداشت داخلی (کاربر نمی‌بیند)…', send: 'ارسال', saved: 'پاسخ آماده',
    no_saved: 'پاسخ آماده‌ای برای این موضوع نیست', attach: 'پیوست', status: 'وضعیت', priority: 'اولویت', assignee: 'مسئول',
    unassigned: '— بدون مسئول —', close: 'بستن', reopen: 'بازگشایی', close_q: 'تیکت بسته شود؟', customer: 'مشتری',
    services: 'سرویس‌ها', payments: 'آخرین پرداخت‌ها', other_tickets: 'تیکت‌های دیگر', no_perm_pay: 'دسترسی مشاهدهٔ پرداخت ندارید',
    crm_soon: 'نمای کامل مشتری (CRM) در فاز بعد', none_short: '—', internal: 'یادداشت داخلی', open_customer: 'مشتری',
    telegram: 'تلگرام من', tg_title: 'اتصال تلگرام برای اعلان تیکت‌ها', tg_linked: 'تلگرام شما متصل است.',
    tg_unlink: 'قطع اتصال', tg_get: 'دریافت کد اتصال', tg_steps: 'لینک زیر را در تلگرام باز کنید (یا دستور را برای ربات بفرستید). کد 10 دقیقه اعتبار دارد.',
    copy: 'کپی', copied: 'کپی شد', topics: 'موضوعات و پاسخ‌های آماده', file_big: 'هر فایل حداکثر 5 مگابایت', file_type: 'فقط عکس یا PDF',
    ev: { assigned: 'سپرده شد به', unassigned: 'مسئول برداشته شد', status: 'وضعیت', priority: 'اولویت', closed: 'بست', reopened: 'بازگشایی کرد',
      auto_closed: 'به‌طور خودکار بسته شد', created: 'تیکت را باز کرد', system: 'سامانه' },
    st: { open: 'باز', awaiting_admin: 'در انتظار پشتیبانی', awaiting_user: 'در انتظار کاربر', on_hold: 'در حال پیگیری', closed: 'بسته' },
    pr: { low: 'کم', normal: 'عادی', high: 'زیاد', urgent: 'فوری' },
    svc: { active: 'فعال', on_hold: 'در انتظار اتصال', limited: 'حجم تمام', expired: 'منقضی', disabled: 'غیرفعال', pending: 'در حال ساخت' },
    src: { site: 'سایت', bot: 'ربات', panel: 'پنل' },
  },
  en: {
    title: 'Tickets', search: 'Search: number, subject, user, phone…', all_topics: 'All topics', all_prio: 'All priorities',
    f_active: 'Active', f_all: 'All', anyone: 'Anyone', me: 'Assigned to me', none: 'Unassigned', empty: 'No tickets match these filters.',
    pick: 'Pick a ticket from the list.', more: 'More', back: 'Back', you: 'You',
    reply: 'Reply to user', note: 'Internal note', note_hint: 'Staff only — never sent to the user',
    reply_ph: 'Write your reply…', note_ph: 'Internal note (the user never sees it)…', send: 'Send', saved: 'Saved replies',
    no_saved: 'No saved replies for this topic', attach: 'Attach', status: 'Status', priority: 'Priority', assignee: 'Assignee',
    unassigned: '— unassigned —', close: 'Close', reopen: 'Reopen', close_q: 'Close this ticket?', customer: 'Customer',
    services: 'Services', payments: 'Recent payments', other_tickets: 'Other tickets', no_perm_pay: 'No permission to view payments',
    crm_soon: 'Full customer view (CRM) comes in the next phase', none_short: '—', internal: 'Internal note', open_customer: 'Customer',
    telegram: 'My Telegram', tg_title: 'Link Telegram for ticket alerts', tg_linked: 'Your Telegram is linked.',
    tg_unlink: 'Unlink', tg_get: 'Get a link code', tg_steps: 'Open the link below in Telegram (or send the command to the bot). The code is valid for 10 minutes.',
    copy: 'Copy', copied: 'Copied', topics: 'Topics & saved replies', file_big: 'Each file up to 5 MB', file_type: 'Images or PDF only',
    ev: { assigned: 'assigned to', unassigned: 'unassigned', status: 'status', priority: 'priority', closed: 'closed it', reopened: 'reopened it',
      auto_closed: 'closed automatically', created: 'opened the ticket', system: 'system' },
    st: { open: 'Open', awaiting_admin: 'Awaiting admin', awaiting_user: 'Awaiting user', on_hold: 'On hold', closed: 'Closed' },
    pr: { low: 'Low', normal: 'Normal', high: 'High', urgent: 'Urgent' },
    svc: { active: 'Active', on_hold: 'On hold', limited: 'Used up', expired: 'Expired', disabled: 'Disabled', pending: 'Creating' },
    src: { site: 'site', bot: 'bot', panel: 'panel' },
  },
}
const STATUSES = ['open', 'awaiting_admin', 'awaiting_user', 'on_hold', 'closed']
const PRIOS = ['low', 'normal', 'high', 'urgent']
const ST_TONE = { open: 'primary', awaiting_admin: 'warning', awaiting_user: 'success', on_hold: 'muted', closed: 'muted' }
const PR_TONE = { low: 'muted', normal: 'muted', high: 'warning', urgent: 'danger' }
const OK_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'application/pdf']
const apiPath = (url) => url.replace(/^\/api\/v1/, '')
const hm = (iso) => new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })

function useT() {
  const { lang } = useI18n()
  return [T[lang] || T.fa, lang]
}
const tname = (tp, lang) => (lang === 'en' ? tp?.name_en : tp?.name_fa) || tp?.name_fa || ''

function Ico({ d, w = 18 }) {
  return (
    <svg width={w} height={w} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {(Array.isArray(d) ? d : [d]).map((p, i) => <path key={i} d={p} />)}
    </svg>
  )
}
const I = {
  back: 'M15 18l-6-6 6-6', clip: 'M21.4 11.1l-9.2 9.2a6 6 0 01-8.5-8.5l9.2-9.2a4 4 0 015.7 5.7l-9.2 9.2a2 2 0 01-2.8-2.8l8.5-8.5',
  send: 'M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z', x: 'M18 6L6 18M6 6l12 12', user: ['M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2', 'M12 11a4 4 0 100-8 4 4 0 000 8z'],
  pdf: ['M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z', 'M14 2v6h6'], lock: ['M5 11h14v10H5z', 'M8 11V7a4 4 0 018 0v4'],
  tg: 'M21.5 4.5L2.5 11.8l6.2 2.2 2.3 6.5 3.5-4.4 5.3 3.9 1.7-15.5zM8.7 14l9.6-7.3', bolt: 'M13 10V3L4 14h7v7l9-11h-7z',
  search: ['M21 21l-4.3-4.3', 'M11 18a7 7 0 100-14 7 7 0 000 14z'], tag: 'M7 7h.01M3 11V5a2 2 0 012-2h6l10 10-8 8L3 11z',
}

function Chip({ tone, children }) {
  return <span className={`ti-chip ti-chip--${tone}`}>{children}</span>
}

/** the inbox fills the viewport from its top edge (desktop) — the page itself doesn't scroll */
function useFillHeight(ref) {
  const [h, setH] = useState(null)
  useLayoutEffect(() => {
    const fit = () => {
      const el = ref.current
      if (!el) return
      const top = el.getBoundingClientRect().top + window.scrollY
      const bottomNav = window.matchMedia('(max-width: 767px)').matches ? 76 : 12
      setH(Math.max(420, (window.visualViewport?.height || window.innerHeight) - top - bottomNav))
    }
    fit()
    window.addEventListener('resize', fit)
    return () => window.removeEventListener('resize', fit)
  }, [ref])
  return h
}

// ================================= inbox ========================================
export default function Tickets() {
  const [s, lang] = useT()
  const { id } = useParams()
  const go = useNavigate()
  const { can } = useAuth()
  const { refreshBadge } = useLiveTickets()
  const wrapRef = useRef(null)
  const height = useFillHeight(wrapRef)
  const [filters, setFilters] = useState(() => {
    try { return { status: 'active', topic: '', priority: '', assigned: '', q: '', ...JSON.parse(sessionStorage.getItem('ti_filters') || '{}') } }
    catch { return { status: 'active', topic: '', priority: '', assigned: '', q: '' } }
  })
  const [list, setList] = useState(null)
  const [topics, setTopics] = useState([])
  const [staff, setStaff] = useState([])
  const [qDraft, setQDraft] = useState(filters.q)
  const [tg, setTg] = useState(false)

  useEffect(() => { try { sessionStorage.setItem('ti_filters', JSON.stringify(filters)) } catch { /* private mode */ } }, [filters])
  useEffect(() => {
    api.get('/admin/tickets/topics/').then((r) => setTopics(r.data)).catch(() => {})
    api.get('/admin/tickets/staff/').then((r) => setStaff(r.data)).catch(() => {})
  }, [])
  useEffect(() => { const t = setTimeout(() => setFilters((f) => (f.q === qDraft ? f : { ...f, q: qDraft })), 350); return () => clearTimeout(t) }, [qDraft])

  const load = useCallback((offset = 0) => {
    const p = new URLSearchParams()
    Object.entries(filters).forEach(([k, v]) => v && p.set(k, v))
    if (offset) p.set('offset', offset)
    return api.get(`/admin/tickets/?${p}`).then((r) => {
      setList((cur) => (offset && cur ? { ...r.data, results: [...cur.results, ...r.data.results] } : r.data))
    }).catch(() => setList((c) => c || { results: [], count: 0, status_counts: {} }))
  }, [filters])
  useEffect(() => { load() }, [load])
  useTicketEvents(() => { load(); refreshBadge() })

  const set = (k, v) => setFilters((f) => ({ ...f, [k]: v }))
  const selected = id ? Number(id) : null

  return (
    <div className={'ti' + (selected ? ' ti--has-sel' : '')} ref={wrapRef} style={height ? { height } : undefined}>
      <style>{CSS}</style>
      {/* ---------- list pane ---------- */}
      <aside className="ti-list">
        <div className="ti-list-head">
          <div className="ti-list-title">
            <h1 className="text-lg font-bold">{s.title}</h1>
            <span className="ti-head-acts">
              <button type="button" className="ti-mini" onClick={() => setTg(true)} title={s.telegram}><Ico d={I.tg} w={16} /></button>
              {can('tickets.manage_topics') && <Link to="/tickets/topics" className="ti-mini" title={s.topics}><Ico d={I.tag} w={16} /></Link>}
            </span>
          </div>
          <label className="ti-search">
            <Ico d={I.search} w={16} />
            <input value={qDraft} onChange={(e) => setQDraft(e.target.value)} placeholder={s.search} />
          </label>
          <div className="ti-seg" role="tablist">
            {[['active', s.f_active], ...STATUSES.map((x) => [x, s.st[x]]), ['', s.f_all]].map(([k, l]) => (
              <button key={k || 'all'} type="button" className={'ti-seg-b' + (filters.status === k ? ' on' : '')} onClick={() => set('status', k)}>
                {l}{k && list?.status_counts && k !== 'active' && <span className="ti-seg-n">{list.status_counts[k] || 0}</span>}
              </button>
            ))}
          </div>
          <div className="ti-selects">
            <select className="input ti-sel" value={filters.assigned} onChange={(e) => set('assigned', e.target.value)}>
              <option value="">{s.anyone}</option><option value="me">{s.me}</option><option value="none">{s.none}</option>
              {staff.map((x) => <option key={x.id} value={x.id}>{x.display_name || x.username}</option>)}
            </select>
            <select className="input ti-sel" value={filters.topic} onChange={(e) => set('topic', e.target.value)}>
              <option value="">{s.all_topics}</option>
              {topics.map((tp) => <option key={tp.id} value={tp.id}>{tname(tp, lang)}</option>)}
            </select>
            <select className="input ti-sel" value={filters.priority} onChange={(e) => set('priority', e.target.value)}>
              <option value="">{s.all_prio}</option>
              {PRIOS.map((p) => <option key={p} value={p}>{s.pr[p]}</option>)}
            </select>
          </div>
        </div>
        <div className="ti-rows">
          {list === null ? <div className="grid place-items-center py-10"><Spinner /></div>
            : list.results.length === 0 ? <div className="ti-empty">{s.empty}</div>
              : list.results.map((r) => (
                <button key={r.id} type="button" className={'ti-row' + (selected === r.id ? ' on' : '') + (r.unread ? ' unread' : '')}
                  onClick={() => go(`/tickets/${r.id}`)}>
                  <span className="ti-row-top">
                    <b className="ti-row-subj">{r.subject}</b>
                    <span className="ti-row-time" dir="ltr">{jalali(r.last_activity_at, true, lang)}</span>
                  </span>
                  <span className="ti-row-mid">
                    <span dir="ltr" className="ti-num">#{r.number}</span>
                    <span className="ti-row-user">{r.user.username}</span>
                    <Chip tone={ST_TONE[r.status]}>{s.st[r.status]}</Chip>
                    {r.priority !== 'normal' && <Chip tone={PR_TONE[r.priority]}>{s.pr[r.priority]}</Chip>}
                  </span>
                  <span className="ti-row-bottom">
                    <span className="ti-row-prev">{r.last_message ? `${r.last_message.author === 'user' ? '' : '↩ '}${r.last_message.body || '📎'}` : ''}</span>
                    {r.assigned_to && <span className="ti-row-as">{r.assigned_to.username}</span>}
                    {r.unread > 0 && <span className="ti-badge">{r.unread}</span>}
                  </span>
                </button>
              ))}
          {list?.next != null && <button type="button" className="ti-more" onClick={() => load(list.next)}>{s.more}</button>}
        </div>
      </aside>

      {/* ---------- chat + customer ---------- */}
      {selected ? <TicketPane key={selected} id={selected} s={s} lang={lang} onChanged={() => { load(); refreshBadge() }} />
        : <section className="ti-pick"><Ico d={I.tag} w={28} /><p>{s.pick}</p></section>}
      {tg && <TelegramLink s={s} onClose={() => setTg(false)} />}
    </div>
  )
}

// ================================ one ticket ======================================
function useBlob(url) {
  const [src, setSrc] = useState(null)
  useEffect(() => {
    if (!url) return undefined
    let dead = false
    let obj
    api.get(apiPath(url), { responseType: 'blob' }).then((r) => { if (!dead) { obj = URL.createObjectURL(r.data); setSrc(obj) } }).catch(() => {})
    return () => { dead = true; if (obj) URL.revokeObjectURL(obj) }
  }, [url])
  return src
}

function Att({ a, onOpen }) {
  const isImg = a.content_type.startsWith('image/')
  const src = useBlob(isImg ? a.url : null)
  if (isImg) {
    return (
      <button type="button" className="ti-img" onClick={() => src && onOpen(src)} aria-label={a.original_name}>
        {src ? <img src={src} alt={a.original_name} /> : <Spinner />}
      </button>
    )
  }
  const open = async () => {
    try {
      const r = await api.get(apiPath(a.url), { responseType: 'blob' })
      const u = URL.createObjectURL(r.data)
      window.open(u, '_blank', 'noopener')
      setTimeout(() => URL.revokeObjectURL(u), 60000)
    } catch { /* ignore */ }
  }
  return <button type="button" className="ti-pdf" onClick={open}><Ico d={I.pdf} w={15} /><span dir="ltr">{a.original_name}</span></button>
}

function Lightbox({ src, onClose }) {
  useEffect(() => {
    const k = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', k)
    return () => document.removeEventListener('keydown', k)
  }, [onClose])
  return createPortal(
    <div className="ti-lightbox" onClick={onClose} role="dialog" aria-modal="true">
      <button type="button" className="ti-lightbox-x" aria-label="close"><Ico d={I.x} w={22} /></button>
      <img src={src} alt="" onClick={(e) => e.stopPropagation()} />
    </div>, document.body)
}

const actor = (label, s) => (label === 'system' || !label ? s.ev.system : label.replace(/^(staff|user):/, ''))

function eventText(e, s) {
  const who = actor(e.actor_label, s)
  switch (e.kind) {
    case 'assigned': return e.new_value ? `${who} · ${s.ev.assigned} ${e.new_value}` : `${who} · ${s.ev.unassigned}`
    case 'status': return `${who} · ${s.ev.status}: ${s.st[e.old_value] || e.old_value} → ${s.st[e.new_value] || e.new_value}`
    case 'priority': return `${who} · ${s.ev.priority}: ${s.pr[e.old_value] || e.old_value} → ${s.pr[e.new_value] || e.new_value}`
    case 'closed': return `${who} · ${s.ev.closed}`
    case 'reopened': return `${who} · ${s.ev.reopened}`
    case 'auto_closed': return s.ev.auto_closed
    default: return null
  }
}

function TicketPane({ id, s, lang, onChanged }) {
  const { can, staff: me } = useAuth()
  const toast = useToast()
  const confirm = useConfirm()
  const go = useNavigate()
  const [t, setT] = useState(null)
  const [err, setErr] = useState('')
  const [assignable, setAssignable] = useState([])
  const [canned, setCanned] = useState([])
  const [mode, setMode] = useState('reply')
  const [body, setBody] = useState('')
  const [files, setFiles] = useState([])
  const [busy, setBusy] = useState(false)
  const [lightbox, setLightbox] = useState(null)
  const [side, setSide] = useState(() => window.matchMedia('(min-width: 1280px)').matches)
  const listRef = useRef(null)
  const fileRef = useRef(null)

  const load = useCallback(() => api.get(`/admin/tickets/${id}/`).then((r) => { setT(r.data); setErr('') })
    .catch((e) => setErr(apiError(e))), [id])
  useEffect(() => { load() }, [load])
  useTicketEvents((e) => { if (e.ticket_id === id || e.event === 'reconnected') load() })
  useEffect(() => {
    if (can('tickets.assign')) api.get(`/admin/tickets/${id}/assignable/`).then((r) => setAssignable(r.data)).catch(() => {})
  }, [id])
  useEffect(() => {
    if (t?.topic?.id && can('tickets.reply')) api.get(`/admin/tickets/canned/?topic=${t.topic.id}`).then((r) => setCanned(r.data)).catch(() => {})
  }, [t?.topic?.id])
  const count = (t?.messages?.length || 0) + (t?.events?.length || 0)
  useEffect(() => { const el = listRef.current; if (el) el.scrollTop = el.scrollHeight }, [count])

  // messages + the events worth a line in the timeline, by time
  const timeline = useMemo(() => {
    if (!t) return []
    const items = t.messages.map((m) => ({ type: 'msg', at: m.created_at, m }))
    for (const e of t.events) {
      const txt = eventText(e, s)
      if (txt) items.push({ type: 'ev', at: e.created_at, e, txt })
    }
    items.sort((a, b) => new Date(a.at) - new Date(b.at))
    const out = []
    let day = null
    for (const it of items) {
      const d = new Date(it.at).toDateString()
      if (d !== day) { out.push({ type: 'day', at: it.at, key: 'd' + it.at }); day = d }
      out.push(it)
    }
    return out
  }, [t, s])

  const act = async (path, data) => {
    try { const r = await api.post(`/admin/tickets/${id}/${path}/`, data); setT(r.data); onChanged() }
    catch { /* FeedbackBridge shows the reason */ }
  }
  const pickFiles = (list) => {
    const out = [...files]
    for (const f of list) {
      if (out.length >= 3) break
      if (!OK_TYPES.includes(f.type)) { toast.error(s.file_type); continue }
      if (f.size > 5 * 1024 * 1024) { toast.error(s.file_big); continue }
      out.push(f)
    }
    setFiles(out)
  }
  const send = async (e) => {
    e?.preventDefault()
    if (!body.trim() && !files.length) return
    setBusy(true)
    const fd = new FormData()
    fd.append('body', body)
    fd.append('internal', mode === 'note' ? 'true' : 'false')
    files.forEach((f) => fd.append('attachments', f))
    try {
      const r = await api.post(`/admin/tickets/${id}/reply/`, fd, { quiet: true })
      setT(r.data); setBody(''); setFiles([]); onChanged()
    } catch (e2) { toast.error(apiError(e2)) } finally { setBusy(false) }
  }
  const close = () => confirm({ tone: 'warning', title: s.close_q, message: `#${t.number} — ${t.subject}`,
    action: async () => { const r = await api.post(`/admin/tickets/${id}/status/`, { status: 'closed' }, { quiet: true }); setT(r.data); onChanged() } })

  if (err && !t) return <section className="ti-chat"><div className="ti-empty">{err}</div></section>
  if (!t) return <section className="ti-chat grid place-items-center"><Spinner /></section>
  const closed = t.status === 'closed'

  return (
    <>
      <section className="ti-chat">
        <header className="ti-chat-head">
          <button type="button" className="ti-back" onClick={() => go('/tickets')} aria-label={s.back}><Ico d={I.back} /></button>
          <div className="min-w-0 flex-1">
            <b className="ti-chat-subj">{t.subject}</b>
            <span className="ti-chat-meta">
              <span dir="ltr" className="ti-num">#{t.number}</span> · {t.user.username} · {tname(t.topic, lang)} · {s.src[t.source] || t.source}
            </span>
          </div>
          <button type="button" className={'ti-mini' + (side ? ' on' : '')} onClick={() => setSide((v) => !v)} title={s.customer}><Ico d={I.user} w={16} /></button>
        </header>
        <div className="ti-controls">
          <label className="ti-ctl"><span>{s.status}</span>
            <select className="input" value={t.status} disabled={!can('tickets.reply')}
              onChange={(e) => {
                const v = e.target.value
                if ((v === 'closed' || closed) && !can('tickets.close')) return
                if (v === 'closed') close(); else act('status', { status: v })
              }}>
              {STATUSES.map((x) => <option key={x} value={x} disabled={(x === 'closed' || closed) && !can('tickets.close')}>{s.st[x]}</option>)}
            </select>
          </label>
          <label className="ti-ctl"><span>{s.priority}</span>
            <select className="input" value={t.priority} disabled={!can('tickets.reply')} onChange={(e) => act('priority', { priority: e.target.value })}>
              {PRIOS.map((p) => <option key={p} value={p}>{s.pr[p]}</option>)}
            </select>
          </label>
          <label className="ti-ctl"><span>{s.assignee}</span>
            <select className="input" value={t.assigned_to?.id || ''} disabled={!can('tickets.assign')}
              onChange={(e) => act('assign', { staff: e.target.value || null })}>
              <option value="">{s.unassigned}</option>
              {(assignable.length ? assignable : t.assigned_to ? [t.assigned_to] : []).map((x) => <option key={x.id} value={x.id}>{x.username}{x.id === me?.id ? ` (${s.you})` : ''}</option>)}
            </select>
          </label>
          {can('tickets.close') && (closed
            ? <button type="button" className="btn-primary text-sm ti-ctl-btn" onClick={() => act('status', { status: 'awaiting_admin' })}>{s.reopen}</button>
            : <button type="button" className="ti-ctl-btn ti-close" onClick={close}>{s.close}</button>)}
        </div>

        <div className="ti-msgs" ref={listRef}>
          {timeline.map((it) => {
            if (it.type === 'day') return <div key={it.key} className="ti-day"><span>{jalali(it.at, false, lang)}</span></div>
            if (it.type === 'ev') return <div key={'e' + it.e.id} className="ti-ev"><span>{it.txt} · <span dir="ltr">{hm(it.at)}</span></span></div>
            const m = it.m
            const staffMsg = m.author === 'staff'
            const cls = m.is_internal ? 'ti-msg ti-msg--note' : staffMsg ? 'ti-msg ti-msg--staff' : 'ti-msg ti-msg--user'
            return (
              <div key={'m' + m.id} className={cls}>
                <span className="ti-msg-who">
                  {m.is_internal && <Ico d={I.lock} w={12} />}
                  {staffMsg ? (m.staff_display || m.staff || '—') : t.user.username}
                  {m.is_internal && <span className="ti-msg-tag">{s.internal}</span>}
                  {m.channel === 'bot' && <span className="ti-msg-tag">{s.src.bot}</span>}
                </span>
                {m.body && <p className="ti-msg-body">{m.body}</p>}
                {m.attachments.length > 0 && <div className="ti-atts">{m.attachments.map((a) => <Att key={a.id} a={a} onOpen={setLightbox} />)}</div>}
                <span className="ti-msg-time" dir="ltr">{hm(m.created_at)}{staffMsg && !m.is_internal && <span className="ti-ticks">{m.read_by_user_at ? ' ✓✓' : ' ✓'}</span>}</span>
              </div>
            )
          })}
        </div>

        {can('tickets.reply') && (
          <form className={'ti-composer' + (mode === 'note' ? ' ti-composer--note' : '')} onSubmit={send}>
            <div className="ti-comp-top">
              <div className="ti-tabs">
                <button type="button" className={mode === 'reply' ? 'on' : ''} onClick={() => setMode('reply')}>{s.reply}</button>
                <button type="button" className={mode === 'note' ? 'on' : ''} onClick={() => setMode('note')}><Ico d={I.lock} w={13} /> {s.note}</button>
              </div>
              <select className="input ti-canned" value="" onChange={(e) => {
                const c = canned.find((x) => String(x.id) === e.target.value)
                if (c) setBody((b) => (b ? `${b}\n${c.body}` : c.body))
              }}>
                <option value="">{canned.length ? `⚡ ${s.saved}` : s.no_saved}</option>
                {canned.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
              </select>
            </div>
            {mode === 'note' && <p className="ti-note-hint">{s.note_hint}</p>}
            {files.length > 0 && (
              <div className="ti-files">{files.map((f, i) => (
                <span key={i} className="ti-file"><span dir="ltr">{f.name}</span>
                  <button type="button" onClick={() => setFiles(files.filter((_, j) => j !== i))} aria-label="remove"><Ico d={I.x} w={12} /></button></span>))}
              </div>
            )}
            <div className="ti-comp-row">
              <input ref={fileRef} type="file" hidden multiple accept="image/jpeg,image/png,image/gif,image/webp,application/pdf"
                onChange={(e) => { pickFiles(e.target.files); e.target.value = '' }} />
              <button type="button" className="ti-icon" onClick={() => fileRef.current?.click()} disabled={files.length >= 3} aria-label={s.attach}><Ico d={I.clip} /></button>
              <textarea className="ti-input" rows={2} maxLength={4000} value={body} placeholder={mode === 'note' ? s.note_ph : s.reply_ph}
                onChange={(e) => setBody(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) send(e) }} />
              <button type="submit" className="ti-send" disabled={busy || (!body.trim() && !files.length)} aria-label={s.send}>
                {busy ? <Spinner /> : <Ico d={I.send} />}
              </button>
            </div>
          </form>
        )}
      </section>
      {side && <CustomerPanel id={id} s={s} lang={lang} onClose={() => setSide(false)} />}
      {lightbox && <Lightbox src={lightbox} onClose={() => setLightbox(null)} />}
    </>
  )
}

// ============================ customer side panel ===================================
function CustomerPanel({ id, s, lang, onClose }) {
  const [d, setD] = useState(null)
  const go = useNavigate()
  useEffect(() => { api.get(`/admin/tickets/${id}/customer/`).then((r) => setD(r.data)).catch(() => setD(false)) }, [id])
  return (
    <aside className="ti-side">
      <div className="ti-side-head">
        <b>{s.customer}</b>
        <button type="button" className="ti-mini" onClick={onClose} aria-label="close"><Ico d={I.x} w={15} /></button>
      </div>
      {d === null ? <div className="grid place-items-center py-8"><Spinner /></div> : d === false ? null : (
        <div className="ti-side-body">
          <div className="ti-cust">
            <span className="ti-av">{(d.user.name || d.user.username).slice(0, 1).toUpperCase()}</span>
            <div className="min-w-0">
              <b className="block truncate">{d.user.name || d.user.username}</b>
              <span className="ti-side-sub" dir="ltr">{d.user.username}</span>
            </div>
          </div>
          <dl className="ti-kv">
            {d.user.phone && <><dt>📞</dt><dd dir="ltr">{d.user.phone}</dd></>}
            {d.user.email && <><dt>✉️</dt><dd dir="ltr">{d.user.email}</dd></>}
            {d.user.telegram_username && <><dt>✈️</dt><dd dir="ltr">@{d.user.telegram_username}</dd></>}
            <dt>🗓</dt><dd>{jalali(d.user.created_at, false, lang)}</dd>
          </dl>
          <h4>{s.services} ({d.services.length})</h4>
          {d.services.length === 0 ? <p className="ti-side-sub">{s.none_short}</p> : d.services.map((x) => (
            <div key={x.id} className="ti-side-item">
              <span className="truncate" dir="ltr">{x.panel_username}</span>
              <Chip tone={x.status === 'active' ? 'success' : x.status === 'on_hold' ? 'primary' : 'muted'}>{s.svc[x.status] || x.status}</Chip>
              <span className="ti-side-sub w-full">{gb(x.data_used)} / {x.data_limit ? gb(x.data_limit) : '∞'} GB{x.expire_at ? ` · ${jalali(x.expire_at, false, lang)}` : ''}</span>
            </div>
          ))}
          <h4>{s.payments}</h4>
          {d.payments === null ? <p className="ti-side-sub">{s.no_perm_pay}</p> : d.payments.length === 0 ? <p className="ti-side-sub">{s.none_short}</p>
            : d.payments.map((p) => (
              <div key={p.id} className="ti-side-item">
                <span>{toman(p.amount, lang)}</span><Chip tone={p.status === 'approved' ? 'success' : p.status === 'pending' ? 'warning' : 'muted'}>{p.status}</Chip>
                <span className="ti-side-sub w-full">{jalali(p.created_at, true, lang)}</span>
              </div>))}
          <h4>{s.other_tickets} ({d.open_tickets})</h4>
          {d.tickets.length === 0 ? <p className="ti-side-sub">{s.none_short}</p> : d.tickets.map((x) => (
            <button key={x.id} type="button" className="ti-side-item ti-side-link" onClick={() => go(`/tickets/${x.id}`)}>
              <span className="truncate">#{x.number} {x.subject}</span><Chip tone={ST_TONE[x.status]}>{s.st[x.status]}</Chip>
            </button>))}
          <p className="ti-crm">{s.crm_soon}</p>
        </div>
      )}
    </aside>
  )
}

// ============================ my Telegram link ======================================
export function TelegramLink({ s, onClose }) {
  const [st, setSt] = useState(null)
  const [code, setCode] = useState(null)
  const toast = useToast()
  const load = () => api.get('/admin/tickets/telegram-link/').then((r) => setSt(r.data)).catch(() => setSt({ linked: false }))
  useEffect(() => { load() }, [])
  const get = async () => { const r = await api.post('/admin/tickets/telegram-link/', null, { quiet: true }); setCode(r.data) }
  const unlink = async () => { await api.delete('/admin/tickets/telegram-link/'); setCode(null); load() }
  const copy = async (txt) => { if (await copyToClipboard(txt)) toast.success(s.copied) }
  return createPortal(
    <div className="ti-modal-wrap" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <style>{CSS}</style>
      <div className="ti-modal card" role="dialog" aria-modal="true">
        <div className="ti-side-head"><b><Ico d={I.tg} w={16} /> {s.tg_title}</b>
          <button type="button" className="ti-mini" onClick={onClose} aria-label="close"><Ico d={I.x} w={15} /></button></div>
        {st === null ? <Spinner /> : st.linked ? (
          <div className="space-y-3"><p>✅ {s.tg_linked}</p>
            <button type="button" className="ti-ctl-btn ti-close" onClick={unlink}>{s.tg_unlink}</button></div>
        ) : code ? (
          <div className="space-y-3">
            <p className="text-sm text-muted">{s.tg_steps}</p>
            {code.deep_link && <a className="btn-primary text-sm ti-tg-link" href={code.deep_link} target="_blank" rel="noreferrer" dir="ltr">{code.deep_link}</a>}
            <div className="ti-code"><code dir="ltr">{code.command}</code><button type="button" className="ti-mini" onClick={() => copy(code.command)}>{s.copy}</button></div>
            <button type="button" className="btn-ghost text-sm" onClick={load}>↻</button>
          </div>
        ) : <button type="button" className="btn-primary text-sm" onClick={get}>{s.tg_get}</button>}
      </div>
    </div>, document.body)
}

const CSS = `
.ti { display: grid; grid-template-columns: minmax(0, 1fr); gap: 12px; min-height: 420px; }
@media (min-width: 1024px) {
  .ti { grid-template-columns: 360px minmax(0, 1fr); }
  .ti:has(.ti-side) { grid-template-columns: 340px minmax(0, 1fr) 290px; }
}
@media (max-width: 1023px) {
  .ti--has-sel .ti-list { display: none; }
  .ti:not(.ti--has-sel) .ti-chat, .ti:not(.ti--has-sel) .ti-pick { display: none; }
  .ti--has-sel .ti-side { position: fixed; inset: 0; z-index: 60; border-radius: 0; }
}
@media (min-width: 1024px) { .ti-back { display: none !important; } }
.ti-list, .ti-chat, .ti-side, .ti-pick { min-height: 0; display: flex; flex-direction: column; border: 1px solid var(--c-border); border-radius: 16px;
  background: var(--c-surface); overflow: hidden; }
.dark .ti-list, .dark .ti-chat, .dark .ti-side, .dark .ti-pick { background: color-mix(in srgb, var(--c-surface) 92%, var(--c-bg)); }
.ti-pick { align-items: center; justify-content: center; gap: 10px; color: var(--c-text-muted); }
.ti-list-head { padding: 12px; display: flex; flex-direction: column; gap: 8px; border-bottom: 1px solid var(--c-border); }
.ti-list-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.ti-head-acts { display: inline-flex; gap: 6px; }
.ti-mini { min-width: 34px; height: 34px; padding: 0 9px; display: inline-grid; place-items: center; border-radius: 10px; border: 1px solid var(--c-border);
  background: none; color: var(--c-text); cursor: pointer; font-size: 12px; text-decoration: none; }
.ti-mini.on, .ti-mini:hover { border-color: var(--c-primary); color: var(--c-primary); }
.ti-search { display: flex; align-items: center; gap: 8px; padding: 0 10px; height: 40px; border-radius: 12px; border: 1px solid var(--c-border); color: var(--c-text-muted); }
.ti-search input { flex: 1; min-width: 0; border: 0; background: none; outline: none; color: var(--c-text); font-size: 14px; }
.ti-seg { display: flex; gap: 4px; overflow-x: auto; scrollbar-width: thin; padding-bottom: 2px; }
.ti-seg-b { flex-shrink: 0; display: inline-flex; align-items: center; gap: 5px; padding: 5px 10px; border-radius: 999px; font-size: 12px; font-weight: 600;
  border: 1px solid var(--c-border); background: none; color: var(--c-text-muted); cursor: pointer; white-space: nowrap; }
.ti-seg-b.on { background: var(--c-primary); border-color: var(--c-primary); color: #fff; }
.ti-seg-n { font-size: 10.5px; opacity: .8; }
.ti-selects { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; }
.ti-sel { font-size: 12.5px !important; padding: 6px 8px !important; min-height: 36px; }
.ti-rows { flex: 1; overflow-y: auto; }
.ti-row { width: 100%; text-align: start; display: flex; flex-direction: column; gap: 4px; padding: 11px 12px; border: 0; border-bottom: 1px solid var(--c-border);
  background: none; color: var(--c-text); cursor: pointer; }
.ti-row:hover { background: color-mix(in srgb, var(--c-primary) 5%, transparent); }
.ti-row.on { background: color-mix(in srgb, var(--c-primary) 12%, transparent); box-shadow: inset 3px 0 0 var(--c-primary); }
[dir="rtl"] .ti-row.on { box-shadow: inset -3px 0 0 var(--c-primary); }
.ti-row-top, .ti-row-bottom { display: flex; align-items: center; gap: 8px; min-width: 0; }
.ti-row-subj { flex: 1; min-width: 0; font-size: 13.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ti-row.unread .ti-row-subj { font-weight: 800; }
.ti-row-time { font-size: 10.5px; color: var(--c-text-muted); flex-shrink: 0; }
.ti-row-mid { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: 11.5px; color: var(--c-text-muted); }
.ti-num { font-family: 'JetBrains Mono', monospace; font-size: 11px; }
.ti-row-prev { flex: 1; min-width: 0; font-size: 12px; color: var(--c-text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ti-row-as { font-size: 10.5px; padding: 1px 6px; border-radius: 6px; background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); color: var(--c-text-muted); }
.ti-badge { min-width: 19px; height: 19px; padding: 0 5px; border-radius: 999px; display: grid; place-items: center; font-size: 10.5px; font-weight: 800; color: #fff; background: var(--c-primary); }
.ti-more { width: 100%; padding: 12px; border: 0; background: none; color: var(--c-primary); font-weight: 700; cursor: pointer; }
.ti-empty { padding: 28px 16px; text-align: center; color: var(--c-text-muted); font-size: 13px; }
.ti-chip { display: inline-flex; align-items: center; padding: 1px 8px; border-radius: 999px; font-size: 10.5px; font-weight: 700; white-space: nowrap; }
.ti-chip--primary { color: var(--c-primary-fg, var(--c-primary)); background: color-mix(in srgb, var(--c-primary) 14%, transparent); }
.ti-chip--warning { color: var(--c-warning-fg, var(--c-warning)); background: color-mix(in srgb, var(--c-warning) 16%, transparent); }
.ti-chip--success { color: var(--c-success-fg, var(--c-success)); background: color-mix(in srgb, var(--c-success) 14%, transparent); }
.ti-chip--danger { color: var(--c-danger-fg, var(--c-danger)); background: color-mix(in srgb, var(--c-danger) 14%, transparent); }
.ti-chip--muted { color: var(--c-text-muted); background: color-mix(in srgb, var(--c-text-muted) 14%, transparent); }

.ti-chat-head { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-bottom: 1px solid var(--c-border); }
.ti-back { width: 36px; height: 36px; display: grid; place-items: center; border-radius: 10px; border: 1px solid var(--c-border); background: none; color: var(--c-text); }
[dir="rtl"] .ti-back svg { transform: scaleX(-1); }
.ti-chat-subj { display: block; font-size: 14.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ti-chat-meta { display: block; font-size: 11.5px; color: var(--c-text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ti-controls { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 8px; padding: 8px 12px; border-bottom: 1px solid var(--c-border); }
.ti-ctl { display: flex; flex-direction: column; gap: 2px; font-size: 10.5px; color: var(--c-text-muted); flex: 1 1 120px; min-width: 0; }
.ti-ctl select { font-size: 12.5px !important; padding: 5px 8px !important; min-height: 34px; }
.ti-ctl-btn { min-height: 34px; padding: 0 14px; border-radius: 10px; font-size: 12.5px; font-weight: 700; cursor: pointer; }
.ti-close { border: 1px solid color-mix(in srgb, var(--c-danger) 45%, transparent); color: var(--c-danger-fg, var(--c-danger)); background: color-mix(in srgb, var(--c-danger) 8%, transparent); }
.ti-msgs { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; background: color-mix(in srgb, var(--c-primary) 3%, var(--c-bg)); }
.ti-day { display: flex; justify-content: center; margin: 8px 0; }
.ti-day span, .ti-ev span { font-size: 11px; padding: 2px 10px; border-radius: 999px; color: var(--c-text-muted); background: var(--c-surface); border: 1px solid var(--c-border); }
.ti-ev { display: flex; justify-content: center; margin: 4px 0; }
.ti-ev span { border-style: dashed; }
.ti-msg { max-width: min(80%, 620px); margin: 3px 0; padding: 7px 12px 5px; border-radius: 15px; display: flex; flex-direction: column; gap: 3px; word-break: break-word; }
.ti-msg--user { align-self: flex-start; background: var(--c-surface); border: 1px solid var(--c-border); border-end-start-radius: 5px; }
.ti-msg--staff { align-self: flex-end; background: var(--c-primary); color: #fff; border-end-end-radius: 5px; }
.ti-msg--note { align-self: stretch; max-width: none; border: 1.5px dashed color-mix(in srgb, var(--c-warning) 70%, transparent);
  background: color-mix(in srgb, var(--c-warning) 12%, var(--c-surface)); color: var(--c-text); }
.ti-msg-who { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 800; opacity: .9; }
.ti-msg--user .ti-msg-who { color: var(--c-primary); }
.ti-msg--note .ti-msg-who { color: var(--c-warning-fg, var(--c-warning)); }
.ti-msg-tag { font-size: 9.5px; font-weight: 700; padding: 0 5px; border-radius: 5px; background: color-mix(in srgb, currentColor 16%, transparent); }
.ti-msg-body { margin: 0; font-size: 13.5px; line-height: 1.75; white-space: pre-wrap; }
.ti-msg-time { align-self: flex-end; font-size: 10px; opacity: .7; }
.ti-atts { display: flex; flex-wrap: wrap; gap: 6px; }
.ti-img { width: 140px; height: 110px; padding: 0; border: 0; border-radius: 10px; overflow: hidden; cursor: zoom-in; background: rgba(0,0,0,.08); display: grid; place-items: center; }
.ti-img img { width: 100%; height: 100%; object-fit: cover; }
.ti-pdf { display: inline-flex; align-items: center; gap: 6px; max-width: 220px; padding: 6px 10px; border-radius: 10px; font-size: 12px; border: 1px solid currentColor; background: none; color: inherit; cursor: pointer; }
.ti-pdf span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ti-composer { border-top: 1px solid var(--c-border); padding: 8px 10px; display: flex; flex-direction: column; gap: 6px; }
.ti-composer--note { background: color-mix(in srgb, var(--c-warning) 9%, var(--c-surface)); }
.ti-comp-top { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ti-tabs { display: inline-flex; gap: 3px; padding: 3px; border-radius: 10px; background: color-mix(in srgb, var(--c-text-muted) 10%, transparent); }
.ti-tabs button { display: inline-flex; align-items: center; gap: 4px; padding: 5px 10px; border-radius: 8px; font-size: 12px; font-weight: 700; border: 0; background: none; color: var(--c-text-muted); cursor: pointer; }
.ti-tabs button.on { background: var(--c-surface); color: var(--c-text); box-shadow: 0 1px 3px rgba(0,0,0,.12); }
.ti-composer--note .ti-tabs button.on { color: var(--c-warning-fg, var(--c-warning)); }
.ti-canned { flex: 1 1 160px; font-size: 12.5px !important; padding: 5px 8px !important; min-height: 32px; }
.ti-note-hint { margin: 0; font-size: 11.5px; color: var(--c-warning-fg, var(--c-warning)); }
.ti-files { display: flex; flex-wrap: wrap; gap: 5px; }
.ti-file { display: inline-flex; align-items: center; gap: 5px; max-width: 220px; padding: 3px 8px; border-radius: 8px; font-size: 11.5px; background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); }
.ti-file span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ti-file button { border: 0; background: none; color: var(--c-text-muted); cursor: pointer; display: grid; }
.ti-comp-row { display: flex; align-items: flex-end; gap: 8px; }
.ti-input { flex: 1; min-width: 0; resize: vertical; min-height: 44px; max-height: 220px; padding: 9px 12px; border-radius: 14px; font-size: 14px; line-height: 1.6;
  border: 1px solid var(--c-border); background: var(--c-bg); color: var(--c-text); }
.ti-icon, .ti-send { width: 42px; height: 42px; flex-shrink: 0; border-radius: 999px; display: grid; place-items: center; border: 0; cursor: pointer; }
.ti-icon { background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); color: var(--c-text); }
.ti-send { background: var(--c-primary); color: #fff; }
.ti-composer--note .ti-send { background: color-mix(in srgb, var(--c-warning) 80%, #000); }
.ti-send:disabled, .ti-icon:disabled { opacity: .45; cursor: default; }
[dir="rtl"] .ti-send svg { transform: scaleX(-1); }

.ti-side-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 12px; border-bottom: 1px solid var(--c-border); }
.ti-side-head b { display: inline-flex; align-items: center; gap: 6px; }
.ti-side-body { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 8px; font-size: 13px; }
.ti-side-body h4 { margin: 8px 0 0; font-size: 12px; font-weight: 800; color: var(--c-text-muted); }
.ti-cust { display: flex; align-items: center; gap: 10px; }
.ti-av { width: 40px; height: 40px; border-radius: 999px; display: grid; place-items: center; font-weight: 800; color: #fff; background: var(--c-primary); flex-shrink: 0; }
.ti-side-sub { font-size: 11.5px; color: var(--c-text-muted); }
.ti-kv { display: grid; grid-template-columns: 24px 1fr; gap: 4px 6px; margin: 0; }
.ti-kv dd { margin: 0; min-width: 0; overflow-wrap: anywhere; }
.ti-side-item { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 4px 8px; padding: 8px 10px; border-radius: 10px;
  border: 1px solid var(--c-border); background: none; color: var(--c-text); text-align: start; font-size: 12.5px; }
.ti-side-link { cursor: pointer; }
.ti-side-link:hover { border-color: var(--c-primary); }
.ti-crm { margin-top: 8px; padding: 8px 10px; border-radius: 10px; font-size: 11.5px; color: var(--c-text-muted); border: 1px dashed var(--c-border); }
.ti-lightbox { position: fixed; inset: 0; z-index: 90; display: grid; place-items: center; padding: 16px; background: rgba(0,0,0,.86); }
.ti-lightbox img { max-width: 100%; max-height: 100%; border-radius: 10px; }
.ti-lightbox-x { position: absolute; top: 14px; inset-inline-end: 14px; width: 42px; height: 42px; border-radius: 999px; display: grid; place-items: center; border: 0; color: #fff; background: rgba(255,255,255,.14); }
.ti-modal-wrap { position: fixed; inset: 0; z-index: 80; display: grid; place-items: center; padding: 16px; background: rgba(0,0,0,.45); }
.ti-modal { width: min(460px, 100%); display: flex; flex-direction: column; gap: 12px; padding: 0 0 14px; }
.ti-modal > :not(.ti-side-head) { margin: 0 14px; }
.ti-tg-link { display: block; text-align: center; overflow-wrap: anywhere; }
.ti-code { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 10px; background: color-mix(in srgb, var(--c-text-muted) 10%, transparent); }
.ti-code code { flex: 1; min-width: 0; overflow-wrap: anywhere; font-size: 13px; }
@media (max-width: 767px) {
  .ti-list, .ti-chat, .ti-pick { border-radius: 14px; }
  .ti-msg { max-width: 88%; }
  .ti-input { font-size: 16px; }
  .ti-selects { grid-template-columns: 1fr 1fr; }
  .ti-selects .ti-sel:first-child { grid-column: 1 / -1; }
}
`
