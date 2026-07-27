"""Launch Chrome with remote debugging enabled for Playwright/CDP control."""
import subprocess
import time
import json
import urllib.request

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DEBUG_PORT = 9222
USER_DATA_DIR = r"C:\Users\itsji\chrome-debug-profile"

def launch_chrome():
    """Launch Chrome with remote debugging on all interfaces."""
    cmd = [
        CHROME_PATH,
        f"--remote-debugging-port={DEBUG_PORT}",
        "--remote-debugging-address=0.0.0.0",
        f"--user-data-dir={USER_DATA_DIR}",
        "--no-first-run",
    ]
    proc = subprocess.Popen(cmd)
    time.sleep(3)
    return proc

def check_cdp():
    """Check if CDP endpoint is reachable."""
    url = f"http://localhost:{DEBUG_PORT}/json/version"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
            print(f"CDP OK: {data.get('Browser', 'unknown')}")
            print(f"WebSocket: {data.get('webSocketDebuggerUrl', 'N/A')}")
            return True
    except Exception as e:
        print(f"CDP not reachable: {e}")
        return False

if __name__ == "__main__":
    if not check_cdp():
        print("Launching Chrome...")
        launch_chrome()
        time.sleep(3)
        check_cdp()
