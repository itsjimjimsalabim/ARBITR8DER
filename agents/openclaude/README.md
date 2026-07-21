# OpenClaude CLI — Session Chat Pointers

> This directory contains only pointers to where OpenClaude CLI stores session
> chats. OpenCode should consolidate scattered files here during audit sweeps.

## Where Session Chats Live

### Active Sessions (JSONL)
```
~/.openclaude/projects/C--Users-itsji-openclaude/*.jsonl
```
Each file is a complete conversation session (user messages, assistant responses,
tool calls, summaries). File names are UUIDs.

### OpenClaude Config
```
~/.openclaude/settings.json          <- permissions, bypass settings
~/.openclaude/.openclaude-profile.json  <- provider/model profile
~/.openclaude/.config.json           <- app config
```

### Project Settings (per-workspace)
```
~/.openclaude/projects/C--Users-itsji-openclaude/settings.json
```

## Consolidated Copies (ARBITR8DER)

Session history from prior sessions has been preserved here:
```
agents/claude/session-history/opencode-session-notes.md
agents/claude/session-history/opencode-fixes-and-learnings.md
```

## How to Read a Session

Open any `.jsonl` file — each line is a JSON object representing a message,
tool call, or tool result. Grep for `"role":"assistant"` to find AI responses,
or `"type":"tool_result"` to find tool outputs.
