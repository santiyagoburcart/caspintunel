import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { api, tokens } from './api'
import { useAuth } from './auth'

/**
 * Live feed for the payments queue (backend: apps.notifications.live).
 * One WebSocket per admin tab, opened only for staff with `payment.view`.
 * Exposes the pending-payments count (nav badge) and lets pages subscribe to
 * queue events (new order, receipt uploaded, SMS auto-approved, another
 * admin approved/rejected…) to refetch. The server stays the source of truth:
 * events are only a "something changed" nudge.
 */
const Ctx = createContext({ pendingCount: null, connected: false, subscribe: () => () => {}, refreshCount: () => {} })

function wsUrl() {
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${location.host}/ws/admin/payments/?token=${encodeURIComponent(tokens.access || '')}`
}

export function LivePaymentsProvider({ children }) {
  const { staff, can } = useAuth()
  const enabled = !!staff && can('payment.view')
  const [pendingCount, setPendingCount] = useState(null)
  const [connected, setConnected] = useState(false)
  const listeners = useRef(new Set())

  const refreshCount = useCallback(() => {
    api.get('/admin/payments/pending/')
      .then((r) => setPendingCount(r.data.count ?? (r.data.results || []).length))
      .catch(() => {})
  }, [])

  const subscribe = useCallback((fn) => {
    listeners.current.add(fn)
    return () => listeners.current.delete(fn)
  }, [])

  useEffect(() => {
    if (!enabled) { setPendingCount(null); return }
    refreshCount()

    let closed = false
    let ws = null
    let retry = 0
    let retryTimer = null
    let pingTimer = null

    const connect = () => {
      if (closed || !tokens.access) return
      ws = new WebSocket(wsUrl())
      ws.onopen = () => {
        retry = 0
        setConnected(true)
        refreshCount()   // catch up on anything missed while disconnected
        listeners.current.forEach((fn) => { try { fn({ event: 'reconnected' }) } catch { /* ignore */ } })
        clearInterval(pingTimer)
        pingTimer = setInterval(() => { try { ws.send('ping') } catch { /* closed */ } }, 25000)
      }
      ws.onmessage = (ev) => {
        if (ev.data === 'pong') return
        let msg
        try { msg = JSON.parse(ev.data) } catch { return }
        if (typeof msg.pending_count === 'number') setPendingCount(msg.pending_count)
        listeners.current.forEach((fn) => { try { fn(msg) } catch { /* ignore */ } })
      }
      ws.onclose = async (ev) => {
        setConnected(false)
        clearInterval(pingTimer)
        if (closed) return
        // 4401 = token rejected (the 30-min staff access token expired) — any
        // API call refreshes it through the axios interceptor, then retry
        if (ev.code === 4401) { try { await api.get('/admin/auth/me/') } catch { /* interceptor handles logout */ } }
        const delay = Math.min(30000, 1000 * 2 ** retry)
        retry += 1
        retryTimer = setTimeout(connect, delay)
      }
      ws.onerror = () => { try { ws.close() } catch { /* ignore */ } }
    }
    connect()

    // coming back to the tab: refresh the count, and reconnect right away if the socket died
    const onVisible = () => {
      if (document.visibilityState !== 'visible') return
      refreshCount()
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
  }, [enabled, staff?.id])

  return (
    <Ctx.Provider value={{ pendingCount, connected, subscribe, refreshCount }}>
      {children}
    </Ctx.Provider>
  )
}

export const useLivePayments = () => useContext(Ctx)

/** Run `fn(event)` for every live payments event while the component is mounted. */
export function usePaymentsEvents(fn) {
  const { subscribe } = useLivePayments()
  const ref = useRef(fn)
  ref.current = fn
  useEffect(() => subscribe((e) => ref.current(e)), [subscribe])
}
