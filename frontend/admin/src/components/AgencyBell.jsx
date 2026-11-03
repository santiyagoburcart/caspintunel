import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { jalali, relTime } from '../lib/format'
import { playChime } from '../lib/notifySound'

// v1.38.2 agency notifications — header bell (unread count, dropdown; phones: bottom sheet) + the «اعلان‌ها» page.
// ONE component, identical file in both SPAs: the group-manager panel (admin, components/GmBell.jsx wraps it) and the
// /agency/ reseller portal (user, pages/AgencyPortal.jsx). Same look as the customer bell.
//   http   — { get(url, cfg), post(url, body) } of that app (staff JWT / Agency token)
//   url    — notices endpoint relative to http: GET latest · ?page= · POST {read:true} | {id}
//   allTo  — the notifications page route · sound — () => ({ on, volume }) · evt — window event prefix · tid — test-id prefix
const T = {
  fa: { h: 'اعلان‌ها', all: 'همهٔ اعلان‌ها', mark: 'همه خوانده شد', none: 'اعلانی نیست.', close: 'بستن', prev: 'قبلی', next: 'بعدی',
    page: 'صفحهٔ {p} از {n}', unread: '{n} خوانده‌نشده' },
  en: { h: 'Notifications', all: 'All notifications', mark: 'Mark all read', none: 'No notifications.', close: 'Close', prev: 'Previous',
    next: 'Next', page: 'Page {p} of {n}', unread: '{n} unread' },
}
const KIND_ICON = {
  invoice_issued: 'M9 12h6m-6 4h6M7 3h7l5 5v11a2 2 0 01-2 2H7a2 2 0 01-2-2V5a2 2 0 012-2z',
  payment_approved: 'M5 13l4 4L19 7', request_approved: 'M5 13l4 4L19 7',
  payment_rejected: 'M6 6l12 12M18 6L6 18', request_rejected: 'M6 6l12 12M18 6L6 18',
}
const BELL = 'M15 17h5l-1.4-1.4A2 2 0 0118 14.2V11a6 6 0 10-12 0v3.2a2 2 0 01-.6 1.4L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9'
const MOBILE_Q = '(max-width: 767px)'
const tone = (k) => (/rejected/.test(k || '') ? 'bad' : /approved|paid/.test(k || '') ? 'ok' : 'info')
const NO_SOUND = () => ({ on: false, volume: 60 })

function useMobile() {
  const [m, setM] = useState(() => window.matchMedia(MOBILE_Q).matches)
  useEffect(() => {
    const mq = window.matchMedia(MOBILE_Q); const on = () => setM(mq.matches)
    mq.addEventListener('change', on); return () => mq.removeEventListener('change', on)
  }, [])
  return m
}

function Item({ n, lang, onClick }) {
  const title = (lang === 'en' && n.title_en) || n.title
  const body = (lang === 'en' && n.body_en) || n.body
  return (
    <button type="button" className={`gmb-item${n.read ? '' : ' is-unread'}`} data-tone={tone(n.kind)} onClick={onClick}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"
        strokeLinejoin="round" className="gmb-ic" aria-hidden="true"><path d={KIND_ICON[n.kind] || BELL} /></svg>
      <span className="gmb-body">
        <span className="gmb-title">{title}</span>
        {body && <span className="gmb-text">{body}</span>}
        <span className="gmb-time" title={jalali(n.created_at, true, lang)}>{relTime(n.created_at, lang)}</span>
      </span>
      {!n.read && <span className="gmb-dot" />}
    </button>
  )
}

