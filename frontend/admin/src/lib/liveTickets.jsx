import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { api, tokens } from './api'
import { useAuth } from './auth'

/**
 * Live feed for the ticket inbox (backend: apps.tickets.notify → /ws/admin/tickets/).
 * One WebSocket per admin tab for staff with `tickets.view`. Exposes the badge
 * (tickets waiting for this staff member: open / awaiting admin, unassigned or
 * theirs, within their topic scope) and lets pages subscribe to events to refetch.
 */
const Ctx = createContext({ badge: 0, subscribe: () => () => {}, refreshBadge: () => {} })

function wsUrl() {
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${location.host}/ws/admin/tickets/?token=${encodeURIComponent(tokens.access || '')}`
}

export function LiveTicketsProvider({ children }) {
  const { staff, can } = useAuth()
  const enabled = !!staff && can('tickets.view')
  const [badge, setBadge] = useState(0)
  const listeners = useRef(new Set())

  const refreshBadge = useCallback(() => {
    api.get('/admin/tickets/badge/').then((r) => setBadge(r.data.badge || 0)).catch(() => {})
  }, [])
  const subscribe = useCallback((fn) => {
    listeners.current.add(fn)
    return () => listeners.current.delete(fn)
  }, [])

  useEffect(() => {
    if (!enabled) { setBadge(0); return undefined }
    refreshBadge()
    let closed = false
    let ws = null
    let retry = 0
    let retryTimer = null
    let pingTimer = null
    const emit = (msg) => listeners.current.forEach((fn) => { try { fn(msg) } catch { /* ignore */ } })
    const connect = () => {
      if (closed || !tokens.access) return
      ws = new WebSocket(wsUrl())
      ws.onopen = () => {
        retry = 0
        refreshBadge()
        emit({ event: 'reconnected' })
        clearInterval(pingTimer)
        pingTimer = setInterval(() => { try { ws.send('ping') } catch { /* closed */ } }, 25000)
      }
      ws.onmessage = (ev) => {
        if (ev.data === 'pong') return
        let msg
        try { msg = JSON.parse(ev.data) } catch { return }
        if (typeof msg.badge === 'number') setBadge(msg.badge)
        emit(msg)
      }
      ws.onclose = async (ev) => {
        clearInterval(pingTimer)
        if (closed) return
        if (ev.code === 4401) { try { await api.get('/admin/auth/me/') } catch { /* interceptor handles logout */ } }
        const delay = Math.min(30000, 1000 * 2 ** retry)
        retry += 1
        retryTimer = setTimeout(connect, delay)
      }
      ws.onerror = () => { try { ws.close() } catch { /* ignore */ } }
    }
    connect()
    const onVisible = () => {
      if (document.visibilityState !== 'visible') return
      refreshBadge()
      if (!ws || ws.readyState === WebSocket.CLOSED) { clearTimeout(retryTimer); retry = 0; connect() }
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      closed = true
      clearTimeout(retryTimer)
      clearInterval(pingTimer)
      document.removeEventListener('visibilitychange', onVisible)
      try { ws?.close() } catch { /* ignore */ }
    }
  }, [enabled, staff?.id, refreshBadge])

  return <Ctx.Provider value={{ badge, subscribe, refreshBadge }}>{children}</Ctx.Provider>
}

export const useLiveTickets = () => useContext(Ctx)

/** Run `fn(event)` for every live ticket event while the component is mounted. */
export function useTicketEvents(fn) {
  const { subscribe } = useLiveTickets()
  const ref = useRef(fn)
  ref.current = fn
  useEffect(() => subscribe((e) => ref.current(e)), [subscribe])
}
