# Lead Scraper Product Plan

This is the living execution plan for turning the current CLI prototype into a reliable local lead-research product.

## Scoring Rules

- `10/10`: the best practical state for the phase, including automation, tests, documentation, and edge cases.
- `9/10`: production-ready for the current local-product scope. This is the gate required before the next phase starts.
- Scores must be supported by tests, measured output, or a documented review. A completed checklist alone does not raise a score.
- A phase can lose points later if a regression or missing requirement is discovered.

## Progress

| Phase | Area | Baseline | Current | Gate | Status |
|---|---|---:|---:|---:|---|
| 0 | Project foundation | 4/10 | 9/10 | 9/10 | Complete |
| 1 | Data correctness and benchmark | 5/10 | 9/10 | 9/10 | Complete |
| 2 | Contact enrichment and resilience | 3/10 | 9/10 | 9/10 | Complete |
| 3 | Persistence and job engine | 1/10 | 9/10 | 9/10 | Complete |
| 4 | Local API | 0/10 | 9/10 | 9/10 | Complete |
| 5 | Product UX/UI | 0/10 | 9/10 | 9/10 | Complete |
| 6 | Integrated QA and reliability | 2/10 | 9/10 | 9/10 | Complete |
| 7 | Search providers and packaging | 1/10 | 9/10 | 9/10 | Complete |
| 8 | Outreach and compliance controls | 0/10 | 9/10 | 9/10 | Complete |
| 9 | Heavy local discovery engine | 0/10 | 9/10 | 9/10 | Complete |

## Phase 9: Heavy Local Discovery Engine

### 10/10 definition

Leadroom can search a large, self-hosted geospatial business index with no paid API, run it concurrently with live web discovery, merge matching evidence, preserve useful phone-only businesses, and collect categorized results in one polished lead library.

### Tasks

- [x] Install PostgreSQL 18, PostGIS 3.6, and osm2pgsql 2.2 in WSL2.
- [x] Add a reproducible Great Britain download/import workflow and Flex mapping.
- [x] Add trigram, contact, and spatial indexes for local market queries.
- [x] Add `osm_local` and `hybrid` providers with stable OSM identities.
- [x] Persist structured OSM seed evidence with every candidate.
- [x] Support phone/email leads that do not have a website.
- [x] Add a Windows-to-WSL query bridge that does not depend on firewall forwarding.
- [x] Build a responsive Local Data Engine workspace with Local, Web, and combined discovery modes.
- [x] Support unlimited local continuation through exact, non-skipping result batches.
- [x] Add independent All/Local/Web candidate tabs, continuation cursors, and balanced combined batches.
- [x] Run local and web discovery concurrently and merge matching domains without losing local contacts.
- [x] Categorize the shared Repository by niche, location, and evidence source with combined export.
- [x] Import and benchmark the full Great Britain extract plus a deterministic fixture.
- [x] Add locked daily replication updates, catch-up after downtime, manual sync, and UI freshness state.
- [x] Prevent windowed builds from flashing a console during WSL status polling.
- [x] Test desktop/mobile layouts, console errors, overflow, and query interaction.

### Review log

- Baseline: `0/10`.
- Bugs found: the old candidate contract required a website domain; Windows-to-WSL TCP forwarding was intermittent; the schema migration briefly retained SQLite file handles; real OSM boundaries can use `type=boundary`; the first spatial query plan took 14.5 seconds for dense London categories; and every UI status poll could flash a `wsl.exe` console window.
- Fixes: stable OSM candidate IDs, seed-data persistence, no-website enrichment, concurrent local/web discovery, cross-source domain merging, categorized Repository metadata, deterministic SQLite connection closure, a native WSL `psql` bridge, hidden child-process flags, boundary-relation support, an area-first PostGIS query plan, niche qualifier normalization, updateable slim tables, a persistent systemd replication timer, manual sync, app-role grants, and dedicated data-engine and lead-library UI.
- Evidence: the official Great Britain extract imported 798,732 businesses and 11,853 place boundaries in 4m08s; 250,109 records have websites, 151,204 have phones, and 34,140 have emails. Warm local searches benchmark at 0.2-1.7 seconds across London, Manchester, Birmingham, and Bristol. A live unified Manchester search combined 10 local and 15 web results and merged shared local/web evidence into one contact-rich record. The full Python suite, frontend lint/build/unit gates, and serial desktop/mobile Playwright scenarios pass.
- Current: `9/10`.
- Remaining for 10/10: validate package installation and scheduled catch-up on a clean Windows machine.

