import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../lib/api'
import { faDigits, gb, relTime, bps } from '../lib/format'
import { Spinner } from '../components/ui'

const REFRESH_MS = 15000

const SVC_LABEL = {
  site: 'سایت (Web)',
  mysql: 'دیتابیس (MySQL)',
  redis: 'ردیس (Redis)',
  celery_worker: 'Celery Worker',
  celery_beat: 'Celery Beat',
  bot_sales: 'ربات فروش',
  bot_backup: 'ربات بک‌آپ',
  panel: 'پنل پاسارگارد',
  mail: 'میل‌سرور (SMTP)',
}
const BK_STATUS = { ok: 'موفق', failed: 'ناموفق', partial: 'ناقص', running: 'در حال اجرا' }

function svcLat(x) {
  if (x.is_up == null) return 'بدون داده'
  const d = (x.detail || '').toLowerCase()
  if (d === 'ok' || d.startsWith('http ')) return faDigits(x.latency_ms ?? 0) + ' ms'
  return x.detail || (faDigits(x.latency_ms ?? 0) + ' ms')
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

  if (!data) {
    return (
      <div className="grid place-items-center py-16">
        {err ? <p className="text-danger text-sm">دریافت اطلاعات مانیتورینگ ناموفق بود.</p> : <Spinner />}
      </div>
    )
  }

  const { resources: rs, network: net, server: srv, targets, backups } = data
  const disHigh = rs.disk.percent >= 90

  return (
    <div className="mon" dir="rtl">
      <style>{CSS}</style>

      <div className="topbar">
        <h1>مانیتورینگ</h1>
        <span className="status-pill">
          <i className="dot" style={{ background: data.overall === 'ok' ? 'var(--c-success)' : 'var(--c-warning)' }} />
          {faDigits(data.up_count)} از {faDigits(data.total_count)} سرویس فعال
        </span>
        <div className="actions">
          <span className="btn">↻ رفرش خودکار ({faDigits(15)}ث)</span>
          <button className="btn primary" onClick={runBackup} disabled={busy}>
            ↑ {busy ? 'در حال اجرا…' : 'اجرای بک‌آپ'}
          </button>
        </div>
      </div>

      {/* ---- 4 resource cards ---- */}
      <div className="grid r4">
        <ResCard
          icon="⚡" label="پردازنده (CPU)" big={faDigits(rs.cpu.percent) + '٪'}
          sub={`${faDigits(rs.cpu.cores)} هسته · ${faDigits(rs.cpu.freq_ghz ?? '—')} گیگاهرتز`}
          pct={rs.cpu.percent} grad="#7C5CFF,#22D3EE"
          m1={`میانگین ${faDigits(rs.cpu.avg)}٪`} m2={`اوج ${faDigits(rs.cpu.peak)}٪`}
        />
        <ResCard
          icon="▦" label="حافظه (RAM)" big={faDigits(rs.ram.percent) + '٪'}
          sub={`${faDigits(rs.ram.used_gb)} / ${faDigits(rs.ram.total_gb)} گیگابایت`}
          pct={rs.ram.percent} grad="#22D3EE,#34D399"
          m1={`میانگین ${faDigits(rs.ram.avg)}٪`} m2={`اوج ${faDigits(rs.ram.peak)}٪`}
        />
        <ResCard
          icon="🖴" label="دیسک" big={faDigits(rs.disk.percent) + '٪'}
          sub={`${faDigits(rs.disk.used_gb)} / ${faDigits(rs.disk.total_gb)} گیگابایت`}
          pct={rs.disk.percent} grad="#FBBF24,#F87171"
          m1={`آزاد ${faDigits(rs.disk.free_gb)} گیگ`}
          m2={disHigh ? 'توجه' : 'سالم'} m2warn={disHigh}
        />
        <div className="card bw">
          <span className="line" style={{ background: 'linear-gradient(90deg,#34D399,#22D3EE)' }} />
          <div className="card-head"><span className="ic">📶</span><span>پهنای باند</span></div>
          <div className="big sm">
            ↑{bps(net.up_bps)} &nbsp; ↓{bps(net.down_bps)}
          </div>
          <div className="sub">اینترفیس {net.iface}</div>
          <div className="meta">
            <span>ارسال {faDigits(gb(net.sent_total))} گیگ</span>
            <span>دریافت {faDigits(gb(net.recv_total))} گیگ</span>
          </div>
        </div>
      </div>

      {/* ---- service status + network graph ---- */}
      <div className="grid r2">
        <div className="card">
          <div className="title">وضعیت سرویس‌ها</div>
          {targets.map((x) => (
            <div className="svc" key={x.target}>
              <span className={'badge ' + (x.is_up ? 'up' : x.is_up === false ? 'down' : 'na')}>
                {x.is_up ? 'فعال' : x.is_up === false ? 'قطع' : '—'}
              </span>
              <span className="name">{SVC_LABEL[x.target] || x.target}</span>
              <span className="lat">{svcLat(x)}</span>
            </div>
          ))}
        </div>

        <div className="card">
          <div className="speed-head">
            <div>
              <div className="title">ترافیک شبکه</div>
              <div className="sub">مجموع اینترفیس {net.iface}</div>
            </div>
            <div className="speed-pills">
              <span>↑ {bps(net.up_bps)}</span>
              <span>↓ {bps(net.down_bps)}</span>
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
            {!g.line && <text x="300" y="80" textAnchor="middle" fill="var(--c-text-muted)" fontSize="13">در حال جمع‌آوری داده…</text>}
          </svg>
          <div className="speed-foot">
            <div><span>ارسال‌شده</span><b>{faDigits(gb(net.sent_total))} GB</b></div>
            <div><span>دریافت‌شده</span><b>{faDigits(gb(net.recv_total))} GB</b></div>
            <div><span>نسخه سیستم</span><b>v{faDigits(data.version)}</b></div>
          </div>
        </div>
      </div>

      {/* ---- backups + server IPs ---- */}
      <div className="grid r2">
        <div className="card">
          <div className="title">بک‌آپ‌های اخیر</div>
          {(backups || []).length === 0 && <div className="sub">هنوز بک‌آپی ثبت نشده است.</div>}
          {(backups || []).map((b) => (
            <div className="bk" key={b.id}>
              <span className={'dotb ' + (b.status === 'ok' ? 'ok' : 'bad')} />
              <span className="fn">{b.filename}</span>
              <span className="dt">
                {faDigits(Math.round((b.size || 0) / 1024))} کیلوبایت · {BK_STATUS[b.status] || b.status} · {relTime(b.created_at)}
              </span>
            </div>
          ))}
          <button className="btn primary full" onClick={runBackup} disabled={busy}>
            ↑ {busy ? 'در حال اجرا…' : 'اجرای بک‌آپ دستی'}
          </button>
        </div>

        <div className="card">
          <div className="title">آدرس‌های IP سرور</div>
          <div className="kv"><span className="k">IP عمومی (IPv4)</span><span className="v">{srv.public_ip || '—'}</span></div>
          <div className="kv"><span className="k">IP لوکال</span><span className="v">{(srv.local_ips || []).join('، ') || '—'}</span></div>
          <div className="kv"><span className="k">شبکه Docker</span><span className="v">{(srv.docker_ips || []).join('، ') || '—'}</span></div>
          <div className="kv">
            <span className="k">اتصالات باز</span>
            <span className="v">TCP {faDigits(srv.tcp_open)} · UDP {faDigits(srv.udp_open)}</span>
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
.mon .topbar { display:flex; align-items:center; gap:14px; flex-wrap:wrap; margin-bottom:18px; }
.mon .topbar h1 { font-size:22px; font-weight:800; margin:0; }
.mon .status-pill { display:inline-flex; align-items:center; gap:8px; font-size:13px;
  padding:6px 12px; border-radius:999px; background:var(--c-surface); border:1px solid var(--c-border); color:var(--c-text-muted); }
.mon .status-pill .dot { width:8px; height:8px; border-radius:50%; display:inline-block; }
.mon .actions { margin-inline-start:auto; display:flex; gap:8px; flex-wrap:wrap; }
.mon .btn { display:inline-flex; align-items:center; gap:6px; font-size:13px; cursor:pointer;
  padding:8px 14px; border-radius:12px; background:var(--c-surface); border:1px solid var(--c-border);
  color:var(--c-text); transition:opacity .2s; }
.mon .btn.primary { background:linear-gradient(90deg,var(--c-primary),var(--c-secondary)); border:0; color:#fff; }
.mon .btn.full { width:100%; justify-content:center; margin-top:12px; }
.mon .btn:disabled { opacity:.55; cursor:default; }

.mon .grid { display:grid; gap:16px; margin-bottom:16px; }
.mon .grid.r4 { grid-template-columns:repeat(4,1fr); }
.mon .grid.r2 { grid-template-columns:1.3fr 1fr; }
@media (max-width:1000px){ .mon .grid.r4{grid-template-columns:repeat(2,1fr);} .mon .grid.r2{grid-template-columns:1fr;} }
@media (max-width:560px){ .mon .grid.r4{grid-template-columns:1fr;} }

.mon .card { position:relative; overflow:hidden; padding:18px;
  background:var(--c-surface); border:1px solid var(--c-border); border-radius:16px;
  -webkit-backdrop-filter:blur(16px); backdrop-filter:blur(16px); }
.mon .card .line, .mon .card::before { content:""; position:absolute; inset:0 0 auto 0; height:3px;
  background:linear-gradient(90deg,var(--c-primary),var(--c-secondary)); }
.mon .card .line { z-index:1; }
.mon .card-head { display:flex; align-items:center; gap:10px; color:var(--c-text-muted); font-size:14px; margin-bottom:10px; }
.mon .ic { width:26px; height:26px; display:grid; place-items:center; font-size:15px;
  border-radius:9px; background:rgba(124,92,255,.14); }
.mon .big { font-size:38px; font-weight:800; line-height:1; }
.mon .big.sm { font-size:26px; }
.mon .big small { font-size:14px; font-weight:500; color:var(--c-text-muted); }
.mon .sub { color:var(--c-text-muted); font-size:12.5px; margin-top:6px; }
.mon .bar { height:7px; border-radius:999px; background:var(--c-border); margin-top:14px; overflow:hidden; }
.mon .bar i { display:block; height:100%; border-radius:999px; transition:width .5s ease; }
.mon .meta { display:flex; justify-content:space-between; font-size:12px; color:var(--c-text-muted); margin-top:10px; }

.mon .title { font-size:15px; font-weight:700; margin-bottom:14px; }
.mon .svc { display:grid; grid-template-columns:auto 1fr auto; align-items:center; gap:10px;
  padding:9px 0; border-bottom:1px solid var(--c-border); font-size:13.5px; }
.mon .svc:last-of-type { border-bottom:0; }
.mon .badge { font-size:11px; padding:3px 9px; border-radius:999px; font-weight:600; }
.mon .badge.up { background:rgba(52,211,153,.16); color:var(--c-success); }
.mon .badge.down { background:rgba(248,113,113,.16); color:var(--c-danger); }
.mon .badge.na { background:var(--c-border); color:var(--c-text-muted); }
.mon .svc .lat { color:var(--c-text-muted); font-size:12px; font-variant-numeric:tabular-nums; }

.mon .speed-head { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:6px; }
.mon .speed-pills { display:flex; gap:8px; }
.mon .speed-pills span { font-size:12px; padding:4px 10px; border-radius:999px;
  background:var(--c-border); color:var(--c-text); font-variant-numeric:tabular-nums; }
.mon .speed-graph { width:100%; height:150px; display:block; margin:6px 0 4px; }
.mon .speed-foot { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-top:8px; }
.mon .speed-foot div { display:flex; flex-direction:column; gap:3px; }
.mon .speed-foot span { font-size:11px; color:var(--c-text-muted); }
.mon .speed-foot b { font-size:14px; font-weight:700; }

.mon .bk { display:grid; grid-template-columns:auto 1fr auto; align-items:center; gap:10px;
  padding:9px 0; border-bottom:1px solid var(--c-border); font-size:13px; }
.mon .bk .dotb { width:8px; height:8px; border-radius:50%; }
.mon .bk .dotb.ok { background:var(--c-success); }
.mon .bk .dotb.bad { background:var(--c-danger); }
.mon .bk .fn { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.mon .bk .dt { color:var(--c-text-muted); font-size:11.5px; white-space:nowrap; }

.mon .kv { display:flex; justify-content:space-between; align-items:center; gap:10px;
  padding:10px 0; border-bottom:1px solid var(--c-border); font-size:13px; }
.mon .kv:last-of-type { border-bottom:0; }
.mon .kv .k { color:var(--c-text-muted); }
.mon .kv .v { font-variant-numeric:tabular-nums; font-weight:600; direction:ltr; }
`
