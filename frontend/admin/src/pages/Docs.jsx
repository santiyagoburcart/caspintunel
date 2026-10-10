import { Fragment, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, apiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { Alert, Spinner } from '../components/ui'

const T = {
  fa: {
    title: 'مستندات', sub: 'راهنماهای پوشهٔ docs/ مخزن — فقط خواندنی',
    search: 'جستجو در همهٔ مستندات…', toc: 'فهرست مطالب', pages: 'صفحه‌ها',
    no_hits: 'نتیجه‌ای پیدا نشد.', hits: '{n} نتیجه', empty: 'مستنداتی روی سرور پیدا نشد.', clear: 'پاک کردن جستجو',
  },
  en: {
    title: 'Documentation', sub: 'Guides from the repo’s docs/ folder — read-only',
    search: 'Search all docs…', toc: 'Contents', pages: 'Pages',
    no_hits: 'No results.', hits: '{n} results', empty: 'No documentation found on the server.', clear: 'Clear search',
  },
}

const slugify = (s) => s.toLowerCase().replace(/[`*_[\]()]/g, '').trim().replace(/[^\p{L}\p{N}]+/gu, '-').replace(/^-|-$/g, '')

// --- tiny markdown → React (no HTML is ever injected) ------------------------------
function inline(text, key = 'i') {
  const out = []
  const re = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\[[^\]]+\]\([^)\s]+\))|(\*[^*\s][^*]*\*)|(https?:\/\/[^\s)<]+)/g
  let last = 0, m, n = 0
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index))
    const k = `${key}-${n++}`
    const tok = m[0]
    if (m[1]) out.push(<code key={k}>{tok.slice(1, -1)}</code>)
    else if (m[2]) out.push(<strong key={k}>{inline(tok.slice(2, -2), k)}</strong>)
    else if (m[3]) {
      const [, label, href] = tok.match(/^\[([^\]]+)\]\(([^)\s]+)\)$/)
      out.push(<DocLink key={k} href={href}>{inline(label, k)}</DocLink>)
    } else if (m[4]) out.push(<em key={k}>{inline(tok.slice(1, -1), k)}</em>)
    else out.push(<DocLink key={k} href={tok}>{tok}</DocLink>)
    last = m.index + tok.length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

function DocLink({ href, children }) {
  const local = href.match(/^(?:\.\/)?([a-z0-9_-]+)\.md(#.*)?$/i)
  if (local) return <Link to={`/docs/${local[1].toLowerCase()}${local[2] || ''}`}>{children}</Link>
  if (href.startsWith('#')) return <a href={href}>{children}</a>
  if (/^https?:\/\//.test(href)) return <a href={href} target="_blank" rel="noreferrer noopener">{children}</a>
  return <code>{children}</code>          // repo paths: shown, not linked
}

function parse(md) {
  const lines = md.replace(/\r/g, '').split('\n')
  const blocks = []
  let i = 0
  while (i < lines.length) {
    const l = lines[i]
    if (/^```/.test(l)) {
      const body = []; i++
      while (i < lines.length && !/^```/.test(lines[i])) body.push(lines[i++])
      i++; blocks.push({ t: 'code', body: body.join('\n') }); continue
    }
    const h = l.match(/^(#{1,4})\s+(.*)$/)
    if (h) { blocks.push({ t: 'h', level: h[1].length, text: h[2].trim() }); i++; continue }
    if (/^\s*(---|\*\*\*)\s*$/.test(l)) { blocks.push({ t: 'hr' }); i++; continue }
    if (/^\|.*\|\s*$/.test(l) && i + 1 < lines.length && /^\|?\s*:?-{2,}/.test(lines[i + 1])) {
      const cells = (row) => {          // split on | outside `code` (tables here hold `a|b` options)
        const out = ['']; let tick = false
        for (const ch of row.trim().replace(/^\||\|$/g, '')) {
          if (ch === '`') tick = !tick
          if (ch === '|' && !tick) out.push(''); else out[out.length - 1] += ch
        }
        return out.map((c) => c.trim())
      }
      const head = cells(l); i += 2
      const rows = []
      while (i < lines.length && /^\|.*\|\s*$/.test(lines[i])) rows.push(cells(lines[i++]))
      blocks.push({ t: 'table', head, rows }); continue
    }
    if (/^>\s?/.test(l)) {
      const body = []
      while (i < lines.length && /^>\s?/.test(lines[i])) body.push(lines[i++].replace(/^>\s?/, ''))
      blocks.push({ t: 'quote', text: body.join(' ') }); continue
    }
    const li = l.match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/)
    if (li) {
      const ordered = /\d/.test(li[2])
      const items = []
      while (i < lines.length) {
        const m = lines[i].match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/)
        if (m) { items.push({ depth: m[1].length >= 2 ? 1 : 0, text: m[3].replace(/^\[ \]\s+/, '☐ ').replace(/^\[x\]\s+/i, '☑ ') }); i++; continue }
        if (/^\s{2,}\S/.test(lines[i]) && items.length) { items[items.length - 1].text += ' ' + lines[i].trim(); i++; continue }
        break
      }
      blocks.push({ t: 'list', ordered, items }); continue
    }
    if (!l.trim()) { i++; continue }
    const para = []
    while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|```|>|\s*([-*+]|\d+[.)])\s|\|)/.test(lines[i])) para.push(lines[i++].trim())
    if (!para.length) para.push(lines[i++].trim())
    blocks.push({ t: 'p', text: para.join(' ') })
  }
  return blocks
}

function Markdown({ blocks }) {
  return blocks.map((b, n) => {
    const k = `b${n}`
    if (b.t === 'h') {
      const H = `h${Math.min(b.level + 1, 5)}`
      return <H key={k} id={slugify(b.text)} className={`dc-h dc-h${b.level}`}>{inline(b.text, k)}</H>
    }
    if (b.t === 'code') return <pre key={k} className="dc-pre" dir="ltr"><code>{b.body}</code></pre>
    if (b.t === 'hr') return <hr key={k} className="dc-hr" />
    if (b.t === 'quote') return <blockquote key={k} className="dc-quote">{inline(b.text, k)}</blockquote>
    if (b.t === 'table') return (
      <div key={k} className="dc-table-wrap"><table className="dc-table">
        <thead><tr>{b.head.map((c, j) => <th key={j}>{inline(c, `${k}h${j}`)}</th>)}</tr></thead>
        <tbody>{b.rows.map((r, j) => <tr key={j}>{r.map((c, x) => <td key={x}>{inline(c, `${k}r${j}${x}`)}</td>)}</tr>)}</tbody>
      </table></div>
    )
    if (b.t === 'list') {
      const L = b.ordered ? 'ol' : 'ul'
      return <L key={k} className="dc-list">{b.items.map((it, j) => <li key={j} className={it.depth ? 'dc-li-sub' : ''}>{inline(it.text, `${k}l${j}`)}</li>)}</L>
    }
    return <p key={k} className="dc-p">{inline(b.text, k)}</p>
  })
}

function plain(s) { return s.replace(/[`*#>|]/g, '').replace(/\[([^\]]+)\]\([^)]+\)/g, '$1') }

