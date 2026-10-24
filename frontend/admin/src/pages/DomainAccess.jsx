import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { jalali } from '../lib/format'
import { Toggle, Copyable, Spinner } from '../components/ui'
import { useConfirm } from '../components/ConfirmDialog'
import { Why } from '../components/DomainWhy'

// Settings → Domain & Cloudflare → Access mode (docs/access-mode.md): the same domain
// reached directly, through the Cloudflare proxy, or through an Iran tunnel. A switch
// = DNS (root + www; mail.* never) + a check through the new path, reverted on failure.

const T = {
  fa: {
    h: 'حالت دسترسی', sub: 'همان دامنه، سه مسیر. هر زمان قابل تغییر، بدون قطعی، با بازگشت یک‌کلیکی. رکورد mail.* هرگز تغییر نمی‌کند.',
    modes: {
      direct: ['مستقیم', 'رکورد A ← همین سرور، ابر خاکستری.'],
      cloudflare: ['پروکسی Cloudflare', 'ابر نارنجی با همان توکن؛ SSL روی Full (strict). IP واقعی بازدیدکننده فقط از رنج‌های رسمی Cloudflare پذیرفته می‌شود.'],
      tunnel: ['تونل ایران', 'رکورد A ← IP سرور ایران، ابر خاکستری. تونل پورت 443 (و 80) را به این سرور می‌رساند.'],
    },
    now: 'حالت فعلی', switch_to: 'رفتن به این حالت', back: 'بازگشت به حالت قبلی', skip: 'بدون بررسی مسیر (فقط اگر IP ایران از خارج در دسترس نیست)',
    confirm_t: 'تغییر حالت دسترسی', confirm_m: 'ابتدا مسیر جدید بررسی می‌شود، سپس DNS تغییر می‌کند و دوباره بررسی می‌شود. در صورت خطا DNS خودکار به حالت قبل برمی‌گردد. رکورد mail دست نمی‌خورد.',
    tunnel_h: 'تنظیمات تونل', iran: 'IP عمومی سرور ایران', iran_hint: 'یکی در هر خط. در حالت تونل، رکورد A همین است؛ با تغییر آن DNS هم به‌روز می‌شود.',
    sources: 'IPهای مبدأ تونل', sources_hint: 'آدرسی که درخواست‌های تونل با آن به این سرور می‌رسند (IPv4، IPv6، CIDR، رنج خصوصی یا 127.0.0.1). درخواست از این آدرس‌ها از محدودیت‌های تک‌IP معاف است و بر اساس کاربر/نشست محدود می‌شود.',
    detect: 'تشخیص خودکار', detecting: 'در حال ارسال درخواست آزمایشی از مسیر تونل…', found: 'آدرس دیده‌شده', add: 'افزودن به فهرست',
    detect_manual: 'اگر IP ایران از اینجا در دسترس نیست، این دستور را روی سرور ایران اجرا کنید و دوباره «تشخیص خودکار» بزنید:',
    pp: 'PROXY protocol (اختیاری)', pp_hint: 'فقط اگر تونل شما هدر PROXY می‌فرستد روشن کنید؛ آنگاه تونل را به این پورت‌های این سرور بفرستید:',
    pp_port: 'پورت {p} ← این سرور {l}', save: 'ذخیرهٔ تنظیمات',
    dup: 'در حالت تونل بدون PROXY protocol، همهٔ بازدیدکننده‌ها با IP تونل دیده می‌شوند (IP تکراری). این پذیرفتنی است: محدودیت‌ها بر اساس کاربر/نشست اعمال می‌شود، نه IP.',
    steps: { check: 'بررسی', ssl: 'SSL Full (strict)', preverify: 'بررسی مسیر پیش از DNS', dns: 'تغییر DNS', propagate: 'انتشار DNS', verify: 'بررسی مسیر جدید', revert: 'بازگرداندن DNS' },
    st: { running: 'در حال انجام…', ok: 'انجام شد', failed: 'ناموفق', reverted: 'برگشت داده شد' },
    nginx: 'nginx (رنج‌های Cloudflare و PROXY)', ranges: '{n} رنج Cloudflare', ranges_at: 'به‌روزرسانی',
    certs: 'گواهی‌ها با DNS-01', certs_hint: 'تمدید گواهی با توکن Cloudflare (رکورد TXT) — در هر سه حالت کار می‌کند، حتی اگر پورت 80 از بیرون نرسد.',
    certs_on: 'فعال', certs_off: 'غیرفعال (HTTP-01)', certs_btn: 'فعال‌سازی / به‌روزرسانی DNS-01', history: 'سابقهٔ تغییر حالت',
    details: 'جزئیات', yes: 'بله', no: 'خیر', na: 'نامشخص',
  },
  en: {
    h: 'Access mode', sub: 'One domain, three paths. Switch any time, no downtime, one click back. mail.* is never touched.',
    modes: {
      direct: ['Direct', 'A record → this server, grey cloud.'],
      cloudflare: ['Cloudflare proxy', 'Orange cloud with the same token; SSL Full (strict). The visitor’s real IP is accepted only from Cloudflare’s official ranges.'],
      tunnel: ['Iran tunnel', 'A record → the Iran server’s IP, grey cloud. The tunnel carries 443 (and 80) to this server.'],
    },
    now: 'current', switch_to: 'Switch to this mode', back: 'Back to the previous mode', skip: 'Skip the path check (only if the Iran IP can’t be reached from abroad)',
    confirm_t: 'Change the access mode', confirm_m: 'The new path is checked first, then DNS changes and the path is checked again. On any failure DNS goes back automatically. The mail record is not touched.',
    tunnel_h: 'Tunnel settings', iran: 'Iran server public IP', iran_hint: 'One per line. In tunnel mode this is the A record; editing it updates DNS.',
    sources: 'Tunnel source IPs', sources_hint: 'The address tunnel requests arrive from on this server (IPv4, IPv6, CIDR, private range or 127.0.0.1). Requests from these are exempt from per-IP limits and limited per user / session instead.',
    detect: 'Auto-detect', detecting: 'Sending a test request through the tunnel…', found: 'Address seen', add: 'Add to the list',
    detect_manual: 'If the Iran IP can’t be reached from here, run this on the Iran server, then press “Auto-detect” again:',
    pp: 'PROXY protocol (optional)', pp_hint: 'Turn on only if your tunnel sends a PROXY header; then point the tunnel at these ports of this server:',
    pp_port: 'port {p} → this server {l}', save: 'Save settings',
    dup: 'In tunnel mode without PROXY protocol every visitor shows up with the tunnel’s IP (duplicate IP). That is fine: limits apply per user / session, not per IP.',
    steps: { check: 'Check', ssl: 'SSL Full (strict)', preverify: 'Path check before DNS', dns: 'DNS change', propagate: 'DNS propagation', verify: 'New path check', revert: 'DNS put back' },
    st: { running: 'running…', ok: 'done', failed: 'failed', reverted: 'reverted' },
    nginx: 'nginx (Cloudflare ranges + PROXY)', ranges: '{n} Cloudflare ranges', ranges_at: 'updated',
    certs: 'Certificates via DNS-01', certs_hint: 'Renewal with the Cloudflare token (TXT record) — works in all three modes, even when port 80 isn’t reachable.',
    certs_on: 'on', certs_off: 'off (HTTP-01)', certs_btn: 'Enable / refresh DNS-01', history: 'Mode history',
    details: 'details', yes: 'yes', no: 'no', na: 'unknown',
  },
}
const MODES = ['direct', 'cloudflare', 'tunnel']
const STEP_ORDER = ['check', 'ssl', 'preverify', 'dns', 'propagate', 'verify', 'revert']
const lines = (v) => v.split(/[\s,]+/).map((x) => x.trim()).filter(Boolean)

