param(
  [string]$Version = "0.2.1",
  [string]$IssPath = "midori-v0.2.1.iss"
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$target = Join-Path $scriptDir "build-installer.ps1"
& $target -Version $Version -IssPath $IssPath