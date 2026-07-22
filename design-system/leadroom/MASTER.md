# Leadroom Design System

**Product type:** Local B2B lead-discovery workspace  
**Design character:** Signal Desk - editorial, precise, locally trustworthy, dense without feeling cramped
**Updated:** 2026-07-14

## Product Principles

1. The primary workflow is `market -> previous-result strategy -> candidate review -> enrichment`.
2. Default settings should complete the common task. Technical controls belong under progressive disclosure.
3. Previously discovered domains must be explained before a search begins; repeat searches should never feel random.
4. Use one clear primary action per view. Secondary actions must remain visually subordinate.
5. Treat Leadroom as an operational app: use layout and dividers for structure, cards only for real interaction containers.

## Foundations

### Typography

- Primary family: **Public Sans Variable**, bundled locally through `@fontsource-variable/public-sans`.
- Page title: 34-52px / 0.98 / 680. Large type is reserved for the page masthead.
- Section title: 18px / 1.25 / 700.
- Body and supporting copy: 15-16px / 1.5.
- Form labels: 13px / 700.
- Data and table text: 14px with tabular numerals where appropriate.
- Technical values: SFMono-Regular or Consolas.
- Letter spacing stays at `0`.

### Color

| Role | Value | Token |
|---|---:|---|
| Canvas | `#F1F3F0` | `--canvas` |
| Surface | `#FFFFFF` | `--surface` |
| Ink | `#181C1B` | `--ink` |
| Muted text | `#66706D` | `--muted` |
| Border | `#D9DDDA` | `--line` |
| Strong border | `#B9C0BC` | `--line-strong` |
| Primary green | `#087A57` | `--green` |
| Primary dark | `#07583F` | `--green-dark` |
| Primary soft | `#DDF3E9` | `--green-soft` |
| Signal lime | `#BCE967` | navigation and local-state highlights |
| Processing blue | `#315ED1` | `--blue` |
| Human-attention coral | `#ED684A` | `--coral`, `--focus` |

Use blue for active processing, amber for queued/ready states, and red for failure or destructive actions. Never rely on color without text or an icon.

### Spacing

Use the 4/8px scale defined in `App.css`: `4, 8, 12, 16, 24, 32, 40, 48`.

### Shape And Elevation

- Controls: 4-5px radius. Structural surfaces remain square for a research-desk character.
- Status pills only: fully rounded.
- Prefer borders and spacing over shadows.
- Use medium/large shadows only for overlays such as the mobile navigation and lead drawer.

## Interaction

- Minimum pointer/touch target: 44x44px.
- All keyboard focus states must remain visible on the rendered control, including custom radio and checkbox containers.
- Micro-interactions: 150-220ms, animating only opacity and transform where possible.
- Route transitions should remain subtle and respect reduced-motion preferences.
- Dialogs open with focus inside, close with Escape, and expose `role="dialog"` plus `aria-modal="true"`.
- Tabs expose `role="tab"`, `aria-selected`, and a labelled tab panel.

## Responsive Rules

- Mobile: 375-620px. Prioritize the market form and primary action; stack discovery choices.
- Tablet: 621-900px. Use the mobile navigation drawer and preserve readable two-column forms when space allows.
- Desktop: 901px and above. Persistent 240px navigation and constrained working widths.
- No horizontal page scrolling at any supported viewport.
- Fixed overlays must account for safe areas and provide an explicit dismiss target.

## Component Decisions

- **Shell:** a persistent charcoal operations rail, a contextual workspace bar, and one highlighted active destination.
- **New run:** two visible decision groups beside a live dark search brief. Collection limits, provider, delay, and model stay in `Advanced settings`.
- **Runs:** an operational summary band precedes recent activity when data exists; the empty state keeps one action.
- **Settings:** read-only runtime values use definition rows; blocked domains use countable tags instead of comma-separated prose.
- **Lead details:** use a right-side modal drawer with explicit close behavior and evidence grouped before editing.
- **Motion:** use Motion for route continuity, the shared active-navigation indicator, list entry, and live-brief state changes; avoid decorative animation.

## Quality Gate

- Verify 375, 390, 768, 1024, and 1440px widths.
- Verify no horizontal overflow.
- Verify all visible primary interactions are at least 44px.
- Run lint, build, unit tests, Playwright desktop/mobile tests, and packaged-app smoke checks.
- Preserve offline behavior: fonts and required visual assets must be bundled locally.
