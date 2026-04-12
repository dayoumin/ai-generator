# AI Agent Context

This file stores durable notes for future agent sessions.

## Current Technical Context

The current ComfyUI workflow uses separate loaders:

- `UNETLoader`
- `CLIPLoader`
- `VAELoader`

This replaced the older `CheckpointLoaderSimple` assumption because the selected model is diffusion-only and does not include CLIP or VAE in a single checkpoint.

## Current Product Direction

`AI_Generator` is being positioned as a reusable multi-project image generation studio rather than a single-project tool.

The product direction now includes:

- multi-project support
- project-specific assets and policies
- direct generation mode
- LLM-assisted generation mode
- template-centered workflows
- provider abstraction across ComfyUI, API providers, and local helper models

See `docs/platform-product-plan.md` for the current product plan.

## Codex Encoding Safety Note

This repository is edited in an environment that often runs on Windows PowerShell 5.1 with legacy console code pages.

Observed risks:

- Korean text can appear as mojibake in shell output.
- Non-ASCII content can be corrupted during write or display steps.
- Console output problems do not always mean file corruption, but file corruption can also happen.

Rules for future Codex sessions:

1. Prefer ASCII-only edits for agent-authored docs and planning files.
2. Do not rely on shell output to verify non-ASCII text correctness.
3. When checking text integrity, verify using Python file reads instead of console display.
4. Avoid large direct edits to Korean copy unless the environment is known-safe for UTF-8.
5. Keep durable planning docs in ASCII if Codex is expected to edit them again.

## Immediate Open Themes

- introduce provider adapters
- replace global batch state with persistent run storage
- upgrade templates into a structured domain model
- add direct vs assisted generation as explicit product modes
