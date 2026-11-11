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
    code: 'کد', fa: 'نام فارسی', en: 'نام انگلیسی', flag: 'پرچم', slug: 'نام فایل (نام تونل)', order: 'ترتیب', active: 'فعال', save: 'ذخیره',
    in_app: 'در برنامهٔ WireGuard:', tpl: 'الگوی نام فایل (برای همهٔ مکان‌ها)', tpl_hint: 'پیش‌فرض {location} = همان نام فایل هر مکان. {service} = شمارهٔ سرویس (اختیاری). نتیجه باید حداکثر ۱۵ نویسه باشد.',
    bad_len: 'حداکثر ۱۵ نویسه — الان {n} نویسه است', bad_chr: 'فقط حروف انگلیسی، رقم و _ = + . - (بدون فاصله)', empty: 'نام فایل را وارد کنید', no_loc: 'الگو باید {location} داشته باشد',
    tpl_save: 'ذخیرهٔ الگو',
    add: 'افزودن مکان', del: 'حذف', del_t: 'حذف مکان', del_m: 'مکان «{n}» حذف شود؟ فایل‌های آن مکان از این به بعد با کد خام نشان داده می‌شوند.',
  },
  en: {
    title: 'WireGuard locations', sub: 'The name and flag customers see for each WireGuard location. «Code» is the code in the PasarGuard host name (e.g. Ita in “Ita {USERNAME}”); a code not listed here shows as itself.',
    code: 'Code', fa: 'Persian name', en: 'English name', flag: 'Flag', slug: 'File name (tunnel name)', order: 'Order', active: 'Active', save: 'Save',
    in_app: 'In the WireGuard app:', tpl: 'File name template (all locations)', tpl_hint: 'Default {location} = each location’s file name. {service} = the service number (optional). The result must be at most 15 characters.',
    bad_len: 'At most 15 characters — now {n}', bad_chr: 'Only English letters, digits and _ = + . - (no spaces)', empty: 'Enter a file name', no_loc: 'The template needs {location}',
    tpl_save: 'Save template',
    add: 'Add location', del: 'Delete', del_t: 'Delete location', del_m: 'Delete “{n}”? Its files will show the raw code from now on.',
  },
}
// WireGuard tunnel names (the .conf name without ".conf" is the tunnel name in the app): ≤ 15 of A-Z a-z 0-9 _ = + . -
const strip = (v) => String(v || '').trim().replace(/\.conf$/i, '')
export function tunnelProblem(name, s) {
  if (!name) return s.empty
  if (!/^[A-Za-z0-9_=+.\-]*$/.test(name)) return s.bad_chr
  if (name.length > 15) return s.bad_len.replace('{n}', name.length)
  return ''
}
const render = (tpl, loc, sid) => (tpl || '{location}').split('{location}').join(loc).split('{service}').join(String(sid))
const EMPTY = { code: '', name_fa: '', name_en: '', flag: '', slug: '', sort_order: 0, is_active: true }

