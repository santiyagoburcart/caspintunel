import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { api, tokens } from './api'
import { useAuth } from './auth'
import { useI18n } from './i18n'
import { useToast } from '../components/Toast'

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
  const toast = useToast()
  const { lang } = useI18n()
  const notify = useRef(null)
  notify.current = (msg) => {
    const fa = lang === 'fa'
    // the Blu collector went silent / came back (backend payments_sms/blu.py)
    if (msg.event === 'blu_collector') {
      if (msg.connected) toast.success(fa ? 'جمع‌کنندهٔ واریزهای بلو دوباره وصل شد' : 'Blu deposit collector is back online')
      else toast.error(fa ? `از جمع‌کنندهٔ واریزهای بلو ${msg.minutes} دقیقه است خبری نیست — تأیید خودکار بلو متوقف است`
        : `Blu deposit collector silent for ${msg.minutes} min — Blu auto-confirm is paused`)
      return
    }
    // the collector's systemd service on the Iran server (backend blu_service.py)
    if (msg.event === 'blu_service') {
      if (msg.ok) toast.success(fa ? 'سرویس جمع‌کنندهٔ بلو دوباره سالم است' : 'Blu collector service is healthy again')
      else toast.error(fa ? `مشکل جمع‌کنندهٔ بلو: ${({ inactive: 'سرویس غیرفعال', ssh: 'SSH ناموفق', poll: 'خواندن حساب ناموفق', session: 'نشست بلو منقضی شده — دوباره وارد شوید' })[msg.kind] || msg.kind}`
        : `Blu collector problem: ${({ inactive: 'service inactive', ssh: 'SSH failing', poll: 'polling failing', session: 'Blu session expired — sign in again' })[msg.kind] || msg.kind}`)
      return
    }
    // v1.34 agency payments + admin requests (backend apps/agency/billing.py) — never the customer queue
    if (msg.event && msg.event.startsWith('agency_')) {
      const T = {
        agency_request: ['درخواست شارژ تازه از ادمین نمایندگی — نمایندگی ← تأییدها', 'New volume request from an agency admin — Agency → Approvals', 'success'],
        agency_receipt: ['رسید واریز نماینده رسید — نمایندگی ← واریزهای نمایندگان', 'Agency payment receipt — Agency → Agency payments', 'success'],
        agency_approved: ['واریز نماینده تأیید شد', 'Agency payment approved', 'success'],
        agency_mismatch: ['مبلغ نامطابق در واریز نماینده — بررسی کنید', 'Agency payment amount mismatch — review it', 'error'],
        agency_pending_alert: [`واریز نماینده ${msg.number || ''} ${msg.minutes || ''} دقیقه است بررسی نشده`, `Agency payment ${msg.number || ''} waiting ${msg.minutes || ''} min`, 'error'],
      }[msg.event]
      if (T && !(msg.event === 'agency_approved' && msg.source === 'manual')) toast[T[2]](fa ? T[0] : T[1])
      return
    }
    // v1.33 a payment pending longer than the setting (backend payments_sms/pending_alert.py)
    if (msg.event === 'payment_pending_alert') {
      toast.error(fa ? `پرداخت ${msg.tx} (سفارش #${msg.order_id}) ${msg.minutes} دقیقه است تأیید نشده — در صف پرداخت بررسی کنید.`
        : `Payment ${msg.tx} (order #${msg.order_id}) unconfirmed for ${msg.minutes} min — check the payment queue.`)
      return
    }
    // v1.32 rounded-amount auto-approve (backend payments_sms/rounded.py)
    if (msg.event === 'rounded_approved') {
      const n = (v) => Number(v || 0).toLocaleString('en-US')
      toast.success(fa
        ? `تأیید خودکار – مبلغ گرد شده: سفارش #${msg.order_id} — واریز ${n(msg.paid)}، فاکتور ${n(msg.invoice_amount)} تومان (کسری ${n(msg.shortfall)}).`
        : `Auto-approved — rounded amount: order #${msg.order_id} — paid ${n(msg.paid)} T, invoice ${n(msg.invoice_amount)} T (short ${n(msg.shortfall)}).`)
      return
    }
    // a deposit (bank SMS or Blu) close to an open invoice but not equal: never approved, needs a person
    if (msg.event !== 'sms_mismatch' && msg.event !== 'blu_mismatch') return
    const blu = msg.event === 'blu_mismatch'
    const n = (v) => Number(v || 0).toLocaleString('en-US')
    const what = msg.kind === 'more' ? (fa ? 'بیشتر از فاکتور' : 'MORE than the invoice') : (fa ? 'کمتر از فاکتور' : 'LESS than the invoice')
    const src = blu ? (fa ? 'واریز بلو' : 'Blu deposit') : (fa ? 'پیامک' : 'SMS')
    toast.error(fa
      ? `مبلغ نامطابق در ${src} (${what}) — سفارش #${msg.order_id}: ${src} ${n(msg.sms_amount)} تومان، فاکتور ${n(msg.invoice_amount)} تومان. در صف پرداخت بررسی کنید.`
      : `${src} amount mismatch (${what}) — order #${msg.order_id}: ${src} ${n(msg.sms_amount)} T, invoice ${n(msg.invoice_amount)} T. Review it in the payment queue.`)
  }

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
        try { notify.current?.(msg) } catch { /* ignore */ }
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
