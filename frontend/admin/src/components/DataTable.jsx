import { EmptyState } from './Art'

export function DataTable({ columns, rows, empty = '—', emptyArt = 'inbox' }) {
  return (
    <div className="card overflow-x-auto p-0 rtable-wrap">
      <table className="w-full text-sm rtable">
        <thead>
          <tr className="text-muted" style={{ borderBottom: '1px solid var(--c-border)' }}>
            {columns.map((c) => <th key={c.key} scope="col" className="px-3 py-2.5 text-start text-xs font-semibold">{c.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr><td colSpan={columns.length} className="px-3 py-2"><EmptyState art={emptyArt} text={empty} compact /></td></tr>
          )}
          {rows.map((r, i) => (
            <tr key={r.id ?? i} style={{ borderBottom: '1px solid var(--c-border)' }}>
              {columns.map((c) => (
                <td key={c.key} className="px-3 py-2.5" data-label={typeof c.label === 'string' ? c.label : undefined}>{c.render ? c.render(r) : r[c.key] ?? '—'}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
