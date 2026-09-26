# UI design system (ui-refresh)

Applies to both SPAs (`frontend/user`, `frontend/admin`). Built with the
ui-ux-pro-max guidelines: WCAG AA contrast, 44px touch targets, visible focus,
reduced motion, mobile-first.

## Tokens (`src/index.css`, identical head in both apps)

| Group | Tokens |
|---|---|
| Colour roles (palette-driven) | `--c-bg --c-surface --c-primary --c-secondary --c-success --c-danger --c-warning --c-text --c-text-muted --c-border` |
| Text-safe roles (≥4.5:1 on bg, surface and tinted badges) | `--c-primary-fg --c-success-fg --c-danger-fg --c-warning-fg --c-secondary-fg` |
| Derived | `--c-on-primary --c-success-strong` (white text on green) `--c-surface-solid` (sheets) `--c-input-border` (≥3:1 boundary) `--c-hover --c-primary-soft` |
| Fixed | `--toggle-on #11AB53` / `--toggle-off` dark gray |
| Charts (only place for purple) | `--chart-1 … --chart-6` |
| Spacing (4pt) | `--sp-1 … --sp-12` |
| Radius | `--r-xs … --r-2xl --r-full` |
| Elevation | `--sh-1 --sh-2 --sh-3 --sh-primary` |
| Type | `--fs-xs 12px` (minimum anywhere) … `--fs-2xl`, `--lh-base 1.6` |
| Motion | `--dur-1/2/3 --ease-out --ease-in` (all disabled under `prefers-reduced-motion`) |
| Touch / focus / layers | `--touch 44px --ring --z-*` |

Rules:
- **Text in a role colour uses the `-fg` variant** (`color: var(--c-success-fg)`), never the
  brand fill. Fills (buttons, dots, bars, toggles) use the brand colour. `lib/tone.js::fg()`
  converts a computed tone for text.
- Palettes live in `backend/apps/settings_app/theme_palettes.json` (seed writes them to the DB
  on deploy; the preview build bundles the same file). Brand: primary `#1464BA`, success
  `#11AB53`, danger `#DC2626`, warning `#F59E0B`, near-black text; dark themes share accents.
- Minimum font size 12px; inputs 16px on phones (no iOS zoom).

## Components

- `.btn .btn-primary .btn-ghost .btn-soft .btn-danger .btn-success .icon-btn` — 40px desktop,
  44px on phones/touch; press scale; `.btn-spin` for loading.
- `.input .label .hint` — 44px, strong boundary, focus ring, `aria-invalid` styling.
  `Field` renders a real `<label>` (use `group` for option groups).
- `.badge .badge-{success,danger,warning,primary}` — dot + label (status never colour-only).
- `.toggle` — 44px hit area. `.csp-tabs` scrollable pill tabs.
- `.m-actionbar` — on phones the primary action sticks above the bottom nav
  (`--bottomnav-h`); on desktop it is `display: contents`.
- `Art`, `ArtTile`, `EmptyState` (`components/Art.jsx`) — 3D illustrations + empty states.
- `.skeleton`, `.dir-arrow` (forward arrow that flips in RTL).
- Phones and coarse pointers get a 44px floor for every button/input/standalone link.

## Icons and illustrations (bundled, offline, commercial-use OK)

| Asset | Where | Source | Licence |
|---|---|---|---|
| UI icons | everywhere (`@phosphor-icons/react`, tree-shaken) | Phosphor Icons 2.1 — phosphoricons.com | MIT |
| 3D illustrations (44 × 128px WebP, ~3 KB each) | `src/assets/3d/*.webp` | Microsoft Fluent Emoji 3D — github.com/microsoft/fluentui-emoji | MIT (`src/assets/3d/LICENSE.txt`) |

3D art is decorative (`alt=""`, `aria-hidden`) and used for accents only — never as a control.
No emoji characters are used as icons.

## Mobile

- User site: bottom tab bar (Home, Store, History, Help, Profile) ≤999px; Rules in the menu.
- Admin: bottom nav (5 tabs, raised payments button) + Settings hub (3D tiles) ≤767px.
- Sticky primary actions: Store "continue", Checkout "submit"; modals become bottom/full sheets.

## Preview workflow

`./scripts/preview.sh update` builds this checkout for `/preview/` + `/preview-panel/` (banner,
live API, preview palettes) and serves it next to the live site; `remove` deletes it.
