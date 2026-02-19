param(
  [string]$Version = "0.1.0",
  [string]$IssPath = "midori-v0.1.0.iss"
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$target = Join-Path $scriptDir "build-installer.ps1"
& $target -Version $Version -IssPath $IssPath
