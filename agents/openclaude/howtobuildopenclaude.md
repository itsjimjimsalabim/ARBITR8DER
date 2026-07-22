# How to Build OpenClaude From Scratch

This guide is for rebuilding and customizing OpenClaude if you only have the markdown files (AGENTS.md, CONTRIBUTING.md, this file, etc.) and need to reconstruct the project from the ground up.

## What OpenClaude Actually Is

OpenClaude is a **coding-agent CLI** — a terminal-based tool that lets you talk to LLMs (OpenAI, Anthropic, Gemini, DeepSeek, Ollama, etc.) and have them write code, run commands, and edit files on your behalf. It's built with:

- **TypeScript** (strict mode, ESM imports)
- **React + Ink** (terminal UI framework — renders React components in the terminal)
- **Bun** (development runtime, package manager, bundler)
- **Node.js >=22** (production runtime — the built CLI runs on Node)

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Node.js | >=22.0.0 | Runtime for the built CLI |
| Bun | >=1.0 | Dev builds, scripts, tests, dependency management |
| Git | any recent | Source control |

### Installing Bun (if you don't have it)

```bash
curl -fsSL https://bun.sh/install | bash
```

### Installing Node via nvm (recommended)

```bash
nvm install 22
nvm use 22
```

## Rebuild From Scratch (Step by Step)

### 1. Clone the repo

```bash
git clone https://github.com/Gitlawb/openclaude.git
cd openclaude
```

### 2. Install dependencies

```bash
bun install
```

This reads `package.json` and installs everything into `node_modules/`. Bun also generates `bun.lockb` (the lockfile — treat it like `package-lock.json`).

### 3. Build the CLI

```bash
bun run build
```

This runs `scripts/build.ts`, which bundles the TypeScript source into a single distributable file at `dist/cli.mjs`. This is the file that gets shipped to users via npm.

### 4. Smoke test

```bash
bun run smoke
```

Runs `bun run build && node dist/cli.mjs --version` — confirms the build works and prints the version.

### 5. Run the app locally

```bash
bun run dev
```

This runs `bun run build && node bin/openclaude` — builds and then launches the CLI in development mode.

### 6. Full validation

```bash
bun run check
```

Runs smoke test + dead code analysis (`knip`) + full test suite. This is what CI runs.

## Project Structure (What Each Directory Does)

```
openclaude/
├── src/
│   ├── commands/          # Slash commands and CLI command implementations
│   ├── components/        # React/Ink terminal UI components
│   ├── services/          # API clients, MCP, OAuth, voice, etc.
│   ├── tools/             # Tool implementations (file edit, bash, etc.)
│   ├── utils/             # Shared utility functions
│   ├── integrations/      # Provider and model metadata
│   ├── entrypoints/       # CLI entry, MCP server, SDK, generated types
│   ├── tasks/             # Local, remote, workflow, monitor tasks
│   ├── screens/           # Full-screen UI views
│   └── hooks/             # React hooks for the terminal UI
├── bin/
│   └── openclaude         # CLI entry point (shell script)
├── dist/
│   ├── cli.mjs            # Built CLI (the actual distributable)
│   └── sdk.mjs            # Built SDK
├── scripts/               # Build, test, and dev scripts
├── docs/                  # Documentation and integration guides
├── web/                   # Documentation website
├── vendor/                # Vendored dependencies (node-domexception shim)
├── agents/                # Agent guides and conventions
├── package.json           # Dependencies, scripts, metadata
├── tsconfig.json          # TypeScript configuration
├── AGENTS.md              # AI agent coding guide
└── CONTRIBUTING.md        # Contributor guidelines
```

## Key Files to Understand

### `package.json` — The Brain

All build/dev/test commands are defined in `"scripts"`. The important ones:

| Command | What It Does |
|---------|-------------|
| `bun run build` | Bundles source → `dist/cli.mjs` |
| `bun run dev` | Build + launch CLI |
| `bun run smoke` | Build + `--version` check |
| `bun run check` | Smoke + dead code + full tests |
| `bun run test` | Run unit tests |
| `bun run typecheck` | TypeScript type checking |
| `bun run doctor:runtime` | System diagnostics |

