param(
  [string]$Version = "0.1.0",
  [string]$IssPath = "midori-v0.1.0.iss"
)

$ErrorActionPreference = "Stop"

function Resolve-Iscc {
  $rawCandidates = @(
    $env:ISCC_PATH,
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
  )

  $candidates = $rawCandidates | Where-Object {
    $_ -and
    $_.ToString().ToLower().EndsWith(".exe") -and
    (Test-Path $_ -PathType Leaf)
  }

  if ($candidates) {
    return ($candidates | Select-Object -First 1)
  }

  $cmd = Get-Command iscc.exe -ErrorAction SilentlyContinue
  if ($cmd) {
    return $cmd.Source
  }

  throw "ISCC.exe not found. Install Inno Setup 6 or set ISCC_PATH."
}

function Assert-InstallerAssets {
  param(
    [string]$PngPath
  )

  if (!(Test-Path $PngPath -PathType Leaf)) {
    throw "Logo PNG not found: $PngPath"
  }

  Write-Host "Installer logo verified: $PngPath"
}

function New-TemporaryInstallerIcon {
  param(
    [string]$PngPath
  )

  Add-Type -AssemblyName System.Drawing

  $tempName = "midori-installer-$([guid]::NewGuid().ToString('N')).ico"
  $tempIconPath = Join-Path ([System.IO.Path]::GetTempPath()) $tempName

  $bitmap = [System.Drawing.Bitmap]::FromFile($PngPath)
  try {
    $icon = [System.Drawing.Icon]::FromHandle($bitmap.GetHicon())
    try {
      $stream = [System.IO.File]::Open($tempIconPath, [System.IO.FileMode]::Create)
      try {
        $icon.Save($stream)
      } finally {
        $stream.Dispose()
      }
    } finally {
      $icon.Dispose()
    }
  } finally {
    $bitmap.Dispose()
  }

  return $tempIconPath
}

function Build-VSCodeExtensionBundle {
  param(
    [string]$RepoRoot
  )

  $extDir = Join-Path $RepoRoot "vscode-extension"
  $pkgPath = Join-Path $extDir "package.json"
  if (!(Test-Path $pkgPath -PathType Leaf)) {
    throw "VS Code extension package.json not found: $pkgPath"
  }

  $pkg = Get-Content $pkgPath -Raw | ConvertFrom-Json
  $extVersion = [string]$pkg.version
  if ([string]::IsNullOrWhiteSpace($extVersion)) {
    throw "Unable to resolve VS Code extension version from: $pkgPath"
  }

  $distDir = Join-Path $extDir "dist"
  New-Item -ItemType Directory -Path $distDir -Force | Out-Null

  $vsixName = "midori-language-$extVersion.vsix"
  $vsixOut = Join-Path $distDir $vsixName

  Write-Host "Packaging VS Code extension: $vsixName"
  Push-Location $extDir
  try {
    $null = & npx @vscode/vsce package -o $vsixOut
    if ($LASTEXITCODE -ne 0) {
      throw "vsce package failed with exit code $LASTEXITCODE"
    }
  } finally {
    Pop-Location
  }
  Write-Host "VS Code extension bundle ready: $vsixOut"

  return $extVersion
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$issFull = Join-Path $scriptDir $IssPath
if (!(Test-Path $issFull)) {
  throw "Installer script not found: $issFull"
}

$logoPng = Join-Path $scriptDir "..\..\vscode-extension\assets\midori-logo.png"
Assert-InstallerAssets -PngPath $logoPng
$tempSetupIcon = New-TemporaryInstallerIcon -PngPath $logoPng

$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
$vsixVersion = Build-VSCodeExtensionBundle -RepoRoot $repoRoot

$iscc = Resolve-Iscc
Write-Host "Using ISCC: $iscc"
Write-Host "Building MIDORI installer version $Version"

try {
  & $iscc "/DMyAppVersion=$Version" "/DMyVsixVersion=$vsixVersion" "/DMySetupIconFile=$tempSetupIcon" $issFull
  if ($LASTEXITCODE -ne 0) {
    throw "ISCC failed with exit code $LASTEXITCODE"
  }
} finally {
  Remove-Item $tempSetupIcon -Force -ErrorAction SilentlyContinue
}

Write-Host "Installer build completed."
