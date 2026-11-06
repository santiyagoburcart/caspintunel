import { useLivePayments } from './livePayments'
import { useLiveTickets } from './liveTickets'
import { useLiveApprovals } from './liveApprovals'

// v1.33: one place for "needs action" COUNTS (never dots) — the desktop sidebar, the phone bottom
// tabs, the rows of the Settings index and the sub-tabs inside pages all read from here.
// Transactions mirrors the payments queue (the pending ones are transactions too).
export function useActionCounts() {
  const { pendingCount, failedCount } = useLivePayments()
  const { badge } = useLiveTickets()
  const { pending, agencyReview } = useLiveApprovals()
  const pay = pendingCount || 0
  // v1.34: Agency = approvals + agency payments waiting for review (kept apart from customer payments)
  // v1.42.1: Transactions also counts paid orders PasarGuard refused («ساخت ناموفق»)
  return { '/payments': pay, '/transactions': pay + (failedCount || 0), '/tickets': badge || 0, '/agency': (pending || 0) + (agencyReview || 0),
    '/agency/ledger': agencyReview || 0 }
}

export const fmtCount = (n) => (n > 99 ? '99+' : String(n))
