# AI Specification Files

Each JSON file here defines a unique AI configuration to be tested.
See `AI_SPEC_FORMAT.md` in the parent directory for the full spec format.

## Naming Convention

`{provider}-{model}-{variant}.json`

## Example Files

- `openclaudedotdev-gpt52codex-bigpickle.json` — our tuned Big Pickle config
- `openclaudedotdev-gpt52codex-default.json` — same model, vanilla settings
- `anthropic-claudeopus40-default.json` — Claude Opus 4, default
- `ollama-llama31-8b-default.json` — local Llama 3.1
