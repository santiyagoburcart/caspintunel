// Domain & Cloudflare page: a failure in words (fa / en) with the fix + the raw code / message line
// a failure in words (fa / en) with the fix, and under it the raw code + message
export function Why({ info, lang, s, small }) {
  if (!info) return null
  return (
    <div className={`dm-why${small ? ' sm' : ''}`} role="alert">
      <p>{lang === 'en' ? info.en : info.fa}</p>
      {info.raw && <small className="dm-raw">{s.details}: <bdi dir="ltr">{info.raw}</bdi></small>}
    </div>
  )
}

export const yn = (v, s) => (v === true ? <span className="dm-y">✓ {s.yes}</span> : v === false ? <span className="dm-n">✕ {s.no}</span> : <span className="dm-u">? {s.na}</span>)

