import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali } from '../lib/format'
import { Spinner } from '../components/ui'
import { useToast } from '../components/Toast'
import { useConfirm } from '../components/ConfirmDialog'

// Customer tickets: list → new ticket → Telegram-like chat (apps/tickets API).
const T = {
  fa: {
    title: 'پشتیبانی و تیکت‌ها', sub: 'سؤال یا مشکلی دارید؟ یک تیکت باز کنید — پاسخ همین‌جا و در ربات می‌رسد.',
    new: 'تیکت جدید', empty: 'هنوز تیکتی ندارید.', empty_cta: 'اولین تیکت را باز کنید',
    all: 'همه', open_f: 'باز', closed_f: 'بسته', you: 'شما', support: 'پشتیبانی', attach: 'پیوست',
    topic: 'موضوع', pick_topic: 'موضوع را انتخاب کنید', locked: 'بعد از اولین خرید', subject: 'عنوان',
    subject_ph: 'خلاصهٔ مشکل یا سؤال در یک خط', service: 'سرویس مرتبط (اختیاری)', no_service: '— بدون سرویس —',
    message: 'پیام', message_ph: 'توضیح کامل بنویسید…', files: 'پیوست (عکس یا PDF، حداکثر 3 فایل تا 5 مگابایت)',
    add_file: 'افزودن فایل', send: 'ارسال', create: 'ثبت تیکت', back: 'بازگشت', cancel: 'انصراف',
    expired: 'سرویس شما منقضی شده', renew: 'تمدید', expired_note: 'می‌توانید تیکت را هم ثبت کنید.',
    composer_ph: 'پیام بنویسید…', closed_banner: 'این تیکت بسته شده است.', reopen: 'بازگشایی',
    reopen_gone: 'مهلت بازگشایی تمام شده — یک تیکت جدید باز کنید.', close: 'بستن تیکت',
    close_q: 'این تیکت بسته شود؟', close_msg: 'اگر مشکل حل شده تیکت را ببندید. تا چند روز می‌توانید دوباره بازش کنید.',
    sent: 'ارسال شد', created: 'تیکت ثبت شد', today: 'امروز', yesterday: 'دیروز', new_ticket_short: 'جدید',
    file_too_big: 'هر فایل حداکثر 5 مگابایت', file_type: 'فقط عکس یا PDF', too_many_files: 'حداکثر 3 فایل',
    open_pdf: 'باز کردن PDF', other_hint: 'برای هر موضوع دیگری «سایر» را انتخاب کنید و عنوان دلخواه بنویسید.',
    err: {
      needs_service: 'این موضوع برای مشتریان است — قبل از اولین خرید از «سوالات قبل از خرید» استفاده کنید.',
      too_many_open: 'تعداد تیکت‌های باز شما به حداکثر رسیده — منتظر پاسخ بمانید یا یکی را ببندید.',
      closed: 'این تیکت بسته است — اول بازگشایی کنید.', reopen_expired: 'مهلت بازگشایی تمام شده — تیکت جدید باز کنید.',
      empty: 'پیام خالی است.', attachment: 'فایل پذیرفته نشد: فقط عکس یا PDF تا 5 مگابایت.', subject: 'عنوان را بنویسید.',
      topic: 'موضوع را انتخاب کنید.', default: 'انجام نشد — دوباره تلاش کنید.',
    },
    st: { open: 'باز', awaiting_admin: 'در انتظار پشتیبانی', awaiting_user: 'پاسخ داده شد', on_hold: 'در حال پیگیری', closed: 'بسته' },
  },
  en: {
    title: 'Support tickets', sub: 'A question or a problem? Open a ticket — the answer arrives here and in the bot.',
    new: 'New ticket', empty: 'You have no tickets yet.', empty_cta: 'Open your first ticket',
    all: 'All', open_f: 'Open', closed_f: 'Closed', you: 'You', support: 'Support', attach: 'attachment',
    topic: 'Topic', pick_topic: 'Pick a topic', locked: 'After your first purchase', subject: 'Subject',
    subject_ph: 'Your problem or question in one line', service: 'Related service (optional)', no_service: '— no service —',
    message: 'Message', message_ph: 'Describe it in detail…', files: 'Attachments (images or PDF, up to 3 files, 5 MB each)',
    add_file: 'Add a file', send: 'Send', create: 'Open ticket', back: 'Back', cancel: 'Cancel',
    expired: 'Your service has expired', renew: 'Renew', expired_note: 'You can still open a ticket.',
    composer_ph: 'Write a message…', closed_banner: 'This ticket is closed.', reopen: 'Reopen',
    reopen_gone: 'It can no longer be reopened — open a new ticket.', close: 'Close ticket',
    close_q: 'Close this ticket?', close_msg: 'Close it if the problem is solved. You can reopen it for a few days.',
    sent: 'Sent', created: 'Ticket opened', today: 'Today', yesterday: 'Yesterday', new_ticket_short: 'New',
    file_too_big: 'Each file up to 5 MB', file_type: 'Images or PDF only', too_many_files: 'At most 3 files',
    open_pdf: 'Open PDF', other_hint: 'For anything else pick “Other” and write your own subject.',
    err: {
      needs_service: 'This topic is for customers — before your first purchase use “Pre-purchase questions”.',
      too_many_open: 'You have too many open tickets — wait for an answer or close one.',
      closed: 'This ticket is closed — reopen it first.', reopen_expired: 'It can no longer be reopened — open a new ticket.',
      empty: 'The message is empty.', attachment: 'File refused: images or PDF up to 5 MB only.', subject: 'Write a subject.',
      topic: 'Pick a topic.', default: 'Not done — please try again.',
    },
    st: { open: 'Open', awaiting_admin: 'Waiting for support', awaiting_user: 'Answered', on_hold: 'On hold', closed: 'Closed' },
  },
}
const ST_TONE = { open: 'primary', awaiting_admin: 'warning', awaiting_user: 'success', on_hold: 'muted', closed: 'muted' }
const MAX_FILES = 3
const MAX_BYTES = 5 * 1024 * 1024
const OK_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'application/pdf']

