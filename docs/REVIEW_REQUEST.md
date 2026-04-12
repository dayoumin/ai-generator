# Kemi AI Studio — 코드 리뷰 요청 (Phase 1 파이프라인 포함)

## 프로젝트 개요

AI 이미지 배치 생성 + 리뷰 도구. 2개 프로젝트에 걸쳐 있음:

- **AI_Generator** (Python FastAPI): ComfyUI 기반 이미지 생성, 크롭, R2 업로드, 웹 UI
- **MBTI** (Next.js): 이미지가 표시될 앱. 추출/주입 스크립트 보유

## 전체 아키텍처

```
┌─ MBTI 프로젝트 ──────────────────────────────┐
│ pnpm image:extract                            │
│   dogBreed.ts → prompts.json (12개 견종)      │
│                                                │
│ pnpm image:inject                              │
│   manifest.json → breed-images.ts (lookup map) │
│                                                │
│ TournamentPlay.tsx                              │
│   breed-images.ts에서 이미지 URL 조회 → 표시   │
└────────────────────────────────────────────────┘
         ↕ JSON 파일 교환
┌─ AI_Generator (Python) ───────────────────────┐
│ 1. prompts.json 로드 (웹 UI에서 선택)          │
│ 2. ComfyUI로 1024×1024 이미지 생성             │
│ 3. Pillow 자동 크롭 (4:5 토너먼트, 1:1 썸네일)  │
│ 4. R2 업로드 (R2 키 기반)                      │
│ 5. manifest.json 출력                          │
│ 6. 웹 UI: 갤러리 + 승인/거부 리뷰              │
└────────────────────────────────────────────────┘
         ↕ ComfyUI HTTP API
┌─ ComfyUI (포트 8188) ─────────────────────────┐
│ z-image-turbo + Qwen 3 4B CLIP + VAE          │
│ GPU: RTX 5080 16GB VRAM                       │
└────────────────────────────────────────────────┘
```

## 커밋 이력 (AI_Generator)

| 커밋 | 내용 |
|------|------|
| `a79c840` | 전면 개선 — 버그 10개 + 리뷰 UI + 코드 품질 + RTX 5080 호환 |
| `100b23b` | UX 정비 — 한국어화, 토스트, CSS 누락, 안전성, 성능 |
| `8c78d8a` | 탭별 버튼 표시 |
| `92f14bd` | CSV 프롬프트 50개 + 탭 버튼 제어 |
| `81cba31` | Phase 1-B — JSON 로더 + Pillow 크롭 + manifest 출력 |
| `d19d4b1` | R2 키/URL 수정 — 영어 프롬프트 기반 + 프록시 호환 |

## 커밋 이력 (MBTI)

| 커밋 | 내용 |
|------|------|
| `ec6fb0c4` | ContentImage src 변경 시 상태 초기화 + 이미지 필드명 확정 |
| `f14419e2` | ContentImage errored 상태 초기화 (main 브랜치) |
| `ad6ee3db` | Phase 1-A — extract-prompts.ts + export-prompts-csv.ts |
| `d7a72226` | Phase 1-C/D — inject-urls.ts + R2_ALLOWED_FOLDERS 확장 |

## 주요 파일

### AI_Generator

| 파일 | 줄 수 | 역할 |
|------|-------|------|
| `app.py` | ~600 | FastAPI 백엔드 — 생성, 크롭, manifest, 업로드 |
| `index.html` | ~630 | 웹 UI (대시보드, 프롬프트, 갤러리, 설정, 가이드) |
| `static/js/app.js` | ~720 | 프론트엔드 로직 |
| `static/js/constants.js` | ~91 | DOM ID, API 경로 상수 |
| `static/style.css` | ~730 | 스타일 |
| `projects/mbti.json` | ~15 | 크롭 설정 (비율, 크기) |

### MBTI

| 파일 | 역할 |
|------|------|
| `scripts/image-gen/extract-prompts.ts` | dogBreed 데이터 → prompts.json |
| `scripts/image-gen/inject-urls.ts` | manifest.json → breed-images.ts (lookup map) |
| `src/utils/r2-upload.ts` | R2_ALLOWED_FOLDERS 수정 (breeds, tournaments, content 추가) |
| `src/components/common/ContentImage.tsx` | src 변경 시 errored 초기화 수정 |