export default function WireguardLocations({ canEdit }) {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const confirm = useConfirm()
  const [rows, setRows] = useState(null)
  const [draft, setDraft] = useState(null)
  const [tpl, setTpl] = useState(null)              // { template, sample_service, saved }
  useEffect(() => { api.get('/admin/wireguard/template/').then((r) => setTpl({ ...r.data, saved: r.data.template })).catch(() => setTpl(null)) }, [])
  const sid = tpl?.sample_service || 12
  const tplNow = tpl?.template || '{location}'
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
      {[['code', s.code, 'ltr'], ['name_fa', s.fa, 'rtl'], ['name_en', s.en, 'ltr'], ['flag', s.flag, 'ltr'], ['sort_order', s.order, 'ltr']].map(([k, label, dir]) => (
        <label key={k} className={'wl-f wl-f--' + k}><span>{label}</span>
          <input className="input" dir={dir} value={r[k] ?? ''} disabled={!canEdit} inputMode={k === 'sort_order' ? 'numeric' : undefined}
            onChange={(e) => (i === -1 ? setDraft({ ...r, [k]: e.target.value }) : put(i, k, e.target.value))} /></label>
      ))}
      {(() => {
        const name = strip(r.slug)
        const shown = render(tplNow, name || r.code, sid)
        const why = tunnelProblem(name, s) || tunnelProblem(shown, s)
        return (
          <label className="wl-f wl-f--slug"><span>{s.slug}</span>
            <input className="input" dir="ltr" value={r.slug ?? ''} disabled={!canEdit} aria-invalid={!!why} data-testid="wg-slug"
              onChange={(e) => (i === -1 ? setDraft({ ...r, slug: e.target.value }) : put(i, 'slug', e.target.value))} />
            {why ? <small className="wl-bad" role="alert" data-testid="wg-slug-warn">{why}</small>
              : <small className="wl-ok">{s.in_app} <bdi dir="ltr" className="wl-tun" data-testid="wg-slug-preview">{shown}</bdi></small>}
          </label>
        )
      })()}
      <label className="wl-chk"><input type="checkbox" checked={!!r.is_active} disabled={!canEdit}
        onChange={(e) => (i === -1 ? setDraft({ ...r, is_active: e.target.checked }) : put(i, 'is_active', e.target.checked))} />{s.active}</label>
      {canEdit && (
        <div className="wl-act">
          <button type="button" className="btn-primary text-sm" disabled={(i !== -1 && !r._dirty) || !!(tunnelProblem(strip(r.slug), s) || tunnelProblem(render(tplNow, strip(r.slug), sid), s))} onClick={() => save(r)}>{s.save}</button>
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
      {tpl && (() => {
        const t = (tpl.template || '').trim()
        const noLoc = t && !t.includes('{location}')
        const names = rows.filter((r) => r.is_active).map((r) => [r.code, render(t || '{location}', strip(r.slug) || r.code, sid)])
        const bad = noLoc ? s.no_loc : (names.map(([, n]) => tunnelProblem(n, s)).find(Boolean) || '')
        return (
          <div className="wl-tpl" data-testid="wg-template">
            <label className="wl-f"><span>{s.tpl}</span>
              <input className="input" dir="ltr" value={tpl.template} disabled={!canEdit} onChange={(e) => setTpl({ ...tpl, template: e.target.value })} data-testid="wg-template-input" /></label>
            <small className="text-xs text-muted">{s.tpl_hint}</small>
            {bad ? <small className="wl-bad" role="alert" data-testid="wg-template-warn">{bad}</small> : (
              <div className="wl-prev">{names.map(([c, n]) => <span key={c} className="wl-tun" dir="ltr">{n}</span>)}</div>
            )}
            {canEdit && tpl.template !== tpl.saved && (
              <button type="button" className="btn-primary text-sm" disabled={!!bad} onClick={async () => {
                try { const r = await api.put('/admin/wireguard/template/', { template: tpl.template }); setTpl({ ...r.data, saved: r.data.template }) } catch { /* toast */ }
              }}>{s.tpl_save}</button>
            )}
          </div>
        )
      })()}
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
.wl-bad { color: var(--c-danger-fg, #b91c1c); font-size: 11.5px; font-weight: 700; line-height: 1.6; }
.wl-ok { color: var(--c-text-muted); font-size: 11.5px; }
.wl-tun { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 12px; font-weight: 700; color: var(--c-text);
  padding: 1px 6px; border-radius: 6px; background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); }
.wl-tpl { display: flex; flex-direction: column; gap: 6px; padding: 10px; border: 1px dashed var(--c-border); border-radius: 12px; max-width: 520px; }
.wl-prev { display: flex; flex-wrap: wrap; gap: 6px; }
.wl-f--slug { grid-column: span 2; }
@media (max-width: 767px) { .wl-row { grid-template-columns: 1fr 1fr; } .wl-flag { grid-column: 1 / -1; } .wl-f .input { font-size: 16px; min-height: 44px; } }
`
