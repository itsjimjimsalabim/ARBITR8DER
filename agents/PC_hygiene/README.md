# PC Hygiene & Performance Optimization Framework

## Overview
A lightweight, self-elevating system cleanup tool designed for Windows 11 fresh resets and developer workstations. It purges parasitic background processes, developer workload session indexers, background telemetry, and local AI engines to reclaim CPU and RAM.

---

## Files Structure

- **`agents/PC_hygiene/CleanPC.ps1`**  
  The single, unified PowerShell script that handles UAC elevation, process termination, system policy enforcement, Defender exclusions, and live hardware telemetry.
- **`agents/PC_hygiene/README.md`**  
  This documentation file.
- **Desktop Shortcut:** `Clean PC & Boost CPU`  
  Located directly on your Desktop, configured to run `CleanPC.ps1` elevated.

---

## How to Run

### Method 1: Desktop Shortcut (Recommended)
Double-click **`Clean PC & Boost CPU`** on your Desktop.
- Automatically prompts Windows UAC for Administrator rights.
- Opens an interactive console that remains open after execution to display results.

### Method 2: Manual PowerShell Execution
Right-click PowerShell -> **Run as Administrator**, then execute:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\itsji\ARBITR8DER\agents\PC_hygiene\CleanPC.ps1"
```

---

## Target Catalog

| Target Category | Processes Terminated |
| :--- | :--- |
| **Developer Workloads** | `WorkloadsSessionHost` (Dev Drive & VS Session Indexer) |
| **Windows AI & Copilot** | `AIXHost`, `ClickToDo`, `Recall` |
| **Telemetry & Sync** | `PhoneExperienceHost`, `CrossDeviceService`, `CrossDeviceResume`, `AutoCatHost` |
| **UI Bloat & Web Feeds** | `SearchHost`, `Widgets`, `msedgewebview2` |
| **OEM Helpers** | `VirtualPet`, `AsusMouseAgent` |
| **Local AI Engines** | `ollama`, `ollama_llama_server`, `cowork-svc` |
| **Desktop User Apps** | `chrome`, `msedge`, `Claude`, `Teams`, `PowerAutomate`, `ONENOTEM` |

---

## System Optimizations Applied

1. **Background App Restrictions:** Sets `HKCU:\Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications` -> `GlobalUserDisabled = 1`.
2. **Defender Real-Time Exclusion:** Adds `C:\Users\itsji\ARBITR8DER` to Microsoft Defender exclusions to eliminate CPU thrashing during code builds and script runs.
3. **Telemetry Polling:** Pauses 5 seconds to allow Windows memory reclamation before taking live CPU, RAM, and Disk samples.
