import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { api, apiError } from '../lib/api'
import { isTelegramWebView } from '../lib/telegram'
import { useToast } from './Toast'

// v1.55 «وایرگارد» on a service (backend apps/panel/wireguard.py): one row per location (flag + country), each with its own
// .conf download, plus «دانلود همه» (zip). Files come straight from PasarGuard on every request (never stored). Inside the
// Telegram Mini App a WebView download is unreliable, so the bot sends the file to the user's chat instead.
const T = {
  fa: {
    title: 'وایرگارد', sub: 'برای هر مکان یک فایل ‎.conf‎ — آن را در برنامهٔ WireGuard «وارد» (Import) کنید.',
    sub_tg: 'فایل هر مکان در چت ربات برایتان فرستاده می‌شود؛ آن را در برنامهٔ WireGuard «وارد» کنید.',
    get: 'دانلود', send: 'ارسال در چت', all: 'دانلود همه (zip)', all_tg: 'ارسال همه (zip)', close: 'بستن', sent: 'فایل در چت ربات ارسال شد',
    done: 'فایل دانلود شد', none: 'کانفیگی پیدا نشد.', open: 'وایرگارد',
  },
  en: {
    title: 'WireGuard', sub: 'One .conf file per location — import it in the WireGuard app.',
    sub_tg: 'Each location’s file is sent to your bot chat; import it in the WireGuard app.',
    get: 'Download', send: 'Send to chat', all: 'Download all (zip)', all_tg: 'Send all (zip)', close: 'Close', sent: 'Sent to your bot chat',
    done: 'Downloaded', none: 'No configs found.', open: 'WireGuard',
  },
}

export function useWgText(lang) { return T[lang] || T.fa }

export default function WireguardSheet({ s, lang, onClose }) {
  const t = T[lang] || T.fa
  const toast = useToast()
  const tg = isTelegramWebView()
  const [rows, setRows] = useState(null)
  const [allName, setAllName] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState('')
  useEffect(() => {
    const h = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    api.get(`/services/${s.id}/wireguard/`).then((r) => { setRows(r.data.results || []); setAllName(r.data.all_filename || '') })
      .catch((e) => { setErr(e?.response?.data?.detail_fa && lang === 'fa' ? e.response.data.detail_fa : apiError(e)); setRows([]) })
    return () => window.removeEventListener('keydown', h)
  }, [s.id])

  const get = async (key, name) => {
    setBusy(key)
    try {
      if (tg) {
        await api.post(`/services/${s.id}/wireguard/${key}/send/`, {})
        toast.success(t.sent)
      } else {
        const r = await api.get(`/services/${s.id}/wireguard/${key}/`, { responseType: 'blob' })
        const url = URL.createObjectURL(r.data)
        const a = document.createElement('a')
        a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove()
        setTimeout(() => URL.revokeObjectURL(url), 2000)
        toast.success(t.done)
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail_fa && lang === 'fa' ? e.response.data.detail_fa : apiError(e))
    } finally { setBusy('') }
  }

  return createPortal(
    <div className="wg-ov" onClick={onClose} role="presentation">
      <style>{CSS}</style>
      <div className="wg-sheet" role="dialog" aria-modal="true" aria-label={t.title} onClick={(e) => e.stopPropagation()} data-testid="wg-sheet">
        <div className="wg-head">
          <div><b>{t.title}</b> · <bdi dir="ltr">{s.panel_username}</bdi><p>{tg ? t.sub_tg : t.sub}</p></div>
          <button type="button" className="wg-x" onClick={onClose} aria-label={t.close}>×</button>
        </div>
        {err && <p className="wg-err" role="alert">{err}</p>}
        {rows === null ? <div className="wg-spin" aria-busy="true" /> : rows.length === 0 && !err ? <p className="wg-err">{t.none}</p> : (
          <ul className="wg-list">
            {rows.map((r) => (
              <li key={r.key} className="wg-row" data-testid="wg-row">
                <span className="wg-flag" aria-hidden="true">{r.flag || '🌐'}</span>
                <span className="wg-name"><b>{lang === 'fa' ? r.name_fa : r.name_en}</b><small dir="ltr">{r.filename}</small></span>
                <button type="button" className="wg-btn" disabled={!!busy} onClick={() => get(r.key, r.filename)} data-testid={`wg-get-${r.key}`}>
                  {busy === r.key ? '…' : tg ? t.send : t.get}</button>
              </li>
            ))}
          </ul>
        )}
        {rows && rows.length > 1 && (
          <button type="button" className="wg-btn wg-btn--all" disabled={!!busy} onClick={() => get('all', allName || 'wireguard.zip')} data-testid="wg-all">
            {busy === 'all' ? '…' : tg ? t.all_tg : t.all}</button>
        )}
      </div>
    </div>, document.body)
}

const CSS = `
.wg-ov { position: fixed; inset: 0; z-index: 1200; background: rgba(0,0,0,.45); display: grid; place-items: end center; padding: 0; }
@media (min-width: 640px) { .wg-ov { place-items: center; padding: 16px; } }
.wg-sheet { width: 100%; max-width: 480px; max-height: 88vh; overflow: auto; background: var(--c-bg); color: var(--c-text);
  border-radius: 20px 20px 0 0; padding: 16px; display: flex; flex-direction: column; gap: 10px; box-shadow: 0 -8px 30px rgba(0,0,0,.25); }
@media (min-width: 640px) { .wg-sheet { border-radius: 20px; } }
.wg-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.wg-head p { margin: 4px 0 0; font-size: 12.5px; line-height: 1.8; color: var(--c-text-muted); }
.wg-x { min-width: 44px; min-height: 44px; border: 0; background: transparent; color: var(--c-text); font-size: 24px; cursor: pointer; }
.wg-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.wg-row { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border: 1px solid var(--c-border); border-radius: 14px; min-width: 0; }
.wg-flag { font-size: 24px; line-height: 1; }
.wg-name { flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.wg-name small { font-size: 11px; color: var(--c-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wg-btn { min-height: 44px; padding: 0 14px; border-radius: 12px; border: 0; background: var(--c-primary); color: #fff; font-weight: 700;
  font-size: 13px; cursor: pointer; white-space: nowrap; }
.wg-btn:disabled { opacity: .6; cursor: default; }
.wg-btn--all { width: 100%; }
.wg-err { font-size: 13px; color: var(--c-danger); margin: 0; }
.wg-spin { height: 80px; }
`
