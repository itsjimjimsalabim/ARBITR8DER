@echo off
title OpenCode - Big Pickle
cd /d C:\Users\itsji\ARBITR8DER
wsl bash /mnt/c/Users/itsji/ARBITR8DER/agents/openclaude/launchers/launch-opencode.sh %*
if %ERRORLEVEL% neq 0 (
    echo.
    echo [OpenCode] Exited with error code %ERRORLEVEL%
    echo.
    pause
)
