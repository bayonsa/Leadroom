# Leadroom Release Plan

## Current Status

Leadroom has a public source repository and locally built installer/portable release candidates. Do not publish a binary GitHub Release until clean-machine validation, automation, and the dependency-licence blocker in `docs/DEPENDENCY_LICENSES.md` are complete.

## Goal

Publish Leadroom as an open-source Windows application that can be installed and used without manually configuring Python or frontend dependencies.

Initial supported platform:

- Windows 10/11
- 64-bit systems

## Release Packages

Each GitHub release should provide:

- `Leadroom-Setup.exe`: guided Windows installer
- `Leadroom-Portable.zip`: portable build that does not require installation
- `checksums.txt`: SHA-256 checksums for release files
- Release notes and upgrade instructions
- Source code archive, license, and third-party notices

## Installation Modes

### Standard

Designed for most users:

- Install Leadroom and create Start Menu/Desktop shortcuts
- Create the local application data directories and SQLite database
- Check whether Ollama is available
- Offer to install Ollama with user approval
- Offer to download a recommended lightweight model
- Enable web discovery and normal enrichment workflows

### Full Local

Designed for powerful computers and offline/private discovery:

- Include everything from Standard mode
- Check available RAM, disk space, and supported Windows version
- Install or configure PostgreSQL and PostGIS
- Download and import the selected OpenStreetMap dataset
- Configure automatic local-data updates
- Offer one or more larger recommended Ollama models
- Display download size and estimated disk usage before starting

Large models and datasets should be downloaded on demand instead of being embedded in the installer.

## Technical Stack

- PyInstaller for the packaged Leadroom executable
- Inno Setup for `Leadroom-Setup.exe`
- PowerShell bootstrap scripts for prerequisite detection and optional downloads
- GitHub Actions for reproducible builds and GitHub Releases
- SHA-256 checksums for downloadable artifacts
- Optional code signing for trusted Windows distribution

## Installer Requirements

The installer should:

- Require as few decisions as possible
- Show Standard and Full Local as clear installation choices
- Never install large optional components without explicit approval
- Check network connectivity, free disk space, RAM, and required ports
- Resume or safely retry interrupted downloads
- Verify downloaded files using checksums
- Avoid opening visible command windows during background setup
- Preserve user data during application upgrades
- Provide a complete uninstaller
- Keep optional datasets and models when requested during uninstall
- Write actionable installation logs

## First-Run Setup

On first launch, Leadroom should provide an in-app setup flow for:

1. Workspace name, subtitle, logo, and theme
2. Discovery mode: Web, Local, or Both
3. Ollama detection and installation status
4. Installed and downloadable model selection
5. Model compatibility benchmark
6. Optional SMTP and paid model-provider configuration
7. Optional local dataset setup
8. Final health check before entering the workspace

Secrets must be stored using Windows DPAPI or an equivalent operating-system credential store.

## Open-Source Readiness

Before publication:

- Choose and add an open-source license
- Add `CONTRIBUTING.md`, `SECURITY.md`, and a code of conduct
- Document supported hardware and operating systems
- Document data-source licenses and OpenStreetMap attribution
- Audit bundled dependency licenses
- Ensure no API keys, passwords, local databases, logs, or personal data are committed
- Add issue and pull-request templates
- Add architecture, development, testing, and packaging documentation

## GitHub Automation

The release workflow should:

1. Run backend tests
2. Run frontend lint, unit tests, production build, and Playwright tests
3. Build the PyInstaller executable
4. Smoke-test the packaged executable
5. Build the Inno Setup installer
6. Build the portable ZIP
7. Generate SHA-256 checksums
8. Sign artifacts when a certificate is configured
9. Upload artifacts and release notes to GitHub Releases

## Update Strategy

The first public release may use manual updates through GitHub Releases. A later phase can add:

- In-app update notifications
- Download and checksum verification
- Safe replacement of application binaries
- Database migration and rollback support
- Stable, beta, and nightly release channels

## Release Phases

### Phase 1: Repository Readiness

- [x] Select the licence
- [x] Clean and document the repository
- [x] Add contributor, conduct, security, issue, and pull-request documentation
- [x] Audit the current dependency licences and record binary-release blockers
- [x] Confirm reproducible local builds from a fresh clone

Validated on Windows with Python 3.12 on 22 July 2026 by creating a new local clone, installing `requirements-dev.txt` and the locked frontend packages, and running `scripts/check.ps1` successfully.

### Phase 2: Portable Release

- [x] Finalize PyInstaller packaging
- [x] Add packaged-app and installer smoke tests
- [x] Generate `Leadroom-Portable.zip`
- [ ] Verify operation on a clean Windows user profile

### Phase 3: Windows Installer

- [x] Create the Inno Setup project
- [x] Add shortcuts, data directories, upgrade behavior, and uninstaller
- [x] Add Standard and Full Local installation choices
- [x] Prevent visible terminal windows during setup

### Phase 4: Dependency Bootstrap

- [x] Detect and optionally install WebView2 and Ollama
- [x] Download and verify recommended models
- [x] Detect and optionally configure PostgreSQL/PostGIS
- [x] Download, import, and update OpenStreetMap data
- [x] Add resumable model and map downloads

### Phase 5: First-Run Experience

- Build the guided setup flow inside Leadroom
- Add system and model compatibility checks
- Add clear progress, pause, resume, retry, and cancellation states

### Phase 6: Automated Releases

- Add GitHub Actions build and test pipelines
- Generate installer, portable package, checksums, and release notes
- Add optional artifact signing

### Phase 7: Clean-Machine Validation

- Test Standard installation on clean Windows 10 and Windows 11 systems
- Test Full Local installation and interrupted downloads
- Test upgrades without losing user data
- Test uninstall behavior
- Resolve issues until the release workflow reaches at least 9/10 readiness

## Definition of Done

The release phase is complete when:

- A non-developer can install and launch Leadroom without installing Python or Node.js
- Standard mode completes with minimal interaction
- Full Local mode clearly communicates size and hardware requirements
- Downloads are verified and recoverable
- The packaged app passes automated health, authentication, deep-link, and single-instance smoke tests
- Updates preserve workspace settings, repositories, runs, and compliance records
- Installer and portable artifacts are reproducibly generated by GitHub Actions
- Documentation is sufficient for users and contributors
- Clean-machine validation reaches at least 9/10
