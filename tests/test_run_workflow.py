import json
import shutil
import unittest
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
        app.restore_idle_batch_status()

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
