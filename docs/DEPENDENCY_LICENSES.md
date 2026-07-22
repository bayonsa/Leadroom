# Dependency Licence Audit

This document records the source-publication audit performed on 22 July 2026. It is not legal advice and does not replace the licence text shipped by each dependency.

## Scope

- Direct Python dependencies declared in `pyproject.toml`
- Their installed runtime dependency graph in the project virtual environment
- Non-development frontend packages in `frontend/package-lock.json`
- Optional OpenStreetMap data and ScrapeGraphAI attribution described in `THIRD_PARTY_NOTICES.md`

## Result

- 108 installed Python runtime packages were inspected using package metadata, including `License-Expression`, `License`, and licence classifiers.
- 15 frontend runtime packages were inspected from the lockfile; all declared a licence and no strong-copyleft licence was reported.
- ScrapeGraphAI's installed wheel does not expose complete licence metadata. Its upstream repository declares the MIT licence and is attributed in `THIRD_PARTY_NOTICES.md`.
- `html2text==2025.4.15`, pulled transitively by ScrapeGraphAI, declares `GPL-3.0-or-later`.

## Release Decision

The source repository may be published under Leadroom's MIT licence while retaining third-party notices. Public binary distribution remains blocked until the `html2text` path is removed or replaced, or the complete GPL distribution obligations have been reviewed and implemented. No installer or portable GitHub Release should be published before that decision is recorded.

## Re-run Before Every Binary Release

1. Build from a clean environment using the locked dependency versions.
2. Inspect both Python and frontend runtime dependency trees.
3. Resolve packages with missing or ambiguous metadata against their official source distributions.
4. Include all required licence texts and notices in the release artifact.
5. Re-check bundled browser, WebView, Ollama, model, and map-data licences because those components may not appear in language package metadata.

The authoritative dependency declarations are `pyproject.toml`, `requirements.txt`, and `frontend/package-lock.json`.
