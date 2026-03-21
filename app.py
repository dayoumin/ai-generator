import json
import uuid
import asyncio
import os
import re
import random
import time
from datetime import datetime
import pandas as pd
from fastapi import FastAPI, Form, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
import aiohttp
from typing import List, Dict
import boto3
from botocore.config import Config
from dotenv import load_dotenv
import logging
from dataclasses import dataclass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ComfyUI-Batch")

load_dotenv()

app = FastAPI()

# Configuration
COMFYUI_SERVER_ADDRESS = "127.0.0.1:8188"
CLIENT_ID = str(uuid.uuid4())
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
PROMPTS_DIR = os.path.join(BASE_DIR, "kemi", "prompts")
WORKFLOW_PATH = os.path.join(BASE_DIR, "workflow_api.json")

os.makedirs(PROMPTS_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


# --- Helpers ---
def validate_filename(filename: str) -> bool:
    return '..' not in filename and '/' not in filename and '\\' not in filename


def add_log(message, level="info"):
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = {"warning": "WARN", "error": "ERROR", "success": "OK"}.get(level, "")
    entry = f"[{ts}] {prefix} {message}" if prefix else f"[{ts}] {message}"
    batch_status["logs"].append(entry)


def make_result_entry(desc, t, prompt_text, final_positive, final_negative, width, height, *, url=None, local_path=None, status="success", duration=0):
    return {
        "name": desc, "type": t, "prompt": prompt_text,
        "positive": final_positive, "negative": final_negative,
        "width": width, "height": height,
        "url": url, "local_path": local_path,
        "status": status, "review_status": "pending",
        "duration": duration
    }


# --- Global State ---
_INITIAL_STATUS = {
    "is_running": False,
    "cancel_requested": False,
    "finish_status": None,
    "total": 0, "completed": 0, "succeeded": 0,
    "warnings": 0, "errors": 0,
    "current_item": "",
    "logs": [], "results": [],
    "timing": {"batch_start": None, "image_durations": [], "current_start": None}
}

batch_status = dict(_INITIAL_STATUS)


def reset_batch_status():
    batch_status.update({
        **{k: ([] if isinstance(v, list) else v) for k, v in _INITIAL_STATUS.items()},
        "is_running": True,
        "logs": [], "results": [],
        "timing": {"batch_start": time.time(), "image_durations": [], "current_start": None}
    })


# --- Wildcard Processing ---
def process_wildcards(text):
    def replace(match):
        options = match.group(1).split('|')
        return random.choice(options).strip()
    while '{' in text and '}' in text:
        text = re.sub(r'\{([^{}]*)\}', replace, text)
    return text


# --- Aspect Ratio Mapping ---
ASPECT_RATIOS = {
    "16:9": (1216, 832), "9:16": (832, 1216),
    "1:1": (1024, 1024), "4:3": (1152, 896),
    "3:4": (896, 1152), "21:9": (1536, 640),
    "16:10": (1216, 768), "2:3": (832, 1248),
    "3:2": (1248, 832),
}

# Workflow Node IDs
NODE_KSAMPLER = "3"
NODE_POSITIVE = "6"
NODE_NEGATIVE = "7"
NODE_LATENT = "13"
NODE_UNET = "16"
NODE_VAE = "17"
NODE_CLIP = "18"


# --- Static Files ---
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")


# --- Routes ---
@app.get("/")
async def read_index():
    return FileResponse("index.html")


@app.get("/api/health")
async def health_check():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"http://{COMFYUI_SERVER_ADDRESS}/system_stats",
                timeout=aiohttp.ClientTimeout(total=3)
            ) as resp:
                if resp.status == 200:
                    return {"status": "ok", "comfyui": True}
    except Exception:
        pass
    return {"status": "ok", "comfyui": False}


@app.get("/api/prompts/files")
async def list_prompt_files():
    files = [f for f in os.listdir(PROMPTS_DIR) if f.endswith('.csv')]
    return {"files": files}


@app.get("/api/prompts/content")
async def get_prompt_content(filename: str = "thumbnail-prompts.csv"):
    if not validate_filename(filename):
        return {"error": "Invalid filename", "prompts": []}
    path = os.path.join(PROMPTS_DIR, filename)
    if not os.path.exists(path):
        return {"error": "File not found", "prompts": []}
    try:
        df = pd.read_csv(path)
        if 'desc_ko' not in df.columns or 'prompt' not in df.columns:
            return {"error": "Invalid CSV format (Missing desc_ko or prompt columns)", "prompts": []}
        prompts = df.to_dict(orient="records")
        for i, p in enumerate(prompts):
            p['id'] = i
        return {"filename": filename, "prompts": prompts}
    except Exception as e:
        return {"error": str(e), "prompts": []}


