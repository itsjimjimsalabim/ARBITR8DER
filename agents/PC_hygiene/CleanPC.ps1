# Requires -RunAsAdministrator
[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"

# Check elevation. If not elevated, auto-launch an elevated window with -NoExit and exit background process.
$isElevated = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isElevated) {
    Start-Process powershell.exe -ArgumentList "-NoExit -NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

Clear-Host
Write-Host "===================================================================" -ForegroundColor Red
Write-Host "          ARBITR8DER DEEP SYSTEM CLEANUP & HARD RESET              " -ForegroundColor Red
Write-Host "===================================================================" -ForegroundColor Red
Write-Host ""

$targets = @(
    # Developer & System Bloat
    @{ Name = "WorkloadsSessionHost"; Category = "Dev Workloads / Dev Drive Indexer" },
    @{ Name = "AIXHost";              Category = "Windows AI / Copilot Background Host" },
    @{ Name = "ClickToDo";            Category = "Windows Copilot Click To Do Action Host" },
    @{ Name = "PhoneExperienceHost";  Category = "Windows Phone Link Sync Host" },
    @{ Name = "CrossDeviceService";   Category = "Windows Cross-Device / Hand off Host" },
    @{ Name = "CrossDeviceResume";    Category = "Windows Cross-Device Resume Host" },
    @{ Name = "AutoCatHost";          Category = "Windows Auto Categorization Host" },
    @{ Name = "SearchHost";           Category = "Windows Search Indexer UI" },
    @{ Name = "Widgets";              Category = "Windows Widgets & Web Feeds" },
    @{ Name = "msedgewebview2";       Category = "Edge WebView2 Background Instances" },
    @{ Name = "VirtualPet";           Category = "OEM / Asus Telemetry Bloatware" },
    @{ Name = "AsusMouseAgent";       Category = "OEM Helper Agent" },

    # Heavy Local AI Engines & Background Services
    @{ Name = "ollama";               Category = "Ollama Local LLM Engine" },
    @{ Name = "ollama_llama_server";  Category = "Ollama Model Runner Instance" },
    @{ Name = "cowork-svc";           Category = "Cowork Background Service" },

    # User Applications & Browsers (Complete Desktop Flush)
    @{ Name = "chrome";               Category = "Google Chrome Browser" },
    @{ Name = "msedge";               Category = "Microsoft Edge Browser" },
    @{ Name = "Claude";               Category = "Claude Desktop App" },
    @{ Name = "Teams";                Category = "Microsoft Teams" },
    @{ Name = "PowerAutomate";        Category = "Power Automate Desktop" },
    @{ Name = "ONENOTEM";             Category = "OneNote Quick Launcher" }
)

Write-Host "[1/3] Terminating user applications, local AI models, and background bloat..." -ForegroundColor Yellow
Write-Host ""

$killedCount   = 0
$cleanCount    = 0
$errorCount    = 0
$freedMemBytes = 0

foreach ($item in $targets) {
    $procName = $item.Name
    $cat      = $item.Category
    
    $procs = Get-Process -Name $procName -ErrorAction SilentlyContinue

    if ($procs) {
        $count = $procs.Count
        $sumBytes = 0
        foreach ($p in $procs) { $sumBytes += $p.WorkingSet64 }
        $freedMemBytes += $sumBytes
        $memMB = [math]::Round($sumBytes / 1MB, 1)

        Write-Host "  [RUNNING] $procName ($count instance(s), $memMB MB) -> Terminating..." -NoNewline
        try {
            $procs | Stop-Process -Force -ErrorAction Stop
            Write-Host " [KILLED]" -ForegroundColor Green
            $killedCount++
        } catch {
            Write-Host " [FAILED: $_]" -ForegroundColor Red
            $errorCount++
        }
    } else {
        Write-Host "  [CLEAN]   $procName ($cat) -> Not running." -ForegroundColor Gray
        $cleanCount++
    }
}

$freedMemMB = [math]::Round($freedMemBytes / 1MB, 1)

Write-Host ""
Write-Host "-------------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "Cleanup Summary: $killedCount Killed | $cleanCount Already Clean | $errorCount Errors | ~$freedMemMB MB Reclaimed" -ForegroundColor Cyan
Write-Host "-------------------------------------------------------------------" -ForegroundColor DarkGray

Write-Host ""
Write-Host "[2/3] Enforcing system policies & dev exclusions..." -ForegroundColor Yellow

try {
    Write-Host "  -> Disabling global background app access..." -NoNewline
    Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications" -Name "GlobalUserDisabled" -Value 1 -ErrorAction Stop
    Write-Host " [SUCCESS]" -ForegroundColor Green
} catch {
    Write-Host " [NOTICE: $_]" -ForegroundColor Gray
}

try {
    Write-Host "  -> Verifying Defender exclusion for C:\Users\itsji\ARBITR8DER..." -NoNewline
    Add-MpPreference -ExclusionPath "C:\Users\itsji\ARBITR8DER" -ErrorAction Stop
    Write-Host " [SUCCESS]" -ForegroundColor Green
} catch {
    Write-Host " [ACTIVE/ALREADY EXCLUDED]" -ForegroundColor Gray
}

Write-Host ""
Write-Host "[3/3] Stabilizing memory & measuring telemetry..." -ForegroundColor Yellow
for ($i = 5; $i -gt 0; $i--) {
    Write-Host "  -> Sampling hardware stats in $i s...   `r" -NoNewline
    Start-Sleep -Seconds 1
}
Write-Host "  -> Hardware sampling completed.            " -ForegroundColor Gray

Write-Host ""
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host "                   LIVE POST-CLEANUP TELEMETRY                     " -ForegroundColor Cyan
Write-Host "===================================================================" -ForegroundColor Cyan

try {
    $cpuObj = Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average
    $cpu = if ($cpuObj.Average) { [math]::Round($cpuObj.Average, 1) } else { 0 }

    $os = Get-CimInstance Win32_OperatingSystem
    $totalRamGB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
    $freeRamGB  = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
    $usedRamGB  = [math]::Round($totalRamGB - $freeRamGB, 2)
    $ramPercent = [math]::Round(($usedRamGB / $totalRamGB) * 100, 1)

    $disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
    $totalDiskGB = [math]::Round($disk.Size / 1GB, 2)
    $freeDiskGB  = [math]::Round($disk.FreeSpace / 1GB, 2)
    $usedDiskGB  = [math]::Round($totalDiskGB - $freeDiskGB, 2)
    $diskPercent = [math]::Round(($usedDiskGB / $totalDiskGB) * 100, 1)

    Write-Host " CPU Usage:       $cpu%" -ForegroundColor $(if($cpu -gt 50){"Red"}else{"Green"})
    Write-Host " Memory (RAM):    $usedRamGB GB / $totalRamGB GB used ($ramPercent%)" -ForegroundColor $(if($ramPercent -gt 70){"Yellow"}else{"Green"})
    Write-Host " Disk (C:):       $usedDiskGB GB / $totalDiskGB GB used ($diskPercent%)" -ForegroundColor Green
} catch {
    Write-Host "Telemetry error: $_" -ForegroundColor Red
}

Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press any key to exit..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
