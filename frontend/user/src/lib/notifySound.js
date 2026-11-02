// v1.33: a short chime for new notifications — synthesized with WebAudio (no audio file, no CDN).
// Browsers start audio only after a user gesture: the first tap / key anywhere unlocks it; until
// then `soundState().blocked` lets the page show a small "enable sound" prompt.
// (identical file in both SPAs)
let ctx = null
let lastAt = 0
let blocked = false
const subs = new Set()
const emit = () => subs.forEach((fn) => { try { fn(soundState()) } catch { /* ignore */ } })

function audio() {
  if (ctx) return ctx
  const C = typeof window !== 'undefined' && (window.AudioContext || window.webkitAudioContext)
  if (!C) return null
  try { ctx = new C() } catch { ctx = null }
  return ctx
}

export function soundState() {
  return { supported: !!(typeof window !== 'undefined' && (window.AudioContext || window.webkitAudioContext)),
    unlocked: !!ctx && ctx.state === 'running', blocked }
}

export function onSoundState(fn) { subs.add(fn); return () => subs.delete(fn) }

export function unlockSound() {
  const c = audio()
  if (!c) return Promise.resolve(false)
  return c.resume().then(() => { if (c.state === 'running') blocked = false; emit(); return c.state === 'running' })
    .catch(() => false)
}

const TONES = { default: [880, 1320], alert: [740, 520], success: [660, 990] }

/** volume 0–100; kind default | alert | success. Bursts within 1.5 s ring once. */
export function playChime(volume = 60, kind = 'default') {
  const c = audio()
  if (!c || c.state !== 'running') { blocked = true; emit(); return false }
  const now = Date.now()
  if (now - lastAt < 1500) return true
  lastAt = now
  const peak = Math.max(0.0002, Math.min(1, Number(volume) / 100)) * 0.4
  ;(TONES[kind] || TONES.default).forEach((f, i) => {
    const t0 = c.currentTime + i * 0.14
    const osc = c.createOscillator()
    const g = c.createGain()
    osc.type = 'sine'
    osc.frequency.setValueAtTime(f, t0)
    g.gain.setValueAtTime(0.0001, t0)
    g.gain.exponentialRampToValueAtTime(peak, t0 + 0.02)
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.28)
    osc.connect(g).connect(c.destination)
    osc.start(t0)
    osc.stop(t0 + 0.3)
  })
  return true
}

if (typeof window !== 'undefined') {
  const first = () => {
    unlockSound().then((ok) => {
      if (ok) ['pointerdown', 'keydown', 'touchend'].forEach((e) => window.removeEventListener(e, first))
    })
  }
  ;['pointerdown', 'keydown', 'touchend'].forEach((e) => window.addEventListener(e, first, { passive: true }))
}
