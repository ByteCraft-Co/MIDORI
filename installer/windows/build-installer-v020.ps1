param(
  [string]$Version = "0.2.0",
  [string]$IssPath = "midori-v0.2.0.iss"
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$target = Join-Path $scriptDir "build-installer-v0.2.0.ps1"
& $target -Version $Version -IssPath $IssPath
