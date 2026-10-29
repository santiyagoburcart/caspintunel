import { useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import { Spinner } from '../components/ui'

/** One-click renew (/renew/<service>, from warning messages): straight to the renewal
 *  checkout of that service — with its plan, or the plan list when it has none. */
export default function Renew() {
  const { id } = useParams()
  const go = useNavigate()
  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get('code')
    api.get(`/services/${id}/renew-info/`)
      .then(({ data }) => {
        const c = code ? `&code=${encodeURIComponent(code)}` : ''
        // always the same account: own plan pre-selected, else the plan list (never a new purchase)
        go(data.plan ? `/checkout?plan=${data.plan.id}&renew=${id}${c}` : `/checkout?renew=${id}${c}`, { replace: true })
      })
      .catch(() => go('/', { replace: true }))
  }, [id])
  return <div className="grid place-items-center py-16"><Spinner /></div>
}
