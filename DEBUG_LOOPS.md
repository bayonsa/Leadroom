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
| 3 | Repository, collections, editing, and export | 4.8 | 8.6 | Passed |
| 4 | Outreach, compliance, drafts, and email delivery | 4.9 | 8.7 | Passed |
| 5 | Settings, models, storage, themes, and branding | 4.8 | 8.8 | Passed |
| 6 | Desktop shell, packaging, installation, and shutdown | 4.5 | 8.7 | Passed |
| 7 | Cross-app UI/UX, responsive behavior, accessibility, performance | TBD | TBD | In progress |

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

## Stage 3: Repository, Collections, Editing, and Export

### Findings

| ID | Severity | Defect | Fix | Regression |
|---|---|---|---|---|
| REP-001 | High | Editing any non-collection field sent only the first collection and silently removed every other membership. | Edit mode no longer submits collection; moving remains a separate explicit action. | Backend collection preservation and multi-membership tests |
| REP-002 | High | Deleting one collection added `Uncategorised` even when the lead still belonged to other collections. | Delete now removes only the named membership and uses `Uncategorised` only when none remain. | `test_repository_collections_remain_complete_and_delete_only_the_named_membership` |
| REP-003 | High | A lead silently lost collection history after 12 distinct search niches. | Removed the hidden cap for `niches` while retaining bounded contacts and services. | Same 20-collection regression test |
| REP-004 | High | Listing Repository leads ran a write transaction and permanently deleted ineligible legacy records. | Repository GET is now a read-only session; invalid legacy records are omitted without mutation. | `test_repository_read_never_deletes_an_ineligible_legacy_record` |
| REP-005 | High | Editing Website changed the displayed URL but not the record's domain identity, allowing duplicate future imports. | Website edits must remain on the existing registered business domain. | `test_repository_edit_rejects_identity_change_and_refreshes_manual_evidence` |
| REP-006 | High | Repository edits left score, explanation, and evidence describing the previous values. | Contacts are revalidated, manual evidence is refreshed, and score/reason are recalculated atomically. | Same repository edit regression test |
| REP-007 | Medium | Collection casing and whitespace variants could duplicate membership within a lead. | Added whitespace and case-insensitive canonical deduplication across merge/update paths. | Multi-collection regression coverage |
| REP-008 | Medium | Explicit `domains: []` imported every completed lead because it was treated like omission. | Empty explicit selections now fail request validation; omitted means import all. | Repository API workflow test |
| REP-009 | Medium | Export ignored active UI filters without making its full-repository scope clear. | Commands now read `All JSON` and `Export all CSV`. | Frontend build and lint |
| REP-010 | Medium | Repository read and render still load the complete dataset. | Deferred server pagination/virtualization as an explicit scale item; no data-integrity defect remains. | 10,000-lead benchmark required before large deployments |

### Verification

- 177 Python tests pass.
- Ruff, frontend ESLint, production build, and Vitest pass.
- Repository regressions cover multi-membership, 20 collections, collection
  deletion, identity protection, evidence/score refresh, read-only legacy data,
  explicit empty imports, contact normalization, CSV safety, and exports.

### Score

- Baseline: 4.8/10
- Loop 1: 7.3/10
- Loop 2: 8.6/10
- Final: **8.6/10**
- Residual risks: server pagination and row virtualization are still required for
  repositories in the tens of thousands; the mobile row layout is assigned to
  the cross-app responsive stage.

## Stage 4: Outreach, Compliance, Drafts, and Email Delivery

### Findings

