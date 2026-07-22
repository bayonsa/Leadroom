# InsightDeck Theme

## Purpose

InsightDeck adapts Leadroom into a polished analytical workspace. It prioritizes data clarity, scanning, comparison, and presentation-ready hierarchy without turning operational pages into marketing layouts.

## Tokens

- Background: `#F8FAFC`
- Surface: `#FFFFFF`
- Primary teal: `#0D9488`
- Secondary purple: `#9333EA`
- Tertiary pink: `#EC4899`
- Text: `#0F172A`
- Muted text: `#64748B`
- Border: `#E2E8F0`
- Success: `#10B981`
- Warning: `#F59E0B`
- Error: `#EF4444`
- Info: `#3B82F6`

## Product Adaptation

- Teal owns commands, navigation, links, focus, selection, and progress.
- Purple identifies workspace-level insight and secondary analytical signals.
- Pink is reserved for exceptional trends and tertiary highlights.
- Tables, metrics, and evidence surfaces stay white and quiet so the data carries the hierarchy.
- A single view never uses more than five data colors.
- Leadroom has no chart canvas yet; presentation mode should be introduced alongside reporting and chart features rather than as an empty chrome toggle.

## Runtime Cost

InsightDeck is a scoped CSS layer selected with `data-theme="insightdeck"`. It adds no font, image, network request, or animation dependency.
