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


def make_result_entry(desc, t, prompt_text, final_positive, final_negative, width, height, *, url=None, local_path=None, status="success", duration=0, row=None):
    entry = {
        "name": desc, "type": t, "prompt": prompt_text,
        "positive": final_positive, "negative": final_negative,
        "width": width, "height": height,
        "url": url, "local_path": local_path,
        "status": status, "review_status": "pending",
        "duration": duration
    }
    if row:
        for key in ("_source_id", "_subject_key", "_result_index", "_category", "_target_crops"):
            if key in row:
                entry[key] = row[key]
    return entry


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
    files = [f for f in os.listdir(PROMPTS_DIR) if f.endswith(('.csv', '.json'))]
    return {"files": files}


@app.get("/api/prompts/content")
async def get_prompt_content(filename: str = "thumbnail-prompts.csv"):
    if not validate_filename(filename):
        return {"error": "Invalid filename", "prompts": []}
    filepath = os.path.join(PROMPTS_DIR, filename)
    if not os.path.exists(filepath):
        return {"error": "File not found", "prompts": []}
    try:
        if filename.endswith('.json'):
            return _load_json_prompts(filepath, filename)
        df = pd.read_csv(filepath)
        if 'desc_ko' not in df.columns or 'prompt' not in df.columns:
            return {"error": "Invalid CSV format (Missing desc_ko or prompt columns)", "prompts": []}
        df = df.fillna('')
        prompts = df.to_dict(orient="records")
        for i, p in enumerate(prompts):
            p['id'] = i
        return {"filename": filename, "prompts": prompts}
    except Exception as e:
        return {"error": str(e), "prompts": []}


def _load_json_prompts(filepath: str, filename: str):
    """prompts.json (extract-prompts.ts 출력) → CSV 호환 형식으로 변환"""
    with open(filepath, "r", encoding="utf-8") as f:
        items = json.load(f)
    prompts = []
    for i, item in enumerate(items):
        prompts.append({
            "id": i,
            "desc_ko": item.get("name", ""),
            "prompt": item.get("prompt", ""),
            "aspect_ratio": "1:1",
            "extra_positive": item.get("style", ""),
            "extra_negative": "",
            "seed": "",
            "_source_id": item.get("id", ""),
            "_subject_key": item.get("subjectKey", ""),
            "_result_index": item.get("resultIndex", 0),
            "_category": item.get("category", ""),
            "_target_crops": item.get("targetCrops", []),
        })
    return {"filename": filename, "prompts": prompts, "source": "json"}


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
            return False, make_result_entry(desc, t, prompt_text, final_positive, final_negative, width, height, status="error", row=row)
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
                safe_name = re.sub(r'[<>:"/\\|?*]', '', prompt_text).replace(' ', '_')[:50]
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
                    status="success", duration=duration, row=row
                )
        await asyncio.sleep(1)

    # Timeout
    duration = time.time() - start_time
    add_log(f"Timeout ({timeout_seconds}s) for {desc} ({t}) — skipping", "warning")
    return False, make_result_entry(desc, t, prompt_text, final_positive, final_negative, width, height, status="timeout", duration=duration, row=row)


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


# --- Crop ---
PROJECTS_DIR = os.path.join(BASE_DIR, "projects")

