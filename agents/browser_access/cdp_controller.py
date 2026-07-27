"""Control Chrome via Chrome DevTools Protocol (CDP) using HTTP endpoints."""
import json
import sys
import time
import urllib.request

CDP_BASE = "http://localhost:9222"

def cdp_get(path):
    """GET request to CDP HTTP endpoint."""
    url = f"{CDP_BASE}{path}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"CDP GET error: {e}")
        return None

def list_tabs():
    """List all open Chrome tabs."""
    tabs = cdp_get("/json/list")
    if tabs:
        for i, tab in enumerate(tabs):
            print(f"  [{i}] {tab.get('title', 'untitled')} - {tab.get('url', 'no url')}")
    return tabs

def new_tab(url="about:blank"):
    """Open a new tab with the given URL."""
    result = cdp_get(f"/json/new?{url}")
    return result

def navigate_tab(tab_id, url):
    """Navigate a tab to a URL via CDP HTTP endpoint."""
    # Use /json/protocol approach - need WebSocket for this
    # For now, open new tab
    return new_tab(url)

def take_screenshot_via_cdp():
    """Take screenshot - requires WebSocket, use cdp_screenshot.py instead."""
    print("Screenshot requires WebSocket connection. Use cdp_screenshot.py")
    return None

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "tabs"
    if cmd == "tabs":
        print("Open tabs:")
        list_tabs()
    elif cmd == "new":
        url = sys.argv[2] if len(sys.argv) > 2 else "https://www.youtube.com"
        print(f"Opening: {url}")
        new_tab(url)
        time.sleep(2)
        list_tabs()
    elif cmd == "version":
        info = cdp_get("/json/version")
        print(json.dumps(info, indent=2))
