# tests/test_launcher_scripts.ps1
# Verifies all launcher scripts and shortcuts point to valid targets.
# Run: pwsh -File tests/test_launcher_scripts.ps1

$ErrorActionPreference = "Stop"
$pass = 0
$fail = 0

function Test-FileExists {
    param([string]$Path, [string]$Label)
    if (Test-Path -LiteralPath $Path) {
        Write-Host "  PASS  $Label -> $Path" -ForegroundColor Green
        $script:pass++
    } else {
        Write-Host "  FAIL  $Label -> $Path (NOT FOUND)" -ForegroundColor Red
        $script:fail++
    }
}

function Test-CommandExists {
    param([string]$Command, [string]$Label)
    try {
        $null = Get-Command $Command -ErrorAction Stop
        Write-Host "  PASS  $Label ($Command found)" -ForegroundColor Green
        $script:pass++
    } catch {
        Write-Host "  FAIL  $Label ($Command not found)" -ForegroundColor Red
        $script:fail++
    }
}

Write-Host "`n=== Launcher Tests ===" -ForegroundColor Cyan

# --- Windows Binaries ---
Write-Host "`n[Windows Binaries]" -ForegroundColor Yellow
Test-FileExists "C:\Program Files\nodejs\node.exe" "Node.js"
Test-FileExists "C:\Users\itsji\.bun\bin\bun.exe" "Bun"
Test-FileExists "C:\Users\itsji\.openclaude\dist\cli.mjs" "OpenClaude dist/cli.mjs"
Test-FileExists "C:\Users\itsji\.bun\bin\opencode.exe" "OpenCode binary"
Test-CommandExists "git" "Git"
Test-CommandExists "python" "Python"

# --- WSL Binaries ---
Write-Host "`n[WSL Binaries]" -ForegroundColor Yellow
$wslChecks = @(
    @{ Label = "WSL claude script"; Path = "\\wsl$\Ubuntu\home\itsjimjimsalabim\bin\claude" },
    @{ Label = "WSL opencode binary"; Path = "\\wsl$\Ubuntu\home\itsjimjimsalabim\.opencode\bin\opencode" },
    @{ Label = "WSL .openclaude/.env"; Path = "\\wsl$\Ubuntu\home\itsjimjimsalabim\.bashrc" }
)
foreach ($check in $wslChecks) {
    Test-FileExists $check.Path $check.Label
}

# --- No stale bun claude ---
Write-Host "`n[Stale Binary Check]" -ForegroundColor Yellow
$staleBunClaude = "\\wsl$\Ubuntu\home\itsjimjimsalabim\.bun\bin\claude"
if (Test-Path -LiteralPath $staleBunClaude) {
    Write-Host "  FAIL  STALE ~/.bun/bin/claude EXISTS — will shadow ~/bin/claude!" -ForegroundColor Red
    Write-Host "         Fix: wsl bash -c 'rm ~/.bun/bin/claude'" -ForegroundColor Yellow
    $fail++
} else {
    Write-Host "  PASS  No stale ~/.bun/bin/claude" -ForegroundColor Green
    $pass++
}

# --- API Keys ---
Write-Host "`n[API Keys]" -ForegroundColor Yellow
$envFile = "C:\Users\itsji\.openclaude\.env"
if (Test-Path -LiteralPath $envFile) {
    $envContent = Get-Content $envFile -Raw
    if ($envContent -match "OPENCODE_API_KEY=sk-") {
        Write-Host "  PASS  .openclaude/.env has OPENCODE_API_KEY" -ForegroundColor Green
        $pass++
    } else {
        Write-Host "  FAIL  .openclaude/.env missing OPENCODE_API_KEY" -ForegroundColor Red
        $fail++
    }
    if ($envContent -match "OPENAI_MODEL=big-pickle") {
        Write-Host "  PASS  .openclaude/.env has OPENAI_MODEL=big-pickle" -ForegroundColor Green
        $pass++
    } else {
        Write-Host "  FAIL  .openclaude/.env missing OPENAI_MODEL" -ForegroundColor Red
        $fail++
    }
} else {
    Write-Host "  FAIL  .openclaude/.env not found" -ForegroundColor Red
    $fail++
}

