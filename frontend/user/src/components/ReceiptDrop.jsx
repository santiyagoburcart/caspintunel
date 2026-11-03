/**
 * v1.38.1 receipt picker — the ONE receipt upload control (customer checkout, agency portal payment,
 * group-manager payment, staff manual invoice). This file is kept identical in both apps.
 *
 * Tap / click or drag a picture onto it → checked here (type + size, fa/en errors) → preview with the
 * file name, size and «حذف». `progress` (0–100) shows the upload bar while the parent sends it
 * (axios `onUploadProgress` → `uploadPct(e)`). The server checks the image again (Pillow).
 */
import { useEffect, useId, useRef, useState } from 'react'

export const RECEIPT_MAX_MB = 10
const TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif']
const EXT = /\.(jpe?g|png|webp|gif)$/i

const STR = {
  fa: {
    pick: 'انتخاب عکس رسید', drag: 'عکس رسید را اینجا بکشید یا بزنید تا انتخاب کنید', phone: 'برای انتخاب عکس رسید بزنید',
    rules: `JPG، PNG، WEBP یا GIF · حداکثر ${RECEIPT_MAX_MB} مگابایت`, remove: 'حذف', change: 'تغییر عکس', uploading: 'در حال ارسال…',
    bad_type: 'فقط عکس رسید (JPG، PNG، WEBP یا GIF) پذیرفته می‌شود.', too_big: `حجم عکس بیشتر از ${RECEIPT_MAX_MB} مگابایت است — عکس کوچک‌تری انتخاب کنید.`,
    empty: 'این فایل خالی است.', drop: 'رها کنید', kb: 'کیلوبایت', mb: 'مگابایت',
  },
  en: {
    pick: 'Choose the receipt photo', drag: 'Drag the receipt photo here, or click to choose', phone: 'Tap to choose the receipt photo',
    rules: `JPG, PNG, WEBP or GIF · up to ${RECEIPT_MAX_MB} MB`, remove: 'Remove', change: 'Change', uploading: 'Uploading…',
    bad_type: 'Only a receipt picture (JPG, PNG, WEBP or GIF) is accepted.', too_big: `The picture is larger than ${RECEIPT_MAX_MB} MB — choose a smaller one.`,
    empty: 'This file is empty.', drop: 'Drop it', kb: 'KB', mb: 'MB',
  },
}

/** fa/en reason a file is refused, or '' when it is fine. */
export function receiptProblem(file, lang = 'fa') {
  const s = STR[lang] || STR.fa
  if (!file) return ''
  if (!(TYPES.includes(file.type) || (!file.type && EXT.test(file.name || '')))) return s.bad_type
  if (!file.size) return s.empty
  if (file.size > RECEIPT_MAX_MB * 1024 * 1024) return s.too_big
  return ''
}

/** axios onUploadProgress event → 0–100 */
export const uploadPct = (e) => (e && e.total ? Math.min(100, Math.round((e.loaded / e.total) * 100)) : null)

const sizeText = (b, s) => (b < 1024 * 1024 ? `${Math.max(1, Math.round(b / 1024))} ${s.kb}` : `${(b / 1024 / 1024).toFixed(1)} ${s.mb}`)

export default function ReceiptDrop({ file, onChange, lang = 'fa', progress = null, disabled = false, label, hint, testId = 'receipt-drop' }) {
  const s = STR[lang] || STR.fa
  const input = useRef(null)
  const id = useId()
  const [err, setErr] = useState('')
  const [over, setOver] = useState(false)
  const [url, setUrl] = useState('')
  useEffect(() => {
    if (!file) { setUrl(''); return undefined }
    const u = URL.createObjectURL(file); setUrl(u)
    return () => URL.revokeObjectURL(u)
  }, [file])
  useEffect(() => { setErr('') }, [lang])
  const take = (f) => {
    if (!f) return
    const p = receiptProblem(f, lang)
    setErr(p)
    if (!p) onChange(f)
  }
  const busy = progress != null
  const open = () => { if (!disabled && !busy) input.current?.click() }
  const coarse = typeof window !== 'undefined' && window.matchMedia?.('(pointer: coarse)').matches
  return (
    <div className="rd" data-testid={testId}>
      <style>{RD_CSS}</style>
      {label && <span className="rd-l" id={`${id}-l`}>{label}</span>}
      <input ref={input} id={id} type="file" accept="image/jpeg,image/png,image/webp,image/gif" hidden disabled={disabled || busy}
        data-testid={`${testId}-input`} onChange={(e) => { take(e.target.files?.[0]); e.target.value = '' }} />
      {!file ? (
        <button type="button" className="rd-zone" data-over={over || undefined} disabled={disabled} aria-labelledby={label ? `${id}-l` : undefined}
          aria-describedby={`${id}-r`} onClick={open}
          onDragOver={(e) => { e.preventDefault(); if (!disabled) setOver(true) }} onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); if (!disabled) take(e.dataTransfer?.files?.[0]) }}>
          <svg className="rd-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M4 16.5V18a2 2 0 002 2h12a2 2 0 002-2v-1.5M12 4v11M7.5 8.5L12 4l4.5 4.5" /></svg>
          <b>{over ? s.drop : s.pick}</b>
          <small>{hint || (coarse ? s.phone : s.drag)}</small>
          <small className="rd-rules" id={`${id}-r`}>{s.rules}</small>
        </button>
      ) : (
        <div className="rd-file" data-busy={busy || undefined}>
          {url && <img src={url} alt="" className="rd-img" />}
          <div className="rd-meta">
            <bdi dir="ltr" className="rd-name" title={file.name}>{file.name || 'receipt'}</bdi>
            <small dir="ltr">{sizeText(file.size, s)}</small>
            {busy ? (
              <div className="rd-prog" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress} aria-label={s.uploading}>
                <span className="rd-bar"><i style={{ width: `${progress}%` }} /></span><small dir="ltr">{progress}%</small>
              </div>
            ) : (
              <div className="rd-acts">
                <button type="button" className="rd-btn" onClick={open} disabled={disabled}>{s.change}</button>
                <button type="button" className="rd-btn rd-rm" onClick={() => { setErr(''); onChange(null) }} disabled={disabled} data-testid={`${testId}-remove`}>{s.remove}</button>
              </div>
            )}
          </div>
        </div>
      )}
      {err && <p className="rd-err" role="alert" data-testid={`${testId}-error`}>{err}</p>}
    </div>
  )
}