export default function Docs() {
  const { lang } = useI18n()
  const s = T[lang] || T.fa
  const { slug } = useParams()
  const nav = useNavigate()
  const [list, setList] = useState(null)
  const [pages, setPages] = useState({})            // slug -> {title, markdown}
  const [err, setErr] = useState('')
  const [q, setQ] = useState('')

  useEffect(() => {
    api.get('/admin/docs/').then(async (r) => {
      setList(r.data)
      const all = await Promise.all(r.data.map((d) => api.get(`/admin/docs/${d.slug}/`).then((x) => [d.slug, x.data]).catch(() => null)))
      setPages(Object.fromEntries(all.filter(Boolean)))
    }).catch((e) => { setErr(apiError(e)); setList([]) })
  }, [])

  const current = slug || list?.[0]?.slug
  const page = pages[current]
  const blocks = useMemo(() => (page ? parse(page.markdown) : []), [page])
  const toc = blocks.filter((b) => b.t === 'h' && b.level >= 2 && b.level <= 3)

  useEffect(() => {          // jump to #anchor once the page is rendered
    const id = decodeURIComponent(window.location.hash.slice(1))
    if (id && page) requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ block: 'start' }))
  }, [page])

  const hits = useMemo(() => {
    const term = q.trim().toLowerCase()
    if (term.length < 2) return null
    const out = []
    for (const d of list || []) {
      const p = pages[d.slug]
      if (!p) continue
      let section = ''
      for (const line of p.markdown.split('\n')) {
        const h = line.match(/^#{1,4}\s+(.*)$/)
        if (h) section = h[1].trim()
        if (line.toLowerCase().includes(term)) out.push({ slug: d.slug, doc: d.title, section, text: plain(line).trim().slice(0, 160) })
        if (out.length >= 60) return out
      }
    }
    return out
  }, [q, list, pages])

  if (!list) return <div className="grid place-items-center py-16"><Spinner /></div>

  return (
    <div className="dc space-y-4">
      <style>{CSS}</style>
      <div>
        <h1 className="text-lg font-bold">{s.title}</h1>
        <p className="text-sm text-muted mt-1">{s.sub}</p>
      </div>
      <Alert>{err}</Alert>
      {!list.length && !err && <div className="card text-sm text-muted">{s.empty}</div>}

      {list.length > 0 && (
        <div className="dc-grid">
          <aside className="dc-side">
            <div className="dc-search">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" />
              </svg>
              <input type="search" className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder={s.search} aria-label={s.search} />
              {q && <button type="button" className="dc-x" onClick={() => setQ('')} aria-label={s.clear}>×</button>}
            </div>
            <nav className="dc-pages" aria-label={s.pages}>
              {list.map((d) => (
                <Link key={d.slug} to={`/docs/${d.slug}`} onClick={() => setQ('')}
                  className={'dc-page' + (d.slug === current ? ' is-on' : '')} aria-current={d.slug === current ? 'page' : undefined}>
                  {d.title}
                </Link>
              ))}
            </nav>
            {!hits && toc.length > 0 && (
              <details className="dc-toc" open={typeof window !== 'undefined' && window.matchMedia('(min-width: 900px)').matches}>
                <summary>{s.toc}</summary>
                {toc.map((b, j) => (
                  <a key={j} href={`#${slugify(b.text)}`} className={b.level === 3 ? 'dc-toc-sub' : ''}
                    onClick={(e) => { e.preventDefault(); document.getElementById(slugify(b.text))?.scrollIntoView({ behavior: 'smooth' }); nav(`/docs/${current}#${slugify(b.text)}`, { replace: true }) }}>
                    {plain(b.text)}
                  </a>
                ))}
              </details>
            )}
          </aside>

          <article className="card dc-body" dir={!hits && /-fa$/.test(current || '') ? 'rtl' : 'ltr'}>
            {hits ? (
              <div className="dc-hits">
                <div className="text-xs text-muted mb-2" dir="auto">{hits.length ? s.hits.replace('{n}', hits.length) : s.no_hits}</div>
                {hits.map((h, j) => (
                  <Link key={j} className="dc-hit" onClick={() => setQ('')}
                    to={`/docs/${h.slug}${h.section ? '#' + slugify(h.section) : ''}`}>
                    <span className="dc-hit-where">{h.doc}{h.section ? ` › ${plain(h.section)}` : ''}</span>
                    <span className="dc-hit-text">{h.text}</span>
                  </Link>
                ))}
              </div>
            ) : page ? <Markdown blocks={blocks} /> : <div className="grid place-items-center py-10"><Spinner /></div>}
          </article>
        </div>
      )}
    </div>
  )
}

