# Security Policy

## Supported Versions

Leadroom is currently pre-release. Security fixes are applied to the latest commit on the default branch; older snapshots are not maintained.

## Reporting a Vulnerability

Please use GitHub's private vulnerability reporting for this repository. Do not open a public issue containing API keys, SMTP credentials, lead data, database files, logs with personal information, or exploit details.

Include:

- the affected commit or build;
- reproduction steps and expected impact;
- whether the issue can expose credentials, lead data, or send email;
- any suggested mitigation.

Rotate any credential that may have been exposed before sending a report. Acknowledgement and remediation timing will depend on severity and maintainer availability.

## Security Boundaries

- The supported desktop build is local to Windows and binds its API to loopback.
- Stored application secrets use Windows DPAPI for the current user.
- Web discovery, target websites, model APIs, SMTP servers, Ollama catalog access, and optional dataset downloads are external trust boundaries.
- Source runs on non-Windows platforms do not receive DPAPI protection and are not supported release targets.
- Leadroom's outreach checks reduce mistakes but do not establish legal compliance.
