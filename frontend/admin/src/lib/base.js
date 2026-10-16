// Where the admin panel lives (docs/paths.md). nginx injects
// <meta name="ct-admin-base" content="/x"> (and <base href="/x/"> for the relative
// asset URLs); without it (dev server) the panel is on /panel.
export const ADMIN_BASE = (document.querySelector('meta[name="ct-admin-base"]')?.content || '/panel').replace(/\/+$/, '')