### `src/entrypoints/` — Where It All Starts

- `cli.mts` — Main CLI entry point (parses args, launches the app)
- `sdk.mts` — Public SDK entry for programmatic use
- `mcp.mts` — MCP (Model Context Protocol) server entry

### `bin/openclaude` — The Shell Launcher

A shell script that finds Node and runs `dist/cli.mjs`. This is what users invoke when they type `openclaude` in their terminal.

### `scripts/build.ts` — The Build Pipeline

Bundles all TypeScript source into a single ESM file (`dist/cli.mjs`) using Bun's bundler. Handles React/Ink JSX, external dependencies, and Node built-ins.

## Customization Points

### Adding a New Provider

1. Read `docs/integrations/overview.md`
2. Follow the how-to guide in `docs/integrations/how-to/`
3. Add provider metadata in `src/integrations/`
4. Add API client in `src/services/api/`
5. Test with `bun run test:provider`

### Adding a New Tool

1. Create a new file in `src/tools/`
2. Follow existing tool patterns (look at adjacent files)
3. Register it in the tool index
4. Add tests in a `.test.ts` file next to the tool

### Adding a New Slash Command

1. Create a new file in `src/commands/`
2. Follow existing command patterns
3. Register it in the command index

### Modifying the Terminal UI

Components live in `src/components/` and use React + Ink. The pattern is:
- Functional components with hooks
- `chalk` for colors
- `cli-boxes` for box drawing
- `figures` for unicode symbols

## If Something Breaks

### Build fails

```bash
# Clean and rebuild
rm -rf dist node_modules
bun install
bun run build
```

### Tests fail

```bash
# Run just the failing test file
bun test ./path/to/failing.test.ts

# Run with more output
bun test --verbose ./path/to/failing.test.ts
```

### Type errors

```bash
bun run typecheck
```

### Runtime errors

```bash
bun run doctor:runtime
```

This runs a system check that reports Node version, platform, key dependencies, and potential issues.

## Minimum Viable OpenClaude

If you need to get OpenClaude running with the absolute minimum:

```bash
git clone https://github.com/Gitlawb/openclaude.git
cd openclaude
bun install
bun run build
node dist/cli.mjs --version
```

That's it — you have a working CLI. Set your provider environment variables and go.

## Environment Variables (Quick Reference)

| Variable | Purpose | Required for Linux |
|----------|---------|-------------------|
| `CLAUDE_CODE_USE_OPENAI` | Set to `"1"` to use OpenAI-compatible APIs | YES |
| `OPENAI_API_KEY` | API key for OpenAI / compatible providers | YES — without this, CLI defaults to Anthropic |
| `OPENAI_BASE_URL` | Custom endpoint URL (DeepSeek, Ollama, etc.) | YES — set to `https://opencode.ai/zen/v1` |
| `OPENAI_MODEL` | Model name to use | YES — set to `big-pickle` |
| `ANTHROPIC_API_KEY` | API key for Anthropic | Only if using Anthropic directly |
| `OPENCLAUDE_OLLAMA_NUM_CTX` | Ollama context window size | Only for Ollama |

**Linux gotcha:** The Windows build reads `.openclaude-profile.json` which has the full provider config. The Linux build doesn't read it the same way, so you MUST set these env vars in `.openclaude/.env` or the CLI will ask for Anthropic login.

## Further Reading

- [AGENTS.md](../../AGENTS.md) — AI agent coding conventions
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — Contributor guidelines and PR process
- [docs/advanced-setup.md](../../docs/advanced-setup.md) — Advanced provider configuration
- [docs/quick-start-windows.md](../../docs/quick-start-windows.md) — Windows setup guide
- [docs/quick-start-mac-linux.md](../../docs/quick-start-mac-linux.md) — Mac/Linux setup guide