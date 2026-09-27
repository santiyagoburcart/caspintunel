// Liquid Glass runtime (identical in both SPAs) — picks the glass tier and
// drives the scroll states the CSS in styles/liquid.css reacts to.
//
//   html[data-glass]  full | lite | solid
//     solid — prefers-reduced-transparency or prefers-contrast: more
//     lite  — no blur: low-end device (≤ 4 GB RAM or ≤ 4 cores), Save-Data,
//             no backdrop-filter support, or slow frames measured on this
//             device (the verdict is remembered)
//     full  — everything else
//   html.lg-scrolled  page scrolled past the top (scroll-edge effect on bars)
//   html.lg-min       scrolling down → floating tab bars shrink; any scroll up,
//                     or reaching the top/bottom, expands them again
//
// Manual override for testing/support: ?glass=full|lite|solid (remembered),
// ?glass=auto clears it.

const KEY = 'ct_glass'          // manual override
const PERF_KEY = 'ct_glass_perf' // "slow" once this device dropped frames

const store = {
  get(k) { try { return localStorage.getItem(k) } catch { return null } },
  set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v) } catch { /* private mode */ } },
}
const mq = (q) => typeof window.matchMedia === 'function' && window.matchMedia(q)

function supportsBlur() {
  const css = window.CSS
  return !!css?.supports && (css.supports('backdrop-filter', 'blur(1px)') || css.supports('-webkit-backdrop-filter', 'blur(1px)'))
}

function lowEnd() {
  const nav = navigator
  const mem = nav.deviceMemory            // Chrome/Android only; bucketed, max 8
  const cores = nav.hardwareConcurrency
  return (mem && mem <= 4) || (cores && cores <= 4) || nav.connection?.saveData === true
}

export function glassTier() {
  const forced = store.get(KEY)
  if (forced === 'full' || forced === 'lite' || forced === 'solid') return forced
  if (mq('(prefers-reduced-transparency: reduce)')?.matches || mq('(prefers-contrast: more)')?.matches) return 'solid'
  if (!supportsBlur() || lowEnd() || store.get(PERF_KEY) === 'slow') return 'lite'
  return 'full'
}

function apply() {
  document.documentElement.setAttribute('data-glass', glassTier())
}

/** Watch real frame times while the user scrolls; if this device can't keep
 *  ~45 fps with blur on, switch to lite for good (8-core phones like the
 *  Galaxy Note 10 report 8 GB and pass the static checks above). */
function probeFrames() {
  if (document.documentElement.getAttribute('data-glass') !== 'full' || store.get(KEY)) return
  let frames = 0, slow = 0, last = 0, active = false, idle, samples = 0
  const tick = (t) => {
    if (!active) return
    if (last) { frames++; if (t - last > 34) slow++ }  // > 34 ms = missed at least one 60 Hz frame twice
    last = t
    requestAnimationFrame(tick)
  }
  const onScroll = () => {
    clearTimeout(idle)
    if (!active) { active = true; last = 0; requestAnimationFrame(tick) }
    idle = setTimeout(() => {
      active = false
      samples++
      if (frames >= 30 && slow / frames > 0.25) {
        store.set(PERF_KEY, 'slow')
        apply()
        window.removeEventListener('scroll', onScroll)
      } else if (samples >= 6) {
        window.removeEventListener('scroll', onScroll)   // this device is fine
      }
      frames = 0; slow = 0
    }, 180)
  }
  window.addEventListener('scroll', onScroll, { passive: true })
}

function trackScroll() {
  const root = document.documentElement
  let lastY = window.scrollY, ticking = false
  const update = () => {
    ticking = false
    const y = window.scrollY
    const max = root.scrollHeight - window.innerHeight
    root.classList.toggle('lg-scrolled', y > 4)
    if (y < 80 || y >= max - 8) root.classList.remove('lg-min')        // top / bottom → expanded
    else if (y > lastY + 6) root.classList.add('lg-min')               // scrolling down → minimized
    else if (y < lastY - 6) root.classList.remove('lg-min')            // any scroll up → expanded
    if (Math.abs(y - lastY) > 6) lastY = y
  }
  window.addEventListener('scroll', () => {
    if (!ticking) { ticking = true; requestAnimationFrame(update) }
  }, { passive: true })
  update()
}

export function initGlass() {
  try {
    const q = new URLSearchParams(location.search).get('glass')
    if (q === 'auto') store.set(KEY, null)
    else if (q === 'full' || q === 'lite' || q === 'solid') store.set(KEY, q)
  } catch { /* ignore */ }
  apply()
  // follow OS setting changes live
  for (const q of ['(prefers-reduced-transparency: reduce)', '(prefers-contrast: more)']) {
    const m = mq(q)
    m?.addEventListener?.('change', apply)
  }
  trackScroll()
  probeFrames()
}
