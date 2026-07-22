# RawBlock Theme

## Purpose

RawBlock brings a strict brutalist mode to Leadroom. Hierarchy comes from black and white inversion, border weight, and typography rather than shadows, color decoration, or rounded surfaces.

## Tokens

- Canvas and surface: `#FFFFFF`
- Inverted surface, text, and borders: `#000000`
- Input surface: `#F0F0F0`
- Link and information: `#0000FF`
- Success: `#008000`
- Warning: `#FFA500`
- Error: `#FF0000`

## Type And Geometry

- Public Sans, already bundled with Leadroom, stands in for Archivo Black and Work Sans.
- Source Code Pro, also already bundled, stands in for Space Mono.
- Headings use the existing responsive scale with weight 900. The source system's 48-64px headings are not used inside operational panels.
- Letter spacing remains zero to preserve readability.
- All visual containers and controls use a zero radius. Native radio controls remain circular.
- Borders range from 2px for compact status objects to 5px for focus and high importance.

## Interaction

- Primary actions are black with white text and invert on hover.
- Secondary actions invert from white to black.
- Selection uses a complete black surface inversion.
- Inputs use grey fill, a 3px border, and a 5px focus border.
- Links alone may use pure blue.
- No shadows, gradients, opacity-based disabled states, or decorative animation are used.

## Product Adaptation

Leadroom retains familiar Lucide icons because they materially improve scanning and command recognition in a repeated-use tool. Deliberately irregular spacing and oversized portfolio typography are excluded because they would damage table alignment, responsive behavior, and lead comparison.

## Runtime Cost

RawBlock is a scoped CSS layer selected through `data-theme="rawblock"`. It adds no package, font, image, network request, or animation loop.
