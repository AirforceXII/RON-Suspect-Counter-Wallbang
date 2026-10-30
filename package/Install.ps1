param(
    [Parameter(Mandatory = $true)]
    [string]$ModsDirectory
)
$ErrorActionPreference = 'Stop'
$modsRoot = (Resolve-Path -LiteralPath $ModsDirectory).Path
if (-not (Test-Path -LiteralPath $modsRoot -PathType Container)) {
    throw 'ModsDirectory must be an existing UE4SS Mods folder.'
}
$source = Join-Path $PSScriptRoot 'Mods\ReactiveSuspects'
if (-not (Test-Path -LiteralPath (Join-Path $source 'Scripts\main.lua') -PathType Leaf)) {
    throw 'Package Scripts/main.lua is missing. Extract the full ZIP first.'
}
$destination = Join-Path $modsRoot 'ReactiveSuspects'
if (Test-Path -LiteralPath $destination) {
    $backupRoot = Join-Path (Split-Path -Parent $modsRoot) 'ReactiveSuspects-backups'
    New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
    $backup = Join-Path $backupRoot ('ReactiveSuspects-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
    Copy-Item -LiteralPath $destination -Destination $backup -Recurse
    Write-Host "Existing mod backed up to: $backup"
}
New-Item -ItemType Directory -Force -Path $destination | Out-Null
foreach ($item in Get-ChildItem -LiteralPath $source -Force) {
    Copy-Item -LiteralPath $item.FullName -Destination $destination -Recurse -Force
}
$version = (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'VERSION') -Raw).Trim()
Write-Host "Installed ReactiveSuspects $version into: $destination"
Write-Host 'If mods.txt explicitly disables ReactiveSuspects, change that entry to 1.'
Write-Host "Start the game as host and look for [ReactiveSuspects] READY $version in UE4SS.log."