function useT() {
  const { lang } = useI18n()
  return [T[lang] || T.fa, lang]
}
const errText = (s, e) => {
  const code = e?.response?.data?.code
  return (code && s.err[code]) || s.err.default
}
const topicName = (tp, lang) => (lang === 'en' ? tp?.name_en : tp?.name_fa) || tp?.name_fa || ''

function Ico({ d, w = 18 }) {
  return (
    <svg width={w} height={w} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {(Array.isArray(d) ? d : [d]).map((p, i) => <path key={i} d={p} />)}
    </svg>
  )
}
const I = {
  plus: 'M12 5v14M5 12h14', back: 'M15 18l-6-6 6-6', clip: 'M21.4 11.1l-9.2 9.2a6 6 0 01-8.5-8.5l9.2-9.2a4 4 0 015.7 5.7l-9.2 9.2a2 2 0 01-2.8-2.8l8.5-8.5',
  send: 'M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z', lock: ['M5 11h14v10H5z', 'M8 11V7a4 4 0 018 0v4'], x: 'M18 6L6 18M6 6l12 12',
  pdf: ['M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z', 'M14 2v6h6'], chat: 'M8 10h8M8 14h5M21 12c0 4.4-4 8-9 8-1.4 0-2.8-.3-4-.8L3 20l1.3-3.9C3.5 14.9 3 13.5 3 12c0-4.4 4-8 9-8s9 3.6 9 8z',
  check: 'M5 13l4 4L19 7', warn: ['M12 9v4', 'M12 17h.01', 'M10.3 3.9L2.7 17a2 2 0 001.7 3h15.2a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z'],
}

function StatusChip({ status, s }) {
  return <span className={`tk-chip tk-chip--${ST_TONE[status] || 'muted'}`}>{s.st[status] || status}</span>
}

/** listens for live ticket events from the bell's socket (components/NotificationBell) */
function useTicketEvents(fn) {
  const ref = useRef(fn)
  ref.current = fn
  useEffect(() => {
    const on = (e) => ref.current(e.detail || {})
    window.addEventListener('ct:ticket', on)
    return () => window.removeEventListener('ct:ticket', on)
  }, [])
}

