import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { Ic } from './AgencyIcons'

// v1.60 «پوسته» on «فروشگاه» (our staff only). Stores never change themes: by default a store follows the theme active on
// our platform; here our staff may pin one of OUR themes for this store (backend settings_app/themes.py).
const T = {
  fa: { title: 'پوسته', follow: 'پیروی از پوستهٔ فعال پلتفرم', now: 'الان: {n}', save: 'ذخیره',
    hint: 'فروشگاه خودش پوسته را تغییر نمی‌دهد. پیش‌فرض: هر وقت پوستهٔ پلتفرم را عوض کنید، این فروشگاه هم عوض می‌شود.' },
  en: { title: 'Theme', follow: 'Follow the platform’s active theme', now: 'now: {n}', save: 'Save',
    hint: 'A store can’t change its theme. Default: whenever you switch the platform theme, this store follows.' },
}

export default function StoreTheme({ base, manage }) {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const [row, setRow] = useState(null)
  const [pick, setPick] = useState('')
  useEffect(() => {
    api.get(`${base}theme/`).then((r) => { setRow(r.data); setPick(r.data.override ? String(r.data.override) : '') }).catch(() => setRow(null))
  }, [base])
  if (!row) return null
  const dirty = pick !== (row.override ? String(row.override) : '')
  const save = async () => {
    try {
      const { data } = await api.put(`${base}theme/`, { theme: pick ? Number(pick) : null })
      setRow(data); setPick(data.override ? String(data.override) : '')
    } catch { /* the toast shows why */ }
  }
  return (
    <div className="stt" data-testid="store-theme">
      <style>{CSS}</style>
      <div className="text-sm font-semibold">{s.title}</div>
      <p className="text-xs text-muted">{s.hint}</p>
      <div className="stt-row">
        <select className="input stt-sel" value={pick} disabled={!manage} onChange={(e) => setPick(e.target.value)} aria-label={s.title}>
          <option value="">{s.follow}{row.platform ? ` (${s.now.replace('{n}', row.platform.name)})` : ''}</option>
          {row.options.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select>
        {manage && <button type="button" className="btn-primary text-sm stt-btn" disabled={!dirty} onClick={save}><Ic n="check" />{s.save}</button>}
      </div>
    </div>
  )
}

const CSS = `
.stt { display: flex; flex-direction: column; gap: 6px; }
.stt-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.stt-sel { flex: 1 1 220px; min-width: 0; min-height: 44px; }
.stt-btn { min-height: 44px; display: inline-flex; align-items: center; gap: 6px; }
@media (max-width: 767px) { .stt-sel { font-size: 16px; } .stt-btn { flex: 1 1 100%; justify-content: center; } }
`
