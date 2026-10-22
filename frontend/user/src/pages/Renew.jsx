import { useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import { Spinner } from '../components/ui'

/** One-click renew (/renew/<service>, from warning messages): straight to the renewal
 *  checkout of that service, or to the store when its plan can't be renewed. */
export default function Renew() {
  const { id } = useParams()
  const go = useNavigate()
  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get('code')
    api.get(`/services/${id}/renew-info/`)
      .then(({ data }) => go(data.can_renew && data.plan
        ? `/checkout?plan=${data.plan.id}&renew=${id}${code ? `&code=${encodeURIComponent(code)}` : ''}`
        : '/store', { replace: true }))
      .catch(() => go('/', { replace: true }))
  }, [id])
  return <div className="grid place-items-center py-16"><Spinner /></div>
}
