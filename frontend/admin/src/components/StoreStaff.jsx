import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali, digits } from '../lib/format'
import { copyToClipboard } from '../lib/clipboard'
import { ADMIN_BASE } from '../lib/base'
import { useConfirm } from './ConfirmDialog'
import { useToast } from './Toast'
import { Ic } from './AgencyIcons'

// v1.52 (multi-tenant Phase 8) on «فروشگاه» — our staff only (backend apps/tenancy/staff.py): the store owner's login (created /
// password reset here, shown ONCE) and the permission ceiling — what the store's staff may ever hold and grant.
const T = {
  fa: {
    owner: 'ورود مالک فروشگاه', none: 'هنوز ورودی برای نماینده ساخته نشده.', username: 'نام کاربری مالک', create: 'ساخت ورود مالک',
    reset: 'رمز جدید', active: 'فعال', inactive: 'غیرفعال', last: 'آخرین ورود', never: 'هنوز نه', staff_n: '{n} کارمند در این فروشگاه',
    where: 'ورود نماینده در', no_domain: 'پس از فعال شدن دامنهٔ فروشگاه',
    pwd: 'رمز عبور (فقط همین یک بار نمایش داده می‌شود — کپی کنید و به نماینده بدهید)', copy: 'کپی', copied: 'کپی شد',
    c_title: 'ساخت ورود مالک فروشگاه', c_msg: 'یک حساب پنل برای این فروشگاه ساخته می‌شود؛ فقط روی دامنهٔ خود فروشگاه کار می‌کند و دسترسی‌اش برابر سقف زیر است.',
    c_btn: 'بله، بساز', r_title: 'رمز جدید برای مالک فروشگاه', r_msg: 'رمز فعلی و همهٔ نشست‌های باز مالک باطل می‌شود.', r_btn: 'بله، رمز جدید',
    ceil: 'سقف دسترسی فروشگاه', ceil_hint: 'نماینده و کارمندانش فقط همین‌ها را می‌توانند داشته باشند یا به نقش‌ها بدهند. دسترسی‌های پلتفرم (نمایندگی، حسابداری ما، دامنه، ربات‌ها…) هرگز اینجا نیستند.',
    save: 'ذخیرهٔ سقف', s_title: 'تغییر سقف دسترسی', s_msg: 'دسترسی‌های برداشته‌شده همین حالا از همهٔ نقش‌های این فروشگاه حذف می‌شوند.', s_btn: 'بله، ذخیره کن',
    all: 'همه', clear: 'هیچ‌کدام',
  },
  en: {
    owner: 'Store owner login', none: 'No login for the reseller yet.', username: 'Owner username', create: 'Create owner login',
    reset: 'New password', active: 'active', inactive: 'disabled', last: 'last login', never: 'never', staff_n: '{n} staff in this store',
    where: 'The reseller signs in at', no_domain: 'once the store domain is active',
    pwd: 'Password (shown only this once — copy it and give it to the reseller)', copy: 'Copy', copied: 'Copied',
    c_title: 'Create the store owner login', c_msg: 'A panel account for this store is created; it works only on the store’s own domain and holds exactly the ceiling below.',
    c_btn: 'Yes, create it', r_title: 'New password for the store owner', r_msg: 'The current password and every open session of the owner end.', r_btn: 'Yes, new password',
    ceil: 'Store permission ceiling', ceil_hint: 'The reseller and their staff can only hold or grant these. Platform permissions (agency, our accounting, domains, bots…) are never here.',
    save: 'Save ceiling', s_title: 'Change the permission ceiling', s_msg: 'Permissions taken away are removed from every role of this store right now.', s_btn: 'Yes, save it',
    all: 'All', clear: 'None',
  },
}

