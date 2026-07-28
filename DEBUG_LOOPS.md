# Leadroom Debug Loops

This document tracks the current, evidence-based debug campaign. Historical phase
scores do not count here. Each stage must pass the loop below and reach at least
`8/10` before the next stage is closed.

## Loop Rules

1. Audit the stage through code review, automated tests, and realistic UI flows.
2. Record every reproducible defect with severity and evidence.
3. Fix defects in severity order without hiding failures or weakening assertions.
4. Add a regression test for behavior that can reasonably be automated.
5. Re-run the focused tests and the shared quality gate.
6. Score the result using the rubric below. Repeat when the score is below 8.

## Scoring

- Correctness and recovery: 3 points
- Data integrity, privacy, and security: 2 points
- UX, accessibility, and responsive behavior: 2 points
- Automated regression coverage: 2 points
- Performance and diagnostics: 1 point

A stage with an unresolved critical defect cannot score above 5. An unresolved
high-severity defect caps the stage at 7.

## Current Campaign

| Stage | Surface | Baseline | Current | Status |
|---|---|---:|---:|---|
| 0 | Shared baseline and quality gate | 6.5 | 6.5 | In progress |
| 1 | Discovery, New Run, and run controls | 5.5 | 8.7 | Passed |
| 2 | Enrichment, deep crawl, normalization, deduplication | 5.2 | 8.8 | Passed |
| 3 | Repository, collections, editing, and export | TBD | TBD | Pending |
| 4 | Outreach, compliance, drafts, and email delivery | TBD | TBD | Pending |
| 5 | Settings, models, storage, themes, and branding | TBD | TBD | Pending |
| 6 | Desktop shell, packaging, installation, and shutdown | TBD | TBD | Pending |
| 7 | Cross-app UI/UX, responsive behavior, accessibility, performance | TBD | TBD | Pending |

## Stage 0: Shared Baseline

### Evidence

- Python: 163 tests pass with 83% total coverage.
- Frontend: ESLint, TypeScript production build, and 2 Vitest tests pass.
- Dependency integrity: `pip check` passes.
- Preflight: Python, output storage, and Ollama service pass.

### Bugs

| ID | Severity | Defect | State |
|---|---|---|---|
| BASE-001 | High | The configured default model is missing, so `scripts/check.ps1` fails instead of selecting or clearly persisting an installed fallback. | Open; assigned to Stage 5 |
| BASE-002 | Medium | Production JavaScript is 171.35 KiB gzip, above the documented 150 KiB budget. | Open; assigned to Stage 7 |
| BASE-003 | Low | Upstream FastAPI, Starlette, Pydantic, and LangChain dependencies emit 87 deprecation warnings, reducing signal in test output. | Open; dependency boundary review |

### Gate

Stage 0 remains open until the shared quality gate exits successfully without
ignoring the missing-model failure.

## Stage 1: Discovery, New Run, and Run Controls

### Findings

| ID | Severity | Defect | Fix | Regression |
|---|---|---|---|---|
| RUN-001 | Critical | Stop followed quickly by Continue could leave the old enrichment worker alive. Both workers could then process the same candidate and the stale worker could overwrite the resumed run's status or exports. | Added per-run enrichment generation tokens and suppressed all stale progress, lead, export, and terminal-status writes. | `test_superseded_worker_does_not_write_lead_export_or_terminal_status` |
| RUN-002 | High | Start and Retry accepted incompatible run states, allowing duplicate workers and state transitions. | Restricted Start to `ready`; rejected Retry for active runs and runs without failed/interrupted candidates. | `test_run_actions_reject_invalid_and_duplicate_states` |
| RUN-003 | Medium | Stop could convert an already-ready or terminal run to `stopped`, corrupting the persisted state shown to the user. | Stop now accepts only `searching` and `running`. | `test_run_actions_reject_invalid_and_duplicate_states` |
| RUN-004 | Medium | Enrichment could start with no selected candidates and immediately create an empty completed run. | Added a database-boundary candidate selection guard. | `test_start_rejects_a_ready_run_without_selected_candidates` |
| RUN-005 | Medium | Completed discovery futures remained registered until another action replaced them. | Added token-aware completion cleanup for discovery and enrichment futures. | Covered by the run action and shutdown test paths. |

