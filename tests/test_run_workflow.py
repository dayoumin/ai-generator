import json
import asyncio
import os
import shutil
import socket
import threading
import time
import unittest
from datetime import datetime, timedelta
from unittest import mock
from pathlib import Path

from fastapi.testclient import TestClient

import app


class RunWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app.app)
        self.project = "kemi"
        self.runs_dir = Path(app.resolve_runs_dir(self.project))
        self.created_run_ids = []

    def tearDown(self):
        for run_id in self.created_run_ids:
            shutil.rmtree(self.runs_dir / run_id, ignore_errors=True)
        with app.UPSCALE_JOB_LOCK:
            app.UPSCALE_JOBS.clear()
        app.restore_idle_batch_status()

    def cleanup_project_run(self, project, run_id):
        shutil.rmtree(Path(app.resolve_runs_dir(project)) / run_id, ignore_errors=True)

    def wait_for_upscale_job(self, job_id, timeout=5):
        deadline = time.time() + timeout
        payload = None
        while time.time() < deadline:
            response = self.client.get(f"/api/upscale/jobs/{job_id}")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            if payload["status"] in {"success", "partial", "error", "cancelled"}:
                return payload
            time.sleep(0.05)
        self.fail(f"Upscale job did not finish: {payload}")

    def get_free_local_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    def start_uvicorn_server(self, fastapi_app, port):
        import uvicorn

        config = uvicorn.Config(fastapi_app, host="127.0.0.1", port=port, log_level="warning")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        deadline = time.time() + 5
        while not server.started and time.time() < deadline:
            time.sleep(0.05)
        self.assertTrue(server.started)
        return server, thread

    def write_run(self, run_id, *, project=None, parent_run_id=None):
        project = project or self.project
        run_dir = Path(app.resolve_runs_dir(project)) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        self.created_run_ids.append(run_id)
        metadata = {}
        if parent_run_id:
            metadata["retry_from_run_id"] = parent_run_id
            metadata["retry_source"] = "review-suggestion"
        record = {
            "runId": run_id,
            "projectId": project,
            "mode": "assisted",
            "providerId": "comfyui",
            "createdAt": "2026-04-11T12:00:00",
            "updatedAt": "2026-04-11T12:00:00",
            "request": {
                "templateId": "duo-template",
                "sceneSpec": {
                    "scene": {
                        "situation": "coffee spill",
                        "background": "cafe",
                    },
                    "visual": {
                        "lighting": "warm indoor",
                    },
                },
                "prompts": [{"prompt": "seed prompt"}],
                "outputTypes": ["thumb"],
                "generationParams": {
                    "aspectRatio": "16:9",
                    "steps": 20,
                    "batchCount": 1,
                    "negativePrompt": "blurry",
                    "extraPositive": "soft pastel",
                },
                "metadata": metadata,
            },
            "referenceAssets": [{"path": "characters/a.png", "slot": "character"}],
            "status": {
                "is_running": False,
                "cancel_requested": False,
                "finish_status": "completed",
                "total": 1,
                "completed": 1,
                "succeeded": 1,
                "warnings": 0,
                "errors": 0,
                "current_item": "",
            },
            "results": [{
                "name": "image-1",
                "type": "thumb",
                "status": "done",
                "review_status": "pending",
                "review_note": "",
            }],
            "logs": [],
            "timing": {"batch_start": None, "image_durations": [], "current_start": None},
        }
        (run_dir / "run.json").write_text(json.dumps(record, ensure_ascii=True, indent=2), encoding="utf-8")
        return record

    def test_validate_generation_rejects_unsupported_provider(self):
        response = self.client.post("/api/generation/validate", json={
            "project": self.project,
            "mode": "assisted",
            "provider_id": "ollama",
            "scene_spec": {"scene": {"situation": "test scene"}},
            "types": ["thumb"],
        })
        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["ok"])
        self.assertIn("Unsupported provider", payload["errors"][0])

    def test_validate_generation_rejects_unconfigured_openai_provider(self):
        adapter = app.PROVIDER_REGISTRY["api-image"]
        with mock.patch.object(adapter, "is_configured", return_value=False), mock.patch.object(
            adapter,
            "configuration_error",
            return_value="Set OPENAI_API_KEY to enable the OpenAI image provider.",
        ):
            response = self.client.post("/api/generation/validate", json={
                "project": self.project,
                "mode": "assisted",
                "provider_id": "api-image",
                "scene_spec": {"scene": {"situation": "test scene"}},
                "types": ["thumb"],
            })
        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["ok"])
        self.assertIn("OPENAI_API_KEY", payload["errors"][0])

    def test_validate_generation_warns_when_api_image_ignores_custom_seed(self):
        adapter = app.PROVIDER_REGISTRY["api-image"]
        with mock.patch.object(adapter, "is_configured", return_value=False), mock.patch.object(
            adapter,
            "configuration_error",
            return_value="Set OPENAI_API_KEY to enable the OpenAI image provider.",
        ):
            response = self.client.post("/api/generation/validate", json={
                "project": self.project,
                "mode": "direct",
                "provider_id": "api-image",
                "prompts": [{"prompt": "test prompt", "seed": 12345}],
                "types": ["thumb"],
            })
        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["ok"])
        self.assertTrue(any("사용자 지정 프롬프트 seed 값을 무시합니다" in item for item in payload["warnings"]))

    def test_validate_generation_uses_resolved_provider_for_seed_warning_on_error(self):
        adapter = app.PROVIDER_REGISTRY["api-image"]
        mock_config = {
            "id": "mock-project",
            "name": "Mock Project",
            "sourceDir": "",
            "promptsDir": str(Path(app.BASE_DIR) / "kemi" / "prompts"),
            "defaultPromptFile": "",
            "referenceAssetsDir": str(Path(app.BASE_DIR) / "kemi" / "reference-assets"),
            "workflowMode": "prompt-first",
            "generation": {},
            "provider": "api-image",
            "supportedProviders": ["api-image"],
            "referencePolicy": {},
            "capabilities": {"supportsReferenceAssets": False},
        }
        with mock.patch.object(adapter, "is_configured", return_value=True), mock.patch(
            "app.load_project_config",
            return_value=mock_config,
        ):
            response = self.client.post("/api/generation/validate", json={
                "project": "mock-project",
                "mode": "direct",
                "operator_mode": "codex-conversation",
                "prompts": [{"prompt": "test prompt", "seed": 12345}],
                "types": ["thumb"],
            })
        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["ok"])
        self.assertIn("Codex conversation operator requires assisted mode", payload["errors"][0])
        self.assertTrue(any("사용자 지정 프롬프트 seed 값을 무시합니다" in item for item in payload["warnings"]))

    def test_validate_generation_rejects_codex_operator_in_direct_mode(self):
        response = self.client.post("/api/generation/validate", json={
            "project": self.project,
            "mode": "direct",
            "operator_mode": "codex-conversation",
            "provider_id": "comfyui",
            "prompts": [{"prompt": "test prompt"}],
            "types": ["thumb"],
        })
        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["ok"])
        self.assertIn("Codex conversation operator requires assisted mode", payload["errors"][0])

    def test_projects_api_exposes_provider_and_effective_capabilities(self):
        response = self.client.get("/api/projects")
        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item["id"] == "comfyui" for item in payload["providers"]))
        self.assertTrue(any(item["id"] == "api-image" for item in payload["providers"]))
        kemi = next(item for item in payload["projects"] if item["id"] == "kemi")
        self.assertEqual(kemi["providerInfo"]["id"], "comfyui")
        self.assertIn("supportsAssistedGeneration", kemi["effectiveCapabilities"])
        self.assertIn("api-image", kemi["supportedProviders"])

    def test_health_api_exposes_provider_statuses(self):
        response = self.client.get("/api/health")
        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn("providers", payload)
        self.assertIn("comfyui", payload["providers"])
        self.assertIn("api-image", payload["providers"])
        self.assertEqual(payload["providers"]["api-image"]["label"], "OpenAI 이미지")
        self.assertEqual(payload["providers"]["api-image"]["status"], "not-configured")
        self.assertIn("configured", payload["providers"]["api-image"])
        self.assertIn("available", payload["providers"]["api-image"])
        self.assertIn("upscale", payload)
        self.assertTrue(payload["upscale"]["pillow"]["available"])
        self.assertIn("pid-http", payload["upscale"])

    def test_upscale_health_uses_post_contract_probe(self):
        calls = []

        class FakeResponse:
            status = 200
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc, tb):
                return False
            async def json(self, *args, **kwargs):
                return {
                    "status": "ok",
                    "contract": "ai-generator-upscale-v1",
                    "backend": "pillow-stub",
                }

        class FakeSession:
            def __init__(self, *args, **kwargs):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc, tb):
                return False
            def post(self, endpoint, json):
                calls.append((endpoint, json))
                return FakeResponse()

        with mock.patch.dict("os.environ", {"LOCAL_UPSCALE_ENDPOINT": "http://127.0.0.1:9876/upscale"}), \
             mock.patch("app.aiohttp.ClientSession", FakeSession):
            payload = asyncio.run(app.get_upscale_health("mbti"))
        self.assertTrue(payload["pid-http"]["available"])
        self.assertEqual(calls[0][0], "http://127.0.0.1:9876/upscale")
        self.assertTrue(calls[0][1]["probe"])
        self.assertEqual(calls[0][1]["contract"], "ai-generator-upscale-v1")

    def test_upscale_health_rejects_missing_post_contract(self):
        class FakeResponse:
            status = 405
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc, tb):
                return False

        class FakeSession:
            def __init__(self, *args, **kwargs):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc, tb):
                return False
            def post(self, endpoint, json):
                return FakeResponse()

        with mock.patch.dict("os.environ", {"LOCAL_UPSCALE_ENDPOINT": "http://127.0.0.1:9876/upscale"}), \
             mock.patch("app.aiohttp.ClientSession", FakeSession):
            payload = asyncio.run(app.get_upscale_health("mbti"))
        self.assertFalse(payload["pid-http"]["available"])
        self.assertIn("POST probe HTTP 405", payload["pid-http"]["reason"])

    def test_upscale_health_rejects_contract_mismatch(self):
        class FakeResponse:
            status = 200
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc, tb):
                return False
            async def json(self, *args, **kwargs):
                return {"status": "ok", "contract": "other-contract"}

        class FakeSession:
            def __init__(self, *args, **kwargs):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc, tb):
                return False
            def post(self, endpoint, json):
                return FakeResponse()

        with mock.patch.dict("os.environ", {"LOCAL_UPSCALE_ENDPOINT": "http://127.0.0.1:9876/upscale"}), \
             mock.patch("app.aiohttp.ClientSession", FakeSession):
            payload = asyncio.run(app.get_upscale_health("mbti"))
        self.assertFalse(payload["pid-http"]["available"])
        self.assertIn("contract mismatch", payload["pid-http"]["reason"])

    def test_request_summary_persists_operator_mode(self):
        req = app.StartBatchRequest(
            project=self.project,
            mode="assisted",
            operator_mode="codex-conversation",
            provider_id="comfyui",
            scene_spec=app.SceneSpecPayload(
                scene=app.SceneContextPayload(situation="test scene"),
            ),
            types=["thumb"],
        )
        summary = app.build_request_summary(req)
        self.assertEqual(summary["operatorMode"], "codex-conversation")

    def test_output_types_are_normalized_consistently(self):
        req = app.StartBatchRequest(
            project=self.project,
            mode="assisted",
            scene_spec=app.SceneSpecPayload(
                scene=app.SceneContextPayload(situation="test scene"),
                outputs=["thumb", "foo", "hero", "thumb"],
            ),
            types=["thumb", "foo", "thumb"],
            batch_count=1,
            steps=20,
        )
        app.validate_generation_request(req)
        preflight = app.build_preflight_validation(req)
        summary = app.build_request_summary(req)
        self.assertEqual(preflight["summary"]["outputTypes"], ["thumb"])
        self.assertEqual(summary["outputTypes"], ["thumb"])
        self.assertIn("effectiveCapabilities", preflight["summary"])

    def test_upscale_endpoint_allows_only_exact_local_http_hosts(self):
        self.assertTrue(app.is_local_http_endpoint("http://127.0.0.1:9000/upscale"))
        self.assertTrue(app.is_local_http_endpoint("http://localhost:9000/upscale"))
        self.assertFalse(app.is_local_http_endpoint("https://127.0.0.1:9000/upscale"))
        self.assertFalse(app.is_local_http_endpoint("http://localhost.evil.test/upscale"))
        self.assertFalse(app.is_local_http_endpoint("http://127.0.0.1.evil.test/upscale"))

    def test_pid_http_runner_stub_probe_and_upscale(self):
        from PIL import Image
        from scripts import pid_http_runner_stub

        root = Path(app.OUTPUT_DIR) / self.project / "runner-stub"
        source_path = root / "input.png"
        output_path = root / "output.webp"
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (6, 4), (60, 80, 100)).save(source_path)

        try:
            runner_client = TestClient(pid_http_runner_stub.app)
            with mock.patch.dict(os.environ, {"UPSCALE_ALLOWED_ROOT": str(root)}):
                probe = runner_client.post("/upscale", json={
                    "probe": True,
                    "contract": "ai-generator-upscale-v1",
                    "inputPath": "",
                    "outputPath": "",
                    "scale": 2,
                })
                self.assertEqual(probe.status_code, 200)
                self.assertEqual(probe.json()["contract"], "ai-generator-upscale-v1")

                response = runner_client.post("/upscale", json={
                    "contract": "ai-generator-upscale-v1",
                    "inputPath": str(source_path),
                    "outputPath": str(output_path),
                    "scale": 2,
                    "engine": "pid-http",
                })
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["status"], "success")
            self.assertEqual(payload["outputPath"], str(output_path.resolve()))
            with Image.open(output_path) as saved:
                self.assertEqual(saved.size, (12, 8))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pid_http_runner_stub_rejects_paths_outside_allowed_root(self):
        from scripts import pid_http_runner_stub

        root = Path(app.OUTPUT_DIR) / self.project / "runner-stub-allowed"
        outside = Path(app.OUTPUT_DIR) / self.project / "runner-stub-outside.png"
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        outside.write_text("not an image", encoding="utf-8")
        try:
            runner_client = TestClient(pid_http_runner_stub.app)
            with mock.patch.dict(os.environ, {"UPSCALE_ALLOWED_ROOT": str(root)}):
                response = runner_client.post("/upscale", json={
                    "contract": "ai-generator-upscale-v1",
                    "inputPath": str(outside),
                    "outputPath": str(root / "output.webp"),
                    "scale": 2,
                    "engine": "pid-http",
                })
            self.assertEqual(response.status_code, 400)
            self.assertIn("Path must stay under", response.json()["detail"])
        finally:
            shutil.rmtree(root, ignore_errors=True)
            outside.unlink(missing_ok=True)

    def test_external_upscale_image_bytes_are_written_as_webp(self):
        from io import BytesIO
        from PIL import Image

        out_path = Path(app.OUTPUT_DIR) / self.project / "upscaled" / "unittest-reencoded.webp"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            buf = BytesIO()
            Image.new("RGB", (11, 7), (10, 20, 30)).save(buf, format="PNG")
            width, height = app.write_image_bytes_as_webp(buf.getvalue(), str(out_path))
            self.assertEqual((width, height), (11, 7))
            with Image.open(out_path) as saved:
                self.assertEqual(saved.format, "WEBP")
        finally:
            out_path.unlink(missing_ok=True)

    def test_uploaded_image_can_be_upscaled_without_run(self):
        from io import BytesIO
        from PIL import Image

        project = "mbti"
        stem = "unittest-upload-upscale"
        input_dir = Path(app.OUTPUT_DIR) / project / "upscale-inputs"
        output_dir = Path(app.OUTPUT_DIR) / project / "upscaled"
        for path in input_dir.glob(f"{stem}*"):
            path.unlink(missing_ok=True)
        for path in output_dir.glob(f"{stem}*"):
            path.unlink(missing_ok=True)

        buf = BytesIO()
        Image.new("RGB", (13, 9), (40, 80, 120)).save(buf, format="PNG")
        run_id_to_cleanup = None

        try:
            response = self.client.post(
                "/api/upscale/upload",
                data={"project": project, "scale": "2", "engine": "pillow"},
                files={"file": (f"{stem}.png", buf.getvalue(), "image/png")},
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["status"], "success")
            self.assertEqual(payload["engine"], "pillow")
            self.assertEqual(payload["upscaled"][0]["source"], "upload")
            self.assertEqual(payload["upscaled"][0]["width"], 26)
            self.assertEqual(payload["upscaled"][0]["height"], 18)
            self.assertIn("versionId", payload["upscaled"][0])
            run_id_to_cleanup = payload["runId"]
            self.assertTrue((Path(app.resolve_runs_dir(project)) / run_id_to_cleanup / "run.json").exists())
            self.assertTrue((Path(payload["upscaled"][0]["path"])).exists())
        finally:
            if run_id_to_cleanup:
                self.cleanup_project_run(project, run_id_to_cleanup)
            for path in input_dir.glob(f"{stem}*"):
                path.unlink(missing_ok=True)
            for path in output_dir.glob(f"{stem}*"):
                path.unlink(missing_ok=True)

    def test_uploaded_cmyk_image_is_normalized_before_upscale(self):
        from io import BytesIO
        from PIL import Image

        project = "mbti"
        stem = "unittest-upload-cmyk"
        input_dir = Path(app.OUTPUT_DIR) / project / "upscale-inputs"
        output_dir = Path(app.OUTPUT_DIR) / project / "upscaled"
        for path in input_dir.glob(f"{stem}*"):
            path.unlink(missing_ok=True)
        for path in output_dir.glob(f"{stem}*"):
            path.unlink(missing_ok=True)

        buf = BytesIO()
        Image.new("CMYK", (8, 6), (0, 80, 120, 0)).save(buf, format="JPEG")
        run_id_to_cleanup = None

        try:
            response = self.client.post(
                "/api/upscale/upload",
                data={"project": project, "scale": "2", "engine": "pillow"},
                files={"file": (f"{stem}.jpg", buf.getvalue(), "image/jpeg")},
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["upscaled"][0]["width"], 16)
            self.assertEqual(payload["upscaled"][0]["height"], 12)
            run_id_to_cleanup = payload["runId"]
        finally:
            if run_id_to_cleanup:
                self.cleanup_project_run(project, run_id_to_cleanup)
            for path in input_dir.glob(f"{stem}*"):
                path.unlink(missing_ok=True)
            for path in output_dir.glob(f"{stem}*"):
                path.unlink(missing_ok=True)

    def test_uploaded_upscale_job_reports_progress_and_result(self):
        from io import BytesIO
        from PIL import Image

        project = "mbti"
        stem = "unittest-upload-job"
        input_dir = Path(app.OUTPUT_DIR) / project / "upscale-inputs"
        output_dir = Path(app.OUTPUT_DIR) / project / "upscaled"
        for path in input_dir.glob(f"{stem}*"):
            path.unlink(missing_ok=True)
        for path in output_dir.glob(f"{stem}*"):
            path.unlink(missing_ok=True)

        buf = BytesIO()
        Image.new("RGB", (9, 5), (70, 90, 110)).save(buf, format="PNG")
        run_id_to_cleanup = None

        try:
            response = self.client.post(
                "/api/upscale/upload/jobs",
                data={"project": project, "scale": "2", "engine": "pillow"},
                files={"file": (f"{stem}.png", buf.getvalue(), "image/png")},
            )
            self.assertEqual(response.status_code, 200)
            started = response.json()
            self.assertEqual(started["kind"], "upload")
            finished = self.wait_for_upscale_job(started["jobId"])
            self.assertEqual(finished["status"], "success")
            self.assertEqual(finished["completed"], 2)
            self.assertEqual(finished["succeeded"], 1)
            self.assertEqual(finished["result"]["upscaled"][0]["width"], 18)
            self.assertEqual(finished["result"]["upscaled"][0]["height"], 10)
            run_id_to_cleanup = finished["result"]["runId"]
            run_file = Path(app.resolve_runs_dir(project)) / run_id_to_cleanup / "run.json"
            self.assertTrue(run_file.exists())
            run_record = json.loads(run_file.read_text(encoding="utf-8"))
            self.assertEqual(run_record["mode"], "upscale-upload")
            self.assertEqual(run_record["results"][0]["_upscaled"]["source"]["versionId"], finished["result"]["upscaled"][0]["versionId"])
            manifest = self.client.get("/api/manifest", params={"project": project, "run_id": run_id_to_cleanup}).json()
            self.assertEqual(manifest["runId"], run_id_to_cleanup)
            self.assertIn("source", manifest["items"][0]["variants"])
            self.assertEqual(manifest["items"][0]["variants"]["source"]["upscaled"]["width"], 18)
        finally:
            if run_id_to_cleanup:
                self.cleanup_project_run(project, run_id_to_cleanup)
            for path in input_dir.glob(f"{stem}*"):
                path.unlink(missing_ok=True)
            for path in output_dir.glob(f"{stem}*"):
                path.unlink(missing_ok=True)

    def test_run_upscale_job_reports_progress_and_updates_run(self):
        from PIL import Image

        project = self.project
        run_id = "unittest-upscale-job"
        source_dir = Path(app.OUTPUT_DIR) / project / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        source_path = source_dir / f"{run_id}.png"
        self.cleanup_project_run(project, run_id)
        Image.new("RGB", (12, 8), (20, 30, 40)).save(source_path)

        run_dir = Path(app.resolve_runs_dir(project)) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "runId": run_id,
            "projectId": project,
            "status": {"is_running": False, "succeeded": 1},
            "results": [{
                "name": "upscale job source",
                "status": "success",
                "_project": project,
                "local_path": str(source_path),
                "width": 12,
                "height": 8,
            }],
            "logs": [],
        }
        (run_dir / "run.json").write_text(json.dumps(record), encoding="utf-8")

        try:
            response = self.client.post("/api/upscale/jobs", json={
                "project": project,
                "run_id": run_id,
                "source": "source",
                "scale": 2,
                "engine": "pillow",
            })
            self.assertEqual(response.status_code, 200)
            started = response.json()
            self.assertEqual(started["kind"], "run")
            finished = self.wait_for_upscale_job(started["jobId"])
            self.assertEqual(finished["status"], "success")
            self.assertEqual(finished["completed"], 1)
            self.assertEqual(finished["result"]["runId"], run_id)
            saved = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["results"][0]["_upscaled"]["source"]["width"], 24)
            self.assertIn("versionId", saved["results"][0]["_upscaled"]["source"])
            self.assertEqual(len(saved["results"][0]["_upscale_history"]), 1)
        finally:
            self.cleanup_project_run(project, run_id)
            source_path.unlink(missing_ok=True)
            for path in (Path(app.OUTPUT_DIR) / project / "upscaled").glob(f"{run_id}*"):
                path.unlink(missing_ok=True)

    def test_pid_http_engine_calls_local_runner_and_updates_run(self):
        from PIL import Image
        from scripts import pid_http_runner_stub

        project = self.project
        run_id = "unittest-pid-http-runner"
        source_dir = Path(app.OUTPUT_DIR) / project / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        source_path = source_dir / f"{run_id}.png"
        self.cleanup_project_run(project, run_id)
        Image.new("RGB", (10, 6), (25, 45, 65)).save(source_path)

        run_dir = Path(app.resolve_runs_dir(project)) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "runId": run_id,
            "projectId": project,
            "status": {"is_running": False, "succeeded": 1},
            "results": [{
                "name": run_id,
                "status": "success",
                "_project": project,
                "local_path": str(source_path),
                "width": 10,
                "height": 6,
            }],
            "logs": [],
        }
        (run_dir / "run.json").write_text(json.dumps(record), encoding="utf-8")

        port = self.get_free_local_port()
        with mock.patch.dict(os.environ, {
            "UPSCALE_ALLOWED_ROOT": str(Path(app.OUTPUT_DIR).resolve()),
            "LOCAL_UPSCALE_ENDPOINT": f"http://127.0.0.1:{port}/upscale",
        }):
            server, thread = self.start_uvicorn_server(pid_http_runner_stub.app, port)
            try:
                response = self.client.post("/api/upscale", json={
                    "project": project,
                    "run_id": run_id,
                    "source": "source",
                    "scale": 2,
                    "engine": "pid-http",
                })
            finally:
                server.should_exit = True
                thread.join(timeout=5)

        try:
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["status"], "success")
            self.assertEqual(payload["engine"], "pid-http")
            self.assertEqual(payload["upscaled"][0]["width"], 20)
            self.assertEqual(payload["upscaled"][0]["height"], 12)
            saved = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["results"][0]["_upscaled"]["source"]["engine"], "pid-http")
            self.assertEqual(saved["results"][0]["_upscaled"]["source"]["width"], 20)
        finally:
            self.cleanup_project_run(project, run_id)
            source_path.unlink(missing_ok=True)
            for path in (Path(app.OUTPUT_DIR) / project / "upscaled").glob(f"{run_id}*"):
                path.unlink(missing_ok=True)

    def test_run_upscale_merge_preserves_existing_history(self):
        project = self.project
        run_id = "unittest-upscale-merge"
        self.cleanup_project_run(project, run_id)
        run_dir = Path(app.resolve_runs_dir(project)) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "runId": run_id,
            "projectId": project,
            "status": {"is_running": False, "succeeded": 1},
            "results": [{
                "name": "merge source",
                "status": "success",
                "_project": project,
                "_upscaled": {"source": {"versionId": "old-v", "path": "old.webp", "sourceKey": "source"}},
                "_upscale_history": [{"versionId": "old-v", "path": "old.webp", "sourceKey": "source"}],
            }],
            "logs": [],
        }
        (run_dir / "run.json").write_text(json.dumps(record), encoding="utf-8")
        try:
            app.merge_upscale_updates_into_run_record(
                project,
                run_id,
                [{
                    "_upscaled": {"source": {"versionId": "new-v", "path": "new.webp", "sourceKey": "source"}},
                    "_upscale_history": [{"versionId": "new-v", "path": "new.webp", "sourceKey": "source"}],
                }],
                "[00:00:00] OK merge test",
            )
            saved = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["results"][0]["_upscaled"]["source"]["versionId"], "new-v")
            history_versions = [item["versionId"] for item in saved["results"][0]["_upscale_history"]]
            self.assertEqual(history_versions, ["old-v", "new-v"])
        finally:
            self.cleanup_project_run(project, run_id)

    def test_select_upscale_version_updates_current_variant(self):
        project = self.project
        run_id = "unittest-select-upscale-version"
        self.cleanup_project_run(project, run_id)
        run_dir = Path(app.resolve_runs_dir(project)) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "runId": run_id,
            "projectId": project,
            "status": {"is_running": False, "succeeded": 1},
            "results": [{
                "name": "version source",
                "status": "success",
                "_project": project,
                "_upscaled": {"source": {"versionId": "new-v", "path": "new.webp", "sourceKey": "source", "width": 20}},
                "_upscale_history": [
                    {"versionId": "old-v", "path": "old.webp", "sourceKey": "source", "width": 10},
                    {"versionId": "new-v", "path": "new.webp", "sourceKey": "source", "width": 20},
                ],
            }],
            "logs": [],
        }
        (run_dir / "run.json").write_text(json.dumps(record), encoding="utf-8")
        try:
            response = self.client.post(
                "/api/results/0/upscale-version",
                params={"project": project, "run_id": run_id},
                json={"sourceKey": "source", "versionId": "old-v"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["versionId"], "old-v")
            saved = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["results"][0]["_upscaled"]["source"]["versionId"], "old-v")
            self.assertEqual(saved["results"][0]["_upscaled"]["source"]["width"], 10)

            missing = self.client.post(
                "/api/results/0/upscale-version",
                params={"project": project, "run_id": run_id},
                json={"sourceKey": "source", "versionId": "missing-v"},
            )
            self.assertEqual(missing.status_code, 404)
        finally:
            self.cleanup_project_run(project, run_id)

    def test_uploaded_upscale_cancel_after_processing_stays_cancelled(self):
        from io import BytesIO
        from PIL import Image

        project = "mbti"
        stem = "unittest-upload-cancel-after"
        input_dir = Path(app.OUTPUT_DIR) / project / "upscale-inputs"
        output_dir = Path(app.OUTPUT_DIR) / project / "upscaled"
        for path in input_dir.glob(f"{stem}*"):
            path.unlink(missing_ok=True)
        for path in output_dir.glob(f"{stem}*"):
            path.unlink(missing_ok=True)

        buf = BytesIO()
        Image.new("RGB", (7, 5), (30, 40, 50)).save(buf, format="PNG")
        job = app.make_upscale_job("upload", project, total=2)

        async def fake_upscale(_input_path, _output_path, _scale, _config):
            app.update_upscale_job(job["jobId"], cancelRequested=True)
            return 14, 10

        try:
            with mock.patch("app.upscale_image_file", side_effect=fake_upscale):
                payload = asyncio.run(app.execute_uploaded_upscale(
                    project,
                    2,
                    "pillow",
                    f"{stem}.png",
                    buf.getvalue(),
                    job_id=job["jobId"],
                ))
            self.assertEqual(payload["status"], "cancelled")
            self.assertEqual(payload["upscaled"], [])
            job_status = app.get_upscale_job(job["jobId"])
            self.assertEqual(job_status["status"], "cancelled")
            self.assertIsNone(job_status.get("result", {}).get("runId"))
        finally:
            with app.UPSCALE_JOB_LOCK:
                app.UPSCALE_JOBS.pop(job["jobId"], None)
            for path in input_dir.glob(f"{stem}*"):
                path.unlink(missing_ok=True)
            for path in output_dir.glob(f"{stem}*"):
                path.unlink(missing_ok=True)

    def test_completed_upscale_jobs_are_cleaned_after_ttl(self):
        job = app.make_upscale_job("run", self.project)
        try:
            old = datetime.now() - timedelta(seconds=app.UPSCALE_JOB_TTL_SECONDS + 1)
            with app.UPSCALE_JOB_LOCK:
                app.UPSCALE_JOBS[job["jobId"]]["status"] = "success"
                app.UPSCALE_JOBS[job["jobId"]]["updatedAt"] = old.isoformat()
            app.cleanup_upscale_jobs()
            with app.UPSCALE_JOB_LOCK:
                self.assertNotIn(job["jobId"], app.UPSCALE_JOBS)
        finally:
            with app.UPSCALE_JOB_LOCK:
                app.UPSCALE_JOBS.pop(job["jobId"], None)

    def test_upscale_file_cleanup_dry_run_and_delete_keeps_referenced_files(self):
        project = self.project
        run_id = "unittest-upscale-cleanup"
        self.cleanup_project_run(project, run_id)
        input_dir = Path(app.OUTPUT_DIR) / project / "upscale-inputs"
        output_dir = Path(app.OUTPUT_DIR) / project / "upscaled"
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        stale_unreferenced = output_dir / "cleanup-stale-unreferenced.webp"
        stale_referenced = output_dir / "cleanup-stale-referenced.webp"
        stale_input_referenced = input_dir / "cleanup-stale-input.webp"
        fresh_unreferenced = output_dir / "cleanup-fresh-unreferenced.webp"
        for path in [stale_unreferenced, stale_referenced, stale_input_referenced, fresh_unreferenced]:
            path.write_bytes(b"test")
        old_time = time.time() - (9 * 24 * 60 * 60)
        os.utime(stale_unreferenced, (old_time, old_time))
        os.utime(stale_referenced, (old_time, old_time))
        os.utime(stale_input_referenced, (old_time, old_time))

        run_dir = Path(app.resolve_runs_dir(project)) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "runId": run_id,
            "projectId": project,
            "status": {"is_running": False, "succeeded": 1},
            "results": [{
                "name": "cleanup source",
                "status": "success",
                "_project": project,
                "local_path": str(stale_input_referenced),
                "_upscaled": {"source": {"path": str(stale_referenced), "sourceKey": "source"}},
                "_upscale_history": [{"path": str(stale_referenced), "sourceKey": "source"}],
            }],
            "logs": [],
        }
        (run_dir / "run.json").write_text(json.dumps(record), encoding="utf-8")

        try:
            dry_run = self.client.post("/api/upscale/cleanup", json={
                "project": project,
                "older_than_days": 7,
                "dry_run": True,
            })
            self.assertEqual(dry_run.status_code, 200)
            dry_payload = dry_run.json()
            self.assertEqual(dry_payload["candidateCount"], 1)
            self.assertEqual(Path(dry_payload["candidates"][0]["path"]), stale_unreferenced)
            self.assertTrue(stale_unreferenced.exists())

            actual = self.client.post("/api/upscale/cleanup", json={
                "project": project,
                "older_than_days": 7,
                "dry_run": False,
            })
            self.assertEqual(actual.status_code, 200)
            payload = actual.json()
            self.assertEqual(payload["deleted"], 1)
            self.assertFalse(stale_unreferenced.exists())
            self.assertTrue(stale_referenced.exists())
            self.assertTrue(stale_input_referenced.exists())
            self.assertTrue(fresh_unreferenced.exists())
        finally:
            self.cleanup_project_run(project, run_id)
            for path in [stale_unreferenced, stale_referenced, stale_input_referenced, fresh_unreferenced]:
                path.unlink(missing_ok=True)

    def test_upscale_job_cancel_endpoint_marks_job(self):
        job = app.make_upscale_job("run", self.project)
        try:
            response = self.client.post(f"/api/upscale/jobs/{job['jobId']}/cancel")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload["cancelRequested"])
            self.assertEqual(payload["status"], "cancelling")
        finally:
            with app.UPSCALE_JOB_LOCK:
                app.UPSCALE_JOBS.pop(job["jobId"], None)

    def test_run_upscale_all_failures_returns_error(self):
        from PIL import Image

        project = self.project
        run_id = "unittest-upscale-all-failures"
        source_dir = Path(app.OUTPUT_DIR) / project / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        source_path = source_dir / f"{run_id}.png"
        self.cleanup_project_run(project, run_id)
        Image.new("RGB", (10, 10), (20, 30, 40)).save(source_path)

        run_dir = Path(app.resolve_runs_dir(project)) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "runId": run_id,
            "projectId": project,
            "status": {"is_running": False, "succeeded": 1},
            "results": [{
                "name": "upscale failure source",
                "status": "success",
                "_project": project,
                "local_path": str(source_path),
                "width": 10,
                "height": 10,
            }],
            "logs": [],
        }
        (run_dir / "run.json").write_text(json.dumps(record), encoding="utf-8")

        try:
            response = self.client.post("/api/upscale", json={
                "project": project,
                "run_id": run_id,
                "source": "source",
                "scale": 2,
                "engine": "unsupported-test-engine",
            })
            self.assertEqual(response.status_code, 400)
            self.assertIn("Upscale failed for all selected images", response.json()["detail"])
            saved = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            self.assertIn("ERROR Upscaled 0 variants", saved["logs"][-1])
        finally:
            self.cleanup_project_run(project, run_id)
            source_path.unlink(missing_ok=True)

    def test_review_route_updates_historical_run_and_rejects_project_mismatch(self):
        self.write_run("review-run")
        response = self.client.post(
            "/api/results/0/review",
            params={"project": self.project, "run_id": "review-run"},
            json={"status": "approved", "note": "better framing"},
        )
        self.assertEqual(response.status_code, 200)
        updated = app.load_run_record(self.project, "review-run")
        self.assertEqual(updated["results"][0]["review_status"], "approved")
        self.assertEqual(updated["results"][0]["review_note"], "better framing")

        mismatch = self.client.post(
            "/api/results/0/review",
            params={"project": "mbti", "run_id": "review-run"},
            json={"status": "approved", "note": "x"},
        )
        self.assertEqual(mismatch.status_code, 404)

    def test_codex_import_crop_manifest_review_simulation(self):
        project = "mbti"
        run_id = "unittest-codex-import-flow"
        request_id = "codex-unittest-reaction-v1"
        imports_dir = Path(app.BASE_DIR) / "imports"
        imports_dir.mkdir(parents=True, exist_ok=True)
        source_path = imports_dir / "unittest-codex-source.png"
        self.cleanup_project_run(project, run_id)
        for path in (Path(app.OUTPUT_DIR) / project / "source").glob(f"{request_id}*"):
            path.unlink(missing_ok=True)
        for path in (Path(app.OUTPUT_DIR) / project / "cropped").glob(f"{request_id}*"):
            path.unlink(missing_ok=True)
        for path in (Path(app.OUTPUT_DIR) / project / "upscaled").glob(f"{request_id}*"):
            path.unlink(missing_ok=True)

        from PIL import Image
        Image.new("RGB", (640, 640), (120, 160, 200)).save(source_path)

        try:
            payload = {
                "project": project,
                "run_id": run_id,
                "run_name": "Unit test Codex import",
                "images": [{
                    "source_path": str(source_path),
                    "request_id": request_id,
                    "content_type": "reaction",
                    "content_id": "situation-reaction-unittest",
                    "asset_kind": "character-scene",
                    "category": "reaction",
                    "slots": ["feed-media", "option-image", "share-og"],
                    "target_storage": {
                        "type": "r2",
                        "keyPrefix": "reaction/situation-reaction-unittest",
                    },
                    "prompt": "relatable meeting reaction scene",
                    "negative_prompt": "text, logo, watermark",
                    "style_preset": "codex-generated",
                    "alt_text": "meeting reaction",
                    "provider_params": {"sourceProvider": "codex"},
                    "review_policy": {"noText": True, "cropSafe": True},
                    "metadata": {"test": True},
                }],
            }
            imported = self.client.post("/api/codex-import", json=payload)
            self.assertEqual(imported.status_code, 200)
            self.assertEqual(imported.json()["runId"], run_id)

            duplicate = self.client.post("/api/codex-import", json=payload)
            self.assertEqual(duplicate.status_code, 409)

            cropped = self.client.post("/api/crop", params={"project": project, "run_id": run_id})
            self.assertEqual(cropped.status_code, 200)
            self.assertEqual(cropped.json()["status"], "success")

            upscaled = self.client.post("/api/upscale", json={
                "project": project,
                "run_id": run_id,
                "source": "crops",
                "scale": 2,
                "engine": "pillow",
                "crop_names": ["feed-media"],
            })
            self.assertEqual(upscaled.status_code, 200)
            self.assertEqual(upscaled.json()["status"], "success")
            self.assertEqual(len(upscaled.json()["upscaled"]), 1)

            source_upscaled = self.client.post("/api/upscale", json={
                "project": project,
                "run_id": run_id,
                "source": "source",
                "scale": 2,
                "engine": "pillow",
            })
            self.assertEqual(source_upscaled.status_code, 200)
            self.assertEqual(source_upscaled.json()["status"], "success")
            self.assertEqual(source_upscaled.json()["upscaled"][0]["source"], "source")

            missing_crop = self.client.post("/api/upscale", json={
                "project": project,
                "run_id": run_id,
                "source": "crops",
                "scale": 2,
                "engine": "pillow",
                "crop_names": ["does-not-exist"],
            })
            self.assertEqual(missing_crop.status_code, 200)
            self.assertEqual(missing_crop.json()["error"], "No matching images to upscale")

            invalid_source = self.client.post("/api/upscale", json={
                "project": project,
                "run_id": run_id,
                "source": "remote-url",
                "scale": 2,
                "engine": "pillow",
            })
            self.assertEqual(invalid_source.status_code, 400)

            restricted_record = app.load_run_record(project, run_id)
            restricted_record["results"][0]["_upscaled"]["source"]["engine"] = "pid-http"
            app.save_run_record(project, run_id, restricted_record)
            restricted_upload = self.client.post("/api/upload", params={"project": project, "run_id": run_id})
            self.assertEqual(restricted_upload.status_code, 400)
            self.assertIn("Restricted upscale variants", restricted_upload.json()["detail"])

            project_manifest = Path(app.OUTPUT_DIR) / project / "manifest.json"
            project_manifest.write_text('{"sentinel":true}', encoding="utf-8")
            manifest_resp = self.client.get("/api/manifest", params={"project": project, "run_id": run_id})
            self.assertEqual(manifest_resp.status_code, 200)
            manifest = manifest_resp.json()
            self.assertEqual(manifest["runId"], run_id)
            self.assertEqual(manifest["totalImages"], 1)
            item = manifest["items"][0]
            self.assertIn(request_id, item["assetId"])
            self.assertEqual(item["reviewStatus"], "pending")
            self.assertIn("localUrl", item["variants"]["feed-media"])
            self.assertIn(request_id, item["variants"]["feed-media"]["storageKey"])
            self.assertIn("upscaled", item["variants"]["feed-media"])
            self.assertEqual(item["variants"]["feed-media"]["upscaled"]["scale"], 2)
            self.assertEqual(item["variants"]["feed-media"]["upscaled"]["width"], 1600)
            self.assertIn("source", item["variants"])
            self.assertEqual(item["variants"]["source"]["upscaled"]["width"], 1280)
            self.assertEqual(item["variants"]["source"]["upscaled"]["engine"], "pid-http")
            self.assertTrue((Path(app.resolve_runs_dir(project)) / run_id / "manifest.json").exists())
            self.assertEqual(json.loads(project_manifest.read_text(encoding="utf-8")), {"sentinel": True})

            review = self.client.post(
                "/api/results/0/review",
                params={"project": project, "run_id": run_id},
                json={"status": "revision_requested", "note": "needs a clearer expression"},
            )
            self.assertEqual(review.status_code, 200)
            reviewed_manifest = self.client.get("/api/manifest", params={"project": project, "run_id": run_id}).json()
            self.assertEqual(reviewed_manifest["items"][0]["reviewStatus"], "revision_requested")
        finally:
            source_path.unlink(missing_ok=True)
            self.cleanup_project_run(project, run_id)
            for path in (Path(app.OUTPUT_DIR) / project / "source").glob(f"{request_id}*"):
                path.unlink(missing_ok=True)
            for path in (Path(app.OUTPUT_DIR) / project / "cropped").glob(f"{request_id}*"):
                path.unlink(missing_ok=True)
            for path in (Path(app.OUTPUT_DIR) / project / "upscaled").glob(f"{request_id}*"):
                path.unlink(missing_ok=True)

    def test_lineage_route_includes_change_summary(self):
        self.write_run("lineage-root")
        child = self.write_run("lineage-child", parent_run_id="lineage-root")
        child["request"]["sceneSpec"]["scene"]["situation"] = "coffee spill with bigger reaction"
        child["request"]["sceneSpec"]["visual"]["lighting"] = "clear face lighting"
        child["request"]["generationParams"]["extraPositive"] = "soft pastel, sharp face"
        child["referenceAssets"].append({"path": "props/coffee.png", "slot": "prop"})
        (self.runs_dir / "lineage-child" / "run.json").write_text(json.dumps(child, ensure_ascii=True, indent=2), encoding="utf-8")

        response = self.client.get("/api/runs/lineage-child/lineage", params={"project": self.project})
        payload = response.json()
        self.assertEqual(response.status_code, 200)
        child_item = next(item for item in payload["items"] if item["runId"] == "lineage-child")
        self.assertEqual(child_item["retry"]["fromRunId"], "lineage-root")
        self.assertGreater(child_item["changesFromParent"]["count"], 0)
        self.assertIn("상황:", child_item["changesFromParent"]["summary"])

    def test_runs_api_summarizes_camel_case_retry_metadata(self):
        record = self.write_run("camel-retry-run")
        record["request"]["metadata"] = {
            "retryFromRunId": "camel-parent",
            "retrySource": "review-suggestion",
        }
        (self.runs_dir / "camel-retry-run" / "run.json").write_text(
            json.dumps(record, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

        response = self.client.get("/api/runs", params={"project": self.project, "limit": 10})
        payload = response.json()
        self.assertEqual(response.status_code, 200)
        run_item = next(item for item in payload["runs"] if item["runId"] == "camel-retry-run")
        self.assertTrue(run_item["retry"]["isRetry"])
        self.assertEqual(run_item["retry"]["fromRunId"], "camel-parent")
        self.assertEqual(run_item["retry"]["source"], "review-suggestion")

    def test_codex_handoff_endpoint_returns_review_and_retry_context_without_mutation(self):
        self.write_run("handoff-root")
        child = self.write_run("handoff-child", parent_run_id="handoff-root")
        child["results"][0]["review_status"] = "rejected"
        child["results"][0]["review_note"] = "lighting is too dark and expression is weak"
        (self.runs_dir / "handoff-child" / "run.json").write_text(json.dumps(child, ensure_ascii=True, indent=2), encoding="utf-8")

        response = self.client.get("/api/runs/handoff-child/codex-handoff", params={"project": self.project})
        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn("message", payload)
        self.assertEqual(payload["payload"]["runContext"]["runId"], "handoff-child")
        self.assertEqual(payload["payload"]["runContext"]["reviewSummary"]["rejected"], 1)
        self.assertIn("lighting is too dark", payload["message"])
        self.assertIn("promptHints", payload["payload"]["retryContext"]["suggestion"])
        self.assertEqual(payload["payload"]["retryContext"]["lineage"]["runCount"], 2)

        updated = app.load_run_record(self.project, "handoff-child")
        self.assertNotIn("codexHandoff", updated)
        self.assertEqual(updated["updatedAt"], "2026-04-11T12:00:00")

    def test_codex_handoff_endpoint_handles_unknown_provider_in_saved_run(self):
        record = self.write_run("legacy-provider-run")
        record["providerId"] = "legacy-provider"
        (self.runs_dir / "legacy-provider-run" / "run.json").write_text(json.dumps(record, ensure_ascii=True, indent=2), encoding="utf-8")

        response = self.client.get("/api/runs/legacy-provider-run/codex-handoff", params={"project": self.project})
        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["payload"]["execution"]["providerId"], "legacy-provider")
        self.assertEqual(payload["payload"]["execution"]["providerLabel"], "legacy-provider")

    def test_create_initial_run_record_persists_handoff_lineage(self):
        self.write_run("queued-parent")
        self.created_run_ids.append("queued-child")
        request_summary = {
            "templateId": "duo-template",
            "sceneSpec": {
                "scene": {"situation": "retry queued scene", "background": "cafe"},
                "visual": {"lighting": "warm indoor"},
            },
            "prompts": [{"prompt": "retry prompt"}],
            "outputTypes": ["thumb"],
            "generationParams": {"aspectRatio": "16:9", "steps": 20, "batchCount": 1},
            "metadata": {
                "retry_from_run_id": "queued-parent",
                "retry_source": "review-suggestion",
            },
            "operatorMode": "studio",
        }
        app.create_initial_run_record(self.project, "queued-child", "assisted", "comfyui", request_summary, [])
        queued = app.load_run_record(self.project, "queued-child")
        self.assertEqual(queued["codexHandoff"]["payload"]["retryContext"]["lineage"]["runCount"], 2)

    def test_review_save_persists_handoff_with_lineage(self):
        self.write_run("review-handoff-root")
        child = self.write_run("review-handoff-child", parent_run_id="review-handoff-root")
        child["results"][0]["review_status"] = "rejected"
        child["results"][0]["review_note"] = "lighting is too dark and expression is weak"
        (self.runs_dir / "review-handoff-child" / "run.json").write_text(json.dumps(child, ensure_ascii=True, indent=2), encoding="utf-8")

        review_resp = self.client.post(
            "/api/results/0/review",
            params={"project": self.project, "run_id": "review-handoff-child"},
            json={"status": "approved", "note": "keep the stronger expression"},
        )
        self.assertEqual(review_resp.status_code, 200)

        reviewed = app.load_run_record(self.project, "review-handoff-child")
        self.assertEqual(reviewed["codexHandoff"]["payload"]["retryContext"]["lineage"]["runCount"], 2)
        self.assertEqual(reviewed["codexHandoff"]["payload"]["runContext"]["reviewSummary"]["approved"], 1)

    def test_persist_current_run_uses_supplied_snapshot(self):
        self.created_run_ids.append("snapshot-run")
        snapshot = {
            "run_id": "snapshot-run",
            "project": self.project,
            "mode": "assisted",
            "provider_id": "comfyui",
            "request": {
                "templateId": "snapshot-template",
                "sceneSpec": {"scene": {"situation": "snapshot scene"}},
                "prompts": [{"prompt": "snapshot prompt"}],
                "outputTypes": ["thumb"],
                "generationParams": {"aspectRatio": "16:9", "steps": 20, "batchCount": 1},
                "metadata": {},
            },
            "reference_assets": [],
            "is_running": False,
            "cancel_requested": False,
            "finish_status": "success",
            "total": 1,
            "completed": 1,
            "succeeded": 1,
            "warnings": 0,
            "errors": 0,
            "current_item": "Finished",
            "logs": [],
            "results": [],
            "timing": {"batch_start": None, "image_durations": [], "current_start": None},
        }
        app.batch_status.update({
            "run_id": "different-live-run",
            "project": self.project,
            "is_running": True,
        })
        app.persist_current_run(snapshot)
        stored = app.load_run_record(self.project, "snapshot-run")
        self.assertEqual(stored["runId"], "snapshot-run")
        self.assertEqual(stored["status"]["finish_status"], "success")

    def test_claim_batch_start_blocks_second_start_until_restored(self):
        request_summary = {
            "mode": "assisted",
            "projectId": self.project,
            "providerId": "comfyui",
            "operatorMode": "studio",
            "outputTypes": ["thumb"],
            "prompts": [],
            "referenceAssets": [],
            "generationParams": {},
            "metadata": {},
        }
        app.claim_batch_start(self.project, "claimed-run", "assisted", "comfyui", request_summary, [])
        self.assertTrue(app.batch_status["is_running"])
        self.assertEqual(app.batch_status["run_id"], "claimed-run")

        with self.assertRaises(app.HTTPException) as exc:
            app.claim_batch_start(self.project, "second-run", "assisted", "comfyui", request_summary, [])
        self.assertEqual(exc.exception.status_code, 400)

        app.restore_idle_batch_status()
        app.claim_batch_start(self.project, "second-run", "assisted", "comfyui", request_summary, [])
        self.assertEqual(app.batch_status["run_id"], "second-run")

    def test_status_route_does_not_leak_other_project_batch_state(self):
        app.batch_status.update({
            "run_id": "live-kemi",
            "project": "kemi",
            "is_running": True,
            "finish_status": None,
            "total": 1,
            "completed": 0,
            "succeeded": 0,
            "warnings": 0,
            "errors": 0,
            "current_item": "working",
            "logs": [],
            "results": [],
            "timing": {"batch_start": None, "image_durations": [], "current_start": None},
        })
        with mock.patch("app.find_latest_run_record", return_value=None):
            response = self.client.get("/api/batch/status", params={"project": "mbti"})
        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["project"], "mbti")
        self.assertIsNone(payload["run_id"])
        self.assertFalse(payload["is_running"])

    def test_status_route_prefers_persisted_record_when_batch_is_idle(self):
        record = self.write_run("idle-status-run")
        record["status"]["finish_status"] = "success"
        record["status"]["current_item"] = "Persisted final state"
        (self.runs_dir / "idle-status-run" / "run.json").write_text(json.dumps(record, ensure_ascii=True, indent=2), encoding="utf-8")

        app.batch_status.update({
            "run_id": "idle-status-run",
            "project": self.project,
            "is_running": False,
            "finish_status": "error",
            "current_item": "Stale memory state",
            "logs": [],
            "results": [],
            "timing": {"batch_start": None, "image_durations": [], "current_start": None},
        })

        response = self.client.get("/api/batch/status", params={"project": self.project})
        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["finish_status"], "success")
        self.assertEqual(payload["current_item"], "Persisted final state")


if __name__ == "__main__":
    unittest.main()
