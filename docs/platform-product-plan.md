# AI Generator Platform Product Plan

## 1. Product Definition

This app is not a single-project image generator. It should become a reusable image generation studio that can support multiple projects with different characters, assets, styles, and output rules.

Core goals:

- Support multiple projects with different worldbuilding, characters, assets, and output profiles.
- Preserve a stable creative frame while still producing varied situations, reactions, props, and compositions.
- Support multiple rendering backends such as ComfyUI, API-based models, and local models.
- Support multiple operating paths: direct studio runs, assisted studio runs, and conversational Codex-guided runs.
- Keep generation, review, reuse, manifest export, and upload in one operating tool.
- Support both direct generation and LLM-assisted generation.

## 2. Product Principles

### 2.1 Separate shared core from project policy

Shared core responsibilities:

- generation request model
- run state and history
- template management
- review state
- provider adapter calls
- result storage, manifest, and upload pipeline

Project-specific responsibilities:

- character assets
- background, prop, and style assets
- prompt policy
- output sizes and crop rules
- required slot policy
- default provider settings

### 2.2 Separate fixed elements from variation elements

To avoid repetitive output, do not randomize everything. Split the system into:

Fixed elements:

- character identity
- brand tone
- world rules
- output format rules
- project safety rules

Variation elements:

- emotion
- pose
- reaction
- background situation
- props
- composition
- camera distance
- lighting
- time of day
- season

### 2.3 Templates must be domain models, not just presets

Templates should represent meaning, not only UI state.

Required meaning:

- single, duo, and group composition
- character slots
- scene slots
- prop slots
- style slots
- output profile set
- allowed variation rules
- provider hints

### 2.4 Direct and assisted generation must coexist

The product should support both paths:

- Direct generation: user chooses prompts and options and renders directly.
- Assisted generation: user defines the scene through structured UI and an LLM translates that into a richer generation spec.

Rules:

- keep the current direct path
- add assisted generation as an additional mode
- share project assets, templates, and review flows across both modes
- let the user choose speed versus precision per task

### 2.5 Separate render backend from operator mode

Do not treat every usage style as just another provider.

Separate these concerns:

- render backend: API, ComfyUI, local model
- operator mode: studio, Codex conversation

This creates three practical usage styles:

- direct plus API
- direct plus local
- conversational plus Codex using the same scene state

## 3. Core Domain Model

### 3.1 Project

- project id
- name
- description
- prompt source
- reference asset root
- template slot policy
- output profiles
- default provider
- generation defaults

### 3.2 Template

- template id
- name
- composition type: single, duo, group
- scene intent
- fixed slots
- variable slots
- style rules
- output profile set
- provider hints

### 3.3 Character

- character id
- identity assets
- emotion assets
- role assets
- prop assets
- prompt hints

### 3.4 Scene

- scene type
- background
- context
- interaction rules
- camera rules
- lighting rules

### 3.5 SceneSpec

- project
- template
- actors
- scene
- props
- visual rules
- output targets
- variation controls

### 3.6 GenerationRequest

- project
- provider
- mode: direct or assisted
- template or scene spec
- prompt inputs
- output types
- generation params

### 3.7 Run

- run id
- project
- request snapshot
- provider execution state
- output list
- review state
- upload state

## 4. Variety Strategy

### 4.1 Variety layers

Use layered variation:

1. Character layer
- single
- duo
- group

2. Emotion layer
- neutral
- joy
- awkward
- anger
- surprise
- comfort

3. Situation layer
- conversation
- conflict
- collaboration
- encouragement
- mistake
- daily life
- event

4. Environment layer
- indoor
- outdoor
- home
- office
- cafe
- transit

5. Visual layer
- close-up
- medium shot
- wide shot
- front
- side
- top

6. Style layer
- fixed brand style
- project style anchors
- situation-specific style intensity

### 4.2 Variation rules

- lock identity strongly
- vary emotion, scene, props, and camera within bounded rules
- allow output-type-specific composition changes
- prefer structured variation over seed-only repetition

## 5. Target Architecture

### 5.1 Layers

1. Project Registry
- load project settings
- validate schema

2. Asset Catalog Service
- index reference assets
- classify by slots

3. Template Service
- save templates
- validate templates
- apply templates