@app.post("/api/prompts/save")
async def save_prompts(filename: str = Form(...), content: str = Form(...)):
    if not validate_filename(filename):
        return JSONResponse(status_code=400, content={"error": "Invalid filename"})
    path = os.path.join(PROMPTS_DIR, filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"status": "saved"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/batch/status")
async def get_batch_status_route():
    return batch_status


@app.post("/api/batch/cancel")
async def cancel_batch():
    if not batch_status["is_running"]:
        return {"status": "not_running"}
    batch_status["cancel_requested"] = True
    add_log("Cancel requested — stopping after current image...", "warning")
    return {"status": "cancelling"}


@app.post("/api/results/{index}/review")
async def review_result(index: int, body: dict):
    if index < 0 or index >= len(batch_status["results"]):
        raise HTTPException(status_code=404, detail="Result not found")
    review_status = body.get("status", "pending")
    if review_status not in ("approved", "rejected", "pending"):
        raise HTTPException(status_code=400, detail="Invalid status")
    batch_status["results"][index]["review_status"] = review_status
    return {"status": "updated", "index": index, "review_status": review_status}


# --- Model Discovery ---
async def discover_models(session):
    def pick_best(options, preferred_names, partial_keywords=None):
        partial_keywords = partial_keywords or []
        lowered = [o for o in options if isinstance(o, str)]
        for preferred in preferred_names:
            for option in lowered:
                if option.lower() == preferred.lower():
                    return option
        for keyword in partial_keywords:
            for option in lowered:
                if keyword.lower() in option.lower():
                    return option
        return None

    # Parallel model info requests
    unet_coro = session.get(f"http://{COMFYUI_SERVER_ADDRESS}/object_info/UNETLoader")
    clip_coro = session.get(f"http://{COMFYUI_SERVER_ADDRESS}/object_info/CLIPLoader")
    vae_coro = session.get(f"http://{COMFYUI_SERVER_ADDRESS}/object_info/VAELoader")

    async with unet_coro as r1, clip_coro as r2, vae_coro as r3:
        unet_info, clip_info, vae_info = await r1.json(), await r2.json(), await r3.json()

    available_unets = unet_info.get("UNETLoader", {}).get("input", {}).get("required", {}).get("unet_name", [[]])[0]
    available_clips = clip_info.get("CLIPLoader", {}).get("input", {}).get("required", {}).get("clip_name", [[]])[0]
    available_vaes = vae_info.get("VAELoader", {}).get("input", {}).get("required", {}).get("vae_name", [[]])[0]

    found_unet = pick_best(available_unets, ["z_image_turbo_bf16.safetensors"], ["z_image_turbo"])
    found_clip = pick_best(available_clips, ["qwen_3_4b.safetensors"], ["qwen_3_4b"])
    found_vae = pick_best(available_vaes, ["ae.safetensors"], ["ae"])

    results = {"UNET": found_unet, "CLIP": found_clip, "VAE": found_vae}
    missing = [k for k, v in results.items() if not v]
    if missing:
        raise RuntimeError(f"Missing model components: {', '.join(missing)}")

    return found_unet, found_clip, found_vae


# --- Generation Config ---
@dataclass
class GenConfig:
    workflow_template: dict
    style_prompt: str
    negative_prompt: str
    target_unet: str
    target_clip: str
    target_vae: str
    steps: int
    global_aspect_ratio: str


# --- Core Generation ---
async def generate_single_image(session, config: GenConfig, prompt_text, desc, t, row, batch_idx=0):
    """Generate a single image. Returns (success: bool, result_entry: dict)"""
    start_time = time.time()

    workflow = json.loads(json.dumps(config.workflow_template))

    # Steps
    if NODE_KSAMPLER in workflow:
        workflow[NODE_KSAMPLER]["inputs"]["steps"] = config.steps

    # Aspect ratio
    ar_str = str(row.get('aspect_ratio', '')).strip()
    if not ar_str or ar_str.lower() == "nan" or ar_str == "None":
        ar_str = config.global_aspect_ratio
    width, height = ASPECT_RATIOS.get(ar_str, (1024, 1024))
    if t == "thumb":
        width //= 2
        height //= 2

    # Models
    if NODE_UNET in workflow:
        workflow[NODE_UNET]["inputs"]["unet_name"] = config.target_unet
    if NODE_CLIP in workflow:
        workflow[NODE_CLIP]["inputs"]["clip_name"] = config.target_clip
    if NODE_VAE in workflow:
        workflow[NODE_VAE]["inputs"]["vae_name"] = config.target_vae

    # Dimensions
    workflow[NODE_LATENT]["inputs"]["width"] = width
    workflow[NODE_LATENT]["inputs"]["height"] = height

    # Prompts
    raw_positive = f"{prompt_text}, {row.get('extra_positive', '')}, {config.style_prompt}"
    raw_negative = f"{config.negative_prompt}, {row.get('extra_negative', '')}"
    final_positive = process_wildcards(raw_positive)
    final_negative = process_wildcards(raw_negative)
    workflow[NODE_POSITIVE]["inputs"]["text"] = final_positive
    workflow[NODE_NEGATIVE]["inputs"]["text"] = final_negative

    # Seed
    try:
        custom_seed = int(row.get('seed', 0))
        workflow[NODE_KSAMPLER]["inputs"]["seed"] = custom_seed if custom_seed > 0 else uuid.uuid4().int >> 96
    except (ValueError, TypeError):
        workflow[NODE_KSAMPLER]["inputs"]["seed"] = uuid.uuid4().int >> 96

    # Submit to ComfyUI
    p = {"prompt": workflow, "client_id": CLIENT_ID}
    async with session.post(f"http://{COMFYUI_SERVER_ADDRESS}/prompt", json=p) as resp:
        result = await resp.json()
        if 'prompt_id' not in result:
            error_msg = result.get('node_errors', result.get('error', 'Unknown ComfyUI Error'))
            add_log(f"ComfyUI error for {desc} ({t}): {error_msg}", "error")
            return False, make_result_entry(desc, t, prompt_text, final_positive, final_negative, width, height, status="error")
        prompt_id = result['prompt_id']

    # Dynamic timeout
    durations = batch_status["timing"]["image_durations"]
    if not durations:
        timeout_seconds = 300
    else:
        avg = sum(durations) / len(durations)
        timeout_seconds = max(60, int(avg * 3))

    # Poll for completion
    poll_start = time.time()
    while (time.time() - poll_start) < timeout_seconds:
        if batch_status["cancel_requested"]:
            break
        async with session.get(f"http://{COMFYUI_SERVER_ADDRESS}/history/{prompt_id}") as h_resp:
            history = await h_resp.json()
            if prompt_id in history:
                outputs = history[prompt_id]['outputs']
                img_info = None
                for node_id in outputs:
                    if 'images' in outputs[node_id]:
                        img_info = outputs[node_id]['images'][0]
                        break
                if not img_info:
                    add_log(f"No image output for {desc} ({t})", "warning")
                    break

                img_url = f"http://{COMFYUI_SERVER_ADDRESS}/view?filename={img_info['filename']}&subfolder={img_info['subfolder']}&type={img_info['type']}"
                sub_dir = os.path.join(OUTPUT_DIR, "kemi", t)
                os.makedirs(sub_dir, exist_ok=True)
                safe_name = prompt_text.replace(' ', '_')[:50]
                short_id = str(uuid.uuid4())[:8]
                file_name = f"{safe_name}_{t}_{short_id}.png"
                save_path = os.path.join(sub_dir, file_name)
                async with session.get(img_url) as img_resp:
                    img_content = await img_resp.read()
                    with open(save_path, "wb") as f_save:
                        f_save.write(img_content)

                duration = time.time() - start_time
                durations.append(duration)
                add_log(f"Completed {desc} ({t}) in {duration:.1f}s", "success")
                return True, make_result_entry(
                    desc, t, prompt_text, final_positive, final_negative, width, height,
                    url=f"/outputs/kemi/{t}/{file_name}", local_path=save_path,
                    status="success", duration=duration
                )
        await asyncio.sleep(1)

    # Timeout
    duration = time.time() - start_time
    add_log(f"Timeout ({timeout_seconds}s) for {desc} ({t}) — skipping", "warning")
    return False, make_result_entry(desc, t, prompt_text, final_positive, final_negative, width, height, status="timeout", duration=duration)


# --- Batch Runner ---
async def run_kemi_batch(selected_prompts, types, style_prompt="", negative_prompt="", global_aspect_ratio="16:9", batch_count=1, steps=20):
    reset_batch_status()
    add_log("Starting batch generation...")

    try:
        with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
            workflow_template = json.load(f)

        batch_status["total"] = len(selected_prompts) * len(types) * batch_count

        async with aiohttp.ClientSession() as session:
            try:
                target_unet, target_clip, target_vae = await discover_models(session)
            except Exception as e:
                add_log(f"Model check failed: {str(e)}", "error")
                batch_status["errors"] += 1
                return

            add_log(f"Using UNET: {target_unet}")
            add_log(f"Using CLIP: {target_clip}")
            add_log(f"Using VAE: {target_vae}")

            config = GenConfig(
                workflow_template=workflow_template,
                style_prompt=style_prompt, negative_prompt=negative_prompt,
                target_unet=target_unet, target_clip=target_clip, target_vae=target_vae,
                steps=steps, global_aspect_ratio=global_aspect_ratio
            )

            for row in selected_prompts:
                if batch_status["cancel_requested"]:
                    add_log("Batch cancelled by user.", "warning")
                    break
                for t in types:
                    if batch_status["cancel_requested"]:
                        break
                    for i in range(batch_count):
                        if batch_status["cancel_requested"]:
                            break
                        desc = row.get('desc_ko', 'Unknown')
                        suffix = f" #{i+1}" if batch_count > 1 else ""
                        batch_status["current_item"] = f"{desc} ({t}){suffix}"
                        add_log(f"Generating {t}: {desc}{suffix}")

                        success, result_entry = await generate_single_image(
                            session, config, row.get('prompt', ''), desc, t, row, i
                        )

                        batch_status["results"].append(result_entry)
                        batch_status["completed"] += 1
                        if success:
                            batch_status["succeeded"] += 1
                        elif result_entry["status"] == "timeout":
                            batch_status["warnings"] += 1
                        else:
                            batch_status["errors"] += 1

    except Exception as e:
        add_log(f"Fatal error: {str(e)}", "error")
        batch_status["errors"] += 1
    finally:
        batch_status["is_running"] = False
        if batch_status["cancel_requested"]:
            batch_status["finish_status"] = "cancelled"
        elif batch_status["errors"] > 0:
            batch_status["finish_status"] = "error"
        elif batch_status["warnings"] > 0:
            batch_status["finish_status"] = "partial"
        else:
            batch_status["finish_status"] = "success"

        s = batch_status["succeeded"]
        t = batch_status["total"]
        batch_status["current_item"] = f"Finished — {s}/{t} succeeded"
        add_log(f"Batch complete: {s}/{t} succeeded, {batch_status['warnings']} warnings, {batch_status['errors']} errors")


# --- Pydantic Models ---
from pydantic import BaseModel

class StartBatchRequest(BaseModel):
    prompts: List[Dict]
    types: List[str] = ["thumb", "hero"]
    style_prompt: str = ""
    negative_prompt: str = ""
    global_aspect_ratio: str = "16:9"
    batch_count: int = 1
    steps: int = 20


@app.post("/api/batch/start")
async def start_batch(background_tasks: BackgroundTasks, req: StartBatchRequest):
    if batch_status["is_running"]:
        raise HTTPException(status_code=400, detail="Batch already running")
    background_tasks.add_task(
        run_kemi_batch, req.prompts, req.types, req.style_prompt,
        req.negative_prompt, req.global_aspect_ratio, req.batch_count, req.steps
    )
    return {"status": "started"}


# --- R2 Upload ---
@app.post("/api/upload")
async def upload_to_r2():
    try:
        s3 = boto3.client(
            's3',
            endpoint_url=f"https://{os.getenv('CLOUDFLARE_ACCOUNT_ID')}.r2.cloudflarestorage.com",
            aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'),
            config=Config(signature_version='s3v4'),
            region_name='auto'
        )
        bucket_name = os.getenv('R2_BUCKET_NAME')
        mappings = {}

        for root, _, files in os.walk(os.path.join(OUTPUT_DIR, "kemi")):
            for file in files:
                if file.endswith(('.png', '.webp')):
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, OUTPUT_DIR).replace("\\", "/")
                    content_type = 'image/webp' if file.endswith('.webp') else 'image/png'
                    await asyncio.to_thread(
                        s3.upload_file, file_path, bucket_name, rel_path,
                        ExtraArgs={'ContentType': content_type}
                    )
                    mappings[file] = f"https://{bucket_name}.r2.dev/{rel_path}"

        return {"status": "success", "mappings": mappings}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
