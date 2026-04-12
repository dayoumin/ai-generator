# Project Setup Responsibilities

## Principle

`AI_Generator` is the shared image studio.
Each project provides its own image spec and assets.

## What Lives In AI_Generator

- studio UI
- project selector
- prompt loading
- reference asset browsing and upload
- batch generation flow
- crop / manifest / upload
- provider adapters

Typical files:

- [app.py](/D:/Projects/AI_Generator/app.py)
- [index.html](/D:/Projects/AI_Generator/index.html)
- [app.js](/D:/Projects/AI_Generator/static/js/app.js)
- [style.css](/D:/Projects/AI_Generator/static/style.css)

## What Lives In Each Project

- project config
- prompt source files
- reference assets
- crop rules
- final injection or sync logic

MBTI example:

- [mbti.json](/D:/Projects/AI_Generator/projects/mbti.json)
- [prompts.json](/D:/Projects/MBTI/scripts/image-gen/output/prompts.json)
- [reference-assets](/D:/Projects/MBTI/scripts/image-gen/reference-assets)
- [manifest.json](/D:/Projects/MBTI/scripts/image-gen/reference-assets/characters/haru/manifest.json)
- [prompt-pack.json](/D:/Projects/MBTI/scripts/image-gen/reference-assets/characters/haru/prompt-pack.json)

## Generation Modes

### 1. Local model

- engine: `ComfyUI`
- good for bulk iteration and local control
- current default mode

### 2. API model

- engine: hosted provider
- good for selective high-quality shots
- should use the same prompt/reference structure as local mode

### 3. Codex-assisted mode

Codex does not have to be the pixel renderer.
Codex can operate this structure by:

- creating or editing project configs
- preparing prompt packs
- organizing reference assets
- choosing the right provider
- triggering available engines through the studio
- reviewing outputs and refining prompts

In practice:

- renderer = `ComfyUI` or API
- orchestrator = `Codex`

That is the recommended third mode.