4. Generation Service
- normalize UI input into GenerationRequest
- run preflight validation

5. Provider Adapter Layer
- ComfyUI adapter
- API adapter
- Ollama helper adapter

6. LLM Orchestration Layer
- scene planning
- prompt composition
- variation planning
- QC assistance

7. Run Store
- persist run state
- persist outputs
- persist review state

### 5.2 Provider roles

ComfyUI:

- primary local renderer
- default rendering backend

API provider:

- commercial image API path
- high quality or model-specific path

Ollama:

- better fit for prompt correction, QC, and scene composition help
- can become a rendering adapter if a suitable local image path is added

### 5.3 Dual generation modes

Direct Generation Mode:

- user chooses project, prompts, reference assets, and generation options
- ComfyUI or an API provider renders directly
- keep this as the fast default path

Assisted Generation Mode:

- user defines template, characters, emotion, background, props, situation, and camera through structured UI
- an LLM converts that into a SceneSpec and final generation instructions
- if a direct image generation route is available, use it
- otherwise pass the enriched instructions to a rendering provider

### 5.5 Operator modes

Studio Operator Mode:

- generation is started and executed by the app UI
- the app owns preflight, request submission, and run tracking

Codex Conversation Mode:

- the user keeps working in the web UI but also collaborates in chat
- Codex reads the same scene state, templates, references, and review notes
- Codex can guide prompt composition, scene refinement, retry planning, and manual generation work
- renderer choice remains separate from operator mode

### 5.4 State storage

Current global in-memory state is not suitable long term.

Initial recommended structure:

- `outputs/<project>/runs/<run-id>/run.json`
- `outputs/<project>/runs/<run-id>/assets/...`
- `outputs/<project>/runs/<run-id>/manifest.json`

Later option:

- SQLite or another database

## 6. UI/UX Plan

### 6.1 Journey-based information architecture

Recommended flow:

1. Project
- choose project
- show provider status

2. Mode
- direct generation
- assisted generation
- studio operator or Codex conversation operator

3. Template or Prompt
- direct mode: prompt source, style, generation params
- assisted mode: choose or create template

4. Scene Build
- choose characters
- choose emotion, role, background, and props
- build single, duo, or group composition

5. Prompt and Output
- choose prompt source
- confirm style rules
- choose output types
- set generation params
- confirm render backend versus operator mode

6. Preflight
- show missing slots
- show provider support
- show template compatibility
- show expected output count

7. Generate and Review
- run generation
- review outputs
- crop, manifest, and upload

### 6.2 UI principles

- keep project switching global
- make template a first-class concept, not a sub-feature of references
- make it obvious what a template stores
- show missing items before showing output count
- hide provider complexity when possible but expose support limits clearly
- clearly separate direct generation and assisted generation

## 7. Authentication Strategy

### 7.1 Separate user auth from model auth

There are two different concerns:

1. User authentication
- who can enter the app

2. AI provider authentication
- which model service the app can call

Do not treat them as the same thing.

### 7.2 Recommended baseline

Initial options:

- no auth or simple admin auth for local/internal use
- Google or GitHub login for external multi-user use
- if needed: Firebase Auth, Supabase Auth, Clerk, or Auth0

Important distinctions:

- a consumer subscription is not the same thing as API access
- a login provider is not the same thing as a model provider
- even if a user already pays for a consumer AI subscription, automated calls inside this app may still need separate API credentials and billing

### 7.3 OpenAI Codex / Gemini position

- do not plan around "Sign in with OpenAI/Codex" as a general user login provider
- treat "Gemini login" as Google login, not as a separate identity provider
- keep user auth on Google or GitHub and keep model access separate

### 7.4 Subscription usage strategy

The real goal is not "login with subscriptions". The goal is to use the AI environment that already exists as effectively as possible.

Recommended approach:

- use standard user auth for people
- use provider credentials for model access
- allow project-level or operator-level provider keys
- rely on official API and SDK paths, not on consumer-subscription-only UX

Practical interpretation:

- ChatGPT Plus/Pro and Google AI Pro are not reliable foundations for automated app-side entitlement
- OpenAI API, Gemini API, and local Ollama are the realistic provider routes
- Codex/Gemini are more valuable for orchestration than for identity

