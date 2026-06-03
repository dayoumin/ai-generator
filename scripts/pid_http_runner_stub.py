import argparse
import os
import threading
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


CONTRACT = "ai-generator-upscale-v1"
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
        },
    }


@app.get("/health")
def health() -> Dict[str, Any]:
    return probe_response()


@app.post("/upscale")
def upscale(payload: UpscalePayload) -> Dict[str, Any]:
    if payload.contract != CONTRACT:
        raise HTTPException(status_code=400, detail="Unsupported upscale contract")
    if payload.probe:
        return probe_response()
    if payload.scale not in {2, 4}:
        raise HTTPException(status_code=400, detail="Only x2 and x4 are supported by this stub")

    input_path = resolve_allowed_path(payload.inputPath, must_exist=True)
    output_path = resolve_allowed_path(payload.outputPath)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not RUN_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Runner is busy")
    try:
        from PIL import Image

        with Image.open(input_path) as img:
            source = img.convert("RGBA") if img.mode in {"RGBA", "LA", "P"} else img.convert("RGB")
            resized = source.resize((source.width * payload.scale, source.height * payload.scale), Image.LANCZOS)
            resized.save(output_path, "WEBP", quality=92)
            width, height = resized.size
    finally:
        RUN_LOCK.release()

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
    args = parser.parse_args()

    if args.host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("This runner is intended for localhost only. Use 127.0.0.1 or localhost.")

    os.environ["UPSCALE_ALLOWED_ROOT"] = str(Path(args.allowed_root).expanduser().resolve())

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
