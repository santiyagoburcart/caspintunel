// Small stroke icons for the Agency pages and the reseller portal (identical copy
// in both SPAs). Decorative: always next to visible text, so aria-hidden.
const P = {
  sold: 'M3 3v18h18M7 15l4-4 3 3 6-7',
  used: 'M21 12a9 9 0 11-9-9v9h9z',
  remaining: 'M3 8h15v8H3zM21 11v2M6 11v2',
  hidden: 'M3 3l18 18M10.6 10.6a2 2 0 002.8 2.8M9.9 5.1A9.8 9.8 0 0112 5c5 0 9 4.5 9.9 7a11 11 0 01-2.6 3.8M6.2 6.2A11 11 0 002.1 12c.9 2.5 4.9 7 9.9 7a9.6 9.6 0 004.5-1.1',
  users: 'M17 20v-2a4 4 0 00-4-4H7a4 4 0 00-4 4v2M10 10a4 4 0 100-8 4 4 0 000 8zM21 20v-2a4 4 0 00-3-3.9M16 2.1a4 4 0 010 7.8',
  user: 'M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2M12 11a4 4 0 100-8 4 4 0 000 8z',
  status: 'M22 12h-4l-3 9L9 3l-3 9H2',
  usage: 'M12 14l4-4M3.3 17a9 9 0 1117.4 0',
  limit: 'M12 2l8 4v6c0 5-3.5 9-8 10-4.5-1-8-5-8-10V6z',
  wallet: 'M3 7h18v13H3zM16 14h2M3 7l3-4h12l3 4',
  clock: 'M12 7v5l3 2M12 22a10 10 0 100-20 10 10 0 000 20z',
  link: 'M10 13a5 5 0 007 0l3-3a5 5 0 00-7-7l-1 1M14 11a5 5 0 00-7 0l-3 3a5 5 0 007 7l1-1',
  copy: 'M8 8h12v12H8zM4 16V4h12',
  qr: 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h3v3h-3zM18 18h3v3h-3z',
  check: 'M5 13l4 4L19 7',
  plus: 'M12 5v14M5 12h14',
  edit: 'M4 20h4L19 9l-4-4L4 16zM14 6l4 4',
  trash: 'M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3',
  infinity: 'M6 16c-2.2 0-4-1.8-4-4s1.8-4 4-4c4 0 8 8 12 8 2.2 0 4-1.8 4-4s-1.8-4-4-4c-4 0-8 8-12 8z',
  power: 'M12 2v10M18.4 6.6a9 9 0 11-12.8 0',
  reset: 'M3 12a9 9 0 0115.5-6.2L21 8M21 3v5h-5M21 12a9 9 0 01-15.5 6.2L3 16M3 21v-5h5',
  gauge: 'M12 14l4-4M3.3 17a9 9 0 1117.4 0M12 14h.01',
  download: 'M12 3v12M7 10l5 5 5-5M4 21h16',
  tag: 'M3 12V3h9l9 9-9 9zM7.5 7.5h.01',
  money: 'M12 2v20M17 6.5C17 4.6 14.8 3.5 12 3.5S7 4.6 7 6.5 9.2 10 12 10.5s5 1.6 5 3.5-2.2 3.5-5 3.5-5-1.6-5-3.5',
  sliders: 'M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6',
  x: 'M6 6l12 12M18 6L6 18',
  logout: 'M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9',
  login: 'M15 3h4a2 2 0 012 2v14a2 2 0 01-2 2h-4M10 17l5-5-5-5M15 12H3',
  doc: 'M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8zM14 2v6h6M8 13h8M8 17h8',
  list: 'M4 6h16M4 12h16M4 18h10',
  globe: 'M12 22a10 10 0 100-20 10 10 0 000 20zM2 12h20M12 2a15 15 0 010 20M12 2a15 15 0 000 20',
  sync: 'M3 12a9 9 0 0115.5-6.2L21 8M21 3v5h-5M21 12a9 9 0 01-15.5 6.2L3 16M3 21v-5h5',
  alert: 'M12 9v4M12 17h.01M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z',
  more: 'M6 9l6 6 6-6',
  shield: 'M12 3l8 3v6c0 4.4-3.4 8.3-8 9-4.6-.7-8-4.6-8-9V6l8-3z',
  bell: 'M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 01-3.4 0',
  key: 'M15 7a4 4 0 11-3.9 4.9L3 20v-3h3v-3h3l2.1-2.1A4 4 0 0115 7z',
  server: 'M4 4h16v6H4zM4 14h16v6H4zM8 7h.01M8 17h.01',
}

export function Ic({ n, size = 15, className = '' }) {
  return (
    <svg className={'agi ' + className} viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d={P[n] || P.list} />
    </svg>
  )
}

// accent colours (icons, KPI tiles, header icons). Light values >= 4.5:1 on white,
// dark values >= 7:1 on the dark surfaces; `.dark` swaps them.
export const ACCENT_CSS = `
.ag, .ap { --ac-blue: #1464BA; --ac-purple: #6D28D9; --ac-green: #0E7A3E; --ac-orange: #B45309; --ac-gray: #475569; --ac-red: #B91C1C; --ac-cyan: #0E7490; }
.dark .ag, .dark .ap, .ap.ap-dark { --ac-blue: #7DB3EE; --ac-purple: #B9A3FF; --ac-green: #5EE29A; --ac-orange: #FBBF24; --ac-gray: #A3AEC0; --ac-red: #FCA5A5; --ac-cyan: #67E8F9; }
.agi { flex-shrink: 0; vertical-align: -2px; }
[data-ac="blue"] { --ac: var(--ac-blue); } [data-ac="purple"] { --ac: var(--ac-purple); } [data-ac="green"] { --ac: var(--ac-green); }
[data-ac="orange"] { --ac: var(--ac-orange); } [data-ac="gray"] { --ac: var(--ac-gray); } [data-ac="red"] { --ac: var(--ac-red); } [data-ac="cyan"] { --ac: var(--ac-cyan); }
`
