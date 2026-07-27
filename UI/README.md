# ARBITR8DER UI — Living README

> **PaulieStudios** · Independent UI Codebase · `C:\Users\itsji\ARBITR8DER\UI\`
> Last updated: 2026-07-11

---

## 📁 File Structure

```
UI/
├── index.html                  ← Minimal HTML entrypoint (edit regions here)
├── start.bat                   ← Desktop shortcut launcher
├── package.json                ← npm scripts (dev, typecheck, build, snapshot)
├── tsconfig.json               ← TypeScript config (strict, ES2022, DOM)
├── README.md                   ← This file (living doc)
│
├── src/
│   ├── main.ts                 ← App bootstrap (source of truth)
│   ├── main.js                 ← Compiled — regenerate via: npx tsc
│   ├── logger.ts               ← Structured logger (source of truth)
│   ├── logger.js               ← Compiled — regenerate via: npx tsc
│   └── styles/
│       ├── reset.css           ← Minimal CSS reset
│       ├── tokens.css          ← ALL design tokens (spacing, font, layout dims)
│       ├── themes.css          ← dark-modern + dark-neon (colors, glows, bezel)
│       └── layout.css          ← All region sizing and positioning (no colors)
│
└── tests/
    ├── layout.test.ts          ← Layout + theme test suite (source of truth)
    └── runner.html             ← Browser test runner page
```

---

## 🚀 How to Start

### Option A — Desktop Shortcut
1. Right-click `start.bat` → Send To → Desktop (Create Shortcut)
2. Double-click the Desktop shortcut
3. Browser opens automatically at `http://localhost:3000`

### Option B — Terminal
```powershell
cd C:\Users\itsji\ARBITR8DER\UI
npx serve . --listen 3000
# Then open: http://localhost:3000
```

---

## 🎨 Themes

| Theme | Key | Description |
|---|---|---|
| **Dark Modern** | `dark-modern` | Matte dark metal, subdued palette, zero glow |
| **Dark Neon** | `dark-neon` | Full multi-layer glow: borders, text, HUD windows |

**Toggle**: One switch in the Left Header. Persisted in `localStorage` key `arb8_ui_theme`.

**To add/change a theme value**: Edit `src/styles/tokens.css` (dimensions) or `src/styles/themes.css` (colors + glows).

**Never add a light mode.** Both themes are dark. That is a design requirement.

---

## 🗺️ Layout Regions Map

```
╔══════════════════════════════════════════════════════════════════╗
║ [header-left HUD]    [header-center brand]    [header-right HUD] ║
╠══════════╦══════════════════════════════════════╦════════════════╣
║          ║       [nav-bar]                      ║                ║
║ sidebar  ╠══════════════════════════════════════╣   inspector    ║
║  -left   ║                                      ║    -panel      ║
║          ║       [main-region]                  ║                ║
╠══════════╩══════════════════════════════════════╩════════════════╣
║ [footer-left  (wide)]                        [footer-right]      ║
╚══════════════════════════════════════════════════════════════════╝
```

| Region ID | HTML Element | Role | Notes |
|---|---|---|---|
| `header-left` | `<div>` | HUD Window | Holds theme toggle |
| `header-center` | `<div>` | Brand | Art deco, borderless. PaulieStudios / ARBITR8DER |
| `header-right` | `<div>` | HUD Window | Reserved |
| `sidebar-left` | `<aside>` | Left Sidebar | Blank — future nav/controls |
| `nav-bar` | `<nav>` | Navigation | Below center header, above main |
| `main-region` | `<main>` | Main Content | Primary data display area |
| `inspector-panel` | `<aside>` | Inspector | Same width as footer-right |
| `footer-left` | `<div>` | Wide Footer | Most of the footer width |
| `footer-right` | `<div>` | Narrow Footer | Matches inspector-panel width |

**Gap**: `8px` uniform between all regions and viewport edge (from `--gap` token).

---

## 🔧 Developer Reference

