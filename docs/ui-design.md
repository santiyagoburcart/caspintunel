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

- Glass layer: see **Liquid Glass** below — never put `.lg` on a content card.
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
- Admin: bottom nav (5 tabs, payments queue as the prominent centre action) + Settings hub (3D tiles) ≤767px.
- Sticky primary actions: Store "continue", Checkout "submit"; modals become bottom/full sheets.

### Phone density (≤767px)

Compact and information-dense; compactness comes from padding, rhythm and layout —
**tap targets stay ≥44px and inputs stay 16px** (the touch floor in `index.css` is untouched).

| | Size |
|---|---|
| Body / secondary | 14px / 12–13px (`--m-fs-body`, `--m-fs-2`; 12px is still the floor) |
| Section / page title | 17px / 20px (`main h1` is forced to 20px) |
| Big numbers (KPIs, amounts) | 18–20px |
| Card padding / gap | 14px / 12px (`--m-card-pad`, `--m-gap`; `.space-y-4`, `.gap-4` tighten inside `main`) |

Patterns:
- Hero / banner ≤ ~30% of the viewport: one title row + a 3-up KPI strip (user dashboard ≈19%).
- Records that were "one label: value line per field" are a **grid of label-over-value cells**
  under a full-width title row (`.rtable`, admin users, admin services).
- Secondary details fold away: the service card's "change link" sits behind a ⋯ disclosure,
  marketing leads are clamped/hidden, tips drop their descriptions, the dashboard filter bar
  hides for ≤3 services, the payment receipt becomes a 92px thumbnail beside the details.
- Numbers of fitting cards/rows per page are in PROGRESS.md (ui-refresh entry).

## Liquid Glass (floating layer)

Files: `src/styles/liquid.css` + `src/lib/glass.js` (identical in both SPAs, loaded by `main.jsx`).

### Principles (Apple HIG / developer docs)

1. **Glass is a functional layer that floats above content** — navigation and controls (tab
   bars, sidebars, toolbars, sheets, menus). *Don't use it in the content layer*; content uses
   standard (solid/frosted) materials. The exception is transient controls such as toggles and
   sliders, whose knob turns into glass while being pressed. — HIG *Materials*.