### Verification

- 166 Python tests pass.
- Ruff passes for the application, tests, entry points, and benchmarks.
- Frontend ESLint, TypeScript production build, and Vitest pass.
- Targeted run-state tests cover Start, Stop, Continue, Retry, duplicate requests,
  empty selection, deletion, and stale-worker isolation.

### Score

- Baseline: 5.5/10
- Loop 1: 7.6/10
- Loop 2: 8.7/10
- Final: **8.7/10**
- Residual risk: a running HTTP/browser request cannot be forcibly interrupted;
  its result and progress are now discarded once its worker generation is stale.

## Stage 2: Enrichment, Deep Crawl, and Contact Quality

### Findings

| ID | Severity | Defect | Fix | Regression |
|---|---|---|---|---|
| ENR-001 | High | A same-site URL could redirect to a booking platform or unrelated public domain and have that domain's contacts merged into the business lead. | Enforced registered-domain continuity for every crawl response and the HTML passed to the LLM. | `test_crawl_rejects_contacts_from_an_external_redirect`, `test_scraper_rejects_an_unrelated_redirect_before_llm` |
| ENR-002 | High | Stop was checked only around the entire scrape, so a deep crawl could continue through dozens of pages after cancellation. | Propagated cancellation through sitemap traversal, page traversal, and the pre-LLM boundary. | `test_crawl_stops_between_pages_when_cancelled` |
| ENR-003 | High | Raw OSM email and phone values bypassed web contact validation and normalization. Invalid evidence could remain attached to an empty field. | Applied domain-aware email validation, phone normalization, and evidence generation only after validation. | `test_local_contacts_are_normalized_and_unrelated_email_is_rejected` |
| ENR-004 | Medium-high | Contact lists were truncated before the crawl finished, so three named addresses on the homepage could hide a later `info@` address. Cross-page phone formats were not identity-deduplicated. | Re-ranked merged email candidates and identity-deduplicated phones after every page while keeping evidence for the winning contact. | `test_later_generic_email_displaces_lower_priority_named_contacts`, existing UK phone normalization tests |
| ENR-005 | Medium | Disabling adaptive fetching did not apply to the second HTML fetch used by the LLM. | Passed `advanced_fetching` to both fetchers. | `test_scraper_propagates_adaptive_setting_to_llm_source_fetch` |
| ENR-006 | Medium | Results with no public email or phone were persisted as leads and displayed as `Not found / 0/10`. | Added terminal candidate state `no_contact`; diagnostic raw output remains available, but no Lead record is stored or shown. | `test_pipeline_does_not_persist_a_result_without_public_contacts` |
| ENR-007 | Medium | Gzip sitemap expansion and browser HTML had incomplete size enforcement. | Added bounded gzip expansion and a 5 MB browser HTML limit. | `test_fetch_text_rejects_a_gzip_document_that_expands_beyond_limit` |
| ENR-008 | Medium | Concurrent workers used the same cache temp filename and could race during atomic replacement. | Gave each cache writer a unique temporary path and retained atomic replacement. | Covered by atomic cache implementation; stress test remains desirable. |

### Verification

- 174 Python tests pass; 69 focused enrichment/pipeline/local/database/filter tests pass.
- Ruff passes.
- Frontend ESLint, production build, and Vitest pass with the new `No contact` state.

### Score

- Baseline: 5.2/10
- Loop 1: 7.4/10
- Loop 2: 8.8/10
- Final: **8.8/10**
- Residual risks: an in-flight network request stops at its timeout rather than
  mid-socket; visible-text phone extraction remains UK-oriented, while explicit
  `tel:` links and structured data support international formats.

## Stage Review Template

### Audit scope

- Entry points and primary user workflow
- Empty, loading, partial, success, failure, retry, cancel, and restart states
- Validation boundaries and persistence
- Keyboard, screen-reader, mobile, tablet, and desktop behavior
- Logs, diagnostics, timeouts, and performance

### Findings

| ID | Severity | Defect | Reproduction | Fix | Regression |
|---|---|---|---|---|---|

### Score

- Baseline:
- Loop 1:
- Loop 2:
- Final:
- Residual risks:
