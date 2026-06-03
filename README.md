# Kemi AI Studio (Image Generator)

## Local Upscale Runner (Personal Use)

AI_Generator keeps PiD-style upscaling as a local-only extension. The app does not bundle or download NVIDIA PiD weights, and `pid` / `pid-http` outputs are blocked from R2 upload by default unless the project explicitly enables restricted uploads.

Use the contract stub to verify the web-server path before installing a real model backend:

```powershell
python scripts/pid_http_runner_stub.py --host 127.0.0.1 --port 8765 --allowed-root outputs
$env:LOCAL_UPSCALE_ENDPOINT="http://127.0.0.1:8765/upscale"
python app.py
```

The stub implements `ai-generator-upscale-v1` with Pillow/LANCZOS and is for local contract testing, not PiD image quality. A future real PiD backend should keep the same `POST /upscale` contract, stay bound to `127.0.0.1`, and restrict file reads/writes to the configured `outputs` root.

AI 이미지 배치 생성 + 리뷰 도구. ComfyUI 기반 로컬 생성 + 웹 UI 관리.

> Multi-project integration starts from [docs/project-integration-contract.md](docs/project-integration-contract.md).
> New projects should prepare a project config, image request file, reference assets, output profiles, and an import/sync script.

---

## 모델/업스케일 라이선스 정책

- 현재 기본 후처리는 crop/profile별 리사이즈이며, AI 업스케일러는 아직 기본 기능이 아니다.
- NVIDIA PiD는 개인 로컬 사용 및 내부 품질 평가 후보로 둔다. 현재 모델 카드 기준 비상업적 연구/평가용 라이선스이므로, 서버형 공개 웹 서비스에 모델을 내장해서 제공하지 않는다.
- 나중에 웹에 올리는 경우에도 PiD 같은 제한 라이선스 모델은 서비스 서버에서 직접 실행하지 않고, 사용자가 본인 PC에 ComfyUI/모델을 설치한 뒤 클라이언트 또는 로컬 엔드포인트로 연결하는 방식을 우선 검토한다.
- 상용/공개 배포가 필요한 업스케일 기능은 라이선스가 명확한 별도 ComfyUI 업스케일러 또는 API 제공자를 기본값으로 둔다.
- 개인 로컬 사용에서는 AI_Generator 자체 FastAPI의 `/api/upscale`로 crop 결과를 `outputs/{project}/upscaled/`에 저장한다. PiD 런타임은 `LOCAL_UPSCALE_ENDPOINT=http://127.0.0.1:.../upscale` 또는 프로젝트 `upscale.endpoint`로 연결하는 로컬 HTTP 엔진(`pid-http`)을 우선 지원한다.
- PiD HTTP runner는 `POST` JSON 계약을 지원해야 한다. Health probe는 `{ "probe": true, "contract": "ai-generator-upscale-v1", "inputPath": "", "outputPath": "", "scale": 2 }`를 보내며, 실제 실행은 `{ "contract": "ai-generator-upscale-v1", "inputPath": "...", "outputPath": "...", "scale": 2, "engine": "pid-http" }`를 보낸다. runner는 이미지 응답, `imageBase64`, `outputPath`, 또는 지정된 `outputPath` 파일 생성을 반환할 수 있다.
- `pid`/`pid-http` 업스케일 결과는 R2 업로드를 기본 차단한다. 정말 업로드해야 할 때만 프로젝트 `upscale.allowRestrictedUpload=true` 또는 `ALLOW_RESTRICTED_UPSCALE_UPLOAD=1`로 명시 허용한다.
- 자체 웹서버는 기본적으로 `127.0.0.1:8000`에 바인딩한다. 외부 기기에서 접속해야 할 때만 `AI_GENERATOR_HOST=0.0.0.0`처럼 명시적으로 연다.

---

## 1. 아키텍처

```
[브라우저]              [AI_Generator]              [ComfyUI]              [GPU]
localhost:8000          포트 8000                   포트 8188              RTX 5080
                        Python FastAPI              Python + PyTorch
  웹 UI ──요청──→  배치 관리/리뷰 ──API 호출──→  이미지 생성 엔진 ──연산──→ VRAM 16GB
  결과 확인 ←──응답──  프롬프트 관리  ←──이미지──   z-image-turbo 모델
                       R2 업로드                    Qwen CLIP + VAE
```

### 왜 서버가 2개인가?

| | ComfyUI (포트 8188) | AI_Generator (포트 8000) |
|---|---|---|
| **역할** | GPU로 이미지를 생성하는 AI 엔진 | 웹 UI + 배치 관리 + ComfyUI에 작업 요청 |
| **비유** | 자동차 엔진 | 운전석 (핸들, 대시보드) |
| **누가 만들었나** | 오픈소스 (ComfyUI 커뮤니티) | 우리 프로젝트 |
| **위치** | `D:\Projects\ComfyUI\` | `D:\Projects\AI_Generator\` |
| **합칠 수 있나** | 불가 — 독립 프로젝트 | ComfyUI API를 호출하는 클라이언트 |

---

## 2. 터미널 구분법

### 터미널 1: ComfyUI (AI 엔진)

```
특징적인 메시지:
  "To see the GUI go to: http://0.0.0.0:8188"   ← 시작 완료
  "got prompt"                                    ← 작업 받음
  "100%|████████████| 20/20 [00:03]"             ← 이미지 생성 진행률
  "Prompt executed in 9.47 seconds"               ← 1장 완료
  "loaded completely; 13267 MB"                   ← 모델 VRAM에 로딩
