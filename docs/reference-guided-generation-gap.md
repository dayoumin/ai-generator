# Reference-Guided Generation Gap

## Current State

The studio can now:

- select a project
- load prompt files per project
- upload and select reference assets
- send selected reference metadata with batch requests

But the current [workflow_api.json](/D:/Projects/AI_Generator/workflow_api.json) is still a plain text-to-image workflow.

Current node set:

- `UNETLoader`
- `CLIPLoader`
- `VAELoader`
- `CLIPTextEncode`
- `EmptySD3LatentImage`
- `KSampler`
- `VAEDecode`
- `SaveImage`

There is no image-input conditioning node yet.

## What This Means

Reference assets are currently useful for:

- organizing the character bible
- selecting which identity anchors should apply to a batch
- storing that selection in batch metadata
- preparing the UI and workflow for the next step

They are **not yet** used by ComfyUI as a conditioning input.

## Required Next Step

Add a second workflow for reference-guided generation, for example:

- image reference encoder
- IP-Adapter style conditioning
- Redux or similar image-conditioning path
- optional image prompt or identity-preserving node chain

Then update `app.py` to:

1. choose the reference workflow when assets are selected
2. upload or point ComfyUI to the selected reference files
3. map selected assets into workflow node inputs

## Recommended Sequence

1. Keep the current text-only workflow as the safe default.
2. Create `workflow_reference_api.json` as a separate experiment.
3. Add provider capability flags:
   - `supportsReferenceAssets: false` for current text workflow
   - `supportsReferenceAssets: true` when the new workflow is ready
4. Gate the UI with a clear label when reference assets are metadata-only.