export function AgencyBell({ http, url, allTo, lang, sound = NO_SOUND, evt = 'ct:gm-notices', tid = 'gm' }) {
  const s = T[lang] || T.fa
  const [open, setOpen] = useState(false)
  const [d, setD] = useState({ results: [], unread: 0 })
  const last = useRef(null)
  const box = useRef(null)
  const panel = useRef(null)
  const mobile = useMobile()
  const snd = useRef(sound); snd.current = sound
  const load = () => http.get(url).then((r) => {
    const n = r.data.unread || 0
    const p = snd.current()
    if (last.current !== null && n > last.current && p.on) playChime(p.volume, 'default')
    last.current = n; setD(r.data)
  }).catch(() => {})
  useEffect(() => {
    load()
    const t = setInterval(() => { if (document.visibilityState === 'visible') load() }, 45000)
    const on = () => load()
    window.addEventListener(evt, on)
    return () => { clearInterval(t); window.removeEventListener(evt, on) }
  }, [])
  useEffect(() => {
    if (!open) return undefined
    const inside = (el) => box.current?.contains(el) || panel.current?.contains(el)
    const off = (e) => { if (!inside(e.target)) setOpen(false) }
    const esc = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', off); document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('mousedown', off); document.removeEventListener('keydown', esc) }
  }, [open])
  const readOne = (n) => {
    if (n.read) return
    setD((cur) => ({ unread: Math.max(0, cur.unread - 1), results: cur.results.map((x) => (x.id === n.id ? { ...x, read: true } : x)) }))
    last.current = Math.max(0, (last.current || 1) - 1)
    http.post(url, { id: n.id }).then(() => window.dispatchEvent(new CustomEvent(evt + '-read'))).catch(() => {})
  }
  const readAll = () => {
    setD((cur) => ({ unread: 0, results: cur.results.map((x) => ({ ...x, read: true })) })); last.current = 0
    http.post(url, { read: true }).then(() => window.dispatchEvent(new CustomEvent(evt + '-read'))).catch(() => {})
  }
  const content = (
    <>
      <div className="gmb-head">
        <strong>{s.h}</strong>
        <span className="gmb-acts">
          {d.unread > 0 && <button type="button" className="gmb-mark" onClick={readAll}>{s.mark}</button>}
          <button type="button" className="gmb-x" onClick={() => setOpen(false)} aria-label={s.close}>✕</button>
        </span>
      </div>
      <div className="gmb-list">
        {d.results.length === 0 ? <div className="gmb-empty">{s.none}</div>
          : d.results.slice(0, 8).map((n) => <Item key={n.id} n={n} lang={lang} onClick={() => readOne(n)} />)}
      </div>
      <Link to={allTo} className="gmb-all" onClick={() => setOpen(false)} data-testid={`${tid}-bell-all`}>{s.all}</Link>
    </>
  )
  return (
    <div className="gmb" ref={box}>
      <style>{GMB_CSS}</style>
      <button type="button" className="gmb-btn" onClick={() => setOpen((o) => !o)} aria-label={`${s.h}${d.unread ? ` (${d.unread})` : ''}`}
        aria-expanded={open} data-testid={`${tid}-bell`}>
        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"
          strokeLinejoin="round" aria-hidden="true"><path d={BELL} /></svg>
        {d.unread > 0 && <span className="gmb-badge" data-testid={`${tid}-bell-count`}>{d.unread > 99 ? '99+' : d.unread}</span>}
      </button>
      {open && !mobile && <div className="gmb-panel" ref={panel}>{content}</div>}
      {open && mobile && createPortal(
        <div className="gmb-wrap" dir={lang === 'fa' ? 'rtl' : 'ltr'}>
          <style>{GMB_CSS}</style>
          <div className="gmb-scrim" onClick={() => setOpen(false)} />
          <div className="gmb-panel gmb-sheet" ref={panel} role="dialog" aria-modal="true" aria-label={s.h}>
            <span className="gmb-grab" aria-hidden="true" />{content}
          </div>
        </div>, document.body)}
    </div>
  )
}

