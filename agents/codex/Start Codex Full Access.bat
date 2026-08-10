@echo off
setlocal EnableExtensions

rem Windows bridge for the Codex launcher in the active WSL Ubuntu environment.
rem Real launcher:
rem   /home/itsjimjimsalabim/bin/start-codex-full-access

set "WSL_EXE=%SystemRoot%\System32\wsl.exe"
set "WSL_HOME=/home/itsjimjimsalabim"
set "WSL_LAUNCHER=/home/itsjimjimsalabim/bin/start-codex-full-access"

if not exist "%WSL_EXE%" (
    echo ERROR: wsl.exe was not found at "%WSL_EXE%".
    echo This shortcut must be run from Windows with WSL installed.
    pause
    exit /b 1
)

call :DOCK_RIGHT
echo.
echo Starting Codex Full Access in the default WSL Ubuntu distro...
echo Launcher: %WSL_LAUNCHER%
echo.

"%WSL_EXE%" --cd "%WSL_HOME%" --exec "%WSL_LAUNCHER%" %*
if errorlevel 1 goto ON_ERROR
exit /b 0

:DOCK_RIGHT
if defined CODEX_NO_DOCK exit /b 0
powershell -NoProfile -ExecutionPolicy Bypass -Command "$sig='[DllImport(\"user32.dll\")]public static extern bool MoveWindow(IntPtr hWnd,int X,int Y,int nWidth,int nHeight,bool bRepaint);[DllImport(\"user32.dll\")]public static extern IntPtr GetForegroundWindow();'; Add-Type -Namespace Win32 -Name Native -MemberDefinition $sig; Add-Type -AssemblyName System.Windows.Forms; $wa=[System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea; $hwnd=[Win32.Native]::GetForegroundWindow(); if($hwnd -ne [IntPtr]::Zero){[Win32.Native]::MoveWindow($hwnd,[int]($wa.Left+$wa.Width/2),[int]$wa.Top,[int]($wa.Width/2),[int]($wa.Height),$true) | Out-Null}" >nul 2>nul
exit /b 0

:ON_ERROR
set "ERR=%ERRORLEVEL%"
echo.
echo ERROR: WSL Codex launcher failed. Code: %ERR%
echo.
echo Quick checks:
echo   wsl.exe -d Ubuntu --cd /home/itsjimjimsalabim
echo   /home/itsjimjimsalabim/bin/start-codex-full-access --self-test
echo.
echo Press any key to exit...
pause >nul
exit /b %ERR%