| ID | Severity | Defect | Fix | Regression |
|---|---|---|---|---|
| OUT-001 | Critical | Recipient duplicate checks omitted `sending` and `uncertain`, allowing another draft while SMTP acceptance was unresolved. | Defined one recipient-lock state contract shared by draft creation and preflight. | Interrupted-delivery duplicate and preflight test |
| OUT-002 | Critical | Concurrent send requests could both pass the active-job check and reserve overlapping daily capacity. | Made active-job validation, account validation, database reservation, job registration, and executor submission one application-level critical section. | Full API and compliance send suite |
| OUT-003 | High | Corporate-status and privacy-notice confirmations were accepted but discarded, leaving no durable approval evidence. | Persisted the human approval record, reviewer, flags, and timestamp inside the existing audit document without requiring a destructive database migration. | Approval audit assertions |
| OUT-004 | High | Opt-out addresses were weakly validated, not exposed in the audit record, and could differ from the selected sending account. | Added strict address validation, durable audit storage, and pre-send matching against the account's From or Reply-To address. | Invalid address and account mismatch tests |
| OUT-005 | High | The daily limit counted only completed `sent` events, not queued/sending reservations or mail accepted after suppression. | Counted active reservations and every accepted SMTP outcome before admitting a new batch. | Compliance queue suite |
| OUT-006 | High | Application shutdown did not signal an active campaign, so background sends could continue while the desktop window closed. | Added a shutdown event, stop requests for every active campaign, and release of drafts whose SMTP attempt had not started. | Shutdown and worker regression paths |
| OUT-007 | High | Retention purge either deleted delivery evidence or, after an initial conservative fix, retained recipient PII indefinitely. | Old inactive drafts without delivery history are deleted; records with delivery history are irreversibly redacted while status, timestamps, and provider audit remain. | `test_retention_purges_pii_but_keeps_delivery_audit` |
| OUT-008 | High | A suppression added during SMTP delivery could be overwritten by the later uncertain state. | Preserved `blocked` as the authoritative draft state while recording an independent uncertain delivery event. | `test_uncertain_delivery_keeps_blocked_suppression_state` |
| OUT-009 | High | Approved content was not checked against current lead data before queue or export. | Revalidated recipient, score, evidence, and personalization inputs against a stable lead snapshot at the final boundary. | Lead-change queue rejection test |
| OUT-010 | High | A parent-domain suppression did not block a lead or mailbox hosted on a subdomain. | Canonicalized domain suppressions to the registered business domain and checked email, host, and registered domains together. | Parent-domain/subdomain suppression test |
| OUT-011 | Medium | Executor rejection during shutdown could leave drafts stuck in `queued`. | Roll back the in-memory job and release every unstarted reservation when submission fails. | Covered by defensive submission path |
| OUT-012 | High | The worker reloaded a mutable email account after validation, so changing Settings while queued could bypass the opt-out/account match. | Captured an immutable, private delivery-config snapshot at reservation time; secrets never enter the public job payload. | API send path and independent patch review |

### Verification

- 182 Python tests pass; 56 focused API and compliance tests pass.
- Ruff passes for the application, tests, desktop entry point, and benchmarks.
- Frontend ESLint, production build, and Vitest pass.
- Outreach regressions cover consent, approval, suppression, restart recovery,
  SMTP uncertainty, account binding, stale lead evidence, export, and audit output.

### Score

- Baseline: 4.9/10
- Loop 1: 7.5/10
- Loop 2: 8.7/10
- Final: **8.7/10**
- Residual risks: SMTP cannot retract a message once the server accepts it; those
  ambiguous outcomes are deliberately quarantined as `uncertain`. Suppression
  hashes are privacy-minimized but are not keyed, so a future schema migration
  should replace SHA-256 with a keyed digest.

## Stage 5: Settings, Models, Storage, Themes, and Branding

### Findings

| ID | Severity | Defect | Fix | Regression |
|---|---|---|---|---|
| SET-001 | Critical | Workspace migration deleted the source database before export migration completed, and retry then refused the partial destination. | Added restartable staging, integrity checks, idempotent export merge, and source cleanup only after the complete destination commits. | Interrupted export copy and corrupt staging recovery test |
| SET-002 | Critical | A database appearing at the destination after scheduling could be adopted and cause the real source to be deleted. | Bound every migration to its source with a durable marker and SHA-256 destination identity check. | `test_migration_never_adopts_a_database_that_appears_after_scheduling` |
| SET-003 | High | Corrupt `storage.json` silently opened an empty default workspace, making existing data appear lost. | Invalid locator files now stop with an explicit recovery error and never fall back silently. | Invalid locator regression |
| SET-004 | High | “Use selected folder” accepted corrupt or unrelated SQLite files, while nested move targets could recursively migrate themselves. | Validate integrity and Leadroom schema before scheduling, and reject overlapping move paths. | Corrupt database and nested destination tests |
| SET-005 | High | Malformed persisted provider, endpoint, model, theme, domains, SMTP values, or accounts could break Settings and new runs. | Added typed read-time sanitization with compare-and-set persistence so stale repairs cannot overwrite a newer user edit. | Stored-settings repair and stale-repair race tests |
| SET-006 | High | One unreadable DPAPI secret disabled every settings consumer. | Isolated decryption per secret, cleared only the unreadable value in memory, and exposed a re-entry marker without revealing ciphertext. | Unreadable-secret API test |
| SET-007 | High | Model connection testing accepted a reachable endpoint even when the selected model was missing or unable to generate. | Inventory now must contain the selected model and a real generation request must return usable content. | Compatible-provider and missing-model tests |
| SET-008 | High | Enrichment could start with a locally selected model that had been deleted outside Leadroom. | Added an installed-model gate before Start, Continue-enrichment, and Retry, leaving the run state unchanged on failure. | Missing-local-model start test |
| SET-009 | High | The fit test used a reduced ad hoc schema unrelated to production extraction. | It now uses the full `LeadExtraction` schema and parser against realistic HTML with evidence-only instructions. | Ollama benchmark regression |
| SET-010 | High | Unlimited, non-cancellable model pulls shared workers with discovery and could block forever. | Added a dedicated single-worker download queue, duplicate lock, bounded reads, queued cancellation, and active stream interruption by closing its private HTTP client. | Queued and active cancellation tests |
| SET-011 | High | Theme requests could finish out of order, and automatic repairs could race with user saves. | Added persistent monotonic theme versions, server-side stale-write rejection, compare-and-set repairs, and client rollback only for the current request. | Stale theme version and repair race tests |
| SET-012 | Medium | Selecting a model saved the entire unfinished Settings form. | Added a narrow installed-model endpoint so model choice changes only `model_name`. | Model-only persistence test |
| SET-013 | Medium | Logo validation trusted MIME text and byte length rather than image content or dimensions. | Added Pillow decode/verify, format matching, and dimension/pixel limits; Pillow is now an explicit runtime dependency. | Invalid image bytes test |

