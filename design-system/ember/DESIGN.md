# Ember Studio Theme

## Purpose

Ember Studio gives Leadroom a calm craft-focused workspace. Warm stone surfaces and terracotta interaction are paired with restrained serif headings so the interface feels intentional without becoming decorative or less efficient.

## Tokens

- Canvas: `#FAFAF9`
- Surface: `#F5F5F4`
- Raised surface: `#E7E5E4`
- Foreground: `#1C1917`
- Secondary text: `#57534E`
- Border: `#D6D3D1`
- Primary terracotta: `#C2410C`
- Primary hover: `#9A3412`
- Amber attention: `#F59E0B`
- Success: `#16A34A`
- Warning: `#D97706`
- Error: `#DC2626`

## Type And Shape

- Georgia provides a local, zero-download serif voice for headings in place of Playfair Display.
- Public Sans, already bundled, replaces Source Sans 3 for UI copy.
- Source Code Pro, already bundled, replaces Fira Code.
- Letter spacing remains zero and existing responsive sizes are retained.
- Buttons, inputs, cards, and panels use an 8px radius. Compact chips and status badges may be pill-shaped.

## Interaction

- Terracotta is limited to commands, active navigation, links, focus, progress, and selected-item edges.
- Amber remains a semantic attention color rather than decoration.
- Selected rows and cards use the raised stone surface with a restrained 2px terracotta left edge.
- Hover elevation is limited to interactive cards and controls.
- Reduced-motion preferences remove optional transitions.

## Component Language

- Page headers use a quiet editorial rule to establish hierarchy without a marketing-style hero.
- Primary workspace tabs use the specified terracotta underline treatment instead of segmented cards.
- Run, repository, and local-index metrics use warm stone cells with terracotta reserved for the active metric.
- Operational summaries and active collection controls use warm charcoal with amber signals, creating a crafted dark counterpoint without turning the whole shell dark.
- Candidate cards use a raised stone surface and a 2px terracotta edge; repository collection tabs use the documented underline treatment.
- Navigation, tabs, cards, chips, and checkboxes keep distinct selected states instead of sharing one rounded tinted container.
- The local-data engine uses a deep warm-stone console with terracotta and amber signals rather than the base theme's green-black treatment.
- Outreach forms, audit rows, drawers, evidence links, and compliance states receive dedicated Ember surfaces and semantic borders.

## Product Adaptation

Google Fonts are intentionally not requested, avoiding startup delay, offline failure, and extra weight. The source system's 48-64px editorial heading scale is not used inside Leadroom's operational pages. Pure white and black are avoided in the theme layer in favor of the supplied warm palette.

## Runtime Cost

Ember Studio is a scoped CSS layer selected through `data-theme="ember"`. It adds no package, font, image, request, or animation loop.