const RD_CSS = `
.rd { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.rd-l { font-size: 12.5px; font-weight: 700; }
.rd-zone { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; width: 100%; min-height: 118px; padding: 16px 12px;
  border-radius: 14px; border: 2px dashed var(--c-border); background: color-mix(in srgb, var(--c-primary, #1464BA) 4%, transparent); color: var(--c-text);
  cursor: pointer; text-align: center; font: inherit; transition: border-color .15s, background-color .15s; }
.rd-zone:hover:not(:disabled), .rd-zone[data-over] { border-color: var(--c-primary, #1464BA); background: color-mix(in srgb, var(--c-primary, #1464BA) 9%, transparent); }
.rd-zone:focus-visible { outline: 2px solid var(--c-primary, #1464BA); outline-offset: 2px; }
.rd-zone:disabled { opacity: .55; cursor: not-allowed; }
.rd-zone b { font-size: 14px; font-weight: 800; }
.rd-zone small { font-size: 12px; color: var(--c-muted-fg, var(--c-text-muted)); line-height: 1.6; }
.rd-ic { width: 30px; height: 30px; color: var(--c-primary, #1464BA); margin-bottom: 2px; }
.rd-rules { font-size: 11.5px !important; opacity: .9; }
.rd-file { display: flex; gap: 12px; align-items: center; padding: 10px; border-radius: 14px; border: 1px solid var(--c-border); min-width: 0;
  background: color-mix(in srgb, var(--c-text-muted, #888) 5%, transparent); }
.rd-img { width: 76px; height: 76px; flex-shrink: 0; border-radius: 10px; object-fit: cover; background: var(--c-bg); border: 1px solid var(--c-border); }
.rd-meta { display: flex; flex-direction: column; gap: 3px; min-width: 0; flex: 1 1 auto; }
.rd-name { font-size: 13px; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: start; display: block; }
.rd-meta small { font-size: 11.5px; color: var(--c-muted-fg, var(--c-text-muted)); text-align: start; }
.rd-acts { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px; }
.rd-btn { min-height: 36px; padding: 0 12px; border-radius: 10px; border: 1px solid var(--c-border); background: transparent; color: var(--c-text); font: inherit; font-size: 12.5px; font-weight: 700; cursor: pointer; }
.rd-btn:hover:not(:disabled) { background: color-mix(in srgb, var(--c-primary, #1464BA) 8%, transparent); }
.rd-rm { color: var(--c-danger-fg, var(--c-danger)); border-color: color-mix(in srgb, var(--c-danger) 35%, var(--c-border)); }
.rd-prog { display: flex; align-items: center; gap: 8px; margin-top: 6px; }
.rd-bar { flex: 1 1 auto; height: 8px; border-radius: 999px; overflow: hidden; background: color-mix(in srgb, var(--c-text-muted, #888) 18%, transparent); }
.rd-bar i { display: block; height: 100%; border-radius: inherit; background: var(--c-primary, #1464BA); transition: width .2s; }
.rd-err { font-size: 12.5px; font-weight: 700; line-height: 1.7; padding: 7px 10px; border-radius: 10px; color: var(--c-danger-fg, var(--c-danger));
  background: color-mix(in srgb, var(--c-danger) 10%, transparent); }
@media (max-width: 767px) { .rd-btn { min-height: 44px; } .rd-zone { min-height: 128px; } }
`
