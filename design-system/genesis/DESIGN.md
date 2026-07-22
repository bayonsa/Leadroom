# Genesis Theme

Genesis is an editorial precision theme adapted for Leadroom from the supplied Genesis design-system brief.

## Runtime approach

- Implemented as CSS custom-property and selector overrides in `frontend/src/Themes.css`.
- Uses the fonts already bundled with Leadroom: Public Sans for display, DM Sans for UI text, and Source Code Pro for code.
- Adds no runtime dependency, remote font request, image, gradient, or illustration.
- Keeps Leadroom's shared layout, component behavior, responsive rules, and handwritten metric numerals.

## Tokens

- Primary: `#6366F1`; hover: `#4F46E5`
- Canvas: `#FAFAFA`; surface: `#FFFFFF`
- Ink: `#0A0A0A`; muted: `#6B6B6B`
- Border: `#E8E8EC`
- Success: `#10B981`; warning: `#F59E0B`; error: `#EF4444`
- Buttons and inputs: 6px radius
- Panels and dropdowns: 8px radius
- Major framed surfaces: 12px radius
- Static surfaces remain flat; hover and popover elevation use restrained shadows.
- Focus uses an indigo 3px ring.

## Product adaptations

The source brief describes a community marketplace with a sticky top navigation, kit galleries, and global command search. Those are product-layout patterns rather than theme tokens, so they are intentionally excluded. Leadroom retains its operational sidebar, tables, run workflow, repository, and responsive behavior.
