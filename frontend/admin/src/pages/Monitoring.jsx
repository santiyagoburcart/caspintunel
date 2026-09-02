import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { digits as D, gb, relTime, bps } from '../lib/format'
import { Spinner } from '../components/ui'

const REFRESH_MS = 15000

const T = {
  fa: {
    title: 'مانیتورینگ', autorefresh: '↻ رفرش خودکار (۱۵ث)', run_backup: '↑ اجرای بک‌آپ',
    running: 'در حال اجرا…', fetch_fail: 'دریافت اطلاعات مانیتورینگ ناموفق بود.',
    services_active: 'سرویس فعال', of: 'از',
    cpu: 'پردازنده (CPU)', ram: 'حافظه (RAM)', disk: 'دیسک', bandwidth: 'پهنای باند',
    cores: 'هسته', ghz: 'گیگاهرتز', gb: 'گیگابایت', gb_short: 'گیگ',
    avg: 'میانگین', peak: 'اوج', free: 'آزاد', attention: 'توجه', healthy: 'سالم', pct: '٪',
    iface: 'اینترفیس', sent: 'ارسال', recv: 'دریافت',
    svc_status: 'وضعیت سرویس‌ها', up: 'فعال', down: 'قطع', no_data: 'بدون داده',
    net_traffic: 'ترافیک شبکه', total_iface: 'مجموع اینترفیس', collecting: 'در حال جمع‌آوری داده…',
    sent_label: 'ارسال‌شده', recv_label: 'دریافت‌شده', sysver: 'نسخه سیستم',
    recent_backups: 'بک‌آپ‌های اخیر', no_backups: 'هنوز بک‌آپی ثبت نشده است.',
    run_backup_manual: '↑ اجرای بک‌آپ دستی', kb: 'کیلوبایت',
    server_ips: 'آدرس‌های IP سرور', public_ip: 'IP عمومی (IPv4)', local_ip: 'IP لوکال',
    docker_net: 'شبکه Docker', open_conns: 'اتصالات باز',
    bk_ok: 'موفق', bk_failed: 'ناموفق', bk_partial: 'ناقص', bk_running: 'در حال اجرا',
    svc_site: 'سایت (Web)', svc_mysql: 'دیتابیس (MySQL)', svc_redis: 'ردیس (Redis)',
    svc_celery_worker: 'Celery Worker', svc_celery_beat: 'Celery Beat',
    svc_bot_sales: 'ربات فروش', svc_bot_backup: 'ربات بک‌آپ',
    svc_panel: 'پنل‌ها (مجموع)', svc_mail: 'میل‌سرور (SMTP)',
    panels: 'وضعیت پنل‌ها', panel_users: 'کاربران', panel_online: 'آنلاین',
    panel_nodes: 'نودها', panel_cpu: 'CPU', panel_ram: 'RAM', panel_no_stats: 'آمار در دسترس نیست',
  },
  en: {
    title: 'Monitoring', autorefresh: '↻ Auto-refresh (15s)', run_backup: '↑ Run backup',
    running: 'running…', fetch_fail: 'Failed to load monitoring data.',
    services_active: 'services up', of: 'of',
    cpu: 'Processor (CPU)', ram: 'Memory (RAM)', disk: 'Disk', bandwidth: 'Bandwidth',
    cores: 'cores', ghz: 'GHz', gb: 'GB', gb_short: 'GB',
    avg: 'avg', peak: 'peak', free: 'free', attention: 'attention', healthy: 'healthy', pct: '%',
    iface: 'interface', sent: 'sent', recv: 'received',
    svc_status: 'Service status', up: 'up', down: 'down', no_data: 'no data',
    net_traffic: 'Network traffic', total_iface: 'total, interface', collecting: 'collecting data…',
    sent_label: 'Sent', recv_label: 'Received', sysver: 'System version',
    recent_backups: 'Recent backups', no_backups: 'No backups recorded yet.',
    run_backup_manual: '↑ Run manual backup', kb: 'KB',
    server_ips: 'Server IP addresses', public_ip: 'Public IP (IPv4)', local_ip: 'Local IP',
    docker_net: 'Docker network', open_conns: 'Open connections',
    bk_ok: 'success', bk_failed: 'failed', bk_partial: 'partial', bk_running: 'running',
    svc_site: 'Website (Web)', svc_mysql: 'Database (MySQL)', svc_redis: 'Redis',
    svc_celery_worker: 'Celery Worker', svc_celery_beat: 'Celery Beat',
    svc_bot_sales: 'Sales bot', svc_bot_backup: 'Backup bot',
    svc_panel: 'Panels (overall)', svc_mail: 'Mail server (SMTP)',
    panels: 'Panel status', panel_users: 'users', panel_online: 'online',
    panel_nodes: 'nodes', panel_cpu: 'CPU', panel_ram: 'RAM', panel_no_stats: 'stats unavailable',
  },
}