```

### 터미널 2: AI_Generator (관리 도구)

```
특징적인 메시지:
  "Uvicorn running on http://0.0.0.0:8000"       ← 시작 완료
  "GET /api/health HTTP/1.1" 200 OK              ← 30초마다 ComfyUI 연결 체크
  "POST /api/batch/start HTTP/1.1" 200 OK        ← 배치 생성 시작됨
  "GET /api/batch/status HTTP/1.1" 200 OK        ← 브라우저가 진행 상태 확인
  "Shutting down"                                 ← 서버 종료됨
```

### 요약

- **`/api/` 로그** = AI_Generator
- **`got prompt` + 프로그레스 바** = ComfyUI

---

## 3. 실행 방법

### 방법 1: bat 파일로 한번에 실행

```
D:\Projects\AI_Generator\run_studio.bat
```

ComfyUI 자동 시작 → 15초 대기 → AI_Generator 시작 → 브라우저 자동 열림.

### 방법 2: 수동 실행 (에러 확인이 필요할 때)

**터미널 1 — ComfyUI 먼저**

```bash
cd D:\Projects\ComfyUI
python main.py --listen --disable-xformers
```

아래 메시지가 나오면 준비 완료:
```
To see the GUI go to: http://0.0.0.0:8188
```

**터미널 2 — AI_Generator (ComfyUI 준비된 후)**

```bash
cd D:\Projects\AI_Generator
.venv\Scripts\activate
python app.py
```

아래 메시지가 나오면 준비 완료:
```
Uvicorn running on http://0.0.0.0:8000
```

브라우저에서 http://localhost:8000 접속.

---

## 4. 종료 방법

| 상황 | 방법 |
|------|------|
| AI_Generator 종료 | 해당 터미널에서 `Ctrl+C` 2번 빠르게 |
| ComfyUI 종료 | 해당 터미널 창 X 버튼으로 닫기 |
| 프롬프트가 안 나타남 | 터미널 창 닫고 새 터미널 열기 |
| 둘 다 종료 | 두 터미널 창 모두 닫기 |

---

## 5. 재시작 방법

### AI_Generator만 재시작 (코드 수정 후)

ComfyUI는 그대로 두고, AI_Generator 터미널만:

1. `Ctrl+C` 2번 (또는 터미널 닫기)
2. 새 터미널:
```bash
cd D:\Projects\AI_Generator
.venv\Scripts\activate
python app.py
```
3. 브라우저 `Ctrl+Shift+R` (강제 새로고침)

### 둘 다 재시작

1. 두 터미널 모두 닫기
2. 위 "수동 실행" 순서대로 다시 실행

---

## 6. 에러 대응

### ComfyUI 에러

| 에러 | 원인 | 해결 |
|------|------|------|
| `CUDA error ... invalid argument` | xformers 호환 이슈 (RTX 5080) | `--disable-xformers` 플래그 추가 |
| `Missing required model components` | 모델 파일 없음 | `ComfyUI/models/` 폴더에 모델 확인 |
| `ModuleNotFoundError: triton` | Triton 미설치 (무시 가능) | 경고만, 동작에 문제 없음 |

### AI_Generator 에러

| 에러 | 원인 | 해결 |
|------|------|------|
| `ModuleNotFoundError: boto3` | 의존성 미설치 | `.venv\Scripts\activate` 후 `uv pip install -r requirements.txt` |
| `Cannot connect to 127.0.0.1:8188` | ComfyUI가 안 돌고 있음 | ComfyUI 먼저 실행 |
| `Batch already running` | 이전 배치가 아직 실행 중 | 완료 대기 또는 서버 재시작 |
| `Timeout (300s)` | 첫 이미지 모델 로딩 지연 | 정상 — 첫 1장만 느림, 이후 ~10초 |

### 브라우저 에러

| 에러 | 원인 | 해결 |
|------|------|------|
| `Unsafe attempt to load URL` | 서버 시작 전 페이지 로드 | 새 탭에서 `http://localhost:8000` 직접 입력 |
| 탭 클릭 안 됨 | JS 캐시 | `Ctrl+Shift+R` 강제 새로고침 |
| ComfyUI Offline (빨간 점) | ComfyUI 미실행 또는 종료됨 | ComfyUI 터미널 확인 후 재실행 |

---

## 7. 주요 설정

| 항목 | 값 | 비고 |
|------|------|------|
| ComfyUI 모델 | z_image_turbo_bf16 + Qwen 3 4B CLIP + ae VAE | `ComfyUI/models/` 하위 |
| 이미지 출력 | `AI_Generator/outputs/kemi/` | thumb/ + hero/ 하위 |
| 프롬프트 CSV | `AI_Generator/kemi/prompts/` | 웹 UI에서 편집 가능 |
| R2 업로드 설정 | `.env` 파일 | 플레이스홀더 → 실제 키로 교체 필요 |
| 워크플로우 | `workflow_api.json` | ComfyUI 노드 구성 |

다른 프로젝트 연결 기준:

- [Project Integration Contract](docs/project-integration-contract.md)
- [Project Setup Responsibilities](docs/project-setup-responsibilities.md)

---

## 8. 기술 스택

- **백엔드**: Python FastAPI + aiohttp + boto3
- **프론트엔드**: Vanilla JS + CSS (빌드 도구 없음)
- **AI 엔진**: ComfyUI 0.13.0 (z-image-turbo + Qwen 3 4B CLIP + VAE)
- **GPU**: NVIDIA RTX 5080 16GB VRAM
- **Python**: 3.13.7 + 가상환경 (.venv)
