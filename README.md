# Kemi AI Studio (Image Generator)

AI 이미지 배치 생성 + 리뷰 도구. ComfyUI 기반 로컬 생성 + 웹 UI 관리.

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

---

## 8. 기술 스택

- **백엔드**: Python FastAPI + aiohttp + boto3
- **프론트엔드**: Vanilla JS + CSS (빌드 도구 없음)
- **AI 엔진**: ComfyUI 0.13.0 (z-image-turbo + Qwen 3 4B CLIP + VAE)
- **GPU**: NVIDIA RTX 5080 16GB VRAM
- **Python**: 3.13.7 + 가상환경 (.venv)
