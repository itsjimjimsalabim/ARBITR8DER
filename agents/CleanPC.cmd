@echo off
:: Self-elevate script to Administrator if not already elevated
net session >nul 2>&1
if %errorLevel% neq 0 (
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:: Run the CleanPC PowerShell script
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\itsji\ARBITR8DER\agents\CleanPC.ps1"
