// Runtime paths injected by nginx (docs/paths.md): the reseller portal path, and
// the admin-panel link — only present while the admin panel is on its default
// path (a custom admin path is never revealed on the public site).
const meta = (name) => document.querySelector(`meta[name="${name}"]`)?.getAttribute('content')
const m = meta('ct-portal-path')
export const PORTAL_PATH = ((m == null ? '/agency' : m) || '/agency').replace(/\/+$/, '')
const a = meta('ct-admin-link')
export const ADMIN_LINK = a == null ? '/panel/' : a      // '' = hide the link