// ================================ list =========================================
export function TicketsList() {
  const [s, lang] = useT()
  const [rows, setRows] = useState(null)
  const [filter, setFilter] = useState('all')
  const load = useCallback(() => {
    api.get('/tickets/').then((r) => setRows(r.data.results)).catch(() => setRows([]))
  }, [])
  useEffect(() => { load() }, [load])
  useTicketEvents(load)

  const shown = (rows || []).filter((r) => filter === 'all' || (filter === 'closed' ? r.status === 'closed' : r.status !== 'closed'))
  return (
    <div className="tk space-y-4">
      <style>{CSS}</style>
      <div className="tk-head">
        <div className="min-w-0">
          <h1 className="text-lg font-bold">{s.title}</h1>
          <p className="text-sm text-muted mt-1">{s.sub}</p>
        </div>
        <Link to="/tickets/new" className="btn-primary text-sm tk-new"><Ico d={I.plus} w={16} />{s.new}</Link>
      </div>
      <div className="tk-filters" role="tablist">
        {[['all', s.all], ['open', s.open_f], ['closed', s.closed_f]].map(([k, l]) => (
          <button key={k} type="button" role="tab" aria-selected={filter === k} className={'tk-filter' + (filter === k ? ' on' : '')}
            onClick={() => setFilter(k)}>{l}</button>
        ))}
      </div>
      {rows === null ? <div className="grid place-items-center py-16"><Spinner /></div> : shown.length === 0 ? (
        <div className="card tk-empty">
          <span className="tk-empty-ico"><Ico d={I.chat} w={26} /></span>
          <p className="text-muted">{s.empty}</p>
          <Link to="/tickets/new" className="btn-primary text-sm">{s.empty_cta}</Link>
        </div>
      ) : (
        <div className="card p-0 tk-list">
          {shown.map((r) => {
            const lm = r.last_message
            const preview = lm ? `${lm.author === 'user' ? s.you + ': ' : ''}${lm.body || (lm.attachments ? '📎 ' + s.attach : '')}` : ''
            return (
              <Link key={r.id} to={`/tickets/${r.id}`} className={'tk-row' + (r.unread ? ' tk-row--unread' : '')}>
                <span className="tk-row-ico"><Ico d={I.chat} /></span>
                <span className="tk-row-main">
                  <span className="tk-row-top">
                    <b className="tk-row-subj">{r.subject}</b>
                    <span className="tk-row-time" dir="ltr">{jalali(r.last_activity_at, true, lang)}</span>
                  </span>
                  <span className="tk-row-mid">
                    <span className="tk-row-num" dir="ltr">#{r.number}</span>
                    <span className="tk-row-topic">{topicName(r.topic, lang)}</span>
                    <StatusChip status={r.status} s={s} />
                  </span>
                  <span className="tk-row-bottom">
                    <span className="tk-row-prev">{preview}</span>
                    {r.unread > 0 && <span className="tk-badge">{r.unread}</span>}
                  </span>
                </span>
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ============================== new ticket ======================================
function useRenew() {
  const go = useNavigate()
  return async (serviceId) => {
    try {
      const { data } = await api.get(`/services/${serviceId}/renew-info/`)
      if (data.can_renew && data.plan) return go(`/checkout?plan=${data.plan.id}&renew=${serviceId}`)
    } catch { /* fall through */ }
    go('/store')
  }
}

function pickFiles(list, current, s, toast) {
  const out = [...current]
  for (const f of list) {
    if (out.length >= MAX_FILES) { toast.error(s.too_many_files); break }
    if (!OK_TYPES.includes(f.type)) { toast.error(s.file_type); continue }
    if (f.size > MAX_BYTES) { toast.error(s.file_too_big); continue }
    out.push(f)
  }
  return out
}

function FileChips({ files, onRemove }) {
  if (!files.length) return null
  return (
    <div className="tk-files">
      {files.map((f, i) => (
        <span key={i} className="tk-file">
          <Ico d={f.type === 'application/pdf' ? I.pdf : I.clip} w={14} />
          <span className="tk-file-name" dir="ltr">{f.name}</span>
          <button type="button" onClick={() => onRemove(i)} aria-label="remove"><Ico d={I.x} w={13} /></button>
        </span>
      ))}
    </div>
  )
}

export function TicketNew() {
  const [s, lang] = useT()
  const toast = useToast()
  const go = useNavigate()
  const renew = useRenew()
  const [info, setInfo] = useState(null)
  const [services, setServices] = useState([])
  const [f, setF] = useState({ topic: null, subject: '', body: '', service: '' })
  const [files, setFiles] = useState([])
  const [busy, setBusy] = useState(false)
  const fileRef = useRef(null)

  useEffect(() => {
    api.get('/tickets/topics/').then((r) => setInfo(r.data)).catch(() => setInfo({ topics: [] }))
    api.get('/services/').then((r) => setServices(r.data.results || r.data || [])).catch(() => {})
  }, [])

  const submit = async (e) => {
    e.preventDefault()
    if (!f.topic) return toast.error(s.err.topic)
    if (!f.subject.trim()) return toast.error(s.err.subject)
    setBusy(true)
    const fd = new FormData()
    fd.append('topic', f.topic); fd.append('subject', f.subject.trim()); fd.append('body', f.body)
    if (f.service) fd.append('service', f.service)
    files.forEach((x) => fd.append('attachments', x))
    try {
      const { data } = await api.post('/tickets/', fd)
      toast.success(s.created)
      go(`/tickets/${data.id}`, { replace: true })
    } catch (e2) { toast.error(errText(s, e2)) } finally { setBusy(false) }
  }

  if (!info) return <div className="grid place-items-center py-16"><Spinner /></div>
  return (
    <form className="tk tk-new-form space-y-4" onSubmit={submit}>
      <style>{CSS}</style>
      <div className="tk-head">
        <Link to="/tickets" className="tk-back" aria-label={s.back}><Ico d={I.back} /></Link>
        <h1 className="text-lg font-bold flex-1">{s.new}</h1>
      </div>

      {info.renew_hint && (
        <div className="tk-hint" role="note">
          <Ico d={I.warn} />
          <span className="flex-1"><b>{s.expired}</b> <span className="text-muted">— {s.expired_note}</span></span>
          <button type="button" className="btn-primary text-xs" onClick={() => renew(info.renew_hint.service_id)}>{s.renew}</button>
        </div>
      )}

      <section className="space-y-2">
        <h2 className="tk-label">{s.pick_topic}</h2>
        <div className="tk-topics">
          {info.topics.map((tp) => (
            <button key={tp.id} type="button" disabled={!tp.available} aria-pressed={f.topic === tp.id}
              className={'tk-topic' + (f.topic === tp.id ? ' on' : '') + (tp.available ? '' : ' locked')}
              onClick={() => tp.available && setF({ ...f, topic: tp.id })}>
              <b>{topicName(tp, lang)}</b>
              <span className="tk-topic-d">{tp.available ? (lang === 'en' ? tp.description_en : tp.description_fa) : <><Ico d={I.lock} w={12} /> {s.locked}</>}</span>
            </button>
          ))}
        </div>
        <p className="text-xs text-muted">{s.other_hint}</p>
      </section>

      <div className="card space-y-3">
        <label className="block">
          <span className="label">{s.subject}</span>
          <input className="input" maxLength={150} value={f.subject} placeholder={s.subject_ph}
            onChange={(e) => setF({ ...f, subject: e.target.value })} />
        </label>
        {services.length > 0 && (
          <label className="block">
            <span className="label">{s.service}</span>
            <select className="input" value={f.service} onChange={(e) => setF({ ...f, service: e.target.value })}>
              <option value="">{s.no_service}</option>
              {services.map((x) => <option key={x.id} value={x.id}>{x.panel_username}</option>)}
            </select>
          </label>
        )}
        <label className="block">
          <span className="label">{s.message}</span>
          <textarea className="input tk-textarea" rows={5} maxLength={4000} value={f.body} placeholder={s.message_ph}
            onChange={(e) => setF({ ...f, body: e.target.value })} />
        </label>
        <div>
          <span className="label">{s.files}</span>
          <FileChips files={files} onRemove={(i) => setFiles(files.filter((_, j) => j !== i))} />
          <input ref={fileRef} type="file" hidden multiple accept="image/jpeg,image/png,image/gif,image/webp,application/pdf"
            onChange={(e) => { setFiles(pickFiles(e.target.files, files, s, toast)); e.target.value = '' }} />
          {files.length < MAX_FILES && (
            <button type="button" className="tk-addfile" onClick={() => fileRef.current?.click()}>
              <Ico d={I.clip} w={15} /> {s.add_file}
            </button>
          )}
        </div>
      </div>
      <div className="tk-actions">
        <Link to="/tickets" className="btn-ghost text-sm">{s.cancel}</Link>
        <button type="submit" className="btn-primary text-sm" disabled={busy}>{busy ? '…' : s.create}</button>
      </div>
    </form>
  )
}

// ================================= chat ==========================================
const apiPath = (url) => url.replace(/^\/api\/v1/, '')     // attachment urls are absolute API paths

function useBlobUrl(path) {
  const [url, setUrl] = useState(null)
  useEffect(() => {
    if (!path) return undefined
    let dead = false
    let obj
    api.get(apiPath(path), { responseType: 'blob' }).then((r) => {
      if (dead) return
      obj = URL.createObjectURL(r.data)
      setUrl(obj)
    }).catch(() => {})
    return () => { dead = true; if (obj) URL.revokeObjectURL(obj) }
  }, [path])
  return url
}

function ImageThumb({ att, onOpen }) {
  const url = useBlobUrl(att.url)
  return (
    <button type="button" className="tk-img" onClick={() => url && onOpen(url)} aria-label={att.original_name}>
      {url ? <img src={url} alt={att.original_name} /> : <span className="tk-img-wait"><Spinner /></span>}
    </button>
  )
}

function PdfChip({ att, s }) {
  const open = async () => {
    try {
      const r = await api.get(apiPath(att.url), { responseType: 'blob' })
      const u = URL.createObjectURL(r.data)
      window.open(u, '_blank', 'noopener')
      setTimeout(() => URL.revokeObjectURL(u), 60000)
    } catch { /* ignore */ }
  }
  return (
    <button type="button" className="tk-pdf" onClick={open} title={s.open_pdf}>
      <Ico d={I.pdf} w={16} /><span dir="ltr">{att.original_name}</span>
    </button>
  )
}

export function Lightbox({ src, onClose }) {
  useEffect(() => {
    const k = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', k)
    return () => document.removeEventListener('keydown', k)
  }, [onClose])
  return createPortal(
    <div className="tk-lightbox" onClick={onClose} role="dialog" aria-modal="true">
      <button type="button" className="tk-lightbox-x" onClick={onClose} aria-label="close"><Ico d={I.x} w={22} /></button>
      <img src={src} alt="" onClick={(e) => e.stopPropagation()} />
    </div>, document.body)
}

function dayLabel(iso, s, lang) {
  const d = new Date(iso)
  const today = new Date()
  const y = new Date(); y.setDate(today.getDate() - 1)
  const same = (a, b) => a.toDateString() === b.toDateString()
  if (same(d, today)) return s.today
  if (same(d, y)) return s.yesterday
  return jalali(iso, false, lang)
}
const hm = (iso) => new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })

/** the chat fills the screen from its top edge down (any header height, either layout) */
function useFillHeight(ref) {
  const [h, setH] = useState(null)
  useLayoutEffect(() => {
    const fit = () => {
      const el = ref.current
      if (!el) return
      const top = el.getBoundingClientRect().top + window.scrollY
      setH(Math.max(360, (window.visualViewport?.height || window.innerHeight) - top - 8))
    }
    fit()
    window.addEventListener('resize', fit)
    window.visualViewport?.addEventListener('resize', fit)
    return () => { window.removeEventListener('resize', fit); window.visualViewport?.removeEventListener('resize', fit) }
  }, [ref])
  return h
}

export function TicketChat() {
  const [s, lang] = useT()
  const { id } = useParams()
  const toast = useToast()
  const confirm = useConfirm()
  const [t, setT] = useState(null)
  const [err, setErr] = useState(false)
  const [body, setBody] = useState('')
  const [files, setFiles] = useState([])
  const [busy, setBusy] = useState(false)
  const [lightbox, setLightbox] = useState(null)
  const boxRef = useRef(null)
  const listRef = useRef(null)
  const fileRef = useRef(null)
  const height = useFillHeight(boxRef)

  const load = useCallback(() => api.get(`/tickets/${id}/`).then((r) => { setT(r.data); setErr(false) }).catch(() => setErr(true)), [id])
  useEffect(() => { load() }, [load])
  useEffect(() => { const timer = setInterval(load, 30000); return () => clearInterval(timer) }, [load])
  useTicketEvents((ev) => { if (String(ev.ticket_id) === String(id)) load() })
  const count = t?.messages?.length || 0
  useEffect(() => { const el = listRef.current; if (el) el.scrollTop = el.scrollHeight }, [count])

  const groups = useMemo(() => {
    const out = []
    for (const m of t?.messages || []) {
      const day = new Date(m.created_at).toDateString()
      if (!out.length || out[out.length - 1].day !== day) out.push({ day, iso: m.created_at, items: [] })
      out[out.length - 1].items.push(m)
    }
    return out
  }, [t])

  const send = async (e) => {
    e?.preventDefault()
    if (!body.trim() && !files.length) return
    setBusy(true)
    const fd = new FormData()
    fd.append('body', body)
    files.forEach((x) => fd.append('attachments', x))
    try {
      const { data } = await api.post(`/tickets/${id}/reply/`, fd)
      setT(data); setBody(''); setFiles([])
    } catch (e2) { toast.error(errText(s, e2)) } finally { setBusy(false) }
  }
  const reopen = async () => {
    try { await api.post(`/tickets/${id}/reopen/`); load() } catch (e2) { toast.error(errText(s, e2)) }
  }
  const close = () => confirm({
    tone: 'warning', title: s.close_q, message: s.close_msg,
    action: async () => { await api.post(`/tickets/${id}/close/`); await load() },
  })

  if (err && !t) return <div className="card text-center text-muted py-10">{s.err.default}</div>
  if (!t) return <div className="grid place-items-center py-16"><Spinner /></div>
  const closed = t.status === 'closed'

  return (
    <div className="tk tk-chat" ref={boxRef} style={height ? { height } : undefined}>
      <style>{CSS}</style>
      <header className="tk-chat-head">
        <Link to="/tickets" className="tk-back" aria-label={s.back}><Ico d={I.back} /></Link>
        <div className="min-w-0 flex-1">
          <b className="tk-chat-subj">{t.subject}</b>
          <span className="tk-chat-meta"><span dir="ltr">#{t.number}</span> · {topicName(t.topic, lang)} · <StatusChip status={t.status} s={s} /></span>
        </div>
        {!closed && <button type="button" className="tk-close-btn" onClick={close}>{s.close}</button>}
      </header>

      <div className="tk-msgs" ref={listRef}>
        {groups.map((g) => (
          <div key={g.day}>
            <div className="tk-day"><span>{dayLabel(g.iso, s, lang)}</span></div>
            {g.items.map((m) => {
              const mine = m.author === 'user'
              return (
                <div key={m.id} className={'tk-msg ' + (mine ? 'tk-msg--me' : 'tk-msg--them')}>
                  {!mine && <span className="tk-msg-who">{m.author_name || s.support}</span>}
                  {m.body && <p className="tk-msg-body">{m.body}</p>}
                  {m.attachments.length > 0 && (
                    <div className="tk-msg-atts">
                      {m.attachments.map((a) => (a.content_type.startsWith('image/')
                        ? <ImageThumb key={a.id} att={a} onOpen={setLightbox} />
                        : <PdfChip key={a.id} att={a} s={s} />))}
                    </div>
                  )}
                  <span className="tk-msg-time" dir="ltr">
                    {hm(m.created_at)}{mine && <span className={'tk-ticks' + (m.read ? ' read' : '')}>{m.read ? '✓✓' : '✓'}</span>}
                  </span>
                </div>
              )
            })}
          </div>
        ))}
      </div>

      {closed ? (
        <div className="tk-banner">
          <span>{s.closed_banner} {!t.can_reopen && <span className="text-muted">{s.reopen_gone}</span>}</span>
          {t.can_reopen
            ? <button type="button" className="btn-primary text-sm" onClick={reopen}>{s.reopen}</button>
            : <Link to="/tickets/new" className="btn-primary text-sm">{s.new}</Link>}
        </div>
      ) : (
        <form className="tk-composer" onSubmit={send}>
          <FileChips files={files} onRemove={(i) => setFiles(files.filter((_, j) => j !== i))} />
          <div className="tk-composer-row">
            <input ref={fileRef} type="file" hidden multiple accept="image/jpeg,image/png,image/gif,image/webp,application/pdf"
              onChange={(e) => { setFiles(pickFiles(e.target.files, files, s, toast)); e.target.value = '' }} />
            <button type="button" className="tk-icon" onClick={() => fileRef.current?.click()} aria-label={s.add_file}
              disabled={files.length >= MAX_FILES}><Ico d={I.clip} /></button>
            <textarea className="tk-input" rows={1} maxLength={4000} value={body} placeholder={s.composer_ph}
              onChange={(e) => setBody(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) send(e) }} />
            <button type="submit" className="tk-send" disabled={busy || (!body.trim() && !files.length)} aria-label={s.send}>
              {busy ? <Spinner /> : <Ico d={I.send} />}
            </button>
          </div>
        </form>
      )}
      {lightbox && <Lightbox src={lightbox} onClose={() => setLightbox(null)} />}
    </div>
  )
}

const CSS = `
.tk-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.tk-head > .min-w-0 { flex: 1 1 220px; }
.tk-new { display: inline-flex; align-items: center; gap: 6px; }
.tk-back { width: 38px; height: 38px; display: grid; place-items: center; border-radius: 12px; border: 1px solid var(--c-border); color: var(--c-text); flex-shrink: 0; }
[dir="rtl"] .tk-back svg { transform: scaleX(-1); }
.tk-filters { display: inline-flex; gap: 4px; padding: 4px; border-radius: 999px; background: color-mix(in srgb, var(--c-text-muted) 10%, transparent); }
.tk-filter { padding: 6px 14px; border-radius: 999px; font-size: 13px; font-weight: 600; color: var(--c-text-muted); background: none; border: 0; cursor: pointer; }
.tk-filter.on { background: var(--c-primary); color: #fff; }
.tk-empty { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 36px 16px; text-align: center; }
.tk-empty-ico { width: 54px; height: 54px; border-radius: 16px; display: grid; place-items: center; color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 12%, transparent); }
.tk-list { overflow: hidden; }
.tk-row { display: flex; gap: 12px; padding: 14px 16px; border-bottom: 1px solid var(--c-border); color: inherit; text-decoration: none; min-width: 0; }
.tk-row:last-child { border-bottom: 0; }
.tk-row:hover { background: color-mix(in srgb, var(--c-primary) 5%, transparent); }
.tk-row-ico { width: 40px; height: 40px; border-radius: 12px; flex-shrink: 0; display: grid; place-items: center; color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 12%, transparent); }
.tk-row-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.tk-row-top, .tk-row-bottom { display: flex; align-items: center; gap: 8px; min-width: 0; }
.tk-row-subj { flex: 1; min-width: 0; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tk-row-time { font-size: 11px; color: var(--c-text-muted); flex-shrink: 0; }
.tk-row-mid { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 12px; color: var(--c-text-muted); }
.tk-row-num { font-family: 'JetBrains Mono', monospace; font-size: 11.5px; }
.tk-row-prev { flex: 1; min-width: 0; font-size: 12.5px; color: var(--c-text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tk-row--unread .tk-row-subj, .tk-row--unread .tk-row-prev { color: var(--c-text); font-weight: 700; }
.tk-badge { min-width: 20px; height: 20px; padding: 0 6px; border-radius: 999px; background: var(--c-primary); color: #fff; font-size: 11px; font-weight: 800; display: grid; place-items: center; }
.tk-chip { display: inline-flex; align-items: center; padding: 2px 9px; border-radius: 999px; font-size: 11px; font-weight: 700; white-space: nowrap; }
.tk-chip--primary { color: var(--c-primary-fg, var(--c-primary)); background: color-mix(in srgb, var(--c-primary) 14%, transparent); }
.tk-chip--warning { color: var(--c-warning-fg, var(--c-warning)); background: color-mix(in srgb, var(--c-warning) 16%, transparent); }
.tk-chip--success { color: var(--c-success-fg, var(--c-success)); background: color-mix(in srgb, var(--c-success) 14%, transparent); }
.tk-chip--muted { color: var(--c-text-muted); background: color-mix(in srgb, var(--c-text-muted) 14%, transparent); }
.tk-hint { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 10px 14px; border-radius: 14px; font-size: 13px;
  color: var(--c-warning-fg, var(--c-warning)); background: color-mix(in srgb, var(--c-warning) 12%, transparent); border: 1px solid color-mix(in srgb, var(--c-warning) 30%, transparent); }
.tk-hint b { color: var(--c-text); }
.tk-label { font-size: 13px; font-weight: 700; }
.tk-topics { display: grid; gap: 10px; grid-template-columns: repeat(auto-fill, minmax(min(100%, 200px), 1fr)); }
.tk-topic { text-align: start; display: flex; flex-direction: column; gap: 4px; padding: 13px 14px; border-radius: 14px; border: 1.5px solid var(--c-border);
  background: var(--c-surface); color: var(--c-text); cursor: pointer; min-height: 64px; transition: border-color .15s, background .15s; }
.tk-topic:hover:not(.locked) { border-color: var(--c-primary); }
.tk-topic.on { border-color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 10%, var(--c-surface)); }
.tk-topic.locked { opacity: .6; cursor: not-allowed; }
.tk-topic-d { font-size: 12px; color: var(--c-text-muted); display: inline-flex; align-items: center; gap: 4px; }
.tk-textarea { min-height: 120px; resize: vertical; }
.tk-files { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0; }
.tk-file { display: inline-flex; align-items: center; gap: 6px; max-width: 100%; padding: 5px 8px; border-radius: 10px; font-size: 12px;
  background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); }
.tk-file-name { max-width: 160px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tk-file button { display: grid; place-items: center; color: var(--c-text-muted); background: none; border: 0; cursor: pointer; }
.tk-addfile { display: inline-flex; align-items: center; gap: 6px; margin-top: 6px; padding: 8px 12px; border-radius: 10px; font-size: 13px;
  border: 1px dashed var(--c-border); background: none; color: var(--c-text); cursor: pointer; }
.tk-actions { display: flex; justify-content: flex-end; gap: 8px; }

/* chat */
.tk-chat { display: flex; flex-direction: column; min-height: 360px; border: 1px solid var(--c-border); border-radius: 18px; overflow: hidden; background: var(--c-surface); }
.tk-chat-head { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-bottom: 1px solid var(--c-border); background: var(--c-surface); }
.tk-chat-subj { display: block; font-size: 14.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tk-chat-meta { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: 12px; color: var(--c-text-muted); margin-top: 2px; }
.tk-close-btn { flex-shrink: 0; padding: 7px 12px; border-radius: 10px; font-size: 12.5px; font-weight: 600; border: 1px solid var(--c-border); background: none; color: var(--c-text); cursor: pointer; }
.tk-msgs { flex: 1; overflow-y: auto; padding: 12px 12px 16px; display: flex; flex-direction: column;
  background: color-mix(in srgb, var(--c-primary) 4%, var(--c-bg)); overscroll-behavior: contain; }
.tk-day { display: flex; justify-content: center; margin: 10px 0; }
.tk-day span { font-size: 11.5px; font-weight: 600; padding: 3px 10px; border-radius: 999px; color: var(--c-text-muted); background: color-mix(in srgb, var(--c-surface) 85%, transparent); border: 1px solid var(--c-border); }
.tk-msg { max-width: min(78%, 560px); margin: 3px 0; padding: 8px 12px 6px; border-radius: 16px; display: flex; flex-direction: column; gap: 4px; word-break: break-word; }
.tk-msg--me { align-self: flex-end; background: var(--c-primary); color: #fff; border-end-end-radius: 6px; }
.tk-msg--them { align-self: flex-start; background: var(--c-surface); color: var(--c-text); border: 1px solid var(--c-border); border-end-start-radius: 6px; }
.tk-msg-who { font-size: 11.5px; font-weight: 800; color: var(--c-primary); }
.tk-msg-body { margin: 0; font-size: 14px; line-height: 1.75; white-space: pre-wrap; }
.tk-msg-time { align-self: flex-end; font-size: 10.5px; opacity: .75; display: inline-flex; gap: 4px; align-items: center; }
.tk-ticks { letter-spacing: -2px; }
.tk-ticks.read { color: #bfe3ff; opacity: 1; }
.tk-msg-atts { display: flex; flex-wrap: wrap; gap: 6px; }
.tk-img { width: 150px; height: 120px; border-radius: 12px; overflow: hidden; border: 0; padding: 0; cursor: zoom-in; background: rgba(0,0,0,.08); }
.tk-img img { width: 100%; height: 100%; object-fit: cover; display: block; }
.tk-img-wait { display: grid; place-items: center; width: 100%; height: 100%; }
.tk-pdf { display: inline-flex; align-items: center; gap: 6px; max-width: 220px; padding: 7px 10px; border-radius: 10px; font-size: 12.5px; cursor: pointer;
  border: 1px solid currentColor; background: transparent; color: inherit; }
.tk-pdf span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tk-banner { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; padding: 12px 14px; border-top: 1px solid var(--c-border); font-size: 13px; background: var(--c-surface); }
.tk-composer { padding: 8px 10px calc(8px + env(safe-area-inset-bottom, 0px)); border-top: 1px solid var(--c-border); background: var(--c-surface); }
.tk-composer .tk-files { margin: 0 0 6px; }
.tk-composer-row { display: flex; align-items: flex-end; gap: 8px; }
.tk-input { flex: 1; min-width: 0; resize: none; max-height: 140px; min-height: 42px; padding: 10px 14px; border-radius: 20px; font-size: 16px; line-height: 1.5;
  border: 1px solid var(--c-border); background: var(--c-bg); color: var(--c-text); field-sizing: content; }
.tk-input:focus { outline: 2px solid color-mix(in srgb, var(--c-primary) 45%, transparent); outline-offset: 0; }
.tk-icon, .tk-send { width: 42px; height: 42px; flex-shrink: 0; border-radius: 999px; display: grid; place-items: center; border: 0; cursor: pointer; }
.tk-icon { background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); color: var(--c-text); }
.tk-send { background: var(--c-primary); color: #fff; }
.tk-send:disabled, .tk-icon:disabled { opacity: .45; cursor: default; }
[dir="rtl"] .tk-send svg { transform: scaleX(-1); }
.tk-lightbox { position: fixed; inset: 0; z-index: 90; display: grid; place-items: center; padding: 16px; background: rgba(0,0,0,.86); }
.tk-lightbox img { max-width: 100%; max-height: 100%; border-radius: 10px; }
.tk-lightbox-x { position: absolute; top: 14px; inset-inline-end: 14px; width: 42px; height: 42px; border-radius: 999px; display: grid; place-items: center; border: 0; color: #fff; background: rgba(255,255,255,.14); cursor: pointer; }
@media (max-width: 767px) {
  .tk-chat { border-radius: 0; border-inline: 0; margin-inline: calc(-1 * clamp(12px, 3vw, 28px)); }
  .tk-msg { max-width: 86%; }
  .tk-head .tk-new { width: 100%; justify-content: center; }
}
`
