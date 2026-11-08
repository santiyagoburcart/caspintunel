import { useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { jalali } from '../lib/format'
import { copyToClipboard } from '../lib/clipboard'
import { useConfirm } from './ConfirmDialog'
import { useToast } from './Toast'
import { Ic } from './AgencyIcons'

// v1.45 (multi-tenant Phase 3) store domains on «فروشگاه» — our staff only (backend apps/tenancy/domains.py). Each domain shows the
// exact records for the reseller's Cloudflare, what the DNS / certificate / health checks saw, and the actions.
const T = {
  fa: {
    title: 'دامنه‌ها', none: 'هنوز دامنه‌ای ثبت نشده.', add: 'افزودن دامنه', host: 'دامنه (مثلاً shop.example.com)',
    mode: 'حالت', m_direct: 'مستقیم — آی‌پی فنلاند', m_tunnel: 'تونل ایران — آی‌پی ایران', www: 'www هم باشد (به دامنهٔ اصلی هدایت می‌شود)',
    st_pending_dns: 'در انتظار DNS', st_verified: 'تأیید شد', st_cert_pending: 'در انتظار گواهی', st_active: 'فعال', st_failed: 'ناموفق',
    proxied: 'پروکسی Cloudflare', records: 'رکوردهایی که نماینده در Cloudflare خودش می‌سازد', type: 'نوع', name: 'نام', value: 'مقدار',
    p_any: 'DNS only یا Proxied', p_dns: 'فقط DNS only', copy: 'کپی', copied: 'کپی شد', copy_all: 'کپی همهٔ رکوردها',
    cf_note: 'اگر رکورد A روی Proxied (ابر نارنجی) است: SSL/TLS را روی «Full» بگذارید؛ «Full (strict)» فقط بعد از صدور گواهی، و «Flexible» هرگز (حلقهٔ ریدایرکت). TTL کوتاه (Auto یا 1 دقیقه) بهتر است.',
    checks: 'بررسی‌ها', c_txt: 'رکورد TXT', c_a: 'رکورد A', c_www: 'رکورد www', c_reach: 'رسیدن درخواست به سرور ما (از پشت Cloudflare)',
    seen: 'دیده شد', expected: 'انتظار', nothing: 'هیچ', c_cert: 'گواهی', c_health: 'سلامت (TLS از مسیر عمومی)',
    expires: 'انقضا', ok: 'درست', bad: 'نادرست', waiting: 'هنوز بررسی نشده', last: 'آخرین بررسی', error: 'خطا',
    check: 'بررسی الان', retry: 'تلاش دوباره', remove: 'حذف دامنه', change_mode: 'تغییر حالت', www_on: 'افزودن www', www_off: 'برداشتن www',
    r_title: 'حذف دامنه', r_msg: 'فروشگاه دیگر روی {h} جواب نمی‌دهد؛ فایل nginx و گواهی آن حذف می‌شوند. نماینده می‌تواند رکوردها را پاک کند.', r_btn: 'بله، حذف شود',
    m_title: 'تغییر حالت دامنه', m_msg: 'رکورد A باید به «{ip}» عوض شود (رکوردهای تازه نمایش داده می‌شود). تا تأیید DNS جدید، دامنه دوباره بررسی می‌شود{active}.', m_active: ' (سایت فعال تا آن موقع کار می‌کند)', m_btn: 'بله، تغییر بده',
    w_title: 'تغییر www', w_msg: 'برای {h} گواهی تازه گرفته می‌شود.', w_btn: 'بله',
    a_title: 'افزودن دامنه', a_msg: 'دامنهٔ {h} برای این فروشگاه ثبت می‌شود و رکوردهای لازم نمایش داده می‌شود.', a_btn: 'بله، اضافه کن',
    failures: 'تلاش ناموفق گواهی', steps: 'مراحل: DNS → گواهی (HTTP-01) → فعال', fails_note: 'بعد از ۳ تلاش ناموفق متوقف می‌شود — «تلاش دوباره».',
  },
  en: {
    title: 'Domains', none: 'No domain yet.', add: 'Add domain', host: 'Domain (e.g. shop.example.com)',
    mode: 'Mode', m_direct: 'Direct — Finland IP', m_tunnel: 'Iran tunnel — Iran IP', www: 'Include www (redirects to the bare domain)',
    st_pending_dns: 'Waiting for DNS', st_verified: 'Verified', st_cert_pending: 'Certificate pending', st_active: 'Active', st_failed: 'Failed',
    proxied: 'Cloudflare proxy', records: 'Records the reseller creates in their Cloudflare', type: 'Type', name: 'Name', value: 'Value',
    p_any: 'DNS only or Proxied', p_dns: 'DNS only', copy: 'Copy', copied: 'Copied', copy_all: 'Copy all records',
    cf_note: 'If the A record is Proxied (orange cloud): set SSL/TLS to “Full”; “Full (strict)” only after the certificate exists, never “Flexible” (redirect loop). A short TTL (Auto or 1 min) is best.',
    checks: 'Checks', c_txt: 'TXT record', c_a: 'A record', c_www: 'www record', c_reach: 'A request reaches our server (behind Cloudflare)',
    seen: 'seen', expected: 'expected', nothing: 'nothing', c_cert: 'Certificate', c_health: 'Health (TLS over the public path)',
    expires: 'expires', ok: 'OK', bad: 'wrong', waiting: 'not checked yet', last: 'Last check', error: 'Error',
    check: 'Check now', retry: 'Retry', remove: 'Remove domain', change_mode: 'Change mode', www_on: 'Add www', www_off: 'Drop www',
    r_title: 'Remove domain', r_msg: 'The store stops answering on {h}; its nginx file and certificate are removed. The reseller can delete the records.', r_btn: 'Yes, remove it',
    m_title: 'Change domain mode', m_msg: 'The A record must change to “{ip}” (the new records are shown). The domain is checked again until the new DNS is verified{active}.', m_active: ' (the live site keeps working meanwhile)', m_btn: 'Yes, change it',
    w_title: 'Change www', w_msg: 'A new certificate is issued for {h}.', w_btn: 'Yes',
    a_title: 'Add domain', a_msg: 'The domain {h} is registered for this store and the records to create are shown.', a_btn: 'Yes, add it',
    failures: 'failed certificate attempts', steps: 'Steps: DNS → certificate (HTTP-01) → active', fails_note: 'Stops after 3 failed attempts — “Retry”.',
  },
}

export default function StoreDomains({ base, domains, manage, onChanged }) {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const confirm = useConfirm()
  const toast = useToast()
  const [form, setForm] = useState({ host: '', mode: 'direct', www: true })

  const add = async (e) => {
    e.preventDefault()
    const h = form.host.trim()
    if (!h) return
    const ok = await confirm({ tone: 'primary', icon: 'plus', title: s.a_title, targetLabel: s.title, targetId: h,
      message: s.a_msg.replace('{h}', h), confirmLabel: s.a_btn, action: () => api.post(`${base}domains/`, { ...form, host: h }) })
    if (ok) { setForm({ host: '', mode: form.mode, www: true }); onChanged() }
  }
  const copy = async (text) => { if (await copyToClipboard(text)) toast.success(s.copied) }

  return (
    <div className="sd" data-testid="store-domains">
      <style>{CSS}</style>
      <div className="text-sm font-semibold">{s.title}</div>
      <p className="text-xs text-muted">{s.steps}</p>
      {domains.length === 0 && <p className="text-xs text-muted">{s.none}</p>}
      {domains.map((d) => <Domain key={d.id} d={d} s={s} lang={lang} base={base} manage={manage} copy={copy} confirm={confirm} onChanged={onChanged} />)}
      {manage && (
        <form className="sd-add" onSubmit={add} data-testid="domain-add">
          <input className="input sd-host" dir="ltr" autoCapitalize="none" autoCorrect="off" spellCheck={false} placeholder={s.host}
            aria-label={s.host} value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} />
          <div className="sd-modes" role="radiogroup" aria-label={s.mode}>
            {['direct', 'tunnel'].map((m) => (
              <button key={m} type="button" role="radio" aria-checked={form.mode === m} className={'sd-mode' + (form.mode === m ? ' on' : '')}
                onClick={() => setForm({ ...form, mode: m })}>{s['m_' + m]}</button>
            ))}
          </div>
          <label className="sd-chk"><input type="checkbox" checked={form.www} onChange={(e) => setForm({ ...form, www: e.target.checked })} />{s.www}</label>
          <button className="btn-primary text-sm sd-btn" disabled={!form.host.trim()}><Ic n="plus" />{s.add}</button>
        </form>
      )}
    </div>
  )
}

