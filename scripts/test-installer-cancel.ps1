param(
    [string]$SetupPath = "",
    [string]$Model = "phi3:mini"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$build = (Resolve-Path (Join-Path $root "build")).Path
if (-not $SetupPath) { $SetupPath = Join-Path $root "dist\Leadroom-Setup.exe" }
$SetupPath = (Resolve-Path $SetupPath).Path
$testRoot = Join-Path $build ("installer-cancel-" + [guid]::NewGuid().ToString("N"))
$app = Join-Path $testRoot "app"
$data = Join-Path $testRoot "data"
$downloads = Join-Path $testRoot "downloads"
$bootstrap = Join-Path $env:LOCALAPPDATA "Leadroom"
$backup = Join-Path $testRoot "bootstrap-backup"
$hadBootstrap = Test-Path -LiteralPath $bootstrap
$originalModels = [Environment]::GetEnvironmentVariable("OLLAMA_MODELS", "User")

Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class LeadroomInstallerWindows {
    public delegate bool EnumWindowsProc(IntPtr hwnd, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr parent, EnumWindowsProc callback, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int count);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr hwnd, uint message, IntPtr wParam, IntPtr lParam);
}
"@

function Get-WindowText([IntPtr]$Handle) {
    $text = [Text.StringBuilder]::new(512)
    [void][LeadroomInstallerWindows]::GetWindowText($Handle, $text, $text.Capacity)
    return $text.ToString()
}

function Find-TopWindow([string]$Caption) {
    $found = [IntPtr]::Zero
    $callback = [LeadroomInstallerWindows+EnumWindowsProc]{
        param($handle, $state)
        if ([LeadroomInstallerWindows]::IsWindowVisible($handle) -and (Get-WindowText $handle) -eq $Caption) {
            $script:foundTopWindow = $handle
            return $false
        }
        return $true
    }
    $script:foundTopWindow = [IntPtr]::Zero
    [void][LeadroomInstallerWindows]::EnumWindows($callback, [IntPtr]::Zero)
    return $script:foundTopWindow
}

function Find-ChildWindow([IntPtr]$Parent, [string]$Caption) {
    $callback = [LeadroomInstallerWindows+EnumWindowsProc]{
        param($handle, $state)
        if ([LeadroomInstallerWindows]::IsWindowVisible($handle) -and (Get-WindowText $handle) -eq $Caption) {
            $script:foundChildWindow = $handle
            return $false
        }
        return $true
    }
    $script:foundChildWindow = [IntPtr]::Zero
    [void][LeadroomInstallerWindows]::EnumChildWindows($Parent, $callback, [IntPtr]::Zero)
    return $script:foundChildWindow
}

function Remove-TreeWithRetry([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    for ($attempt = 0; $attempt -lt 10; $attempt++) {
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force
            return
        } catch {
            if ($attempt -eq 9) { throw }
            Start-Sleep -Milliseconds (250 * ($attempt + 1))
        }
    }
}

New-Item -ItemType Directory -Force -Path $testRoot | Out-Null
if ($hadBootstrap) { Copy-Item -LiteralPath $bootstrap -Destination $backup -Recurse -Force }
$setup = $null
try {
    $arguments = @(
        "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
        "/DIR=$app", "/DATAROOT=$data", "/DOWNLOADSROOT=$downloads",
        "/INSTALL_WEBVIEW=0", "/INSTALL_OLLAMA=0", "/DOWNLOAD_MODEL=1",
        "/MODEL=$Model", "/FORCE_STORAGE=1",
        "/LOG=$(Join-Path $build 'installer-cancel.log')"
    )
    $setup = Start-Process -FilePath $SetupPath -ArgumentList $arguments -PassThru
    $deadline = (Get-Date).AddMinutes(2)
    $button = [IntPtr]::Zero
    while ((Get-Date) -lt $deadline -and -not $setup.HasExited) {
        $window = Find-TopWindow "Setup - Leadroom"
        if ($window -ne [IntPtr]::Zero) {
            $download = Find-ChildWindow $window "Downloading $Model"
            $button = Find-ChildWindow $window "Cancel setup"
            if ($download -ne [IntPtr]::Zero -and $button -ne [IntPtr]::Zero) { break }
        }
        Start-Sleep -Milliseconds 250
        $setup.Refresh()
    }
    if ($button -eq [IntPtr]::Zero) { throw "The cancellable model-download page did not appear." }
    [void][LeadroomInstallerWindows]::SendMessage($button, 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero)
    if (-not $setup.WaitForExit(30000)) { throw "Setup did not stop within 30 seconds of cancellation." }
    if ($setup.ExitCode -eq 0) { throw "Cancelled Setup returned a success exit code." }
    if (Test-Path -LiteralPath (Join-Path $app "Leadroom.exe")) {
        throw "Cancelled Setup left Leadroom.exe behind."
    }
    $modelsAfterCancel = [Environment]::GetEnvironmentVariable("OLLAMA_MODELS", "User")
    if ($modelsAfterCancel -ne $originalModels) {
        throw "Cancelled Setup did not restore the previous OLLAMA_MODELS setting."
    }
    $orphan = Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" |
        Where-Object { $_.CommandLine -like "*install-bootstrap.ps1*" }
    if ($orphan) { throw "Cancelled Setup left its bootstrap process running." }
    Write-Host "Installer cancellation stopped the download and left no installed application files."
} finally {
    if ($setup -and -not $setup.HasExited) { Stop-Process -Id $setup.Id -Force -ErrorAction SilentlyContinue }
    [Environment]::SetEnvironmentVariable("OLLAMA_MODELS", $originalModels, "User")
    if (Test-Path -LiteralPath $bootstrap) { Remove-TreeWithRetry $bootstrap }
    if ($hadBootstrap -and (Test-Path -LiteralPath $backup)) {
        Move-Item -LiteralPath $backup -Destination $bootstrap
    }
    if (Test-Path -LiteralPath $testRoot) { Remove-TreeWithRetry $testRoot }
}
