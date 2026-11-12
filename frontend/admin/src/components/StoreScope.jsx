import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { getStoreScope, setStoreScope } from '../lib/storeScope'

// v1.59 «فروشگاه» filter on OUR panel's CRM / analytics pages: our store (default) or one reseller store. Hidden on a store's
// own panel (it only ever sees itself) and when there is no store yet.
export default function StoreScope({ lang }) {
  const { staff } = useAuth()
  const [stores, setStores] = useState(null)
  const cur = getStoreScope()
  useEffect(() => { if (!staff?.store) api.get('/admin/crm/stores/').then((r) => setStores(r.data || [])).catch(() => setStores([])) }, [])
  if (staff?.store || !stores || stores.length === 0) return null
  const fa = lang !== 'en'
  const name = stores.find((t) => String(t.id) === cur)?.name
  return (
    <div className="ss" data-testid="store-scope">
      <style>{CSS}</style>
      <label className="ss-l"><span>{fa ? 'فروشگاه' : 'Store'}</span>
        <select className="input" value={cur} onChange={(e) => { setStoreScope(e.target.value); window.location.reload() }} data-testid="store-scope-select">
          <option value="">{fa ? 'فروشگاه ما' : 'Our store'}</option>
          {stores.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
      </label>
      {cur && name && <span className="ss-on" data-testid="store-scope-on">{fa ? `نمایش داده‌های «${name}»` : `Showing “${name}”`}</span>}
    </div>
  )
}
const CSS = `
.ss { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; }
.ss-l { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 700; color: var(--c-muted-fg); }
.ss-l .input { width: auto; min-width: 180px; min-height: 40px; }
.ss-on { font-size: 12.5px; font-weight: 800; padding: 4px 12px; border-radius: 999px; color: var(--c-warning-fg);
  background: color-mix(in srgb, var(--c-warning) 15%, transparent); border: 1px solid color-mix(in srgb, var(--c-warning) 35%, transparent); }
@media (max-width: 767px) { .ss-l, .ss-l .input { width: 100%; } .ss-l .input { font-size: 16px; min-height: 44px; } }
`