function Mark({ ok, s }) {
  if (ok == null) return <span className="sd-m" data-ok="na">• {s.waiting}</span>
  return <span className="sd-m" data-ok={ok ? '1' : '0'}>{ok ? '✓' : '✗'} {ok ? s.ok : s.bad}</span>
}

function Domain({ d, s, lang, base, manage, copy, confirm, onChanged }) {
  const url = `${base}domains/${d.id}/`
  const ins = d.instructions || { records: [] }
  const dns = d.dns || {}
  const w = d.watcher || {}
  const other = d.mode === 'direct' ? 'tunnel' : 'direct'
  const act = async (fn) => { try { await fn(); onChanged() } catch { /* the toast shows why */ } }
  const remove = async () => {
    const ok = await confirm({ tone: 'danger', icon: 'trash', title: s.r_title, targetLabel: s.title, targetId: d.host,
      message: s.r_msg.replace('{h}', d.host), confirmLabel: s.r_btn, action: () => api.delete(url) })
    if (ok) onChanged()
  }
  const setMode = async () => {
    const ok = await confirm({ tone: 'warning', icon: 'sync', title: s.m_title, targetLabel: s.title, targetId: `${d.host} → ${s['m_' + other]}`,
      message: s.m_msg.replace('{ip}', s['m_' + other]).replace('{active}', d.state === 'active' ? s.m_active : ''),
      confirmLabel: s.m_btn, action: () => api.patch(url, { mode: other }) })
    if (ok) onChanged()
  }
  const setWww = async () => {
    const ok = await confirm({ tone: 'warning', icon: 'globe', title: s.w_title, targetLabel: s.title, targetId: d.host,
      message: s.w_msg.replace('{h}', d.host), confirmLabel: s.w_btn, action: () => api.patch(url, { www: !d.www }) })
    if (ok) onChanged()
  }
  const recText = ins.records.map((r) => `${r.type}\t${r.name}\t${r.value}`).join('\n')
  const aRow = (k, label) => dns[k] && (
    <li><b>{label}</b> <Mark ok={dns[k].ok || dns[k].proxied} s={s} />
      <span className="sd-dim"> · {s.seen}: <bdi dir="ltr">{dns[k].seen?.join(', ') || s.nothing}</bdi>
        {!dns[k].proxied && <> · {s.expected}: <bdi dir="ltr">{dns[k].expected}</bdi></>}</span></li>)
  return (
    <div className="sd-card" data-testid="domain-card" data-state={d.state}>
      <div className="sd-head">
        <bdi dir="ltr" className="sd-name">{d.host}</bdi>
        <span className="sd-pill" data-st={d.state}>{s['st_' + d.state] || d.state}</span>
        <span className="sd-chip">{s['m_' + d.mode]}</span>
        {d.proxied && <span className="sd-chip">{s.proxied}</span>}
      </div>
      {d.state !== 'active' && ins.records.length > 0 && (
        <div className="sd-recs">
          <div className="sd-sub">{s.records}</div>
          <div className="sd-table">
            {ins.records.map((r) => (
              <div key={r.type + r.name} className="sd-rec">
                <span className="sd-type">{r.type}</span>
                <bdi dir="ltr" className="sd-v">{r.name}</bdi>
                <bdi dir="ltr" className="sd-v sd-val">{r.value || '—'}</bdi>
                <span className="sd-dim">{r.proxy === 'dns_only' ? s.p_dns : s.p_any}</span>
                <button type="button" className="sd-copy" onClick={() => copy(r.value)} aria-label={`${s.copy} ${r.name}`}><Ic n="copy" />{s.copy}</button>
              </div>
            ))}
          </div>
          <button type="button" className="sd-link" onClick={() => copy(recText)}><Ic n="copy" />{s.copy_all}</button>
          <p className="sd-note">{s.cf_note}</p>
        </div>
      )}
      <div className="sd-sub">{s.checks}</div>
      <ul className="sd-checks">
        {dns.txt && <li><b>{s.c_txt}</b> <Mark ok={dns.txt.ok} s={s} /></li>}
        {aRow('a', s.c_a)}
        {aRow('www', s.c_www)}
        {dns.reach && <li><b>{s.c_reach}</b> <Mark ok={dns.reach.ok} s={s} /></li>}
        {(d.state === 'cert_pending' || d.state === 'active' || d.state === 'failed') && (
          <li><b>{s.c_cert}</b> <Mark ok={w.cert_ok ?? (d.cert_expires_at ? true : null)} s={s} />
            {d.cert_expires_at && <span className="sd-dim"> · {s.expires} {jalali(d.cert_expires_at, false, lang)}</span>}
            {d.cert_failures > 0 && <span className="sd-dim"> · {d.cert_failures} {s.failures}</span>}</li>)}
        {d.health && <li><b>{s.c_health}</b> <Mark ok={d.health.ok} s={s} />
          {d.health.at && <span className="sd-dim"> · {jalali(d.health.at, true, lang)}</span>}</li>}
        {!dns.at && <li className="sd-dim">{s.waiting}</li>}
      </ul>
      {d.last_error && <p className="sd-err" dir="auto"><b>{s.error}:</b> <bdi dir="ltr">{d.last_error}</bdi></p>}
      {d.state === 'failed' && <p className="sd-dim text-xs">{s.fails_note}</p>}
      {d.last_check_at && <p className="sd-dim text-xs">{s.last}: {jalali(d.last_check_at, true, lang)}</p>}
      {manage && (
        <div className="sd-acts">
          <button type="button" className="sd-act" onClick={() => act(() => api.post(`${url}check/`))} data-testid="domain-check">
            <Ic n="sync" />{d.state === 'failed' ? s.retry : s.check}</button>
          <button type="button" className="sd-act" onClick={setMode}><Ic n="server" />{s.change_mode}</button>
          <button type="button" className="sd-act" onClick={setWww}><Ic n="globe" />{d.www ? s.www_off : s.www_on}</button>
          <button type="button" className="sd-act" data-tone="danger" onClick={remove}><Ic n="trash" />{s.remove}</button>
        </div>
      )}
    </div>
  )
}