## Phase 0: Project Foundation

### 10/10 definition

A fresh checkout has a documented setup, deterministic dependencies, safe defaults, version control, consistent tooling, actionable diagnostics, and one command for tests.

### Tasks

- [x] Initialize Git and add a project-specific `.gitignore`.
- [x] Separate runtime and development dependencies and pin direct versions.
- [x] Add `pyproject.toml` for project metadata and test/tool configuration.
- [x] Validate environment variables and filesystem paths.
- [x] Add a preflight command for Python, Ollama, model, and writable output checks.
- [x] Improve README with setup, run, test, troubleshooting, and architecture.
- [x] Remove generated caches from the tracked project surface.
- [x] Run unit tests, compile checks, dependency checks, and CLI help smoke test.

### Baseline findings

- The folder is not a Git repository.
- Dependencies are unpinned and `requirements.txt` lists Streamlit although it is not installed or used.
- There is no automated preflight check.
- Setup and troubleshooting documentation are too short for a fresh machine.

### Review log

- Baseline: `4/10`.
- Bugs found: 8 lint violations, unsafe run filenames, missing bounds validation, and no runtime diagnostics.
- Fixes: initialized Git; added ignore rules, pinned runtime/dev dependencies, project metadata, config validation, preflight diagnostics, expanded setup/troubleshooting docs, and a single quality-gate script.
- Evidence: 14 tests passed; Ruff, compileall, pip check, CLI help, writable output, Ollama service, and configured model checks passed.
- Current: `9/10`.
- Remaining for 10/10: verify bootstrap and the full quality gate on a clean Windows machine or CI runner.

## Phase 1: Data Correctness and Benchmark

### 10/10 definition

All lead data crosses a typed schema boundary, structured model output is validated, scoring is deterministic and explainable, and a representative labelled benchmark prevents silent quality regressions.

### Tasks

- [x] Define Pydantic models for run configuration, candidates, extraction, leads, errors, and summaries.
- [x] Fix string boolean handling such as `"false"` becoming truthy.
- [x] Replace LLM-owned scoring with deterministic evidence-based scoring.
- [x] Pass a JSON Schema to Ollama where supported and validate every extraction.
- [x] Preserve validation errors and raw evidence without promoting invalid leads.
- [x] Create a labelled benchmark across at least three niches.
- [x] Measure candidate precision, clean-lead yield, contact coverage, duplicate rate, and failure rate.
- [x] Add regression tests for malformed output, domain drift, false booleans, and score boundaries.

### Baseline findings

- `bool("false")` currently evaluates to `True` in lead normalization.
- The model chooses `lead_score`; malformed scores silently become `5`.
- Pydantic is installed but not used as the canonical data contract.
- The new 100% smoke-test yield covers only three scraped sites and is not representative.

### Review log

- Baseline: `5/10`.
- Bugs found: string `false` promoted invalid leads; LLM scores were trusted; WhatClinic, TikTok, Tuugo, Cleanster, Need a Pro, Pinterest, and out-of-location results bypassed filters.
- Fixes: Pydantic contracts, Ollama JSON Schema, deterministic evidence scoring, validation diagnostics, quality metrics, expanded filters, and stable/live three-niche benchmarks.
- Evidence: 26 tests passed with 79% total coverage; the 30-case labelled corpus reports 100% precision and accuracy; live schema extraction returned a valid independent business after false-positive fixes.
- Current: `9/10`.
- Remaining for 10/10: grow the labelled corpus with periodically reviewed real runs and remove upstream ScrapeGraphAI deprecation warnings when its dependency chain supports it.