### 7.5 Where Codex/Gemini add value

1. Scene Planner
- normalize template and slot selections into a scene description

2. Prompt Composer
- build final prompts with project rules

3. Variation Engine
- create safe variations that reduce repetition

4. QC Assistant
- describe result images, detect missing elements, suggest retries

5. Review Copilot
- help reviewers approve or reject faster

6. Assisted Generation Mode
- power the structured scene-building path
- coexist with provider-based rendering

Conclusion:

Using Codex/Gemini as an orchestration layer is more realistic and more valuable than trying to use them as a login mechanism.

## 8. Phase Priorities

### Phase A. Lock the design

- finalize domain model
- finalize template structure
- define provider adapter interface
- separate user auth strategy from provider credential strategy

### Phase B. Refactor the core

- introduce GenerationRequest
- introduce ProviderAdapter
- introduce RunStore
- remove global batch_status dependence
- add generation mode split: direct vs assisted

### Phase C. Upgrade the template system

- support single, duo, and group templates
- separate fixed slots and variable slots
- add variation rules
- define a normalized SceneSpec format

### Phase D. Rebuild the UI flow

- create a template-centered generation workspace
- add preflight validation
- reorganize around project-centered workflows
- add a clear direct-versus-assisted mode switch

### Phase E. Add operating features

- review workflow
- upload policy
- user auth
- team operation features
- AI orchestration copilot
- assisted-generation comparison and retry loop

## 9. Scoped Releases

### 9.1 V1 Scope

V1 goal:

- keep the current direct generation workflow usable
- add a practical assisted generation path that improves consistency and scene accuracy
- avoid architecture work that will be thrown away later

Include in V1:

- multi-project project registry based on `projects/*.json`
- current direct generation flow using ComfyUI
- template v1 with single and duo support
- fixed slots and variable slots
- SceneSpec v1
- GenerationRequest with `mode=direct|assisted`
- file-based RunStore
- minimal preflight validation
- assisted generation as `scene spec -> prompt composition -> provider render`
- review, crop, manifest, and upload flow kept intact

V1 preflight checks:

- missing required slots
- provider support mismatch
- template and project mismatch
- output count summary

Do not require in V1:

- user auth
- team collaboration
- full API-provider parity
- direct LLM pixel rendering as a required path
- advanced QC automation
- group-template completeness

### 9.2 V1.5 Scope

Candidate V1.5 items:

- first-class API provider support
- richer assisted retry suggestions
- assisted result comparison UI
- better prompt repair and QC support from local helper models
- template import and export
- stronger project schema validation

### 9.3 V2 Scope

Candidate V2 items:

- user auth
- multi-user collaboration
- team review workflows
- advanced provider matrix
- group composition templates
- automated QC and retry orchestration
- deeper direct-generation support from LLM-integrated image paths

## 10. V1 Design Spec

### 10.1 GenerationRequest v1

Purpose:

- define one normalized request object for both direct and assisted generation

Fields:

- `requestId`
- `projectId`
- `mode`: `direct` or `assisted`
- `providerId`
- `operatorMode`
- `templateId` optional
- `sceneSpec` optional
- `promptSource` optional
- `promptText` optional
- `referenceAssetIds`
- `outputTypes`
- `generationParams`
- `metadata`

Notes:

- direct mode can rely on `promptSource` and `promptText`
- assisted mode should rely on `sceneSpec`
- both modes should end up passing through one generation service path

### 10.2 Template v1

Purpose:

- store reusable scene-building structures without trying to solve every future case

Fields:

- `templateId`
- `projectId`
- `name`
- `mode`: `single` or `duo`
- `description`
- `fixedSlots`
- `variableSlots`
- `styleRules`
- `defaultOutputTypes`
- `providerHints`
- `updatedAt`

V1 slot set:

- `identity`
- `emotion`
- `role`
- `scene`
- `prop`
- `style`

Notes:

- group mode is deferred beyond v1
- template v1 should be expressive enough for single and duo use cases only

### 10.3 SceneSpec v1

Purpose:

- define the structured scene used by assisted generation

Fields:

- `projectId`
- `templateId`
- `actors`
- `scene`
- `props`
- `visual`
- `style`
- `outputs`
- `variation`

Suggested shape:

- `actors`: list of one or two actor objects
- `scene`: background, location, situation, interaction
- `props`: selected prop ids
- `visual`: framing, camera distance, lighting
- `style`: style anchor ids or style labels
- `outputs`: output type list
- `variation`: bounded variation controls

### 10.4 Run v1

Purpose:

- persist a single execution independently of process memory

Fields:

- `runId`
- `projectId`
- `request`
- `status`
- `providerState`
- `results`
- `reviewSummary`
- `uploadSummary`
- `createdAt`
- `updatedAt`

Status values:

- `queued`
- `running`
- `success`
- `partial`
- `error`
- `cancelled`

### 10.5 ValidationResult v1

Purpose:

- return preflight findings before execution

Fields:

- `ok`
- `errors`
- `warnings`
- `missingSlots`
- `providerCompatibility`
- `outputSummary`

V1 checks:

- missing required slots
- template and project mismatch
- unsupported provider/reference combination
- empty prompt path in direct mode
- empty or invalid SceneSpec in assisted mode

### 10.6 GenerationParams v1

Purpose:

- keep rendering parameters stable across modes

Fields:

- `aspectRatio`
- `steps`
- `batchCount`
- `seed` optional
- `negativePrompt` optional
- `extraPositive` optional

## 11. V1 Service Boundaries

### 11.1 Project Registry

Responsibilities:

- load project configs
- validate project existence
- expose project defaults

### 11.2 Template Service

Responsibilities:

- list templates
- save templates
- validate templates
- map template slots into a SceneSpec starter

### 11.3 Generation Service

Responsibilities:

- accept GenerationRequest
- normalize mode-specific input
- call preflight validation
- route to provider adapter
- create and update Run records

### 11.4 Provider Adapter

Required interface:

- `validate(request)`
- `submit(request)`
- `poll(run)`
- `collect(run)`
- `supportsReferenceAssets()`

V1 requirement:

- ComfyUI adapter required
- API adapter optional but interface should be designed now

### 11.5 Run Store

Responsibilities:

- create run records
- update run status
- store result metadata
- store review and upload summary

Storage format for V1:

- file-based JSON per run

### 11.6 Preflight Validation

Responsibilities:

- validate by mode
- validate by project slot policy
- validate provider compatibility
- produce user-facing errors and warnings

## 12. V1 UI Mapping

### 12.1 Direct Mode UI

Inputs:

- project
- prompt file or manual prompt
- reference assets
- style prompt
- negative prompt
- aspect ratio
- steps
- batch count

Output:

- GenerationRequest with `mode=direct`

### 12.2 Assisted Mode UI

Inputs:

- project
- template
- one or two actors
- emotion
- role
- background and situation
- props
- style anchor
- output types

Output:

- SceneSpec
- GenerationRequest with `mode=assisted`

### 12.3 Shared UI Outputs

- preflight panel
- run status
- latest preview
- gallery results
- review controls
- manifest and upload actions

### 12.4 Operator controls

The shared generation modal should expose:

- render backend selector
- operator mode selector
- direct versus assisted generation mode

Rules:

- `direct + studio` is the default fast path
- `direct + codex` is not required
- `assisted + studio` is the app-managed assisted path
- `assisted + codex-conversation` is the chat-guided path using the same scene state

## 13. Decisions To Make Now

1. Is the first target an internal tool or a multi-user service?
2. Is the minimum template unit a scene template or a character-combination template?
3. Do we add auth now or stay local-first for the first release?
4. Is Ollama a rendering provider or a support engine?
5. Does Codex/Gemini run in the runtime orchestration layer or only as an operator-side helper?
6. In assisted generation, should we prefer direct image generation or provider rendering first?

## 14. Current Conclusion

The correct direction is a reusable multi-project image generation platform.

The first priorities are not visual polish. They are:

- clean domain model
- provider abstraction
- persistent run state
- proper template domain design

After that, UI/UX should be rebuilt around template-centered workflows.

Also, if the goal is to use AI subscriptions effectively, the better path is not to force them into login. The better path is to use Codex/Gemini for scene planning, prompt composition, variation, and QC.

Finally, keep the original direct-generation workflow and add an LLM-assisted workflow next to it. The product should expose both as selectable generation modes inside the same studio.
