export function DataTable({ columns, rows, empty = '—' }) {
  return (
    <div className="card overflow-x-auto p-0">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-muted" style={{ borderBottom: '1px solid var(--c-border)' }}>
            {columns.map((c) => <th key={c.key} className="px-3 py-2 text-start font-medium">{c.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr><td colSpan={columns.length} className="px-3 py-6 text-center text-muted">{empty}</td></tr>
          )}
          {rows.map((r, i) => (
            <tr key={r.id ?? i} style={{ borderBottom: '1px solid var(--c-border)' }}>
              {columns.map((c) => (
                <td key={c.key} className="px-3 py-2">{c.render ? c.render(r) : r[c.key] ?? '—'}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
