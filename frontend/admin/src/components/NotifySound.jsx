import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { api, apiError } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { ADMIN_BASE } from '../lib/base'
import { useToast } from './Toast'
import { Toggle } from './ui'
import { usePaymentsEvents } from '../lib/livePayments'
import { useLiveTickets } from '../lib/liveTickets'
import { useLiveApprovals } from '../lib/liveApprovals'
import { onSoundState, playChime, soundState, unlockSound } from '../lib/notifySound'
import { currentSubscription, needsHomeScreen, pushSupported, subscribePush, unsubscribePush } from '../lib/webPush'

// v1.33: a short sound for new things that need a person (payments queue, approvals,
// tickets, alerts), per staff member (Staff.notify_prefs: sound on/off + volume), plus the
// optional browser push for this browser.
const T = {
  fa: {
    btn: 'صدا و اعلان', h: 'صدا و اعلان‌ها', sound: 'صدای اعلان‌های تازه', sound_d: 'صف پرداخت، تأییدها، تیکت‌ها و هشدارها',
    volume: 'بلندی صدا', test: 'پخش آزمایشی', enable: 'فعال‌سازی صدا', enable_q: 'صدای اعلان‌ها فعال شود؟',
    push: 'اعلان مرورگر (وقتی پنل بسته است)', push_d: 'فقط برای همین مرورگر', push_off_srv: 'اعلان مرورگر روی سرور پیکربندی نشده است.',
    push_unsupported: 'این مرورگر از اعلان‌های Push پشتیبانی نمی‌کند.', push_test: 'ارسال اعلان آزمایشی',
    ios: 'در آیفون / آیپد اعلان مرورگر فقط وقتی کار می‌کند که سایت به صفحهٔ اصلی اضافه شده باشد: در Safari دکمهٔ «اشتراک‌گذاری» ← «Add to Home Screen»، سپس پنل را از آیکون صفحهٔ اصلی باز کنید و این گزینه را روشن کنید (iOS 16.4 به بالا).',
    denied: 'اجازهٔ اعلان در مرورگر رد شده است — از تنظیمات سایت در مرورگر آن را باز کنید.', close: 'بستن',
    on: 'روشن', off: 'خاموش',
  },
  en: {
    btn: 'Sound & notifications', h: 'Sound & notifications', sound: 'Sound for new notifications', sound_d: 'payments queue, approvals, tickets and alerts',
    volume: 'Volume', test: 'Play test', enable: 'Enable sound', enable_q: 'Turn on notification sound?',
    push: 'Browser notifications (while the panel is closed)', push_d: 'this browser only', push_off_srv: 'Browser push is not configured on the server.',
    push_unsupported: 'This browser does not support push notifications.', push_test: 'Send a test notification',
    ios: 'On iPhone / iPad browser notifications only work for a site added to the Home Screen: in Safari tap Share → “Add to Home Screen”, open the panel from that icon, then turn this on (iOS 16.4+).',
    denied: 'Notifications are blocked for this site — allow them in the browser’s site settings.', close: 'Close',
    on: 'on', off: 'off',
  },
}
const BASE = `${ADMIN_BASE.replace(/\/$/, '')}/`
const PAY_EVENTS = { receipt_uploaded: 'default', sms_mismatch: 'alert', blu_mismatch: 'alert', payment_pending_alert: 'alert',
  rounded_approved: 'success',
  // v1.34 agency payments / requests
  agency_request: 'default', agency_receipt: 'default', agency_approved: 'success', agency_mismatch: 'alert', agency_pending_alert: 'alert' }
const TICKET_EVENTS = new Set(['new_ticket', 'user_reply', 'assigned'])

export const prefsOf = (staff) => ({ sound: true, volume: 60, ...(staff?.notify_prefs || {}) })

function useSoundState() {
  const [st, setSt] = useState(soundState)
  useEffect(() => onSoundState(setSt), [])
  return st
}

