$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path -Path $DesktopPath -ChildPath "Clean PC & Boost CPU.lnk"
$TargetScript = "C:\Users\itsji\ARBITR8DER\agents\CleanPC.ps1"

$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "powershell.exe"
$Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$TargetScript`""
$Shortcut.IconLocation = "shell32.dll,238"
$Shortcut.Description = "Run PC Cleanup and Telemetry Check as Admin"
$Shortcut.Save()

Write-Host "Created Desktop shortcut: $ShortcutPath"
