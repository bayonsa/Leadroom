# Vercel Interface Theme

## Purpose

This theme adapts the supplied Vercel interface guidance to Leadroom's dense operational workspace. It uses engineered monochrome surfaces, crisp shadow borders, deliberate focus states, and a small workflow accent palette.

## Tokens

- Canvas and surface: `#FFFFFF`
- Primary text: `#171717`
- Secondary text: `#666666`
- Subtle surface: `#FAFAFA`
- Divider: `#EAEAEA`
- Develop blue: `#0A72EF`
- Preview pink: `#DE1D8D`
- Ship red: `#FF5B4F`
- Focus blue: `#0070F3`

## Component Language

- Cards and inputs use layered shadow borders rather than heavy CSS borders.
- Navigation is flat and monochrome; active state uses increased contrast and a crisp black edge.
- Tabs use a black underline and never become filled rounded controls.
- Metrics use tabular numerals; workflow colors are limited to meaningful data signals.
- Buttons keep native action semantics and icon-only controls retain accessible labels.
- Motion is limited to transform and opacity and honors reduced-motion preferences.

## Product Adaptation

- Public Sans substitutes for Geist Sans and Source Code Pro substitutes for Geist Mono, avoiding another font payload.
- Letter spacing stays at zero to satisfy Leadroom's readability rules; the source system's aggressive negative tracking is intentionally omitted.
- URL-driven filters and list virtualization are architectural improvements, not visual tokens. They should be implemented separately when pagination and lists beyond 50 visible items are introduced.

## Runtime Cost

The theme is a scoped CSS layer selected with `data-theme="vercel"`. It adds no package, image, font, request, or animation loop.
