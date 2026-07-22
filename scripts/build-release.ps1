param(
    [string]$Version = "0.1.0",
    [switch]$SkipAppBuild
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$dist = Join-Path $root "dist"
$build = Join-Path $root "build"
$portableStage = Join-Path $build "Leadroom-Portable"
$portableArchive = Join-Path $dist "Leadroom-Portable.zip"

if (-not $SkipAppBuild) {
    & (Join-Path $PSScriptRoot "package.ps1")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if (-not (Test-Path (Join-Path $dist "Leadroom.exe"))) {
    throw "dist\Leadroom.exe is missing. Run scripts\package.ps1 first."
}

New-Item -ItemType Directory -Force -Path $dist, $build | Out-Null
if (Test-Path -LiteralPath $portableStage) {
    $resolved = (Resolve-Path -LiteralPath $portableStage).Path
    if (-not $resolved.StartsWith($build, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe portable staging path: $resolved"
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $portableStage | Out-Null
Copy-Item (Join-Path $dist "Leadroom.exe") $portableStage
Copy-Item (Join-Path $root "LICENSE") $portableStage
Copy-Item (Join-Path $root "THIRD_PARTY_NOTICES.md") $portableStage
Copy-Item (Join-Path $root "README.md") $portableStage
if (Test-Path -LiteralPath $portableArchive) { Remove-Item -LiteralPath $portableArchive -Force }
Compress-Archive -Path (Join-Path $portableStage "*") -DestinationPath $portableArchive -CompressionLevel Optimal

$isccCandidates = @(
    (Get-Command ISCC.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
$iscc = $isccCandidates | Select-Object -First 1
if (-not $iscc) {
    throw "Inno Setup 6 was not found. Install it with: winget install JRSoftware.InnoSetup"
}
& $iscc "/DAppVersion=$Version" (Join-Path $root "installer\Leadroom.iss")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$artifacts = @(
    (Join-Path $dist "Leadroom-Setup.exe"),
    $portableArchive
)
$checksumLines = foreach ($artifact in $artifacts) {
    if (-not (Test-Path -LiteralPath $artifact)) { throw "Missing release artifact: $artifact" }
    $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $artifact
    "{0}  {1}" -f $hash.Hash.ToLowerInvariant(), (Split-Path $artifact -Leaf)
}
$checksumLines | Set-Content -LiteralPath (Join-Path $dist "checksums.txt") -Encoding ASCII

Write-Host "Release artifacts are ready:"
Get-Item -LiteralPath ($artifacts + (Join-Path $dist "checksums.txt")) |
    Select-Object Name, Length, LastWriteTime