### Changing Layout Dimensions
All in `src/styles/tokens.css`:
```css
--gap:              20px;   /* uniform gap between all regions & viewport */
--header-height:    110px;
--nav-height:       75px;
--footer-height:    160px;
--sidebar-width:    320px;
--inspector-width:  var(--sidebar-width); /* symmetrical sidebars */
--bezel-gap:        4px;    /* space between outer and inner HUD border */
```

### Region Consistency & Backgrounds
To maintain absolute consistency:
- Only `#header-left` and `#header-right` use the `hud-window` styling (with background gradients and phosphor scanline overlays).
- `#inspector-panel`, `#footer-left`, and `#footer-right` use standard `.panel` styling, ensuring they share the exact same background colors, gradients, and bezel details as `#sidebar-left` and `#main-region`.
- `#nav-bar` inherits the standard `.panel` background gradient to remain consistent, but has custom rules to remain borderless.
- Symmetrical layout: `#sidebar-left` and `#inspector-panel` share the exact same width (`320px`), framing the center workspace.
- The right bottom bar (`#footer-right`) is aligned in width with the top-right header (`#header-right`) occupying exactly 1/3 of the viewport width, while `#footer-left` occupies 2/3 of the viewport width.

### HUD Bezel Border System
All `.hud-window` elements use a **double-border bezel** (no clip-path, no corner cuts):
- **Outer border** — on the element itself, uses `--color-border-hud-outer`
- **Bezel gap** — `--bezel-gap` (4px) of space
- **Inner border** — `::before` pseudo-element, uses `--color-border-hud-inner`

To adjust the bezel: change `--bezel-gap` in `tokens.css`.
To change border brightness: edit `--color-border-hud-outer` / `--color-border-hud-inner` in each theme block in `themes.css`.

### Theme Custom Properties Pattern
```
[data-theme="dark-modern"] { --color-bg-panel: hsl(...); }
[data-theme="dark-neon"]   { --color-bg-panel: hsl(...); }
```
All color variables are consumed in `themes.css` and applied to classes/IDs. Never put `hsl()` values in `layout.css`.

### Compiled JS
`src/main.js` and `src/logger.js` are hand-maintained compiled versions.
When you edit the `.ts` source, regenerate with:
```powershell
npx tsc
```
Or install TypeScript globally: `npm install -g typescript` then `tsc`.

### Debug Namespace (DevTools)
After page load, open browser DevTools console and inspect:
```js
window.__ARBITR8DER_UI__
// → { version, theme, log }

window.__ARBITR8DER_UI__.log.getLog()
// → Array of all log entries since page load

window.__ARBITR8DER_UI__.theme.current
// → 'dark-modern' | 'dark-neon'

window.__ARBITR8DER_UI__.theme.toggle()
// → Programmatically toggle theme
```

### Running Tests
1. Start the dev server (`start.bat` or `npx serve . --listen 3000`)
2. Open `http://localhost:3000` (tests auto-run on page load via `window.load`)
3. Open DevTools → Console — look for the `ARBITR8DER UI — Layout Tests` group
4. Results also at: `window.__ARBITR8DER_UI__.testResults`

### Taking a Snapshot
The snapshot tool takes a real headless browser screenshot and saves `UI_SNAPSHOT.png`.
Any AI can read `UI_SNAPSHOT.png` to see the current visual state without running the server.

```powershell
# Start server first (if not running)
npx serve . --listen 3000

# Then in a second terminal:
node snapshot.js              # dark-modern theme
node snapshot.js --neon       # dark-neon theme (more visually distinctive)
node snapshot.js --both       # saves both, latest = neon

# Or use npm scripts:
npm run snapshot
npm run snapshot:neon
npm run snapshot:both

# Or just double-click:
# snapshot.bat (auto-installs puppeteer on first run)
```

> **First run**: `snapshot.bat` installs puppeteer (downloads ~170MB Chromium). One time only.

---

## 📋 To Do

