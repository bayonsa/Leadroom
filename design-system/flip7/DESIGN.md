# Flip7 Theme

## Purpose

Flip7 adapts a retro-playful game system into a focused Leadroom workspace. It keeps the source system's teal, coral, gold, cream surfaces, tactile feedback, and compact rounded geometry without turning operational screens into a game.

## Tokens

- Canvas: `#EFF8F7`
- Surface: `#FFFFFF`
- Input surface: `#FFF8E7`
- Primary teal: `#2BA8A2`
- Deep teal: `#1E8C86`
- Gold action: `#FFD23F`
- Coral emphasis: `#EF6C4A`
- Information: `#5DADE2`
- Success: `#27AE60`
- Error: `#E74C3C`
- Text: `#153B39`

## Type And Shape

- Public Sans, already bundled with Leadroom, replaces the source system's generic system stack.
- Source Code Pro remains reserved for domains, identifiers, and runtime values.
- Headings use weight 800 with zero letter spacing.
- Controls, panels, cards, and previews use an 8px radius.
- Badges and domain tags may use a pill shape because they are compact status objects rather than commands.

## Interaction

- Primary commands use gold with dark text.
- Navigation and selection use teal.
- Coral is reserved for urgency and energetic emphasis.
- Interactive elevation uses subtle teal or gold shadows.
- Press feedback is limited to a short scale transition; all continuous game animations are omitted.
- Reduced-motion preferences remove optional transitions.

## Product Adaptation

The following source concepts are intentionally excluded:

- Confetti, crowns, victory podiums, and score celebrations
- Emoji section markers
- Decorative fan cards and folded ribbons
- Pulsing or infinite glow animation
- Decorative gradients

These patterns fit a scoring game but would reduce scan speed and information density in a lead operations product. Flip7 instead applies the same personality through color, tactile focus states, dashed section separators, and colored card accents.

## Runtime Cost

The theme is a scoped CSS layer selected through `data-theme="flip7"`. It adds no JavaScript package, image, font, network request, or runtime animation loop.
