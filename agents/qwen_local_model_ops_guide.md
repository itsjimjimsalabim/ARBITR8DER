# Qwen Local Model Ops Guide

Purpose: keep one small always-on manager model and one larger on-demand coding model available on this laptop, without guessing about what the machine is doing.

## Current Local Split

- `qwen3:4b-instruct` is the small manager model.
- `qwen3-coder:30b` is the larger coding worker.
- `ollama serve` is the local model host.

## What Each Model Is For

- Use `qwen3:4b-instruct` for all-day coordination, summaries, planning, routing, and short edits.
- Use `qwen3-coder:30b` for onboarding a hard task, analyzing a bigger code change, or doing a complex coding burst.
- After the hard task is done, stop leaning on the 30b model so the laptop can stay responsive.

## Verified Machine Tools

| Tool | Verify | Version | Notes |
|------|--------|---------|-------|
| Git | `git --version` | `2.55.0.windows.2` | source control |
| GitHub CLI | `gh --version` | `2.96.0` | push, pull, PR, repo ops |
| Python | `python --version` | `3.12.4` | primary interpreter on this machine; `python3` is not an alias here |
| Node.js | `node --version` | `v24.18.0` | JavaScript tooling |
| Bun | `bun --version` | `1.3.14` | OpenCode / JS runtime support |
| Ollama | `ollama --version` | `0.32.3` | local model runtime |

## How To Check Progress

Use these commands when someone asks whether a pull is still running or whether a model is already installed:

```powershell
ollama list
ollama ps
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'ollama.exe' } | Select-Object ProcessId, CommandLine
Get-ChildItem "$env:USERPROFILE\.ollama\models\blobs" -Filter '*-partial'
```

Download logs from the last pull live under:

```text
trading_studio/runtime/logs/ollama-downloads/
```

## What It Does To The Laptop

- CPU: expect real CPU usage when the models are active. Do not assume the local AI NPU is being used unless you benchmark it.
- RAM: the 4b manager model is light enough to keep around; the 30b coder model can get heavy and should be treated as a burst tool.
- Disk: the installed models currently take about 20.5 GB total on disk, plus cache and any partial blobs.
- Network: initial pulls are large and will consume bandwidth.
- Responsiveness: the 30b model is the one most likely to make the laptop feel busy; unload or ignore it first if the machine starts to drag.

## Hardware Reference

- Full specs live in `agents/System Information (PC SPECS).txt`.
- The laptop has AMD Ryzen AI hardware, but Ollama should still be treated as CPU-first unless a benchmark proves otherwise.

## Operating Rule

- Keep `qwen3:4b-instruct` ready for all-day management.
- Pull `qwen3-coder:30b` only when you need the bigger reasoning/coding worker.
- If the laptop needs headroom, stop using the 30b model first.