@app.post("/api/crop")
async def crop_images(project: str = "mbti"):
    """생성된 1024x1024 이미지를 프로젝트 설정의 크롭 비율로 자동 크롭"""
    project_path = os.path.join(PROJECTS_DIR, f"{project}.json")
    if not os.path.exists(project_path):
        return JSONResponse(status_code=404, content={"error": f"Project config not found: {project}"})

    with open(project_path, "r", encoding="utf-8") as f:
        project_config = json.load(f)

    crops = project_config.get("crops", {})
    if not crops:
        return {"error": "No crops defined in project config"}

    results = batch_status.get("results", [])
    successful = [r for r in results if r.get("status") == "success" and r.get("local_path")]
    if not successful:
        return {"error": "No successful images to crop"}

    cropped = []
    try:
        from PIL import Image

        crop_output_dir = os.path.join(OUTPUT_DIR, "kemi", "cropped")
        os.makedirs(crop_output_dir, exist_ok=True)

        for result in successful:
            src_path = result["local_path"]
            if not os.path.exists(src_path):
                continue

            img = Image.open(src_path)
            w, h = img.size
            base_name = os.path.splitext(os.path.basename(src_path))[0]

            result_crops = {}
            # _target_crops가 있으면 해당 크롭만, 없으면 전체
            target_crops = result.get("_target_crops") or list(crops.keys())

            for crop_name in target_crops:
                if crop_name not in crops:
                    continue
                spec = crops[crop_name]
                tw, th = spec["width"], spec["height"]
                target_ratio = tw / th

                # 중앙 기준 크롭
                current_ratio = w / h
                if current_ratio > target_ratio:
                    new_w = int(h * target_ratio)
                    left = (w - new_w) // 2
                    box = (left, 0, left + new_w, h)
                else:
                    new_h = int(w / target_ratio)
                    top = (h - new_h) // 2
                    box = (0, top, w, top + new_h)

                cropped_img = img.crop(box).resize((tw, th), Image.LANCZOS)

                out_name = f"{base_name}_{crop_name}.webp"
                out_path = os.path.join(crop_output_dir, out_name)
                cropped_img.save(out_path, "WEBP", quality=85)

                # R2 키 생성: _category(breeds/dogs) + 결과명 기반
                category = result.get("_category", "misc")
                safe_result_name = re.sub(r'[<>:"/\\|?*\s]', '-', result.get("name", "unknown")).lower().strip('-')
                r2_key = f"{category}/{safe_result_name}_{crop_name}.webp"

                result_crops[crop_name] = {
                    "path": out_path,
                    "localUrl": f"/outputs/kemi/cropped/{out_name}",
                    "r2Key": r2_key,
                    "url": f"/api/images/{r2_key}",
                    "width": tw,
                    "height": th,
                }

            if result_crops:
                result["_crops"] = result_crops
                cropped.append({"name": result["name"], "crops": list(result_crops.keys())})

        add_log(f"Cropped {len(cropped)} images into {sum(len(c['crops']) for c in cropped)} variants", "success")
        return {"status": "success", "cropped": cropped}

    except ImportError:
        return JSONResponse(status_code=500, content={"error": "Pillow not installed. Run: pip install Pillow"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# --- Manifest ---
@app.get("/api/manifest")
async def get_manifest(project: str = "mbti"):
    """생성+크롭 완료된 이미지 목록을 manifest.json 형태로 반환"""
    results = batch_status.get("results", [])
    successful = [r for r in results if r.get("status") == "success"]

    items = []
    for r in successful:
        assets = []
        crops = r.get("_crops", {})
        for crop_name, crop_info in crops.items():
            assets.append({
                "cropType": crop_name,
                "r2Key": crop_info.get("r2Key", ""),
                "url": crop_info["url"],
                "width": crop_info["width"],
                "height": crop_info["height"],
            })

        items.append({
            "contentId": r.get("_source_id", f"{r['name']}-{r['type']}"),
            "subjectKey": r.get("_subject_key", ""),
            "resultIndex": r.get("_result_index", 0),
            "assetType": r.get("type", ""),
            "name": r["name"],
            "status": r.get("review_status", "pending"),
            "originalPath": r.get("local_path", ""),
            "originalUrl": r.get("url", ""),
            "assets": assets,
        })

    manifest = {
        "generatedAt": datetime.now().isoformat(),
        "project": project,
        "totalImages": len(items),
        "items": items,
    }

    # 파일로도 저장
    manifest_path = os.path.join(OUTPUT_DIR, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return manifest


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
        uploaded = 0

        # 크롭된 이미지를 R2 키 기반으로 업로드
        results = batch_status.get("results", [])
        for result in results:
            crops = result.get("_crops", {})
            for crop_name, crop_info in crops.items():
                local_path = crop_info.get("path", "")
                r2_key = crop_info.get("r2Key", "")
                if not local_path or not r2_key or not os.path.exists(local_path):
                    continue
                content_type = 'image/webp' if local_path.endswith('.webp') else 'image/png'
                await asyncio.to_thread(
                    s3.upload_file, local_path, bucket_name, r2_key,
                    ExtraArgs={'ContentType': content_type}
                )
                mappings[r2_key] = f"/api/images/{r2_key}"
                uploaded += 1

        add_log(f"Uploaded {uploaded} images to R2", "success")
        return {"status": "success", "mappings": mappings, "uploaded": uploaded}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
