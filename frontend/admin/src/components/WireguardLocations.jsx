import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useConfirm } from './ConfirmDialog'

// v1.55 «مکان‌های وایرگارد» (backend apps/panel/wireguard.py · WireguardLocation): the country name + flag shown to customers
// for each WireGuard location, matched by the code in the PasarGuard host remark («Ita {USERNAME}» → Ita). A code that is not
// here shows as itself. The file name of a location's .conf uses «slug» (e.g. CT-12-germany.conf). Our staff only.
const T = {
  fa: {
    title: 'مکان‌های وایرگارد', sub: 'نام و پرچمی که مشتری برای هر مکان وایرگارد می‌بیند. «کد» همان کد نام هاست در پاسارگارد است (مثلاً Ita در «Ita {USERNAME}»)؛ کدی که اینجا نباشد با همان کد نشان داده می‌شود.',
    code: 'کد', fa: 'نام فارسی', en: 'نام انگلیسی', flag: 'پرچم', slug: 'نام فایل', order: 'ترتیب', active: 'فعال', save: 'ذخیره',
    add: 'افزودن مکان', del: 'حذف', del_t: 'حذف مکان', del_m: 'مکان «{n}» حذف شود؟ فایل‌های آن مکان از این به بعد با کد خام نشان داده می‌شوند.',
  },
  en: {
    title: 'WireGuard locations', sub: 'The name and flag customers see for each WireGuard location. «Code» is the code in the PasarGuard host name (e.g. Ita in “Ita {USERNAME}”); a code not listed here shows as itself.',
    code: 'Code', fa: 'Persian name', en: 'English name', flag: 'Flag', slug: 'File name', order: 'Order', active: 'Active', save: 'Save',
    add: 'Add location', del: 'Delete', del_t: 'Delete location', del_m: 'Delete “{n}”? Its files will show the raw code from now on.',
  },
}
const EMPTY = { code: '', name_fa: '', name_en: '', flag: '', slug: '', sort_order: 0, is_active: true }

export default function WireguardLocations({ canEdit }) {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const confirm = useConfirm()
  const [rows, setRows] = useState(null)
  const [draft, setDraft] = useState(null)
  const load = () => api.get('/admin/wireguard/locations/').then((r) => setRows(Array.isArray(r.data) ? r.data : r.data.results || [])).catch(() => setRows([]))
  useEffect(() => { load() }, [])
  const put = (i, k, v) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, [k]: v, _dirty: true } : r)))
  const save = async (r) => {
    try {
      const body = { code: r.code, name_fa: r.name_fa, name_en: r.name_en, flag: r.flag, slug: r.slug, sort_order: Number(r.sort_order) || 0, is_active: r.is_active }
      if (r.id) await api.patch(`/admin/wireguard/locations/${r.id}/`, body); else await api.post('/admin/wireguard/locations/', body)
      setDraft(null); load()
    } catch { /* the toast shows why */ }
  }
  const del = async (r) => {
    const ok = await confirm({ tone: 'danger', icon: 'trash', title: s.del_t, targetLabel: s.title, targetId: r.code,
      message: s.del_m.replace('{n}', r.name_fa || r.code), confirmLabel: s.del, action: () => api.delete(`/admin/wireguard/locations/${r.id}/`) })
    if (ok) load()
  }
  if (rows === null) return null
  // a render function, not a component: a component declared here would remount (and lose input focus) on every keystroke
  const row = (r, i) => (
    <div className="wl-row" data-testid="wg-loc" key={r.id || 'new'}>
      <span className="wl-flag" aria-hidden="true">{r.flag || '🌐'}</span>
      {[['code', s.code, 'ltr'], ['name_fa', s.fa, 'rtl'], ['name_en', s.en, 'ltr'], ['flag', s.flag, 'ltr'], ['slug', s.slug, 'ltr'], ['sort_order', s.order, 'ltr']].map(([k, label, dir]) => (
        <label key={k} className={'wl-f wl-f--' + k}><span>{label}</span>
          <input className="input" dir={dir} value={r[k] ?? ''} disabled={!canEdit} inputMode={k === 'sort_order' ? 'numeric' : undefined}
            onChange={(e) => (i === -1 ? setDraft({ ...r, [k]: e.target.value }) : put(i, k, e.target.value))} /></label>
      ))}
      <label className="wl-chk"><input type="checkbox" checked={!!r.is_active} disabled={!canEdit}
        onChange={(e) => (i === -1 ? setDraft({ ...r, is_active: e.target.checked }) : put(i, 'is_active', e.target.checked))} />{s.active}</label>
      {canEdit && (
        <div className="wl-act">
          <button type="button" className="btn-primary text-sm" disabled={i !== -1 && !r._dirty} onClick={() => save(r)}>{s.save}</button>
          {r.id && <button type="button" className="btn-ghost text-sm" onClick={() => del(r)}>{s.del}</button>}
        </div>
      )}
    </div>
  )
  return (
    <section className="card wl" data-testid="wg-locations">
      <style>{CSS}</style>
      <h2 className="font-bold">{s.title}</h2>
      <p className="text-xs text-muted">{s.sub}</p>
      <div className="wl-list">
        {rows.map((r, i) => row(r, i))}
        {draft && row(draft, -1)}
      </div>
      {canEdit && !draft && <button type="button" className="btn-ghost text-sm" onClick={() => setDraft({ ...EMPTY })}>+ {s.add}</button>}
    </section>
  )
}

const CSS = `
.wl { display: flex; flex-direction: column; gap: 10px; }
.wl-list { display: flex; flex-direction: column; gap: 8px; }
.wl-row { display: grid; grid-template-columns: 34px repeat(auto-fit, minmax(min(100%, 110px), 1fr)); gap: 8px; align-items: end;
  padding: 10px; border: 1px solid var(--c-border); border-radius: 12px; min-width: 0; }
.wl-flag { font-size: 24px; align-self: center; }
.wl-f { display: flex; flex-direction: column; gap: 3px; font-size: 11.5px; font-weight: 700; min-width: 0; }
.wl-chk { display: flex; align-items: center; gap: 6px; font-size: 13px; min-height: 40px; }
.wl-act { display: flex; gap: 6px; flex-wrap: wrap; }
@media (max-width: 767px) { .wl-row { grid-template-columns: 1fr 1fr; } .wl-flag { grid-column: 1 / -1; } .wl-f .input { font-size: 16px; min-height: 44px; } }
`
