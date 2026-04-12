import copy
import json
import uuid
import asyncio
import base64
import os
import re
import random
import shutil
import threading
import time
from datetime import datetime
import pandas as pd
from fastapi import FastAPI, Form, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
import aiohttp
from typing import List, Dict, Any, Optional, Tuple
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
PROJECTS_DIR = os.path.join(BASE_DIR, "projects")
TEMPLATES_DIR = os.path.join(PROJECTS_DIR, "templates")

os.makedirs(PROMPTS_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(PROJECTS_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)

SUPPORTED_PROVIDERS = {"comfyui", "api-image"}
RUN_STORE_LOCK = threading.RLock()
START_BATCH_LOCK = threading.Lock()


# --- Helpers ---
def validate_filename(filename: str) -> bool:
    return '..' not in filename and '/' not in filename and '\\' not in filename


def validate_relative_path(path: str) -> bool:
    if not path:
        return True
    normalized = path.replace("\\", "/")
    if normalized.startswith("/") or ":" in normalized:
        return False
    return ".." not in normalized.split("/")


def add_log(message, level="info"):
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = {"warning": "WARN", "error": "ERROR", "success": "OK"}.get(level, "")
    entry = f"[{ts}] {prefix} {message}" if prefix else f"[{ts}] {message}"
    batch_status["logs"].append(entry)


def resolve_project_output_dir(project: str) -> str:
    if not validate_filename(project):
        raise HTTPException(status_code=400, detail="Invalid project")
    path = os.path.join(OUTPUT_DIR, project)
    os.makedirs(path, exist_ok=True)
    return path


def resolve_runs_dir(project: str) -> str:
    path = os.path.join(resolve_project_output_dir(project), "runs")
    os.makedirs(path, exist_ok=True)
    return path


def resolve_run_dir(project: str, run_id: str) -> str:
    if not validate_filename(run_id):
        raise HTTPException(status_code=400, detail="Invalid run id")
    path = os.path.join(resolve_runs_dir(project), run_id)
    os.makedirs(path, exist_ok=True)
    return path


def resolve_run_file(project: str, run_id: str) -> str:
    return os.path.join(resolve_run_dir(project, run_id), "run.json")


def _legacy_kemi_project() -> Dict[str, Any]:
    return {
        "id": "kemi",
        "name": "Kemi (Legacy)",
        "sourceDir": os.path.join(BASE_DIR, "kemi"),
        "promptsDir": PROMPTS_DIR,
        "defaultPromptFile": "thumbnail-prompts.csv",
        "referenceAssetsDir": "",
        "crops": {},
        "generation": {
            "aspectRatio": "16:9",
            "style": "",
        },
        "provider": "comfyui",
        "supportedProviders": ["comfyui", "api-image"],
        "workflowMode": "prompt-first",
        "capabilities": {
            "supportsReferenceAssets": False,
        },
        "referencePolicy": {
            "requiredSlots": [],
            "recommendedSlots": [],
            "singleSelectSlots": [],
            "libraryPresets": [],
            "temporaryRoot": "temp",
        },
    }


def load_project_config(project: str = "kemi") -> Dict[str, Any]:
    if project == "kemi":
        return _legacy_kemi_project()

    project_path = os.path.join(PROJECTS_DIR, f"{project}.json")
    if not os.path.exists(project_path):
        raise FileNotFoundError(f"Project config not found: {project}")

    with open(project_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    prompts_file = data.get("promptsFile", "")
    prompts_dir = os.path.dirname(prompts_file) if prompts_file else PROMPTS_DIR
    default_prompt_file = os.path.basename(prompts_file) if prompts_file else ""

    return {
        "id": project,
        "name": data.get("name", project),
        "sourceDir": data.get("sourceDir", ""),
        "promptsDir": prompts_dir,
        "defaultPromptFile": default_prompt_file,
        "referenceAssetsDir": data.get("referenceAssetsDir", ""),
        "crops": data.get("crops", {}),
        "generation": data.get("generation", {}),
        "provider": data.get("provider", "comfyui"),
        "supportedProviders": data.get("supportedProviders", [data.get("provider", "comfyui")]),
        "workflowMode": data.get("workflowMode", "prompt-first"),
        "capabilities": data.get("capabilities", {"supportsReferenceAssets": False}),
        "referencePolicy": data.get("referencePolicy", {
            "requiredSlots": [],
            "recommendedSlots": [],
            "singleSelectSlots": [],
            "libraryPresets": [],
            "temporaryRoot": "temp",
        }),
    }


def list_projects() -> List[Dict[str, Any]]:
    projects: List[Dict[str, Any]] = [_legacy_kemi_project()]
    for filename in sorted(os.listdir(PROJECTS_DIR)):
        if not filename.endswith(".json"):
            continue
        project_id = os.path.splitext(filename)[0]
        try:
            projects.append(load_project_config(project_id))
        except Exception as exc:
            logger.warning("Failed to load project config %s: %s", filename, exc)
    return projects


def serialize_project_descriptor(config: Dict[str, Any]) -> Dict[str, Any]:
    provider_id = str(config.get("provider", "comfyui") or "comfyui").strip().lower()
    provider_info = get_provider_descriptor(provider_id) if provider_id in PROVIDER_REGISTRY else {
        "id": provider_id,
        "label": provider_id,
        "description": "",
        "capabilities": {},
    }
    supported_provider_ids = []
    for item in config.get("supportedProviders", [provider_id]) or [provider_id]:
        value = str(item or "").strip().lower()
        if value and value not in supported_provider_ids:
            supported_provider_ids.append(value)
    return {
        "id": config["id"],
        "name": config["name"],
        "sourceDir": config.get("sourceDir", ""),
        "defaultPromptFile": config.get("defaultPromptFile", ""),
        "referenceAssetsDir": config.get("referenceAssetsDir", ""),
        "generation": config.get("generation", {}),
        "provider": provider_id,
        "providerInfo": provider_info,
        "supportedProviders": supported_provider_ids,
        "supportedProviderInfo": [
            get_provider_descriptor(item) if item in PROVIDER_REGISTRY else {
                "id": item,
                "label": item,
                "description": "",
                "capabilities": {},
            }
            for item in supported_provider_ids
        ],
        "workflowMode": config.get("workflowMode", "prompt-first"),
        "capabilities": config.get("capabilities", {"supportsReferenceAssets": False}),
        "effectiveCapabilities": build_effective_project_capabilities(config, provider_id),
        "referencePolicy": config.get("referencePolicy", {}),
    }


def resolve_prompts_dir(project: str) -> str:
    config = load_project_config(project)
    prompts_dir = config["promptsDir"]
    os.makedirs(prompts_dir, exist_ok=True)
    return prompts_dir


def resolve_reference_assets_dir(project: str) -> str:
    config = load_project_config(project)
    explicit_dir = config.get("referenceAssetsDir", "")
    if explicit_dir:
        assets_dir = explicit_dir
    else:
        source_dir = config.get("sourceDir") or BASE_DIR
        assets_dir = os.path.join(source_dir, "scripts", "image-gen", "reference-assets")
    os.makedirs(assets_dir, exist_ok=True)
    return assets_dir


def resolve_reference_asset_path(project: str, relative_path: str) -> str:
    if not validate_relative_path(relative_path):
        raise HTTPException(status_code=400, detail="Invalid asset path")
    root_dir = resolve_reference_assets_dir(project)
    full_path = os.path.normpath(os.path.join(root_dir, relative_path))
    if os.path.commonpath([root_dir, full_path]) != os.path.normpath(root_dir):
        raise HTTPException(status_code=400, detail="Invalid asset path")
    return full_path


def resolve_template_store_path(project: str) -> str:
    if not validate_filename(project):
        raise HTTPException(status_code=400, detail="Invalid project")
    return os.path.join(TEMPLATES_DIR, f"{project}.json")


def load_project_templates(project: str) -> List[Dict[str, Any]]:
    path = resolve_template_store_path(project)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    templates = payload.get("templates", [])
    if not isinstance(templates, list):
        return []
    normalized: List[Dict[str, Any]] = []
    for item in templates:
        if not isinstance(item, dict):
            continue
        scene_draft = item.get("sceneDraft")
        if not isinstance(scene_draft, dict):
            scene_draft = {}
        if not any(scene_draft.values()):
            legacy_scene_draft = (item.get("meta") or {}).get("sceneDraft", {})
            if isinstance(legacy_scene_draft, dict):
                scene_draft = legacy_scene_draft
        item = dict(item)
        item["sceneDraft"] = {
            "situation": str(scene_draft.get("situation", "") or "").strip(),
            "interaction": str(scene_draft.get("interaction", "") or "").strip(),
            "background": str(scene_draft.get("background", "") or "").strip(),
            "location": str(scene_draft.get("location", "") or "").strip(),
            "lighting": str(scene_draft.get("lighting", "") or "").strip(),
        }
        normalized.append(item)
    return normalized


def save_project_templates(project: str, templates: List[Dict[str, Any]]) -> None:
    path = resolve_template_store_path(project)
    write_json_atomic(path, {
        "project": project,
        "updatedAt": datetime.now().isoformat(),
        "templates": templates,
    })


def normalize_template_reference_paths(paths: List[str]) -> List[str]:
    normalized: List[str] = []
    seen = set()
    for path in paths or []:
        if not isinstance(path, str):
            continue
        cleaned = path.replace("\\", "/").strip().strip("/")
        if not cleaned or not validate_relative_path(cleaned) or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


REFERENCE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def build_reference_asset_entry(project: str, root_dir: str, full_path: str) -> Dict[str, Any]:
    rel_path = os.path.relpath(full_path, root_dir).replace("\\", "/")
    filename = os.path.basename(full_path)
    base_name, ext = os.path.splitext(filename)
    parts = rel_path.split("/")
    family = parts[0] if parts else "misc"
    character = ""
    section = "misc"
    if family == "characters" and len(parts) >= 4:
        character = parts[1]
        section = parts[2]
    elif len(parts) >= 2:
        section = parts[-2]
    elif parts:
        section = parts[0]
    group = "/".join(parts[:-1]) if len(parts) > 1 else ""
    slot_map = {
        "base": "identity",
        "emotion": "emotion",
        "emotions": "emotion",
        "role": "role",
        "roles": "role",
        "scene": "scene",
        "scenes": "scene",
        "style": "style",
        "styles": "style",
        "prop": "prop",
        "props": "prop",
    }
    slot = slot_map.get(section, "extra")
    is_temporary = family in ("temp", "temporary") or rel_path.startswith("temp/") or rel_path.startswith("temporary/")
    return {
        "id": rel_path,
        "relativePath": rel_path,
        "name": base_name,
        "filename": filename,
        "extension": ext.lower(),
        "family": family,
        "character": character,
        "section": section,
        "slot": slot,
        "group": group,
        "isTemporary": is_temporary,
        "previewUrl": f"/api/reference-assets/file?project={project}&asset={rel_path}",
    }


def make_result_entry(desc, t, prompt_text, final_positive, final_negative, width, height, *, url=None, local_path=None, status="success", duration=0, row=None):
    entry = {
        "name": desc, "type": t, "prompt": prompt_text,
        "positive": final_positive, "negative": final_negative,
        "width": width, "height": height,
        "url": url, "local_path": local_path,
        "status": status, "review_status": "pending", "review_note": "",
        "duration": duration
    }
    if row:
        for key in ("_source_id", "_subject_key", "_result_index", "_category", "_target_crops", "_project", "_reference_assets"):
            if key in row:
                entry[key] = row[key]
    return entry


def summarize_reference_assets(reference_assets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    summary: List[Dict[str, Any]] = []
    for asset in reference_assets or []:
        if not isinstance(asset, dict):
            continue
        summary.append({
            "id": asset.get("id") or asset.get("relativePath", ""),
            "relativePath": asset.get("relativePath", ""),
            "name": asset.get("name", ""),
            "slot": asset.get("slot", ""),
            "character": asset.get("character", ""),
        })
    return summary


def summarize_prompt_rows(prompts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    summary: List[Dict[str, Any]] = []
    for item in prompts or []:
        if not isinstance(item, dict):
            continue
        summary.append({
            "desc_ko": item.get("desc_ko", ""),
            "prompt": item.get("prompt", ""),
            "aspect_ratio": item.get("aspect_ratio", ""),
            "source_id": item.get("_source_id", ""),
        })
    return summary


def model_to_dict(model: Any) -> Dict[str, Any]:
    if model is None:
        return {}
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def write_json_atomic(path: str, payload: Dict[str, Any]) -> None:
    temp_path = f"{path}.{uuid.uuid4().hex}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


# --- Global State ---
_INITIAL_STATUS = {
    "run_id": None,
    "project": "kemi",
    "mode": "direct",
    "provider_id": "comfyui",
    "request": {},
    "reference_assets": [],
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


def restore_idle_batch_status() -> None:
    batch_status.clear()
    batch_status.update({
        **{k: ([] if isinstance(v, list) else v) for k, v in _INITIAL_STATUS.items()},
        "timing": {"batch_start": None, "image_durations": [], "current_start": None},
    })


def reset_batch_status():
    batch_status.update({
        **{k: ([] if isinstance(v, list) else v) for k, v in _INITIAL_STATUS.items()},
        "run_id": None,
        "project": "kemi",
        "mode": "direct",
        "provider_id": "comfyui",
        "request": {},
        "reference_assets": [],
        "is_running": True,
        "logs": [], "results": [],
        "timing": {"batch_start": time.time(), "image_durations": [], "current_start": None}
    })


def claim_batch_start(
    project: str,
    run_id: str,
    mode: str,
    provider_id: str,
    request_summary: Dict[str, Any],
    reference_assets: List[Dict[str, Any]],
) -> None:
    with START_BATCH_LOCK:
        if batch_status["is_running"]:
            raise HTTPException(status_code=400, detail="Batch already running")
        batch_status.update({
            **{k: ([] if isinstance(v, list) else v) for k, v in _INITIAL_STATUS.items()},
            "run_id": run_id,
            "project": project,
            "mode": mode,
            "provider_id": provider_id,
            "request": request_summary,
            "reference_assets": reference_assets,
            "is_running": True,
            "cancel_requested": False,
            "finish_status": None,
            "logs": [],
            "results": [],
            "current_item": "Queued",
            "timing": {"batch_start": None, "image_durations": [], "current_start": None},
        })


def build_run_record(status_source: Optional[Dict[str, Any]] = None, include_lineage_in_handoff: bool = True) -> Dict[str, Any]:
    status_source = status_source or batch_status
    record = {
        "runId": status_source.get("run_id"),
        "projectId": status_source.get("project"),
        "mode": status_source.get("mode", "direct"),
        "providerId": status_source.get("provider_id", "comfyui"),
        "request": status_source.get("request", {}),
        "status": {
            "is_running": status_source.get("is_running", False),
            "cancel_requested": status_source.get("cancel_requested", False),
            "finish_status": status_source.get("finish_status"),
            "total": status_source.get("total", 0),
            "completed": status_source.get("completed", 0),
            "succeeded": status_source.get("succeeded", 0),
            "warnings": status_source.get("warnings", 0),
            "errors": status_source.get("errors", 0),
            "current_item": status_source.get("current_item", ""),
        },
        "referenceAssets": summarize_reference_assets(status_source.get("reference_assets", [])),
        "results": status_source.get("results", []),
        "logs": status_source.get("logs", []),
        "timing": status_source.get("timing", {}),
        "updatedAt": datetime.now().isoformat(),
    }
    record["codexHandoff"] = build_codex_handoff_snapshot(record, include_lineage=include_lineage_in_handoff)
    return record


def persist_current_run(status_source: Optional[Dict[str, Any]] = None, include_lineage_in_handoff: bool = True) -> None:
    status_source = status_source or batch_status
    run_id = status_source.get("run_id")
    project = status_source.get("project")
    if not run_id or not project:
        return
    path = resolve_run_file(project, run_id)
    record = build_run_record(status_source=status_source, include_lineage_in_handoff=include_lineage_in_handoff)
    with RUN_STORE_LOCK:
        created_at = None
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                    created_at = existing.get("createdAt")
            except Exception:
                created_at = None
        record["createdAt"] = created_at or datetime.now().isoformat()
        write_json_atomic(path, record)


def create_initial_run_record(project: str, run_id: str, mode: str, provider_id: str, request_summary: Dict[str, Any], reference_assets: List[Dict[str, Any]]) -> None:
    path = resolve_run_file(project, run_id)
    now = datetime.now().isoformat()
    record = {
        "runId": run_id,
        "projectId": project,
        "mode": mode,
        "providerId": provider_id,
        "request": request_summary,
        "status": {
            "is_running": False,
            "cancel_requested": False,
            "finish_status": "queued",
            "total": 0,
            "completed": 0,
            "succeeded": 0,
            "warnings": 0,
            "errors": 0,
            "current_item": "Queued",
        },
        "referenceAssets": summarize_reference_assets(reference_assets),
        "results": [],
        "logs": [],
        "timing": {"batch_start": None, "image_durations": [], "current_start": None},
        "createdAt": now,
        "updatedAt": now,
    }
    record["codexHandoff"] = build_codex_handoff_snapshot(record, include_lineage=True)
    with RUN_STORE_LOCK:
        write_json_atomic(path, record)


def save_run_record(project: str, run_id: str, record: Dict[str, Any], include_lineage_in_handoff: bool = True) -> None:
    path = resolve_run_file(project, run_id)
    with RUN_STORE_LOCK:
        existing_created_at = record.get("createdAt")
        if os.path.exists(path) and not existing_created_at:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing_created_at = json.load(f).get("createdAt")
            except Exception:
                existing_created_at = None
        record["createdAt"] = existing_created_at or datetime.now().isoformat()
        record["updatedAt"] = datetime.now().isoformat()
        record["codexHandoff"] = build_codex_handoff_snapshot(record, include_lineage=include_lineage_in_handoff)
        write_json_atomic(path, record)


def load_run_record(project: str, run_id: str) -> Dict[str, Any]:
    path = resolve_run_file(project, run_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Run not found")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_latest_run_record(project: str) -> Optional[Dict[str, Any]]:
    runs_dir = resolve_runs_dir(project)
    latest_record = None
    latest_key = ""
    for entry in os.listdir(runs_dir):
        path = os.path.join(runs_dir, entry, "run.json")
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                record = json.load(f)
        except Exception:
            continue
        key = record.get("updatedAt", "") or record.get("createdAt", "")
        if key >= latest_key:
            latest_key = key
            latest_record = record
    return latest_record


def list_run_records(project: str, limit: int = 10) -> List[Dict[str, Any]]:
    runs_dir = resolve_runs_dir(project)
    records: List[Dict[str, Any]] = []
    for entry in os.listdir(runs_dir):
        path = os.path.join(runs_dir, entry, "run.json")
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                record = json.load(f)
        except Exception:
            continue
        records.append(record)
    records.sort(key=lambda item: item.get("updatedAt", "") or item.get("createdAt", ""), reverse=True)
    return records[:max(1, min(limit, 5000))]


def get_run_retry_info(record: Dict[str, Any]) -> Dict[str, Any]:
    request = record.get("request", {}) or {}
    metadata = request.get("metadata", {}) or {}
    from_run_id = str(metadata.get("retry_from_run_id") or metadata.get("retryFromRunId") or "").strip()
    source = str(metadata.get("retry_source") or metadata.get("retrySource") or "").strip()
    return {
        "isRetry": bool(from_run_id),
        "fromRunId": from_run_id or None,
        "source": source or None,
    }


def summarize_run_record(record: Dict[str, Any]) -> Dict[str, Any]:
    request = record.get("request", {}) or {}
    status = record.get("status", {}) or {}
    scene_spec = request.get("sceneSpec") or {}
    scene = scene_spec.get("scene") or {}
    retry = get_run_retry_info(record)
    review_summary = build_run_review_summary(record)
    return {
        "runId": record.get("runId"),
        "projectId": record.get("projectId"),
        "mode": record.get("mode", "direct"),
        "providerId": record.get("providerId", "comfyui"),
        "templateId": request.get("templateId"),
        "promptCount": len(request.get("prompts") or []),
        "referenceCount": len(record.get("referenceAssets") or []),
        "outputTypes": request.get("outputTypes") or [],
        "finishStatus": status.get("finish_status"),
        "isRunning": status.get("is_running", False),
        "completed": status.get("completed", 0),
        "total": status.get("total", 0),
        "succeeded": status.get("succeeded", 0),
        "createdAt": record.get("createdAt"),
        "updatedAt": record.get("updatedAt"),
        "sceneSummary": scene.get("situation") or scene.get("background") or "",
        "retry": retry,
        "reviewSummary": review_summary,
    }


def compute_run_quality_score(summary: Dict[str, Any]) -> float:
    review = summary.get("reviewSummary", {}) or {}
    total = int(summary.get("total", 0) or 0)
    succeeded = int(summary.get("succeeded", 0) or 0)
    success_rate = (succeeded / total) if total > 0 else 0.0
    return (
        float(review.get("approved", 0) or 0) * 3.0
        - float(review.get("rejected", 0) or 0) * 3.0
        + float(review.get("noted", 0) or 0) * 0.5
        + success_rate
    )


def compare_run_summaries(parent_summary: Dict[str, Any], child_summary: Dict[str, Any]) -> Dict[str, Any]:
    parent_review = parent_summary.get("reviewSummary", {}) or {}
    child_review = child_summary.get("reviewSummary", {}) or {}
    approved_delta = int(child_review.get("approved", 0) or 0) - int(parent_review.get("approved", 0) or 0)
    rejected_delta = int(child_review.get("rejected", 0) or 0) - int(parent_review.get("rejected", 0) or 0)
    noted_delta = int(child_review.get("noted", 0) or 0) - int(parent_review.get("noted", 0) or 0)
    success_delta = int(child_summary.get("succeeded", 0) or 0) - int(parent_summary.get("succeeded", 0) or 0)
    score_delta = round(compute_run_quality_score(child_summary) - compute_run_quality_score(parent_summary), 2)

    if score_delta > 0.5:
        label = "improved"
    elif score_delta < -0.5:
        label = "worse"
    else:
        label = "unchanged"

    summary_bits: List[str] = []
    if approved_delta > 0:
        summary_bits.append("more approved outputs")
    if rejected_delta < 0:
        summary_bits.append("fewer rejected outputs")
    if success_delta > 0:
        summary_bits.append("more successful renders")
    if label == "worse" and not summary_bits:
        if rejected_delta > 0:
            summary_bits.append("more rejected outputs")
        if success_delta < 0:
            summary_bits.append("fewer successful renders")
    if not summary_bits:
        summary_bits.append("review totals stayed close to the previous run")

    return {
        "label": label,
        "scoreDelta": score_delta,
        "summary": ", ".join(summary_bits),
        "deltas": {
            "approved": approved_delta,
            "rejected": rejected_delta,
            "noted": noted_delta,
            "succeeded": success_delta,
        },
    }


def summarize_run_request_changes(parent_record: Dict[str, Any], child_record: Dict[str, Any]) -> Dict[str, Any]:
    parent_request = parent_record.get("request", {}) or {}
    child_request = child_record.get("request", {}) or {}
    parent_scene = (parent_request.get("sceneSpec") or {}).get("scene") or {}
    child_scene = (child_request.get("sceneSpec") or {}).get("scene") or {}
    parent_visual = (parent_request.get("sceneSpec") or {}).get("visual") or {}
    child_visual = (child_request.get("sceneSpec") or {}).get("visual") or {}
    parent_generation = parent_request.get("generationParams") or {}
    child_generation = child_request.get("generationParams") or {}

    changes: List[Dict[str, str]] = []

    def add_change(field: str, before: Any, after: Any, label: str) -> None:
        before_text = str(before or "").strip()
        after_text = str(after or "").strip()
        if before_text == after_text:
            return
        if before_text and after_text:
            detail = f"{label}: {before_text} -> {after_text}"
        elif after_text:
            detail = f"{label}: added {after_text}"
        else:
            detail = f"{label}: removed"
        changes.append({
            "field": field,
            "label": label,
            "detail": detail,
        })

    add_change("templateId", parent_request.get("templateId"), child_request.get("templateId"), "template")
    add_change("scene.situation", parent_scene.get("situation"), child_scene.get("situation"), "situation")
    add_change("scene.interaction", parent_scene.get("interaction"), child_scene.get("interaction"), "interaction")
    add_change("scene.background", parent_scene.get("background"), child_scene.get("background"), "background")
    add_change("scene.location", parent_scene.get("location"), child_scene.get("location"), "location")
    add_change("visual.lighting", parent_visual.get("lighting"), child_visual.get("lighting"), "lighting")
    add_change("stylePrompt", parent_generation.get("extraPositive"), child_generation.get("extraPositive"), "style prompt")
    add_change("negativePrompt", parent_generation.get("negativePrompt"), child_generation.get("negativePrompt"), "negative prompt")
    add_change("aspectRatio", parent_generation.get("aspectRatio"), child_generation.get("aspectRatio"), "aspect ratio")
    add_change("steps", parent_generation.get("steps"), child_generation.get("steps"), "steps")
    add_change("batchCount", parent_generation.get("batchCount"), child_generation.get("batchCount"), "repeat")

    parent_refs = [
        str(item.get("path") or item.get("relativePath") or item.get("name") or "").strip()
        for item in (parent_record.get("referenceAssets") or [])
    ]
    child_refs = [
        str(item.get("path") or item.get("relativePath") or item.get("name") or "").strip()
        for item in (child_record.get("referenceAssets") or [])
    ]
    parent_ref_set = {item for item in parent_refs if item}
    child_ref_set = {item for item in child_refs if item}
    added_refs = sorted(child_ref_set - parent_ref_set)
    removed_refs = sorted(parent_ref_set - child_ref_set)
    if added_refs:
        changes.append({
            "field": "referenceAssets.added",
            "label": "references",
            "detail": "added refs: " + ", ".join(added_refs[:3]),
        })
    if removed_refs:
        changes.append({
            "field": "referenceAssets.removed",
            "label": "references",
            "detail": "removed refs: " + ", ".join(removed_refs[:3]),
        })

    parent_prompts = [str(item.get("prompt", "") or "").strip() for item in (parent_request.get("prompts") or []) if str(item.get("prompt", "") or "").strip()]
    child_prompts = [str(item.get("prompt", "") or "").strip() for item in (child_request.get("prompts") or []) if str(item.get("prompt", "") or "").strip()]
    if parent_prompts != child_prompts:
        if not parent_prompts and child_prompts:
            prompt_detail = "prompts added"
        elif parent_prompts and not child_prompts:
            prompt_detail = "prompts removed"
        else:
            prompt_detail = "prompts changed"
        changes.append({
            "field": "prompts",
            "label": "prompts",
            "detail": prompt_detail,
        })

    return {
        "count": len(changes),
        "summary": ", ".join(item["detail"] for item in changes[:4]) if changes else "No request changes detected.",
        "items": changes[:8],
    }


def build_run_lineage(project: str, run_id: str, limit: int = 1000) -> Dict[str, Any]:
    records = list_run_records(project, limit=limit)
    records_by_id: Dict[str, Dict[str, Any]] = {}
    for record in records:
        record_id = str(record.get("runId") or "").strip()
        if record_id:
            records_by_id[record_id] = record

    if run_id not in records_by_id:
        record = load_run_record(project, run_id)
        records_by_id[run_id] = record

    summaries_by_id = {
        record_id: summarize_run_record(record)
        for record_id, record in records_by_id.items()
    }

    children_by_parent: Dict[str, List[str]] = {}
    for record_id, record in records_by_id.items():
        parent_id = get_run_retry_info(record).get("fromRunId")
        if parent_id:
            children_by_parent.setdefault(parent_id, []).append(record_id)

    root_id = run_id
    visited_parents = set()
    current_id = run_id
    while current_id and current_id not in visited_parents:
        visited_parents.add(current_id)
        parent_id = (summaries_by_id.get(current_id, {}).get("retry", {}) or {}).get("fromRunId")
        if not parent_id or parent_id not in summaries_by_id:
            root_id = current_id
            break
        root_id = parent_id
        current_id = parent_id

    current_path = set()
    current_id = run_id
    while current_id and current_id not in current_path:
        current_path.add(current_id)
        parent_id = (summaries_by_id.get(current_id, {}).get("retry", {}) or {}).get("fromRunId")
        if not parent_id or parent_id not in summaries_by_id:
            break
        current_id = parent_id

    def sort_key(record_id: str) -> str:
        summary = summaries_by_id.get(record_id, {}) or {}
        return str(summary.get("createdAt") or summary.get("updatedAt") or "")

    items: List[Dict[str, Any]] = []
    visited = set()

    def visit(record_id: str, depth: int) -> None:
        if record_id in visited or record_id not in summaries_by_id:
            return
        visited.add(record_id)
        base = dict(summaries_by_id[record_id])
        retry = dict(base.get("retry", {}) or {})
        child_ids = sorted(children_by_parent.get(record_id, []), key=sort_key)
        retry["childCount"] = len(child_ids)
        base["retry"] = retry
        base["depth"] = depth
        base["isCurrent"] = record_id == run_id
        base["isOnCurrentPath"] = record_id in current_path
        parent_id = retry.get("fromRunId")
        base["comparisonToParent"] = (
            compare_run_summaries(summaries_by_id[parent_id], base)
            if parent_id and parent_id in summaries_by_id
            else None
        )
        base["changesFromParent"] = (
            summarize_run_request_changes(records_by_id[parent_id], records_by_id[record_id])
            if parent_id and parent_id in records_by_id
            else None
        )
        items.append(base)
        for child_id in child_ids:
            visit(child_id, depth + 1)

    visit(root_id, 0)
    if run_id not in visited:
        visit(run_id, 0)

    return {
        "project": project,
        "currentRunId": run_id,
        "rootRunId": root_id,
        "runCount": len(items),
        "hasRetries": any(
            (item.get("retry", {}) or {}).get("isRetry")
            or int((item.get("retry", {}) or {}).get("childCount", 0) or 0) > 0
            for item in items
        ),
        "items": items,
    }


def build_transient_run_lineage(project: str, record: Dict[str, Any]) -> Dict[str, Any]:
    run_id = str(record.get("runId") or "").strip()
    retry_info = get_run_retry_info(record)
    items: List[Dict[str, Any]] = []
    parent_id = retry_info.get("fromRunId")
    if parent_id:
        try:
            parent_record = load_run_record(project, parent_id)
            parent_summary = summarize_run_record(parent_record)
            parent_summary["depth"] = 0
            parent_summary["isCurrent"] = False
            items.append(parent_summary)
        except HTTPException:
            pass

    current_summary = summarize_run_record(record)
    current_summary["depth"] = len(items)
    current_summary["isCurrent"] = True
    items.append(current_summary)

    return {
        "project": project,
        "currentRunId": run_id,
        "rootRunId": parent_id or run_id,
        "runCount": len(items),
        "hasRetries": bool(retry_info.get("isRetry")) or len(items) > 1,
        "items": items,
    }


def collect_run_review_notes(record: Dict[str, Any]) -> List[Dict[str, str]]:
    notes: List[Dict[str, str]] = []
    for item in record.get("results") or []:
        note = str(item.get("review_note", "") or "").strip()
        if not note:
            continue
        notes.append({
            "status": str(item.get("review_status", "pending") or "pending"),
            "type": str(item.get("type", "") or ""),
            "name": str(item.get("name", "") or ""),
            "note": note,
        })
    return notes


def build_run_review_summary(record: Dict[str, Any]) -> Dict[str, Any]:
    results = record.get("results") or []
    approved = sum(1 for item in results if item.get("review_status") == "approved")
    rejected = sum(1 for item in results if item.get("review_status") == "rejected")
    pending = sum(1 for item in results if item.get("review_status", "pending") == "pending")
    note_highlights: List[str] = []
    for item in results:
        note = str(item.get("review_note", "") or "").strip()
        if note and note not in note_highlights:
            note_highlights.append(note)
        if len(note_highlights) >= 3:
            break
    return {
        "approved": approved,
        "rejected": rejected,
        "pending": pending,
        "noted": sum(1 for item in results if str(item.get("review_note", "") or "").strip()),
        "noteHighlights": note_highlights,
    }


def dedupe_keep_order(values: List[str]) -> List[str]:
    output: List[str] = []
    seen = set()
    for value in values:
        cleaned = (value or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        output.append(cleaned)
    return output


def build_retry_suggestion(record: Dict[str, Any]) -> Dict[str, Any]:
    request = record.get("request", {}) or {}
    scene_spec = request.get("sceneSpec") or {}
    scene = scene_spec.get("scene") or {}
    generation_params = request.get("generationParams") or {}
    review_notes = collect_run_review_notes(record)

    note_text = " ".join(item["note"].lower() for item in review_notes)
    scene_patch = {
        "situation": "",
        "interaction": "",
        "background": "",
        "location": "",
        "lighting": "",
    }
    style_additions: List[str] = []
    negative_additions: List[str] = []
    prompt_hints: List[str] = []

    if "expression" in note_text or "emotion" in note_text or "reaction" in note_text:
        prompt_hints.append("Strengthen facial expression clarity and reaction readability.")
    if "lighting" in note_text or "dark" in note_text or "bright" in note_text or "shadow" in note_text:
        scene_patch["lighting"] = "clear subject lighting, readable face, controlled contrast"
        prompt_hints.append("Adjust lighting so the face and pose read immediately.")
    if "background" in note_text or "bg" in note_text:
        scene_patch["background"] = scene.get("background") or "clean supporting background"
        prompt_hints.append("Keep the background supporting the character action instead of competing with it.")
    if "crop" in note_text or "framing" in note_text or "close-up" in note_text or "wide" in note_text:
        prompt_hints.append("Review framing and subject spacing before re-rendering.")
    if "blur" in note_text or "blurry" in note_text or "sharp" in note_text:
        style_additions.append("sharp focal details, clear face, clean silhouette")
        negative_additions.append("blurry, soft focus, muddy details")
    if "text" in note_text or "letter" in note_text or "watermark" in note_text:
        negative_additions.append("text, letters, watermark, logo")
    if "messy" in note_text or "noise" in note_text or "artifact" in note_text:
        negative_additions.append("messy details, noise, artifacts")
    if "pose" in note_text or "hand" in note_text or "anatomy" in note_text:
        negative_additions.append("broken anatomy, awkward hands, distorted pose")
        prompt_hints.append("Stabilize pose silhouette and hand readability.")
    if "color" in note_text or "tone" in note_text:
        style_additions.append("controlled color palette, cohesive tone")

    rejected_notes = [item["note"] for item in review_notes if item["status"] == "rejected"]
    approved_notes = [item["note"] for item in review_notes if item["status"] == "approved"]
    summary_bits: List[str] = []
    if rejected_notes:
        summary_bits.append(f"Address {len(rejected_notes)} rejected review notes.")
    if approved_notes:
        summary_bits.append(f"Preserve {len(approved_notes)} approved qualities.")
    if not summary_bits:
        summary_bits.append("No review notes yet. Retry suggestions are based on current scene spec only.")

    if not any(scene_patch.values()):
        scene_patch["situation"] = scene.get("situation", "") or ""
        scene_patch["interaction"] = scene.get("interaction", "") or ""
        scene_patch["background"] = scene.get("background", "") or ""
        scene_patch["location"] = scene.get("location", "") or ""
        scene_patch["lighting"] = scene_spec.get("visual", {}).get("lighting", "") or ""

    return {
        "runId": record.get("runId"),
        "projectId": record.get("projectId"),
        "mode": record.get("mode", "direct"),
        "providerId": record.get("providerId", "comfyui"),
        "summary": " ".join(summary_bits),
        "templateId": request.get("templateId"),
        "referenceAssets": record.get("referenceAssets") or [],
        "outputTypes": request.get("outputTypes") or ["thumb", "hero"],
        "sceneSpec": scene_spec,
        "sceneDraftPatch": scene_patch,
        "stylePromptAdditions": dedupe_keep_order(style_additions),
        "negativePromptAdditions": dedupe_keep_order(negative_additions),
        "promptHints": dedupe_keep_order(prompt_hints),
        "sourceNotes": review_notes[:6],
        "baseGeneration": {
            "stylePrompt": generation_params.get("extraPositive", "") or "",
            "negativePrompt": generation_params.get("negativePrompt", "") or "",
            "aspectRatio": generation_params.get("aspectRatio", "") or "",
            "steps": generation_params.get("steps", 20),
            "batchCount": generation_params.get("batchCount", 1),
        },
    }


def build_codex_handoff_payload_from_record(
    project: str,
    record: Dict[str, Any],
    include_retry: bool = True,
    include_lineage: bool = False,
) -> Dict[str, Any]:
    request = record.get("request", {}) or {}
    provider_id = str(record.get("providerId", "comfyui") or "comfyui")
    provider_info = get_provider_descriptor(provider_id)
    scene_spec = request.get("sceneSpec") or {}
    scene = scene_spec.get("scene") or {}
    visual = scene_spec.get("visual") or {}
    review_summary = build_run_review_summary(record)
    review_notes = collect_run_review_notes(record)[:6]
    template_id = request.get("templateId")
    template = next((item for item in load_project_templates(project) if item.get("id") == template_id), None) if template_id else None
    retry_context: Dict[str, Any] = {
        "focusRunId": record.get("runId"),
        "suggestion": None,
        "lineage": None,
    }
    if include_retry:
        suggestion = build_retry_suggestion(record)
        retry_context["suggestion"] = {
            "runId": suggestion.get("runId"),
            "templateId": suggestion.get("templateId"),
            "summary": suggestion.get("summary", ""),
            "sceneDraftPatch": suggestion.get("sceneDraftPatch", {}),
            "promptHints": suggestion.get("promptHints", []),
            "stylePromptAdditions": suggestion.get("stylePromptAdditions", []),
            "negativePromptAdditions": suggestion.get("negativePromptAdditions", []),
            "sourceNotes": suggestion.get("sourceNotes", []),
        }
    if include_lineage:
        try:
            lineage = build_run_lineage(project, str(record.get("runId") or ""))
        except HTTPException:
            lineage = build_transient_run_lineage(project, record)
        items = lineage.get("items") or []
        current_item = next((item for item in items if item.get("isCurrent")), items[-1] if items else None)
        retry_context["lineage"] = {
            "currentRunId": lineage.get("currentRunId"),
            "hasRetries": bool(lineage.get("hasRetries")),
            "runCount": int(lineage.get("runCount", len(items)) or len(items)),
            "latestOutcome": (current_item or {}).get("comparisonToParent", {}) or {},
            "latestChanges": (current_item or {}).get("changesFromParent", {}) or {},
            "latestReviewNotes": ((current_item or {}).get("reviewSummary", {}) or {}).get("noteHighlights", []),
        }

    payload = {
        "handoffVersion": 2,
        "intent": "codex-conversation-image-generation",
        "source": "run-record",
        "project": {
            "id": project,
            "name": load_project_config(project).get("name", project),
            "workflowMode": load_project_config(project).get("workflowMode", "prompt-first"),
        },
        "execution": {
            "generationMode": record.get("mode", "direct"),
            "operatorMode": request.get("operatorMode", "studio"),
            "providerId": provider_id,
            "providerLabel": provider_info.get("label", provider_id),
        },
        "template": {
            "id": template.get("id"),
            "name": template.get("name"),
            "composition": template.get("composition"),
            "description": template.get("description", ""),
        } if template else (
            {
                "id": template_id,
                "name": template_id,
                "composition": "",
                "description": "",
            } if template_id else None
        ),
        "sceneDraft": {
            "situation": scene.get("situation", "") or "",
            "interaction": scene.get("interaction", "") or "",
            "background": scene.get("background", "") or "",
            "location": scene.get("location", "") or "",
            "lighting": visual.get("lighting", "") or "",
        },
        "sceneSpec": scene_spec,
        "selectedPrompts": request.get("prompts") or [],
        "selectedReferences": record.get("referenceAssets") or [],
        "generationParams": {
            "aspectRatio": (request.get("generationParams") or {}).get("aspectRatio", "") or "",
            "steps": (request.get("generationParams") or {}).get("steps", 20),
            "batchCount": (request.get("generationParams") or {}).get("batchCount", 1),
            "outputTypes": request.get("outputTypes") or [],
            "stylePrompt": (request.get("generationParams") or {}).get("extraPositive", "") or "",
            "negativePrompt": (request.get("generationParams") or {}).get("negativePrompt", "") or "",
        },
        "runContext": {
            "runId": record.get("runId"),
            "mode": record.get("mode", "direct"),
            "providerId": provider_id,
            "operatorMode": request.get("operatorMode", "studio"),
            "templateId": template_id,
            "sceneSummary": scene.get("situation") or scene.get("background") or "",
            "reviewSummary": review_summary,
            "reviewNotes": review_notes,
        },
        "retryContext": retry_context,
        "preflight": None,
        "requestPreview": {
            "project": project,
            "mode": record.get("mode", "direct"),
            "provider_id": provider_id,
            "operator_mode": request.get("operatorMode", "studio"),
            "template_id": template_id,
            "scene_spec": scene_spec,
            "prompts": request.get("prompts") or [],
            "reference_assets": record.get("referenceAssets") or [],
            "types": request.get("outputTypes") or [],
            "style_prompt": (request.get("generationParams") or {}).get("extraPositive", "") or "",
            "negative_prompt": (request.get("generationParams") or {}).get("negativePrompt", "") or "",
            "global_aspect_ratio": (request.get("generationParams") or {}).get("aspectRatio", "") or "",
            "batch_count": (request.get("generationParams") or {}).get("batchCount", 1),
            "steps": (request.get("generationParams") or {}).get("steps", 20),
            "metadata": request.get("metadata") or {},
        },
        "codexAsk": (
            "Use this run state and review feedback to refine the next image generation result with stronger consistency, scene clarity, and character accuracy."
            if str(record.get("mode", "direct") or "direct").lower() == "assisted"
            else "Use this direct run state to refine prompts or propose a stronger assisted scene setup before rendering."
        ),
    }
    return payload


def build_codex_handoff_message(payload: Dict[str, Any]) -> str:
    execution = payload.get("execution", {}) or {}
    template = payload.get("template") or None
    run_context = payload.get("runContext", {}) or {}
    retry_context = payload.get("retryContext", {}) or {}
    retry_suggestion = retry_context.get("suggestion", {}) or {}
    retry_lineage = retry_context.get("lineage", {}) or {}
    prompt_count = len(payload.get("selectedPrompts") or [])
    reference_count = len(payload.get("selectedReferences") or [])
    output_types = ", ".join(payload.get("generationParams", {}).get("outputTypes") or []) or "thumb, hero"
    scene_draft = payload.get("sceneDraft", {}) or {}
    scene_spec = payload.get("sceneSpec", {}) or {}
    scene_data = scene_spec.get("scene", {}) or {}
    scene_cue = (
        scene_draft.get("situation")
        or scene_data.get("situation")
        or scene_data.get("background")
        or "none"
    )
    review_summary = run_context.get("reviewSummary", {}) or {}
    review_summary_text = f"A{review_summary.get('approved', 0)} / R{review_summary.get('rejected', 0)} / N{review_summary.get('noted', 0)}"
    review_notes = run_context.get("reviewNotes") or []
    review_notes_text = " | ".join(f"{item.get('status', 'pending')}: {item.get('note', '')}" for item in review_notes) or "none"
    retry_patch = retry_suggestion.get("sceneDraftPatch", {}) or {}
    retry_patch_text = " | ".join(
        f"{key}={value}" for key, value in retry_patch.items() if str(value or "").strip()
    ) or "none"
    retry_hints_text = " | ".join(retry_suggestion.get("promptHints") or []) or "none"
    retry_style_text = " | ".join(retry_suggestion.get("stylePromptAdditions") or []) or "none"
    retry_negative_text = " | ".join(retry_suggestion.get("negativePromptAdditions") or []) or "none"
    retry_lineage_text = "none"
    if retry_lineage:
        latest_outcome = (retry_lineage.get("latestOutcome", {}) or {}).get("label") or "n/a"
        retry_lineage_text = f"{retry_lineage.get('runCount', 0)} runs, latest outcome: {latest_outcome}"
    template_text = "none selected"
    if template:
        template_text = f"{template.get('name')} ({template.get('composition') or 'custom'})"
    lines = [
        "Use the following studio state as the source of truth.",
        f"Project: {payload.get('project', {}).get('name') or payload.get('project', {}).get('id') or 'unknown'}",
        f"Generation mode: {execution.get('generationMode') or 'assisted'}",
        f"Operator mode: {execution.get('operatorMode') or 'codex-conversation'}",
        f"Renderer: {execution.get('providerLabel') or execution.get('providerId') or 'unknown'}",
        f"Template: {template_text}",
        f"Scene cue: {scene_cue}",
        f"Selected prompts: {prompt_count}",
        f"Selected references: {reference_count}",
        f"Outputs: {output_types}",
        f"Run context: {str(run_context.get('runId') or 'none')[:8]} ({run_context.get('mode') or 'unknown'})",
        f"Review summary: {review_summary_text}",
        f"Review notes: {review_notes_text}",
        f"Retry suggestion: {retry_suggestion.get('summary') or 'none'}",
        f"Retry scene patch: {retry_patch_text}",
        f"Retry prompt hints: {retry_hints_text}",
        f"Retry style additions: {retry_style_text}",
        f"Retry negative additions: {retry_negative_text}",
        f"Retry lineage: {retry_lineage_text}",
        "",
        "Task:",
        payload.get("codexAsk") or "Use this state to create or refine the image generation result.",
        "",
        "When you reply, treat the JSON below as the exact handoff payload.",
        "",
        json.dumps(payload, indent=2, ensure_ascii=True),
    ]
    return "\n".join(lines)


def build_codex_handoff_snapshot(
    record: Dict[str, Any],
    include_retry: bool = True,
    include_lineage: bool = False,
) -> Dict[str, Any]:
    project = str(record.get("projectId", "kemi") or "kemi")
    payload = build_codex_handoff_payload_from_record(
        project,
        record,
        include_retry=include_retry,
        include_lineage=include_lineage,
    )
    return {
        "payload": payload,
        "message": build_codex_handoff_message(payload),
        "updatedAt": datetime.now().isoformat(),
    }


def run_record_to_status(record: Dict[str, Any]) -> Dict[str, Any]:
    status = record.get("status", {})
    return {
        "run_id": record.get("runId"),
        "project": record.get("projectId", "kemi"),
        "mode": record.get("mode", "direct"),
        "provider_id": record.get("providerId", "comfyui"),
        "request": record.get("request", {}),
        "reference_assets": record.get("referenceAssets", []),
        "is_running": status.get("is_running", False),
        "cancel_requested": status.get("cancel_requested", False),
        "finish_status": status.get("finish_status"),
        "total": status.get("total", 0),
        "completed": status.get("completed", 0),
        "succeeded": status.get("succeeded", 0),
        "warnings": status.get("warnings", 0),
        "errors": status.get("errors", 0),
        "current_item": status.get("current_item", ""),
        "logs": record.get("logs", []),
        "results": record.get("results", []),
        "timing": record.get("timing", {"batch_start": None, "image_durations": [], "current_start": None}),
    }


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
    provider_statuses: Dict[str, Any] = {}
    overall_ok = True
    for provider_id in sorted(PROVIDER_REGISTRY.keys()):
        try:
            provider_statuses[provider_id] = await get_provider_adapter(provider_id).health_status()
        except Exception as exc:
            overall_ok = False
            provider_statuses[provider_id] = {
                "id": provider_id,
                "label": provider_id,
                "configured": True,
                "available": False,
                "status": "error",
                "reason": str(exc),
            }

    comfyui_ready = bool((provider_statuses.get("comfyui") or {}).get("available"))
    return {
        "status": "ok" if overall_ok else "degraded",
        "comfyui": comfyui_ready,
        "providers": provider_statuses,
    }


@app.get("/api/projects")
async def get_projects():
    projects = list_projects()
    return {
        "providers": list_provider_descriptors(),
        "projects": [serialize_project_descriptor(p) for p in projects]
    }


@app.get("/api/reference-assets")
async def get_reference_assets(project: str = "kemi"):
    config = load_project_config(project)
    root_dir = resolve_reference_assets_dir(project)
    assets: List[Dict[str, Any]] = []
    definition_files: List[Dict[str, Any]] = []

    for dirpath, _, filenames in os.walk(root_dir):
        for filename in sorted(filenames):
            full_path = os.path.join(dirpath, filename)
            ext = os.path.splitext(filename)[1].lower()
            if ext not in REFERENCE_EXTENSIONS:
                if filename in ("manifest.json", "prompt-pack.json"):
                    definition_files.append({
                        "relativePath": os.path.relpath(full_path, root_dir).replace("\\", "/"),
                        "filename": filename,
                    })
                continue
            assets.append(build_reference_asset_entry(project, root_dir, full_path))

    sections: Dict[str, List[Dict[str, Any]]] = {}
    slot_counts: Dict[str, int] = {}
    section_counts: Dict[str, int] = {}
    library_count = 0
    temporary_count = 0
    for asset in assets:
        sections.setdefault(asset["section"], []).append(asset)
        section_counts[asset["section"]] = section_counts.get(asset["section"], 0) + 1
        if asset.get("isTemporary"):
            temporary_count += 1
            continue
        library_count += 1
        slot_counts[asset["slot"]] = slot_counts.get(asset["slot"], 0) + 1

    reference_policy = config.get("referencePolicy", {}) or {}
    required_slots = reference_policy.get("requiredSlots", [])
    recommended_slots = reference_policy.get("recommendedSlots", [])
    slot_status: List[Dict[str, Any]] = []
    seen_slots = set()
    for slot in [*required_slots, *recommended_slots, *sorted(slot_counts.keys())]:
        if slot in seen_slots:
            continue
        seen_slots.add(slot)
        slot_status.append({
            "slot": slot,
            "count": slot_counts.get(slot, 0),
            "required": slot in required_slots,
            "recommended": slot in recommended_slots,
            "filled": slot_counts.get(slot, 0) > 0,
        })

    return {
        "project": project,
        "rootDir": root_dir,
        "assets": assets,
        "sections": sections,
        "definitionFiles": definition_files,
        "referencePolicy": reference_policy,
        "status": {
            "totalAssets": len(assets),
            "libraryAssets": library_count,
            "temporaryAssets": temporary_count,
            "slotCounts": slot_counts,
            "sectionCounts": section_counts,
            "slotStatus": slot_status,
        }
    }


@app.get("/api/reference-assets/file")
async def get_reference_asset_file(project: str = "kemi", asset: str = ""):
    if not asset:
        raise HTTPException(status_code=400, detail="Missing asset path")
    full_path = resolve_reference_asset_path(project, asset)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(full_path)


@app.post("/api/reference-assets/upload")
async def upload_reference_asset(
    project: str = Form(...),
    target_dir: str = Form("misc"),
    file: UploadFile = File(...),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    if not validate_relative_path(target_dir):
        raise HTTPException(status_code=400, detail="Invalid target directory")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in REFERENCE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    root_dir = resolve_reference_assets_dir(project)
    safe_target_dir = target_dir.strip().replace("\\", "/").strip("/")
    destination_dir = resolve_reference_asset_path(project, safe_target_dir) if safe_target_dir else root_dir
    os.makedirs(destination_dir, exist_ok=True)

    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "-", os.path.basename(file.filename))
    safe_name = re.sub(r"-+", "-", safe_name).strip("-") or f"asset{ext}"
    destination_path = os.path.join(destination_dir, safe_name)

    with open(destination_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    return {
        "status": "uploaded",
        "project": project,
        "asset": build_reference_asset_entry(project, root_dir, destination_path),
    }


@app.get("/api/prompts/files")
async def list_prompt_files(project: str = "kemi"):
    prompts_dir = resolve_prompts_dir(project)
    config = load_project_config(project)
    files = [f for f in os.listdir(prompts_dir) if f.endswith(('.csv', '.json'))]
    return {"project": project, "files": files, "defaultFile": config.get("defaultPromptFile", "")}


@app.get("/api/prompts/content")
async def get_prompt_content(filename: str = "thumbnail-prompts.csv", project: str = "kemi"):
    if not validate_filename(filename):
        return {"error": "Invalid filename", "prompts": []}
    filepath = os.path.join(resolve_prompts_dir(project), filename)
    if not os.path.exists(filepath):
        return {"error": "File not found", "prompts": []}
    try:
        if filename.endswith('.json'):
            return _load_json_prompts(filepath, filename, project)
        df = pd.read_csv(filepath)
        if 'desc_ko' not in df.columns or 'prompt' not in df.columns:
            return {"error": "Invalid CSV format (Missing desc_ko or prompt columns)", "prompts": []}
        df = df.fillna('')
        prompts = df.to_dict(orient="records")
        for i, p in enumerate(prompts):
            p['id'] = i
            p['_project'] = project
        return {"project": project, "filename": filename, "prompts": prompts}
    except Exception as e:
        return {"error": str(e), "prompts": []}


def _load_json_prompts(filepath: str, filename: str, project: str):
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
            "_project": item.get("project", "") or project,
        })
    return {"project": project, "filename": filename, "prompts": prompts, "source": "json"}


@app.post("/api/prompts/save")
async def save_prompts(filename: str = Form(...), content: str = Form(...), project: str = Form("kemi")):
    if not validate_filename(filename):
        return JSONResponse(status_code=400, content={"error": "Invalid filename"})
    path = os.path.join(resolve_prompts_dir(project), filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"status": "saved", "project": project}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/batch/status")
async def get_batch_status_route(project: str = "kemi", run_id: str = ""):
    if run_id:
        return run_record_to_status(load_run_record(project, run_id))
    if batch_status.get("is_running") and batch_status.get("run_id") and batch_status.get("project") == project:
        return batch_status
    latest_record = find_latest_run_record(project)
    if latest_record:
        return run_record_to_status(latest_record)
    return {
        **dict(_INITIAL_STATUS),
        "project": project,
    }


@app.get("/api/runs/{run_id}")
async def get_run_status(run_id: str, project: str = "kemi"):
    return load_run_record(project, run_id)


@app.get("/api/runs/{run_id}/retry-suggestion")
async def get_retry_suggestion(run_id: str, project: str = "kemi"):
    record = load_run_record(project, run_id)
    return build_retry_suggestion(record)


@app.get("/api/runs/{run_id}/lineage")
async def get_run_lineage(run_id: str, project: str = "kemi"):
    load_project_config(project)
    return build_run_lineage(project, run_id)


@app.get("/api/runs/{run_id}/codex-handoff")
async def get_run_codex_handoff(run_id: str, project: str = "kemi"):
    load_project_config(project)
    record = load_run_record(project, run_id)
    snapshot = build_codex_handoff_snapshot(record, include_retry=True, include_lineage=True)
    return {
        "project": project,
        "runId": run_id,
        **snapshot,
    }


@app.get("/api/runs")
async def list_runs(project: str = "kemi", limit: int = 10):
    load_project_config(project)
    records = list_run_records(project, limit=limit)
    return {
        "project": project,
        "runs": [summarize_run_record(record) for record in records],
    }


@app.post("/api/batch/cancel")
async def cancel_batch():
    if not batch_status["is_running"]:
        return {"status": "not_running"}
    batch_status["cancel_requested"] = True
    add_log("Cancel requested — stopping after current image...", "warning")
    persist_current_run()
    return {"status": "cancelling"}


@app.post("/api/results/{index}/review")
async def review_result(index: int, body: dict, project: str = "kemi", run_id: str = ""):
    review_status = body.get("status", "pending")
    if review_status not in ("approved", "rejected", "pending"):
        raise HTTPException(status_code=400, detail="Invalid status")
    review_note = str(body.get("note", "") or "").strip()

    if run_id and batch_status.get("run_id") != run_id:
        with RUN_STORE_LOCK:
            record = load_run_record(project, run_id)
            if record.get("projectId") != project:
                raise HTTPException(status_code=400, detail="Run project does not match review project")
            results = record.get("results", [])
            if index < 0 or index >= len(results):
                raise HTTPException(status_code=404, detail="Result not found")
            results[index]["review_status"] = review_status
            results[index]["review_note"] = review_note[:1000]
            record["results"] = results
            save_run_record(project, run_id, record)
        return {
            "status": "updated",
            "index": index,
            "review_status": review_status,
            "review_note": results[index]["review_note"],
        }

    if batch_status.get("project") != project:
        raise HTTPException(status_code=400, detail="Active run project does not match review project")

    if index < 0 or index >= len(batch_status["results"]):
        raise HTTPException(status_code=404, detail="Result not found")
    batch_status["results"][index]["review_status"] = review_status
    batch_status["results"][index]["review_note"] = review_note[:1000]
    persist_current_run()
    return {
        "status": "updated",
        "index": index,
        "review_status": review_status,
        "review_note": batch_status["results"][index]["review_note"],
    }


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
    project: str
    workflow_template: dict
    style_prompt: str
    negative_prompt: str
    target_unet: str
    target_clip: str
    target_vae: str
    steps: int
    global_aspect_ratio: str


@dataclass
class ProviderImageRequest:
    prompt_text: str
    desc: str
    output_type: str
    row: Dict[str, Any]
    batch_idx: int = 0


@dataclass
class ProviderRuntime:
    provider_id: str


@dataclass
class ComfyUIProviderRuntime(ProviderRuntime):
    session: aiohttp.ClientSession
    config: GenConfig


class GenerationProviderAdapter:
    provider_id = "base"
    label = "Base Provider"
    description = ""

    def capabilities(self) -> Dict[str, Any]:
        return {
            "supportsReferenceAssets": False,
            "supportsSceneSpec": False,
            "supportsDirectGeneration": False,
            "supportsAssistedGeneration": False,
            "supportsHealthcheck": False,
        }

    def is_configured(self) -> bool:
        return True

    def configuration_error(self) -> str:
        return ""

    async def health_status(self) -> Dict[str, Any]:
        configured = self.is_configured()
        return {
            "id": self.provider_id,
            "label": getattr(self, "label", self.provider_id),
            "configured": configured,
            "available": configured,
            "status": "ready" if configured else "not-configured",
            "reason": self.configuration_error() if not configured else "",
        }

    async def prepare_runtime(
        self,
        *,
        project: str,
        style_prompt: str,
        negative_prompt: str,
        steps: int,
        global_aspect_ratio: str,
    ) -> ProviderRuntime:
        raise NotImplementedError

    async def generate_single(
        self,
        runtime: ProviderRuntime,
        request: ProviderImageRequest,
    ) -> Tuple[bool, Dict[str, Any]]:
        raise NotImplementedError

    async def close_runtime(self, runtime: ProviderRuntime) -> None:
        return None


def load_comfyui_workflow_template() -> Dict[str, Any]:
    with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class ComfyUIProviderAdapter(GenerationProviderAdapter):
    provider_id = "comfyui"
    label = "ComfyUI"
    description = "Local ComfyUI renderer connected through the workflow API."

    def capabilities(self) -> Dict[str, Any]:
        return {
            "supportsReferenceAssets": False,
            "supportsSceneSpec": True,
            "supportsDirectGeneration": True,
            "supportsAssistedGeneration": True,
            "supportsHealthcheck": True,
        }

    async def health_status(self) -> Dict[str, Any]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://{COMFYUI_SERVER_ADDRESS}/system_stats",
                    timeout=aiohttp.ClientTimeout(total=3),
                ) as resp:
                    if resp.status == 200:
                        return {
                            "id": self.provider_id,
                            "label": self.label,
                            "configured": True,
                            "available": True,
                            "status": "ready",
                            "reason": "",
                        }
        except Exception:
            pass
        return {
            "id": self.provider_id,
            "label": self.label,
            "configured": True,
            "available": False,
            "status": "offline",
            "reason": "ComfyUI server is not reachable.",
        }

    async def prepare_runtime(
        self,
        *,
        project: str,
        style_prompt: str,
        negative_prompt: str,
        steps: int,
        global_aspect_ratio: str,
    ) -> ComfyUIProviderRuntime:
        workflow_template = load_comfyui_workflow_template()
        session = aiohttp.ClientSession()
        try:
            target_unet, target_clip, target_vae = await discover_models(session)
        except Exception:
            await session.close()
            raise

        add_log(f"Using UNET: {target_unet}")
        add_log(f"Using CLIP: {target_clip}")
        add_log(f"Using VAE: {target_vae}")

        return ComfyUIProviderRuntime(
            provider_id=self.provider_id,
            session=session,
            config=GenConfig(
                project=project,
                workflow_template=workflow_template,
                style_prompt=style_prompt,
                negative_prompt=negative_prompt,
                target_unet=target_unet,
                target_clip=target_clip,
                target_vae=target_vae,
                steps=steps,
                global_aspect_ratio=global_aspect_ratio,
            ),
        )

    async def generate_single(
        self,
        runtime: ComfyUIProviderRuntime,
        request: ProviderImageRequest,
    ) -> Tuple[bool, Dict[str, Any]]:
        return await generate_single_image(
            runtime.session,
            runtime.config,
            request.prompt_text,
            request.desc,
            request.output_type,
            request.row,
            request.batch_idx,
        )

    async def close_runtime(self, runtime: ComfyUIProviderRuntime) -> None:
        await runtime.session.close()


@dataclass
class ApiImageProviderRuntime(ProviderRuntime):
    session: aiohttp.ClientSession
    base_url: str
    model: str
    timeout_seconds: int
    style_prompt: str
    negative_prompt: str
    global_aspect_ratio: str
    project: str


class ApiImageProviderAdapter(GenerationProviderAdapter):
    provider_id = "api-image"
    label = "OpenAI Images"
    description = "OpenAI image generation provider using the Images API."

    def capabilities(self) -> Dict[str, Any]:
        return {
            "supportsReferenceAssets": False,
            "supportsSceneSpec": True,
            "supportsDirectGeneration": True,
            "supportsAssistedGeneration": True,
            "supportsHealthcheck": True,
            "supportsDeterministicSeed": False,
        }

    def is_configured(self) -> bool:
        return bool(os.getenv("OPENAI_API_KEY", "").strip())

    def configuration_error(self) -> str:
        if not self.is_configured():
            return "Set OPENAI_API_KEY to enable the OpenAI image provider."
        return ""

    def _base_url(self) -> str:
        return (os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip() or "https://api.openai.com/v1").rstrip("/")

    def _model(self) -> str:
        return (os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1.5").strip() or "gpt-image-1.5")

    async def health_status(self) -> Dict[str, Any]:
        if not self.is_configured():
            return {
                "id": self.provider_id,
                "label": self.label,
                "configured": False,
                "available": False,
                "status": "not-configured",
                "reason": self.configuration_error(),
            }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._base_url()}/models/{self._model()}",
                    timeout=aiohttp.ClientTimeout(total=3),
                    headers=self._build_headers(),
                ) as resp:
                    if resp.status == 200:
                        return {
                            "id": self.provider_id,
                            "label": self.label,
                            "configured": True,
                            "available": True,
                            "status": "ready",
                            "reason": "",
                        }
                    if resp.status in {401, 403}:
                        return {
                            "id": self.provider_id,
                            "label": self.label,
                            "configured": True,
                            "available": False,
                            "status": "auth-error",
                            "reason": "OpenAI API key was rejected while checking the configured image model.",
                        }
                    if resp.status == 404:
                        return {
                            "id": self.provider_id,
                            "label": self.label,
                            "configured": True,
                            "available": False,
                            "status": "model-error",
                            "reason": f"OpenAI model '{self._model()}' is not available for this account.",
                        }
        except Exception:
            pass
        return {
            "id": self.provider_id,
            "label": self.label,
            "configured": True,
            "available": False,
            "status": "offline",
            "reason": "OpenAI image API is not reachable.",
        }

    def _build_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        org_id = os.getenv("OPENAI_ORG_ID", "").strip()
        if org_id:
            headers["OpenAI-Organization"] = org_id
        project_id = os.getenv("OPENAI_PROJECT_ID", "").strip()
        if project_id:
            headers["OpenAI-Project"] = project_id
        return headers

    def _resolve_openai_size(self, aspect_ratio: str) -> Tuple[str, Tuple[int, int]]:
        width, height = ASPECT_RATIOS.get(aspect_ratio, (1024, 1024))
        if width > height:
            return "1536x1024", (1536, 1024)
        if height > width:
            return "1024x1536", (1024, 1536)
        return "1024x1024", (1024, 1024)

    def _compose_openai_prompt(self, runtime: ApiImageProviderRuntime, request: ProviderImageRequest) -> Tuple[str, str]:
        row = request.row or {}
        base_prompt = str(request.prompt_text or "").strip()
        extra_positive = str(row.get("extra_positive", "") or "").strip()
        style_prompt = str(runtime.style_prompt or "").strip()
        negative_prompt = ", ".join([
            str(runtime.negative_prompt or "").strip(),
            str(row.get("extra_negative", "") or "").strip(),
        ]).strip(" ,")
        reference_assets = row.get("_reference_assets", []) or []
        scene_spec = row.get("_scene_spec") or {}
        template_id = str(row.get("_template_id", "") or "").strip()

        prompt_sections = [part for part in [base_prompt, extra_positive, style_prompt] if part]
        if scene_spec:
            scene_context = []
            actors = scene_spec.get("actors") or []
            if actors:
                actor_bits = []
                for actor in actors:
                    if not isinstance(actor, dict):
                        continue
                    segment = ", ".join([str(actor.get(key, "") or "").strip() for key in ("character", "role", "emotion") if str(actor.get(key, "") or "").strip()])
                    if segment:
                        actor_bits.append(segment)
                if actor_bits:
                    scene_context.append("Characters: " + "; ".join(actor_bits))
            scene = scene_spec.get("scene") or {}
            if isinstance(scene, dict):
                scene_bits = [str(scene.get(key, "") or "").strip() for key in ("situation", "interaction", "background", "location")]
                scene_text = ", ".join([value for value in scene_bits if value])
                if scene_text:
                    scene_context.append("Scene: " + scene_text)
            props = scene_spec.get("props") or []
            if props:
                scene_context.append("Props: " + ", ".join([str(item).strip() for item in props if str(item).strip()]))
            visual = scene_spec.get("visual") or {}
            if isinstance(visual, dict):
                visual_bits = [str(visual.get(key, "") or "").strip() for key in ("framing", "camera_distance", "lighting")]
                visual_text = ", ".join([value for value in visual_bits if value])
                if visual_text:
                    scene_context.append("Visuals: " + visual_text)
            styles = scene_spec.get("style") or []
            if styles:
                scene_context.append("Style anchors: " + ", ".join([str(item).strip() for item in styles if str(item).strip()]))
            if scene_context:
                prompt_sections.append("Structured scene context:\n" + "\n".join(scene_context))

        if reference_assets:
            ref_bits = []
            for asset in reference_assets[:8]:
                if not isinstance(asset, dict):
                    continue
                slot = str(asset.get("slot", "") or "").strip()
                name = str(asset.get("name", "") or asset.get("relativePath", "")).strip()
                if name:
                    ref_bits.append(f"{slot or 'reference'}={name}")
            if ref_bits:
                prompt_sections.append("Reference cues: " + "; ".join(ref_bits))

        if template_id:
            prompt_sections.append(f"Template: {template_id}")

        final_prompt = process_wildcards(", ".join([part for part in prompt_sections if part]))
        return final_prompt, negative_prompt

    async def _post_with_retry(self, session: aiohttp.ClientSession, url: str, payload: Dict[str, Any], timeout_seconds: int) -> Dict[str, Any]:
        last_error: Optional[str] = None
        for attempt in range(3):
            try:
                async with session.post(
                    url,
                    json=payload,
                    headers=self._build_headers(),
                    timeout=aiohttp.ClientTimeout(total=timeout_seconds),
                ) as resp:
                    if resp.status in {408, 409, 429, 500, 502, 503, 504} and attempt < 2:
                        last_error = f"HTTP {resp.status}"
                        await asyncio.sleep(1.5 * (attempt + 1))
                        continue
                    data = await resp.json(content_type=None)
                    if resp.status >= 400:
                        error_msg = ""
                        if isinstance(data, dict):
                            if isinstance(data.get("error"), dict):
                                error_msg = str(data.get("error", {}).get("message") or "")
                            else:
                                error_msg = str(data.get("error") or "")
                        raise RuntimeError(error_msg or f"OpenAI image API returned HTTP {resp.status}")
                    return data if isinstance(data, dict) else {}
            except Exception as exc:
                last_error = str(exc)
                if attempt < 2:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(last_error or "OpenAI image API request failed")
        raise RuntimeError(last_error or "OpenAI image API request failed")

    async def prepare_runtime(
        self,
        *,
        project: str,
        style_prompt: str,
        negative_prompt: str,
        steps: int,
        global_aspect_ratio: str,
    ) -> ApiImageProviderRuntime:
        if not self.is_configured():
            raise RuntimeError(self.configuration_error())
        timeout_seconds = int(os.getenv("OPENAI_API_TIMEOUT", os.getenv("IMAGE_API_TIMEOUT", "90")) or "90")
        return ApiImageProviderRuntime(
            provider_id=self.provider_id,
            session=aiohttp.ClientSession(),
            base_url=self._base_url(),
            model=self._model(),
            timeout_seconds=max(15, min(timeout_seconds, 300)),
            style_prompt=style_prompt,
            negative_prompt=negative_prompt,
            global_aspect_ratio=global_aspect_ratio,
            project=project,
        )

    async def generate_single(
        self,
        runtime: ApiImageProviderRuntime,
        request: ProviderImageRequest,
    ) -> Tuple[bool, Dict[str, Any]]:
        start_time = time.time()
        row = request.row or {}
        ar_str = str(row.get("aspect_ratio", "")).strip()
        if not ar_str or ar_str.lower() == "nan" or ar_str == "None":
            ar_str = runtime.global_aspect_ratio
        openai_size, (width, height) = self._resolve_openai_size(ar_str)
        final_positive, final_negative = self._compose_openai_prompt(runtime, request)
        try:
            custom_seed = int(row.get("seed", 0))
            seed = custom_seed if custom_seed > 0 else uuid.uuid4().int >> 96
        except (ValueError, TypeError):
            seed = uuid.uuid4().int >> 96

        prompt_text = final_positive
        if final_negative:
            prompt_text = f"{prompt_text}\nAvoid: {final_negative}"

        payload = {
            "model": runtime.model,
            "prompt": prompt_text,
            "size": openai_size,
        }
        quality = (os.getenv("OPENAI_IMAGE_QUALITY", "auto").strip() or "auto")
        if quality:
            payload["quality"] = quality
        output_format = (os.getenv("OPENAI_IMAGE_FORMAT", "png").strip() or "png")
        if output_format:
            payload["output_format"] = output_format
        background = os.getenv("OPENAI_IMAGE_BACKGROUND", "").strip()
        if background:
            payload["background"] = background
        moderation = os.getenv("OPENAI_IMAGE_MODERATION", "").strip()
        if moderation:
            payload["moderation"] = moderation

        try:
            data = await self._post_with_retry(
                runtime.session,
                f"{runtime.base_url}/images/generations",
                payload,
                runtime.timeout_seconds,
            )
        except Exception as exc:
            add_log(f"OpenAI provider error for {request.desc} ({request.output_type}): {str(exc)}", "error")
            return False, make_result_entry(
                request.desc,
                request.output_type,
                request.prompt_text,
                final_positive,
                final_negative,
                width,
                height,
                status="error",
                row=row,
            )

        image_base64 = ""
        if isinstance(data, dict):
            image_items = data.get("data") or []
            if isinstance(image_items, list) and image_items:
                first_image = image_items[0] or {}
                if isinstance(first_image, dict):
                    image_base64 = str(first_image.get("b64_json") or "").strip()

        sub_dir = os.path.join(OUTPUT_DIR, runtime.project, request.output_type)
        os.makedirs(sub_dir, exist_ok=True)
        safe_name = re.sub(r'[<>:"/\\|?*]', '', request.prompt_text).replace(' ', '_')[:50]
        short_id = str(uuid.uuid4())[:8]
        file_name = f"{safe_name}_{request.output_type}_{short_id}.png"
        save_path = os.path.join(sub_dir, file_name)

        try:
            if image_base64:
                with open(save_path, "wb") as f_save:
                    f_save.write(base64.b64decode(image_base64))
            else:
                raise RuntimeError("OpenAI image response did not include b64_json image data")
        except Exception as exc:
            add_log(f"OpenAI image save failed for {request.desc} ({request.output_type}): {str(exc)}", "error")
            return False, make_result_entry(
                request.desc,
                request.output_type,
                request.prompt_text,
                final_positive,
                final_negative,
                width,
                height,
                status="error",
                row=row,
            )

        duration = time.time() - start_time
        batch_status["timing"]["image_durations"].append(duration)
        add_log(f"Completed {request.desc} ({request.output_type}) in {duration:.1f}s", "success")
        return True, make_result_entry(
            request.desc,
            request.output_type,
            request.prompt_text,
            final_positive,
            final_negative,
            width,
            height,
            url=f"/outputs/{runtime.project}/{request.output_type}/{file_name}",
            local_path=save_path,
            status="success",
            duration=duration,
            row=row,
        )

    async def close_runtime(self, runtime: ApiImageProviderRuntime) -> None:
        await runtime.session.close()


PROVIDER_REGISTRY: Dict[str, GenerationProviderAdapter] = {
    "comfyui": ComfyUIProviderAdapter(),
    "api-image": ApiImageProviderAdapter(),
}


def get_provider_adapter(provider_id: str) -> GenerationProviderAdapter:
    provider_key = str(provider_id or "").strip().lower()
    adapter = PROVIDER_REGISTRY.get(provider_key)
    if not adapter:
        raise RuntimeError(f"No provider adapter registered for {provider_key}")
    return adapter


def get_provider_descriptor(provider_id: str) -> Dict[str, Any]:
    adapter = PROVIDER_REGISTRY.get(provider_id)
    if not adapter:
        return {
            "id": provider_id,
            "label": provider_id,
            "description": "Unknown or legacy provider id stored in run history.",
            "capabilities": {},
        }
    return {
        "id": adapter.provider_id,
        "label": getattr(adapter, "label", adapter.provider_id),
        "description": getattr(adapter, "description", ""),
        "capabilities": dict(adapter.capabilities() or {}),
    }


def list_provider_descriptors() -> List[Dict[str, Any]]:
    return [get_provider_descriptor(provider_id) for provider_id in sorted(PROVIDER_REGISTRY.keys())]


def build_effective_project_capabilities(config: Dict[str, Any], provider_id: str) -> Dict[str, Any]:
    provider_caps = get_provider_descriptor(provider_id).get("capabilities", {}) or {}
    project_caps = dict(config.get("capabilities", {}) or {})
    effective = dict(provider_caps)
    if "supportsReferenceAssets" in effective:
        effective["supportsReferenceAssets"] = bool(
            provider_caps.get("supportsReferenceAssets", False)
            and project_caps.get("supportsReferenceAssets", False)
        )
    return effective


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
                sub_dir = os.path.join(OUTPUT_DIR, config.project, t)
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
                    url=f"/outputs/{config.project}/{t}/{file_name}", local_path=save_path,
                    status="success", duration=duration, row=row
                )
        await asyncio.sleep(1)

    # Timeout
    duration = time.time() - start_time
    add_log(f"Timeout ({timeout_seconds}s) for {desc} ({t}) — skipping", "warning")
    return False, make_result_entry(desc, t, prompt_text, final_positive, final_negative, width, height, status="timeout", duration=duration, row=row)


# --- Batch Runner ---
async def run_kemi_batch(project, selected_prompts, types, style_prompt="", negative_prompt="", global_aspect_ratio="16:9", batch_count=1, steps=20, *, run_id=None, mode="direct", provider_id="comfyui", request_summary=None):
    reset_batch_status()
    batch_status["run_id"] = run_id
    batch_status["project"] = project
    batch_status["mode"] = mode
    batch_status["provider_id"] = provider_id
    batch_status["request"] = request_summary or {}
    reference_assets = selected_prompts[0].get("_reference_assets", []) if selected_prompts else []
    batch_status["reference_assets"] = reference_assets
    add_log("Starting batch generation...")
    if reference_assets:
        add_log(f"Using {len(reference_assets)} reference assets")
    batch_status["is_running"] = True
    batch_status["finish_status"] = None
    batch_status["current_item"] = "Initializing provider runtime"
    persist_current_run()

    provider_adapter = get_provider_adapter(provider_id)
    runtime: Optional[ProviderRuntime] = None

    try:
        batch_status["total"] = len(selected_prompts) * len(types) * batch_count
        batch_status["current_item"] = "Preparing generation runtime"
        persist_current_run()

        try:
            runtime = await provider_adapter.prepare_runtime(
                project=project,
                style_prompt=style_prompt,
                negative_prompt=negative_prompt,
                steps=steps,
                global_aspect_ratio=global_aspect_ratio,
            )
        except Exception as e:
            add_log(f"Provider runtime init failed: {str(e)}", "error")
            batch_status["errors"] += 1
            return

        for row in selected_prompts:
            if "_project" not in row or not row.get("_project"):
                row["_project"] = project
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

                    success, result_entry = await provider_adapter.generate_single(
                        runtime,
                        ProviderImageRequest(
                            prompt_text=row.get('prompt', ''),
                            desc=desc,
                            output_type=t,
                            row=row,
                            batch_idx=i,
                        ),
                    )

                    batch_status["results"].append(result_entry)
                    batch_status["completed"] += 1
                    if success:
                        batch_status["succeeded"] += 1
                    elif result_entry["status"] == "timeout":
                        batch_status["warnings"] += 1
                    else:
                        batch_status["errors"] += 1
                    persist_current_run()

    except Exception as e:
        add_log(f"Fatal error: {str(e)}", "error")
        batch_status["errors"] += 1
    finally:
        if runtime is not None:
            try:
                await provider_adapter.close_runtime(runtime)
            except Exception as close_error:
                add_log(f"Provider cleanup warning: {str(close_error)}", "warning")
        with START_BATCH_LOCK:
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
            final_snapshot = copy.deepcopy(batch_status)
        persist_current_run(final_snapshot)


# --- Pydantic Models ---
from pydantic import BaseModel, Field

class GenerationParamsPayload(BaseModel):
    aspect_ratio: str = "16:9"
    steps: int = 20
    batch_count: int = 1
    seed: Optional[int] = None
    negative_prompt: str = ""
    extra_positive: str = ""


class SceneActorPayload(BaseModel):
    character: str = ""
    emotion: str = ""
    role: str = ""


class SceneVisualPayload(BaseModel):
    framing: str = ""
    camera_distance: str = ""
    lighting: str = ""


class SceneContextPayload(BaseModel):
    background: str = ""
    location: str = ""
    situation: str = ""
    interaction: str = ""


class SceneDraftPayload(BaseModel):
    situation: str = ""
    interaction: str = ""
    background: str = ""
    location: str = ""
    lighting: str = ""


class SceneSpecPayload(BaseModel):
    project_id: str = ""
    template_id: Optional[str] = None
    actors: List[SceneActorPayload] = Field(default_factory=list)
    scene: SceneContextPayload = Field(default_factory=SceneContextPayload)
    props: List[str] = Field(default_factory=list)
    visual: SceneVisualPayload = Field(default_factory=SceneVisualPayload)
    style: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=lambda: ["thumb", "hero"])
    variation: Dict[str, Any] = Field(default_factory=dict)


class StartBatchRequest(BaseModel):
    project: str = "kemi"
    mode: str = "direct"
    provider_id: Optional[str] = None
    operator_mode: str = "studio"
    template_id: Optional[str] = None
    scene_spec: Optional[SceneSpecPayload] = None
    prompts: List[Dict[str, Any]] = Field(default_factory=list)
    reference_assets: List[Dict[str, Any]] = Field(default_factory=list)
    types: List[str] = Field(default_factory=lambda: ["thumb", "hero"])
    style_prompt: str = ""
    negative_prompt: str = ""
    global_aspect_ratio: str = "16:9"
    batch_count: int = 1
    steps: int = 20
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SceneTemplatePayload(BaseModel):
    id: Optional[str] = None
    name: str
    composition: str = "single"
    description: str = ""
    reference_asset_paths: List[str] = Field(default_factory=list)
    style_prompt: str = ""
    negative_prompt: str = ""
    global_aspect_ratio: str = "16:9"
    batch_count: int = 1
    steps: int = 20
    types: List[str] = Field(default_factory=lambda: ["thumb", "hero"])
    scene_draft: SceneDraftPayload = Field(default_factory=SceneDraftPayload)
    meta: Dict[str, Any] = Field(default_factory=dict)


class SaveSceneTemplateRequest(BaseModel):
    project: str = "kemi"
    template: SceneTemplatePayload


def resolve_provider_id(project: str, requested_provider_id: Optional[str] = None) -> str:
    config = load_project_config(project)
    config_provider = str(config.get("provider", "comfyui") or "comfyui").strip().lower()
    supported_provider_ids = [
        str(item or "").strip().lower()
        for item in (config.get("supportedProviders", [config_provider]) or [config_provider])
        if str(item or "").strip()
    ]
    if config_provider not in supported_provider_ids:
        supported_provider_ids.insert(0, config_provider)
    provider_id = str(requested_provider_id or config_provider).strip().lower() or config_provider
    if provider_id not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider_id}")
    if config_provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Project is configured for unsupported provider: {config_provider}")
    if provider_id not in supported_provider_ids:
        raise HTTPException(status_code=400, detail=f"Project '{project}' does not support provider '{provider_id}'")
    adapter = get_provider_adapter(provider_id)
    if not adapter.is_configured():
        raise HTTPException(status_code=400, detail=adapter.configuration_error() or f"Provider '{provider_id}' is not configured")
    return provider_id


def normalize_output_types(req: "StartBatchRequest") -> List[str]:
    requested_types = req.types or (req.scene_spec.outputs if req.scene_spec else []) or ["thumb", "hero"]
    normalized: List[str] = []
    for item in requested_types:
        value = str(item or "").strip().lower()
        if value in {"thumb", "hero"} and value not in normalized:
            normalized.append(value)
    return normalized


def collect_custom_prompt_seeds(req: "StartBatchRequest") -> List[int]:
    custom_seed_prompts: List[int] = []
    for item in req.prompts or []:
        try:
            seed_value = int(item.get("seed", 0) or 0)
        except (TypeError, ValueError):
            seed_value = 0
        if seed_value > 0:
            custom_seed_prompts.append(seed_value)
    return custom_seed_prompts


def build_seed_capability_warnings(req: "StartBatchRequest") -> List[str]:
    warnings: List[str] = []
    custom_seed_prompts = collect_custom_prompt_seeds(req)
    if not custom_seed_prompts:
        return warnings
    try:
        provider_id = resolve_provider_id(req.project, req.provider_id)
    except HTTPException:
        requested_provider_id = str(req.provider_id or "").strip().lower()
        if requested_provider_id not in SUPPORTED_PROVIDERS:
            return warnings
        provider_id = requested_provider_id
    provider_info = get_provider_descriptor(provider_id)
    if not provider_info.get("capabilities", {}).get("supportsDeterministicSeed", True):
        warnings.append(
            f"Provider '{provider_id}' ignores custom prompt seed values. Runs may not be reproducible from seed inputs alone."
        )
    return warnings


def validate_generation_numbers(req: "StartBatchRequest") -> None:
    if int(req.batch_count or 0) < 1 or int(req.batch_count or 0) > 10:
        raise HTTPException(status_code=400, detail="Repeat count must be between 1 and 10")
    if int(req.steps or 0) < 4 or int(req.steps or 0) > 50:
        raise HTTPException(status_code=400, detail="Steps must be between 4 and 50")


def serialize_scene_template(project: str, template: SceneTemplatePayload, existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    now = datetime.now().isoformat()
    template_id = template.id or existing.get("id") if existing else None
    template_id = template_id or str(uuid.uuid4())
    composition = (template.composition or "single").strip().lower()
    if composition not in {"single", "duo", "group", "custom"}:
        composition = "custom"

    scene_draft = model_to_dict(template.scene_draft)
    scene_draft = {
        "situation": (scene_draft.get("situation", "") or "").strip(),
        "interaction": (scene_draft.get("interaction", "") or "").strip(),
        "background": (scene_draft.get("background", "") or "").strip(),
        "location": (scene_draft.get("location", "") or "").strip(),
        "lighting": (scene_draft.get("lighting", "") or "").strip(),
    }
    meta = dict(template.meta or {})
    legacy_scene_draft = meta.pop("sceneDraft", None)
    if not any(scene_draft.values()) and isinstance(legacy_scene_draft, dict):
        scene_draft = {
            "situation": str(legacy_scene_draft.get("situation", "") or "").strip(),
            "interaction": str(legacy_scene_draft.get("interaction", "") or "").strip(),
            "background": str(legacy_scene_draft.get("background", "") or "").strip(),
            "location": str(legacy_scene_draft.get("location", "") or "").strip(),
            "lighting": str(legacy_scene_draft.get("lighting", "") or "").strip(),
        }

    stored = {
        "id": template_id,
        "project": project,
        "name": template.name.strip(),
        "composition": composition,
        "description": (template.description or "").strip(),
        "referenceAssetPaths": normalize_template_reference_paths(template.reference_asset_paths),
        "stylePrompt": (template.style_prompt or "").strip(),
        "negativePrompt": (template.negative_prompt or "").strip(),
        "globalAspectRatio": template.global_aspect_ratio or "16:9",
        "batchCount": max(1, min(int(template.batch_count or 1), 10)),
        "steps": max(4, min(int(template.steps or 20), 50)),
        "types": [t for t in (template.types or ["thumb", "hero"]) if t in {"thumb", "hero"}] or ["thumb", "hero"],
        "sceneDraft": scene_draft,
        "meta": meta,
        "updatedAt": now,
        "createdAt": existing.get("createdAt", now) if existing else now,
    }
    return stored


def build_assisted_prompt(scene_spec: Optional[SceneSpecPayload], prompts: List[Dict[str, Any]], style_prompt: str) -> str:
    parts: List[str] = []
    if scene_spec:
        actor_bits = []
        for actor in scene_spec.actors:
            segment = ", ".join([value for value in [actor.character, actor.role, actor.emotion] if value])
            if segment:
                actor_bits.append(segment)
        if actor_bits:
            parts.append("characters: " + "; ".join(actor_bits))

        scene = scene_spec.scene
        scene_bits = [scene.situation, scene.interaction, scene.background, scene.location]
        scene_text = ", ".join([value for value in scene_bits if value])
        if scene_text:
            parts.append(scene_text)

        if scene_spec.props:
            parts.append("props: " + ", ".join(scene_spec.props))

        visual_bits = [scene_spec.visual.framing, scene_spec.visual.camera_distance, scene_spec.visual.lighting]
        visual_text = ", ".join([value for value in visual_bits if value])
        if visual_text:
            parts.append("visuals: " + visual_text)

        if scene_spec.style:
            parts.append("style anchors: " + ", ".join(scene_spec.style))

    prompt_texts = [item.get("prompt", "").strip() for item in prompts if item.get("prompt")]
    if prompt_texts:
        parts.append("prompt seeds: " + " | ".join(prompt_texts))

    return ", ".join([part for part in parts if part]).strip()


def build_request_summary(req: StartBatchRequest) -> Dict[str, Any]:
    scene_spec = model_to_dict(req.scene_spec) if req.scene_spec else None
    provider_id = resolve_provider_id(req.project, req.provider_id)
    output_types = normalize_output_types(req)
    operator_mode = str(req.operator_mode or "studio").strip().lower() or "studio"
    return {
        "requestId": str(uuid.uuid4()),
        "projectId": req.project,
        "mode": (req.mode or "direct").strip().lower(),
        "providerId": provider_id,
        "operatorMode": operator_mode,
        "templateId": req.template_id,
        "sceneSpec": scene_spec,
        "promptSource": "manual" if any(item.get("is_manual") for item in req.prompts) else "selection",
        "prompts": summarize_prompt_rows(req.prompts),
        "referenceAssets": summarize_reference_assets(req.reference_assets),
        "outputTypes": output_types,
        "generationParams": {
            "aspectRatio": req.global_aspect_ratio,
            "steps": req.steps,
            "batchCount": req.batch_count,
            "negativePrompt": req.negative_prompt,
            "extraPositive": req.style_prompt,
        },
        "metadata": dict(req.metadata or {}),
    }


def validate_generation_request(req: StartBatchRequest) -> None:
    try:
        load_project_config(req.project)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    resolve_provider_id(req.project, req.provider_id)
    validate_generation_numbers(req)
    mode = (req.mode or "direct").strip().lower()
    operator_mode = str(req.operator_mode or "studio").strip().lower() or "studio"
    if mode not in {"direct", "assisted"}:
        raise HTTPException(status_code=400, detail="Invalid generation mode")
    if operator_mode not in {"studio", "codex-conversation"}:
        raise HTTPException(status_code=400, detail="Invalid operator mode")
    if operator_mode == "codex-conversation" and mode != "assisted":
        raise HTTPException(status_code=400, detail="Codex conversation operator requires assisted mode")
    if mode == "direct" and not req.prompts:
        raise HTTPException(status_code=400, detail="Direct generation requires prompts")
    if mode == "assisted":
        if not req.scene_spec and not req.template_id and not req.prompts:
            raise HTTPException(status_code=400, detail="Assisted generation requires a scene spec, template, or prompt seed")
        if req.scene_spec and req.scene_spec.project_id and req.scene_spec.project_id != req.project:
            raise HTTPException(status_code=400, detail="Scene spec project does not match request project")
        if req.template_id and not any(item.get("id") == req.template_id for item in load_project_templates(req.project)):
            raise HTTPException(status_code=400, detail="Selected template does not exist for this project")


def count_reference_slots(reference_assets: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for asset in summarize_reference_assets(reference_assets):
        slot = (asset.get("slot") or "extra").strip() or "extra"
        counts[slot] = counts.get(slot, 0) + 1
    return counts


def build_preflight_validation(req: StartBatchRequest) -> Dict[str, Any]:
    mode = (req.mode or "direct").strip().lower()
    operator_mode = str(req.operator_mode or "studio").strip().lower() or "studio"
    config = load_project_config(req.project)
    provider_id = resolve_provider_id(req.project, req.provider_id)
    provider_info = get_provider_descriptor(provider_id)
    reference_assets = summarize_reference_assets(req.reference_assets)
    slot_counts = count_reference_slots(reference_assets)
    reference_policy = config.get("referencePolicy", {}) or {}
    project_capabilities = config.get("capabilities", {}) or {}
    effective_capabilities = build_effective_project_capabilities(config, provider_id)
    output_types = normalize_output_types(req)
    errors: List[str] = []
    warnings: List[str] = []
    info: List[str] = []

    if not output_types:
        errors.append("Select at least one output type.")

    if mode == "direct" and not effective_capabilities.get("supportsDirectGeneration", False):
        errors.append(f"Provider '{provider_id}' does not support direct generation for this project.")
    if mode == "assisted" and not effective_capabilities.get("supportsAssistedGeneration", False):
        errors.append(f"Provider '{provider_id}' does not support assisted generation for this project.")
    if mode == "assisted" and req.scene_spec and not effective_capabilities.get("supportsSceneSpec", False):
        warnings.append(f"Provider '{provider_id}' does not use scene spec fields directly. Assisted mode will fall back to prompt composition only.")
    warnings.extend(build_seed_capability_warnings(req))
    if operator_mode == "codex-conversation":
        info.append("Operator: Codex conversation")
        warnings.append("Codex conversation mode keeps this run aligned with chat-guided scene planning and review.")
    else:
        info.append("Operator: Studio")

    required_slots = [slot for slot in reference_policy.get("requiredSlots", []) if slot]
    missing_required = [slot for slot in required_slots if slot_counts.get(slot, 0) == 0]
    if missing_required:
        errors.append("Missing required reference slots: " + ", ".join(missing_required))

    recommended_slots = [slot for slot in reference_policy.get("recommendedSlots", []) if slot]
    missing_recommended = [slot for slot in recommended_slots if slot_counts.get(slot, 0) == 0]
    if missing_recommended:
        warnings.append("Recommended slots are empty: " + ", ".join(missing_recommended))

    if reference_assets and not effective_capabilities.get("supportsReferenceAssets", False):
        provider_supports_refs = provider_info.get("capabilities", {}).get("supportsReferenceAssets", False)
        if not provider_supports_refs:
            warnings.append(f"Provider '{provider_id}' does not yet inject references into the renderer. The selected references will still shape assisted planning and review rules.")
        elif config.get("workflowMode") == "reference-first":
            warnings.append(f"Project '{req.project}' keeps references in planning-first mode for provider '{provider_id}'. The selected references will still shape assisted planning and review rules.")
        else:
            warnings.append(f"Project '{req.project}' currently treats references as planning-only for provider '{provider_id}'.")

    if mode == "assisted":
        if not req.template_id:
            warnings.append("Assisted mode works better with a scene template selected.")
        if not req.scene_spec:
            warnings.append("No scene spec was provided. Assisted mode will fall back to prompt seeds only.")
        else:
            actor_count = len(req.scene_spec.actors or [])
            if actor_count == 0:
                warnings.append("No actors were derived for the scene spec.")
            if req.template_id:
                template = next((item for item in load_project_templates(req.project) if item.get("id") == req.template_id), None)
                composition = (template or {}).get("composition", "")
                if composition == "duo" and actor_count < 2:
                    warnings.append("The selected duo template has fewer than 2 detected actors.")
                if composition == "single" and actor_count > 1:
                    warnings.append("The selected single-person template currently has multiple detected actors.")

            scene_fields = req.scene_spec.scene if req.scene_spec else None
            has_scene_cue = bool(
                scene_fields
                and any([
                    scene_fields.situation,
                    scene_fields.interaction,
                    scene_fields.background,
                    scene_fields.location,
                ])
            )
            if not has_scene_cue and not req.prompts:
                errors.append("Assisted mode needs either a scene cue or prompt seeds.")

    prompt_count = len(req.prompts) if mode == "direct" else max(1, len(req.prompts) or 1)
    estimated_images = prompt_count * max(1, len(output_types)) * max(1, int(req.batch_count or 1))
    if estimated_images >= 20:
        warnings.append(f"This run will attempt {estimated_images} renders. Consider reducing repeat count before testing.")

    info.append(f"Mode: {mode}")
    info.append(f"Provider: {provider_info.get('label', provider_id)}")
    info.append(f"Outputs: {', '.join(output_types)}")
    info.append(f"Selected references: {len(reference_assets)}")

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "summary": {
            "mode": mode,
            "operatorMode": operator_mode,
            "providerId": provider_id,
            "providerLabel": provider_info.get("label", provider_id),
            "projectId": req.project,
            "promptCount": len(req.prompts),
            "estimatedImages": estimated_images,
            "outputTypes": output_types,
            "referenceCount": len(reference_assets),
            "selectedSlots": slot_counts,
            "requiredSlots": required_slots,
            "missingRequiredSlots": missing_required,
            "missingRecommendedSlots": missing_recommended,
            "effectiveCapabilities": effective_capabilities,
            "projectCapabilities": project_capabilities,
        },
    }


def normalize_selected_prompts(req: StartBatchRequest) -> List[Dict[str, Any]]:
    mode = (req.mode or "direct").strip().lower()
    prompts = [dict(prompt) for prompt in req.prompts]
    if mode == "direct":
        return prompts

    assisted_prompt = build_assisted_prompt(req.scene_spec, prompts, req.style_prompt)
    if not assisted_prompt:
        assisted_prompt = ", ".join([item.get("prompt", "") for item in prompts if item.get("prompt")]).strip()
    if not assisted_prompt:
        assisted_prompt = "character scene illustration"

    scene_summary = ""
    if req.scene_spec:
        scene_summary = req.scene_spec.scene.situation or req.scene_spec.scene.background or ""
    scene_summary = scene_summary or req.template_id or "Assisted Scene"

    return [{
        "id": 0,
        "desc_ko": scene_summary,
        "prompt": assisted_prompt,
        "aspect_ratio": req.global_aspect_ratio,
        "_project": req.project,
        "_template_id": req.template_id or (req.scene_spec.template_id if req.scene_spec else ""),
        "_scene_spec": model_to_dict(req.scene_spec),
    }]


@app.get("/api/templates")
async def list_scene_templates(project: str = "kemi"):
    load_project_config(project)
    templates = load_project_templates(project)
    templates = sorted(templates, key=lambda item: item.get("updatedAt", ""), reverse=True)
    return {"project": project, "templates": templates}


@app.post("/api/templates")
async def save_scene_template(req: SaveSceneTemplateRequest):
    load_project_config(req.project)
    template_name = req.template.name.strip()
    if not template_name:
        raise HTTPException(status_code=400, detail="Template name is required")

    templates = load_project_templates(req.project)
    existing = None
    if req.template.id:
        existing = next((item for item in templates if item.get("id") == req.template.id), None)

    stored = serialize_scene_template(req.project, req.template, existing)

    if existing:
        templates = [stored if item.get("id") == stored["id"] else item for item in templates]
    else:
        templates.insert(0, stored)

    save_project_templates(req.project, templates)
    return {"status": "saved", "project": req.project, "template": stored}


@app.delete("/api/templates/{template_id}")
async def delete_scene_template(template_id: str, project: str = "kemi"):
    load_project_config(project)
    templates = load_project_templates(project)
    remaining = [item for item in templates if item.get("id") != template_id]
    if len(remaining) == len(templates):
        raise HTTPException(status_code=404, detail="Template not found")
    save_project_templates(project, remaining)
    return {"status": "deleted", "project": project, "templateId": template_id}


@app.post("/api/generation/validate")
async def validate_generation(req: StartBatchRequest):
    try:
        validate_generation_request(req)
    except HTTPException as exc:
        warnings = build_seed_capability_warnings(req)
        return JSONResponse(
            status_code=200,
            content={
                "ok": False,
                "errors": [str(exc.detail)],
                "warnings": warnings,
                "info": [],
                "summary": {
                    "mode": (req.mode or "direct").strip().lower(),
                    "projectId": req.project,
                },
            },
        )
    return build_preflight_validation(req)


@app.post("/api/batch/start")
async def start_batch(background_tasks: BackgroundTasks, req: StartBatchRequest):
    validate_generation_request(req)
    preflight = build_preflight_validation(req)
    if preflight["errors"]:
        raise HTTPException(status_code=400, detail=preflight["errors"][0])
    provider_id = resolve_provider_id(req.project, req.provider_id)
    request_summary = build_request_summary(req)
    run_id = str(uuid.uuid4())
    prompts = normalize_selected_prompts(req)
    output_types = request_summary["outputTypes"]
    claim_batch_start(req.project, run_id, request_summary["mode"], provider_id, request_summary, req.reference_assets)
    try:
        create_initial_run_record(req.project, run_id, request_summary["mode"], provider_id, request_summary, req.reference_assets)
        for prompt in prompts:
            prompt["_reference_assets"] = req.reference_assets
            prompt["_generation_mode"] = request_summary["mode"]
            prompt["_provider_id"] = provider_id

        background_tasks.add_task(
            run_kemi_batch, req.project, prompts, output_types, req.style_prompt,
            req.negative_prompt, req.global_aspect_ratio, req.batch_count, req.steps,
            run_id=run_id, mode=request_summary["mode"], provider_id=provider_id, request_summary=request_summary
        )
    except Exception:
        restore_idle_batch_status()
        raise
    return {"status": "started", "project": req.project, "runId": run_id, "mode": request_summary["mode"], "providerId": provider_id}


# --- Crop ---
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
    successful = [
        r for r in results
        if r.get("status") == "success"
        and r.get("local_path")
        and r.get("_project") in ("", project)
    ]
    if not successful:
        return {"error": "No successful images to crop"}

    cropped = []
    try:
        from PIL import Image

        crop_output_dir = os.path.join(OUTPUT_DIR, project, "cropped")
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

                # R2 키 생성: _category + 영어 프롬프트 기반 (한국어 금지 — MBTI 프록시가 ASCII만 허용)
                category = result.get("_category", "misc")
                # 프롬프트 첫 부분(영어 breed명)에서 R2 키 생성
                prompt_first = result.get("prompt", "unknown").split(",")[0].strip()
                safe_result_name = re.sub(r'[^a-zA-Z0-9]', '-', prompt_first).lower().strip('-')
                safe_result_name = re.sub(r'-+', '-', safe_result_name)  # 연속 하이픈 제거
                gen_type = result.get("type", "img")
                r2_key = f"{category}/{safe_result_name}_{gen_type}_{crop_name}.webp"

                result_crops[crop_name] = {
                    "path": out_path,
                    "localUrl": f"/outputs/{project}/cropped/{out_name}",
                    "r2Key": r2_key,
                    "url": f"/api/images/{r2_key}",
                    "width": tw,
                    "height": th,
                }

            if result_crops:
                result["_crops"] = result_crops
                cropped.append({"name": result["name"], "crops": list(result_crops.keys())})

        add_log(f"Cropped {len(cropped)} images into {sum(len(c['crops']) for c in cropped)} variants", "success")
        persist_current_run()
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
    successful = [r for r in results if r.get("status") == "success" and r.get("_project") in ("", project)]

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
            "referenceAssets": r.get("_reference_assets", []),
            "assets": assets,
        })

    manifest = {
        "generatedAt": datetime.now().isoformat(),
        "project": project,
        "totalImages": len(items),
        "items": items,
    }

    # 파일로도 저장
    manifest_dir = os.path.join(OUTPUT_DIR, project)
    os.makedirs(manifest_dir, exist_ok=True)
    manifest_path = os.path.join(manifest_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return manifest


# --- R2 Upload ---
@app.post("/api/upload")
async def upload_to_r2(project: str = "kemi"):
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
        results = batch_status.get("results", [])

        # 크롭된 이미지를 R2 키 기반으로 업로드
        for result in results:
            if result.get("_project") not in ("", project):
                continue
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
        persist_current_run()
        return {"status": "success", "project": project, "mappings": mappings, "uploaded": uploaded}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
