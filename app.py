import json
import uuid
import urllib.request
import urllib.parse
import asyncio
import os
import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
import aiohttp
from typing import List, Dict
import boto3
from botocore.config import Config
from dotenv import load_dotenv
import logging

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

if not os.path.exists(PROMPTS_DIR): os.makedirs(PROMPTS_DIR)

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# Global State for Batch Progress
batch_status = {
    "is_running": False,
    "total": 0,
    "completed": 0,
    "current_item": "",
    "logs": [],
    "results": []
}

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")

@app.get("/")
async def read_index():
    return FileResponse("index.html")

@app.get("/api/prompts/files")
async def list_prompt_files():
    files = [f for f in os.listdir(PROMPTS_DIR) if f.endswith('.csv')]
    return {"files": files}

@app.get("/api/prompts/content")
async def get_prompt_content(filename: str = "thumbnail-prompts.csv"):
    path = os.path.join(PROMPTS_DIR, filename)
    if not os.path.exists(path):
        return {"error": "File not found", "prompts": []}
    try:
        df = pd.read_csv(path)
        # Ensure required columns exist
        if 'desc_ko' not in df.columns or 'prompt' not in df.columns:
            return {"error": "Invalid CSV format (Missing desc_ko or prompt columns)", "prompts": []}
        
        # Add index-based ID for selection
        prompts = df.to_dict(orient="records")
        for i, p in enumerate(prompts):
            p['id'] = i
        return {"filename": filename, "prompts": prompts}
    except Exception as e:
        return {"error": str(e), "prompts": []}

