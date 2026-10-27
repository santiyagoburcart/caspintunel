import { useEffect, useMemo, useState } from 'react'
import { Link, NavLink, useParams } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useAuth } from '../lib/auth'
import { jalali, toman, digits } from '../lib/format'
import { Alert, Spinner, Toggle } from '../components/ui'
import { copyToClipboard } from '../lib/clipboard'
import { useConfirm } from '../components/ConfirmDialog'
import { useToast } from '../components/Toast'
import { DateRangeModal, DRP_CSS } from '../components/DateRangePicker'
import { Ic } from '../components/AgencyIcons'
import { useLiveApprovals } from '../lib/liveApprovals'

// Agency → group managers, approvals, group statements and group activity
// (backend: apps/agency/managers.py, adminpanel/views/agency_managers.py).
// Rules live on the server; this file only lays them out.

const T = {
  fa: {
    m_title: 'مدیران گروه', m_intro: 'هر مدیر گروه با نام کاربری و رمز خودش در پرتال (آدرس زیر) وارد می‌شود و فقط ادمین‌های گروه‌های خودش را می‌بیند: ساخت ادمین، افزودن حجم (فقط افزایش)، تغییر رمز و اینباند (از فهرست مجاز). هر حجمی که می‌دهد بلافاصله روی PasarGuard اعمال و در «تأییدها» منتظر شما می‌ماند.',
    m_new: 'مدیر گروه جدید', m_edit: 'ویرایش مدیر', m_none: 'هنوز مدیر گروهی ساخته نشده است.', m_portal: 'آدرس ورود مدیران',
    username: 'نام کاربری', password: 'رمز عبور', gen: 'رمز تصادفی', display: 'نام نمایشی', active: 'فعال', disabled: 'غیرفعال',
    cap: 'سقف حجم تأییدنشده (گیگ)', cap_hint: 'خالی = بدون سقف. با رسیدن به سقف، حجم تازه تا تأیید شما بسته می‌شود.', no_cap: 'بدون سقف',
    groups: 'گروه‌ها و اینباندهای مجاز', groups_hint: 'اینباندها در PasarGuard از «نقش» ادمین می‌آیند؛ نقش‌های مالک (sudo) هیچ‌وقت مجاز نیستند.',
    roles_err: 'نقش‌ها از PasarGuard خوانده نشد', inbounds: 'اینباندها', all_inb: 'همه', note: 'یادداشت',
    pending: 'در انتظار', of: 'از', last_login: 'آخرین ورود', never: 'هرگز', save: 'ذخیره', create: 'ساخت',
    reset_pw: 'رمز تازه', reset_msg: 'یک رمز تصادفی ساخته می‌شود و همهٔ نشست‌های این مدیر بسته می‌شود.', disable: 'غیرفعال‌کردن', enable: 'فعال‌کردن',
    disable_msg: 'مدیر دیگر نمی‌تواند وارد شود و نشست‌هایش بسته می‌شود.', saved: 'ذخیره شد', created: 'مدیر گروه ساخته شد',
    cred_title: 'اطلاعات ورود مدیر گروه', cred_note: 'رمز فقط همین یک بار نمایش داده می‌شود.', copy: 'کپی', copied: 'کپی شد', close: 'بستن',
    pick_group: 'حداقل یک گروه انتخاب کنید.', need_role: 'برای هر گروه حداقل یک اینباند مجاز انتخاب کنید.',
    a_title: 'تأییدها', a_intro: 'حجمی که مدیران گروه داده‌اند؛ روی PasarGuard اعمال شده است. تأیید ← شارژ در حسابداری (با منطق آخرین سقف). رد ← همین حجم از PasarGuard برداشته می‌شود و شارژی ثبت نمی‌شود.',
    st_pending: 'در انتظار', st_approved: 'تأییدشده', st_rejected: 'ردشده', st_all: 'همه',
    k_create: 'ادمین جدید', k_add: 'افزودن حجم', group: 'گروه', manager: 'مدیر', admin: 'ادمین', gb: 'حجم', price: 'قیمت هر گیگ', amount: 'مبلغ',
    date: 'تاریخ', approve: 'تأیید', reject: 'رد', approve_sel: 'تأیید انتخاب‌شده‌ها', sel_all: 'انتخاب همه', none_pending: 'موردی در انتظار نیست.',
    no_price: 'قیمت ندارد', price_in: 'قیمت هر گیگ (تومان) برای این ادمین', price_need: 'این ادمین برای آن تاریخ قیمت ندارد — قیمت را وارد کنید (از همان تاریخ ثبت می‌شود).',
    approve_msg: 'شارژ در حسابداری ثبت می‌شود و در تاریخچهٔ سقف به این تغییر وصل می‌شود.', approved: 'تأیید شد', rejected: 'رد شد — حجم برگشت داده شد',
    reject_msg: 'همین حجم از سقف فعلی این ادمین روی PasarGuard کم می‌شود (هرگز نامحدود نمی‌شود). شارژی ثبت نمی‌شود.', reason: 'دلیل (اختیاری)',
    limit_change: 'سقف', bulk_done: '{n} مورد تأیید شد', bulk_failed: '{n} مورد تأیید نشد: ', decided: 'تصمیم', total: 'جمع',
    lg_admin: 'بر اساس ادمین', lg_group: 'بر اساس گروه', g_debt: 'بدهی کل گروه', g_pending: 'تأییدنشده', g_statement: 'صورت‌حساب گروه', admins: 'ادمین‌ها', managers: 'مدیران',
    opening: 'مانده از قبل', charges: 'جمع شارژ', payments: 'جمع پرداخت', closing: 'مانده پایان بازه', balance: 'مانده', kind: 'نوع', note_c: 'توضیح',
    range: 'بازهٔ تاریخ', all_time: 'همهٔ زمان‌ها', csv: 'CSV', xlsx: 'Excel', print: 'چاپ', pending_items: 'در انتظار تأیید (در مانده حساب نشده)', no_entries: 'گردشی در این بازه نیست.',
    k_quota_charge: 'شارژ حجم', k_manual_charge: 'بدهکاری', k_adjustment: 'اصلاحیه', k_payment: 'پرداخت', voided: 'باطل‌شده', back: 'همهٔ گروه‌ها',
    act_title: 'فعالیت', act_none: 'فعالیتی ثبت نشده است.', act_show: 'نمایش فعالیت', act_hide: 'بستن',
    acts: { admin_created: 'ساخت ادمین', volume_added: 'افزودن حجم', password_changed: 'تغییر رمز ادمین', inbounds_changed: 'تغییر اینباند', login: 'ورود', approved: 'تأیید حجم', rejected: 'رد حجم' },
  },
  en: {
    m_title: 'Group managers', m_intro: "Each group manager signs in to the portal (address below) with their own username and password and sees only their groups' admins: create admins, add volume (increase only), change password and inbounds (allowed list). Every volume they give is live on PasarGuard at once and waits for you in Approvals.",
    m_new: 'New group manager', m_edit: 'Edit manager', m_none: 'No group managers yet.', m_portal: 'Managers sign in at',
    username: 'Username', password: 'Password', gen: 'Random', display: 'Display name', active: 'Active', disabled: 'Disabled',
    cap: 'Max unapproved volume (GB)', cap_hint: 'Empty = no cap. When reached, new volume is blocked until you approve.', no_cap: 'no cap',
    groups: 'Groups and allowed inbounds', groups_hint: "In PasarGuard an admin's inbounds come from its role; owner (sudo) roles are never allowed.",
    roles_err: 'Could not read the roles from PasarGuard', inbounds: 'Inbounds', all_inb: 'all', note: 'Note',
    pending: 'pending', of: 'of', last_login: 'Last sign-in', never: 'never', save: 'Save', create: 'Create',
    reset_pw: 'New password', reset_msg: "A random password is made and all of this manager's sessions end.", disable: 'Disable', enable: 'Enable',
    disable_msg: 'The manager can no longer sign in; open sessions end.', saved: 'Saved', created: 'Group manager created',
    cred_title: 'Group manager sign-in', cred_note: 'The password is shown only this once.', copy: 'Copy', copied: 'Copied', close: 'Close',
    pick_group: 'Pick at least one group.', need_role: 'Pick at least one allowed inbound set for each group.',
    a_title: 'Approvals', a_intro: 'Volume given by group managers — already live on PasarGuard. Approve → charge in accounting (last-limit logic). Reject → that volume is taken back on PasarGuard, no charge.',
    st_pending: 'Pending', st_approved: 'Approved', st_rejected: 'Rejected', st_all: 'All',
    k_create: 'New admin', k_add: 'Added volume', group: 'Group', manager: 'Manager', admin: 'Admin', gb: 'Volume', price: 'Price / GB', amount: 'Amount',
    date: 'Date', approve: 'Approve', reject: 'Reject', approve_sel: 'Approve selected', sel_all: 'Select all', none_pending: 'Nothing is waiting.',
    no_price: 'no price', price_in: 'Price per GB (Toman) for this admin', price_need: 'This admin has no price for that date — enter one (saved from that date on).',
    approve_msg: 'The charge is written to accounting and linked to this change in the limit history.', approved: 'Approved', rejected: 'Rejected — the volume was taken back',
    reject_msg: "This volume is taken off the admin's current PasarGuard limit (never made unlimited). No charge.", reason: 'Reason (optional)',
    limit_change: 'Limit', bulk_done: '{n} approved', bulk_failed: '{n} not approved: ', decided: 'Decision', total: 'Total',
    lg_admin: 'By admin', lg_group: 'By group', g_debt: 'Group total debt', g_pending: 'Unapproved', g_statement: 'Group statement', admins: 'Admins', managers: 'Managers',
    opening: 'Opening balance', charges: 'Charges', payments: 'Payments', closing: 'Closing balance', balance: 'Balance', kind: 'Type', note_c: 'Note',
    range: 'Date range', all_time: 'All time', csv: 'CSV', xlsx: 'Excel', print: 'Print', pending_items: 'Pending approval (not in the balance)', no_entries: 'No entries in this range.',
    k_quota_charge: 'Quota charge', k_manual_charge: 'Charge', k_adjustment: 'Adjustment', k_payment: 'Payment', voided: 'voided', back: 'All groups',
    act_title: 'Activity', act_none: 'No activity yet.', act_show: 'Show activity', act_hide: 'Hide',
    acts: { admin_created: 'Admin created', volume_added: 'Volume added', password_changed: 'Admin password changed', inbounds_changed: 'Inbounds changed', login: 'Signed in', approved: 'Volume approved', rejected: 'Volume rejected' },
  },
}
const useS = () => { const { lang } = useI18n(); return [T[lang] || T.fa, lang] }
const N = ({ children }) => <bdi dir="ltr" className="ag-num">{children}</bdi>
const gbText = (v) => `${Number(v || 0).toLocaleString('en-US', { maximumFractionDigits: 2 })} GB`
const limText = (b) => (Number(b) > 0 ? gbText(Number(b) / 1024 ** 3) : '∞')
const money = (v, lang) => (Number(v) < 0 ? '−' : '') + toman(Math.abs(Number(v || 0)), lang)

