
# 🕵️‍♂️ AI Agent Context - ComfyUI Workflow Issue
This is a summary of the current issue for the next AI Agent.

## 📌 Issue Summary
The `z-image-turbo.safetensors` model is failing to load with the standard `CheckpointLoaderSimple` node in ComfyUI.
The error is: `RuntimeError: ERROR: clip input is invalid: None`.

## 🔍 Investigation Findings
- **Model Source:** `Comfy-Org/z_image_turbo` (Hugging Face)
- **File:** `split_files/diffusion_models/z_image_turbo_bf16.safetensors` (12.3GB)
- **Analysis:** This appears to be a **Diffusion Only** model (UNet/Transformer only), meaning it **does not contain the CLIP (Text Encoder) or VAE**.
- **Current Workflow:** Uses `CheckpointLoaderSimple` which expects a full checkpoint (Model + CLIP + VAE).

## ✅ Solution Plan (For Next AI)
You need to refactor the `workflow_api.json` to load components separately:
1.  **Load Diffusion Model:** Use `UNETLoader` (or similar) to load `z-image-turbo.safetensors`.
2.  **Load CLIP:** Use `CLIPLoader` to load a standard CLIP model (e.g., from SDXL or similar relevant architecture).
    - *Note:* Need to download a CLIP model (e.g., `t5xxl_fp16.safetensors` + `clip_l.safetensors` for Flux/SD3).
3.  **Load VAE:** Use `VAELoader` to load a standard VAE (e.g., `ae.safetensors`).
4.  **Connect:** Link these separate outputs to the `KSampler` and `CLIPTextEncode`.

## ⚠️ Action Required
- Download the necessary **CLIP** and **VAE** models to `models/clip` and `models/vae`.
- Update `workflow_api.json` to use the multi-loader approach.
