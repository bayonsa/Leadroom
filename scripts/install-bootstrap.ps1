param(
    [ValidateSet("Standard", "FullLocal")]
    [string]$Mode = "Standard",
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [Parameter(Mandatory = $true)]
    [string]$DataRoot,
    [Parameter(Mandatory = $true)]
    [string]$DownloadsRoot,
    [string]$Model = "llama3.2:3b",
    [string]$OsmRegion = "great-britain",
    [switch]$InstallWebView,
    [switch]$InstallOllama,
    [switch]$DownloadModel,
    [switch]$SetupLocalData,
    [switch]$ForceStorage,
    [switch]$PlanOnly,
    [string]$StatusPath,
    [string]$CompletionPath
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "Continue"

$bootstrapRoot = Join-Path $env:LOCALAPPDATA "Leadroom"
$logDirectory = Join-Path $bootstrapRoot "logs"
$logPath = Join-Path $logDirectory "install.log"

function Write-InstallerStatus(
    [int]$Percent,
    [string]$Title,
    [string]$Detail
) {
    if ([string]::IsNullOrWhiteSpace($StatusPath)) { return }
    $safeTitle = ($Title -replace "[\r\n]+", " ").Trim()
    $safeDetail = ($Detail -replace "[\r\n]+", " ").Trim()
    $temporary = "$StatusPath.writing"
    @($Percent, $safeTitle, $safeDetail) |
        Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $StatusPath -Force
}

function Complete-InstallerBootstrap([int]$ExitCode) {
    if (-not [string]::IsNullOrWhiteSpace($CompletionPath)) {
        Set-Content -LiteralPath $CompletionPath -Value $ExitCode -Encoding ASCII
    }
}

trap {
    $message = $_.Exception.Message
    Write-InstallerStatus 0 "Setup could not continue" $message
    try { Write-InstallLog "Bootstrap failed: $message" } catch {}
    Complete-InstallerBootstrap 1
    exit 1
}

function Write-InstallLog([string]$Message) {
    $line = "{0:u} {1}" -f (Get-Date), $Message
    Write-Host $line
    if (-not $PlanOnly) {
        New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
        Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
    }
}

function Resolve-AbsoluteDirectory([string]$Value, [string]$Label) {
    if ([string]::IsNullOrWhiteSpace($Value) -or -not [IO.Path]::IsPathRooted($Value)) {
        throw "$Label must be an absolute Windows folder path."
    }
    return [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($Value))
}

function Get-FreeBytes([string]$Path) {
    $root = [IO.Path]::GetPathRoot($Path)
    if ([string]::IsNullOrWhiteSpace($root)) { return 0 }
    return ([IO.DriveInfo]::new($root)).AvailableFreeSpace
}

function Assert-Capacity([string]$Path, [long]$RequiredBytes, [string]$Label) {
    $free = Get-FreeBytes $Path
    if ($free -lt $RequiredBytes) {
        $requiredGb = [math]::Ceiling($RequiredBytes / 1GB)
        $freeGb = [math]::Round($free / 1GB, 1)
        throw "$Label needs at least $requiredGb GB free; only $freeGb GB is available."
    }
}

function Find-Winget {
    $command = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    return $null
}

function Install-WingetPackage([string]$Id, [string]$Name) {
    $winget = Find-Winget
    if (-not $winget) {
        throw "$Name is missing and Windows Package Manager (winget) is unavailable. Install App Installer and retry."
    }
    Write-InstallLog "Installing $Name with winget."
    & $winget install --id $Id --exact --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw "$Name installation failed with exit code $LASTEXITCODE." }
}

