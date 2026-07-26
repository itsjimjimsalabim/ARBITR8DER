"""CDP keyboard and mouse input controller - types like a real user."""
import asyncio
import json
import os
import time
import urllib.request
import websockets

CDP_BASE = "http://localhost:9222"

def get_ws_url():
    with urllib.request.urlopen(f"{CDP_BASE}/json/list", timeout=5) as resp:
        tabs = json.loads(resp.read())
    for tab in tabs:
        if tab.get("webSocketDebuggerUrl") and "accounts.google" in tab.get("url", ""):
            return tab["webSocketDebuggerUrl"]
    for tab in tabs:
        if tab.get("webSocketDebuggerUrl"):
            return tab["webSocketDebuggerUrl"]
    return None

async def send_command(ws, method, params=None):
    msg_id = int.from_bytes(os.urandom(4), "big") % 100000
    cmd = {"id": msg_id, "method": method}
    if params:
        cmd["params"] = params
    await ws.send(json.dumps(cmd))
    while True:
        resp = json.loads(await ws.recv())
        if resp.get("id") == msg_id:
            return resp.get("result", {})

async def type_text(ws, text):
    """Type text character by character using CDP Input."""
    for char in text:
        await send_command(ws, "Input.dispatchKeyEvent", {
            "type": "keyDown",
            "text": char,
            "key": char,
            "code": f"Key{char.upper()}" if char.isalpha() else "",
            "windowsVirtualKeyCode": ord(char.upper()) if char.isalpha() else 0,
        })
        await send_command(ws, "Input.dispatchKeyEvent", {
            "type": "keyUp",
            "key": char,
            "code": f"Key{char.upper()}" if char.isalpha() else "",
            "windowsVirtualKeyCode": ord(char.upper()) if char.isalpha() else 0,
        })
        await asyncio.sleep(0.03)

async def press_key(ws, key, code=None):
    """Press a special key (Enter, Tab, etc.)."""
    await send_command(ws, "Input.dispatchKeyEvent", {
        "type": "keyDown",
        "key": key,
        "code": code or key,
        "windowsVirtualKeyCode": 13 if key == "Enter" else 9 if key == "Tab" else 0,
    })
    await send_command(ws, "Input.dispatchKeyEvent", {
        "type": "keyUp",
        "key": key,
        "code": code or key,
        "windowsVirtualKeyCode": 13 if key == "Enter" else 9 if key == "Tab" else 0,
    })

async def click_element(ws, selector):
    """Click an element by finding its coordinates via JS."""
    js = f"""
    (() => {{
        const el = document.querySelector('{selector}');
        if (!el) return null;
        const rect = el.getBoundingClientRect();
        return {{x: rect.x + rect.width/2, y: rect.y + rect.height/2}};
    }})()
    """
    result = await send_command(ws, "Runtime.evaluate", {
        "expression": js,
        "returnByValue": True,
    })
    coords = result.get("result", {}).get("value")
    if coords:
        await send_command(ws, "Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": coords["x"],
            "y": coords["y"],
            "button": "left",
            "clickCount": 1,
        })
        await send_command(ws, "Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": coords["x"],
            "y": coords["y"],
            "button": "left",
            "clickCount": 1,
        })
        print(f"Clicked at ({coords['x']}, {coords['y']})")
        return True
    print(f"Element not found: {selector}")
    return False

async def google_login(email, password):
    """Login to Google account step by step."""
    ws_url = get_ws_url()
    if not ws_url:
        print("No suitable tab found")
        return

    async with websockets.connect(ws_url) as ws:
        # Make sure page is ready
        await asyncio.sleep(1)

        # Step 1: Type email
        print("Typing email...")
        await type_text(ws, email)
        await asyncio.sleep(0.5)

        # Step 2: Press Enter to submit email
        print("Pressing Enter...")
        await press_key(ws, "Enter", "Enter")
        await asyncio.sleep(4)

        # Step 3: Check if we're on password page
        title_result = await send_command(ws, "Runtime.evaluate", {
            "expression": "document.title",
            "returnByValue": True,
        })
        title = title_result.get("result", {}).get("value", "")
        print(f"Page title after email: {title}")

        # Step 4: Type password
        print("Typing password...")
        await type_text(ws, password)
        await asyncio.sleep(0.5)

        # Step 5: Press Enter to submit password
        print("Pressing Enter...")
        await press_key(ws, "Enter", "Enter")
        await asyncio.sleep(5)

        # Check final state
        title_result = await send_command(ws, "Runtime.evaluate", {
            "expression": "document.title",
            "returnByValue": True,
        })
        title = title_result.get("result", {}).get("value", "")
        print(f"Page title after login: {title}")

if __name__ == "__main__":
    import sys
    email = sys.argv[1] if len(sys.argv) > 1 else ""
    password = sys.argv[2] if len(sys.argv) > 2 else ""
    if email and password:
        asyncio.run(google_login(email, password))
    else:
        print("Usage: python cdp_input.py <email> <password>")