const CSS = `
.sd { display: flex; flex-direction: column; gap: 8px; }
.sd-card { border: 1px solid var(--c-border); border-radius: 14px; padding: 12px; display: flex; flex-direction: column; gap: 8px; background: var(--c-bg); min-width: 0; }
.sd-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.sd-name { font-weight: 800; font-size: 14px; overflow-wrap: anywhere; font-family: 'JetBrains Mono', ui-monospace, monospace; }
.sd-pill { font-size: 12px; font-weight: 800; padding: 2px 10px; border-radius: 999px; color: var(--c-warning-fg); background: color-mix(in srgb, var(--c-warning) 16%, transparent); }
.sd-pill[data-st="active"] { color: var(--c-success-fg); background: color-mix(in srgb, var(--c-success) 16%, transparent); }
.sd-pill[data-st="failed"] { color: var(--c-danger-fg); background: color-mix(in srgb, var(--c-danger) 14%, transparent); }
.sd-chip { font-size: 11.5px; padding: 2px 8px; border-radius: 999px; color: var(--c-muted-fg); background: color-mix(in srgb, var(--c-text-muted) 12%, transparent); }
.sd-sub { font-size: 12px; font-weight: 800; color: var(--c-text-muted); }
.sd-table { display: flex; flex-direction: column; gap: 6px; }
.sd-rec { display: grid; grid-template-columns: 48px minmax(0, 1.2fr) minmax(0, 1.4fr) auto auto; align-items: center; gap: 8px; font-size: 12.5px;
  padding: 6px 8px; border-radius: 10px; background: color-mix(in srgb, var(--c-text-muted) 6%, transparent); }
.sd-type { font-weight: 800; }
.sd-v { overflow-wrap: anywhere; font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 12px; min-width: 0; }
.sd-val { color: var(--c-primary); }
.sd-copy, .sd-link { display: inline-flex; align-items: center; gap: 4px; min-height: 44px; padding: 0 10px; border-radius: 10px; font-size: 12px; font-weight: 700;
  color: var(--c-primary); border: 1px solid var(--c-border); background: var(--c-bg); }
.sd-link { align-self: flex-start; }
.sd-note { font-size: 12px; line-height: 1.8; color: var(--c-text-muted); }
.sd-checks { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; font-size: 12.5px; }
.sd-m[data-ok="1"] { color: var(--c-success-fg); font-weight: 700; }
.sd-m[data-ok="0"] { color: var(--c-danger-fg); font-weight: 700; }
.sd-m[data-ok="na"] { color: var(--c-text-muted); }
.sd-dim { color: var(--c-text-muted); }
.sd-err { font-size: 12px; color: var(--c-danger-fg); overflow-wrap: anywhere; margin: 0; }
.sd-acts { display: flex; flex-wrap: wrap; gap: 6px; }
.sd-act { display: inline-flex; align-items: center; gap: 6px; min-height: 44px; padding: 0 12px; border-radius: 12px; border: 1px solid var(--c-border);
  background: var(--c-bg); font-size: 13px; font-weight: 700; color: var(--c-text); }
.sd-act[data-tone="danger"] { color: var(--c-danger-fg); }
.sd-add { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr)); gap: 8px; align-items: center; }
.sd-host { min-width: 0; }
.sd-modes { display: flex; flex-wrap: wrap; gap: 6px; }
.sd-mode { flex: 1 1 auto; min-height: 44px; padding: 0 12px; border-radius: 12px; border: 1px solid var(--c-border); background: var(--c-bg); font-size: 12.5px; font-weight: 700; color: var(--c-text); }
.sd-mode.on { border-color: var(--c-primary); color: var(--c-primary); background: color-mix(in srgb, var(--c-primary) 10%, var(--c-bg)); }
.sd-chk { display: flex; align-items: center; gap: 8px; font-size: 13px; min-height: 44px; }
.sd-btn { min-height: 44px; display: inline-flex; align-items: center; justify-content: center; gap: 6px; }
@media (max-width: 767px) {
  .sd-host { font-size: 16px; min-height: 44px; }
  .sd-rec { grid-template-columns: 44px minmax(0, 1fr) auto; }
  .sd-rec .sd-val { grid-column: 2 / 3; }
  .sd-rec .sd-dim { grid-column: 1 / -1; font-size: 11.5px; }
  .sd-rec .sd-copy { grid-row: 1 / 3; grid-column: 3; }
}
`