export default function StoreStaff({ base, store, manage, onChanged }) {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const confirm = useConfirm()
  const toast = useToast()
  const [username, setUsername] = useState('')
  const [secret, setSecret] = useState(null)          // {owner, password} — this answer only
  const [codes, setCodes] = useState(store.ceiling || [])
  const [labels, setLabels] = useState({})
  useEffect(() => { setCodes(store.ceiling || []) }, [store.ceiling?.join(',')])
  useEffect(() => {
    api.get('/admin/permissions/?limit=200').then((r) => {
      const rows = r.data.results || r.data || []
      setLabels(Object.fromEntries(rows.map((p) => [p.code, lang === 'fa' ? (p.name_fa || p.name) : p.name])))
    }).catch(() => setLabels({}))
  }, [lang])

  const host = (store.domains || []).find((d) => d.state === 'active')?.host
  const loginUrl = host ? `https://${host}${ADMIN_BASE}/` : null
  const owner = store.owner

  const ownerAction = async (create) => {
    let res = null
    const ok = await confirm({ tone: create ? 'primary' : 'warning', icon: 'lock', title: create ? s.c_title : s.r_title,
      targetLabel: s.owner, targetId: create ? username.trim() : owner.username, message: create ? s.c_msg : s.r_msg,
      confirmLabel: create ? s.c_btn : s.r_btn,
      action: async () => { res = (await api.post(base + 'owner/', create ? { username: username.trim() } : {})).data } })
    if (ok && res) { setSecret({ owner: res.owner, password: res.password }); setUsername(''); onChanged() }
  }
  const saveCeiling = async () => {
    const ok = await confirm({ tone: 'warning', icon: 'shield', title: s.s_title, targetLabel: s.ceil, targetId: store.name,
      message: s.s_msg, confirmLabel: s.s_btn, action: () => api.put(base + 'ceiling/', { codes }) })
    if (ok) onChanged()
  }
  const toggle = (c) => setCodes(codes.includes(c) ? codes.filter((x) => x !== c) : [...codes, c].sort())
  const dirty = codes.join(',') !== (store.ceiling || []).join(',')

  return (
    <section className="ss" data-testid="store-staff">
      <style>{CSS}</style>
      <div className="ss-sub"><Ic n="key" size={14} />{s.owner}</div>
      {owner ? (
        <div className="ss-card">
          <div className="ss-head">
            <bdi dir="ltr" className="ss-name">{owner.username}</bdi>
            <span className="ss-pill" data-ok={owner.is_active ? '1' : '0'}>{owner.is_active ? s.active : s.inactive}</span>
            <span className="text-xs text-muted">{s.last}: {owner.last_login ? jalali(owner.last_login, true, lang) : s.never}</span>
            <span className="text-xs text-muted">{s.staff_n.replace('{n}', digits(owner.staff_count, lang))}</span>
          </div>
          {manage && <button type="button" className="ag-act" data-tone="warning" onClick={() => ownerAction(false)}><Ic n="key" />{s.reset}</button>}
        </div>
      ) : (
        <>
          <p className="text-sm text-muted">{s.none}</p>
          {manage && (
            <form className="ss-form" onSubmit={(e) => { e.preventDefault(); if (username.trim()) ownerAction(true) }}>
              <label className="ss-f"><span>{s.username}</span>
                <input className="input" dir="ltr" autoCapitalize="none" autoCorrect="off" spellCheck={false} value={username}
                  onChange={(e) => setUsername(e.target.value)} /></label>
              <button className="btn-primary text-sm ss-btn" disabled={username.trim().length < 3}>{s.create}</button>
            </form>
          )}
        </>
      )}
      {secret && (
        <div className="ss-secret" role="status" data-testid="owner-password">
          <span className="text-xs">{s.pwd}</span>
          <div className="ss-secret-row">
            <code dir="ltr">{secret.owner} · {secret.password}</code>
            <button type="button" className="ag-act" onClick={async () => { await copyToClipboard(secret.password); toast.success(s.copied) }}>
              <Ic n="copy" />{s.copy}</button>
          </div>
        </div>
      )}
      <p className="text-xs text-muted">{s.where}: {loginUrl ? <bdi dir="ltr"><a href={loginUrl} target="_blank" rel="noreferrer">{loginUrl}</a></bdi> : s.no_domain}</p>

      <div className="ss-sub"><Ic n="shield" size={14} />{s.ceil}</div>
      <p className="text-xs text-muted">{s.ceil_hint}</p>
      <div className="ss-codes" role="group" aria-label={s.ceil}>
        {(store.store_codes || []).map((c) => (
          <label key={c} className="ss-code">
            <input type="checkbox" checked={codes.includes(c)} disabled={!manage} onChange={() => toggle(c)} />
            <span>{labels[c] || c}</span><bdi dir="ltr" className="ss-code-k">{c}</bdi>
          </label>
        ))}
      </div>
      {manage && (
        <div className="ss-acts">
          <button type="button" className="ag-act" onClick={() => setCodes([...(store.store_codes || [])])}>{s.all}</button>
          <button type="button" className="ag-act" onClick={() => setCodes([])}>{s.clear}</button>
          <button type="button" className="btn-primary text-sm ss-btn" disabled={!dirty} onClick={saveCeiling}>{s.save}</button>
        </div>
      )}
    </section>
  )
}

const CSS = `
.ss { display: flex; flex-direction: column; gap: 8px; border-top: 1px solid var(--c-border); padding-top: 12px; min-width: 0; }
.ss-sub { display: flex; align-items: center; gap: 6px; font-weight: 800; font-size: 13.5px; margin-top: 4px; }
.ss-card { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; padding: 12px; border-radius: 14px;
  border: 1px solid var(--c-border); background: var(--c-bg); min-width: 0; }
.ss-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; min-width: 0; }
.ss-name { font-weight: 800; font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 13.5px; overflow-wrap: anywhere; }
.ss-pill { font-size: 12px; font-weight: 800; padding: 2px 10px; border-radius: 999px; color: var(--c-success-fg);
  background: color-mix(in srgb, var(--c-success) 16%, transparent); }
.ss-pill[data-ok="0"] { color: var(--c-muted-fg); background: color-mix(in srgb, var(--c-text-muted) 16%, transparent); }
.ss-form { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr)); gap: 8px; align-items: end; }
.ss-f { display: flex; flex-direction: column; gap: 4px; font-size: 12px; font-weight: 700; min-width: 0; }
.ss-btn { min-height: 44px; }
.ss-secret { display: flex; flex-direction: column; gap: 6px; padding: 10px 12px; border-radius: 12px;
  border: 1px solid color-mix(in srgb, var(--c-warning) 45%, transparent); background: color-mix(in srgb, var(--c-warning) 10%, var(--c-bg)); }
.ss-secret-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; min-width: 0; }
.ss-secret code { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 13px; overflow-wrap: anywhere; }
.ss-codes { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 230px), 1fr)); gap: 6px; }
.ss-code { display: flex; align-items: center; gap: 8px; min-height: 44px; padding: 4px 10px; border-radius: 10px; border: 1px solid var(--c-border);
  font-size: 12.5px; min-width: 0; }
.ss-code span { flex: 1; min-width: 0; }
.ss-code-k { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 11px; color: var(--c-text-muted); }
.ss-acts { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.ss-acts .ag-act { min-height: 44px; }
`