/** The notifications page — every notice, 20 per page. */
export function AgencyNotificationsPage({ http, url, lang, evt = 'ct:gm-notices', tid = 'gm' }) {
  const s = T[lang] || T.fa
  const [page, setPage] = useState(1)
  const [d, setD] = useState(null)
  const load = (p = page) => http.get(url, { params: { page: p } }).then((r) => setD(r.data)).catch(() => setD({ results: [], pages: 1, page: 1, unread: 0 }))
  useEffect(() => { load(page) }, [page])
  useEffect(() => { const on = () => load(page); window.addEventListener(evt + '-read', on); return () => window.removeEventListener(evt + '-read', on) }, [page])
  const readOne = (n) => {
    if (n.read) return
    setD((cur) => ({ ...cur, unread: Math.max(0, cur.unread - 1), results: cur.results.map((x) => (x.id === n.id ? { ...x, read: true } : x)) }))
    http.post(url, { id: n.id }).then(() => window.dispatchEvent(new CustomEvent(evt))).catch(() => {})
  }
  const readAll = () => http.post(url, { read: true }).then(() => { load(page); window.dispatchEvent(new CustomEvent(evt)) })
  return (
    <section className="ap-card gmb-page" data-testid={`${tid}-notifications`}>
      <style>{GMB_CSS}</style>
      <div className="gmb-head gmb-head--page">
        <strong>{s.h}{d?.unread ? <small> · {s.unread.replace('{n}', d.unread)}</small> : null}</strong>
        {d?.unread > 0 && <button type="button" className="gmb-mark" onClick={readAll}>{s.mark}</button>}
      </div>
      {!d ? <div className="ap-spin" /> : d.results.length === 0 ? <div className="gmb-empty">{s.none}</div> : (
        <div className="gmb-list gmb-list--page">{d.results.map((n) => <Item key={n.id} n={n} lang={lang} onClick={() => readOne(n)} />)}</div>
      )}
      {d && d.pages > 1 && (
        <div className="gmb-pager">
          <button type="button" className="gmb-pg" disabled={page <= 1} onClick={() => setPage(page - 1)}>{s.prev}</button>
          <span>{s.page.replace('{p}', d.page).replace('{n}', d.pages)}</span>
          <button type="button" className="gmb-pg" disabled={page >= d.pages} onClick={() => setPage(page + 1)}>{s.next}</button>
        </div>
      )}
    </section>
  )
}