- [ ] Independent codebase in `UI\` — no dependency on trading studio or agents
- [ ] `index.html` — minimal HTML entrypoint, all regions defined with semantic roles
- [ ] `src/styles/reset.css` — clean CSS reset
- [ ] `src/styles/tokens.css` — all design tokens (typography, spacing, layout dims)
- [ ] `src/styles/themes.css` — `dark-modern` + `dark-neon` with solid bezel border system
- [ ] `src/styles/layout.css` — all 9 regions laid out, no color values
- [ ] `src/logger.ts` / `src/logger.js` — structured logger, rolling buffer, `getLog()`
- [ ] `src/main.ts` / `src/main.js` — bootstrap, region validation, theme, debug namespace
- [ ] Theme toggle in left header — one switch, two modes, localStorage persistence
- [ ] HUD bezel borders — outer border + 4px gap + inner border (no clip-path, no corner cuts)
- [ ] Art deco center header — `PaulieStudios` / `ARBITR8DER` branding, no border
- [ ] Header rows: 110px tall (up from 64px)
- [ ] Footer rows: 130px tall (up from 80px)
- [ ] `start.bat` — desktop shortcut launcher, opens browser, no trading-studio coupling
- [ ] `snapshot/snapshot.js` — puppeteer screenshot → `UI_SNAPSHOT.png` (any AI can read this)
- [ ] `snapshot/snapshot.bat` — auto-installs puppeteer, runs snapshot
- [ ] `tests/layout.test.ts` — 13 tests: regions, dimensions, overflow, theme, perf
- [ ] `tests/runner.html` — browser test runner
- [ ] `package.json` + `tsconfig.json` — project config
- [ ] `README.md` — this file


### Phase 1 — Regions & Polish (current phase)
- [ ] Add `?test=1` query param support in `main.js` to auto-import and run tests inline
- [ ] Add subtle breathing/pulse animation to neon HUD borders in dark-neon theme
- [ ] Verify layout renders correctly at `1920×1080`, `2560×1440`, and `3840×2160`
- [ ] Responsive: decide what happens below 1440px wide (current breakpoint is 1024px)

loop and Focus on phase 1, no not proceed with any further phases

### Phase 2 — Navigation
- [ ] Populate nav-bar with tab/view system (no routing library — vanilla JS only)
- [ ] Define what views/tabs exist inside the main-region

### Phase 3 — Components (future)
- [ ] Add components into regions (data grids, status indicators, charts)
- [ ] All components must pull from real ARBITR8DER data — no mock data ever
- [ ] Wire logger to capture component-level events

### Phase 4 — Data Bridge (future, separate concern)
- [ ] Define a clean API interface between UI and ARBITR8DER backend
- [ ] Use `EventSource` or `WebSocket` for live data — decide which
- [ ] UI must be read-only from the data bridge — never write to trading engine from UI directly

---

## ❓ Open Questions (for user to answer)

> These decisions are deferred until user provides input. Nothing should be built that depends on these until they are resolved.

1. **Inspector Panel content**: What is the "never-ending goal" text that should appear in `#inspector-panel`? Static text or dynamic?
2. **Nav bar tabs**: What views will live in the main region? (e.g., Portfolio, Orders, Charts, Logs, Settings)
3. **Left sidebar purpose**: What goes in `#sidebar-left`? Watchlist? Symbol tree? Strategy list?
4. **Data bridge protocol**: Will the UI pull data via REST polling, WebSocket, or EventSource (SSE)?
5. **Port preference**: Is `3000` ok, or does the trading studio already use that port?
6. **Font approval**: Outfit + Rajdhani + Share Tech Mono — approved, or different choices?
7. **HUD corner size**: Currently `10px` diagonal cut on all HUD windows — bigger/smaller/remove?
8. **Footer functions**: What functions will live in the two footer bars?
9. **Favicon**: Should we create one? If so, what icon/symbol?
10. **Resolution target**: Primary display resolution for dev/QA?

---

## 🐛 Debug Handbook — For AI Agents

> Read this section if you are an AI being asked to debug, extend, or QA this UI.

