# Contributing to Leadroom

Thanks for helping improve Leadroom. The project is currently Windows-first and pre-release.

## Development Setup

Follow the source installation steps in [README.md](README.md), then run:

```powershell
.\scripts\check.ps1
```

Frontend changes should also be checked at desktop and mobile widths with Playwright. Keep changes focused and add tests for changed behaviour.

## Pull Requests

1. Explain the user problem and the chosen behaviour.
2. Add or update backend, frontend, and browser tests in proportion to the change.
3. Run the relevant quality checks and report anything that could not be run.
4. Update README, compliance, release, or architecture documentation when contracts change.
5. Keep generated artifacts and unrelated formatting churn out of the diff.

## Sensitive Data

Never commit:

- `.env` files, API keys, SMTP passwords, app passwords, cookies, or access tokens;
- SQLite databases, exports, logs, caches, Ollama models, OSM extracts, or Postgres dumps;
- screenshots or fixtures containing real businesses, contacts, user paths, or account names.

Use reserved `.example` domains and fictional identities in tests and documentation. If a secret enters Git history, revoke it immediately and purge the history before publishing.

## Legal and Data Responsibilities

Only collect public business information you are permitted to process. Changes to outreach eligibility, suppression, retention, or delivery controls require tests and a corresponding update to [COMPLIANCE.md](COMPLIANCE.md).