2. **Use it sparingly**; limit it to the most important functional elements, and don't layer
   glass on glass. — HIG *Materials*; *Adopting Liquid Glass* (Controls, "avoid overcrowding
   or layering Liquid Glass elements on top of each other").
3. **Regular variant for text-heavy surfaces** (sidebars, alerts, popovers): it blurs and
   adjusts the luminosity of what's behind; larger surfaces are more opaque to preserve
   legibility. Clear glass only over media (we have none → regular everywhere). — HIG
   *Materials*; HIG *Color* › Liquid Glass color.
4. **Content scrolls underneath the bars** with a **scroll-edge effect** keeping controls
   legible. — *Adopting Liquid Glass* (Controls, Navigation).
5. **Tab bars float** above content and can **minimize while scrolling down**, expanding on
   scroll up. — HIG *Tab bars*; *Adopting Liquid Glass* (Navigation).
6. **Concentric, rounder shapes**: controls nest into their containers; sheets have larger
   radii and half sheets are inset from the screen edge; full-height sheets become more
   opaque. — *Adopting Liquid Glass* (Controls, Windows and modals).
7. **Color sparingly**: glass takes its colour from content; tint only the primary action's
   background (prominent button), keep bar labels monochrome. — HIG *Color*.
8. **Accessibility adapts the material**: Reduce Transparency → frostier/opaque, Increase
   Contrast → stark borders, Reduce Motion → no elastic effects. — HIG *Materials*; WWDC25
   "Meet Liquid Glass".
9. **iOS/iPadOS 27 (2026)**: refinements for readability — more uniform refraction and improved
   contrast — and a user setting from ultra-clear to fully tinted. We sit at the legible,
   tinted end by default. — Apple Support "About iOS 27 Updates"; Apple Developer News
   "Design kits for iOS, iPadOS, and macOS 27" (June 2026). (No new HIG rules for web beyond
   this were published; HIG *Tab bars* changelog 2026-06-08: terminology/art only.)

Sources: developer.apple.com/design/human-interface-guidelines/materials · …/color ·
…/tab-bars · …/toolbars · …/sheets · developer.apple.com/documentation/technologyoverviews/adopting-liquid-glass ·
developer.apple.com/videos/play/wwdc2025/219 · support.apple.com/en-us/149076 ·
developer.apple.com/news/?id=e2lxw9l1

### What is glass, what stays solid

| Glass (regular) | Glass (strong tint) | Glass look without blur | Solid / lightly frosted |
|---|---|---|---|
| top bars (`.csp-topbar`, `.csp-mtop`, legacy `.lg-bar`, login headers), floating tab bars (`.u-botnav`, `.csp-botnav`), sticky action bars (`.m-actionbar`, `.st-solo-bar`, `.sed-mbar`), toast | admin sidebar/rail, drawers, ConfirmDialog + bottom sheets, notification panel, QR sheet | segmented tabs, toggle knob (while pressed), prominent centre tab, dropdowns inside a bar | every content card, table, form, KPI tile, full-screen page modals (opaque like a full-height sheet), scrims (dim only, never blurred) |

### Material

- Tint: `--lg-tint` = surface 90% (bars) / `--lg-tint-strong` 92% (text surfaces) +
  `blur(20px) saturate(180%)` + top sheen gradient + specular edge (inset top highlight, lower
  rim, hairline) + soft depth shadow. Concentric radii (`--lg-r-item` 22 + `--lg-pad` 6 = bar 28).
- **Readability proof**: `node scripts/ui-audit/glass-contrast.mjs` composites each tint over
  pure black and pure white (the exact luminance extremes of anything that can scroll
  underneath, blur or not) for every palette × mode and checks every text colour drawn on glass
  → 0 below AA. That is why the tints are 90/92% (84% failed: brand blue 4.06:1 over black).
  Labels on glass use `--lg-label` (muted mixed toward text); the selected tab uses
  `--lg-active-fg` (brand blue darkened in light mode) because it sits on a blue pill.
- Motion: spring easing `--lg-spring` for tab-bar minimize, knob, capsule; all off under
  `prefers-reduced-motion`.

### Tiers and low-end fallback (`html[data-glass]`)

| Tier | When | Looks |
|---|---|---|
| `full` | default | tint 90/92% + blur + saturation |
| `lite` | ≤4 GB RAM, ≤4 cores, Save-Data, no `backdrop-filter` support (JS + `@supports not`), **or slow frames measured on the device** (>25% of frames >34 ms while scrolling, remembered in `localStorage.ct_glass_perf`) | same shapes, sheen, rim and shadow, tint 95% / opaque, **no blur** |
| `solid` | `prefers-reduced-transparency: reduce` or `prefers-contrast: more` (followed live) | opaque surface, hairline border, no sheen |

Blur budget: at most **one** blurred bar at the top and one at the bottom (plus an open sheet).
Content cards no longer blur (Aurora-dark/Frost used to blur every card), scrims never blur,
and a dropdown inside a bar never blurs again. Override for support: `?glass=full|lite|solid`,
`?glass=auto` to reset.

### Checks

- `scripts/ui-audit/glass-contrast.mjs` — AA proof (no browser).
- `scripts/ui-audit/public-audit.mjs` — offline Playwright: logged-out pages × 5 theme variants ×
  fa/en × 360/390/768/1440 (contrast, overflow, <12px text, <44px targets, Persian digits,
  unnamed controls, page errors) + the glass runtime suite (tier selection for every
  heuristic, material per tier, scroll states, reduced motion, frame smoke test).

## Preview workflow

`./scripts/preview.sh update` builds this checkout for `/preview/` + `/preview-panel/` (banner,
live API, preview palettes) and serves it next to the live site; `remove` deletes it.
