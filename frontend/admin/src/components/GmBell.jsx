import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { prefsOf } from './NotifySound'
import { AgencyBell, AgencyNotificationsPage } from './AgencyBell'

// v1.37 group-manager notifications (backend GET/POST /agency/manager/notices/). Since v1.38.2 the bell and the page are
// the shared components/AgencyBell.jsx (also used by the /agency/ reseller portal).
const NURL = '/agency/manager/notices/'
const http = { get: (u, cfg) => api.get(u, cfg), post: (u, body) => api.post(u, body, { quiet: true }) }

export function GmBell() {
  const { lang } = useI18n()
  const { staff } = useAuth()
  const sound = () => { const p = prefsOf(staff); return { on: !!p.sound, volume: p.volume } }
  return <AgencyBell http={http} url={NURL} allTo="/my-groups/notifications" lang={lang} sound={sound} />
}

/** /my-groups/notifications — every notice, 20 per page. */
export function GmNotificationsPage() {
  const { lang } = useI18n()
  return <AgencyNotificationsPage http={http} url={NURL} lang={lang} />
}
