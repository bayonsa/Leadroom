# Windows Packaging

Leadroom currently targets 64-bit Windows 10 and Windows 11. The installer is a local release candidate until clean-machine validation and the binary dependency-licence review are complete.

## Build Requirements

- Python 3.12 or 3.13 with `requirements-dev.txt` installed
- Node.js 22+
- Inno Setup 6 (`winget install --id JRSoftware.InnoSetup --exact --source winget`)

## Build All Artifacts

```powershell
.\scripts\build-release.ps1 -Version 0.1.0
```

This produces ignored local artifacts in `dist`:

- `Leadroom-Setup.exe`
- `Leadroom-Portable.zip`
- `checksums.txt`

The installer contains the application executable, licence and third-party notices, bootstrap scripts, and optional Full Local data scripts. Large models and map data are fetched only after explicit selection in the installer.

## Installer Experience

The Wizard provides:

1. Standard or Full Local installation mode
2. Separate workspace-data and large-download folders
3. Optional WebView2 and Ollama installation through `winget`
4. Optional verified `ollama pull` for `llama3.2:3b`
5. Optional WSL/PostgreSQL/PostGIS/OpenStreetMap setup for Full Local
6. Start Menu and optional Desktop shortcuts

Upgrades preserve an existing `storage.json`. Uninstall removes application files and asks whether workspace data and downloads should be retained.

## Silent Test Parameters

```powershell
.\dist\Leadroom-Setup.exe `
  /VERYSILENT /SUPPRESSMSGBOXES /NORESTART `
  /DIR="D:\Apps\Leadroom" `
  /DATAROOT="D:\LeadroomData\workspace" `
  /DOWNLOADSROOT="D:\LeadroomData\downloads" `
  /INSTALL_WEBVIEW=1 /INSTALL_OLLAMA=1 /DOWNLOAD_MODEL=1
```

Other parameters are `/INSTALLMODE=full`, `/SETUP_LOCAL_DATA=1`, and the test-only `/FORCE_STORAGE=1`.

## Smoke Test

```powershell
.\scripts\test-installer.ps1
```

The smoke test temporarily backs up the current Leadroom bootstrap folder, silently installs to `build`, starts the installed executable on a dedicated localhost port, checks `/api/v1/health`, runs the uninstaller, and restores the original bootstrap folder and Ollama environment setting.

## Publication Blockers

Do not upload these artifacts to a public GitHub Release yet. Complete the clean Windows 10/11 matrix, test a fresh Full Local import, add CI artifact generation, and resolve the binary-distribution issue recorded in `DEPENDENCY_LICENSES.md` first.