function fmtBytes(n) {
  if (n == null) return null
  const u = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0; let v = Number(n)
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${u[i]}`
}

// Build an SVG polyline path (600x150 viewBox) from the throughput series.
function graphPaths(series) {
  const pts = (series || []).map((s) => (s.up || 0) + (s.down || 0))
  if (pts.length < 2) return { line: '', area: '' }
  const max = Math.max(...pts, 1)
  const W = 600
  const H = 150
  const step = W / (pts.length - 1)
  const xy = pts.map((v, i) => [i * step, H - (v / max) * (H - 12) - 4])
  const line = xy.map(([x, y], i) => (i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1)).join(' ')
  const area = `${line} L${W} ${H} L0 ${H} Z`
  return { line, area }
}

export default function Monitoring() {
  const { lang } = useI18n()
  const m = T[lang] || T.fa
  const d = (v) => D(v, lang)
  const B = (v) => bps(v, lang)

  const [data, setData] = useState(null)
  const [err, setErr] = useState(false)
  const [busy, setBusy] = useState(false)
  const timer = useRef(null)

  const load = useCallback(async () => {
    try {
      const r = await api.get('/admin/monitoring/')
      setData(r.data)
      setErr(false)
    } catch {
      setErr(true)
    }
  }, [])

  useEffect(() => {
    load()
    timer.current = setInterval(load, REFRESH_MS)
    return () => clearInterval(timer.current)
  }, [load])

  const runBackup = async () => {
    setBusy(true)
    try {
      await api.post('/admin/backups/run/')
      setTimeout(load, 2500)
    } finally {
      setTimeout(() => setBusy(false), 2500)
    }
  }

  const g = useMemo(() => graphPaths(data?.network?.series), [data?.network?.series])

  const svcLat = (x) => {
    if (x.is_up == null) return m.no_data
    const det = (x.detail || '').toLowerCase()
    if (det === 'ok' || det.startsWith('http ')) return d(x.latency_ms ?? 0) + ' ms'
    return x.detail || (d(x.latency_ms ?? 0) + ' ms')
  }

  if (!data) {
    return (
      <div className="grid place-items-center py-16">
        {err ? <p className="text-danger text-sm">{m.fetch_fail}</p> : <Spinner />}
      </div>
    )
  }

  const { resources: rs, network: net, server: srv, targets, backups, panels } = data
  const disHigh = rs.disk.percent >= 90
  const bkStatus = (s) => m['bk_' + s] || s

  return (
    <div className="mon">
      <style>{CSS}</style>

      <div className="topbar">
        <h1>{m.title}</h1>
        <span className="status-pill">
          <i className="dot" style={{ background: data.overall === 'ok' ? 'var(--c-success)' : 'var(--c-warning)' }} />
          {d(data.up_count)} {m.of} {d(data.total_count)} {m.services_active}
        </span>
        <div className="actions">
          <span className="btn">{m.autorefresh}</span>
          <button className="btn primary" onClick={runBackup} disabled={busy}>
            {busy ? m.running : m.run_backup}
          </button>
        </div>
      </div>

      {/* ---- 4 resource cards ---- */}
      <div className="grid r4">
        <ResCard
          icon="⚡" label={m.cpu} big={d(rs.cpu.percent) + m.pct}
          sub={`${d(rs.cpu.cores)} ${m.cores} · ${d(rs.cpu.freq_ghz ?? '—')} ${m.ghz}`}
          pct={rs.cpu.percent} grad="#7C5CFF,#22D3EE"
          m1={`${m.avg} ${d(rs.cpu.avg)}${m.pct}`} m2={`${m.peak} ${d(rs.cpu.peak)}${m.pct}`}
        />
        <ResCard
          icon="▦" label={m.ram} big={d(rs.ram.percent) + m.pct}
          sub={`${d(rs.ram.used_gb)} / ${d(rs.ram.total_gb)} ${m.gb}`}
          pct={rs.ram.percent} grad="#22D3EE,#34D399"
          m1={`${m.avg} ${d(rs.ram.avg)}${m.pct}`} m2={`${m.peak} ${d(rs.ram.peak)}${m.pct}`}
        />
        <ResCard
          icon="🖴" label={m.disk} big={d(rs.disk.percent) + m.pct}
          sub={`${d(rs.disk.used_gb)} / ${d(rs.disk.total_gb)} ${m.gb}`}
          pct={rs.disk.percent} grad="#FBBF24,#F87171"
          m1={`${m.free} ${d(rs.disk.free_gb)} ${m.gb_short}`}
          m2={disHigh ? m.attention : m.healthy} m2warn={disHigh}
        />
        <div className="card bw">
          <span className="line" style={{ background: 'linear-gradient(90deg,#34D399,#22D3EE)' }} />
          <div className="card-head"><span className="ic">📶</span><span>{m.bandwidth}</span></div>
          <div className="bwvals">
            <span>↑ {B(net.up_bps)}</span>
            <span>↓ {B(net.down_bps)}</span>
          </div>
          <div className="sub">{m.iface} {net.iface}</div>
          <div className="meta">
            <span>{m.sent} {d(gb(net.sent_total))} {m.gb_short}</span>
            <span>{m.recv} {d(gb(net.recv_total))} {m.gb_short}</span>
          </div>
        </div>
      </div>

      {/* ---- service status + network graph ---- */}
      <div className="grid r2">
        <div className="card">
          <div className="title">{m.svc_status}</div>
          {targets.map((x) => (
            <div className="svc" key={x.target}>
              <span className={'badge ' + (x.is_up ? 'up' : x.is_up === false ? 'down' : 'na')}>
                {x.is_up ? m.up : x.is_up === false ? m.down : '—'}
              </span>
              <span className="name">{m['svc_' + x.target] || x.target}</span>
              <span className="lat">{svcLat(x)}</span>
            </div>
          ))}
        </div>

        <div className="card">
          <div className="speed-head">
            <div>
              <div className="title">{m.net_traffic}</div>
              <div className="sub">{m.total_iface} {net.iface}</div>
            </div>
            <div className="speed-pills">
              <span>↑ {B(net.up_bps)}</span>
              <span>↓ {B(net.down_bps)}</span>
            </div>
          </div>
          <svg className="speed-graph" viewBox="0 0 600 150" preserveAspectRatio="none">
            <defs>
              <linearGradient id="sg" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0" stopColor="#7C5CFF" stopOpacity="0.30" />
                <stop offset="1" stopColor="#7C5CFF" stopOpacity="0" />
              </linearGradient>
            </defs>
            {g.area && <path d={g.area} fill="url(#sg)" />}
            {g.line && <path d={g.line} fill="none" stroke="#7C5CFF" strokeWidth="2.5" strokeLinejoin="round" />}
            {!g.line && <text x="300" y="80" textAnchor="middle" fill="var(--c-text-muted)" fontSize="13">{m.collecting}</text>}
          </svg>
          <div className="speed-foot">
            <div><span>{m.sent_label}</span><b>{d(gb(net.sent_total))} GB</b></div>
            <div><span>{m.recv_label}</span><b>{d(gb(net.recv_total))} GB</b></div>
            <div><span>{m.sysver}</span><b>v{d(data.version)}</b></div>
          </div>
        </div>
      </div>

      {/* ---- per-panel status ---- */}
      {(panels || []).length > 0 && (
        <div className="grid r1">
          <div className="card">
            <div className="title">{m.panels}</div>
            <div className="panel-grid">
              {panels.map((p) => {
                const st = p.stats || {}
                return (
                  <div className="panel-box" key={p.id}>
                    <div className="panel-top">
                      <span className={'badge ' + (p.is_up ? 'up' : p.is_up === false ? 'down' : 'na')}>
                        {p.is_up ? m.up : p.is_up === false ? m.down : '—'}
                      </span>
                      <span className="name">{p.name}</span>
                      <span className="lat">
                        {p.latency_ms != null ? d(p.latency_ms) + ' ms' : ''}
                      </span>
                    </div>
                    <div className="panel-detail">{p.detail}</div>
                    {(st.users_total != null || st.nodes || st.cpu_usage != null) ? (
                      <div className="panel-stats">
                        {st.users_total != null && (
                          <span>{m.panel_users}: <b>{d(st.users_active ?? st.users_total)}</b>
                            {st.users_active != null ? ` / ${d(st.users_total)}` : ''}
                            {st.users_online != null ? ` · ${d(st.users_online)} ${m.panel_online}` : ''}</span>
                        )}
                        {(st.cpu_usage != null || st.mem_used != null) && (
                          <span>
                            {st.cpu_usage != null && <>{m.panel_cpu} <b>{d(Math.round(st.cpu_usage))}%</b></>}
                            {st.cpu_usage != null && st.mem_used != null ? ' · ' : ''}
                            {st.mem_used != null && st.mem_total != null &&
                              <>{m.panel_ram} <b>{fmtBytes(st.mem_used)}</b>/{fmtBytes(st.mem_total)}</>}
                          </span>
                        )}
                        {Array.isArray(st.nodes) && st.nodes.length > 0 && (
                          <span>{m.panel_nodes}: <b>{st.nodes.filter((n) => n.status === 'connected').length}</b> / {st.nodes.length}</span>
                        )}
                        {st.version && <span className="panel-detail" style={{ margin: 0 }}>v{st.version}</span>}
                      </div>
                    ) : (
                      <div className="panel-detail">{m.panel_no_stats}</div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {/* ---- backups + server IPs ---- */}
      <div className="grid r2">
        <div className="card">
          <div className="title">{m.recent_backups}</div>
          {(backups || []).length === 0 && <div className="sub">{m.no_backups}</div>}
          {(backups || []).map((b) => (
            <div className="bk" key={b.id}>
              <span className={'dotb ' + (b.status === 'ok' ? 'ok' : 'bad')} />
              <span className="fn">{b.filename}</span>
              <span className="dt">
                {d(Math.round((b.size || 0) / 1024))} {m.kb} · {bkStatus(b.status)} · {relTime(b.created_at, lang)}
              </span>
            </div>
          ))}
          <button className="btn primary full" onClick={runBackup} disabled={busy}>
            {busy ? m.running : m.run_backup_manual}
          </button>
        </div>

        <div className="card">
          <div className="title">{m.server_ips}</div>
          <div className="kv"><span className="k">{m.public_ip}</span><span className="v">{srv.public_ip || '—'}</span></div>
          <div className="kv"><span className="k">{m.local_ip}</span><span className="v">{(srv.local_ips || []).join(lang === 'fa' ? '، ' : ', ') || '—'}</span></div>
          <div className="kv"><span className="k">{m.docker_net}</span><span className="v">{(srv.docker_ips || []).join(lang === 'fa' ? '، ' : ', ') || '—'}</span></div>
          <div className="kv">
            <span className="k">{m.open_conns}</span>
            <span className="v">TCP {d(srv.tcp_open)} · UDP {d(srv.udp_open)}</span>
          </div>
        </div>
      </div>
    </div>
  )
}

function ResCard({ icon, label, big, sub, pct, grad, m1, m2, m2warn }) {
  const w = Math.max(0, Math.min(100, Math.round(pct || 0)))
  return (
    <div className="card">
      <span className="line" style={{ background: `linear-gradient(90deg,${grad})` }} />
      <div className="card-head"><span className="ic">{icon}</span><span>{label}</span></div>
      <div className="big">{big}</div>
      <div className="sub">{sub}</div>
      <div className="bar"><i style={{ width: w + '%', background: `linear-gradient(90deg,${grad})` }} /></div>
      <div className="meta">
        <span>{m1}</span>
        <span style={m2warn ? { color: 'var(--c-warning)' } : undefined}>{m2}</span>
      </div>
    </div>
  )
}

const CSS = `
.mon { max-width: 1400px; margin: 0 auto; }
.mon .topbar { display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:18px; }
.mon .topbar h1 { font-size:22px; font-weight:800; margin:0; }
.mon .status-pill { display:inline-flex; align-items:center; gap:8px; font-size:13px;
  padding:6px 12px; border-radius:999px; background:var(--c-surface); border:1px solid var(--c-border); color:var(--c-text-muted); }
.mon .status-pill .dot { width:8px; height:8px; border-radius:50%; display:inline-block; flex:0 0 auto; }
.mon .actions { margin-inline-start:auto; display:flex; gap:8px; flex-wrap:wrap; }
.mon .btn { display:inline-flex; align-items:center; gap:6px; font-size:13px; cursor:pointer;
  padding:8px 14px; border-radius:12px; background:var(--c-surface); border:1px solid var(--c-border);
  color:var(--c-text); transition:opacity .2s; white-space:nowrap; }
.mon .btn.primary { background:linear-gradient(90deg,var(--c-primary),var(--c-secondary)); border:0; color:#fff; }
.mon .btn.full { width:100%; justify-content:center; margin-top:12px; }
.mon .btn:disabled { opacity:.55; cursor:default; }

.mon .grid { display:grid; gap:16px; margin-bottom:16px; }
.mon .grid.r4 { grid-template-columns:repeat(4,minmax(0,1fr)); }
.mon .grid.r2 { grid-template-columns:1.3fr 1fr; }
.mon .grid.r1 { grid-template-columns:1fr; }
@media (max-width:1000px){ .mon .grid.r4{grid-template-columns:repeat(2,minmax(0,1fr));} .mon .grid.r2{grid-template-columns:1fr;} }

.mon .panel-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:12px; }
.mon .panel-box { border:1px solid var(--c-border); border-radius:12px; padding:12px; min-width:0; }
.mon .panel-top { display:grid; grid-template-columns:auto minmax(0,1fr) auto; align-items:center; gap:8px; }
.mon .panel-top .name { font-weight:700; font-size:13.5px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.mon .panel-top .lat { font-size:11.5px; color:var(--c-text-muted); font-variant-numeric:tabular-nums; white-space:nowrap; }
.mon .panel-detail { font-size:11.5px; color:var(--c-text-muted); margin-top:6px;
  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
.mon .panel-stats { display:flex; flex-direction:column; gap:3px; margin-top:8px; font-size:12px; color:var(--c-text-muted); }
.mon .panel-stats b { color:var(--c-text); font-variant-numeric:tabular-nums; }
@media (max-width:560px){ .mon .grid.r4{grid-template-columns:1fr;} }

.mon .card { position:relative; overflow:hidden; padding:18px; min-width:0;
  background:var(--c-surface); border:1px solid var(--c-border); border-radius:16px;
  -webkit-backdrop-filter:blur(16px); backdrop-filter:blur(16px); }
.mon .card .line, .mon .card::before { content:""; position:absolute; inset:0 0 auto 0; height:3px;
  background:linear-gradient(90deg,var(--c-primary),var(--c-secondary)); }
.mon .card .line { z-index:1; }
.mon .card-head { display:flex; align-items:center; gap:10px; color:var(--c-text-muted); font-size:14px; margin-bottom:10px; }
.mon .ic { width:26px; height:26px; display:grid; place-items:center; font-size:15px; flex:0 0 auto;
  border-radius:9px; background:rgba(124,92,255,.14); }
.mon .big { font-size:34px; font-weight:800; line-height:1.05; word-break:break-word; }
.mon .bwvals { display:flex; flex-direction:column; gap:2px; font-size:22px; font-weight:800; line-height:1.15; font-variant-numeric:tabular-nums; }
.mon .sub { color:var(--c-text-muted); font-size:12.5px; margin-top:6px; }
.mon .bar { height:7px; border-radius:999px; background:var(--c-border); margin-top:14px; overflow:hidden; }
.mon .bar i { display:block; height:100%; border-radius:999px; transition:width .5s ease; }
.mon .meta { display:flex; justify-content:space-between; gap:8px; font-size:12px; color:var(--c-text-muted); margin-top:10px; }

.mon .title { font-size:15px; font-weight:700; margin-bottom:14px; }
.mon .svc { display:grid; grid-template-columns:auto minmax(0,1fr) auto; align-items:center; gap:10px;
  padding:9px 0; border-bottom:1px solid var(--c-border); font-size:13.5px; }
.mon .svc:last-of-type { border-bottom:0; }
.mon .svc .name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.mon .badge { font-size:11px; padding:3px 9px; border-radius:999px; font-weight:600; flex:0 0 auto; white-space:nowrap; }
.mon .badge.up { background:rgba(52,211,153,.16); color:var(--c-success); }
.mon .badge.down { background:rgba(248,113,113,.16); color:var(--c-danger); }
.mon .badge.na { background:var(--c-border); color:var(--c-text-muted); }
.mon .svc .lat { color:var(--c-text-muted); font-size:12px; font-variant-numeric:tabular-nums; white-space:nowrap; }

.mon .speed-head { display:flex; justify-content:space-between; align-items:flex-start; gap:10px; margin-bottom:6px; flex-wrap:wrap; }
.mon .speed-pills { display:flex; gap:8px; }
.mon .speed-pills span { font-size:12px; padding:4px 10px; border-radius:999px; white-space:nowrap;
  background:var(--c-border); color:var(--c-text); font-variant-numeric:tabular-nums; }
.mon .speed-graph { width:100%; height:150px; display:block; margin:6px 0 4px; }
.mon .speed-foot { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin-top:8px; }
.mon .speed-foot div { display:flex; flex-direction:column; gap:3px; min-width:0; }
.mon .speed-foot span { font-size:11px; color:var(--c-text-muted); }
.mon .speed-foot b { font-size:14px; font-weight:700; word-break:break-word; }

.mon .bk { display:grid; grid-template-columns:auto minmax(0,1fr) auto; align-items:center; gap:10px;
  padding:9px 0; border-bottom:1px solid var(--c-border); font-size:13px; }
.mon .bk .dotb { width:8px; height:8px; border-radius:50%; flex:0 0 auto; }
.mon .bk .dotb.ok { background:var(--c-success); }
.mon .bk .dotb.bad { background:var(--c-danger); }
.mon .bk .fn { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.mon .bk .dt { color:var(--c-text-muted); font-size:11.5px; white-space:nowrap; text-align:end; }

.mon .kv { display:flex; justify-content:space-between; align-items:center; gap:10px;
  padding:10px 0; border-bottom:1px solid var(--c-border); font-size:13px; }
.mon .kv:last-of-type { border-bottom:0; }
.mon .kv .k { color:var(--c-text-muted); flex:0 0 auto; }
.mon .kv .v { font-variant-numeric:tabular-nums; font-weight:600; text-align:end; word-break:break-word; }
`
