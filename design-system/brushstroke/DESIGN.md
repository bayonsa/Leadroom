# BrushStroke Design System

## Overview

BrushStroke is a textured, organic, and handmade design system crafted for illustrators and fine artists. It embraces warmth and imperfection with a cream-toned canvas, earthy palette, and expressive KPI numerals. Every component feels approachable and artisanal without sacrificing interface readability. The system prioritizes the content above all else, keeping the UI inviting without competing with the work.

For Leadroom, BrushStroke keeps operational surfaces compact and highly legible while applying its expressive character to headings, accents, key actions, and elevated moments.

## Colors

- **Primary** (`#B45309`): Burnt Sienna for calls to action, links, and accents.
- **Secondary** (`#65A30D`): Olive for tags, success-adjacent states, and local data.
- **Tertiary** (`#7E22CE`): Plum for highlights, premium badges, and web data.
- **Background** (`#FFFDF7`): Warm paper-like page backdrop.
- **Surface** (`#FEF9EF`): Cards and content areas.
- **Ink** (`#292524`): Primary text and dark navigation surfaces.
- **Muted** (`#78716C`): Secondary text.
- **Line** (`#E7E5E4`): Borders and dividers.
- **Success** (`#16A34A`): Completed and valid states.
- **Warning** (`#D97706`): Warnings and waiting states.
- **Error** (`#DC2626`): Validation and failed states.
- **Info** (`#2563EB`): Informational states.

## Typography

- **Interface font:** Public Sans
- **KPI numeral font:** Kalam
- **Body fallback:** DM Sans
- **Mono font:** Source Code Pro
- **Display:** Public Sans 48px bold, 1.2 line height.
- **Headline:** Public Sans 36px bold, 1.25 line height.
- **Subhead:** Public Sans 24px semibold, 1.3 line height.
- **Body large:** DM Sans 18px regular, 1.65 line height, 0.01em tracking.
- **Body:** DM Sans 16px regular, 1.65 line height, 0.01em tracking.
- **Body small:** DM Sans 14px regular, 1.5 line height, 0.01em tracking.
- **Caption:** DM Sans 12px medium, 1.4 line height, 0.02em tracking.
- **Overline:** DM Sans 11px bold, 1.4 line height, 0.1em tracking.
- **Code:** Source Code Pro 14px regular, 1.6 line height.

## Spacing

- **Base unit:** 8px.
- **Scale:** `4px / 8px / 16px / 24px / 32px / 48px / 64px / 96px`.
- **Component padding:** buttons `12px 24px`, cards `24px`, inputs `10px 16px`.
- **Section spacing:** 64px between major sections and 96px for hero gaps.
- **Grid gutter:** 24px.

## Border Radius

- **Small:** 8px for chips and badges.
- **Medium:** 12px for inputs and buttons.
- **Large:** 16px for cards, modals, and panels.
- **XL:** 24px for image containers and featured surfaces.
- **Full:** 9999px for avatars and round icons.

Avoid sharp corners except where a functional table edge requires visual continuity.

## Elevation

- **Subtle:** `0 1px 3px rgba(41, 37, 36, 0.06)`.
- **Medium:** `0 4px 12px rgba(41, 37, 36, 0.08)`.
- **Large:** `0 12px 32px rgba(41, 37, 36, 0.12)`.
- **Overlay:** dark backdrop at 30% opacity.
- **Brushed:** `2px 3px 0 rgba(180, 83, 9, 0.15)` for featured elements only.

## Components

### Buttons

- Primary: Burnt Sienna fill and white text; hover uses `#92400E`.
- Secondary: warm surface, Burnt Sienna text and border.
- Ghost: transparent with Stone text and warm-surface hover.
- Destructive: Error fill and white text.
- Heights: 32px small, 40px medium, 48px large.
- Disabled: 45% opacity with no hover state.

### Cards

- Default: Surface fill, 1px Line border, subtle shadow, 16px radius.
- Elevated: Background fill, no border, medium shadow, 16px radius.
- Padding: 24px.

### Inputs

- Default: Line border on Background fill.
- Hover: `#A8A29E` border.
- Focus: 2px Primary border and Primary label.
- Error: 2px Error border and Error label.
- Disabled: `#F5F5F4` fill and `#A8A29E` text.

### Chips And Status

- Filter chips: `#FDF4E0` fill, Stone text, Line border, 8px radius.
- Status chips: semantic color at 15% opacity, 8px radius.

### Lists

Use DM Sans 16px with secondary metadata. Rows are at least 52px high, use a Line divider, a Surface hover state, and a 3px Primary accent for selection.

### Selection Controls

- Checkboxes: 20px soft square, Primary fill when checked.
- Radio buttons: 20px circle, Primary ring and 8px inner dot when selected.

### Tooltips

Use Ink fill, Background text, 12px DM Sans, 8px radius, `6px 12px` padding, and a medium shadow. Maximum width is 260px.

## Usage Rules

1. Use the warm cream background throughout; do not switch to pure white.
2. Use Kalam only for KPI numerals inside rectangular metric groups.
3. Keep content central with generous whitespace and restrained chrome.
4. Do not introduce neon or highly saturated colors.
5. Keep all interface text in Public Sans for readability. Kalam is reserved exclusively for KPI numerals inside metric rectangles.
6. Use the brushed shadow sparingly for featured actions and key surfaces.
7. Do not apply more than one texture treatment per view.
8. Pair Burnt Sienna with Plum for visual interest and Olive for positive states.
9. Do not stack more than two shadow levels on one component.
10. Preserve dense, scannable layouts for Leadroom's repeated operational workflows.
