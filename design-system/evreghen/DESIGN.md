# Evreghen Command Center Theme

## Purpose

Evreghen frames Leadroom as a calm command center: a warm, document-like workspace surrounded by dark translucent application chrome. Orange carries action and telemetry while neutral surfaces preserve scanning speed.

## Tokens

- Canvas: `#FCFAF7`
- Foreground: `#423D38`
- Muted foreground: `#797067`
- Surface: `#FFFFFF`
- Soft surface: `#F3F4F6`
- Outline: `#E3E0DD`
- Primary: `#FE6E00`
- Focus: `#F97015`
- Shell: black at approximately 76-78% opacity
- Success: `#00C758`
- Warning: `#EDB200`
- Danger: `#FB2C36`
- Information: `#3080FF`

## Type And Shape

- The native Segoe UI/system stack implements the source system's practical dashboard voice.
- Source Code Pro remains the workspace monospace for identifiers and runtime values.
- Existing responsive heading sizes are retained; hero-scale typography is not used in operational panels.
- Letter spacing remains zero for reliable compact rendering.
- Inputs and buttons use 6px radii. Cards and navigation use 8px radii. Badges may be pill-shaped.

## Layers

- Sidebar and workspace bar use translucent black with a 12px backdrop blur and faint white borders.
- Main content stays light and warm rather than becoming a dark dashboard.
- Cards use quiet borders and subtle shadows.
- Orange appears on active navigation, primary commands, focus rings, selection edges, and progress telemetry.

## Product Adaptation

The source onboarding split screen, oversized wordmark, charts, and status names are not introduced because Leadroom does not currently expose those product surfaces. Decorative gradients are excluded. Existing semantic states continue to use Leadroom's success, warning, error, and information components.

## Runtime Cost

Evreghen is a scoped CSS layer selected through `data-theme="evreghen"`. It adds no package, font, image, request, or animation loop.
