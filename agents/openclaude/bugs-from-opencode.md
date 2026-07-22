# Bugs Found in Claude/OpenClaude Code — Left by OpenCode

> Date: 2026-07-21
> Reporter: OpenCode (big-pickle)
> Purpose: These are issues found in Claude's configs and launchers during cleanup. OpenCode does not modify these files.

---

## 1. Hardcoded API Key in Launcher Scripts (SECURITY)

The same `OPENCODE_API_KEY` value appears in plaintext in three files:

- `agents/claude/launchers/openclaude.bat` (line 4)
- `agents/claude/launchers/launch-ubuntu.sh` (line 3)
- `OneDrive/Desktop/OpenCode_Ubuntu.bat` (line 8)

These files are NOT in `.gitignore`. If the repo is ever pushed, the key is exposed.

**Fix**: Load the key from `.env` at runtime instead of embedding it. The `.env` file IS gitignored.

---

## 2. Hardcoded API Key in Desktop Bat Files

`OneDrive/Desktop/OpenClaude_Ubuntu.bat` and `OneDrive/Desktop/OpenCode_Ubuntu.bat` both contain the raw API key in line 8. Same issue as above — desktop files outside the repo with embedded secrets.

**Fix**: Both bat files should reference `.env` or a shared secret store, not embed the key.

---

## 3. Junk Files at OpenClaude Repo Root

Four empty (0-byte) files exist at the root of `C:\Users\itsji\openclaude`:

- `binbash`
- `bincmd`
- `binclaude.batbat`
- `binPathC:Users<you...`

These are clearly failed script creation attempts (likely from a session that misclicked or mis-routed file writes). They serve no purpose.

**Fix**: Delete them.

---

## 4. Session History Files Are Duplicated

`agents/claude/session-history/opencode-fixes-and-learnings.md` is a near-duplicate of `agents/opencode/2026-07-17_fixes-and-learnings.md`. Same content, different location.

**Fix**: Keep the canonical copy in `agents/opencode/` (where the opencode agent reads from) and symlink or remove the Claude copy. Or keep both if Claude needs its own reference — but document which is canonical.
