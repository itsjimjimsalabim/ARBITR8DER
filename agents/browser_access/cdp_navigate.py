"""Full CDP controller: navigate, screenshot, extract content from Chrome."""
import asyncio
import base64
import json
import sys
import urllib.request
import websockets

CDP_BASE = "http://localhost:9222"
SCREENSHOT_DIR = r"C:\Users\itsji\ARBITR8DER\agents\browser_access\screenshots"

import os
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

def get_ws_url():
    """Get WebSocket debugger URL for the first tab."""
    with urllib.request.urlopen(f"{CDP_BASE}/json/list", timeout=5) as resp:
        tabs = json.loads(resp.read())
    for tab in tabs:
        if tab.get("webSocketDebuggerUrl"):
            return tab["webSocketDebuggerUrl"]
    return None

async def send_command(ws, method, params=None):
    """Send a CDP command and wait for result."""
    msg_id = int.from_bytes(os.urandom(4), "big") % 100000
    cmd = {"id": msg_id, "method": method}
    if params:
        cmd["params"] = params
    await ws.send(json.dumps(cmd))
    while True:
        resp = json.loads(await ws.recv())
        if resp.get("id") == msg_id:
            return resp.get("result", {})

async def navigate(url):
    """Navigate the active tab to a URL."""
    ws_url = get_ws_url()
    if not ws_url:
        print("No tabs found")
        return
    async with websockets.connect(ws_url) as ws:
        result = await send_command(ws, "Page.navigate", {"url": url})
        print(f"Navigated to: {url}")
        await asyncio.sleep(3)  # wait for page load
        return result

async def screenshot(filename="screenshot.png"):
    """Take a screenshot of the active tab."""
    ws_url = get_ws_url()
    if not ws_url:
        print("No tabs found")
        return
    async with websockets.connect(ws_url) as ws:
        result = await send_command(ws, "Page.captureScreenshot", {"format": "png"})
        img_data = base64.b64decode(result["data"])
        path = os.path.join(SCREENSHOT_DIR, filename)
        with open(path, "wb") as f:
            f.write(img_data)
        print(f"Screenshot saved: {path}")
        return path

async def get_page_text():
    """Extract visible text from the active tab."""
    ws_url = get_ws_url()
    if not ws_url:
        print("No tabs found")
        return
    async with websockets.connect(ws_url) as ws:
        # Get document root
        doc = await send_command(ws, "DOM.getDocument")
        root_id = doc["root"]["nodeId"]
        # Get outer HTML
        html_result = await send_command(ws, "DOM.getOuterHTML", {"nodeId": root_id})
        return html_result.get("outerHTML", "")

async def evaluate_js(expression):
    """Evaluate JavaScript in the active tab."""
    ws_url = get_ws_url()
    if not ws_url:
        print("No tabs found")
        return
    async with websockets.connect(ws_url) as ws:
        result = await send_command(ws, "Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
        })
        return result.get("result", {}).get("value")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "screenshot"
    if cmd == "navigate":
        url = sys.argv[2] if len(sys.argv) > 2 else "https://www.google.com"
        asyncio.run(navigate(url))
    elif cmd == "screenshot":
        fname = sys.argv[2] if len(sys.argv) > 2 else "screenshot.png"
        asyncio.run(screenshot(fname))
    elif cmd == "text":
        text = asyncio.run(get_page_text())
        print(text[:2000] if text else "No text")
    elif cmd == "js":
        expr = sys.argv[2] if len(sys.argv) > 2 else "document.title"
        result = asyncio.run(evaluate_js(expr))
        print(result)
    elif cmd == "tabs":
        with urllib.request.urlopen(f"{CDP_BASE}/json/list", timeout=5) as resp:
            tabs = json.loads(resp.read())
        for i, t in enumerate(tabs):
            print(f"  [{i}] {t.get('title','')} - {t.get('url','')}")