async function download(url, params, fallbackName) {
  const r = await api.get(url, { params, responseType: 'blob' })
  const name = (r.headers['content-disposition'] || '').match(/filename="([^"]+)"/)?.[1] || fallbackName
  const a = document.createElement('a')
  a.href = URL.createObjectURL(r.data); a.download = name
  document.body.appendChild(a); a.click(); a.remove()
  setTimeout(() => URL.revokeObjectURL(a.href), 2000)
}

function useGet(url, deps = []) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const load = () => { if (!url) return; api.get(url).then((r) => { setD(r.data); setErr('') }).catch((e) => { setErr(apiError(e)); setD((x) => x || false) }) }
  useEffect(() => { load() }, [url, ...deps])
  return [d, err, load]
}

// ------------------------------------------------------------------ managers
function RoleChips({ roles, s }) {
  return (
    <span className="gm-roles">
      {roles.map((r) => (
        <span key={r.id} className="gm-role" title={r.name}>
          <b>{r.all_inbounds ? s.all_inb : (r.inbounds || []).join(' · ') || r.name}</b><small>{r.name}</small>
        </span>
      ))}
    </span>
  )
}

function ManagerForm({ s, init, opts, box }) {
  const [v, setV] = useState(() => ({
    username: init?.username || '', password: '', display_name: init?.display_name || '', note: init?.note || '',
    is_active: init ? init.is_active : true, max_unapproved_gb: init?.max_unapproved_gb ?? '',
    assignments: Object.fromEntries((init?.assignments || []).map((a) => [a.group_id, a.role_ids])),
  }))
  useEffect(() => { Object.assign(box, v) }, [v])
  const gen = () => {
    const abc = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'
    const a = new Uint32Array(14); crypto.getRandomValues(a)
    setV({ ...v, password: Array.from(a, (x) => abc[x % abc.length]).join('') + '7a' })
  }
  const toggleGroup = (gid) => setV((x) => {
    const n = { ...x.assignments }
    if (gid in n) delete n[gid]; else n[gid] = []
    return { ...x, assignments: n }
  })
  const toggleRole = (gid, rid) => setV((x) => {
    const cur = x.assignments[gid] || []
    return { ...x, assignments: { ...x.assignments, [gid]: cur.includes(rid) ? cur.filter((r) => r !== rid) : [...cur, rid] } }
  })
  return (
    <div className="gm-form">
      {!init && <>
        <label><span>{s.username} *</span><input className="input" dir="ltr" autoComplete="off" value={v.username} maxLength={64} onChange={(e) => setV({ ...v, username: e.target.value.trim() })} autoFocus /></label>
        <label className="gm-wide"><span>{s.password} *</span>
          <span className="gm-pw"><input className="input" dir="ltr" autoComplete="new-password" value={v.password} onChange={(e) => setV({ ...v, password: e.target.value })} />
            <button type="button" className="ag-act ag-act--sm" data-tone="neutral" onClick={gen}><Ic n="reset" size={13} />{s.gen}</button></span>
        </label>
      </>}
      <label><span>{s.display}</span><input className="input" value={v.display_name} maxLength={100} onChange={(e) => setV({ ...v, display_name: e.target.value })} /></label>
      <label><span>{s.cap}</span><input className="input" dir="ltr" inputMode="decimal" value={v.max_unapproved_gb ?? ''} placeholder={s.no_cap} onChange={(e) => setV({ ...v, max_unapproved_gb: e.target.value.replace(/[^\d.]/g, '') })} /><small>{s.cap_hint}</small></label>
      {init && <div className="gm-row"><Toggle checked={v.is_active} onChange={(c) => setV({ ...v, is_active: c })} label={s.active} /></div>}
      <div className="gm-wide">
        <span className="gm-l">{s.groups}</span>
        <small className="gm-hint">{s.groups_hint}</small>
        {opts?.roles_error && <Alert>{s.roles_err}: {opts.roles_error}</Alert>}
        <div className="gm-groups">
          {(opts?.groups || []).map((g) => {
            const on = g.id in v.assignments
            return (
              <div key={g.id} className="gm-group" data-on={on || undefined}>
                <label className="gm-gcheck"><input type="checkbox" checked={on} onChange={() => toggleGroup(g.id)} /> <b><bdi>{g.name}</bdi></b> <small>({digits(g.admins, 'en')} {s.admins})</small></label>
                {on && (
                  <div className="gm-rolepick">
                    {(opts?.roles || []).map((r) => (
                      <label key={r.id} className="gm-rolei">
                        <input type="checkbox" checked={(v.assignments[g.id] || []).includes(r.id)} onChange={() => toggleRole(g.id, r.id)} />
                        <span><b>{r.all_inbounds ? s.all_inb : r.inbounds.join(' · ') || '—'}</b><small>{r.name}</small></span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
      <label className="gm-wide"><span>{s.note}</span><input className="input" value={v.note} maxLength={255} onChange={(e) => setV({ ...v, note: e.target.value })} /></label>
    </div>
  )
}

function Credentials({ s, username, password, url }) {
  const toast = useToast()
  const text = `${url}\n${s.username}: ${username}\n${s.password}: ${password}`
  return (
    <div className="gm-cred">
      <dl><div><dt>{s.m_portal}</dt><dd><N>{url}</N></dd></div><div><dt>{s.username}</dt><dd><N>{username}</N></dd></div><div><dt>{s.password}</dt><dd><N>{password}</N></dd></div></dl>
      <p className="text-xs text-muted">{s.cred_note}</p>
      <button type="button" className="ag-act" data-tone="primary" onClick={async () => { await copyToClipboard(text); toast.success(s.copied) }}><Ic n="copy" />{s.copy}</button>
    </div>
  )
}

export function AgencyManagersView({ Header }) {
  const [s, lang] = useS()
  const { can } = useAuth()
  const confirm = useConfirm()
  const toast = useToast()
  const [d, err, load] = useGet('/admin/agency/managers/')
  const [link] = useGet('/admin/agency/portal-link/')
  const manage = can('agency.manage')
  const portal = link ? `${link.url.replace(/\/$/, '')}/manager` : ''

  const options = async () => (await api.get('/admin/agency/managers/options/')).data
  const showCred = (username, password) => confirm({ tone: 'primary', icon: 'check', title: s.cred_title, hideCancel: true, confirmLabel: s.close,
    content: <Credentials s={s} username={username} password={password} url={portal} />, action: async () => {} })

  const edit = async (m) => {
    let opts
    try { opts = await options() } catch (e) { toast.error(apiError(e)); return }
    const box = {}
    let created = null
    const ok = await confirm({
      tone: 'primary', title: m ? s.m_edit : s.m_new, targetLabel: m ? s.username : undefined, targetId: m?.username,
      confirmLabel: m ? s.save : s.create, content: <ManagerForm s={s} init={m} opts={opts} box={box} />,
      action: async () => {
        const groups = Object.entries(box.assignments || {})
        if (!groups.length) throw new Error(s.pick_group)
        if (groups.some(([, r]) => !r.length)) throw new Error(s.need_role)
        const body = { display_name: box.display_name, note: box.note, max_unapproved_gb: box.max_unapproved_gb === '' ? null : box.max_unapproved_gb,
          assignments: groups.map(([gid, role_ids]) => ({ group_id: Number(gid), role_ids })) }
        try {
          if (m) await api.patch(`/admin/agency/managers/${m.id}/`, { ...body, is_active: box.is_active })
          else { await api.post('/admin/agency/managers/', { ...body, username: box.username, password: box.password }); created = [box.username, box.password] }
        } catch (e) { throw new Error(apiError(e)) }
      },
    })
    if (!ok) return
    toast.success(m ? s.saved : s.created); load()
    if (created) showCred(...created)
  }
  const resetPw = async (m) => {
    let pw = null
    const ok = await confirm({ tone: 'warning', title: s.reset_pw, targetLabel: s.username, targetId: m.username, message: s.reset_msg, confirmLabel: s.reset_pw,
      action: async () => { try { pw = (await api.post(`/admin/agency/managers/${m.id}/password/`, {})).data.password } catch (e) { throw new Error(apiError(e)) } } })
    if (ok && pw) { load(); showCred(m.username, pw) }
  }
  const toggleActive = async (m) => {
    const ok = await confirm({ tone: m.is_active ? 'danger' : 'primary', title: m.is_active ? s.disable : s.enable, targetLabel: s.username, targetId: m.username,
      message: m.is_active ? s.disable_msg : undefined, confirmLabel: m.is_active ? s.disable : s.enable,
      action: async () => { try { await api.patch(`/admin/agency/managers/${m.id}/`, { is_active: !m.is_active }) } catch (e) { throw new Error(apiError(e)) } } })
    if (ok) { toast.success(s.saved); load() }
  }

  return (
    <div className="ag space-y-4">
      {Header}
      <style>{GM_CSS}</style>
      <div className="ag-gbar">
        <p className="text-sm text-muted">{s.m_intro}</p>
        {manage && <button type="button" className="ag-act" data-tone="primary" onClick={() => edit(null)}><Ic n="plus" />{s.m_new}</button>}
      </div>
      {portal && <div className="card ag-card gm-portal"><span>{s.m_portal}</span><N>{portal}</N>
        <button type="button" className="ag-act ag-act--sm" data-tone="neutral" onClick={async () => { await copyToClipboard(portal); toast.success(s.copied) }}><Ic n="copy" size={13} />{s.copy}</button></div>}
      <Alert>{err}</Alert>
      {d === null ? <div className="grid place-items-center py-16"><Spinner /></div> : d && (
        d.results.length === 0 ? <div className="card text-sm text-muted">{s.m_none}</div> : d.results.map((m) => (
          <section key={m.id} className="card ag-card gm-card" data-off={!m.is_active || undefined}>
            <div className="ag-card-h">
              <div className="gm-name">
                <h3 className="ag-sh" data-ac="purple"><Ic n="user" size={15} /><bdi>{m.display_name || m.username}</bdi></h3>
                <span className="text-xs text-muted"><N>{m.username}</N></span>
                <span className="gm-pill" data-on={m.is_active || undefined}>{m.is_active ? s.active : s.disabled}</span>
              </div>
              {manage && (
                <div className="ag-actions">
                  <button type="button" className="ag-act" data-tone="neutral" onClick={() => edit(m)}><Ic n="edit" />{s.m_edit}</button>
                  <button type="button" className="ag-act" data-tone="neutral" onClick={() => resetPw(m)}><Ic n="reset" />{s.reset_pw}</button>
                  <button type="button" className="ag-act" data-tone={m.is_active ? 'danger' : 'primary'} onClick={() => toggleActive(m)}><Ic n="power" />{m.is_active ? s.disable : s.enable}</button>
                </div>
              )}
            </div>
            <dl className="gm-facts">
              <div><dt>{s.pending}</dt><dd><N>{gbText(m.cap.pending_gb)}</N> {m.cap.max_gb != null ? <>{s.of} <N>{gbText(m.cap.max_gb)}</N></> : <small>({s.no_cap})</small>} · <N>{digits(m.pending_count, 'en')}</N></dd></div>
              <div><dt>{s.last_login}</dt><dd>{m.last_login_at ? jalali(m.last_login_at, true, lang) : s.never}</dd></div>
            </dl>
            <ul className="gm-assign">
              {m.assignments.map((a) => (
                <li key={a.group_id}><b><bdi>{a.group}</bdi></b><RoleChips roles={a.roles} s={s} /></li>
              ))}
            </ul>
            {m.note && <p className="text-xs text-muted">{s.note}: {m.note}</p>}
          </section>
        ))
      )}
    </div>
  )
}

// ------------------------------------------------------------------ approvals
function PriceInput({ s, box }) {
  const [v, setV] = useState('')
  useEffect(() => { box.price = v }, [v])
  return <label className="gm-price"><span>{s.price_in}</span><input className="input" dir="ltr" inputMode="numeric" value={v} onChange={(e) => setV(e.target.value.replace(/[^\d]/g, ''))} autoFocus /><small>{s.price_need}</small></label>
}
function ReasonInput({ s, box }) {
  const [v, setV] = useState('')
  useEffect(() => { box.reason = v }, [v])
  return <label className="gm-price"><span>{s.reason}</span><input className="input" value={v} maxLength={255} onChange={(e) => setV(e.target.value)} /></label>
}

export function AgencyApprovalsView({ Header }) {
  const [s, lang] = useS()
  const { can } = useAuth()
  const confirm = useConfirm()
  const toast = useToast()
  const { refresh } = useLiveApprovals()
  const [st, setSt] = useState('pending')
  const [d, err, load] = useGet(`/admin/agency/approvals/?status=${st}`)
  const [sel, setSel] = useState([])
  const mayApprove = can('agency.manage') && can('agency.accounting')
  const mayReject = can('agency.manage')
  const reload = () => { load(); refresh(); setSel([]) }
  const rows = d?.results || []
  const pend = rows.filter((r) => r.status === 'pending')
  const selRows = pend.filter((r) => sel.includes(r.id))

  const details = (r) => ({ rows: [[s.group, r.group], [s.manager, r.manager], [s.admin, r.admin], [s.gb, gbText(r.gb)],
    [s.limit_change, `${limText(r.old_limit_bytes)} → ${limText(r.new_limit_bytes)}`],
    [s.amount, r.price_per_gb != null ? `${gbText(r.gb)} × ${toman(r.price_per_gb, lang)} = ${toman(r.amount, lang)}` : s.no_price]] })
  const approve = async (r) => {
    const box = {}
    const ok = await confirm({ tone: 'primary', icon: 'check', title: s.approve, targetLabel: s.admin, targetId: r.admin, message: s.approve_msg, details: details(r),
      content: r.price_per_gb == null ? <PriceInput s={s} box={box} /> : undefined, confirmLabel: s.approve,
      action: async () => { try { await api.post(`/admin/agency/approvals/${r.id}/approve/`, box.price ? { price_per_gb: box.price } : {}) } catch (e) { throw new Error(apiError(e)) } } })
    if (ok) { toast.success(s.approved); reload() }
  }
  const reject = async (r) => {
    const box = {}
    const ok = await confirm({ tone: 'danger', title: s.reject, targetLabel: s.admin, targetId: r.admin, message: s.reject_msg,
      details: { rows: [...details(r).rows.slice(0, 4), [s.limit_change, `${limText(r.new_limit_bytes)} → ${limText(Math.max(1, r.new_limit_bytes - r.gb * 1024 ** 3))}`]] },
      content: <ReasonInput s={s} box={box} />, confirmLabel: s.reject,
      action: async () => { try { await api.post(`/admin/agency/approvals/${r.id}/reject/`, { reason: box.reason || '', confirm: true }) } catch (e) { throw new Error(apiError(e)) } } })
    if (ok) { toast.success(s.rejected); reload() }
  }
  const bulk = async () => {
    const sum = selRows.reduce((a, r) => a + Number(r.amount || 0), 0)
    const gbs = selRows.reduce((a, r) => a + Number(r.gb || 0), 0)
    let res = null
    const ok = await confirm({ tone: 'primary', icon: 'check', title: s.approve_sel, message: s.approve_msg, confirmLabel: s.approve_sel,
      details: { rows: [...selRows.map((r) => [`#${r.id} · ${r.admin}`, `${gbText(r.gb)} · ${r.price_per_gb != null ? toman(r.amount, lang) : s.no_price}`]), [s.total, `${gbText(gbs)} · ${toman(sum, lang)}`]] },
      action: async () => { try { res = (await api.post('/admin/agency/approvals/bulk-approve/', { ids: selRows.map((r) => r.id) })).data } catch (e) { throw new Error(apiError(e)) } } })
    if (!ok || !res) return
    if (res.approved.length) toast.success(s.bulk_done.replace('{n}', res.approved.length))
    if (res.failed.length) toast.error(s.bulk_failed.replace('{n}', res.failed.length) + res.failed.map((f) => `#${f.id}: ${f.detail}`).join(' · '))
    reload()
  }

  return (
    <div className="ag space-y-4">
      {Header}
      <style>{GM_CSS}</style>
      <p className="text-sm text-muted">{s.a_intro}</p>
      <div className="gm-bar">
        <div className="gm-seg" role="tablist">
          {['pending', 'approved', 'rejected', 'all'].map((k) => (
            <button key={k} type="button" role="tab" aria-selected={st === k} className={'gm-segb' + (st === k ? ' on' : '')} onClick={() => { setSt(k); setSel([]) }}>{s['st_' + k]}</button>
          ))}
        </div>
        {st === 'pending' && d && pend.length > 0 && (
          <div className="gm-sum"><span>{s.total}:</span> <N>{gbText(d.pending_gb)}</N> · <N>{toman(d.pending_amount, lang)}</N></div>
        )}
        {mayApprove && pend.length > 0 && (
          <div className="ag-actions">
            <button type="button" className="ag-act" data-tone="neutral" onClick={() => setSel(sel.length === pend.length ? [] : pend.map((r) => r.id))}><Ic n="check" />{s.sel_all}</button>
            <button type="button" className="ag-act" data-tone="primary" disabled={!selRows.length} onClick={bulk}><Ic n="check" />{s.approve_sel} {selRows.length > 0 && <N>({selRows.length})</N>}</button>
          </div>
        )}
      </div>
      <Alert>{err}</Alert>
      {d === null ? <div className="grid place-items-center py-16"><Spinner /></div> : d && (
        rows.length === 0 ? <div className="card text-sm text-muted">{s.none_pending}</div> : (
          <div className="card ag-table-wrap">
            <table className="ag-table gm-table">
              <thead><tr>
                {mayApprove && st !== 'approved' && st !== 'rejected' && <th><span className="sr-only">{s.sel_all}</span></th>}
                <th>{s.date}</th><th>{s.group}</th><th>{s.manager}</th><th>{s.admin}</th><th>{s.gb}</th><th>{s.limit_change}</th><th>{s.amount}</th><th>{s.decided}</th>
              </tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} data-st={r.status}>
                    {mayApprove && st !== 'approved' && st !== 'rejected' && (
                      <td className="gm-chk">{r.status === 'pending' && <input type="checkbox" aria-label={`#${r.id}`} checked={sel.includes(r.id)} onChange={() => setSel(sel.includes(r.id) ? sel.filter((x) => x !== r.id) : [...sel, r.id])} />}</td>
                    )}
                    <td data-label={s.date}>{jalali(r.created_at, false, lang)}<small className="gm-sub">{jalali(r.created_at, true, lang).split(/[،,]\s*/).pop()} · #{r.id}</small></td>
                    <td data-label={s.group}><bdi>{r.group}</bdi></td>
                    <td data-label={s.manager}><N>{r.manager}</N></td>
                    <td data-label={s.admin} className="ag-t-name"><Link to={`/agency/admins/${encodeURIComponent(r.admin)}/history`}>{r.admin}</Link><span className="ag-t-grp">{s['k_' + r.kind]}</span></td>
                    <td data-label={s.gb}><N>+{gbText(r.gb)}</N></td>
                    <td data-label={s.limit_change}><N>{limText(r.old_limit_bytes)} → {limText(r.new_limit_bytes)}</N></td>
                    <td data-label={s.amount}>{r.price_per_gb != null ? <><N>{toman(r.amount, lang)}</N><small className="gm-sub"><N>{gbText(r.gb)} × {toman(r.price_per_gb, lang)}</N></small></> : <span className="gm-warn">{s.no_price}</span>}</td>
                    <td data-label={s.decided}>
                      {r.status === 'pending' ? (
                        <span className="gm-acts">
                          {mayApprove && <button type="button" className="ag-act ag-act--sm" data-tone="primary" onClick={() => approve(r)}><Ic n="check" size={13} />{s.approve}</button>}
                          {mayReject && <button type="button" className="ag-act ag-act--sm" data-tone="danger" onClick={() => reject(r)}><Ic n="x" size={13} />{s.reject}</button>}
                        </span>
                      ) : (
                        <span className="gm-dec" data-st={r.status}>{s['st_' + r.status]} · <N>{r.decided_by}</N><small className="gm-sub">{jalali(r.decided_at, true, lang)}{r.reason && ` · ${r.reason}`}</small></span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  )
}

// ------------------------------------------------------------------ group activity (Groups page)
export function GroupActivity({ groupId }) {
  const [s, lang] = useS()
  const [open, setOpen] = useState(false)
  const [d, err] = useGet(open ? `/admin/agency/groups/${groupId}/activity/` : null, [open])
  return (
    <div className="gm-activity">
      <style>{GM_CSS}</style>
      <button type="button" className="ag-act ag-act--sm" data-tone="neutral" aria-expanded={open} onClick={() => setOpen((v) => !v)}><Ic n="clock" size={13} />{open ? s.act_hide : s.act_show}</button>
      {open && (err ? <Alert>{err}</Alert> : !d ? <Spinner /> : (
        <>
          {d.managers.length > 0 && <p className="text-xs text-muted mt-2">{s.managers}: {d.managers.map((m) => m.username).join('، ')}</p>}
          {d.results.length === 0 ? <p className="text-xs text-muted mt-2">{s.act_none}</p> : (
            <ul className="gm-acts-list">
              {d.results.map((a) => <ActivityRow key={a.id} a={a} s={s} lang={lang} />)}
            </ul>
          )}
        </>
      ))}
    </div>
  )
}

export function ActivityRow({ a, s, lang }) {
  const kind = a.action.split('.').pop()
  const det = a.detail || {}
  const extra = det.gb ? `+${gbText(det.gb)}` : det.inbounds ? det.inbounds.join(' · ') : ''
  return (
    <li>
      <b>{s.acts[kind] || a.action}</b>
      {a.admin && <bdi className="gm-a-admin">{a.admin}</bdi>}
      {extra && <N>{extra}</N>}
      <span className="gm-a-by"><N>{a.by}</N> · {jalali(a.at, true, lang)}</span>
    </li>
  )
}

// ------------------------------------------------------------------ accounting → by group
export function LedgerSubNav() {
  const [s] = useS()
  return (
    <nav className="gm-seg gm-subnav">
      <NavLink end to="/agency/ledger" className={({ isActive }) => 'gm-segb' + (isActive ? ' on' : '')}>{s.lg_admin}</NavLink>
      <NavLink to="/agency/ledger/groups" className={({ isActive }) => 'gm-segb' + (isActive ? ' on' : '')}>{s.lg_group}</NavLink>
    </nav>
  )
}

export function AgencyLedgerGroupsView({ Header }) {
  const [s, lang] = useS()
  const [d, err] = useGet('/admin/agency/ledger/groups/')
  return (
    <div className="ag space-y-4">
      {Header}
      <style>{GM_CSS}</style>
      <LedgerSubNav />
      <Alert>{err}</Alert>
      {d === null ? <div className="grid place-items-center py-16"><Spinner /></div> : d && (
        <div className="card ag-table-wrap">
          <table className="ag-table">
            <thead><tr><th>{s.group}</th><th>{s.admins}</th><th>{s.managers}</th><th>{s.g_debt}</th><th>{s.g_pending}</th><th /></tr></thead>
            <tbody>
              {d.results.map((g) => (
                <tr key={g.id}>
                  <td className="ag-t-name" data-label={s.group}><Link to={`/agency/ledger/groups/${g.id}`}><bdi>{g.name}</bdi></Link></td>
                  <td data-label={s.admins}><N>{digits(g.admins, 'en')}</N></td>
                  <td data-label={s.managers}>{g.managers.join('، ') || '—'}</td>
                  <td data-label={s.g_debt}><span className="gm-bal" data-sign={Number(g.total_debt) > 0 ? 'owes' : 'zero'}><N>{money(g.total_debt, lang)}</N></span></td>
                  <td data-label={s.g_pending}><N>{gbText(g.pending_gb)}</N> · <N>{toman(g.pending_amount, lang)}</N></td>
                  <td><Link className="ag-act ag-act--sm" data-tone="neutral" to={`/agency/ledger/groups/${g.id}`}><Ic n="doc" size={13} />{s.g_statement}</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export function AgencyGroupStatementView({ Header }) {
  const { id } = useParams()
  const [s] = useS()
  return (
    <div className="ag space-y-4">
      {Header}
      <style>{GM_CSS}</style>
      <div className="gm-noprint"><LedgerSubNav /></div>
      <Link to="/agency/ledger/groups" className="text-sm gm-noprint">← {s.back}</Link>
      <GroupStatement url={`/admin/agency/ledger/groups/${id}/statement/`} />
    </div>
  )
}

/** The combined group statement — staff (any group). The manager portal has its own copy of the layout. */
export function GroupStatement({ url }) {
  const [s, lang] = useS()
  const [range, setRange] = useState({ from: '', to: '' })
  const [pick, setPick] = useState(false)
  const toast = useToast()
  const params = useMemo(() => ({ ...(range.from ? { from: range.from } : {}), ...(range.to ? { to: range.to } : {}) }), [range])
  const [st, setSt] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { setSt(null); api.get(url, { params }).then((r) => { setSt(r.data); setErr('') }).catch((e) => { setErr(apiError(e)); setSt(false) }) }, [url, params])
  const exp = (fmt) => download(url, { ...params, export: fmt, lang }, `group-statement.${fmt}`).catch((e) => toast.error(apiError(e)))
  return (
    <section className="card ag-card gm-st">
      <style>{DRP_CSS}</style>
      <div className="ag-card-h">
        <h3 className="ag-sh" data-ac="blue"><Ic n="doc" size={15} />{s.g_statement}{st && <> — <bdi>{st.group.name}</bdi></>}</h3>
        <div className="ag-actions gm-noprint">
          <button type="button" className="ag-act" data-tone="neutral" onClick={() => setPick(true)}><Ic n="clock" />{range.from ? `${jalali(range.from, false, lang)} – ${jalali(range.to || range.from, false, lang)}` : s.all_time}</button>
          <button type="button" className="ag-act" data-tone="neutral" onClick={() => exp('csv')}><Ic n="download" />{s.csv}</button>
          <button type="button" className="ag-act" data-tone="neutral" onClick={() => exp('xlsx')}><Ic n="download" />{s.xlsx}</button>
          <button type="button" className="ag-act" data-tone="neutral" onClick={() => window.print()}><Ic n="doc" />{s.print}</button>
        </div>
      </div>
      <DateRangeModal open={pick} onClose={() => setPick(false)} onApply={setRange} />
      <Alert>{err}</Alert>
      {st === null ? <div className="grid place-items-center py-10"><Spinner /></div> : st && <StatementBody st={st} s={s} lang={lang} />}
    </section>
  )
}

function StatementBody({ st, s, lang }) {
  return (
    <>
      <dl className="gm-facts gm-st-sum">
        {st.from && <div><dt>{s.opening}</dt><dd><N>{money(st.opening, lang)}</N></dd></div>}
        <div><dt>{s.charges}</dt><dd><N>{toman(st.charges, lang)}</N></dd></div>
        <div><dt>{s.payments}</dt><dd><N>{toman(st.payments, lang)}</N></dd></div>
        <div><dt>{s.closing}</dt><dd><N>{money(st.closing, lang)}</N></dd></div>
        <div data-strong><dt>{s.g_debt}</dt><dd><span className="gm-bal" data-sign={Number(st.total_debt) > 0 ? 'owes' : 'zero'}><N>{money(st.total_debt, lang)}</N></span></dd></div>
        <div><dt>{s.g_pending}</dt><dd><N>{gbText(st.pending_gb)}</N> · <N>{toman(st.pending_amount, lang)}</N></dd></div>
      </dl>
      {st.entries.length === 0 ? <p className="text-sm text-muted mt-3">{s.no_entries}</p> : (
        <div className="ag-table-wrap mt-3">
          <table className="ag-table gm-st-table">
            <thead><tr><th>{s.date}</th><th>{s.admin}</th><th>{s.kind}</th><th>{s.gb}</th><th>{s.amount}</th><th>{s.balance}</th><th>{s.note_c}</th></tr></thead>
            <tbody>
              {st.entries.map((e) => (
                <tr key={e.id} data-voided={e.voided || undefined}>
                  <td data-label={s.date}>{jalali(e.date, false, lang)}</td>
                  <td data-label={s.admin}><bdi>{e.admin}</bdi></td>
                  <td data-label={s.kind}><span className="lg-kind" data-kind={e.kind}>{s['k_' + e.kind]}</span></td>
                  <td data-label={s.gb}>{e.gb ? <N>{gbText(e.gb)}</N> : '—'}</td>
                  <td data-label={s.amount}><span className="gm-bal" data-sign={e.voided ? 'zero' : Number(e.signed) < 0 ? 'credit' : 'owes'}><N>{Number(e.signed) < 0 ? '−' : '+'}{toman(Math.abs(Number(e.amount)), lang)}</N></span></td>
                  <td data-label={s.balance}><N>{money(e.balance, lang)}</N></td>
                  <td data-label={s.note_c} className="gm-note">{e.note}{e.voided && ` · ${s.voided}`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {st.pending.length > 0 && (
        <div className="gm-pend mt-3">
          <h4>{s.pending_items}</h4>
          <ul>
            {st.pending.map((p) => (
              <li key={p.id}><span>{jalali(p.date, false, lang)}</span><bdi>{p.admin}</bdi><N>+{gbText(p.gb)}</N><N>{p.price_per_gb != null ? toman(p.amount, lang) : s.no_price}</N><small>#{p.id} · {p.manager}</small></li>
            ))}
          </ul>
        </div>
      )}
    </>
  )
}

const GM_CSS = `
.gm-portal { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; font-size: 13px; }
.gm-portal span { font-weight: 700; color: var(--c-muted-fg); }
.gm-card[data-off] { opacity: .7; }
.gm-name { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; min-width: 0; }
.gm-pill { font-size: 11.5px; font-weight: 700; padding: 2px 9px; border-radius: 999px; color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 12%, transparent); }
.gm-pill[data-on] { color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 14%, transparent); }
.gm-facts { display: grid; gap: 8px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 170px), 1fr)); margin-top: 10px; }
.gm-facts > div { padding: 9px 12px; border-radius: 12px; border: 1px solid var(--c-border); min-width: 0; }
.gm-facts > div[data-strong] { border-color: color-mix(in srgb, var(--c-danger) 35%, var(--c-border)); }
.gm-facts dt { font-size: 11.5px; font-weight: 700; color: var(--c-muted-fg); }
.gm-facts dd { font-size: 14px; font-weight: 800; margin-top: 2px; overflow-wrap: anywhere; }
.gm-facts dd small { font-weight: 600; color: var(--c-muted-fg); }
.gm-assign { display: flex; flex-direction: column; gap: 6px; margin-top: 10px; }
.gm-assign li { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; font-size: 13px; }
.gm-roles { display: inline-flex; flex-wrap: wrap; gap: 6px; }
.gm-role { display: inline-flex; flex-direction: column; padding: 3px 10px; border-radius: 10px; border: 1px solid var(--c-border); font-size: 12px; line-height: 1.4; }
.gm-role small, .gm-rolei small { color: var(--c-muted-fg); font-size: 11px; }
.gm-form { display: grid; gap: 10px; grid-template-columns: 1fr 1fr; text-align: start; }
.gm-form label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; font-weight: 700; min-width: 0; }
.gm-form small, .gm-hint { font-size: 11.5px; font-weight: 500; color: var(--c-muted-fg); }
.gm-wide, .gm-row { grid-column: 1 / -1; }
.gm-l { font-size: 12px; font-weight: 700; }
.gm-pw { display: flex; gap: 6px; align-items: center; }
.gm-pw .input { flex: 1; min-width: 0; }
.gm-groups { display: flex; flex-direction: column; gap: 8px; margin-top: 6px; max-height: 46vh; overflow: auto; }
.gm-group { border: 1px solid var(--c-border); border-radius: 12px; padding: 8px 10px; }
.gm-group[data-on] { border-color: color-mix(in srgb, var(--c-primary) 45%, var(--c-border)); }
.gm-form .gm-gcheck { flex-direction: row; align-items: center; gap: 8px; font-size: 13px; }
.gm-rolepick { display: grid; gap: 6px; grid-template-columns: repeat(auto-fill, minmax(min(100%, 190px), 1fr)); margin-top: 8px; }
.gm-form .gm-rolei { flex-direction: row; align-items: flex-start; gap: 8px; font-weight: 500; padding: 6px 8px; border-radius: 10px; background: color-mix(in srgb, var(--c-text-muted) 7%, transparent); }
.gm-rolei span { display: flex; flex-direction: column; }
.gm-cred dl { display: flex; flex-direction: column; gap: 8px; text-align: start; margin-bottom: 8px; }
.gm-cred dt { font-size: 12px; color: var(--c-muted-fg); font-weight: 700; }
.gm-cred dd { font-size: 14px; font-weight: 800; overflow-wrap: anywhere; }
.gm-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; justify-content: space-between; }
.gm-seg { display: inline-flex; gap: 4px; padding: 3px; border-radius: 12px; border: 1px solid var(--c-border); flex-wrap: wrap; }
.gm-segb { padding: 6px 12px; border-radius: 9px; font-size: 13px; font-weight: 700; color: var(--c-text); text-decoration: none; min-height: 36px; display: inline-flex; align-items: center; }
.gm-segb.on { background: color-mix(in srgb, var(--c-primary) 82%, #000); color: #fff; }
.gm-sum { font-size: 13px; font-weight: 700; }
.gm-table td { vertical-align: top; white-space: normal; }
.gm-table .ag-t-name a { overflow-wrap: anywhere; }
.gm-dec { display: inline-block; min-width: 110px; }
.gm-sub { display: block; font-size: 11px; color: var(--c-muted-fg); margin-top: 2px; }
.gm-warn { font-size: 12px; font-weight: 700; color: var(--c-warning-fg); }
.gm-acts { display: inline-flex; flex-wrap: wrap; gap: 6px; }
.gm-dec { font-size: 12.5px; font-weight: 700; }
.gm-dec[data-st="approved"] { color: var(--c-success-fg); } .gm-dec[data-st="rejected"] { color: var(--c-danger-fg); }
.gm-chk input { width: 18px; height: 18px; }
.gm-price { display: flex; flex-direction: column; gap: 4px; font-size: 12px; font-weight: 700; text-align: start; margin-top: 8px; }
.gm-price small { font-weight: 500; color: var(--c-muted-fg); }
.gm-activity { margin-top: 10px; }
.gm-acts-list { display: flex; flex-direction: column; margin-top: 8px; }
.gm-acts-list li { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; padding: 7px 0; border-top: 1px solid var(--c-border); font-size: 12.5px; }
.gm-a-by { margin-inline-start: auto; font-size: 11.5px; color: var(--c-muted-fg); }
.gm-bal { font-weight: 800; }
.gm-bal[data-sign="owes"] { color: var(--c-danger-fg); } .gm-bal[data-sign="credit"] { color: var(--c-success-fg); } .gm-bal[data-sign="zero"] { color: var(--c-muted-fg); }
.gm-st-table tr[data-voided] { opacity: .55; }
.gm-note { font-size: 12px; color: var(--c-muted-fg); overflow-wrap: anywhere; max-width: 260px; }
.gm-pend h4 { font-size: 13px; font-weight: 800; color: var(--c-warning-fg); margin-bottom: 6px; }
.gm-pend li { display: flex; flex-wrap: wrap; gap: 4px 12px; padding: 7px 0; border-top: 1px solid var(--c-border); font-size: 12.5px; }
.gm-pend small { color: var(--c-muted-fg); }
.gm-subnav { margin-bottom: 2px; }
@media (max-width: 767px) {
  .gm-form { grid-template-columns: 1fr; }
  .gm-st > .ag-card-h { flex-direction: column; align-items: stretch; }
  .gm-st > .ag-card-h .ag-actions { display: grid; grid-template-columns: 1fr 1fr; }
  .gm-form .input { font-size: 16px; height: 44px; }
  .gm-bar .ag-actions { width: 100%; }
  .gm-bar .ag-actions .ag-act { flex: 1 1 calc(50% - 8px); }
}
@media print {
  .csp-rail, .csp-topbar, .csp-mtop, .csp-botnav, .ag-tabs, .ag-head, .gm-noprint, .admin-sidebar, header, nav { display: none !important; }
  .csp-main { padding: 0 !important; }
  .gm-st { border: 0 !important; box-shadow: none !important; }
}
`