@app.post("/api/prompts/save")
async def save_prompts(filename: str = Form(...), content: str = Form(...)): # Content expects CSV string
    path = os.path.join(PROMPTS_DIR, filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"status": "saved"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/batch/status")
async def get_batch_status():
    return batch_status

async def run_kemi_batch(selected_prompts: List[Dict], types: List[str], style_prompt: str = "", negative_prompt: str = "", global_aspect_ratio: str = "16:9", batch_count: int = 1, steps: int = 20):
    global batch_status
    batch_status["is_running"] = True
    batch_status["completed"] = 0
    batch_status["logs"] = ["🚀 Starting batch generation..."]
    batch_status["results"] = []

    try:
        with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
            workflow_template = json.load(f)

        batch_status["total"] = len(selected_prompts) * len(types)
        
        # 1. Find the best matching Z-Turbo model
        target_model = "z-image-turbo.safetensors"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"http://{COMFYUI_SERVER_ADDRESS}/object_info/CheckpointLoaderSimple") as obj_resp:
                    obj_info = await obj_resp.json()
                    available_ckpts = obj_info.get('CheckpointLoaderSimple', {}).get('input', {}).get('required', {}).get('ckpt_name', [[]])[0]
                    for ckpt in available_ckpts:
                        if "z_image_turbo" in ckpt.lower() or "z-image-turbo" in ckpt.lower():
                            target_model = ckpt
                            break
            except Exception as e:
                batch_status["logs"].append(f"⚠️ Warning: Failed to fetch models, defaulting to {target_model}")

        batch_status["logs"].append(f"🤖 Using model: {target_model}")

        # 2. Iterate and Generate
        async with aiohttp.ClientSession() as session:
            for row in selected_prompts:
                for t in types:
                    for i in range(batch_count):
                        desc = row.get('desc_ko', 'Unknown')
                        suffix = f" #{i+1}" if batch_count > 1 else ""
                        batch_status["current_item"] = f"{desc} ({t}){suffix}"
                        batch_status["logs"].append(f"🖌️ Generating {t}: {desc}{suffix}")
                        
                        prompt_text = row.get('prompt', '')
                        
                        # Customize Workflow
                        workflow = json.loads(json.dumps(workflow_template))
                        
                        # Apply Steps (Node 13 often SamplerCustom or KSampler)
                        if "13" in workflow and "inputs" in workflow["13"]:
                            workflow["13"]["inputs"]["steps"] = steps
                    
                    # Determine Dimensions
                    ar_str = str(row.get('aspect_ratio', '')).strip()
                    if not ar_str or ar_str.lower() == "nan" or ar_str == "None":
                        ar_str = global_aspect_ratio
                        
                    width = 512 if t == "thumb" else 1024
                    height = 512
                    
                    if ar_str == "16:9":
                        width, height = 1216, 832  # Standard Landscape
                    elif ar_str == "9:16":
                        width, height = 832, 1216  # Standard Portrait
                    elif ar_str == "1:1":
                        width, height = 1024, 1024 # Square
                    elif ar_str == "4:3":
                        width, height = 1152, 896  # Classic Photo
                    elif ar_str == "3:4":
                        width, height = 896, 1152  # Classic Portrait
                    elif ar_str == "21:9":
                        width, height = 1536, 640  # Ultrawide Cinematic
                    elif ar_str == "16:10":
                        width, height = 1216, 768  # Laptop / Tablet
                    elif ar_str == "2:3":
                        width, height = 832, 1248  # Poster / Mobile
                    elif ar_str == "3:2":
                        width, height = 1248, 832  # DSLR Photo
                        
                    if t == "thumb": width //= 2; height //= 2
                    
                    workflow["3"]["inputs"]["ckpt_name"] = target_model 
                    workflow["5"]["inputs"]["width"] = width
                    workflow["5"]["inputs"]["height"] = height
                    
                    # Wildcard Processing Helper
                    def process_wildcards(text):
                        import re
                        import random
                        def replace(match):
                            options = match.group(1).split('|')
                            return random.choice(options).strip()
                        # Process nested/multiple brackets: recursively or iteratively
                        # Simple implementation for single level {a|b|c}
                        while '{' in text and '}' in text:
                            text = re.sub(r'\{([^{}]*)\}', replace, text)
                        return text

                    # Construct Prompt (Subject First for better adherence)
                    # Structure: Main Prompt + Extra Positive + Style + LoRA triggers?
                    raw_positive = f"{prompt_text}, {row.get('extra_positive', '')}, {style_prompt}"
                    raw_negative = f"{negative_prompt}, {row.get('extra_negative', '')}"
                    
                    final_positive = process_wildcards(raw_positive)
                    final_negative = process_wildcards(raw_negative)
                    
                    workflow["6"]["inputs"]["text"] = final_positive
                    workflow["7"]["inputs"]["text"] = final_negative
                    
                    # Seed Handling
                    try:
                        custom_seed = int(row.get('seed', 0))
                        workflow["13"]["inputs"]["seed"] = custom_seed if custom_seed > 0 else uuid.uuid4().int >> 96
                    except:
                        workflow["13"]["inputs"]["seed"] = uuid.uuid4().int >> 96

                    # Queue to ComfyUI
                    p = {"prompt": workflow, "client_id": CLIENT_ID}
                    async with session.post(f"http://{COMFYUI_SERVER_ADDRESS}/prompt", json=p) as resp:
                        result = await resp.json()
                        if 'prompt_id' not in result:
                            error_msg = result.get('node_errors', result.get('error', 'Unknown ComfyUI Error'))
                            batch_status["logs"].append(f"❌ ComfyUI Error: {error_msg}")
                            continue
                        prompt_id = result['prompt_id']

                    # Wait for completion (Timeout 120s)
                    for _ in range(120):
                        async with session.get(f"http://{COMFYUI_SERVER_ADDRESS}/history/{prompt_id}") as h_resp:
                            history = await h_resp.json()
                            if prompt_id in history:
                                outputs = history[prompt_id]['outputs']
                                # Find first node with images
                                img_info = None
                                for node_id in outputs:
                                    if 'images' in outputs[node_id]:
                                        img_info = outputs[node_id]['images'][0]
                                        break
                                
                                if not img_info:
                                    batch_status["logs"].append(f"⚠️ Warning: No images found (History: {str(history)})")
                                    break

                                img_url = f"http://{COMFYUI_SERVER_ADDRESS}/view?filename={img_info['filename']}&subfolder={img_info['subfolder']}&type={img_info['type']}"
                                
                                # Download and save locally
                                sub_dir = os.path.join(OUTPUT_DIR, "kemi", t)
                                if not os.path.exists(sub_dir): os.makedirs(sub_dir)
                                
                                safe_name = prompt_text.replace(' ', '_')[:50]
                                file_name = f"{safe_name}_{t}.png" 
                                save_path = os.path.join(sub_dir, file_name)
                                
                                async with session.get(img_url) as img_resp:
                                    content = await img_resp.read()
                                    with open(save_path, "wb") as f_save:
                                        f_save.write(content)
                                
                                batch_status["results"].append({
                                    "name": desc,
                                    "type": t,
                                    "url": f"/outputs/kemi/{t}/{file_name}",
                                    "local_path": save_path
                                })
                                break
                        await asyncio.sleep(1)
                    
                    batch_status["completed"] += 1
                
    except Exception as e:
        batch_status["logs"].append(f"❌ Error: {str(e)}")
    finally:
        batch_status["is_running"] = False
        batch_status["current_item"] = "Finished"

from pydantic import BaseModel

class StartBatchRequest(BaseModel):
    prompts: List[Dict]
    types: List[str] = ["thumb", "hero"]
    style_prompt: str = "cute kawaii flat illustration, bright pastel colors, soft rounded shapes"
    negative_prompt: str = "text, watermark, ugly, blurry, nsfw, dark, scary, realistic photo"
    global_aspect_ratio: str = "16:9"
    batch_count: int = 1
    steps: int = 20

@app.post("/api/batch/start")
async def start_batch(background_tasks: BackgroundTasks, req: StartBatchRequest):
    if batch_status["is_running"]:
        raise HTTPException(status_code=400, detail="Batch already running")
    background_tasks.add_task(run_kemi_batch, req.prompts, req.types, req.style_prompt, req.negative_prompt, req.global_aspect_ratio, req.batch_count, req.steps)
    return {"status": "started"}

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
                    key = f"{rel_path}"
                    
                    s3.upload_file(file_path, bucket_name, key, ExtraArgs={'ContentType': 'image/png'})
                    mappings[file] = f"https://{bucket_name}.r2.dev/{key}"
        
        return {"status": "success", "mappings": mappings}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
