import { useEffect, useRef, useState } from 'react'
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

export default function NotificationBell({ className = '' }) {
  const { t, lang } = useI18n()
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState([])
  const [unread, setUnread] = useState(0)
  const wsRef = useRef(null)
  const retryRef = useRef(0)
  const boxRef = useRef(null)

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
    const onDocClick = (e) => { if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [open])

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

  return (
    <div ref={boxRef} className={`ct-nbell ${className}`}>
      <button className="ct-nbell-btn" onClick={() => setOpen((o) => !o)} aria-label={t('notifications')}>
        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
          strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d={DEFAULT_ICON} />
        </svg>
        {unread > 0 && <span className="ct-nbell-badge">{unread > 99 ? '99+' : unread}</span>}
      </button>

      {open && (
        <div className="ct-nbell-panel">
          <div className="ct-nbell-head">
            <strong>{t('notifications')}</strong>
            {items.some((n) => !n.is_read) && (
              <button className="ct-nbell-markall" onClick={markAllRead}>{t('mark_all_read')}</button>
            )}
          </div>
          <div className="ct-nbell-list">
            {items.length === 0 && <div className="ct-nbell-empty">{t('no_notifications')}</div>}
            {items.map((n) => {
              const title = lang === 'en' && n.title_en ? n.title_en : n.title
              const body = lang === 'en' && n.body_en ? n.body_en : n.body
              return (
                <button key={n.id} className={`ct-nbell-item ${n.is_read ? '' : 'is-unread'}`}
                  onClick={() => markRead(n)}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                    strokeLinecap="round" strokeLinejoin="round" className="ct-nbell-item-icon" aria-hidden="true">
                    <path d={TYPE_ICON[n.type] || DEFAULT_ICON} />
                  </svg>
                  <span className="ct-nbell-item-body">
                    <span className="ct-nbell-item-title">{title}</span>
                    <span className="ct-nbell-item-text">{body}</span>
                    <span className="ct-nbell-item-time">{timeAgo(n.created_at, lang)}</span>
                  </span>
                  {!n.is_read && <span className="ct-nbell-dot" />}
                </button>
              )
            })}
          </div>
        </div>
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
  display: flex; flex-direction: column; background: var(--c-surface); border: 1px solid var(--c-border);
  border-radius: 14px; box-shadow: 0 12px 32px rgba(0,0,0,.18); overflow: hidden; z-index: 50;
}
.ct-nbell-head {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 10px 12px; border-bottom: 1px solid var(--c-border); font-size: 13px;
}
.ct-nbell-markall { font-size: 11px; color: var(--c-primary); background: none; border: 0; cursor: pointer; }
.ct-nbell-markall:hover { text-decoration: underline; }
.ct-nbell-list { overflow-y: auto; }
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
.ct-nbell-item-time { font-size: 10.5px; color: var(--c-text-muted); font-family: 'JetBrains Mono', ui-monospace, monospace; }
.ct-nbell-dot { flex-shrink: 0; width: 7px; height: 7px; border-radius: 999px; background: var(--c-primary); margin-top: 5px; }
`