### Verification

- 195 Python tests pass, including the final independent-review regressions.
- Ruff, dependency integrity, frontend ESLint, production build, and Vitest pass.
- An independent second review confirmed all previously reported critical/high
  migration, settings-ordering, and active-cancellation findings are fixed.

### Score

- Baseline: 4.8/10
- Loop 1: 7.2/10
- Loop 2: 8.1/10
- Loop 3: 8.8/10
- Final: **8.8/10**
- Residual risks: a corrupt storage locator intentionally stops startup but does
  not yet provide a graphical recovery chooser; that desktop recovery UX belongs
  to Stage 6. Moving Ollama models still requires restarting Ollama because its
  model directory is process-level configuration.

## Stage 6: Desktop Shell, Packaging, Installation, and Shutdown

### Findings

| ID | Severity | Defect | Fix | Regression |
|---|---|---|---|---|
| DESK-001 | Critical | Inno Setup waited forever when the bootstrap helper exited before writing its completion file. | The helper now publishes its PID; Setup waits for startup with a bound and monitors process liveness until completion. | Installer contract test plus PowerShell parse and PlanOnly |
| DESK-002 | High | Cancel did not stop Winget or Full Local child process trees, and a stalled Ollama response could block before headers or between stream lines. | Long-running native commands now run through a cancellable process-tree wrapper; every model-download async boundary polls cancellation. | Cancellable-bootstrap contract tests |
| DESK-003 | High | Cancelling while a temporary Ollama service was starting could leave it orphaned. | `Wait-Ollama` now owns and stops the process on cancellation, timeout, or startup failure. | Bootstrap ownership assertion |
| DESK-004 | High | A slow helper startup could time out while the helper later continued installing in the background. | Startup timeout now leaves a durable cancellation marker that the late helper observes before any installation work. | Installer watchdog contract test |
| DESK-005 | High | Windows PowerShell 5.1 could ignore failed WSL native commands and continue to a false success. | Every WSL, PostgreSQL, download, import, and timer operation now checks its native exit code immediately. | All three Full Local scripts have fail-fast contract coverage |
| DESK-006 | High | Full Local checked only the selected downloads drive even though the Ubuntu VHD may consume the system drive. | Preflight resolves the actual Ubuntu WSL base path and requires 30 GB free there before import. | WSL-storage capacity contract test |
| DESK-007 | High | Closing the native window could leave Uvicorn or non-daemon workers alive indefinitely. | Shutdown escalates from graceful exit to Uvicorn force-exit, then uses a five-second worker bound before terminating the desktop process. | Graceful escalation and stuck-worker tests |
| DESK-008 | High | Storage config, migration, inaccessible-drive, database-validation, and exports-directory failures could close the window silently while retaining the instance lock. | One startup recovery boundary now shows a native error, preserves the workspace, and always releases the lock. | Parameterized startup recovery tests |

### Verification

- 204 Python tests pass; 18 focused desktop and installer tests pass.
- Ruff, dependency integrity, frontend ESLint, Vitest, and production build pass.
- All installer PowerShell files parse successfully and bootstrap PlanOnly emits
  a valid non-destructive plan.
- Independent review found no remaining critical/high Stage 6 issue after the
  second repair loop.

### Score

- Baseline: 4.5/10
- Loop 1: 7.2/10
- Loop 2: 7.9/10
- Loop 3: 8.7/10
- Final: **8.7/10**
- Residual risks: Inno Setup is not installed in the development environment, so
  compilation and a clean-machine installer smoke test remain release gates.
  No setup or portable artifact was built during this stage.

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