export default function AccessMode({ st, lang, take }) {
  const s = T[lang] || T.fa
  const confirm = useConfirm()
  const ax = st.access || {}
  const sw = ax.switch || {}
  const running = sw.status === 'running'
  const [pick, setPick] = useState(ax.mode || 'direct')
  const [iran, setIran] = useState((ax.iran_ips || []).join('\n'))
  const [src, setSrc] = useState((ax.tunnel_sources || []).join('\n'))
  const [pp, setPp] = useState(ax.proxy_protocol || { 80: false, 443: false })
  const [skip, setSkip] = useState(false)
  const [busy, setBusy] = useState('')
  const [det, setDet] = useState(null)
  useEffect(() => { setIran((ax.iran_ips || []).join('\n')); setSrc((ax.tunnel_sources || []).join('\n')); setPp(ax.proxy_protocol || {}) },
    [JSON.stringify(ax.iran_ips), JSON.stringify(ax.tunnel_sources), JSON.stringify(ax.proxy_protocol)])
  useEffect(() => { if (!running) setPick(ax.mode || 'direct') }, [ax.mode, running])

  const post = async (key, url, body = {}) => {
    setBusy(key)
    try { const r = await api.post(url, body); take(r.data); return r.data } catch (e) { if (e?.response?.data?.current) take(e.response.data); return null } finally { setBusy('') }
  }
  const dirty = iran !== (ax.iran_ips || []).join('\n') || src !== (ax.tunnel_sources || []).join('\n')
    || !!pp['80'] !== !!ax.proxy_protocol?.['80'] || !!pp['443'] !== !!ax.proxy_protocol?.['443']
  const save = () => post('save', '/admin/domain/access/settings/', { iran_ips: lines(iran), tunnel_sources: lines(src), proxy_protocol: pp })
  const detect = async () => {
    setBusy('detect'); setDet(null)
    try { const r = await api.post('/admin/domain/access/detect/', {}); setDet(r.data) } catch (e) { setDet({ error: e?.response?.data?.error, found: [] }) } finally { setBusy('') }
  }
  const prev = (sw.history || []).find((h) => h.status === 'ok' && h.from !== ax.mode)?.from

  return (
    <section className="card dm-card ax">
      <style>{CSS}</style>
      <div className="dm-row-h"><h2>{s.h}</h2>{running && <span className="dm-pill run"><span className="dm-spin" /> {s.st.running}</span>}</div>
      <p className="dm-hint">{s.sub}</p>

      <div className="ax-modes" role="radiogroup" aria-label={s.h}>
        {MODES.map((m) => (
          <button key={m} type="button" role="radio" aria-checked={pick === m} disabled={running}
            className={`ax-mode${pick === m ? ' on' : ''}${ax.mode === m ? ' cur' : ''}`} onClick={() => setPick(m)}>
            <b>{s.modes[m][0]}{ax.mode === m && <small> · {s.now}</small>}</b>
            <span>{s.modes[m][1]}</span>
          </button>
        ))}
      </div>
      {pick === 'tunnel' && <p className="ax-note">{s.dup}</p>}
      <div className="dm-actions">
        <button className="btn-primary text-sm" disabled={running || !!busy || pick === ax.mode}
          onClick={() => confirm({ tone: 'danger', title: s.confirm_t, message: s.confirm_m, confirmLabel: s.switch_to,
            details: [[s.now, s.modes[ax.mode || 'direct'][0]], ['→', s.modes[pick][0]]],
            action: async () => { await post('switch', '/admin/domain/access/', { mode: pick, skip_verify: pick === 'tunnel' && skip }) } })}>
          {busy === 'switch' ? <span className="dm-spin" /> : s.switch_to}
        </button>
        {prev && <button className="btn-ghost text-sm" disabled={running || !!busy}
          onClick={() => post('back', '/admin/domain/access/back/')}>{s.back}: {s.modes[prev][0]}</button>}
      </div>
      {pick === 'tunnel' && pick !== ax.mode && (
        <label className="ax-skip"><input type="checkbox" checked={skip} onChange={(e) => setSkip(e.target.checked)} /><span>{s.skip}</span></label>
      )}

      {sw.steps && Object.keys(sw.steps).length > 0 && (
        <ol className="ax-steps" aria-live="polite">
          {STEP_ORDER.filter((k) => sw.steps[k]).map((k) => (
            <li key={k} className={sw.steps[k].state}><b>{s.steps[k]}</b> <bdi className="dm-msg">{sw.steps[k].message}</bdi></li>
          ))}
          {sw.status && sw.status !== 'running' && (
            <li className={sw.status === 'ok' ? 'ok' : 'failed'}><b>{s.modes[sw.to]?.[0]}: {s.st[sw.status] || sw.status}</b>
              {sw.finished_at && <small> · {jalali(sw.finished_at, true, lang)}</small>}</li>
          )}
        </ol>
      )}
      {sw.error && !running && <Why info={sw.error} lang={lang} s={s} />}

      <div className="ax-sub">
        <h3>{s.tunnel_h}</h3>
        <div className="ax-grid">
          <label className="dm-field"><span className="label">{s.iran}</span>
            <textarea className="input dm-mono" dir="ltr" rows={2} value={iran} placeholder="185.124.174.13" onChange={(e) => setIran(e.target.value)} />
            <small className="dm-hint">{s.iran_hint}</small></label>
          <label className="dm-field"><span className="label">{s.sources}</span>
            <textarea className="input dm-mono" dir="ltr" rows={3} value={src} placeholder={'172.19.0.1\n10.10.0.0/24'} onChange={(e) => setSrc(e.target.value)} />
            <small className="dm-hint">{s.sources_hint}</small></label>
        </div>
        <div className="dm-actions">
          <button className="btn-ghost text-sm" disabled={!!busy || !(ax.iran_ips || []).length} onClick={detect}>
            {busy === 'detect' ? <><span className="dm-spin" /> {s.detecting}</> : s.detect}</button>
        </div>
        {det && (
          <div className="ax-det">
            {det.found?.map((ip) => (
              <div key={ip} className="ax-found"><span>{s.found}:</span> <bdi dir="ltr" className="dm-mono">{ip}</bdi>
                {!lines(src).includes(ip) && <button className="btn-ghost text-xs" onClick={() => setSrc((v) => (v.trim() ? `${v.trim()}\n${ip}` : ip))}>{s.add}</button>}</div>
            ))}
            {det.error && <Why info={det.error} lang={lang} s={s} small />}
            {det.command && (<><small className="dm-hint">{s.detect_manual}</small>
              <span className="dm-cp"><code dir="ltr" className="dm-mono ax-cmd">{det.command}</code><Copyable text={det.command} /></span></>)}
          </div>
        )}
        <div className="ax-pp">
          <b>{s.pp}</b>
          <small className="dm-hint">{s.pp_hint}</small>
          {['443', '80'].map((p) => (
            <div key={p} className="dm-www">
              <Toggle checked={!!pp[p]} onChange={(v) => setPp({ ...pp, [p]: v })} label={`PROXY ${p}`} />
              <span dir="ltr">{s.pp_port.replace('{p}', p).replace('{l}', ax.proxy_listen?.[p] ?? '')}</span>
            </div>
          ))}
        </div>
        <div className="dm-actions"><button className="btn-primary text-sm" disabled={!dirty || !!busy} onClick={save}>{busy === 'save' ? <Spinner /> : s.save}</button></div>
      </div>

      <div className="ax-meta">
        <div><b>{s.nginx}</b>: {sw.nginx ? <span className={`ax-${sw.nginx.state}`}>{s.st[sw.nginx.state] || sw.nginx.state}</span> : '—'}
          {sw.nginx?.message && <bdi className="dm-msg"> · {sw.nginx.message}</bdi>}
          <small className="dm-hint"> · {s.ranges.replace('{n}', ax.cf_ranges?.count ?? 0)}{ax.cf_ranges?.at && ` · ${s.ranges_at} ${jalali(ax.cf_ranges.at, true, lang)}`}</small></div>
        {sw.nginx?.error && <Why info={sw.nginx.error} lang={lang} s={s} small />}
        <div><b>{s.certs}</b>: {ax.dns01?.enabled ? <span className="ax-ok">{s.certs_on}</span> : <span>{s.certs_off}</span>}
          {ax.dns01?.state === 'running' && <> · <span className="dm-spin" /></>}
          {ax.dns01?.message && <bdi className="dm-msg"> · {ax.dns01.message}</bdi>}</div>
        {ax.dns01?.error && <Why info={ax.dns01.error} lang={lang} s={s} small />}
        <small className="dm-hint">{s.certs_hint}</small>
        <div className="dm-actions"><button className="btn-ghost text-sm" disabled={!!busy || ax.dns01?.state === 'running'}
          onClick={() => post('dns01', '/admin/domain/access/dns01/')}>{s.certs_btn}</button></div>
      </div>

      {!!sw.history?.length && (
        <details className="ax-hist"><summary>{s.history}</summary>
          <ul>{sw.history.map((h, i) => (
            <li key={i}><span>{s.modes[h.from]?.[0]} → {s.modes[h.to]?.[0]}</span> <b className={h.status === 'ok' ? 'ax-ok' : 'ax-failed'}>{s.st[h.status] || h.status}</b>
              <small> · {jalali(h.at, true, lang)} · {h.by}</small></li>))}</ul>
        </details>
      )}
    </section>
  )
}

const CSS = `
.ax-modes { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.ax-mode { text-align: start; border: 1.5px solid var(--c-border); border-radius: 14px; padding: 12px; display: flex; flex-direction: column; gap: 4px; background: transparent; color: inherit; cursor: pointer; min-height: 44px; }
.ax-mode b { font-size: 14px; } .ax-mode b small { font-weight: 600; color: var(--c-success-fg); }
.ax-mode span { font-size: 12px; color: var(--c-muted-fg); line-height: 1.7; }
.ax-mode.on { border-color: var(--c-primary); box-shadow: 0 0 0 3px color-mix(in srgb, var(--c-primary) 18%, transparent); }
.ax-mode:disabled { opacity: .6; cursor: default; }
.ax-note { font-size: 12.5px; line-height: 1.8; padding: 8px 10px; border-radius: 10px; background: color-mix(in srgb, var(--c-warning) 12%, transparent); border: 1px solid color-mix(in srgb, var(--c-warning) 35%, transparent); }
.ax-skip { display: flex; gap: 8px; align-items: flex-start; font-size: 12.5px; color: var(--c-muted-fg); }
.ax-skip input { margin-top: 4px; width: 18px; height: 18px; flex: none; }
.ax-steps { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; font-size: 12.5px; }
.ax-steps li { padding-inline-start: 18px; position: relative; overflow-wrap: anywhere; }
.ax-steps li::before { content: '•'; position: absolute; inset-inline-start: 4px; }
.ax-steps li.ok { color: var(--c-success-fg); } .ax-steps li.failed { color: var(--c-danger-fg); } .ax-steps li.waiting { color: var(--c-warning-fg); }
.ax-sub { border-top: 1px solid var(--c-border); padding-top: 12px; display: flex; flex-direction: column; gap: 10px; }
.ax-sub h3 { font-size: 14px; font-weight: 800; }
.ax-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.ax-grid textarea { font-size: 13px; resize: vertical; }
.ax-det { display: flex; flex-direction: column; gap: 6px; font-size: 13px; }
.ax-found { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ax-cmd { font-size: 11.5px; word-break: break-all; }
.ax-pp { display: flex; flex-direction: column; gap: 4px; }
.ax-meta { border-top: 1px solid var(--c-border); padding-top: 12px; display: flex; flex-direction: column; gap: 6px; font-size: 13px; }
.ax-ok { color: var(--c-success-fg); font-weight: 700; } .ax-failed { color: var(--c-danger-fg); font-weight: 700; } .ax-running { color: var(--c-warning-fg); }
.ax-hist summary { cursor: pointer; font-size: 13px; font-weight: 700; }
.ax-hist ul { list-style: none; padding: 0; margin: 6px 0 0; display: flex; flex-direction: column; gap: 4px; font-size: 12.5px; }
@media (max-width: 767px) {
  .ax-modes, .ax-grid { grid-template-columns: 1fr; }
  .ax-grid textarea { font-size: 16px; }
}
`
