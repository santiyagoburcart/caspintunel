import { useLivePayments } from './livePayments'
import { useLiveTickets } from './liveTickets'
import { useLiveApprovals } from './liveApprovals'

// v1.33: one place for "needs action" COUNTS (never dots) — the desktop sidebar, the phone bottom
// tabs, the rows of the Settings index and the sub-tabs inside pages all read from here.
// Transactions mirrors the payments queue (the pending ones are transactions too).
export function useActionCounts() {
  const { pendingCount } = useLivePayments()
  const { badge } = useLiveTickets()
  const { pending } = useLiveApprovals()
  const pay = pendingCount || 0
  return { '/payments': pay, '/transactions': pay, '/tickets': badge || 0, '/agency': pending || 0 }
}

export const fmtCount = (n) => (n > 99 ? '99+' : String(n))
