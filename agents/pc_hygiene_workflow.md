# PC Hygiene & Performance Optimization Workflow

## 1. Automated Cleanup Script & Desktop Launcher

We built a complete, interactive, self-elevating cleanup utility and placed it in your codebase and desktop.

- **PowerShell Engine:** [`CleanPC.ps1`](file:///mnt/c/Users/itsji/ARBITR8DER/agents/CleanPC.ps1)
- **Batch Admin Launcher:** [`CleanPC.cmd`](file:///mnt/c/Users/itsji/ARBITR8DER/agents/CleanPC.cmd)

---

## 2. How to Use

### Option A: Right-Click "Run as Administrator"
1. Right-click [`CleanPC.cmd`](file:///mnt/c/Users/itsji/ARBITR8DER/agents/CleanPC.cmd) (or your Desktop shortcut **Clean PC & Boost CPU**).
2. Select **Run as Administrator**.

### Option B: Double-Click (Auto-Elevate)
- If you simply double-click [`CleanPC.cmd`](file:///mnt/c/Users/itsji/ARBITR8DER/agents/CleanPC.cmd), it detects non-admin execution and automatically prompts Windows UAC to elevate to Administrator.

---

## 3. What the Utility Does Step-by-Step

1. **Self-Elevation Check:** Verifies Admin rights; prompts UAC if required.
2. **Process Execution & Real Status:**
   - Finds and force-terminates `WorkloadsSessionHost`, `AIXHost`, `ClickToDo`, `PhoneExperienceHost`, and `CrossDeviceService`.
   - Displays explicit **`[SUCCESS]`**, **`[CLEAN]`**, or actual PowerShell **`[ERROR]`** messages for each target without mocking.
3. **Policies & Defender Exclusion:**
   - Disables global background app auto-launching via Windows Registry.
   - Applies a Microsoft Defender Real-Time Exclusion for `C:\Users\itsji\ARBITR8DER` (drastically reducing CPU spikes during code execution and builds).
4. **Settling Countdown & Telemetry Polling:**
   - Waits 5 seconds for memory and system handles to settle.
   - Queries hardware telemetry (`CimInstance` / `WMI`) for live stats:
     - **CPU Usage %** (1-second sample)
     - **RAM Usage** (Used GB / Total GB and %)
     - **Disk C: Usage** (Used GB / Total GB and %)
