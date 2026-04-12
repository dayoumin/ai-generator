# Desktop UX IA

## Goal

Define a desktop-first information architecture for the studio so users can:

- choose a project
- choose a generation strategy
- compose a scene
- generate
- review and retry

without switching across too many disconnected tabs.

## Primary UX Principle

The desktop product should optimize for a continuous studio workflow, not a toolbox of separate pages.

The current UI exposes the right capabilities, but the interaction model is fragmented:

- project selection lives in the top bar
- prompts and scene planning live in `Prompts`
- templates and references live in `References`
- mode, renderer, and operator live in the confirm modal
- compare, retry, lineage, and handoff live in `Outputs`

This increases mental load because users must remember what is stored where and what will affect the next run.

## Proposed Top-Level IA

Replace the current task emphasis with this desktop-first structure:

1. `Dashboard`
2. `Compose`
3. `Outputs`
4. `Settings`
5. `Guide`

## Role Of Each Area

### 1. Dashboard

Purpose:

- quick project overview
- current renderer status
- current operator mode
- recent runs
- entry points into the main workflow

Should contain:

- active project card
- renderer health card
- last run summary
- quick actions:
  - `Open Compose`
  - `Open Latest Output`
  - `Resume Assisted Retry`

Should not contain:

- detailed generation configuration
- prompt table editing
- run diff internals

### 2. Compose

Purpose:

- the main workspace for setting up the next run

This should become the primary work area and combine what is currently split across `Prompts`, `References`, and the confirm modal.

Compose should include these sections in one screen:

- `Project Context`
  - project selector
  - generation mode
  - renderer
  - operator
  - provider/operator notes

- `Scene Setup`
  - scene template picker
  - template save/apply/delete
  - Scene Planner fields
  - active template summary

- `Reference Setup`
  - selected references summary
  - asset browser
  - slot coverage status
  - upload tools

- `Prompt + Style`
  - prompt file selector
  - prompt table
  - custom prompt form
  - style prompt
  - negative prompt
  - steps
  - repeat count
  - aspect ratio

- `Preflight`
  - visible before start, not only in a modal
  - errors
  - warnings
  - effective output count
  - required missing slots

- `Generate`
  - single clear primary action
  - optional compact confirmation, but not a config-heavy modal

### 3. Outputs

Purpose:

- inspect the latest result
- compare direct vs assisted
- review
- retry

This page should use progressive disclosure.

Default visible sections:

- gallery
- run summary cards
- current run state

Collapsed or secondary sections:

- diff details
- retry suggestion internals
- retry lineage internals
- Codex handoff preview

The key rule:

The first screen in Outputs should answer `what happened` before it answers `why` or `how to debug it`.

### 4. Settings

Purpose:

- stable app-level preferences

Examples:

- sound
- auto-clear behavior
- future desktop preferences

It should not hold generation-state decisions for the next run.

### 5. Guide

Purpose:

- explain concepts
- explain CSV or prompt file format
- explain renderer/operator differences
- explain direct vs assisted workflow

This should be reference material, not a required path through the product.

## Key Desktop Workflow

The primary happy path should be:

1. Pick project
2. Pick generation mode
3. Pick renderer
4. Pick operator
5. Choose template or start blank
6. Add references
7. Adjust scene planner
8. Adjust prompts and style
9. Review preflight
10. Generate
11. Review results
12. Retry if needed

This entire setup path should mostly happen inside `Compose`.

## Main UX Corrections

### Correction 1: Move execution choices out of the confirm modal

`Generation Mode`, `Renderer`, and `Operator` are major setup decisions.

They should be visible in the Compose header, not hidden until the last click.

The confirm modal should become lightweight and only confirm:

- estimated output count
- warnings
- final start action

### Correction 2: Treat template + scene planner + references as one concept

Users think in scenes, not in separate tabs.

The UI should make it obvious that:

- templates capture reusable scene structure
- Scene Planner refines the current run
- references ground identity and scene slots

These should be presented as parts of one composition system.

### Correction 3: Reduce tab switching during setup

The user should not need to bounce:

- Prompts -> References -> modal -> Outputs

for every run.

The desktop version should aim for:

- setup in one workspace
- review in one workspace

### Correction 4: Change onboarding to match the real product model

The current onboarding implies a simple prompt-first generator.

The new onboarding should teach the actual desktop workflow:

- choose project
- choose direct or assisted
- add references or template
- generate and compare

### Correction 5: Split output review into Basic and Advanced layers

Basic:

- gallery
- run status
- approve/reject/note

Advanced:

- compare
- diff
- retry suggestion
- retry lineage
- Codex handoff preview

## Suggested Desktop Layout

### Compose layout

Use a 3-column desktop layout:

- left rail: project and execution setup
- center canvas: prompts and scene planner
- right rail: template, reference summary, preflight, generate

Alternative:

- top sticky workflow header
- left main composition area
- right sticky execution summary

### Outputs layout

Use a 2-level structure:

- top: gallery and result summary
- expandable analysis drawer below or on the side

## Interaction Rules

### Sticky decisions

These should always remain visible while composing:

- project
- mode
- renderer
- operator
- selected template
- selected reference count
- selected prompt count

### Save semantics

The UI should make these distinctions explicit:

- `Template` = reusable scene structure
- `Current run` = temporary setup for the next generation
- `Run review` = feedback on generated outputs

### Warning visibility

Warnings should appear before clicking `Generate`, not only in a modal after the user already decided to start.

## Phased Rollout

### Phase 1

- keep current tabs
- introduce `Compose` as the new primary tab
- move mode/renderer/operator into the page
- keep confirm modal lightweight

### Phase 2

- demote or merge old `Prompts` and `References`
- simplify Dashboard
- collapse advanced Outputs panels by default

### Phase 3

- fully align onboarding, Dashboard, and Outputs around the new mental model

## Success Criteria

The desktop IA is improved if a new user can answer these questions without guesswork:

1. What project am I in?
2. Am I using direct or assisted generation?
3. Which renderer is active?
4. Which operator is active?
5. Which template is applied?
6. Which references are applied?
7. What will affect the next run?
8. Why did preflight warn me?
9. Where do I review and retry?