## Phase 2: Contact Enrichment and Resilience

### 10/10 definition

The pipeline discovers and checks relevant internal pages, extracts public contact evidence efficiently, handles transient failures predictably, respects bounded concurrency, and avoids repeated network or model work.

### Tasks

- [x] Discover same-domain Contact, About, Location, and Booking links from HTML.
- [x] Extract emails, phones, social links, and JSON-LD without an LLM first.
- [x] Use Playwright and ScrapeGraphAI only as fallbacks.
- [x] Add connect/read timeouts, retry classification, exponential backoff, and cancellation checks.
- [x] Cache fetched HTML and extraction results with expiry and content hashes.
- [x] Record field-level source URL and extraction method.
- [x] Add fixture-based contact discovery and network-failure tests.
- [x] Run the benchmark and reach the agreed coverage and failure thresholds.

### Review log

- Baseline: `3/10`.
- Bugs found: no contact-page traversal, no cache/retry/timeout, TLS failures yielded no HTML evidence, and JSON-LD `@graph` businesses were missed.
- Fixes: HTML-first extraction, ranked same-domain discovery, generic-contact privacy filter, bounded retries/backoff, hashed TTL cache, secure HTTP with Playwright fallback, provenance, cancellation checks, and nested JSON-LD traversal.
- Evidence: 32 tests passed; live BCO Salon smoke produced 100% clean yield, email/phone/contact/booking coverage, two cached pages, field provenance, and zero failures.
- Current: `9/10`.
- Remaining for 10/10: run a larger timed contact benchmark and reuse one long-lived browser context for high-volume fallback traffic.

## Phase 3: Persistence and Job Engine

### 10/10 definition

Runs survive process restarts, every domain has an explicit state, duplicate work is prevented, and failed or interrupted work can be resumed, retried, or cancelled safely.

### Tasks

- [x] Add SQLite, SQLAlchemy models, migrations, and foreign-key enforcement.
- [x] Store runs, candidates, leads, field evidence, events, and failures.
- [x] Implement the domain state machine and legal state transitions.
- [x] Add a bounded worker process with leases and stale-job recovery.
- [x] Implement resume, cancel, retry, and idempotent domain deduplication.
- [x] Snapshot run configuration, prompt version, model, and timestamps.
- [x] Add backup/export and database integrity diagnostics.
- [x] Test restart recovery, duplicate submission, cancellation, and migration paths.

### Review log

- Baseline: `1/10`.
- Bugs found: event insertion raced its parent run, in-batch duplicate domains bypassed the in-memory set, and invalid fixture domains hid resume behavior.
- Fixes: SQLite WAL/foreign keys/busy timeout, schema versioning, run/candidate/lead/event records, legal transitions, leases, recovery, cross-run reuse, integrity checks, backups, persistent CLI IDs, and `--resume`.
- Evidence: 39 tests passed with 82% coverage; database module coverage is 97%; live restart/resume continued a run from one to two leads without repeating search.
- Current: `9/10`.
- Remaining for 10/10: add formal Alembic revision files once the schema has a second production migration and test recovery after forced OS-level process termination.

## Phase 4: Local API

### 10/10 definition

The complete workflow is available through a typed, documented local API with stable errors, live progress, cancellation, safe path handling, and integration tests.

### Tasks

- [x] Add FastAPI application structure and versioned routes.
- [x] Add endpoints for settings, runs, candidates, execution, leads, retries, and exports.
- [x] Stream run events through SSE with reconnection support.
- [x] Add consistent problem/cause/fix error responses.
- [x] Validate all inputs, limits, filenames, paths, and provider settings.
- [x] Generate and test OpenAPI contracts.
- [x] Add API integration tests and concurrency tests.
- [x] Keep CLI behavior through the same application service layer.

### Review log