/** Mounted once (main.jsx): rings on live events and shows the "enable sound" prompt. */
export function NotifySound() {
  const { staff } = useAuth()
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const p = prefsOf(staff)
  const ref = useRef(p)
  ref.current = p
  const st = useSoundState()
  const ring = (kind) => { if (ref.current.sound) playChime(ref.current.volume, kind) }

  usePaymentsEvents((e) => {
    if (PAY_EVENTS[e.event]) ring(PAY_EVENTS[e.event])
    else if (e.event === 'blu_collector' && !e.connected) ring('alert')
    else if (e.event === 'blu_service' && !e.ok) ring('alert')
  })
  const { subscribe } = useLiveTickets()
  useEffect(() => subscribe((m) => { if (TICKET_EVENTS.has(m.event)) ring('default') }), [subscribe])
  const { pending } = useLiveApprovals()
  const last = useRef(null)
  useEffect(() => {
    if (last.current !== null && pending > last.current) ring('default')
    last.current = pending
  }, [pending])

  if (!staff || !p.sound || !st.supported || st.unlocked) return null
  return (
    <button type="button" className="ns-chip" onClick={() => unlockSound()} data-testid="enable-sound">
      <SpeakerIcon on /> <span>{st.blocked ? s.enable_q : s.enable}</span>
      <style>{CSS}</style>
    </button>
  )
}

export function SpeakerIcon({ on = true, w = 18 }) {
  return (
    <svg viewBox="0 0 24 24" width={w} height={w} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M11 5L6 9H2v6h4l5 4V5z" />
      {on ? <path d="M15.5 8.5a5 5 0 010 7M19 5a10 10 0 010 14" /> : <path d="M23 9l-6 6M17 9l6 6" />}
    </svg>
  )
}

/** Header button → the sound / push panel. */
export function SoundButton({ className = '' }) {
  const { staff } = useAuth()
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const [open, setOpen] = useState(false)
  const p = prefsOf(staff)
  return (
    <>
      <button type="button" className={className} onClick={() => setOpen(true)} aria-label={s.btn} title={s.btn}
        data-testid="sound-btn" data-on={p.sound || undefined}>
        <SpeakerIcon on={p.sound} />
      </button>
      {open && <SoundPanel onClose={() => setOpen(false)} />}
    </>
  )
}

