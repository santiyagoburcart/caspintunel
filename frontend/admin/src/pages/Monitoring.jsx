import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useTheme } from '../theme/ThemeProvider'
import { digits as D, gb, relTime, bps } from '../lib/format'
import { Spinner } from '../components/ui'
import { Sparkline, PulseDot, PillTabs } from '../components/caspian'

const REFRESH_MS = 15000

const T = {
  fa: {
    title: 'مانیتورینگ', subtitle: 'داشبورد مانیتورینگ عملکرد شبکه و پردازشگر',
    back_to_panel: 'بازگشت به پنل', refresh_now: '↻ رفرش', online: 'آنلاین', degraded: 'اختلال',
    autorefresh: '↻ رفرش خودکار (۱۵ث)', run_backup: '↑ اجرای بک‌آپ',
    running: 'در حال اجرا…', fetch_fail: 'دریافت اطلاعات مانیتورینگ ناموفق بود.',
    services_active: 'سرویس فعال', of: 'از',
    cpu: 'CPU', ram: 'RAM', disk: 'STORAGE', swap: 'SWAP',
    cores: 'هسته', ghz: 'گیگاهرتز', gb: 'گیگابایت', gb_short: 'گیگ',
    avg: 'میانگین', peak: 'اوج', free: 'آزاد', attention: 'توجه', healthy: 'سالم', pct: '٪',
    iface: 'اینترفیس', sent: 'ارسال', recv: 'دریافت',
    svc_status: 'وضعیت سرویس‌ها', up: 'فعال', down: 'قطع', no_data: 'بدون داده', filter_all: 'همه',
    total_iface: 'مجموع اینترفیس', collecting: 'در حال جمع‌آوری داده…',
    sent_label: 'ارسال‌شده', recv_label: 'دریافت‌شده', sysver: 'نسخه سیستم',
    overall_speed: 'سرعت کلی', avg_window: 'میانگین بازه',
    conn_stats: 'وضعیت اتصالات', open_sockets: 'سوکت باز', tcp: 'TCP', udp: 'UDP',
    recent_backups: 'بک‌آپ‌های اخیر', no_backups: 'هنوز بک‌آپی ثبت نشده است.',
    run_backup_manual: '↑ اجرای بک‌آپ دستی', kb: 'کیلوبایت',
    ip_addresses: 'IP ADDRESSES', public_ip: 'IP عمومی', local_ip: 'IP لوکال',
    docker_net: 'شبکه Docker',
    show: 'نمایش', hide: 'پنهان',
    uptime: 'UPTIME', uptime_service: 'سرویس', uptime_os: 'سیستم‌عامل',
    panel_process: 'PANEL', ram_usage: 'مصرف RAM', threads: 'ریسه‌ها',
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
    title: 'Monitoring', subtitle: 'Network & server performance monitoring dashboard',
    back_to_panel: 'Back to panel', refresh_now: '↻ Refresh', online: 'Online', degraded: 'Degraded',
    autorefresh: '↻ Auto-refresh (15s)', run_backup: '↑ Run backup',
    running: 'running…', fetch_fail: 'Failed to load monitoring data.',
    services_active: 'services up', of: 'of',
    cpu: 'CPU', ram: 'RAM', disk: 'STORAGE', swap: 'SWAP',
    cores: 'cores', ghz: 'GHz', gb: 'GB', gb_short: 'GB',
    avg: 'avg', peak: 'peak', free: 'free', attention: 'attention', healthy: 'healthy', pct: '%',
    iface: 'interface', sent: 'sent', recv: 'received',
    svc_status: 'Service status', up: 'up', down: 'down', no_data: 'no data', filter_all: 'All',
    total_iface: 'total, interface', collecting: 'collecting data…',
    sent_label: 'Sent', recv_label: 'Received', sysver: 'System version',
    overall_speed: 'Overall Speed', avg_window: 'Avg over window',
    conn_stats: 'Connection Stats', open_sockets: 'open sockets', tcp: 'TCP', udp: 'UDP',
    recent_backups: 'Recent backups', no_backups: 'No backups recorded yet.',
    run_backup_manual: '↑ Run manual backup', kb: 'KB',
    ip_addresses: 'IP ADDRESSES', public_ip: 'Public IP', local_ip: 'Local IP',
    docker_net: 'Docker network',
    show: 'Show', hide: 'Hide',
    uptime: 'UPTIME', uptime_service: 'Service', uptime_os: 'OS',
    panel_process: 'PANEL', ram_usage: 'RAM usage', threads: 'Threads',
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

// Two overlaid series (TCP/UDP) sharing one scale — the shared <Sparkline>
// draws a single series, so the dual-colour connection chart (+ dashed
// grid guides, matching the reference) keeps its own small helper here.
function dualPaths(series, keyA, keyB, W, H) {
  const a = (series || []).map((s) => s[keyA] || 0)
  const b = (series || []).map((s) => s[keyB] || 0)
  if (a.length < 2) return { a: { line: '', area: '' }, b: { line: '', area: '' } }
  const max = Math.max(...a, ...b, 1)
  const step = W / (a.length - 1)
  const mk = (pts) => {
    const xy = pts.map((v, i) => [i * step, H - (v / max) * (H - 12) - 4])
    const line = xy.map(([x, y], i) => (i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1)).join(' ')
    return { line, area: `${line} L${W} ${H} L0 ${H} Z` }
  }
  return { a: mk(a), b: mk(b) }
}

function GridLines({ n, w, h }) {
  return Array.from({ length: n }).map((_, i) => {
    const y = (h / (n + 1)) * (i + 1)
    return <line key={i} x1="0" y1={y} x2={w} y2={y} stroke="var(--c-text-muted)" strokeOpacity="0.25" strokeWidth="1" strokeDasharray="4 4" />
  })
}

export default function Monitoring() {
  const { lang, setLang } = useI18n()
  const { mode, toggle, locked, styleKey, config } = useTheme()
  const isCaspian = styleKey === 'caspian'
  const m = T[lang] || T.fa
  const d = (v) => D(v, lang)
  const B = (v) => bps(v, lang)
  const brandFa = config?.site_name_fa || 'کسپین تانل'
  const brandEn = config?.site_name_en || 'Caspian Tunnel'

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
  const cg = useMemo(() => dualPaths(data?.connections?.series, 'tcp', 'udp', 400, 150), [data?.connections?.series])
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
    <div className="ip-row" key={label}>
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
    <div className={'mon' + (isCaspian ? ' mon--full' : '')}>
      <style>{CSS}</style>

      {isCaspian ? (
        /* ---- Caspian: standalone full-bleed page, no admin sidebar —
                its own header mirrors the reference _7/_11 exactly:
                status pill + divider + brand block (start) · toolbar
                with only our REAL actions (end) ---- */
        <header className="csp-header card">
          <div className="csp-header-left">
            <span className="status-pill xray">
              <PulseDot status={data.overall === 'ok' ? 'success' : 'warning'} />
              <span className="mono-num">{brandEn} · {data.overall === 'ok' ? m.online : m.degraded}</span>
              <span className="ver-badge mono-num">v{d(data.version)}</span>
            </span>
            <span className="divider" />
            <div className="brand">
              <span className="brand-icon">⚡</span>
              <div className="brand-text">
                <h1>{brandFa} <span className="brand-en mono-num">| {brandEn}</span></h1>
                <span className="brand-sub">{m.subtitle}</span>
              </div>
            </div>
          </div>
          <div className="csp-toolbar">
            <Link to="/" className="btn">↩ {m.back_to_panel}</Link>
            {!locked && <button type="button" className="btn" onClick={toggle}>{mode === 'dark' ? '☀️' : '🌙'}</button>}
            <button type="button" className="btn" onClick={() => setLang(lang === 'fa' ? 'en' : 'fa')}>{lang === 'fa' ? 'EN' : 'فا'}</button>
            <span className="btn">{m.autorefresh}</span>
            <button type="button" className="btn" onClick={load}>{m.refresh_now}</button>
            <button className="btn primary" onClick={runBackup} disabled={busy}>
              {busy ? m.running : m.run_backup}
            </button>
          </div>
        </header>
      ) : (
        <div className="topbar card">
          <div className="topbar-left">
            <span className="status-pill">
              <PulseDot status={data.overall === 'ok' ? 'success' : 'warning'} />
              <span className="mono-num">{d(data.up_count)}/{d(data.total_count)}</span> {m.services_active}
            </span>
            <span className="divider" />
            <div className="brand">
              <span className="brand-icon">⚡</span>
              <div className="brand-text">
                <h1>{m.title}</h1>
                <span className="brand-sub">{m.subtitle}</span>
              </div>
            </div>
          </div>
          <div className="actions">
            <span className="btn">{m.autorefresh}</span>
            <button className="btn primary" onClick={runBackup} disabled={busy}>
              {busy ? m.running : m.run_backup}
            </button>
          </div>
        </div>
      )}

      {/* ---- 4 resource cards: CPU / RAM / SWAP / Storage ---- */}
      <div className="grid r4">
        <ResCard
          icon="⚡" label={m.cpu} detail={`${d(rs.cpu.cores)} ${m.cores} · ${d(rs.cpu.freq_ghz ?? '—')} ${m.ghz}`}
          big={d(rs.cpu.percent)} color="var(--csp-gauge-to)" series={rs.cpu.series}
          l1={m.avg} v1={d(rs.cpu.avg) + m.pct} l2={m.peak} v2={d(rs.cpu.peak) + m.pct}
        />
        <ResCard
          icon="▦" label={m.ram} detail={`${d(rs.ram.used_gb)}/${d(rs.ram.total_gb)} ${m.gb}`}
          big={d(rs.ram.percent)} color="var(--csp-signal)" series={rs.ram.series}
          l1={m.avg} v1={d(rs.ram.avg) + m.pct} l2={m.peak} v2={d(rs.ram.peak) + m.pct}
        />
        <ResCard
          icon="⇄" label={m.swap} detail={`${d(rs.swap.used_gb)}/${d(rs.swap.total_gb)} ${m.gb}`}
          big={d(rs.swap.percent)} color="var(--c-text-muted)" series={rs.swap.series}
          l1={m.avg} v1={d(rs.swap.avg) + m.pct} l2={m.peak} v2={d(rs.swap.peak) + m.pct}
        />
        <ResCard
          icon="🖴" label={m.disk} detail={`${d(rs.disk.used_gb)}/${d(rs.disk.total_gb)} ${m.gb}`}
          big={d(rs.disk.percent)} color="var(--csp-gauge-from)" series={rs.disk.series}
          l1={m.free} v1={`${d(rs.disk.free_gb)} ${m.gb_short}`} l2={m.avg} v2={d(rs.disk.avg) + m.pct} warn2={disHigh}
        />
      </div>

      {/* ---- overall speed (2fr) + connection stats (1fr) ---- */}
      <div className="grid r2w">
        <div className="card">
          <div className="speed-head">
            <div>
              <div className="title">{m.overall_speed}</div>
              <div className="sub mono-num">{m.total_iface} {net.iface}</div>
            </div>
            <div className="speed-pills">
              <span>↑ {B(net.up_bps)}</span>
              <span>↓ {B(net.down_bps)}</span>
            </div>
          </div>
          <div className="chart-area big-chart">
            <Sparkline series={netCombined} width={900} height={210} color="var(--csp-gauge-to)" gridLines={4} />
          </div>
          <div className="speed-foot">
            <div><span>{m.sent_label}</span><b className="mono-num">{d(gb(net.sent_total))} GB</b></div>
            <div><span>{m.recv_label}</span><b className="mono-num">{d(gb(net.recv_total))} GB</b></div>
            <div><span>{m.avg_window}</span><b className="mono-num">↑ {B(netAvg.up)} ↓ {B(netAvg.down)}</b></div>
            <div><span>{m.sysver}</span><b className="mono-num">v{d(data.version)}</b></div>
          </div>
        </div>

        <div className="card">
          <div className="conn-head">
            <span className="title">{m.conn_stats}</span>
            <PulseDot status="success" />
          </div>
          <div className="conn-big">
            <span className="big mono-num">{d(cn.total)}</span>
            <span className="sub">{m.open_sockets}</span>
          </div>
          <div className="legend">
            <span><i className="dot" style={{ background: 'var(--csp-gauge-to)' }} />{m.tcp} <b className="mono-num">{d(cn.tcp)}</b></span>
            <span><i className="dot" style={{ background: 'var(--c-text-muted)' }} />{m.udp} <b className="mono-num">{d(cn.udp)}</b></span>
          </div>
          <div className="chart-area">
            <svg width="100%" height="150" viewBox="0 0 400 150" preserveAspectRatio="none" style={{ display: 'block' }}>
              <defs>
                <linearGradient id="cgA" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0" stopColor="var(--csp-gauge-to)" stopOpacity="0.35" />
                  <stop offset="1" stopColor="var(--csp-gauge-to)" stopOpacity="0" />
                </linearGradient>
              </defs>
              <GridLines n={3} w={400} h={150} />
              {cg.a.area && <path d={cg.a.area} fill="url(#cgA)" />}
              {cg.b.line && (
                <path d={cg.b.line} fill="none" stroke="var(--c-text-muted)" strokeWidth="1.6"
                  strokeLinejoin="round" strokeOpacity="0.7" />
              )}
              {cg.a.line && (
                <path d={cg.a.line} fill="none" stroke="var(--csp-gauge-to)" strokeWidth="2.2"
                  strokeLinejoin="round" strokeLinecap="round" className="csp-glow-path" />
              )}
              {!cg.a.line && <text x="200" y="80" textAnchor="middle" fill="var(--c-text-muted)" fontSize="13">{m.collecting}</text>}
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

      {/* ---- bottom strip: ONE card, 3 segments divided by a border
              (Uptime · Panel · IP addresses) — matches the reference's
              single BottomSummaryRow section, not 3 separate cards ---- */}
      <div className="grid r1">
        <div className="card strip">
          <div className="strip-grid">
            <div className="strip-seg">
              <div className="seg-head"><span className="ic">🕐</span><span className="label-mono">{m.uptime}</span></div>
              <div className="seg-cols">
                <div><span className="seg-label">{m.uptime_service}</span><span className="seg-value mono-num">{fmtDur(pr.service_uptime_s, m, d)}</span></div>
                <div><span className="seg-label">{m.uptime_os}</span><span className="seg-value mono-num accent">{fmtDur(pr.os_uptime_s, m, d)}</span></div>
              </div>
            </div>

            <div className="strip-seg">
              <div className="seg-head"><span className="ic">▦</span><span className="label-mono">{m.panel_process}</span></div>
              <div className="seg-cols">
                <div><span className="seg-label">{m.ram_usage}</span><span className="seg-value mono-num">{pr.ram_mb != null ? `${d(pr.ram_mb)} MB` : '—'}</span></div>
                <div><span className="seg-label">{m.threads}</span><span className="seg-value mono-num accent">{pr.threads != null ? d(pr.threads) : '—'}</span></div>
              </div>
            </div>

            <div className="strip-seg ip-seg">
              <div className="ip-seg-inner">
                <div className="ip-seg-content">
                  <div className="seg-head"><span className="ic">🌐</span><span className="label-mono">{m.ip_addresses}</span></div>
                  <div className="ip-list">
                    {ipRow(m.public_ip, srv.public_ip)}
                    {ipRow(m.local_ip, (srv.local_ips || []).join(lang === 'fa' ? '، ' : ', '))}
                    {ipRow(m.docker_net, (srv.docker_ips || []).join(lang === 'fa' ? '، ' : ', '))}
                  </div>
                </div>
                <button type="button" className="eye-btn" onClick={() => setShowIp((s) => !s)} title={showIp ? m.hide : m.show} aria-label={showIp ? m.hide : m.show}>
                  {showIp ? '🙈' : '👁'}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function ResCard({ icon, label, detail, big, color, series, l1, v1, l2, v2, warn2 }) {
  return (
    <div className="card rescard">
      <div className="card-head">
        <div className="card-head-left"><span className="ic">{icon}</span><span className="label-mono">{label}</span></div>
        <span className="head-detail mono-num">{detail}</span>
      </div>
      <div className="big-row">
        <span className="big mono-num">{big}</span>
        <span className="big-unit">%</span>
      </div>
      <div className="card-foot">
        <div className="avgpeak">
          <span>{l1} <b>{v1}</b></span>
          <span>{l2} <b className={warn2 ? 'warn' : 'accent'}>{v2}</b></span>
        </div>
        <div className="spark-slot">
          <Sparkline series={series} color={color} width={200} height={40} />
        </div>
      </div>
    </div>
  )
}

const CSS = `
.mon { max-width: 1400px; margin: 0 auto; }
/* Caspian: standalone full-bleed page (no admin sidebar), matching the
   reference's own p-4 md:p-6 lg:p-8 / max-w-[1720px] rhythm */
.mon.mon--full { max-width: 1720px; padding: 16px; }
@media (min-width: 768px) { .mon.mon--full { padding: 24px; } }
@media (min-width: 1024px) { .mon.mon--full { padding: 32px; } }

/* ---- header: brand block + status pill (start) · toolbar (end) ---- */
.mon .topbar, .mon .csp-header { display:flex; align-items:center; gap:16px; flex-wrap:wrap; margin-bottom:18px; padding:14px 18px; }
.mon .topbar-left, .mon .csp-header-left { display:flex; align-items:center; gap:14px; flex-wrap:wrap; }
.mon .divider { width:1px; height:20px; background:var(--c-border); }
.mon .brand { display:flex; align-items:center; gap:10px; }
.mon .brand-icon { width:32px; height:32px; border-radius:9px; display:grid; place-items:center; font-size:15px; flex:0 0 auto;
  background:linear-gradient(135deg,var(--csp-gauge-from),var(--csp-gauge-to)); color:#fff; }
.mon .brand-text { display:flex; flex-direction:column; line-height:1.3; }
.mon .brand-text h1 { font-size:15px; font-weight:800; margin:0; }
.mon .brand-en { font-weight:500; font-size:12px; color:var(--csp-gauge-to); }
.mon .brand-sub { font-size:11px; color:var(--c-text-muted); }
.mon .status-pill { display:inline-flex; align-items:center; gap:8px; font-size:12.5px;
  padding:6px 12px; border-radius:999px; background:var(--csp-muted-bg); color:var(--c-text-muted); white-space:nowrap; }
.mon .status-pill.xray { background:color-mix(in srgb, var(--c-success) 14%, transparent);
  border:1px solid color-mix(in srgb, var(--c-success) 30%, transparent); color:var(--c-success); }
.mon .ver-badge { font-size:10px; padding:2px 7px; border-radius:6px; background:color-mix(in srgb, var(--c-success) 20%, transparent); }
.mon .actions, .mon .csp-toolbar { margin-inline-start:auto; display:flex; gap:8px; flex-wrap:wrap; }
.mon .btn { display:inline-flex; align-items:center; gap:6px; font-size:13px; cursor:pointer; text-decoration:none;
  padding:8px 14px; border-radius:12px; background:var(--csp-muted-bg); border:1px solid var(--c-border);
  color:var(--c-text); transition:opacity .2s, box-shadow .2s; white-space:nowrap; }
.mon .btn.primary { background:linear-gradient(90deg,var(--csp-gauge-from),var(--csp-gauge-to)); border:0; color:#fff; }
.mon .btn.full { width:100%; justify-content:center; margin-top:12px; }
.mon .btn:disabled { opacity:.55; cursor:default; }

.mon .grid { display:grid; gap:16px; margin-bottom:16px; }
.mon .grid.r4 { grid-template-columns:repeat(4,minmax(0,1fr)); }
.mon .grid.r2w { grid-template-columns:2fr 1fr; }
.mon .grid.r1 { grid-template-columns:1fr; }
@media (max-width:1000px){ .mon .grid.r4{grid-template-columns:repeat(2,minmax(0,1fr));} .mon .grid.r2w{grid-template-columns:1fr;} }
@media (max-width:560px){ .mon .grid.r4{grid-template-columns:1fr;} }

.mon .card { position:relative; overflow:hidden; padding:18px; min-width:0; }

/* ---- resource cards: header row (icon+label / detail) · big value ·
        divider · avg-peak row · sparkline pinned to the bottom edge ---- */
.mon .rescard { display:flex; flex-direction:column; justify-content:space-between; }
.mon .card-head { display:flex; align-items:center; justify-content:space-between; gap:10px; }
.mon .card-head-left { display:flex; align-items:center; gap:8px; color:var(--csp-gauge-to); font-weight:700; }
.mon .label-mono { font-family:'JetBrains Mono',ui-monospace,monospace; font-size:12.5px; text-transform:uppercase; letter-spacing:.04em; }
.mon .head-detail { font-size:11px; color:var(--c-text-muted); white-space:nowrap; }
.mon .ic { width:22px; height:22px; display:grid; place-items:center; font-size:13px; flex:0 0 auto; }
.mon .big-row { display:flex; align-items:baseline; gap:4px; margin-top:8px; }
.mon .big-row .big { font-size:32px; font-weight:800; line-height:1; }
.mon .big-row .big-unit { font-size:16px; font-weight:600; color:var(--c-text-muted); }
.mon .card-foot { margin-top:16px; padding-top:12px; border-top:1px solid var(--c-border); }
.mon .avgpeak { display:flex; justify-content:space-between; font-size:11px; color:var(--c-text-muted); margin-bottom:8px;
  text-transform:uppercase; letter-spacing:.02em; }
.mon .avgpeak b { color:var(--c-text); text-transform:none; font-variant-numeric:tabular-nums; }
.mon .avgpeak b.accent { color:var(--csp-gauge-to); }
.mon .avgpeak b.warn { color:var(--c-warning); }
.mon .spark-slot { height:40px; margin:0 -18px -18px; }
.mon .spark-slot svg { display:block; }

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

.mon .title { font-size:13px; font-weight:700; margin-bottom:14px; text-transform:uppercase; letter-spacing:.05em;
  font-family:'JetBrains Mono',ui-monospace,monospace; }
.mon .title-row { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:14px; flex-wrap:wrap; }
.mon .svc { display:grid; grid-template-columns:auto minmax(0,1fr) auto; align-items:center; gap:10px;
  padding:9px 0; border-bottom:1px solid var(--c-border); font-size:13.5px; }
.mon .svc:last-of-type { border-bottom:0; }
.mon .svc .name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.mon .badge { font-size:11px; padding:3px 9px; border-radius:999px; font-weight:600; flex:0 0 auto; white-space:nowrap; }
.mon .badge.up { background:color-mix(in srgb, var(--c-success) 16%, transparent); color:var(--c-success); }
.mon .badge.down { background:color-mix(in srgb, var(--c-danger) 16%, transparent); color:var(--c-danger); }
.mon .badge.na { background:var(--c-border); color:var(--c-text-muted); }
.mon .svc .lat { color:var(--c-text-muted); font-size:12px; white-space:nowrap; }

/* ---- overall speed / connection stats ---- */
.mon .speed-head { display:flex; justify-content:space-between; align-items:flex-start; gap:10px; flex-wrap:wrap; }
.mon .speed-pills { display:flex; gap:8px; flex-wrap:wrap; }
.mon .speed-pills span { font-size:12px; padding:4px 10px; border-radius:999px; white-space:nowrap;
  background:var(--csp-muted-bg); color:var(--c-text); font-variant-numeric:tabular-nums; }
.mon .chart-area { margin:14px -6px 0; }
.mon .chart-area.big-chart { height:210px; }
.mon .speed-foot { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin-top:14px; padding-top:14px; border-top:1px solid var(--c-border); }
.mon .speed-foot div { display:flex; flex-direction:column; gap:3px; min-width:0; }
.mon .speed-foot span { font-size:11px; color:var(--c-text-muted); text-transform:uppercase; letter-spacing:.03em; }
.mon .speed-foot b { font-size:14px; font-weight:700; word-break:break-word; }
@media (max-width:560px){ .mon .speed-foot{grid-template-columns:repeat(2,minmax(0,1fr));} }

.mon .conn-head { display:flex; align-items:center; justify-content:space-between; }
.mon .conn-big { display:flex; align-items:baseline; gap:8px; margin-top:16px; }
.mon .conn-big .big { font-size:34px; font-weight:800; }
.mon .conn-big .sub { font-size:13px; color:var(--c-text-muted); }
.mon .legend { display:flex; gap:16px; margin-top:10px; font-size:12px; color:var(--c-text-muted); }
.mon .legend .dot { width:10px; height:3px; border-radius:2px; display:inline-block; margin-inline-end:6px; }
.mon .legend b { color:var(--c-text); font-weight:700; }

.mon .bk { display:grid; grid-template-columns:auto minmax(0,1fr) auto; align-items:center; gap:10px;
  padding:9px 0; border-bottom:1px solid var(--c-border); font-size:13px; }
.mon .bk .dotb { width:8px; height:8px; border-radius:50%; flex:0 0 auto; }
.mon .bk .dotb.ok { background:var(--c-success); }
.mon .bk .dotb.bad { background:var(--c-danger); }
.mon .bk .fn { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.mon .bk .dt { color:var(--c-text-muted); font-size:11.5px; white-space:nowrap; text-align:end; }

/* ---- bottom strip: one card, 3 segments separated by a divider ---- */
.mon .strip-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:24px; align-items:center; }
.mon .strip-seg { padding-inline-end:24px; border-inline-end:1px solid var(--c-border); }
.mon .strip-seg:last-child { border-inline-end:0; padding-inline-end:0; }
.mon .seg-head { display:flex; align-items:center; gap:8px; color:var(--c-text-muted); margin-bottom:14px; }
.mon .seg-cols { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
.mon .seg-cols > div { display:flex; flex-direction:column; gap:4px; min-width:0; }
.mon .seg-label { font-size:11px; color:var(--c-text-muted); text-transform:uppercase; letter-spacing:.03em; }
.mon .seg-value { font-size:17px; font-weight:800; }
.mon .seg-value.accent { color:var(--csp-gauge-to); }
/* IP segment: reference keeps the eye button beside the WHOLE label+list
   block (vertically centered), not inline with just the label */
.mon .ip-seg-inner { display:flex; align-items:center; justify-content:space-between; gap:14px; }
.mon .ip-seg-content { min-width:0; flex:1; }
.mon .ip-seg-content .seg-head { margin-bottom:10px; }
.mon .eye-btn { display:inline-flex; align-items:center; justify-content:center; width:28px; height:28px; cursor:pointer;
  flex:0 0 auto; border-radius:999px; background:var(--csp-muted-bg); border:0; color:var(--c-text); font-size:14px; }
.mon .ip-list { display:flex; flex-direction:column; gap:8px; }
.mon .ip-row { display:flex; align-items:center; justify-content:space-between; gap:10px; font-size:12.5px; }
.mon .ip-row .k { color:var(--c-text-muted); flex:0 0 auto; }
.mon .ip-row .v { font-weight:600; text-align:end; word-break:break-word; cursor:pointer; transition:filter .25s; }
.mon .ip-row .v.blurred { filter:blur(5px); user-select:none; }
@media (max-width:800px){
  .mon .strip-grid { grid-template-columns:1fr; gap:18px; }
  .mon .strip-seg { padding-inline-end:0; border-inline-end:0; padding-bottom:18px; border-bottom:1px solid var(--c-border); }
  .mon .strip-seg:last-child { padding-bottom:0; border-bottom:0; }
}

/* ---- Caspian dark ("Caspian Tunnel") only: recessed neomorphic wells for
   chart troughs, per DESIGN-dark-caspian-tunnel.md's Layer 2 spec — the
   light "Azure Telemetry" variant stays crisp/flat (untouched). ---- */
[data-theme-style="caspian"].dark .mon .spark-slot {
  background: var(--csp-well);
  box-shadow: inset 3px 3px 6px rgba(0, 0, 0, .8), inset -2px -2px 5px rgba(255, 255, 255, .03);
  border-bottom-left-radius: var(--csp-radius-card);
  border-bottom-right-radius: var(--csp-radius-card);
}
[data-theme-style="caspian"].dark .mon .chart-area {
  background: var(--csp-well);
  border-radius: 12px;
  box-shadow: inset 3px 3px 6px rgba(0, 0, 0, .8), inset -2px -2px 5px rgba(255, 255, 255, .03);
  margin: 14px 0 0;
  padding: 10px;
  box-sizing: border-box;
}
[data-theme-style="caspian"].dark .mon .chart-area.big-chart { height: auto; }
`