- Baseline: `0/10`.
- Bugs found: FastAPI 0.139 rejected the original SSE response shape, validation errors used an unsupported argument, and repeated Start requests could enqueue the same run twice.
- Fixes: versioned FastAPI routes, typed request models, SSE event replay cursor, consistent problem/cause/fix errors, repository-backed execution and exports, OpenAPI tests, and atomic run-start protection.
- Evidence: 45 full-suite tests passed with 83% coverage; API coverage is 87%; focused API/database concurrency tests, Ruff, compile checks, dependency checks, and a real Uvicorn health/OpenAPI smoke test passed.
- Current: `9/10`.
- Remaining for 10/10: generate a checked-in API client from the OpenAPI contract and run sustained concurrent request/load testing.

## Phase 5: Product UX/UI

### 10/10 definition

A user can create, supervise, recover, review, edit, and export a run without a terminal. The interface is fast, accessible, responsive, evidence-aware, and optimized for repeated lead-research work.

### Tasks

- [x] Create React, TypeScript, and Vite frontend with a restrained operational design system.
- [x] Build Runs, New Run, Candidates, Progress, Leads, Lead Detail, and Settings views.
- [x] Use a staged flow: search, candidate review, enrichment, result review, export.
- [x] Add live per-domain status, elapsed time, cancel, retry, and actionable failures.
- [x] Build sortable, filterable, selectable, editable lead tables.
- [x] Show field confidence, source URL, extraction method, and needs-review states.
- [x] Add empty, loading, partial, error, interrupted, and completed states.
- [x] Verify keyboard access, contrast, responsive layout, text fit, and no overlap.
- [x] Test desktop and mobile behavior with browser automation and screenshots.

### Review log

- Baseline: `0/10`.
- Bugs found: the npm registry certificate chain failed locally, TypeScript 6 rejected parameter properties, Vitest collected Playwright specs, and exports could return a stale file from another run.
- Fixes: React/Vite workspace, staged operational UI, responsive navigation, market-history preview, accessible new/reuse/refresh discovery controls, candidate selection, persisted discovery summaries, polling progress, sortable/filterable leads, evidence drawer, persisted lead editing, per-run database exports, explicit unit/E2E discovery, and temporary command-scoped npm TLS handling.
- Evidence: production TypeScript build and ESLint pass; two Vitest tests and four Playwright workflows pass on 1440px desktop and 390px mobile; screenshots were visually reviewed; console errors and horizontal overflow are zero; the full project gate passes.
- Current: `9/10`.
- Remaining for 10/10: conduct moderated usability testing with target lead researchers and add virtualized table rendering for runs with thousands of leads.

## Phase 6: Integrated QA and Reliability

### 10/10 definition

Unit, contract, integration, end-to-end, and benchmark tests cover critical paths; failures are observable; and release checks catch functional, data-quality, performance, and UX regressions.

### Tasks

- [x] Define a test pyramid and minimum critical-path coverage.
- [x] Add deterministic site fixtures and provider fakes.
- [x] Add full pipeline integration tests without live external dependencies.
- [x] Add Playwright end-to-end tests for all primary workflows.
- [x] Test slow sites, malformed HTML, model errors, disk errors, restart, and cancellation.
- [x] Add structured logs, run diagnostics, and privacy-safe error reports.
- [x] Establish performance budgets for search, scrape, UI updates, and exports.
- [x] Add a single release-check command and document residual risks.

### Review log

- Baseline: `2/10`.
- Bugs found: disk-full export left runs without an explicit terminal failure, Vitest and Playwright discovery overlapped, and operators had no privacy-safe run diagnostics.
- Fixes: layered test strategy, deterministic provider/network fakes, disk-failure handling, diagnostics endpoint, 500-candidate read budget, bundle/navigation/health budgets, retained Playwright traces, and a single release-check command.
- Evidence: 48 Python tests pass at 83% coverage; two frontend unit tests and four desktop/mobile E2E tests pass; database integrity and structured events pass a real diagnostics smoke; release-check passes end to end.
- Current: `9/10`.
- Remaining for 10/10: run fault injection against forced process termination and collect longitudinal p95 budgets across clean Windows machines.

## Phase 7: Search Providers and Local Packaging

### 10/10 definition