export function SoundPanel({ onClose }) {
  const { staff, refreshMe } = useAuth()
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const toast = useToast()
  const [p, setP] = useState(prefsOf(staff))
  const [push, setPush] = useState(null)       // {enabled, public_key}
  const [sub, setSub] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.get('/admin/push/').then((r) => setPush(r.data)).catch(() => setPush({ enabled: false }))
    currentSubscription(BASE).then((x) => setSub(!!x)).catch(() => {})
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  const save = async (next, quiet = true) => {
    setP(next)
    try { await api.patch('/admin/auth/me/prefs/', next, { quiet }); refreshMe() } catch (e) { toast.error(apiError(e)) }
  }
  const test = async () => { await unlockSound(); playChime(p.volume, 'default') }
  const togglePush = async (on) => {
    setBusy(true)
    try {
      if (on) {
        const json = await subscribePush(BASE, push.public_key)
        await api.post('/admin/push/subscribe/', { subscription: json })
        setSub(true)
      } else {
        const endpoint = await unsubscribePush(BASE)
        if (endpoint) await api.post('/admin/push/unsubscribe/', { endpoint })
        setSub(false)
      }
    } catch (e) {
      toast.error(e?.message === 'denied' ? s.denied : e?.message === 'unsupported' ? s.push_unsupported : apiError(e))
    } finally { setBusy(false) }
  }

  return createPortal(
    <div className="ns-back" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <style>{CSS}</style>
      <div className="ns-panel card" role="dialog" aria-modal="true" aria-label={s.h} data-testid="sound-panel">
        <div className="ns-head">
          <b>{s.h}</b>
          <button type="button" className="ns-x" onClick={onClose} aria-label={s.close}>✕</button>
        </div>
        <div className="ns-row">
          <span className="min-w-0"><span className="block text-sm font-semibold">{s.sound}</span><span className="block text-xs text-muted">{s.sound_d}</span></span>
          <Toggle checked={p.sound} onChange={(v) => save({ ...p, sound: v }, false)} label={s.sound} />
        </div>
        <label className="ns-vol">
          <span className="text-xs font-semibold">{s.volume} <bdi dir="ltr" className="mono-num">{p.volume}%</bdi></span>
          <input type="range" min="0" max="100" step="5" value={p.volume} disabled={!p.sound}
            onChange={(e) => setP({ ...p, volume: Number(e.target.value) })}
            onPointerUp={() => save(p)} onKeyUp={() => save(p)} onTouchEnd={() => save(p)} aria-label={s.volume} />
        </label>
        <button type="button" className="btn-ghost text-sm ns-btn" onClick={test} disabled={!p.sound}>▶ {s.test}</button>

        <div className="ns-sep" />
        {push === null ? null : !push.enabled ? <p className="text-xs text-muted">{s.push_off_srv}</p>
          : !pushSupported() ? <p className="text-xs text-muted">{needsHomeScreen() ? s.ios : s.push_unsupported}</p> : (
            <>
              <div className="ns-row">
                <span className="min-w-0"><span className="block text-sm font-semibold">{s.push}</span><span className="block text-xs text-muted">{s.push_d}</span></span>
                <Toggle checked={sub} onChange={busy ? () => {} : togglePush} label={s.push} />
              </div>
              {sub && <button type="button" className="btn-ghost text-sm ns-btn" onClick={() => api.post('/admin/push/test/', {})}>{s.push_test}</button>}
            </>
          )}
        {needsHomeScreen() && push?.enabled && pushSupported() && <p className="ns-ios">{s.ios}</p>}
      </div>
    </div>,
    document.body,
  )
}

const CSS = `
.ns-chip { position: fixed; z-index: 60; inset-inline-start: 14px; bottom: calc(14px + env(safe-area-inset-bottom, 0px));
  display: inline-flex; align-items: center; gap: 8px; min-height: 44px; padding: 0 14px; border-radius: 999px;
  font-size: 13px; font-weight: 700; color: #fff; background: var(--c-primary); box-shadow: 0 6px 20px rgba(0,0,0,.25); border: 0; }
@media (max-width: 767px) { .ns-chip { bottom: calc(80px + env(safe-area-inset-bottom, 0px)); } }
.ns-back { position: fixed; inset: 0; z-index: 70; background: rgba(0,0,0,.35); display: flex; justify-content: flex-end; align-items: flex-start; padding: 64px 16px 16px; }
.ns-back .ns-panel { width: min(360px, 100%); display: flex; flex-direction: column; gap: 12px; padding: 16px; border-radius: 16px;
  background: var(--c-bg) !important; -webkit-backdrop-filter: none; backdrop-filter: none; box-shadow: 0 18px 50px rgba(0,0,0,.3); }
.ns-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.ns-x { width: 44px; height: 44px; display: grid; place-items: center; border-radius: 10px; color: var(--c-text-muted); background: transparent; border: 0; }
.ns-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.ns-vol { display: flex; flex-direction: column; gap: 6px; }
.ns-vol input { width: 100%; min-height: 32px; accent-color: var(--c-primary); }
.ns-btn { align-self: flex-start; min-height: 40px; }
.ns-sep { border-top: 1px solid var(--c-border); }
.ns-ios { font-size: 12px; line-height: 1.8; color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 10%, transparent); border-radius: 10px; padding: 8px 10px; }
@media (max-width: 767px) {
  .ns-back { align-items: flex-end; padding: 0; }
  .ns-back .ns-panel { width: 100%; border-radius: 18px 18px 0 0; padding-bottom: calc(16px + env(safe-area-inset-bottom, 0px)); }
  .ns-btn { min-height: 44px; }
}
`