function Invoke-OllamaModelPull([string]$Endpoint, [string]$ModelName) {
    $client = [Net.Http.HttpClient]::new()
    $client.Timeout = [Threading.Timeout]::InfiniteTimeSpan
    try {
        $payload = @{ name = $ModelName; stream = $true } | ConvertTo-Json -Compress
        $content = [Net.Http.StringContent]::new($payload, [Text.Encoding]::UTF8, "application/json")
        $request = [Net.Http.HttpRequestMessage]::new([Net.Http.HttpMethod]::Post, "$Endpoint/api/pull")
        $request.Content = $content
        $response = $client.SendAsync($request, [Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
        $response.EnsureSuccessStatusCode()
        $stream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $reader = [IO.StreamReader]::new($stream)
        try {
            while (-not $reader.EndOfStream) {
                $line = $reader.ReadLine()
                if ([string]::IsNullOrWhiteSpace($line)) { continue }
                $event = $line | ConvertFrom-Json
                if ($event.error) { throw [InvalidOperationException]::new([string]$event.error) }
                $status = if ($event.status) { [string]$event.status } else { "Receiving model data" }
                if ($event.total -and [long]$event.total -gt 0) {
                    $percent = [math]::Min(100, [math]::Floor(([double]$event.completed / [double]$event.total) * 100))
                    $receivedGb = [math]::Round([double]$event.completed / 1GB, 2)
                    $totalGb = [math]::Round([double]$event.total / 1GB, 2)
                    Write-InstallerStatus $percent "Downloading $ModelName" "$status - $percent% ($receivedGb of $totalGb GB)"
                } else {
                    Write-InstallerStatus 0 "Downloading $ModelName" $status
                }
            }
        } finally {
            $reader.Dispose()
            $stream.Dispose()
            $response.Dispose()
            $request.Dispose()
        }
    } finally {
        $client.Dispose()
    }
}

function Test-WebViewRuntime {
    $clientId = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    $keys = @(
        "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$clientId",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$clientId",
        "HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$clientId"
    )
    return [bool]($keys | Where-Object { Test-Path $_ } | Select-Object -First 1)
}

function Find-Ollama {
    $command = Get-Command ollama.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"),
        (Join-Path $env:ProgramFiles "Ollama\ollama.exe")
    )
    return $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}

function Wait-Ollama([string]$Executable, [string]$Endpoint = "http://127.0.0.1:11434") {
    try {
        Invoke-RestMethod -Uri "$Endpoint/api/tags" -TimeoutSec 2 | Out-Null
        return $null
    } catch {
        Write-InstallLog "Starting the local Ollama service."
        $started = Start-Process -FilePath $Executable -ArgumentList "serve" -WindowStyle Hidden -PassThru
    }
    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 750
        try {
            Invoke-RestMethod -Uri "$Endpoint/api/tags" -TimeoutSec 2 | Out-Null
            return $started
        } catch {}
    }
    throw "Ollama was installed but its local service did not become ready."
}

function Save-StorageLocator([string]$DataPath, [string]$DownloadsPath) {
    New-Item -ItemType Directory -Force -Path $bootstrapRoot, $DataPath, $DownloadsPath | Out-Null
    $configPath = Join-Path $bootstrapRoot "storage.json"
    if ((Test-Path -LiteralPath $configPath) -and -not $ForceStorage) {
        Write-InstallLog "Keeping the existing storage configuration during upgrade."
        return
    }
    $payload = [ordered]@{
        data_root = $DataPath
        downloads_root = $DownloadsPath
        data_action = "use"
        move_downloads = $false
    }
    $temporary = "$configPath.installing"
    $payload | ConvertTo-Json | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $configPath -Force
    Write-InstallLog "Configured workspace storage at $DataPath and downloads at $DownloadsPath."
}

$InstallRoot = Resolve-AbsoluteDirectory $InstallRoot "Install folder"
$DataRoot = Resolve-AbsoluteDirectory $DataRoot "Workspace data folder"
$DownloadsRoot = Resolve-AbsoluteDirectory $DownloadsRoot "Downloads folder"

$minimumDownloadSpace = if ($Mode -eq "FullLocal") { 35GB } elseif ($DownloadModel) { 5GB } else { 1GB }
Assert-Capacity $DataRoot 500MB "Workspace data folder"
Assert-Capacity $DownloadsRoot $minimumDownloadSpace "Downloads folder"

$plan = [ordered]@{
    mode = $Mode
    install_root = $InstallRoot
    data_root = $DataRoot
    downloads_root = $DownloadsRoot
    install_webview = [bool]$InstallWebView
    install_ollama = [bool]$InstallOllama
    download_model = [bool]$DownloadModel
    model = $Model
    setup_local_data = [bool]$SetupLocalData
    force_storage = [bool]$ForceStorage
    osm_region = $OsmRegion
}
if ($PlanOnly) {
    $plan | ConvertTo-Json
    Complete-InstallerBootstrap 0
    exit 0
}

Write-InstallerStatus 5 "Checking this computer" "Validating storage space and selected components"
Write-InstallLog "Starting Leadroom $Mode bootstrap."

if (-not (Test-WebViewRuntime)) {
    if (-not $InstallWebView) { throw "Microsoft Edge WebView2 Runtime is required to open Leadroom." }
    Write-InstallerStatus 10 "Installing WebView2" "Windows Package Manager is preparing the desktop runtime"
    Install-WingetPackage "Microsoft.EdgeWebView2Runtime" "Microsoft Edge WebView2 Runtime"
}
Write-InstallerStatus 20 "WebView2 is ready" "Checking the local AI runtime"
Write-InstallLog "WebView2 runtime is ready."