# --- Desktop Shortcuts ---
Write-Host "`n[Desktop Shortcuts (OneDrive Desktop)]" -ForegroundColor Yellow
$desktop = "C:\Users\itsji\OneDrive\Desktop"
$expectedShortcuts = @(
    "Claude Windows.lnk",
    "OpenCode at Home.lnk",
    "OpenClaude_Ubuntu.bat",
    "OpenCode_Ubuntu.bat",
    "Start Codex Full Access.lnk",
    "ARBITR8DER - Shortcut.lnk",
    "agents - Shortcut.lnk"
)
foreach ($name in $expectedShortcuts) {
    Test-FileExists "$desktop\$name" $name
}

# --- Claude .bat Content ---
Write-Host "`n[Claude Windows .bat]" -ForegroundColor Yellow
$claudeBat = "C:\Users\itsji\bin\claude.bat"
if (Test-Path -LiteralPath $claudeBat) {
    $content = Get-Content $claudeBat -Raw
    $checks = @(
        @{ Pattern = "CLAUDE_CODE_OPENAI_FALLBACK_CONTEXT_WINDOW"; Label = "Fallback context 256K" },
        @{ Pattern = "CLAUDE_CODE_MAX_OUTPUT_TOKENS"; Label = "Max output tokens" },
        @{ Pattern = "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"; Label = "Autocompact override" },
        @{ Pattern = "OPENCLAUDE_AUTOCOMPACT_FAILURE_COOLDOWN_MS"; Label = "Cooldown" },
        @{ Pattern = "\.openclaude"; Label = "Env file path" }
    )
    foreach ($check in $checks) {
        if ($content -match $check.Pattern) {
            Write-Host "  PASS  $($check.Label)" -ForegroundColor Green
            $pass++
        } else {
            Write-Host "  FAIL  $($check.Label) not found in claude.bat" -ForegroundColor Red
            $fail++
        }
    }
} else {
    Write-Host "  FAIL  C:\Users\itsji\bin\claude.bat not found" -ForegroundColor Red
    $fail++
}

# --- WSL claude Script Content ---
Write-Host "`n[WSL claude Script]" -ForegroundColor Yellow
$wslClaude = "\\wsl$\Ubuntu\home\itsjimjimsalabim\bin\claude"
if (Test-Path -LiteralPath $wslClaude) {
    $content = Get-Content $wslClaude -Raw
    $checks = @(
        @{ Pattern = "\.openclaude/\.env"; Label = "Sources .openclaude/.env" },
        @{ Pattern = "CLAUDE_CODE_OPENAI_FALLBACK_CONTEXT_WINDOW"; Label = "Fallback context 256K" },
        @{ Pattern = "CLAUDE_CODE_MAX_OUTPUT_TOKENS"; Label = "Max output tokens" },
        @{ Pattern = "exec node.*cli\.mjs"; Label = "Runs node cli.mjs" }
    )
    foreach ($check in $checks) {
        if ($content -match $check.Pattern) {
            Write-Host "  PASS  $($check.Label)" -ForegroundColor Green
            $pass++
        } else {
            Write-Host "  FAIL  $($check.Label) not found in ~/bin/claude" -ForegroundColor Red
            $fail++
        }
    }
} else {
    Write-Host "  FAIL  ~/bin/claude not found" -ForegroundColor Red
    $fail++
}

# --- WSL Version Checks ---
Write-Host "`n[WSL Version Checks]" -ForegroundColor Yellow
$versionChecks = @(
    @{ Cmd = "wsl -e bash -ic 'claude --version' 2>&1"; Label = "claude --version (WSL)" },
    @{ Cmd = "wsl -e bash -ic 'opencode --version' 2>&1"; Label = "opencode --version (WSL)" }
)
foreach ($vc in $versionChecks) {
    $output = Invoke-Expression $vc.Cmd 2>&1
    $outputStr = $output -join "`n"
    if ($outputStr -match "\d+\.\d+") {
        Write-Host "  PASS  $($vc.Label) -> $($outputStr.Trim())" -ForegroundColor Green
        $pass++
    } else {
        Write-Host "  FAIL  $($vc.Label) -> $outputStr" -ForegroundColor Red
        $fail++
    }
}

# --- Summary ---
Write-Host "`n=== Results ===" -ForegroundColor Cyan
Write-Host "  Passed: $pass" -ForegroundColor Green
Write-Host "  Failed: $fail" -ForegroundColor $(if ($fail -gt 0) { "Red" } else { "Green" })
Write-Host ""
if ($fail -gt 0) { exit 1 }
