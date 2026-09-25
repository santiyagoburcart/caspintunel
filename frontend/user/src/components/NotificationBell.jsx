import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { api, tokens } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { timeAgo } from '../lib/format'

const TYPE_ICON = {
  order_confirmed: 'M5 13l4 4L19 7',
  service_ready: 'M5 13l4 4L19 7',
  volume_warning: 'M12 9v4m0 4h.01M10.3 3.9L2.7 17a2 2 0 001.7 3h15.2a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z',
  expiry_warning: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z',
  admin_broadcast: 'M11 5.9V4a1 1 0 011.6-.8l7 5.3a1 1 0 010 1.6l-7 5.3A1 1 0 0111 14.9v-1.8C6 13.1 3 15 1 18c0-5.5 3-10.5 10-12.1z',
  broadcast: 'M11 5.9V4a1 1 0 011.6-.8l7 5.3a1 1 0 010 1.6l-7 5.3A1 1 0 0111 14.9v-1.8C6 13.1 3 15 1 18c0-5.5 3-10.5 10-12.1z',
}
const DEFAULT_ICON = 'M15 17h5l-1.4-1.4A2 2 0 0118 14.2V11a6 6 0 10-12 0v3.2a2 2 0 01-.6 1.4L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9'

function wsUrl() {
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${location.host}/ws/notifications/?token=${encodeURIComponent(tokens.access || '')}`
}

const MOBILE_Q = '(max-width: 767px)'

function useIsMobile() {
  const [m, setM] = useState(() => typeof window !== 'undefined' && window.matchMedia(MOBILE_Q).matches)
  useEffect(() => {
    const mq = window.matchMedia(MOBILE_Q)
    const on = () => setM(mq.matches)
    mq.addEventListener ? mq.addEventListener('change', on) : mq.addListener(on)
    return () => { mq.removeEventListener ? mq.removeEventListener('change', on) : mq.removeListener(on) }
  }, [])
  return m
}

export default function NotificationBell({ className = '' }) {
  const { t, lang } = useI18n()
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState([])
  const [unread, setUnread] = useState(0)
  const wsRef = useRef(null)
  const retryRef = useRef(0)
  const boxRef = useRef(null)
  const panelRef = useRef(null)
  const isMobile = useIsMobile()

  const loadList = () => {
    api.get('/notifications/').then(({ data }) => setItems(data.results || data)).catch(() => {})
  }
  const loadUnread = () => {
    api.get('/notifications/unread-count/').then(({ data }) => setUnread(data.unread_count || 0)).catch(() => {})
  }

  useEffect(() => {
    if (!tokens.access) return
    loadList()
    loadUnread()

    let closed = false
    const connect = () => {
      if (closed || !tokens.access) return
      const ws = new WebSocket(wsUrl())
      wsRef.current = ws
      ws.onopen = () => { retryRef.current = 0 }
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data)
          setItems((prev) => [data.notification, ...prev].slice(0, 20))
          setUnread((u) => data.unread_count ?? u + 1)
        } catch { /* ignore malformed frame */ }
      }
      ws.onclose = () => {
        if (closed) return
        const delay = Math.min(30000, 1000 * 2 ** retryRef.current)
        retryRef.current += 1
        setTimeout(connect, delay)
      }
      ws.onerror = () => ws.close()
    }
    connect()

    return () => { closed = true; wsRef.current?.close() }
  }, [])

  useEffect(() => {
    if (!open) return
    const inside = (el) => boxRef.current?.contains(el) || panelRef.current?.contains(el)
    const onDocClick = (e) => { if (!inside(e.target)) setOpen(false) }
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onKey)
    // the phone sheet covers the page — stop the page behind it from scrolling
    const prevOverflow = document.body.style.overflow
    if (isMobile) document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [open, isMobile])

  const markRead = (item) => {
    if (item.is_read) return
    setItems((prev) => prev.map((n) => (n.id === item.id ? { ...n, is_read: true } : n)))
    setUnread((u) => Math.max(0, u - 1))
    api.post(`/notifications/${item.id}/read/`).catch(() => {})
  }

  const markAllRead = () => {
    setItems((prev) => prev.map((n) => ({ ...n, is_read: true })))
    setUnread(0)
    api.post('/notifications/read-all/').catch(() => {})
  }

  const content = (
    <>
      <div className="ct-nbell-head">
        <strong>{t('notifications')}</strong>
        <span className="ct-nbell-head-acts">
          {items.some((n) => !n.is_read) && (
            <button className="ct-nbell-markall" onClick={markAllRead}>{t('mark_all_read')}</button>
          )}
          <button className="ct-nbell-close" onClick={() => setOpen(false)} aria-label={t('close')}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"
              strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </span>
      </div>
      <div className="ct-nbell-list">
        {items.length === 0 && <div className="ct-nbell-empty">{t('no_notifications')}</div>}
        {items.map((n) => {
          const title = lang === 'en' && n.title_en ? n.title_en : n.title
          const text = lang === 'en' && n.body_en ? n.body_en : n.body
          return (
            <button key={n.id} className={`ct-nbell-item ${n.is_read ? '' : 'is-unread'}`}
              onClick={() => markRead(n)}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                strokeLinecap="round" strokeLinejoin="round" className="ct-nbell-item-icon" aria-hidden="true">
                <path d={TYPE_ICON[n.type] || DEFAULT_ICON} />
              </svg>
              <span className="ct-nbell-item-body">
                <span className="ct-nbell-item-title">{title}</span>
                <span className="ct-nbell-item-text">{text}</span>
                <span className="ct-nbell-item-time">{timeAgo(n.created_at, lang)}</span>
              </span>
              {!n.is_read && <span className="ct-nbell-dot" />}
            </button>
          )
        })}
      </div>
    </>
  )

  return (
    <div ref={boxRef} className={`ct-nbell ${className}`}>
      <button className="ct-nbell-btn" onClick={() => setOpen((o) => !o)} aria-label={t('notifications')}>
        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
          strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d={DEFAULT_ICON} />
        </svg>
        {unread > 0 && <span className="ct-nbell-badge">{unread > 99 ? '99+' : unread}</span>}
      </button>

      {open && !isMobile && (
        <div ref={panelRef} className="ct-nbell-panel">
          {content}
        </div>
      )}

      {/* phones: a bottom sheet portalled to <body> — a fixed element inside
          the (backdrop-filtered) header would be positioned relative to the
          header instead of the viewport */}
      {open && isMobile && createPortal(
        <div className="ct-nbell-sheet-wrap" dir={lang === 'fa' ? 'rtl' : 'ltr'}>
          <div className="ct-nbell-scrim" onClick={() => setOpen(false)} />
          <div ref={panelRef} className="ct-nbell-panel ct-nbell-sheet" role="dialog" aria-modal="true"
            aria-label={t('notifications')}>
            <span className="ct-nbell-grab" aria-hidden="true" />
            {content}
          </div>
        </div>,
        document.body,
      )}

      <style>{NBELL_CSS}</style>
    </div>
  )
}

const NBELL_CSS = `
.ct-nbell { position: relative; }
.ct-nbell-btn {
  position: relative; width: 36px; height: 36px; display: grid; place-items: center; border-radius: 999px;
  color: var(--c-text-muted); background: color-mix(in srgb, var(--c-text-muted) 10%, transparent);
  border: 0; cursor: pointer; transition: color .15s, background .15s;
}
.ct-nbell-btn:hover { color: var(--c-text); background: color-mix(in srgb, var(--c-text-muted) 16%, transparent); }
.ct-nbell-badge {
  position: absolute; top: -2px; inset-inline-end: -2px; min-width: 16px; height: 16px; padding: 0 3px;
  border-radius: 999px; background: var(--c-danger, #ef4444); color: #fff; font-size: 10px; font-weight: 800;
  display: grid; place-items: center; line-height: 1; border: 2px solid var(--c-surface);
}
.ct-nbell-panel {
  position: absolute; top: calc(100% + 8px); inset-inline-end: 0; width: min(360px, 92vw); max-height: 420px;
  display: flex; flex-direction: column; color: var(--c-text); border: 1px solid var(--c-border);
  /* solid: --c-surface alone is translucent in dark themes and made the list unreadable */
  background: linear-gradient(var(--c-surface), var(--c-surface)), var(--c-bg);
  border-radius: 14px; box-shadow: 0 12px 32px rgba(0,0,0,.18); overflow: hidden; z-index: 50;
}
.ct-nbell-head {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 10px 12px; border-bottom: 1px solid var(--c-border); font-size: 13px;
}
.ct-nbell-head-acts { display: inline-flex; align-items: center; gap: 6px; }
.ct-nbell-close {
  display: none; width: 34px; height: 34px; place-items: center; border-radius: 999px; border: 0; cursor: pointer;
  color: var(--c-text); background: color-mix(in srgb, var(--c-text-muted) 14%, transparent);
}
.ct-nbell-markall { font-size: 11px; color: var(--c-primary); background: none; border: 0; cursor: pointer; }
.ct-nbell-markall:hover { text-decoration: underline; }
.ct-nbell-list { overflow-y: auto; overscroll-behavior: contain; -webkit-overflow-scrolling: touch; }
.ct-nbell-empty { padding: 24px 12px; text-align: center; font-size: 12px; color: var(--c-text-muted); }
.ct-nbell-item {
  width: 100%; display: flex; align-items: flex-start; gap: 8px; padding: 10px 12px; text-align: start;
  background: none; border: 0; border-bottom: 1px solid var(--c-border); cursor: pointer;
}
.ct-nbell-item:last-child { border-bottom: 0; }
.ct-nbell-item:hover { background: color-mix(in srgb, var(--c-text-muted) 6%, transparent); }
.ct-nbell-item.is-unread { background: color-mix(in srgb, var(--c-primary) 6%, transparent); }
.ct-nbell-item-icon { flex-shrink: 0; margin-top: 2px; color: var(--c-primary); }
.ct-nbell-item-body { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
.ct-nbell-item-title { font-size: 12.5px; font-weight: 700; color: var(--c-text); }
.ct-nbell-item-text { font-size: 12px; color: var(--c-text-muted); overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.ct-nbell-item-time { font-size: 10.5px; color: var(--c-text-muted); }
.ct-nbell-dot { flex-shrink: 0; width: 7px; height: 7px; border-radius: 999px; background: var(--c-primary); margin-top: 5px; }

/* ---- phones (≤767px): full-width bottom sheet ---- */
.ct-nbell-sheet-wrap { position: fixed; inset: 0; width: 100vw; max-width: 100%; z-index: 1000; display: flex; flex-direction: column; justify-content: flex-end; }
.ct-nbell-scrim { position: absolute; inset: 0; background: rgba(0,0,0,.5); animation: ct-nbell-fade .18s ease-out; }
.ct-nbell-panel.ct-nbell-sheet {
  position: relative; top: auto; inset-inline-end: auto; width: 100%; max-height: 88vh; max-height: 88dvh;
  border-radius: 20px 20px 0 0; border-bottom: 0; box-shadow: 0 -12px 40px rgba(0,0,0,.35);
  padding-bottom: env(safe-area-inset-bottom, 0px); animation: ct-nbell-up .22s ease-out;
}
.ct-nbell-grab { display: block; width: 40px; height: 4px; border-radius: 999px; margin: 8px auto 0;
  background: color-mix(in srgb, var(--c-text-muted) 45%, transparent); flex-shrink: 0; }
.ct-nbell-sheet .ct-nbell-head { padding: 10px 16px 12px; font-size: 16px; flex-shrink: 0; }
.ct-nbell-sheet .ct-nbell-close { display: grid; }
.ct-nbell-sheet .ct-nbell-markall { font-size: 13px; font-weight: 600; padding: 6px 4px; }
.ct-nbell-sheet .ct-nbell-list { flex: 1; min-height: 0; }
.ct-nbell-sheet .ct-nbell-item { padding: 14px 16px; gap: 12px; }
.ct-nbell-sheet .ct-nbell-item-icon { width: 20px; height: 20px; }
.ct-nbell-sheet .ct-nbell-item-title { font-size: 14.5px; line-height: 1.6; }
.ct-nbell-sheet .ct-nbell-item-text { font-size: 13.5px; line-height: 1.8; -webkit-line-clamp: unset; display: block; white-space: pre-line; word-break: break-word; }
.ct-nbell-sheet .ct-nbell-item-time { font-size: 11.5px; }
.ct-nbell-sheet .ct-nbell-empty { padding: 40px 16px; font-size: 14px; }
@keyframes ct-nbell-up { from { transform: translateY(100%); } to { transform: none; } }
@keyframes ct-nbell-fade { from { opacity: 0; } to { opacity: 1; } }
`
