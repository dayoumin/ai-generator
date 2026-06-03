import argparse
import html
import io
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel


CONTRACT = "ai-generator-upscale-v1"
MAX_UPLOAD_BYTES = int(os.getenv("UPSCALE_STANDALONE_MAX_BYTES", str(100 * 1024 * 1024)))
DEFAULT_MAX_PIXELS = 64_000_000
OUTPUT_FILE_RE = re.compile(r"^[^/\\]+_x[24]_[0-9]{8}-[0-9]{6}-[0-9a-f]{6}\.webp$")
RUN_LOCK = threading.Lock()
app = FastAPI(title="AI Generator Local Upscale Runner Stub")


class UpscalePayload(BaseModel):
    contract: str
    probe: bool = False
    inputPath: str = ""
    outputPath: str = ""
    scale: int = 2
    engine: str = "pid-http"


def allowed_root() -> Path:
    configured = os.getenv("UPSCALE_ALLOWED_ROOT", "")
    root = Path(configured) if configured else Path.cwd() / "outputs"
    return root.expanduser().resolve()


def standalone_output_dir() -> Path:
    configured = os.getenv("UPSCALE_STANDALONE_OUTPUT_DIR", "")
    output_dir = Path(configured).expanduser().resolve() if configured else allowed_root() / "standalone-upscaled"
    try:
        output_dir.relative_to(allowed_root())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Standalone output dir must stay under {allowed_root()}") from exc
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def resolve_allowed_path(path_value: str, *, must_exist: bool = False) -> Path:
    if not path_value:
        raise HTTPException(status_code=400, detail="Path is required")
    path = Path(path_value).expanduser().resolve()
    root = allowed_root()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Path must stay under {root}") from exc
    if must_exist and not path.exists():
        raise HTTPException(status_code=400, detail="Input path does not exist")
    return path


def sanitize_output_name(value: str, fallback: str = "upscaled") -> str:
    name = Path(str(value or "").strip()).name
    stem = Path(name).stem
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in stem).strip("-._")
    return safe or fallback


def build_output_name(input_name: str, scale: int, output_name: str = "") -> str:
    timestamp = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    stem = sanitize_output_name(output_name or input_name, "upscaled")
    return f"{stem}_x{scale}_{timestamp}.webp"


def ensure_scale(scale: int) -> int:
    if scale not in {2, 4}:
        raise HTTPException(status_code=400, detail="Only x2 and x4 are supported by this stub")
    return scale


def max_upload_pixels() -> int:
    return max(1, int(os.getenv("UPSCALE_STANDALONE_MAX_PIXELS", str(DEFAULT_MAX_PIXELS))))


def normalize_image(img: "Image.Image") -> "Image.Image":
    return img.convert("RGBA") if img.mode in {"RGBA", "LA", "P"} else img.convert("RGB")


