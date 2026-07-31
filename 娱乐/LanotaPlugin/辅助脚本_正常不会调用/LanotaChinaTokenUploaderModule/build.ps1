param(
    [string]$Config = (Join-Path $PSScriptRoot 'config.local.conf'),
    [string]$Version = '1.2.0'
)

$ErrorActionPreference = 'Stop'
$sourceDir = Join-Path $PSScriptRoot 'src'
$moduleDir = Join-Path $PSScriptRoot 'module'
$buildDir = Join-Path $PSScriptRoot 'build'
$stageDir = Join-Path $buildDir 'module-stage'
$distDir = Join-Path $PSScriptRoot 'dist'
$zipPath = Join-Path $distDir "LanotaChinaTokenUploader-v$Version-configured.zip"
$apkDistPath = Join-Path $distDir "LanotaControl-v$Version.apk"
$appBuildScript = Join-Path $PSScriptRoot 'app\build-apk.ps1'

function Assert-NativeSuccess {
    param([string]$Step)
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE."
    }
}

if (-not (Test-Path -LiteralPath $Config)) {
    throw "Missing configured file: $Config"
}
$configText = [System.IO.File]::ReadAllText((Resolve-Path -LiteralPath $Config))
if ($configText.Contains('CHANGE_ME')) {
    throw 'The configured file still contains CHANGE_ME.'
}

New-Item -ItemType Directory -Force -Path $distDir | Out-Null
& $appBuildScript
if ($LASTEXITCODE -ne 0) {
    throw 'Control APK build failed.'
}
Copy-Item -Force -LiteralPath (Join-Path $PSScriptRoot 'app\LanotaControl.apk') -Destination $apkDistPath

Push-Location $sourceDir
try {
    go mod tidy
    Assert-NativeSuccess 'go mod tidy'
    go test ./...
    Assert-NativeSuccess 'go test'
} finally {
    Pop-Location
}

if (Test-Path -LiteralPath $buildDir) {
    Remove-Item -Recurse -Force -LiteralPath $buildDir
}
New-Item -ItemType Directory -Force -Path $stageDir, $distDir | Out-Null
Copy-Item -Recurse -Force -Path (Join-Path $moduleDir '*') -Destination $stageDir
New-Item -ItemType Directory -Force -Path (Join-Path $stageDir 'bin') | Out-Null
Remove-Item -Recurse -Force -LiteralPath (Join-Path $stageDir 'app') -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path (Join-Path $stageDir 'app') | Out-Null
Copy-Item -Force -LiteralPath (Join-Path $PSScriptRoot 'app\LanotaControl.apk') -Destination (Join-Path $stageDir 'app\LanotaControl.apk')
[System.IO.File]::WriteAllText(
    (Join-Path $stageDir 'config.conf'),
    $configText,
    [System.Text.UTF8Encoding]::new($false)
)

$originalGoOS = $env:GOOS
$originalGoArch = $env:GOARCH
$originalGoArm = $env:GOARM
$originalCgo = $env:CGO_ENABLED
Push-Location $sourceDir
try {
    # CGO-free Linux ELF binaries run directly on the Android Linux kernel.
    $env:GOOS = 'linux'
    $env:CGO_ENABLED = '0'

    $env:GOARCH = 'arm64'
    Remove-Item Env:GOARM -ErrorAction SilentlyContinue
    go build -trimpath -ldflags '-s -w' -o (Join-Path $stageDir 'bin\lanota-token-daemon-arm64') .
    Assert-NativeSuccess 'arm64 build'

    $env:GOARCH = 'arm'
    $env:GOARM = '7'
    go build -trimpath -ldflags '-s -w' -o (Join-Path $stageDir 'bin\lanota-token-daemon-arm') .
    Assert-NativeSuccess 'armv7 build'
} finally {
    Pop-Location
    $env:GOOS = $originalGoOS
    $env:GOARCH = $originalGoArch
    $env:GOARM = $originalGoArm
    $env:CGO_ENABLED = $originalCgo
}

if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -Force -LiteralPath $zipPath
}
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$stream = [System.IO.File]::Open($zipPath, [System.IO.FileMode]::CreateNew)
$archive = [System.IO.Compression.ZipArchive]::new(
    $stream,
    [System.IO.Compression.ZipArchiveMode]::Create,
    $false
)
try {
    $stageRoot = (Resolve-Path -LiteralPath $stageDir).Path
    Get-ChildItem -File -Recurse -LiteralPath $stageRoot | ForEach-Object {
        $relativePath = $_.FullName.Substring($stageRoot.Length).TrimStart('\', '/')
        $entryName = $relativePath.Replace('\', '/')
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive,
            $_.FullName,
            $entryName,
            [System.IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
    }
} finally {
    $archive.Dispose()
    $stream.Dispose()
}
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath).Hash.ToLowerInvariant()
Write-Host "Package: $zipPath"
Write-Host "SHA256: $hash"