const GMB_CSS = `
.gmb { position: relative; }
.gmb-btn { position: relative; width: 36px; height: 36px; display: grid; place-items: center; border-radius: 999px; border: 0; cursor: pointer;
  color: var(--c-text-muted); background: color-mix(in srgb, var(--c-text-muted) 10%, transparent); }
.gmb-btn:hover { color: var(--c-text); background: color-mix(in srgb, var(--c-text-muted) 16%, transparent); }
.gmb-btn::after { content: ''; position: absolute; inset: -4px; }
.gmb-badge { position: absolute; top: -3px; inset-inline-end: -3px; min-width: 17px; height: 17px; padding: 0 4px; border-radius: 999px; font-size: 10px;
  font-weight: 800; line-height: 1; display: grid; place-items: center; color: #fff; background: color-mix(in srgb, var(--c-danger) 75%, #000); border: 2px solid var(--c-bg); }
.gmb-panel { position: absolute; top: calc(100% + 8px); inset-inline-end: 0; width: min(360px, 92vw); max-height: 460px; display: flex; flex-direction: column;
  color: var(--c-text); border: 1px solid var(--c-border); background: linear-gradient(var(--c-surface), var(--c-surface)), var(--c-bg);
  border-radius: 14px; box-shadow: 0 12px 32px rgba(0,0,0,.18); overflow: hidden; z-index: 60; text-align: start; }
.gmb-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 10px 12px; border-bottom: 1px solid var(--c-border); font-size: 13px; }
.gmb-head small { font-weight: 600; color: var(--c-text-muted); font-size: 12px; }
.gmb-head--page { padding: 0 0 10px; font-size: 15px; }
.gmb-acts { display: inline-flex; align-items: center; gap: 6px; }
.gmb-mark { font-size: 12px; font-weight: 700; color: var(--c-primary); background: none; border: 0; cursor: pointer; min-height: 36px; padding: 0 4px; }
.gmb-x { display: none; width: 36px; height: 36px; place-items: center; border-radius: 999px; border: 0; color: var(--c-text); background: color-mix(in srgb, var(--c-text-muted) 14%, transparent); }
.gmb-list { overflow-y: auto; overscroll-behavior: contain; }
.gmb-list--page { border: 1px solid var(--c-border); border-radius: 12px; }
.gmb-empty { padding: 24px 12px; text-align: center; font-size: 12.5px; color: var(--c-text-muted); }
.gmb-item { width: 100%; display: flex; align-items: flex-start; gap: 10px; padding: 11px 12px; text-align: start; background: none; border: 0;
  border-bottom: 1px solid var(--c-border); cursor: pointer; color: var(--c-text); min-height: 44px; }
.gmb-item:last-child { border-bottom: 0; }
.gmb-item:hover { background: color-mix(in srgb, var(--c-text-muted) 6%, transparent); }
.gmb-item.is-unread { background: color-mix(in srgb, var(--c-primary) 6%, transparent); }
.gmb-ic { flex-shrink: 0; margin-top: 2px; color: var(--c-primary); }
.gmb-item[data-tone="ok"] .gmb-ic { color: var(--c-success-fg); }
.gmb-item[data-tone="bad"] .gmb-ic { color: var(--c-danger-fg); }
.gmb-body { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
.gmb-title { font-size: 13px; font-weight: 700; overflow-wrap: anywhere; }
.gmb-text { font-size: 12.5px; color: var(--c-text-muted); overflow-wrap: anywhere; line-height: 1.7; }
.gmb-time { font-size: 11px; color: var(--c-text-muted); }
.gmb-dot { flex-shrink: 0; width: 8px; height: 8px; border-radius: 999px; background: var(--c-primary); margin-top: 6px; }
.gmb-all { display: flex; align-items: center; justify-content: center; min-height: 44px; font-size: 13px; font-weight: 700; color: var(--c-primary); border-top: 1px solid var(--c-border); }
.gmb-pager { display: flex; align-items: center; justify-content: center; gap: 12px; margin-top: 12px; font-size: 13px; }
.gmb-wrap { position: fixed; inset: 0; z-index: 1000; display: flex; flex-direction: column; justify-content: flex-end; }
.gmb-scrim { position: absolute; inset: 0; background: rgba(0,0,0,.5); }
.gmb-panel.gmb-sheet { position: relative; top: auto; inset-inline-end: auto; width: 100%; max-height: 88dvh; border-radius: 20px 20px 0 0; border-bottom: 0;
  padding-bottom: env(safe-area-inset-bottom, 0px); }
.gmb-grab { display: block; width: 40px; height: 4px; border-radius: 999px; margin: 8px auto 0; background: color-mix(in srgb, var(--c-text-muted) 45%, transparent); flex-shrink: 0; }
.gmb-sheet .gmb-head { padding: 10px 16px 12px; font-size: 16px; }
.gmb-sheet .gmb-x { display: grid; }
.gmb-sheet .gmb-list { flex: 1; min-height: 0; }
.gmb-sheet .gmb-item { padding: 14px 16px; }
.gmb-sheet .gmb-title { font-size: 14.5px; }
.gmb-sheet .gmb-text { font-size: 13.5px; }
.gmb-pg { min-height: 40px; padding: 0 14px; border-radius: 10px; border: 1px solid var(--c-border); background: transparent; color: var(--c-text); font: inherit; font-size: 13px; font-weight: 700; cursor: pointer; }
.gmb-pg:disabled { opacity: .45; cursor: not-allowed; }
@media (max-width: 767px) { .gmb-pg { min-height: 44px; } .gmb-btn { width: 40px; height: 40px; } }
`