def ensure_image_limits(width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise HTTPException(status_code=400, detail="Uploaded image is not readable")
    if width * height > max_upload_pixels():
        raise HTTPException(status_code=400, detail=f"Uploaded image has too many pixels. Max {max_upload_pixels():,} pixels")


def save_upscaled_image(input_path: Path, output_path: Path, scale: int) -> tuple[int, int]:
    if not RUN_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Runner is busy")
    try:
        from PIL import Image

        with Image.open(input_path) as img:
            ensure_image_limits(img.width, img.height)
            source = normalize_image(img)
            resized = source.resize((source.width * scale, source.height * scale), Image.LANCZOS)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            resized.save(output_path, "WEBP", quality=92)
            return resized.size
    finally:
        RUN_LOCK.release()


def save_upscaled_bytes(image_bytes: bytes, output_path: Path, scale: int) -> tuple[int, int]:
    if not RUN_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Runner is busy")
    try:
        from PIL import Image, UnidentifiedImageError

        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                ensure_image_limits(img.width, img.height)
                source = normalize_image(img)
                resized = source.resize((source.width * scale, source.height * scale), Image.LANCZOS)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                resized.save(output_path, "WEBP", quality=92)
                return resized.size
        except UnidentifiedImageError as exc:
            raise HTTPException(status_code=400, detail="Uploaded file is not a readable image") from exc
    finally:
        RUN_LOCK.release()


def is_valid_output_filename(filename: str) -> bool:
    return bool(OUTPUT_FILE_RE.match(filename))


def probe_response() -> Dict[str, Any]:
    return {
        "status": "ok",
        "contract": CONTRACT,
        "backend": "pillow-stub",
        "modelAvailable": False,
        "reason": "Contract-compatible local stub. It does not bundle or run NVIDIA PiD weights.",
        "capabilities": {
            "scales": [2, 4],
            "formats": ["png", "jpg", "jpeg", "webp"],
            "singleJob": True,
            "batchUpload": True,
        },
    }


@app.get("/health")
def health() -> Dict[str, Any]:
    return probe_response()


@app.get("/", response_class=HTMLResponse)
def standalone_home() -> str:
    root = html.escape(str(allowed_root()))
    output_dir = html.escape(str(standalone_output_dir()))
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local Upscale Runner</title>
  <style>
    body {{ margin: 0; font-family: system-ui, sans-serif; background: #0f172a; color: #e5e7eb; }}
    main {{ max-width: 720px; margin: 0 auto; padding: 32px 20px; }}
    form, .note, .result-list {{ border: 1px solid rgba(255,255,255,.12); border-radius: 12px; background: rgba(15,23,42,.72); padding: 18px; }}
    label {{ display: grid; gap: 8px; margin: 14px 0; color: #94a3b8; font-weight: 700; }}
    input, select, button {{ font: inherit; border-radius: 8px; border: 1px solid rgba(255,255,255,.16); padding: 10px 12px; }}
    input, select {{ background: #111827; color: #f8fafc; }}
    button, .download-link {{ border: 0; border-radius: 8px; background: #6366f1; color: white; cursor: pointer; font-weight: 800; padding: 10px 12px; text-decoration: none; display: inline-flex; }}
    .subtle {{ color: #94a3b8; }}
    .item {{ border-top: 1px solid rgba(255,255,255,.1); padding: 14px 0; display: grid; gap: 8px; }}
    .item:first-child {{ border-top: 0; }}
    code {{ color: #c7d2fe; word-break: break-all; }}
  </style>
</head>
<body>
  <main>
    <h1>Local Upscale Runner</h1>
    <p>AI_Generator 앱 run/manifest와 별개로 PC 이미지를 업로드하고 결과를 바로 저장합니다.</p>
    <p class="subtle">현재 기본 엔진은 Pillow/LANCZOS 테스트 runner입니다. NVIDIA PiD 모델/weights는 포함되어 있지 않습니다.</p>
    <form action="/standalone/upscale" method="post" enctype="multipart/form-data">
      <label>이미지 파일
        <input name="file" type="file" accept="image/png,image/jpeg,image/webp" multiple required>
        <span class="subtle">여러 파일을 한 번에 선택할 수 있습니다.</span>
      </label>
      <label>배율
        <select name="scale">
          <option value="2">x2</option>
          <option value="4">x4</option>
        </select>
      </label>
      <label>결과 파일 이름(선택)
        <input name="outputName" type="text" placeholder="비우면 원본 파일 이름을 사용합니다. 여러 파일이면 공통 prefix로 씁니다.">
      </label>
      <label>
        <span><input name="keepInput" type="checkbox" value="true"> 처리 원본도 standalone-inputs에 보관</span>
      </label>
      <button type="submit">업스케일해서 저장</button>
    </form>
    <div class="note">
      <p>허용 루트: <code>{root}</code></p>
      <p>저장 폴더: <code>{output_dir}</code></p>
    </div>
  </main>
</body>
</html>"""


def wants_html_response(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/html" in accept and "application/json" not in accept


def render_standalone_result_page(payload: Dict[str, Any]) -> str:
    status = html.escape(str(payload.get("status") or "success"))
    results = payload.get("results") or []
    errors = payload.get("errors") or []
    result_items = "\n".join(
        f"""
        <div class="item">
          <strong>{html.escape(str(item.get("sourceName") or "image"))}</strong>
          <span class="subtle">{html.escape(str(item.get("width") or "?"))} x {html.escape(str(item.get("height") or "?"))} · x{html.escape(str(item.get("scale") or ""))} · {html.escape(str(item.get("backend") or "pillow-stub"))}</span>
          <code>{html.escape(str(item.get("outputPath") or ""))}</code>
          <a class="download-link" href="{html.escape(str(item.get("downloadUrl") or ""))}">Download result</a>
        </div>
        """
        for item in results
    ) or '<p class="subtle">No files were generated.</p>'
    error_items = "\n".join(
        f"<li>{html.escape(str(item.get('sourceName') or 'image'))}: {html.escape(str(item.get('error') or 'failed'))}</li>"
        for item in errors
    )
    error_block = f"<h2>Skipped files</h2><ul>{error_items}</ul>" if error_items else ""
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Upscale Results</title>
  <style>
    body {{ margin: 0; font-family: system-ui, sans-serif; background: #0f172a; color: #e5e7eb; }}
    main {{ max-width: 820px; margin: 0 auto; padding: 32px 20px; }}
    .result-list, .note {{ border: 1px solid rgba(255,255,255,.12); border-radius: 12px; background: rgba(15,23,42,.72); padding: 18px; }}
    .item {{ border-top: 1px solid rgba(255,255,255,.1); padding: 14px 0; display: grid; gap: 8px; }}
    .item:first-child {{ border-top: 0; }}
    .subtle {{ color: #94a3b8; }}
    code {{ color: #c7d2fe; word-break: break-all; }}
    a {{ color: #c7d2fe; }}
    .download-link {{ justify-self: start; border-radius: 8px; background: #6366f1; color: white; font-weight: 800; padding: 10px 12px; text-decoration: none; }}
  </style>
</head>
<body>
  <main>
    <h1>Upscale Results</h1>
    <p class="subtle">Status: {status} · generated {html.escape(str(payload.get("succeeded") or 0))} / {html.escape(str(payload.get("count") or 0))}</p>
    <section class="result-list">
      {result_items}
    </section>
    {error_block}
    <p><a href="/">Run another batch</a></p>
  </main>
</body>
</html>"""


async def process_standalone_upload(file: UploadFile, scale: int, output_name: str, keep_input: bool) -> Dict[str, Any]:
    source_name = Path(file.filename or "upload.png").name
    suffix = Path(source_name).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=400, detail="Only PNG, JPG, JPEG, or WEBP images can be upscaled")

    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded image is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail=f"Uploaded image is too large. Max {MAX_UPLOAD_BYTES // (1024 * 1024)}MB")

    output_path = standalone_output_dir() / build_output_name(source_name, scale, output_name)
    width, height = save_upscaled_bytes(data, output_path, scale)
    input_path = None
    if keep_input:
        safe_stem = sanitize_output_name(source_name, "upload")
        input_dir = allowed_root() / "standalone-inputs"
        input_dir.mkdir(parents=True, exist_ok=True)
        input_path = input_dir / f"{safe_stem}_{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}{suffix}"
        input_path.write_bytes(data)

    result = {
        "sourceName": source_name,
        "backend": "pillow-stub",
        "outputPath": str(output_path),
        "downloadUrl": f"/standalone/files/{output_path.name}",
        "width": width,
        "height": height,
        "scale": scale,
        "inputKept": bool(input_path),
    }
    if input_path:
        result["inputPath"] = str(input_path)
    return result


@app.post("/standalone/upscale")
async def standalone_upscale(
    request: Request,
    file: list[UploadFile] = File(...),
    scale: int = Form(2),
    outputName: str = Form(""),
    keepInput: bool = Form(False),
) -> Any:
    scale = ensure_scale(int(scale))
    uploads = [item for item in file if item.filename]
    if not uploads:
        raise HTTPException(status_code=400, detail="At least one image file is required")

    results = []
    errors = []
    for upload in uploads:
        try:
            results.append(await process_standalone_upload(upload, scale, outputName, keepInput))
        except HTTPException as exc:
            errors.append({
                "sourceName": Path(upload.filename or "upload").name,
                "statusCode": exc.status_code,
                "error": str(exc.detail),
            })

    if not results:
        detail = errors[0]["error"] if errors else "No images were upscaled"
        raise HTTPException(status_code=400, detail=detail)

    response: Dict[str, Any] = {
        "status": "partial" if errors else "success",
        "mode": "standalone",
        "backend": "pillow-stub",
        "count": len(uploads),
        "succeeded": len(results),
        "results": results,
        "errors": errors,
        "scale": scale,
    }
    if len(results) == 1:
        response.update(results[0])
    if wants_html_response(request):
        return HTMLResponse(render_standalone_result_page(response))
    return response


@app.get("/standalone/files/{filename}")
def standalone_file(filename: str):
    safe_name = Path(filename).name
    if safe_name != filename or not is_valid_output_filename(safe_name):
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = standalone_output_dir() / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, media_type="image/webp", filename=safe_name)


@app.post("/upscale")
def upscale(payload: UpscalePayload) -> Dict[str, Any]:
    if payload.contract != CONTRACT:
        raise HTTPException(status_code=400, detail="Unsupported upscale contract")
    if payload.probe:
        return probe_response()
    scale = ensure_scale(payload.scale)

    input_path = resolve_allowed_path(payload.inputPath, must_exist=True)
    output_path = resolve_allowed_path(payload.outputPath)
    width, height = save_upscaled_image(input_path, output_path, scale)

    return {
        "status": "success",
        "contract": CONTRACT,
        "backend": "pillow-stub",
        "modelAvailable": False,
        "outputPath": str(output_path),
        "width": width,
        "height": height,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local AI_Generator upscale HTTP stub.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--allowed-root", default=str(Path.cwd() / "outputs"))
    parser.add_argument("--output-dir", default="", help="Standalone results folder. Must stay under --allowed-root.")
    args = parser.parse_args()

    if args.host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("This runner is intended for localhost only. Use 127.0.0.1 or localhost.")

    os.environ["UPSCALE_ALLOWED_ROOT"] = str(Path(args.allowed_root).expanduser().resolve())
    if args.output_dir:
        os.environ["UPSCALE_STANDALONE_OUTPUT_DIR"] = str(Path(args.output_dir).expanduser().resolve())
    try:
        standalone_output_dir()
    except HTTPException as exc:
        raise SystemExit(str(exc.detail)) from exc

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
