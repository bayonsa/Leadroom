# Test and Reliability Strategy

## Release Gate

The release gate is layered so failures stay fast and diagnosable:

1. Python unit and integration tests cover schemas, filtering, enrichment, persistence, API contracts, restart, cancellation, retries, and disk failures.
2. The labelled benchmark protects candidate precision across salons, dentists, and accountants.
3. Frontend unit tests protect the API client contract; TypeScript build and ESLint protect static correctness.
4. Playwright runs the primary review and edit workflows at 1440x960 and 390x844, checks console errors and horizontal overflow, and retains traces on failure.
5. Preflight verifies the writable data path, Ollama service, and configured local model.

Run the offline gate with `scripts/check.ps1`. With the API and UI running, run `scripts/release-check.ps1` to include browser tests.

## Performance Budgets

| Surface | Local budget | Measurement |
|---|---:|---|
| Health API | 250 ms p95 | release-check HTTP samples |
| Persisted run detail API | 500 ms p95 for 500 candidates | integration benchmark |
| Initial UI production bundle | 150 KiB gzip JavaScript | Vite build output |
| UI navigation to persisted run | 2 seconds | Playwright assertion |
| Live progress refresh | 2 seconds | React Query polling interval |
| Candidate HTTP fetch | 12 seconds per attempt | validated configuration |

Budgets target a local single-user Windows product. External search and model latency are recorded separately and do not relax UI or persisted-data budgets.

## Privacy-Safe Diagnostics

`GET /api/v1/runs/{run_id}/diagnostics` returns database integrity, non-secret run settings, status counts, and the last 100 structured events. It excludes environment variables, raw page HTML, and private credentials.

## Residual Risks

- Live provider and website behavior remains variable; stable fixtures and labelled cases are the release gate.
- ScrapeGraphAI currently emits upstream Pydantic and LangChain deprecation warnings.
- Clean-machine Windows installation and forced OS-process termination are deferred to packaging validation.
