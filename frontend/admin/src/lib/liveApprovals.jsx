import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { api } from './api'
import { useAuth } from './auth'
import { useI18n } from './i18n'
import { useToast } from '../components/Toast'

/**
 * Agency → Approvals: volume given by group managers that waits for staff
 * (backend: apps/agency/managers.py). Polled every 30 s and when the tab comes
 * back; the count is the badge on the Agency menu entry, and a rise shows an
 * in-site notification (toast).
 */
const Ctx = createContext({ pending: 0, refresh: () => {} })

export function LiveApprovalsProvider({ children }) {
  const { staff, can } = useAuth()
  const enabled = !!staff && can('agency.view')
  const [pending, setPending] = useState(0)
  const last = useRef(null)
  const toast = useToast()
  const { lang } = useI18n()
  const langRef = useRef(lang)
  langRef.current = lang

  const refresh = useCallback(() => {
    api.get('/admin/agency/approvals/badge/').then((r) => {
      const n = r.data.pending || 0
      if (last.current !== null && n > last.current) {
        toast.success(langRef.current === 'fa'
          ? `درخواست حجم تازه از مدیر گروه — ${n} مورد در انتظار تأیید (نمایندگی ← تأییدها)`
          : `New volume from a group manager — ${n} waiting for approval (Agency → Approvals)`)
      }
      last.current = n
      setPending(n)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!enabled) { setPending(0); last.current = null; return undefined }
    refresh()
    const t = setInterval(() => { if (document.visibilityState === 'visible') refresh() }, 30000)
    const onVisible = () => { if (document.visibilityState === 'visible') refresh() }
    document.addEventListener('visibilitychange', onVisible)
    return () => { clearInterval(t); document.removeEventListener('visibilitychange', onVisible) }
  }, [enabled])

  return <Ctx.Provider value={{ pending, refresh }}>{children}</Ctx.Provider>
}

export const useLiveApprovals = () => useContext(Ctx)