### First Steps
1. Read `UI-README.txt` — original design requirements
2. Read this `README.md` top to bottom
3. Start the dev server and load `http://localhost:3000` in a browser
4. Open DevTools → Console — the bootstrap log will show all regions validated
5. Run `window.__ARBITR8DER_UI__.log.getLog()` to see full log history

### Architecture Rules (do not violate)
- **No color in `layout.css`** — colors belong in `themes.css` only
- **No dimensions in `themes.css`** — dimensions belong in `tokens.css` and `layout.css` only
- **No mock data anywhere** — the UI renders empty regions until real data is wired
- **No light mode** — `data-theme` may only be `dark-modern` or `dark-neon`
- **No external CSS frameworks** — vanilla CSS only (no Tailwind, no Bootstrap)
- **No bundler in dev** — files load directly as ES modules via `npx serve`
- **Logger is the source of truth for runtime state** — use `Logger.getLog()` before assuming anything

### Common Issues & Fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| Blank page | Missing `src/main.js` or `src/logger.js` | Run `npx tsc` or check those files exist |
| Theme not applying | `data-theme` attribute missing on `<html>` | Check `ThemeManager.init()` ran — look in console log |
| Toggle doesn't switch | `#theme-toggle` element missing | Check `index.html` has the toggle `<input>` |
| Region missing from DOM | HTML region deleted or ID changed | Restore in `index.html`, check `REQUIRED_REGIONS` in `main.js` |
| Glow not showing | In wrong theme | Toggle to `dark-neon` — glows are zero in `dark-modern` by design |
| Layout overflow | A region has `min-width` larger than viewport | Check `layout.css`, ensure flex children have `min-width: 0` |
| Fonts not loading | No internet connection | Google Fonts CDN — fallback to `system-ui` is already set |
| CORS error on module import | Opened `index.html` as `file://` | Must be served via `npx serve` or `start.bat` |

### Adding a New Region
1. Add HTML element with a unique `id` in `index.html`
2. Add layout rules in `src/styles/layout.css` (dimensions only)
3. Add theme-driven colors in `src/styles/themes.css` (for both themes)
4. Add the `id` to `REQUIRED_REGIONS` in `src/main.ts` AND `src/main.js`
5. Add an existence test in `tests/layout.test.ts`
6. Update the Region Map table in this README

### Adding a New Theme Variable
1. Add the variable to `:root` in `tokens.css` with a fallback value
2. Override it in both `[data-theme="dark-modern"]` and `[data-theme="dark-neon"]` blocks in `themes.css`
3. Use the variable in a CSS rule — never hardcode `hsl()` values in components

### Log Level Guide
| Level | When to use |
|---|---|
| `DEBUG` | Granular internal state, only useful during active development |
| `INFO` | Meaningful state changes: theme switched, module initialized |
| `WARN` | Something unexpected but recoverable: element not found, fallback used |
| `ERROR` | Something broken that affects user-visible functionality |

### Performance Budget
- Page load target: **< 1 second** on localhost
- JS execution on boot: **< 10ms** (no heavy computation on startup)
- Theme transition: **360ms CSS animation** (deliberate, do not reduce below 200ms)
- No `setInterval` or polling loops — all future data connections via push (WebSocket/SSE)

---

## 📐 Design Constraints (Non-negotiable)

These are locked requirements from `UI-README.txt`:

1. All UI files live in `C:\Users\itsji\ARBITR8DER\UI\` — no external dependencies on the trading studio
2. HTML entrypoint is minimal — structure only
3. CSS, TypeScript, minimal HTML
4. **No mock data — ever**
5. Equal spacing (gap) between all regions and viewport edge
6. Three equal-width header bars
7. Left and right headers: bordered HUD windows (holographic)
8. Center header: borderless, art deco — `PaulieStudios` above `ARBITR8DER`
9. Two footer bars, taller than usual — left wide, right = inspector width
10. One toggle switch — dark-modern ↔ dark-neon — no light mode

---

*This README is the single source of truth for this codebase. Update it whenever a significant change is made.*
