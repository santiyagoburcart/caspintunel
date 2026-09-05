import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { digits as D, gb, relTime, bps } from '../lib/format'
import { Spinner } from '../components/ui'
import { Sparkline, PulseDot, PillTabs } from '../components/caspian'

const REFRESH_MS = 15000

const T = {
  fa: {
    title: 'مانیتورینگ', autorefresh: '↻ رفرش خودکار (۱۵ث)', run_backup: '↑ اجرای بک‌آپ',
    running: 'در حال اجرا…', fetch_fail: 'دریافت اطلاعات مانیتورینگ ناموفق بود.',
    services_active: 'سرویس فعال', of: 'از',
    cpu: 'پردازنده (CPU)', ram: 'حافظه (RAM)', disk: 'دیسک', bandwidth: 'پهنای باند',
    swap: 'سواپ (SWAP)',
    cores: 'هسته', ghz: 'گیگاهرتز', gb: 'گیگابایت', gb_short: 'گیگ',
    avg: 'میانگین', peak: 'اوج', free: 'آزاد', attention: 'توجه', healthy: 'سالم', pct: '٪',
    iface: 'اینترفیس', sent: 'ارسال', recv: 'دریافت',
    svc_status: 'وضعیت سرویس‌ها', up: 'فعال', down: 'قطع', no_data: 'بدون داده', filter_all: 'همه',
    net_traffic: 'ترافیک شبکه', total_iface: 'مجموع اینترفیس', collecting: 'در حال جمع‌آوری داده…',
    sent_label: 'ارسال‌شده', recv_label: 'دریافت‌شده', sysver: 'نسخه سیستم',
    overall_speed: 'سرعت کلی', avg_window: 'میانگین بازه',
    conn_stats: 'وضعیت اتصالات', open_sockets: 'سوکت باز', tcp: 'TCP', udp: 'UDP',
    recent_backups: 'بک‌آپ‌های اخیر', no_backups: 'هنوز بک‌آپی ثبت نشده است.',
    run_backup_manual: '↑ اجرای بک‌آپ دستی', kb: 'کیلوبایت',
    ip_addresses: 'آدرس‌های IP', public_ip: 'IP عمومی', local_ip: 'IP لوکال',
    docker_net: 'شبکه Docker',
    show: 'نمایش', hide: 'پنهان',
    uptime: 'مدت کارکرد', uptime_service: 'سرویس', uptime_os: 'سیستم‌عامل',
    panel_process: 'پردازش پنل', ram_usage: 'مصرف RAM', threads: 'ریسه‌ها',
    d_u: 'روز', h_u: 'ساعت', m_u: 'دقیقه',
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
    swap: 'Swap (SWAP)',
    cores: 'cores', ghz: 'GHz', gb: 'GB', gb_short: 'GB',
    avg: 'avg', peak: 'peak', free: 'free', attention: 'attention', healthy: 'healthy', pct: '%',
    iface: 'interface', sent: 'sent', recv: 'received',
    svc_status: 'Service status', up: 'up', down: 'down', no_data: 'no data', filter_all: 'All',
    net_traffic: 'Network traffic', total_iface: 'total, interface', collecting: 'collecting data…',
    sent_label: 'Sent', recv_label: 'Received', sysver: 'System version',
    overall_speed: 'Overall Speed', avg_window: 'Avg over window',
    conn_stats: 'Connection Stats', open_sockets: 'open sockets', tcp: 'TCP', udp: 'UDP',
    recent_backups: 'Recent backups', no_backups: 'No backups recorded yet.',
    run_backup_manual: '↑ Run manual backup', kb: 'KB',
    ip_addresses: 'IP addresses', public_ip: 'Public IP', local_ip: 'Local IP',
    docker_net: 'Docker network',
    show: 'Show', hide: 'Hide',
    uptime: 'Uptime', uptime_service: 'Service', uptime_os: 'OS',
    panel_process: 'Panel process', ram_usage: 'RAM usage', threads: 'Threads',
    d_u: 'd', h_u: 'h', m_u: 'm',
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

function fmtDur(sec, m, d) {
  if (sec == null) return '—'
  const dd = Math.floor(sec / 86400)
  const hh = Math.floor((sec % 86400) / 3600)
  const mm = Math.floor((sec % 3600) / 60)
  if (dd > 0) return `${d(dd)}${m.d_u} ${d(hh)}${m.h_u}`
  if (hh > 0) return `${d(hh)}${m.h_u} ${d(mm)}${m.m_u}`
  return `${d(mm)}${m.m_u}`
}

// Two overlaid series (TCP/UDP) sharing one scale (600x150 viewBox) — the
// shared <Sparkline> draws a single series, so the dual-colour connection
// chart keeps its own small helper here.
function dualPaths(series, keyA, keyB) {
  const a = (series || []).map((s) => s[keyA] || 0)
  const b = (series || []).map((s) => s[keyB] || 0)
  if (a.length < 2) return { a: { line: '', area: '' }, b: { line: '', area: '' } }
  const W = 600; const H = 150
  const max = Math.max(...a, ...b, 1)
  const step = W / (a.length - 1)
  const mk = (pts) => {
    const xy = pts.map((v, i) => [i * step, H - (v / max) * (H - 12) - 4])
    const line = xy.map(([x, y], i) => (i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1)).join(' ')
    return { line, area: `${line} L${W} ${H} L0 ${H} Z` }
  }
  return { a: mk(a), b: mk(b) }
}

export default function Monitoring() {
  const { lang } = useI18n()
  const m = T[lang] || T.fa
  const d = (v) => D(v, lang)
  const B = (v) => bps(v, lang)

  const [data, setData] = useState(null)
  const [err, setErr] = useState(false)
  const [busy, setBusy] = useState(false)
  const [showIp, setShowIp] = useState(false)
  const [svcFilter, setSvcFilter] = useState('all')
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

  const netCombined = useMemo(
    () => (data?.network?.series || []).map((s) => (s.up || 0) + (s.down || 0)),
    [data?.network?.series],
  )
  const cg = useMemo(() => dualPaths(data?.connections?.series, 'tcp', 'udp'), [data?.connections?.series])
  const netAvg = useMemo(() => {
    const s = data?.network?.series || []
    if (!s.length) return { up: 0, down: 0 }
    const up = s.reduce((a, x) => a + (x.up || 0), 0) / s.length
    const down = s.reduce((a, x) => a + (x.down || 0), 0) / s.length
    return { up, down }
  }, [data?.network?.series])

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

  const { resources: rs, network: net, connections: cn, process: pr, server: srv, targets, backups, panels } = data
  const disHigh = rs.disk.percent >= 90
  const bkStatus = (s) => m['bk_' + s] || s
  const filteredTargets = targets.filter((x) => (
    svcFilter === 'all' ? true : svcFilter === 'up' ? x.is_up === true : x.is_up === false
  ))
  const ipRow = (label, value) => (
    <div className="kv">
      <span className="k">{label}</span>
      <span
        className={'v mono-num' + (showIp ? '' : ' blurred')}
        onClick={() => setShowIp((s) => !s)}
        title={showIp ? m.hide : m.show}
      >
        {value || '—'}
      </span>
    </div>
  )

  return (
    <div className="mon">
      <style>{CSS}</style>

      <div className="topbar card">
        <h1 className="csp-headline">{m.title}</h1>
        <span className="status-pill">
          <PulseDot status={data.overall === 'ok' ? 'success' : 'warning'} />
          {d(data.up_count)} {m.of} {d(data.total_count)} {m.services_active}
        </span>
        <div className="actions">
          <span className="btn">{m.autorefresh}</span>
          <button className="btn primary" onClick={runBackup} disabled={busy}>
            {busy ? m.running : m.run_backup}
          </button>
        </div>
      </div>

      {/* ---- 4 resource cards: CPU / RAM / SWAP / Storage ---- */}
      <div className="grid r4">
        <ResCard
          icon="⚡" label={m.cpu} big={d(rs.cpu.percent) + m.pct}
          sub={`${d(rs.cpu.cores)} ${m.cores} · ${d(rs.cpu.freq_ghz ?? '—')} ${m.ghz}`}
          color="var(--csp-gauge-to)" series={rs.cpu.series}
          m1={`${m.avg} ${d(rs.cpu.avg)}${m.pct}`} m2={`${m.peak} ${d(rs.cpu.peak)}${m.pct}`}
        />
        <ResCard
          icon="▦" label={m.ram} big={d(rs.ram.percent) + m.pct}
          sub={`${d(rs.ram.used_gb)} / ${d(rs.ram.total_gb)} ${m.gb}`}
          color="var(--csp-signal)" series={rs.ram.series}
          m1={`${m.avg} ${d(rs.ram.avg)}${m.pct}`} m2={`${m.peak} ${d(rs.ram.peak)}${m.pct}`}
        />
        <ResCard
          icon="⇄" label={m.swap} big={d(rs.swap.percent) + m.pct}
          sub={`${d(rs.swap.used_gb)} / ${d(rs.swap.total_gb)} ${m.gb}`}
          color="var(--c-text-muted)" series={rs.swap.series}
          m1={`${m.avg} ${d(rs.swap.avg)}${m.pct}`} m2={`${m.peak} ${d(rs.swap.peak)}${m.pct}`}
        />
        <ResCard
          icon="🖴" label={m.disk} big={d(rs.disk.percent) + m.pct}
          sub={`${d(rs.disk.used_gb)} / ${d(rs.disk.total_gb)} ${m.gb}`}
          color="var(--csp-gauge-from)" series={rs.disk.series}
          m1={`${m.free} ${d(rs.disk.free_gb)} ${m.gb_short}`}
          m2={disHigh ? m.attention : m.healthy} m2warn={disHigh}
        />
      </div>

      {/* ---- overall speed (network traffic) + connection stats ---- */}
      <div className="grid r2w">
        <div className="card">
          <div className="speed-head">
            <div>
              <div className="title">{m.overall_speed}</div>
              <div className="sub">{m.total_iface} {net.iface}</div>
            </div>
            <div className="speed-pills">
              <span>↑ {B(net.up_bps)}</span>
              <span>↓ {B(net.down_bps)}</span>
            </div>
          </div>
          <Sparkline series={netCombined} width={600} height={150} color="var(--csp-gauge-to)" />
          <div className="speed-foot">
            <div><span>{m.sent_label}</span><b className="mono-num">{d(gb(net.sent_total))} GB</b></div>
            <div><span>{m.recv_label}</span><b className="mono-num">{d(gb(net.recv_total))} GB</b></div>
            <div><span>{m.avg_window}</span><b className="mono-num">↑ {B(netAvg.up)} ↓ {B(netAvg.down)}</b></div>
            <div><span>{m.sysver}</span><b className="mono-num">v{d(data.version)}</b></div>
          </div>
        </div>

        <div className="card">
          <div className="speed-head">
            <div>
              <div className="title-row" style={{ marginBottom: 0 }}>
                <span className="title" style={{ marginBottom: 0 }}>{m.conn_stats}</span>
                <PulseDot status="success" />
              </div>
              <div className="big mono-num" style={{ fontSize: 30, marginTop: 6 }}>{d(cn.total)}</div>
              <div className="sub">{m.open_sockets}</div>
            </div>
          </div>
          <div className="speed-pills" style={{ margin: '10px 0' }}>
            <span style={{ color: 'var(--csp-gauge-to)' }}>● {m.tcp} <b className="mono-num">{d(cn.tcp)}</b></span>
            <span style={{ color: 'var(--c-text-muted)' }}>● {m.udp} <b className="mono-num">{d(cn.udp)}</b></span>
          </div>
          <div className="csp-chart-well">
            <svg className="speed-graph" viewBox="0 0 600 150" preserveAspectRatio="none">
              <defs>
                <linearGradient id="cgA" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0" stopColor="var(--csp-gauge-to)" stopOpacity="0.30" />
                  <stop offset="1" stopColor="var(--csp-gauge-to)" stopOpacity="0" />
                </linearGradient>
              </defs>
              {cg.a.area && <path d={cg.a.area} fill="url(#cgA)" />}
              {cg.b.line && (
                <path d={cg.b.line} fill="none" stroke="var(--c-text-muted)" strokeWidth="1.6"
                  strokeLinejoin="round" strokeOpacity="0.7" />
              )}
              {cg.a.line && (
                <path d={cg.a.line} fill="none" stroke="var(--csp-gauge-to)" strokeWidth="2.2"
                  strokeLinejoin="round" strokeLinecap="round" />
              )}
              {!cg.a.line && <text x="300" y="80" textAnchor="middle" fill="var(--c-text-muted)" fontSize="13">{m.collecting}</text>}
            </svg>
          </div>
        </div>
      </div>

      {/* ---- service status ---- */}
      <div className="grid r1">
        <div className="card">
          <div className="title-row">
            <div className="title" style={{ marginBottom: 0 }}>{m.svc_status}</div>
            <PillTabs
              tabs={[{ value: 'all', label: m.filter_all }, { value: 'up', label: m.up }, { value: 'down', label: m.down }]}
              value={svcFilter} onChange={setSvcFilter}
            />
          </div>
          <div className="svc-grid">
            {filteredTargets.map((x) => (
              <div className="svc" key={x.target}>
                <span className={'badge ' + (x.is_up ? 'up' : x.is_up === false ? 'down' : 'na')}>
                  {x.is_up ? m.up : x.is_up === false ? m.down : '—'}
                </span>
                <span className="name">{m['svc_' + x.target] || x.target}</span>
                <span className="lat mono-num">{svcLat(x)}</span>
              </div>
            ))}
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
                      <span className="lat mono-num">
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

      {/* ---- recent backups ---- */}
      <div className="grid r1">
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
      </div>

      {/* ---- uptime / panel process / IP addresses ---- */}
      <div className="grid r3">
        <div className="card">
          <div className="title">{m.uptime}</div>
          <div className="kv"><span className="k">{m.uptime_service}</span><span className="v mono-num">{fmtDur(pr.service_uptime_s, m, d)}</span></div>
          <div className="kv"><span className="k">{m.uptime_os}</span><span className="v mono-num">{fmtDur(pr.os_uptime_s, m, d)}</span></div>
        </div>

        <div className="card">
          <div className="title">{m.panel_process}</div>
          <div className="kv"><span className="k">{m.ram_usage}</span><span className="v mono-num">{pr.ram_mb != null ? `${d(pr.ram_mb)} MB` : '—'}</span></div>
          <div className="kv"><span className="k">{m.threads}</span><span className="v mono-num">{pr.threads != null ? d(pr.threads) : '—'}</span></div>
        </div>

        <div className="card">
          <div className="title-row">
            <div className="title" style={{ marginBottom: 0 }}>{m.ip_addresses}</div>
            <button type="button" className="eye-btn" onClick={() => setShowIp((s) => !s)}>
              {showIp ? '🙈' : '👁'} {showIp ? m.hide : m.show}
            </button>
          </div>
          {ipRow(m.public_ip, srv.public_ip)}
          {ipRow(m.local_ip, (srv.local_ips || []).join(lang === 'fa' ? '، ' : ', '))}
          {ipRow(m.docker_net, (srv.docker_ips || []).join(lang === 'fa' ? '، ' : ', '))}
        </div>
      </div>
    </div>
  )
}

function ResCard({ icon, label, big, sub, color, series, m1, m2, m2warn }) {
  return (
    <div className="card">
      <span className="line" />
      <div className="card-head"><span className="ic">{icon}</span><span>{label}</span></div>
      <div className="big mono-num">{big}</div>
      <div className="sub mono-num">{sub}</div>
      <div className="meta">
        <span>{m1}</span>
        <span style={m2warn ? { color: 'var(--c-warning)' } : undefined}>{m2}</span>
      </div>
      <Sparkline series={series} color={color} />
    </div>
  )
}

const CSS = `
.mon { max-width: 1400px; margin: 0 auto; }
.mon .topbar { display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:18px; padding:14px 18px; }
.mon .topbar h1 { font-size:20px; font-weight:800; margin:0; }
.mon .status-pill { display:inline-flex; align-items:center; gap:8px; font-size:13px;
  padding:6px 12px; border-radius:999px; background:var(--csp-muted-bg); color:var(--c-text-muted); }
.mon .actions { margin-inline-start:auto; display:flex; gap:8px; flex-wrap:wrap; }
.mon .btn { display:inline-flex; align-items:center; gap:6px; font-size:13px; cursor:pointer;
  padding:8px 14px; border-radius:12px; background:var(--csp-muted-bg); border:1px solid var(--c-border);
  color:var(--c-text); transition:opacity .2s; white-space:nowrap; }
.mon .btn.primary { background:linear-gradient(90deg,var(--csp-gauge-from),var(--csp-gauge-to)); border:0; color:#fff; }
.mon .btn.full { width:100%; justify-content:center; margin-top:12px; }
.mon .btn:disabled { opacity:.55; cursor:default; }

.mon .grid { display:grid; gap:16px; margin-bottom:16px; }
.mon .grid.r4 { grid-template-columns:repeat(4,minmax(0,1fr)); }
.mon .grid.r3 { grid-template-columns:repeat(3,minmax(0,1fr)); }
.mon .grid.r2w { grid-template-columns:1.7fr 1fr; }
.mon .grid.r1 { grid-template-columns:1fr; }
@media (max-width:1000px){ .mon .grid.r4{grid-template-columns:repeat(2,minmax(0,1fr));} .mon .grid.r2w{grid-template-columns:1fr;} .mon .grid.r3{grid-template-columns:1fr;} }
@media (max-width:560px){ .mon .grid.r4{grid-template-columns:1fr;} }

.mon .svc-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); column-gap:20px; }
.mon .svc-grid .svc { border-bottom:1px solid var(--c-border); }
@media (max-width:640px){ .mon .svc-grid{grid-template-columns:1fr;} }

.mon .panel-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:12px; }
.mon .panel-box { border:1px solid var(--c-border); border-radius:12px; padding:12px; min-width:0; }
.mon .panel-top { display:grid; grid-template-columns:auto minmax(0,1fr) auto; align-items:center; gap:8px; }
.mon .panel-top .name { font-weight:700; font-size:13.5px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.mon .panel-top .lat { font-size:11.5px; color:var(--c-text-muted); white-space:nowrap; }
.mon .panel-detail { font-size:11.5px; color:var(--c-text-muted); margin-top:6px;
  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
.mon .panel-stats { display:flex; flex-direction:column; gap:3px; margin-top:8px; font-size:12px; color:var(--c-text-muted); }
.mon .panel-stats b { color:var(--c-text); font-variant-numeric:tabular-nums; }

.mon .card { position:relative; overflow:hidden; padding:18px; min-width:0; }
.mon .card .line { content:""; position:absolute; inset:0 0 auto 0; height:2px;
  background:linear-gradient(90deg,var(--csp-gauge-from),var(--csp-gauge-to)); opacity:.7; }
.mon .card-head { display:flex; align-items:center; gap:10px; color:var(--c-text-muted); font-size:13px; margin-bottom:10px;
  text-transform:uppercase; letter-spacing:.03em; font-weight:600; }
.mon .ic { width:26px; height:26px; display:grid; place-items:center; font-size:14px; flex:0 0 auto;
  border-radius:9px; background:var(--csp-muted-bg); }
.mon .big { font-size:32px; font-weight:800; line-height:1.05; word-break:break-word; }
.mon .sub { color:var(--c-text-muted); font-size:12px; margin-top:4px; }
.mon .meta { display:flex; justify-content:space-between; gap:8px; font-size:11.5px; color:var(--c-text-muted); margin-top:12px; }
.mon .meta b { color:var(--c-text); font-variant-numeric:tabular-nums; }

.mon .title { font-size:14px; font-weight:700; margin-bottom:14px; text-transform:uppercase; letter-spacing:.03em; }
.mon .title-row { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:14px; flex-wrap:wrap; }
.mon .eye-btn { display:inline-flex; align-items:center; gap:5px; font-size:11.5px; cursor:pointer;
  padding:4px 10px; border-radius:999px; background:var(--csp-muted-bg); border:0; color:var(--c-text); white-space:nowrap; }
.mon .svc { display:grid; grid-template-columns:auto minmax(0,1fr) auto; align-items:center; gap:10px;
  padding:9px 0; border-bottom:1px solid var(--c-border); font-size:13.5px; }
.mon .svc:last-of-type { border-bottom:0; }
.mon .svc .name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.mon .badge { font-size:11px; padding:3px 9px; border-radius:999px; font-weight:600; flex:0 0 auto; white-space:nowrap; }
.mon .badge.up { background:color-mix(in srgb, var(--c-success) 16%, transparent); color:var(--c-success); }
.mon .badge.down { background:color-mix(in srgb, var(--c-danger) 16%, transparent); color:var(--c-danger); }
.mon .badge.na { background:var(--c-border); color:var(--c-text-muted); }
.mon .svc .lat { color:var(--c-text-muted); font-size:12px; white-space:nowrap; }

.mon .speed-head { display:flex; justify-content:space-between; align-items:flex-start; gap:10px; margin-bottom:10px; flex-wrap:wrap; }
.mon .speed-pills { display:flex; gap:8px; flex-wrap:wrap; }
.mon .speed-pills span { font-size:12px; padding:4px 10px; border-radius:999px; white-space:nowrap;
  background:var(--csp-muted-bg); color:var(--c-text); font-variant-numeric:tabular-nums; }
.mon .speed-graph { width:100%; height:150px; display:block; }
.mon .speed-foot { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin-top:14px; padding-top:14px; border-top:1px solid var(--c-border); }
.mon .speed-foot div { display:flex; flex-direction:column; gap:3px; min-width:0; }
.mon .speed-foot span { font-size:11px; color:var(--c-text-muted); text-transform:uppercase; letter-spacing:.03em; }
.mon .speed-foot b { font-size:14px; font-weight:700; word-break:break-word; }
@media (max-width:560px){ .mon .speed-foot{grid-template-columns:repeat(2,minmax(0,1fr));} }

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
.mon .kv .v { font-weight:600; text-align:end; word-break:break-word; cursor:pointer; transition:filter .25s; }
.mon .kv .v.blurred { filter:blur(5px); user-select:none; }
`
