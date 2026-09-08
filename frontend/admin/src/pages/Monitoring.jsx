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
  const { styleKey } = useTheme()
  // Caspian ships a faithful port of the Stitch reference screens
  // (_7.html dark / _11.html light) — its own self-contained markup + CSS,
  // pinned to the reference's literal values (NOT the project design tokens).
  // Midnight Aurora / Royal Frost keep the original dashboard untouched.
  return styleKey === 'caspian' ? <CaspianMonitoring /> : <LegacyMonitoring />
}

function LegacyMonitoring() {
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

/* ==================================================================== *
 *  CaspianMonitoring — a faithful port of the Stitch reference screens  *
 *  _7.html ("Caspian Tunnel", dark) and _11.html ("Azure Telemetry",   *
 *  light). Everything below is pinned to the reference files' OWN       *
 *  embedded values (sky-blue `brand` scale on #070C14 for dark; the    *
 *  Material-3 blue set on #faf8ff for light) — the project's Caspian    *
 *  design tokens (--c-* / --csp-*) are deliberately NOT used here.      *
 *  Self-contained: its own `.cm` class tree + <style>, so Midnight      *
 *  Aurora / Royal Frost monitoring is completely untouched.            *
 * ==================================================================== */

const CT = {
  fa: {
    subtitle: 'داشبورد مانیتورینگ عملکرد شبکه و پردازشگر',
    back: 'بازگشت به پنل', online: 'برقرار', degraded: 'اختلال', live: 'زنده',
    auto_on: 'رفرش خودکار: روشن', auto_off: 'رفرش خودکار: خاموش', refresh: 'رفرش',
    run_backup: 'اجرای بک‌آپ', running: 'در حال اجرا…', fetch_fail: 'دریافت اطلاعات مانیتورینگ ناموفق بود.',
    cpu_fa: '(پردازنده)', ram_fa: '(حافظه اصلی)', swap_fa: '(سواپ)', storage_fa: '(دیسک)',
    cores: 'هسته', avg: 'میانگین', peak: 'پیک مصرف', free: 'فضای آزاد', gb: 'GB',
    active_use: 'مصرف فعال', gb_free: 'گیگ آزاد', root_fs: 'NVMe Root FS', flat: 'بدون فعالیت',
    overall_speed: 'OVERALL SPEED', overall_speed_fa: '(سرعت کلی پهنای‌باند)',
    iface_total: 'مجموع اینترفیس · پیک', upload: 'آپلود', download: 'دانلود',
    sent: 'ترافیک ارسالی (SENT)', received: 'ترافیک دریافتی (RECEIVED)', avg_window: 'میانگین بازه زنده',
    conn_stats: 'CONNECTION STATS', conn_stats_fa: 'وضعیت اتصالات فعال و سوکت‌ها',
    open_sockets: 'سوکت باز (open sockets)', tcp: 'TCP', udp: 'UDP',
    ago60: '−۶۰ دقیقه', stable: 'اتصالات پایدار', now: 'اکنون',
    svc_status: 'وضعیت سرویس‌ها', svc_status_fa: '(سلامت زیرساخت)',
    f_all: 'همه', f_up: 'برقرار', f_down: 'قطع', up: 'برقرار', down: 'قطع', nodata: 'بدون داده',
    panels: 'وضعیت پنل‌ها', p_users: 'کاربران', p_online: 'آنلاین', p_nodes: 'نودها',
    p_cpu: 'CPU', p_ram: 'RAM', p_nostats: 'آمار در دسترس نیست',
    backups: 'بک‌آپ‌های اخیر', backups_fa: '(پشتیبان‌گیری پایگاه‌داده)', no_backups: 'هنوز بک‌آپی ثبت نشده است.',
    run_backup_now: 'اجرای بک‌آپ دستی', kb: 'کیلوبایت',
    uptime: 'UPTIME', uptime_fa: '(مدت زمان فعالیت)', u_service: 'سرویس هسته', u_os: 'سیستم‌عامل',
    panel_res: 'PANEL RESOURCES', panel_res_fa: '(مصرف پنل)', ram_alloc: 'حافظهٔ تخصیص‌یافته', threads: 'تِرِدهای فعال',
    ips: 'IP ADDRESSES', ips_fa: '(نشانی شبکه)', ip_public: 'عمومی', ip_local: 'داخلی', ip_docker: 'شبکهٔ Docker',
    show: 'نمایش', hide: 'پنهان',
    svc_site: 'سایت (Web)', svc_mysql: 'دیتابیس (MySQL)', svc_redis: 'ردیس (Redis)',
    svc_celery_worker: 'Celery Worker', svc_celery_beat: 'Celery Beat',
    svc_bot_sales: 'ربات فروش', svc_bot_backup: 'ربات بک‌آپ', svc_panel: 'پنل‌ها (مجموع)', svc_mail: 'میل‌سرور (SMTP)',
    d_u: 'روز', h_u: 'ساعت', m_u: 'دقیقه',
    bk_ok: 'موفق', bk_failed: 'ناموفق', bk_partial: 'ناقص', bk_running: 'در حال اجرا',
  },
  en: {
    subtitle: 'Network & processor performance monitoring',
    back: 'Back to panel', online: 'Online', degraded: 'Degraded', live: 'LIVE',
    auto_on: 'Auto-refresh: on', auto_off: 'Auto-refresh: off', refresh: 'Refresh',
    run_backup: 'Run backup', running: 'running…', fetch_fail: 'Failed to load monitoring data.',
    cpu_fa: '(processor)', ram_fa: '(main memory)', swap_fa: '(swap)', storage_fa: '(disk)',
    cores: 'cores', avg: 'avg', peak: 'peak', free: 'free', gb: 'GB',
    active_use: 'active use', gb_free: 'GB free', root_fs: 'NVMe Root FS', flat: 'no activity',
    overall_speed: 'OVERALL SPEED', overall_speed_fa: '(total bandwidth)',
    iface_total: 'Interface total · peak', upload: 'Upload', download: 'Download',
    sent: 'SENT', received: 'RECEIVED', avg_window: 'AVG OVER WINDOW',
    conn_stats: 'CONNECTION STATS', conn_stats_fa: 'Active connections & sockets',
    open_sockets: 'open sockets', tcp: 'TCP', udp: 'UDP',
    ago60: '−60 min', stable: 'Stable handshakes', now: 'Now',
    svc_status: 'SERVICE STATUS', svc_status_fa: '(infrastructure health)',
    f_all: 'All', f_up: 'Up', f_down: 'Down', up: 'up', down: 'down', nodata: 'no data',
    panels: 'PANEL STATUS', p_users: 'users', p_online: 'online', p_nodes: 'nodes',
    p_cpu: 'CPU', p_ram: 'RAM', p_nostats: 'stats unavailable',
    backups: 'RECENT BACKUPS', backups_fa: '(database backups)', no_backups: 'No backups recorded yet.',
    run_backup_now: 'Run manual backup', kb: 'KB',
    uptime: 'UPTIME', uptime_fa: '(time since start)', u_service: 'Core service', u_os: 'Operating system',
    panel_res: 'PANEL RESOURCES', panel_res_fa: '(panel footprint)', ram_alloc: 'RAM allocated', threads: 'Active threads',
    ips: 'IP ADDRESSES', ips_fa: '(network addresses)', ip_public: 'Public', ip_local: 'Local', ip_docker: 'Docker network',
    show: 'Show', hide: 'Hide',
    svc_site: 'Website (Web)', svc_mysql: 'Database (MySQL)', svc_redis: 'Redis',
    svc_celery_worker: 'Celery Worker', svc_celery_beat: 'Celery Beat',
    svc_bot_sales: 'Sales bot', svc_bot_backup: 'Backup bot', svc_panel: 'Panels (overall)', svc_mail: 'Mail server (SMTP)',
    d_u: 'd', h_u: 'h', m_u: 'm',
    bk_ok: 'success', bk_failed: 'failed', bk_partial: 'partial', bk_running: 'running',
  },
}

// tiny stroke-icon set — the `d` paths are lifted straight from _7.html so
// the dark variant's iconography matches the reference exactly.
const ICO = {
  cpu: 'M9 3v2m6-2v2M9 19v2m6-2v2M3 9h2m-2 6h2m16-6h2m-2 6h2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z',
  ram: 'M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10',
  swap: 'M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4',
  storage: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4',
  clock: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z',
  chip: 'M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2',
  globe: 'M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9',
  refresh: 'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15',
  bolt: 'M13 10V3L4 14h7v7l9-11h-7z',
  backup: 'M8 4H6a2 2 0 00-2 2v12a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-2m-4-1v8m0 0l3-3m-3 3L9 8',
  eye: 'M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z',
  eyeoff: 'M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18',
  sun: 'M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z',
  moon: 'M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z',
}

function Ico({ d, size = 16, w = 2 }) {
  return (
    <svg className="cm-ico" style={{ width: size, height: size }} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={w} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {d.split(' M').map((seg, i) => <path key={i} d={(i ? 'M' : '') + seg} />)}
    </svg>
  )
}

// line + area path for any viewBox, from a plain numeric series (bound to
// real /admin/monitoring/ data — the reference's static demo paths can't be
// reproduced, but stroke widths / gradients / grid guides below match it).
function cmPath(vals, w, h, pad = 4) {
  const pts = (vals || []).filter((v) => typeof v === 'number')
  if (pts.length < 2) return { line: '', area: '' }
  const max = Math.max(...pts, 1)
  const step = w / (pts.length - 1)
  const xy = pts.map((v, i) => [i * step, h - pad - (v / max) * (h - pad * 2)])
  const line = xy.map(([x, y], i) => (i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1)).join(' ')
  return { line, area: `${line} L${w} ${h} L0 ${h} Z` }
}

function CmGrid({ n, w, h }) {
  return Array.from({ length: n }).map((_, i) => {
    const y = (h / (n + 1)) * (i + 1)
    return <line key={i} x1="0" y1={y} x2={w} y2={y} stroke="var(--cm-dim)" strokeOpacity="0.2"
      strokeWidth="1" strokeDasharray="4 4" />
  })
}

function CmMetric({ isDark, ico, label, labelFa, badge, detail, value, unit, a1, v1, a2, v2, hot2, viz }) {
  return (
    <div className="cm-card cm-metric">
      <div>
        <div className="cm-m-head">
          <span className="cm-m-head-l"><Ico d={ico} /><span className="cm-m-label">{label}</span>
            {isDark && labelFa && <span className="cm-m-label-fa">{labelFa}</span>}</span>
          {isDark
            ? <span className="cm-m-badge">{badge}</span>
            : <span className="cm-m-detail">{detail}</span>}
        </div>
        <div className="cm-m-value"><span className="n mono-num">{value}</span><span className="u">{unit}</span></div>
        {isDark && <p className="cm-m-sub mono-num">{detail}</p>}
      </div>
      <div className="cm-m-foot">
        <div className="cm-avgpeak">
          <span>{a1}{isDark ? ' ' : ': '}<strong className="mono-num">{v1}</strong></span>
          <span>{a2}{isDark ? ' ' : ': '}<strong className={'mono-num' + (hot2 ? ' hot' : '')}>{v2}</strong></span>
        </div>
        {viz}
      </div>
    </div>
  )
}

function CaspianMonitoring() {
  const { lang } = useI18n()
  const { mode, config } = useTheme()
  const isDark = mode === 'dark'
  const m = CT[lang] || CT.fa
  const d = (v) => D(v, lang)
  const B = (v) => bps(v, lang)
  const brandEn = config?.site_name_en || 'Caspian Tunnel'

  const [data, setData] = useState(null)
  const [err, setErr] = useState(false)
  const [busy, setBusy] = useState(false)
  const [auto, setAuto] = useState(true)
  const [showIp, setShowIp] = useState(false)
  const [svcFilter, setSvcFilter] = useState('all')
  const timer = useRef(null)

  const load = useCallback(async () => {
    try {
      const r = await api.get('/admin/monitoring/')
      setData(r.data); setErr(false)
    } catch { setErr(true) }
  }, [])

  useEffect(() => {
    load()
    if (auto) { timer.current = setInterval(load, REFRESH_MS); return () => clearInterval(timer.current) }
  }, [load, auto])

  const runBackup = async () => {
    setBusy(true)
    try { await api.post('/admin/backups/run/'); setTimeout(load, 2500) }
    finally { setTimeout(() => setBusy(false), 2500) }
  }

  const netSeries = useMemo(
    () => (data?.network?.series || []).map((s) => (s.up || 0) + (s.down || 0)),
    [data?.network?.series],
  )
  const netAvg = useMemo(() => {
    const s = data?.network?.series || []
    if (!s.length) return { up: 0, down: 0 }
    return {
      up: s.reduce((a, x) => a + (x.up || 0), 0) / s.length,
      down: s.reduce((a, x) => a + (x.down || 0), 0) / s.length,
    }
  }, [data?.network?.series])

  const svcLat = (x) => {
    if (x.is_up == null) return m.nodata
    const det = (x.detail || '').toLowerCase()
    if (det === 'ok' || det.startsWith('http ')) return d(x.latency_ms ?? 0) + ' ms'
    return x.detail || (d(x.latency_ms ?? 0) + ' ms')
  }
  // the reference (_7 / _11) uses Latin "5d 20h" suffixes in both languages —
  // keeping them also avoids RTL bidi mangling the number/unit order
  const dur = (sec) => {
    if (sec == null) return '—'
    const dd = Math.floor(sec / 86400), hh = Math.floor((sec % 86400) / 3600), mm = Math.floor((sec % 3600) / 60)
    if (dd > 0) return `${d(dd)}d ${d(hh)}h`
    if (hh > 0) return `${d(hh)}h ${d(mm)}m`
    return `${d(mm)}m`
  }

  if (!data) {
    return (
      <div className={'cm' + (isDark ? ' cm-dark' : '')}>
        <style>{CM_CSS}</style>
        <div className="cm-wrap"><div className="cm-loading">
          {err ? <p className="cm-err">{m.fetch_fail}</p> : <Spinner />}
        </div></div>
      </div>
    )
  }

  const { resources: rs, network: net, process: pr, server: srv, targets, backups, panels } = data
  const bkLabel = (s) => m['bk_' + s] || s
  const filtered = targets.filter((x) => (
    svcFilter === 'all' ? true : svcFilter === 'up' ? x.is_up === true : x.is_up === false
  ))
  const spd = cmPath(netSeries, 900, 240, 8)

  // ---- metric-card footer visualisations (per-variant, matching _7 / _11) ----
  const spark = (series, color) => {
    const p = cmPath(series, 200, isDark ? 40 : 48, 3)
    return (
      <svg className="cm-spark" viewBox={`0 0 200 ${isDark ? 40 : 48}`} preserveAspectRatio="none">
        {p.area && <path d={p.area} fill={color} fillOpacity={isDark ? 0.18 : 0.08} />}
        {p.line && <path className="cm-glow" d={p.line} fill="none" stroke={color} strokeWidth="2"
          strokeLinecap="round" strokeLinejoin="round" />}
      </svg>
    )
  }
  const vbar = (pct) => (                  // _7 dark: vertical gradient fill well
    <div className="cm-vbar"><i style={{ height: `${Math.max(pct, 0)}%` }} /></div>
  )
  const hbar = (pct, from, to, lA, lB) => ( // _11 light: horizontal gauge + labels
    <div className="cm-hbar-wrap">
      <div className="cm-hbar"><i style={{ width: `${Math.max(pct, 0)}%`, background: `linear-gradient(to right, ${from}, ${to})` }} /></div>
      <div className="cm-hbar-labels"><span>{lA}</span><span>{lB}</span></div>
    </div>
  )
  const flat = () => isDark
    ? <div className="cm-vbar"><i className="cm-flat" /></div>
    : <div className="cm-hbar cm-hbar--thin"><i style={{ width: 0 }} /></div>

  const accent = 'var(--cm-accent)'

  const cpuViz = spark(rs.cpu.series, accent)
  const ramViz = isDark
    ? vbar(rs.ram.percent)
    : hbar(rs.ram.percent, 'var(--cm-accent-2)', 'var(--cm-accent)', m.active_use, `${d(Math.max(rs.ram.total_gb - rs.ram.used_gb, 0).toFixed(1))} ${m.gb} ${m.free}`)
  const swapViz = flat()
  const diskViz = isDark
    ? vbar(rs.disk.percent)
    : hbar(rs.disk.percent, 'var(--cm-accent-soft)', 'var(--cm-accent)', m.root_fs, `${d(100 - Math.round(rs.disk.percent))}${T[lang].pct} ${m.free}`)

  return (
    <div className={'cm' + (isDark ? ' cm-dark' : '')} dir={lang === 'fa' ? 'rtl' : 'ltr'}>
      <style>{CM_CSS}</style>
      <div className="cm-wrap">

        {/* ================= HEADER ================= */}
        <header className="cm-card cm-header">
          <div className="cm-header-l">
            <span className={'cm-pill' + (data.overall === 'ok' ? '' : ' cm-pill-warn')}>
              <span className="cm-ping" />
              <span className="mono-num">{brandEn} · {data.overall === 'ok' ? m.online : m.degraded}</span>
              <span className="cm-pill-ver mono-num">v{d(data.version)}</span>
            </span>
          </div>
          <div className="cm-toolbar">
            <button type="button" className={'cm-btn' + (auto ? ' on' : '')} onClick={() => setAuto((a) => !a)}>
              <span className={'cm-auto-dot' + (auto ? ' live' : '')} />{auto ? m.auto_on : m.auto_off}
            </button>
            <button type="button" className="cm-btn cm-btn-icon" onClick={load} title={m.refresh}>
              <Ico d={ICO.refresh} size={15} />
            </button>
            <button type="button" className="cm-btn cm-btn-green" onClick={runBackup} disabled={busy}>
              <Ico d={ICO.backup} size={15} />{busy ? m.running : m.run_backup}
            </button>
          </div>
        </header>

        {/* ================= 4 METRIC CARDS ================= */}
        <section className="cm-grid cm-r4">
          <CmMetric isDark={isDark} ico={ICO.cpu} label="CPU" labelFa={m.cpu_fa} badge="LIVE"
            detail={`${d(rs.cpu.cores)} ${m.cores} · ${d(rs.cpu.freq_ghz ?? '—')} GHz`}
            value={d(rs.cpu.percent)} unit="%"
            a1={m.avg} v1={d(rs.cpu.avg) + '%'} a2={m.peak} v2={d(rs.cpu.peak) + '%'} hot2 viz={cpuViz} />
          <CmMetric isDark={isDark} ico={ICO.ram} label="RAM" labelFa={m.ram_fa} badge="MEM"
            detail={`${d(rs.ram.used_gb)} / ${d(rs.ram.total_gb)} ${m.gb}`}
            value={d(rs.ram.percent)} unit="%"
            a1={m.avg} v1={d(rs.ram.avg) + '%'} a2={m.peak} v2={d(rs.ram.peak) + '%'} hot2 viz={ramViz} />
          <CmMetric isDark={isDark} ico={ICO.swap} label="SWAP" labelFa={m.swap_fa} badge="0% ACTIVE"
            detail={`${d(rs.swap.used_gb)} / ${d(rs.swap.total_gb)} ${m.gb}`}
            value={d(rs.swap.percent)} unit="%"
            a1={m.avg} v1={d(rs.swap.avg) + '%'} a2={m.peak} v2={d(rs.swap.peak) + '%'} viz={swapViz} />
          <CmMetric isDark={isDark} ico={ICO.storage} label="STORAGE" labelFa={m.storage_fa} badge="NVMe"
            detail={`${d(rs.disk.used_gb)} / ${d(rs.disk.total_gb)} ${m.gb}`}
            value={d(rs.disk.percent)} unit="%"
            a1={m.free} v1={`${d(rs.disk.free_gb)} ${m.gb}`} a2={m.avg} v2={d(rs.disk.avg) + '%'} hot2 viz={diskViz} />
        </section>

        {/* ================= OVERALL SPEED (full width) ================= */}
        <section className="cm-card cm-card-lg">
          <div className="cm-speed-head">
            <div>
              <div className="cm-h2-row"><h2 className="cm-h2">{m.overall_speed}</h2>
                <span className="cm-h2-fa">{m.overall_speed_fa}</span></div>
              <p className="cm-h2-sub mono-num">{m.iface_total} {net.iface}</p>
            </div>
            <div className="cm-speed-pills">
              <span className="cm-pill-up"><b>↑</b> <span className="cm-pill-k">{m.upload}</span> <b className="cm-pill-v mono-num">{B(net.up_bps)}</b></span>
              <span className="cm-pill-dn"><b>↓</b> <span className="cm-pill-k">{m.download}</span> <b className="cm-pill-v mono-num">{B(net.down_bps)}</b></span>
            </div>
          </div>
          <div className="cm-chart cm-chart-lg">
            <svg viewBox="0 0 900 240" preserveAspectRatio="none">
              <defs>
                <linearGradient id="cmSpeed" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="var(--cm-accent)" stopOpacity={isDark ? 0.38 : 0.25} />
                  <stop offset="60%" stopColor="var(--cm-accent-2)" stopOpacity={isDark ? 0.12 : 0.05} />
                  <stop offset="100%" stopColor="var(--cm-accent)" stopOpacity="0" />
                </linearGradient>
              </defs>
              <CmGrid n={4} w={900} h={240} />
              <line x1="0" x2="900" y1="168" y2="168" stroke="var(--cm-accent)" strokeDasharray="4 4" strokeOpacity="0.4" strokeWidth="1.2" />
              {spd.area && <path d={spd.area} fill="url(#cmSpeed)" />}
              {spd.line && <path className="cm-glow" d={spd.line} fill="none" stroke="var(--cm-accent)"
                strokeWidth={isDark ? 2.2 : 2.5} strokeLinecap="round" strokeLinejoin="round" />}
              {!spd.line && <text x="450" y="120" textAnchor="middle" fill="var(--cm-dim)" fontSize="13">…</text>}
            </svg>
          </div>
          <div className="cm-speed-foot">
            <div><span>{m.sent}</span><b className="mono-num">{d(gb(net.sent_total))} <i>{m.gb}</i></b></div>
            <div><span>{m.received}</span><b className="mono-num">{d(gb(net.recv_total))} <i>{m.gb}</i></b></div>
            <div><span>{m.avg_window}</span><b className="mono-num cm-aw"><span className="up">↑ {B(netAvg.up)}</span> <span className="dn">↓ {B(netAvg.down)}</span></b></div>
          </div>
        </section>

        {/* ================= SERVICE HEALTH (our 9 targets — not in the ref) ================= */}
        <section className="cm-card">
          <div className="cm-sec-head">
            <div className="cm-h2-row"><h2 className="cm-h2">{m.svc_status}</h2><span className="cm-h2-fa">{m.svc_status_fa}</span></div>
            <div className="cm-filter">
              {[['all', m.f_all], ['up', m.f_up], ['down', m.f_down]].map(([v, l]) => (
                <button key={v} type="button" className={'cm-chip' + (svcFilter === v ? ' on' : '')} onClick={() => setSvcFilter(v)}>{l}</button>
              ))}
            </div>
          </div>
          <div className="cm-svc-grid">
            {filtered.map((x) => (
              <div className="cm-svc" key={x.target}>
                <span className={'cm-dot ' + (x.is_up ? 'up' : x.is_up === false ? 'down' : 'na')} />
                <span className="name">{m['svc_' + x.target] || x.target}</span>
                <span className="lat mono-num">{svcLat(x)}</span>
              </div>
            ))}
          </div>
        </section>

        {/* ================= PER-PANEL STATUS ================= */}
        {(panels || []).length > 0 && (
          <section className="cm-card">
            <div className="cm-h2-row"><h2 className="cm-h2">{m.panels}</h2></div>
            <div className="cm-panel-grid">
              {panels.map((p) => {
                const st = p.stats || {}
                return (
                  <div className="cm-panel" key={p.id}>
                    <div className="cm-panel-top">
                      <span className={'cm-dot ' + (p.is_up ? 'up' : p.is_up === false ? 'down' : 'na')} />
                      <span className="name">{p.name}</span>
                      <span className="lat mono-num">{p.latency_ms != null ? d(p.latency_ms) + ' ms' : ''}</span>
                    </div>
                    {(st.users_total != null || st.cpu_usage != null || Array.isArray(st.nodes)) ? (
                      <div className="cm-panel-stats">
                        {st.users_total != null && (
                          <span>{m.p_users}: <b>{d(st.users_active ?? st.users_total)}</b>
                            {st.users_online != null ? ` · ${d(st.users_online)} ${m.p_online}` : ''}</span>
                        )}
                        {st.cpu_usage != null && (
                          <span>{m.p_cpu} <b>{d(Math.round(st.cpu_usage))}%</b>
                            {st.mem_used != null && st.mem_total != null ? ` · ${m.p_ram} ${fmtBytes(st.mem_used)}/${fmtBytes(st.mem_total)}` : ''}</span>
                        )}
                        {Array.isArray(st.nodes) && st.nodes.length > 0 && (
                          <span>{m.p_nodes}: <b>{st.nodes.filter((n) => n.status === 'connected').length}</b> / {st.nodes.length}</span>
                        )}
                      </div>
                    ) : <div className="cm-panel-detail">{p.detail || m.p_nostats}</div>}
                  </div>
                )
              })}
            </div>
          </section>
        )}

        {/* ================= UPTIME · PANEL RESOURCES · IP ADDRESSES ================= */}
        {isDark ? (
          /* _7: ONE card, 3 segments divided by inner borders */
          <section className="cm-card cm-strip">
            <div className="cm-strip-grid">
              <div className="cm-seg">
                <div className="cm-seg-head"><Ico d={ICO.clock} /><span className="cm-seg-title">{m.uptime}</span><span className="cm-seg-fa">{m.uptime_fa}</span></div>
                <div className="cm-seg-cols">
                  <div><span className="k">{m.u_service}</span><span className="v mono-num">{dur(pr.service_uptime_s)}</span></div>
                  <div><span className="k">{m.u_os}</span><span className="v mono-num hot">{dur(pr.os_uptime_s)}</span></div>
                </div>
              </div>
              <div className="cm-seg">
                <div className="cm-seg-head"><Ico d={ICO.chip} /><span className="cm-seg-title">{m.panel_res}</span><span className="cm-seg-fa">{m.panel_res_fa}</span></div>
                <div className="cm-seg-cols">
                  <div><span className="k">{m.ram_alloc}</span><span className="v mono-num">{pr.ram_mb != null ? `${d(pr.ram_mb)} MB` : '—'}</span></div>
                  <div><span className="k">{m.threads}</span><span className="v mono-num hot">{pr.threads != null ? d(pr.threads) : '—'}</span></div>
                </div>
              </div>
              <div className="cm-seg cm-seg-ip">
                <div className="cm-seg-ip-row">
                  <div className="cm-seg-ip-body">
                    <div className="cm-seg-head"><Ico d={ICO.globe} /><span className="cm-seg-title">{m.ips}</span><span className="cm-seg-fa">{m.ips_fa}</span></div>
                    <CmIpList m={m} srv={srv} showIp={showIp} onToggle={() => setShowIp((s) => !s)} lang={lang} />
                  </div>
                  <button type="button" className="cm-eye" onClick={() => setShowIp((s) => !s)} title={showIp ? m.hide : m.show}>
                    <Ico d={showIp ? ICO.eye : ICO.eyeoff} size={18} />
                  </button>
                </div>
              </div>
            </div>
          </section>
        ) : (
          /* _11: 3 SEPARATE cards */
          <section className="cm-grid cm-r3">
            <div className="cm-card">
              <div className="cm-seg-head"><Ico d={ICO.clock} /><span className="cm-seg-title">{m.uptime}</span><span className="cm-seg-fa">{m.uptime_fa}</span></div>
              <div className="cm-seg-cols cm-seg-cols--row">
                <div><span className="k">{m.u_service}</span><span className="v mono-num">{dur(pr.service_uptime_s)}</span></div>
                <span className="cm-seg-vdiv" />
                <div><span className="k">{m.u_os}</span><span className="v mono-num">{dur(pr.os_uptime_s)}</span></div>
              </div>
            </div>
            <div className="cm-card">
              <div className="cm-seg-head"><Ico d={ICO.chip} /><span className="cm-seg-title">{m.panel_res}</span><span className="cm-seg-fa">{m.panel_res_fa}</span></div>
              <div className="cm-seg-cols cm-seg-cols--row">
                <div><span className="k">{m.ram_alloc}</span><span className="v mono-num">{pr.ram_mb != null ? `${d(pr.ram_mb)} MB` : '—'}</span></div>
                <span className="cm-seg-vdiv" />
                <div><span className="k">{m.threads}</span><span className="v mono-num">{pr.threads != null ? d(pr.threads) : '—'}</span></div>
              </div>
            </div>
            <div className="cm-card">
              <div className="cm-seg-head cm-seg-head--sb">
                <span><Ico d={ICO.globe} /><span className="cm-seg-title">{m.ips}</span><span className="cm-seg-fa">{m.ips_fa}</span></span>
                <button type="button" className="cm-eye-inline" onClick={() => setShowIp((s) => !s)} title={showIp ? m.hide : m.show}>
                  <Ico d={showIp ? ICO.eye : ICO.eyeoff} size={16} />
                </button>
              </div>
              <CmIpList m={m} srv={srv} showIp={showIp} onToggle={() => setShowIp((s) => !s)} lang={lang} />
            </div>
          </section>
        )}

        {/* ================= RECENT BACKUPS (last) ================= */}
        <section className="cm-card">
          <div className="cm-h2-row"><h2 className="cm-h2">{m.backups}</h2><span className="cm-h2-fa">{m.backups_fa}</span></div>
          {(backups || []).length === 0 && <div className="cm-panel-detail">{m.no_backups}</div>}
          {(backups || []).map((b) => (
            <div className="cm-bk" key={b.id}>
              <span className={'cm-dot ' + (b.status === 'ok' ? 'up' : b.status === 'running' ? 'na' : 'down')} />
              <span className="fn">{b.filename}</span>
              <span className="meta mono-num">{d(Math.round((b.size || 0) / 1024))} {m.kb} · {bkLabel(b.status)} · {relTime(b.created_at, lang)}</span>
            </div>
          ))}
          <button type="button" className="cm-btn cm-btn-green cm-btn-full" onClick={runBackup} disabled={busy}>
            <Ico d={ICO.backup} size={15} />{busy ? m.running : m.run_backup_now}
          </button>
        </section>
      </div>
    </div>
  )
}

function CmIpList({ m, srv, showIp, onToggle, lang }) {
  const sep = lang === 'fa' ? '، ' : ', '
  const row = (tag, label, value) => (
    <div className="cm-ip-row" key={tag}>
      <span className="tag mono-num">{tag}</span>
      <span className="lbl">{label}</span>
      <span className={'val mono-num' + (showIp ? '' : ' masked')} onClick={onToggle} title={showIp ? m.hide : m.show}>
        {value || '—'}
      </span>
    </div>
  )
  return (
    <div className="cm-ip-list">
      {row('PUB', m.ip_public, srv.public_ip)}
      {row('LAN', m.ip_local, (srv.local_ips || []).join(sep))}
      {row('DKR', m.ip_docker, (srv.docker_ips || []).join(sep))}
    </div>
  )
}

const CM_CSS = `
/* ---- .cm scope: LIGHT = _11.html "Azure Telemetry" ------------------ */
.cm {
  --cm-bg:#faf8ff; --cm-card:#ffffff; --cm-well:#f2f3ff; --cm-chip:#eaedff;
  --cm-divider:#eaedff; --cm-hair:#eaedff;
  --cm-text:#131b2e; --cm-text2:#3f4850; --cm-dim:#707881;
  /* brand blue (#1464BA) is the single-source primary — driven by the
     Caspian theme palette (--c-primary / --c-secondary) */
  --cm-accent:var(--c-primary); --cm-accent-2:var(--c-secondary);
  --cm-accent-soft:color-mix(in srgb, var(--c-secondary) 55%, #ffffff);
  --cm-ok:var(--c-success); --cm-warn:#F59E0B; --cm-bad:#ba1a1a;
  --cm-radius:12px; --cm-radius-in:8px;
  --cm-pad:16px; --cm-pad-lg:20px; --cm-gap:16px; --cm-stack:24px;
  --cm-shadow:0 1px 2px rgba(15,23,42,.06),0 1px 3px rgba(15,23,42,.04);
  --cm-card-border:transparent;
  /* this page uses Vazirmatn for Persian + UI labels in both variants;
     JetBrains Mono (.mono-num) stays on the pure number/telemetry readouts */
  --cm-font:'Vazirmatn',ui-sans-serif,system-ui,sans-serif;
  --cm-font-display:'Vazirmatn',ui-sans-serif,sans-serif;
  --cm-value-size:44px; --cm-value-weight:700; --cm-value-font:var(--cm-font-display);
  --cm-unit-color:var(--cm-dim);
  --cm-pill-bg:color-mix(in srgb, var(--c-success) 12%, transparent); --cm-pill-fg:color-mix(in srgb, var(--c-success) 82%, #000); --cm-pill-bd:color-mix(in srgb, var(--c-success) 26%, transparent);
  --cm-primary-bg:var(--c-primary); --cm-primary-fg:#ffffff;
  color:var(--cm-text);
  font-family:var(--cm-font);
}
/* ---- .cm.cm-dark: DARK = _7.html "Caspian Tunnel" ------------------- */
.cm.cm-dark {
  --cm-bg:#070C14; --cm-card:#10192A; --cm-well:#0f172a; --cm-chip:#1e293b;
  --cm-divider:rgba(30,47,77,.6); --cm-hair:#1E2F4D;
  --cm-text:#ffffff; --cm-text2:#e2e8f0; --cm-dim:#94a3b8;
  /* on the near-black canvas the lighter tint (--c-secondary) carries the
     charts/icons; solid CTAs + fills still use --c-primary (#1464BA) */
  --cm-accent:var(--c-secondary); --cm-accent-2:var(--c-primary);
  --cm-accent-soft:color-mix(in srgb, var(--c-secondary) 70%, #ffffff);
  --cm-ok:var(--c-success); --cm-warn:#fbbf24; --cm-bad:#f43f5e;
  --cm-radius:16px; --cm-radius-in:8px;
  --cm-pad:20px; --cm-pad-lg:24px; --cm-gap:20px; --cm-stack:24px;
  --cm-shadow:0 1px 3px rgba(0,0,0,.5);
  --cm-card-border:#1E2F4D;
  --cm-font:'Vazirmatn',ui-sans-serif,system-ui,sans-serif;
  --cm-font-display:'Vazirmatn',ui-sans-serif,sans-serif;
  --cm-value-size:36px; --cm-value-weight:800; --cm-value-font:'JetBrains Mono',ui-monospace,monospace;
  --cm-unit-color:var(--cm-accent);
  --cm-pill-bg:color-mix(in srgb, var(--c-success) 20%, transparent); --cm-pill-fg:color-mix(in srgb, var(--c-success) 55%, #ffffff); --cm-pill-bd:color-mix(in srgb, var(--c-success) 32%, transparent);
  --cm-primary-bg:var(--c-primary); --cm-primary-fg:#ffffff;
}

/* rendered inside the normal Caspian sidebar layout — no full-viewport fill,
   the layout <main> handles width/padding */
.cm { background:transparent; min-height:0; }
.cm .mono-num { font-family:'JetBrains Mono',ui-monospace,monospace; font-variant-numeric:tabular-nums; direction:ltr; unicode-bidi:isolate; }
/* light variant: Persian text + UI labels in Vazirmatn (the dark variant keeps
   its _7.html font-code mono labels). Number/telemetry readouts (.mono-num,
   the big metric value) stay JetBrains Mono in both. */
.cm:not(.cm-dark) .cm-m-label,
.cm:not(.cm-dark) .cm-m-detail,
.cm:not(.cm-dark) .cm-avgpeak,
.cm:not(.cm-dark) .cm-hbar-labels,
.cm:not(.cm-dark) .cm-h2-sub,
.cm:not(.cm-dark) .cm-speed-foot span,
.cm:not(.cm-dark) .cm-speed-foot b i,
.cm:not(.cm-dark) .cm-pill-up,
.cm:not(.cm-dark) .cm-pill-dn,
.cm:not(.cm-dark) .cm-pill-k,
.cm:not(.cm-dark) .cm-seg-title,
.cm:not(.cm-dark) .cm-seg-fa,
.cm:not(.cm-dark) .cm-ip-row .tag { font-family:var(--cm-font); }
.cm-wrap { max-width:none; margin:0; padding:0; display:flex; flex-direction:column; gap:var(--cm-stack); }
.cm-loading { display:grid; place-items:center; padding:80px 0; }
.cm-err { color:var(--cm-bad); font-size:14px; }

.cm-card {
  background:var(--cm-card); border:1px solid var(--cm-card-border);
  border-radius:var(--cm-radius); box-shadow:var(--cm-shadow);
  padding:var(--cm-pad); position:relative; overflow:hidden; min-width:0;
}
.cm-card-lg { padding:var(--cm-pad-lg); display:flex; flex-direction:column; }

.cm-grid { display:grid; gap:var(--cm-gap); }
.cm-r4 { grid-template-columns:repeat(4,minmax(0,1fr)); }
.cm-r2w { grid-template-columns:2fr 1fr; }
.cm-r3 { grid-template-columns:repeat(3,minmax(0,1fr)); }
@media (max-width:1024px){ .cm-r4{grid-template-columns:repeat(2,minmax(0,1fr));} .cm-r2w{grid-template-columns:1fr;} }
@media (max-width:768px){ .cm-r3{grid-template-columns:1fr;} }
@media (max-width:560px){ .cm-r4{grid-template-columns:1fr;} }

/* ---- header ---- */
.cm-header { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:16px; }
.cm-header-l { display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
.cm-pill {
  display:inline-flex; align-items:center; gap:10px; padding:6px 14px; border-radius:999px;
  background:var(--cm-pill-bg); color:var(--cm-pill-fg); border:1px solid var(--cm-pill-bd);
  font-size:12px; font-weight:600; white-space:nowrap;
}
.cm-pill-ver { font-size:10px; padding:2px 6px; border-radius:4px; background:rgba(255,255,255,.12); }
.cm.cm-dark .cm-pill-ver { background:color-mix(in srgb, var(--c-success) 34%, transparent); color:color-mix(in srgb, var(--c-success) 55%, #ffffff); }
.cm:not(.cm-dark) .cm-pill-ver { background:#ffffff; color:#707881; }
.cm-ping { position:relative; width:9px; height:9px; border-radius:50%; background:var(--cm-ok); flex:0 0 auto; }
.cm-ping::after { content:""; position:absolute; inset:0; border-radius:50%; background:var(--cm-ok); opacity:.75; animation:cm-ping 1.4s cubic-bezier(0,0,.2,1) infinite; }
@keyframes cm-ping { 75%,100%{ transform:scale(2.4); opacity:0; } }
.cm-pill-warn { background:color-mix(in srgb, var(--cm-warn) 14%, transparent); color:color-mix(in srgb, var(--cm-warn) 78%, #000); border-color:color-mix(in srgb, var(--cm-warn) 30%, transparent); }
.cm.cm-dark .cm-pill-warn { color:color-mix(in srgb, var(--cm-warn) 60%, #fff); }
.cm-pill-warn .cm-ping, .cm-pill-warn .cm-ping::after { background:var(--cm-warn); }

.cm-toolbar { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.cm-btn {
  display:inline-flex; align-items:center; gap:6px; padding:7px 12px; border-radius:var(--cm-radius-in);
  font-size:12px; font-weight:500; cursor:pointer; white-space:nowrap; text-decoration:none;
  background:var(--cm-well); border:1px solid var(--cm-hair); color:var(--cm-text2);
  transition:background .15s,border-color .15s,box-shadow .15s;
}
.cm-btn:hover { border-color:var(--cm-accent); }
.cm.cm-dark .cm-btn { background:#131F33; color:#cbd5e1; }
.cm.cm-dark .cm-btn:hover { background:#1e293b; }
.cm-btn.cm-btn-icon { padding:7px 9px; }
.cm-btn.on { color:var(--cm-accent); border-color:var(--cm-accent); }
.cm-btn-ar { font-size:13px; }
.cm-auto-dot { width:7px; height:7px; border-radius:50%; background:var(--cm-dim); flex:0 0 auto; }
.cm-auto-dot.live { background:var(--cm-ok); box-shadow:0 0 6px var(--cm-ok); }
.cm-btn-primary { background:var(--cm-primary-bg); color:var(--cm-primary-fg); border:0; font-weight:600; }
.cm.cm-dark .cm-btn-primary { box-shadow:0 0 20px -3px color-mix(in srgb, var(--c-primary) 45%, transparent); }
/* Run-backup CTA — brand green (#11AB53) */
.cm-btn-green { background:var(--c-success); color:#ffffff; border:0; font-weight:700;
  box-shadow:0 4px 14px -2px color-mix(in srgb, var(--c-success) 45%, transparent); }
.cm-btn-green:hover { background:color-mix(in srgb, var(--c-success) 90%, #000); }
.cm.cm-dark .cm-btn-green { box-shadow:0 0 22px -4px color-mix(in srgb, var(--c-success) 55%, transparent); }
.cm-btn-green:disabled { opacity:.6; cursor:default; }
.cm-btn-primary:disabled { opacity:.55; cursor:default; }
.cm-btn-full { width:100%; justify-content:center; margin-top:14px; padding:10px; }

/* ---- metric cards ---- */
.cm-metric { display:flex; flex-direction:column; justify-content:space-between; }
.cm-m-head { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:6px; }
.cm-m-head-l { display:flex; align-items:center; gap:7px; color:var(--cm-accent); font-weight:700; min-width:0; }
.cm:not(.cm-dark) .cm-metric:nth-child(2) .cm-m-head-l { color:var(--c-secondary); }
.cm:not(.cm-dark) .cm-metric:nth-child(3) .cm-m-head-l { color:var(--c-secondary); }
.cm .cm-ico { flex:0 0 auto; }
.cm-m-label { font-family:'JetBrains Mono',ui-monospace,monospace; font-size:12px; font-weight:600;
  text-transform:uppercase; letter-spacing:.06em; }
.cm-m-label-fa { font-size:11px; color:var(--cm-dim); font-weight:400; }
.cm-m-badge { font-family:'JetBrains Mono',ui-monospace,monospace; font-size:9.5px; padding:2px 7px; border-radius:4px;
  background:color-mix(in srgb, var(--cm-accent) 12%, transparent); color:var(--cm-accent-soft);
  border:1px solid color-mix(in srgb, var(--cm-accent) 24%, transparent); white-space:nowrap; flex:0 0 auto; }
.cm-m-detail { font-family:'JetBrains Mono',ui-monospace,monospace; font-size:10px; color:var(--cm-dim); white-space:nowrap; }
.cm-m-value { display:flex; align-items:baseline; gap:4px; margin-top:2px; direction:ltr; }
.cm-m-value .n { font-family:var(--cm-value-font); font-size:var(--cm-value-size); font-weight:var(--cm-value-weight);
  color:var(--cm-text); letter-spacing:-.02em; line-height:1.05; }
.cm-m-value .u { font-family:var(--cm-value-font); font-size:19px; font-weight:600; color:var(--cm-unit-color); }
.cm-m-sub { font-family:'JetBrains Mono',ui-monospace,monospace; font-size:11px; color:var(--cm-dim);
  margin:4px 0 0; direction:ltr; text-align:right; }
.cm-m-foot { margin-top:14px; }
.cm.cm-dark .cm-m-foot { padding-top:12px; border-top:1px solid var(--cm-divider); }
.cm-avgpeak { display:flex; justify-content:space-between; gap:8px; font-family:'JetBrains Mono',ui-monospace,monospace;
  font-size:11px; color:var(--cm-dim); margin-bottom:8px; }
.cm-avgpeak strong { color:var(--cm-text2); font-weight:600; }
.cm-avgpeak strong.hot { color:var(--cm-accent); }
.cm:not(.cm-dark) .cm-metric:nth-child(2) .cm-avgpeak strong.hot { color:var(--c-secondary); }

.cm-spark { display:block; width:100%; height:100%; }
.cm-metric .cm-m-foot > .cm-spark, .cm-metric .cm-m-foot > svg.cm-spark { height:40px; }
.cm:not(.cm-dark) .cm-metric .cm-m-foot > .cm-spark { height:48px; }

/* dark vertical fill well (_7 RAM/STORAGE/SWAP) */
.cm-vbar { height:40px; border-radius:8px; background:#0f172a; border:1px solid var(--cm-hair);
  display:flex; align-items:flex-end; overflow:hidden; }
.cm-vbar > i { display:block; width:100%; border-top:2px solid var(--cm-accent);
  background:linear-gradient(to top, color-mix(in srgb, var(--cm-accent) 42%, transparent),
    color-mix(in srgb, var(--cm-accent) 22%, transparent) 45%, color-mix(in srgb, var(--cm-accent) 10%, transparent));
  box-shadow:0 0 20px -3px color-mix(in srgb, var(--cm-accent) 35%, transparent); }
.cm-vbar > i.cm-flat { height:2px !important; border-top:0; background:rgba(51,65,85,.4); box-shadow:none; }

/* light horizontal gauge (_11 RAM/STORAGE) */
.cm-hbar-wrap { display:flex; flex-direction:column; gap:4px; margin-top:4px; }
.cm-hbar { height:12px; border-radius:999px; background:#eaedff; padding:2px; overflow:hidden; }
.cm-hbar.cm-hbar--thin { height:6px; padding:0; }
.cm-hbar > i { display:block; height:100%; border-radius:999px; background:var(--cm-accent); }
.cm-hbar-labels { display:flex; justify-content:space-between; font-family:'JetBrains Mono',ui-monospace,monospace;
  font-size:10px; color:var(--cm-dim); }

/* ---- overall speed ---- */
.cm-speed-head { display:flex; flex-wrap:wrap; align-items:flex-start; justify-content:space-between; gap:16px;
  padding-bottom:16px; border-bottom:1px solid var(--cm-divider); }
.cm-h2-row { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.cm-h2 { margin:0; font-family:'JetBrains Mono',ui-monospace,monospace; font-size:14px; font-weight:700;
  letter-spacing:.03em; text-transform:uppercase; color:var(--cm-text); }
.cm:not(.cm-dark) .cm-h2 { font-family:var(--cm-font-display); font-size:16px; letter-spacing:.02em; }
.cm-h2-fa { font-size:12px; color:var(--cm-dim); }
.cm-h2-sub { margin:2px 0 0; font-family:'JetBrains Mono',ui-monospace,monospace; font-size:11px; color:var(--cm-dim);
  direction:ltr; text-align:right; }
.cm-speed-pills { display:flex; gap:10px; flex-wrap:wrap; direction:ltr; }
.cm-pill-up, .cm-pill-dn { display:inline-flex; align-items:center; gap:6px; padding:5px 10px; border-radius:8px;
  font-family:'JetBrains Mono',ui-monospace,monospace; font-size:11px; white-space:nowrap; }
.cm-pill-up { background:color-mix(in srgb, var(--cm-accent) 12%, transparent); border:1px solid color-mix(in srgb, var(--cm-accent) 30%, transparent); color:var(--cm-accent-soft); }
.cm-pill-dn { background:color-mix(in srgb, var(--cm-accent-2) 12%, transparent); border:1px solid color-mix(in srgb, var(--cm-accent-2) 30%, transparent); color:var(--cm-accent-soft); }
.cm:not(.cm-dark) .cm-pill-up { background:#f2f3ff; border-color:transparent; color:var(--cm-accent); }
.cm:not(.cm-dark) .cm-pill-dn { background:#f2f3ff; border-color:transparent; color:var(--c-secondary); }
.cm-pill-up b:first-child, .cm-pill-dn b:first-child { font-weight:700; }
.cm-pill-k { color:var(--cm-dim); }
.cm-pill-v { color:var(--cm-text); font-weight:700; }
.cm-chart { margin:14px 0 0; }
.cm-chart svg { display:block; width:100%; }
.cm-chart-lg svg { height:240px; }
@media (max-width:640px){ .cm-chart-lg svg{ height:180px; } }
.cm-glow { filter:none; }
.cm.cm-dark .cm-glow { filter:drop-shadow(0 2px 8px color-mix(in srgb, var(--cm-accent) 55%, transparent)); }
.cm-speed-foot { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; margin-top:16px;
  padding-top:16px; border-top:1px solid var(--cm-divider); }
.cm-speed-foot div { display:flex; flex-direction:column; gap:3px; min-width:0; }
.cm-speed-foot span { font-family:'JetBrains Mono',ui-monospace,monospace; font-size:10px; color:var(--cm-dim);
  text-transform:uppercase; letter-spacing:.04em; }
.cm-speed-foot b { font-size:20px; font-weight:700; color:var(--cm-text); word-break:break-word; }
.cm-speed-foot b i { font-size:12px; font-weight:400; color:var(--cm-dim); font-style:normal; }
.cm-speed-foot .cm-aw { font-size:13px; display:flex; gap:8px; flex-wrap:wrap; }
.cm-aw .up { color:var(--cm-accent); }
.cm-aw .dn { color:var(--cm-accent-soft); }
.cm:not(.cm-dark) .cm-aw .dn { color:var(--c-secondary); }
@media (max-width:560px){ .cm-speed-foot{ grid-template-columns:repeat(2,1fr); } }

/* ---- section heads / service health / panels / backups ---- */
.cm-sec-head { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom:14px; }
.cm-card > .cm-h2-row { margin-bottom:14px; }
.cm-sec-head .cm-h2-row, .cm-speed-head .cm-h2-row, .cm-conn-head .cm-h2-row { margin-bottom:0; }
.cm-filter { display:inline-flex; gap:6px; }
.cm-chip { padding:5px 12px; border-radius:999px; font-size:12px; font-weight:600; cursor:pointer;
  background:var(--cm-chip); border:1px solid transparent; color:var(--cm-dim); }
.cm-chip.on { background:var(--cm-accent); color:var(--cm-primary-fg); }
.cm.cm-dark .cm-chip.on { color:#020617; }
.cm-svc-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); column-gap:24px; }
@media (max-width:640px){ .cm-svc-grid{ grid-template-columns:1fr; } }
.cm-svc { display:grid; grid-template-columns:auto minmax(0,1fr) auto; align-items:center; gap:10px;
  padding:10px 0; border-bottom:1px solid var(--cm-divider); font-size:13px; }
.cm-svc .name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--cm-text2); }
.cm-svc .lat { font-size:11px; color:var(--cm-dim); white-space:nowrap; }
.cm-dot { width:8px; height:8px; border-radius:50%; flex:0 0 auto; }
.cm-dot.up { background:var(--cm-ok); } .cm-dot.down { background:var(--cm-bad); } .cm-dot.na { background:var(--cm-dim); }
.cm.cm-dark .cm-dot.up { box-shadow:0 0 8px var(--cm-ok); }

.cm-panel-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:12px; }
.cm-panel { border:1px solid var(--cm-hair); border-radius:var(--cm-radius-in); padding:12px; min-width:0; }
.cm-panel-top { display:grid; grid-template-columns:auto minmax(0,1fr) auto; align-items:center; gap:8px; }
.cm-panel-top .name { font-weight:700; font-size:13px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.cm-panel-top .lat { font-size:11px; color:var(--cm-dim); }
.cm-panel-stats { display:flex; flex-direction:column; gap:3px; margin-top:8px; font-size:12px; color:var(--cm-dim); }
.cm-panel-stats b { color:var(--cm-text2); }
.cm-panel-detail { font-size:12px; color:var(--cm-dim); margin-top:6px; }

.cm-bk { display:grid; grid-template-columns:auto minmax(0,1fr) auto; align-items:center; gap:10px;
  padding:10px 0; border-bottom:1px solid var(--cm-divider); font-size:13px; }
.cm-bk:last-of-type { border-bottom:0; }
.cm-bk .fn { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--cm-text2); }
.cm-bk .meta { font-size:11px; color:var(--cm-dim); white-space:nowrap; text-align:end; }

/* ---- bottom summary ---- */
.cm-strip-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:24px; align-items:center; }
.cm-seg { padding-inline-end:24px; border-inline-end:1px solid rgba(30,47,77,.7); }
.cm-seg:last-child { border-inline-end:0; padding-inline-end:0; }
.cm-seg-head { display:flex; align-items:center; gap:8px; color:var(--cm-dim); margin-bottom:14px; }
.cm-seg-head--sb { justify-content:space-between; }
.cm-seg-head--sb > span { display:flex; align-items:center; gap:8px; }
.cm-seg-head .cm-ico { color:var(--cm-accent); }
.cm-seg-title { font-family:'JetBrains Mono',ui-monospace,monospace; font-size:12px; font-weight:600;
  text-transform:uppercase; letter-spacing:.06em; color:var(--cm-dim); }
.cm-seg-fa { font-size:11px; color:var(--cm-dim); }
.cm-seg-cols { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
.cm-seg-cols--row { display:flex; align-items:center; gap:24px; margin-top:14px; }
.cm-seg-cols > div, .cm-seg-cols--row > div { display:flex; flex-direction:column; gap:4px; min-width:0; }
.cm-seg-cols .k, .cm-seg-cols--row .k { font-size:10px; color:var(--cm-dim); text-transform:uppercase; letter-spacing:.04em; }
.cm-seg-cols .v, .cm-seg-cols--row .v { font-size:18px; font-weight:800; color:var(--cm-text); }
.cm-seg-cols .v.hot { color:var(--cm-accent-soft); }
.cm-seg-vdiv { width:1px; height:32px; background:var(--cm-chip); flex:0 0 auto; }
.cm-seg-ip-row { display:flex; align-items:center; justify-content:space-between; gap:14px; }
.cm-seg-ip-body { min-width:0; flex:1; }
.cm-eye { display:inline-flex; align-items:center; justify-content:center; width:36px; height:36px; flex:0 0 auto;
  border-radius:12px; background:rgba(30,41,59,.8); border:1px solid var(--cm-hair); color:#cbd5e1; cursor:pointer; }
.cm-eye:hover { background:color-mix(in srgb, var(--cm-accent) 20%, transparent); color:var(--cm-accent-soft); }
.cm-eye-inline { background:none; border:0; color:var(--cm-dim); cursor:pointer; padding:2px; }
.cm-ip-list { display:flex; flex-direction:column; gap:8px; margin-top:12px; }
.cm-ip-row { display:grid; grid-template-columns:auto auto minmax(0,1fr); align-items:center; gap:8px; font-size:12px; }
.cm-ip-row .tag { font-size:9px; padding:2px 5px; border-radius:4px; background:var(--cm-chip); color:var(--cm-dim); }
.cm-ip-row .lbl { color:var(--cm-dim); }
.cm-ip-row .val { text-align:end; font-size:12px; color:var(--cm-accent); word-break:break-word; cursor:pointer; transition:filter .3s; }
.cm:not(.cm-dark) .cm-ip-row .val { color:var(--cm-text); font-weight:700; }
.cm-ip-row .val.masked { filter:blur(5px); user-select:none; }
@media (max-width:768px){
  .cm-strip-grid { grid-template-columns:1fr; gap:18px; }
  .cm-seg { padding-inline-end:0; border-inline-end:0; padding-bottom:18px; border-bottom:1px solid rgba(30,47,77,.7); }
  .cm-seg:last-child { padding-bottom:0; border-bottom:0; }
}
`