$ollama = Find-Ollama
if (-not $ollama -and $InstallOllama) {
    Write-InstallerStatus 25 "Installing Ollama" "Windows Package Manager is preparing the local AI runtime"
    Install-WingetPackage "Ollama.Ollama" "Ollama"
    $env:Path = "$env:LOCALAPPDATA\Programs\Ollama;$env:Path"
    $ollama = Find-Ollama
}
if ($DownloadModel -and -not $ollama) {
    throw "The selected model cannot be downloaded because Ollama is not installed."
}
if ($ollama -and ($InstallOllama -or $DownloadModel)) {
    $modelDirectory = Join-Path $DownloadsRoot "ollama\models"
    New-Item -ItemType Directory -Force -Path $modelDirectory | Out-Null
    $previousModelDirectory = [Environment]::GetEnvironmentVariable("OLLAMA_MODELS", "User")
    [Environment]::SetEnvironmentVariable("OLLAMA_MODELS", $modelDirectory, "User")
    $env:OLLAMA_MODELS = $modelDirectory
    Write-InstallLog "Ollama is ready and new models will be stored at $modelDirectory."
    if ($DownloadModel) {
        Write-InstallerStatus 30 "Starting Ollama" "Preparing the recommended model download"
        $temporaryServer = $null
        $previousHost = $env:OLLAMA_HOST
        try {
            $defaultServerRunning = $false
            try {
                Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2 | Out-Null
                $defaultServerRunning = $true
            } catch {}
            $endpoint = "http://127.0.0.1:11434"
            if ($defaultServerRunning -and $previousModelDirectory -ne $modelDirectory) {
                $env:OLLAMA_HOST = "127.0.0.1:11435"
                $endpoint = "http://127.0.0.1:11435"
                Write-InstallLog "Using an isolated Ollama download service for the selected model folder."
            }
            $temporaryServer = Wait-Ollama $ollama $endpoint
            Write-InstallLog "Downloading or verifying Ollama model $Model."
            Invoke-OllamaModelPull $endpoint $Model
            Write-InstallerStatus 90 "AI model is ready" "Finishing Leadroom setup"
            Write-InstallLog "Model $Model is ready."
        } finally {
            if ($temporaryServer) { Stop-Process -Id $temporaryServer.Id -Force -ErrorAction SilentlyContinue }
            if ($null -eq $previousHost) { Remove-Item Env:OLLAMA_HOST -ErrorAction SilentlyContinue }
            else { $env:OLLAMA_HOST = $previousHost }
        }
    }
} elseif ($ollama) {
    Write-InstallLog "Existing Ollama installation detected; no model download was selected."
}

if ($Mode -eq "FullLocal" -and $SetupLocalData) {
    Write-InstallerStatus 5 "Preparing local discovery" "Checking WSL2, Ubuntu, memory, and database tools"
    $memory = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory
    if ($memory -lt 16GB) { throw "Full Local setup requires at least 16 GB RAM." }
    $ubuntu = @(wsl.exe -l -q 2>$null) -replace "`0", "" | Where-Object { $_.Trim() -eq "Ubuntu" }
    if (-not $ubuntu) {
        throw "Full Local setup needs WSL2 with Ubuntu. Run 'wsl --install -d Ubuntu', restart Windows, then rerun the installer."
    }
    Write-InstallerStatus 10 "Building the local index" "Downloading and importing OpenStreetMap data; this can take a long time"
    Write-InstallLog "Installing the Full Local database engine."
    & (Join-Path $InstallRoot "scripts\setup-local-data.ps1")
    if ($LASTEXITCODE -ne 0) { throw "The Full Local database setup failed." }
    & (Join-Path $InstallRoot "scripts\import-osm.ps1") -Region $OsmRegion -DataDirectory (Join-Path $DownloadsRoot "osm")
    if ($LASTEXITCODE -ne 0) { throw "The OpenStreetMap import failed." }
}

Write-InstallerStatus 95 "Saving workspace settings" "Recording the selected storage folders"
Save-StorageLocator $DataRoot $DownloadsRoot
Write-InstallLog "Leadroom bootstrap completed successfully."
Write-InstallerStatus 100 "Leadroom is ready" "Selected components were prepared successfully"
Complete-InstallerBootstrap 0
