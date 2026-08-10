$ErrorActionPreference = 'Stop'

$launcher = 'C:\Users\itsji\ARBITR8DER\agents\codex\Start Codex Full Access.bat'
$desktop = 'C:\Users\itsji\OneDrive\Desktop'
$shortcut = Join-Path $desktop 'Start Codex Full Access.lnk'
$workingDirectory = 'C:\Users\itsji\ARBITR8DER\agents'

if (-not (Test-Path -LiteralPath $launcher)) {
    throw "Launcher not found: $launcher"
}

if (-not (Test-Path -LiteralPath $desktop)) {
    New-Item -ItemType Directory -Path $desktop | Out-Null
}

if (Test-Path -LiteralPath $shortcut) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    Copy-Item -LiteralPath $shortcut -Destination "$shortcut.bak-$stamp" -Force
}

$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($shortcut)
$lnk.TargetPath = "$env:ComSpec"
$lnk.Arguments = "/k ""$launcher"""
$lnk.WorkingDirectory = $workingDirectory
$lnk.IconLocation = "$env:SystemRoot\System32\cmd.exe,0"
$lnk.Description = 'Start Codex in agents root with full local sandbox access'
$lnk.Save()

Write-Host "Created shortcut: $shortcut"
Write-Host "Target: $($lnk.TargetPath) $($lnk.Arguments)"