## 리뷰 포인트

### 1. 파이프라인 데이터 흐름

전체 흐름을 추적하면서 검증 필요:

```
extract-prompts.ts
  → prompts.json (id, prompt, style, targetCrops, category)
  → AI_Generator _load_json_prompts (JSON → CSV 호환 dict 변환)
  → make_result_entry (row의 _source_id, _target_crops 등 메타 전달)
  → generate_single_image → ComfyUI 1024×1024 PNG
  → POST /api/crop → Pillow 중앙 크롭 → WebP
    → R2 키: {category}/{영어prompt첫부분}_{genType}_{cropName}.webp
  → GET /api/manifest → JSON (contentId, assets[{cropType, r2Key, url}])
  → inject-urls.ts → breed-images.ts (lookup map)
```

**검증 질문**:
- `_target_crops` 메타데이터가 generate → crop까지 전달되는지
- R2 키가 MBTI 프록시의 ASCII-only 정규식을 통과하는지
- manifest의 URL(`/api/images/{r2Key}`)이 inject에서 올바르게 사용되는지
- 부분 실패 시 (12개 중 9개만 성공) inject가 안전하게 동작하는지

### 2. R2 키 생성 로직 (app.py crop endpoint)

```python
prompt_first = result.get("prompt", "unknown").split(",")[0].strip()
safe_result_name = re.sub(r'[^a-zA-Z0-9]', '-', prompt_first).lower().strip('-')
gen_type = result.get("type", "img")
r2_key = f"{category}/{safe_result_name}_{gen_type}_{crop_name}.webp"
```

예시: `breeds/dogs/golden-retriever_hero_tournament.webp`

- 프롬프트 첫 부분이 항상 영어 breed 이름인지 보장 가능한가?
- 같은 breed를 다른 배치에서 재생성하면 키가 동일 → R2에서 덮어쓰기. 의도적인가?

### 3. 인메모리 상태의 한계

`batch_status`는 전역 dict. 서버 재시작 시 모든 결과 손실. 생성 → 크롭 → manifest가 한 세션에서 이루어져야 함.

- 이 제약이 12장 규모에서 허용 가능한가?
- Phase 2에서 SQLite로 전환 예정이지만, 현재 사용에 문제가 될 수 있는 시나리오는?

### 4. TournamentPlay.tsx 미수정

현재 `TournamentPlay.tsx`는 이모지만 렌더링. `imageUrl` 또는 `breed-images.ts` lookup을 사용하는 코드가 없음. Phase 1 완료 기준("앱에서 이미지 표시")을 충족하려면 이 컴포넌트 수정이 필요.

### 5. 백엔드 (app.py)

- `generate_single_image`의 ComfyUI 폴링 루프 (while + sleep 1초). WebSocket이 더 나은지.
- `POST /api/crop`이 `from PIL import Image`를 함수 내부에서 import. 이상적인 패턴인지.
- R2 업로드가 크롭 결과 기반으로 변경됨 (이전: 전체 outputs/ 워크). 기존 원본 이미지(PNG)는 업로드 안 됨. 의도적인지.

### 6. 프론트엔드 (app.js)

- Vanilla JS 720줄+ 유지보수 한계
- 일부 DOM ID가 CONFIG.DOM에 미등록
- Settings/Guide/Help 모달 영어 미번역

## 알려진 미해결 사항

| 항목 | 우선도 | 비고 |
|------|--------|------|
| TournamentPlay.tsx imageUrl 렌더링 | 높음 | 이미지 생성 후 수정 예정 |
| Settings/Guide/Help 영어 → 한국어 | 낮음 | 기능에 영향 없음 |
| CONFIG.DOM 미등록 ID | 낮음 | 동작 문제 없음 |
| 배치 재실행 시 이전 결과 덮어쓰기 | 중간 | Phase 2 SQLite로 해결 예정 |
| 계획서의 pipeline 상태 필드 미구현 | 낮음 | manifest에 아직 포함 안 됨 |
