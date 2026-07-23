# Run this ONCE as Administrator to create symlinks for OpenCode session databases.
# Right-click PowerShell -> Run as Administrator, then:
#   cd C:\Users\itsji\ARBITR8DER
#   .\agents\opencode\session-history\setup-symlinks.ps1

$ErrorActionPreference = "Stop"
$sessionDir = "$PSScriptRoot"

$windowsDb = "C:\Users\itsji\.local\share\opencode\opencode.db"
$wslDb = "\\wsl.localhost\Ubuntu\home\itsjimjimsalabim\.local\share\opencode\opencode.db"

$targets = @{
    "opencode_windows.db" = $windowsDb
    "opencode_wsl.db"     = $wslDb
}

foreach ($name in $targets.Keys) {
    $link = Join-Path $sessionDir $name
    $target = $targets[$name]

    if (Test-Path $link) {
        Write-Host "[SKIP] $name already exists"
        continue
    }

    if (-not (Test-Path $target)) {
        Write-Host "[WARN] Source not found: $target — skipping $name"
        continue
    }

    New-Item -ItemType SymbolicLink -Path $link -Target $target | Out-Null
    Write-Host "[OK]   Created symlink: $name -> $target"
}

Write-Host "`nDone. Symlinks created. These are gitignored and will not be pushed to GitHub."