Search providers are interchangeable and observable, the application installs and upgrades predictably on the target platform, and user data can be backed up and restored safely.

### Tasks

- [x] Define a search-provider interface and normalized result contract.
- [x] Add Brave Search or Serper with quotas, retries, and provider diagnostics.
- [x] Keep DDGS as a clearly labelled prototype/fallback provider.
- [x] Compare provider precision, cost, latency, and coverage on the benchmark.
- [x] Package the React frontend and Python service as a local desktop application.
- [x] Add startup health checks, data-directory management, upgrade, and rollback behavior.
- [x] Add backup, restore, and uninstall-with-data-preservation flows.
- [ ] Test installation on a clean Windows environment.

### Review log

- Baseline: `1/10`.
- Bugs found: search was coupled directly to DDGS, live dental precision fell to 1/5, SQLite backup connections remained locked on Windows, SPA deep links returned 404, and windowed Uvicorn could not start without standard streams.
- Fixes: provider protocol, Brave adapter with bounded retry and offsets, DDGS fallback, market-scoped cross-run deduplication, deeper-page discovery for replacement candidates, niche/location relevance and expanded blocklist, measured provider report, integrity-checked backup/restore, static SPA fallback, PyInstaller launcher, persistent local data directory, windowed stream handling, and an explicit Uvicorn console-logging bypass for no-console builds.
- Evidence: 72 Python tests pass at 85% coverage, including desktop logging, market-history, deep-page replacement, reuse, and refresh regressions; six desktop/mobile E2E scenarios pass; live three-niche DDGS benchmark was manually reviewed after two filter iterations; the 122.9 MB Windows executable passed packaged API health, discovery-history, root, and deep-link smoke tests.
- Current: `9/10`.
- Remaining for 10/10: run the installer/artifact on a clean Windows VM, live-benchmark Brave with a project key, and add code signing plus an installer-level rollback UI.

## Phase 8: Outreach and Compliance Controls

### 10/10 definition

Outreach is generated only from verified evidence, requires deliberate approval, protects personal data, supports suppression and opt-out, and provides an auditable UK-focused compliance workflow.

### Tasks

- [x] Define outreach eligibility and block personal-email use by default.
- [x] Generate evidence-grounded drafts without unsupported claims.
- [x] Require human approval before any send or external export.
- [x] Add suppression lists, opt-out records, retention controls, and deletion workflows.
- [x] Record lawful-basis notes and source provenance where required.
- [x] Add rate and batch limits plus duplicate-contact protection.
- [x] Add compliance review checkpoints for GDPR and PECR.
- [x] Test prohibited-data, opt-out, duplicate, and accidental-send scenarios.

### Review log

- Baseline: `0/10`.
- Bugs found: there was no distinction between corporate and individual subscribers, no suppression/audit model, no approval gate, and no deletion workflow that preserved objections.
- Fixes: generic-mailbox eligibility, source and score requirements, conservative subscriber classification, consent documentation, templated evidence-grounded drafts, immutable suppression hashes, immediate draft blocking, human approval, 25-per-day export cap, duplicate protection, retention purge, and delete-with-suppression preservation. No sending endpoint exists.
- Evidence: 65 backend tests pass at 84% coverage, including personal-email, consent, suppression, duplicate, deletion, accidental-export, and API approval cases; six desktop/mobile E2E tests pass with no console error or overflow; current ICO guidance is linked in `COMPLIANCE.md`; bundled Outreach routes and API passed executable smoke.
- Current: `9/10`.
- Remaining for 10/10: obtain a formal legal review for the operator's exact use case, add organisation-specific privacy-notice/LIA templates, and conduct a live opt-out tabletop exercise with accountable staff.

## Explicitly Deferred

- Multi-user cloud deployment: local single-user reliability comes first.
- PostgreSQL, Redis, and distributed workers: unnecessary until concurrency or deployment requires them.
- Automatic email sending: deferred until lead quality and compliance controls reach their gates.
- CRM and Google Sheets integrations: useful after the core run and export workflow is stable.