const CSS = `
.dc-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 14px; align-items: start; }
@media (min-width: 900px) { .dc-grid { grid-template-columns: 240px minmax(0, 1fr); } .dc-side { position: sticky; top: 12px; } }
.dc-side { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.dc-search { position: relative; display: flex; align-items: center; }
.dc-search svg { position: absolute; inset-inline-start: 11px; color: var(--c-text-muted); pointer-events: none; }
.dc-search .input { padding-inline-start: 34px; padding-inline-end: 34px; width: 100%; }
.dc-x { position: absolute; inset-inline-end: 4px; width: 36px; height: 36px; border: 0; background: none; color: var(--c-text-muted); font-size: 20px; cursor: pointer; }
.dc-pages { display: flex; flex-direction: column; gap: 2px; }
.dc-page { padding: 8px 10px; border-radius: 9px; font-size: 13px; font-weight: 600; color: var(--c-text); text-decoration: none; }
.dc-page:hover { background: color-mix(in srgb, var(--c-text-muted) 10%, transparent); }
.dc-page.is-on { background: color-mix(in srgb, var(--c-primary) 13%, transparent); color: var(--c-primary-fg); }
.dc-toc { border-top: 1px solid var(--c-border); padding-top: 8px; display: flex; flex-direction: column; }
.dc-toc summary { font-size: 12px; font-weight: 700; color: var(--c-text-muted); cursor: pointer; padding: 4px 2px; }
.dc-toc a { display: block; font-size: 12.5px; padding: 4px 10px; color: var(--c-text-muted); text-decoration: none; unicode-bidi: plaintext; text-align: start; }
.dc-toc a:hover { color: var(--c-text); }
.dc-toc .dc-toc-sub { padding-left: 22px; font-size: 12px; }
.dc-body { padding: 20px 24px; min-width: 0; text-align: left; font-family: Inter, Vazirmatn, sans-serif; font-size: 14px; line-height: 1.65; }
.dc-body[dir="rtl"] { text-align: right; font-family: Vazirmatn, Inter, sans-serif; line-height: 1.9; }
.dc-body[dir="rtl"] .dc-list { padding-left: 0; padding-right: 22px; }
.dc-body[dir="rtl"] .dc-li-sub { margin-left: 0 !important; margin-right: 18px !important; }
.dc-body[dir="rtl"] .dc-table th, .dc-body[dir="rtl"] .dc-table td { text-align: right; }
.dc-body[dir="rtl"] .dc-quote { border-left: 0; border-right: 3px solid var(--c-primary); border-radius: 8px 0 0 8px; }
.dc-body[dir="rtl"] code { direction: ltr; unicode-bidi: isolate; }
.dc-body a { color: var(--c-primary-fg); text-decoration: underline; text-underline-offset: 2px; }
.dc-h { font-weight: 800; line-height: 1.3; scroll-margin-top: 70px; }
.dc-h1 { font-size: 22px; margin: 0 0 12px; }
.dc-h2 { font-size: 17px; margin: 22px 0 8px; padding-top: 12px; border-top: 1px solid var(--c-border); }
.dc-h3 { font-size: 15px; margin: 16px 0 6px; }
.dc-h4 { font-size: 14px; margin: 12px 0 4px; }
.dc-p { margin: 8px 0; }
.dc-body code { font-family: 'JetBrains Mono', monospace; font-size: 12.5px; padding: 1px 5px; border-radius: 5px;
  background: color-mix(in srgb, var(--c-text-muted) 13%, transparent); overflow-wrap: anywhere; }
.dc-pre { margin: 10px 0; padding: 12px 14px; border-radius: 10px; overflow-x: auto; background: color-mix(in srgb, var(--c-text-muted) 11%, var(--c-bg));
  border: 1px solid var(--c-border); }
.dc-pre code { padding: 0; background: none; font-size: 12.5px; white-space: pre; overflow-wrap: normal; }
.dc-list { margin: 8px 0; padding-left: 22px; }
.dc-list { list-style: disc; } ol.dc-list { list-style: decimal; }
.dc-list li { margin: 3px 0; }
.dc-li-sub { margin-left: 18px !important; list-style: circle; }
.dc-quote { margin: 10px 0; padding: 8px 12px; border-left: 3px solid var(--c-primary); background: color-mix(in srgb, var(--c-primary) 7%, transparent); border-radius: 0 8px 8px 0; }
.dc-hr { border: 0; border-top: 1px solid var(--c-border); margin: 16px 0; }
.dc-table-wrap { overflow-x: auto; margin: 10px 0; }
.dc-table { border-collapse: collapse; font-size: 13px; min-width: 100%; }
.dc-table th, .dc-table td { border: 1px solid var(--c-border); padding: 6px 10px; text-align: left; vertical-align: top; }
.dc-table th { background: color-mix(in srgb, var(--c-text-muted) 9%, transparent); font-weight: 700; }
.dc-hits { display: flex; flex-direction: column; gap: 6px; }
.dc-hit { display: flex; flex-direction: column; gap: 2px; padding: 9px 11px; border-radius: 10px; border: 1px solid var(--c-border); text-decoration: none !important; color: var(--c-text) !important; }
.dc-hit:hover { border-color: var(--c-primary); }
.dc-hit-where { font-size: 11.5px; font-weight: 700; color: var(--c-primary-fg); }
.dc-hit-text { font-size: 13px; overflow-wrap: anywhere; }
@media (max-width: 767px) {
  .dc-body { padding: 14px; font-size: 14px; }
  .dc-pages { flex-direction: row; overflow-x: auto; gap: 6px; padding-bottom: 2px; }
  .dc-page { white-space: nowrap; border: 1px solid var(--c-border); min-height: 40px; display: flex; align-items: center; }
  .dc-search .input { font-size: 16px; }
}
`
