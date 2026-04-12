# Kemi AI Studio: 다중 프로젝트 통합 관리 및 에셋 파이프라인 기획서 V2

## 1. 개요 및 아키텍처 원칙

### 💡 아키텍처 원칙: Admin Studio & 설정 주도 방식 (Config-driven)
* **어플리케이션 분리:** 본 도구(AI_Generator)는 오직 개발자/관리자를 위한 **이미지 공장(Admin Studio)**입니다. Kemi, MBTI 등 타 서비스 앱들은 이 UI를 사용하지 않으며 산출물(R2 URL)만 읽어 갑니다.
* **외부 종속성 투명화:** AI_Generator 안에 타 프로젝트의 프롬프트 등을 통째로 복사해 쌓아두지 않습니다. 대신 `projects/mbti.json`과 같은 설정 파일 내 `promptsFile: "D:/Projects/MBTI/..."` 절대 경로 등 **외부 프로젝트 원본 데이터를 직접 참조**하여 단일 진실 공급원(SSOT)을 유지합니다.

---

## 2. 전체 시스템 흐름 (목표 아키텍처)

```text
[ 외부 프로젝트 워크스페이스 ]
  ├── MBTI 앱 (D:/Projects/MBTI/...) ← 생성 요청 프롬프트 JSON 물리적 소유 (SSOT)
  └── Kemi 앱 (D:/Projects/Kemi/...) 
        │
        ▼ (설정 파일을 통한 간접/실시간 참조)
[ 관리자 전용 UI (AI_Generator) ]
  ├── [선택: MBTI 프로젝트]
  │    ├── 프롬프트 로드 (D:/Projects/MBTI/... 실시간 매핑)
  │    ├── 생성 및 크롭 (mbti.json 규칙 적용)
  │    └── 상태 파일 (outputs/mbti_state.json) 관리 구축 (영구 저장)
  └── [선택: Kemi 프로젝트] 
        │
        ▼ API 호출
[ ComfyUI 엔진 (로컬 분리 시스템) ] ← AI_Generator의 스케줄링을 받아 GPU 렌더링
        │
        ▼ 업로드 및 매핑
[ Cloudflare R2 스토리지 ] ← [ 타 서비스 앱이 URL 직접 소비 (CDN Cache 갱신 기법 적용) ]
```

---

## 3. 단계별 개발 로드맵 (마일스톤)

### 🔴 Phase 1: AI 생성 엔진 복구 및 검증 (우선 과제)
UI보다 이미지 생성 엔진의 정상화가 최우선입니다. `AI_CONTEXT.md`에 기술된 ComfyUI 워크플로우 오류를 신속히 조치합니다.
* **이슈:** `z_image_turbo_bf16.safetensors` 컴피유아이(UI) 로드 실패 현상 (Diffusion Only 모델의 단독 연결 문제).
* **작업 1:** `workflow_api.json` 분해. 단일 로더(`CheckpointLoaderSimple`) 대신 `UNETLoader`, Text Encoder(`qwen_3_4b`), `VAELoader`로 역할을 철저히 분산 및 재배치 설정.
* **작업 2:** 필요 노드 및 모델 파일 점검 로직 연동 (`download_model.py` 활용 방안 검토).

### 🟡 Phase 2: 설정 기반 다중 프로젝트 동적 라우팅 (Backend / UI)
하드코딩 된 경로(`kemi/...`)를 제거하고, 외부 경로 설정 파일을 읽어오는 유연한 골격을 생성합니다.
* **프론트엔드 (UI):** 화면 상단부에 콤보박스 형태의 **프로젝트 선택기(Project Selector)**를 추가. 프로젝트 변경 시 관련 데이터(Prompts List, Gallery)가 리렌더링됨.
* **백엔드 (API 로직):** 선택한 프로젝트의 `.json` 속 외부 절대경로(`promptsFile`)를 직접 참조하여 렌더링. 출력 결과물 폴더 체계도 `outputs/{project_name}/` 구조로 동적 매핑화.

### 🟢 Phase 3: 로컬 리뷰 갤러리 및 영구 메타 DB 설계
웹브라우저나 서버를 껐다 켜も 리뷰(Approve/Reject) 결과가 남도록 개선.
* **상태 메타 데이터 도입:** 메모리 관리를 벗어나, 파일 형태의 가벼운 DB (예: `outputs/{project_name}_state.json`)를 갖추어 생성 기록, 승인/거절 내역을 영구 저장/불러오기.
* **로컬 파일 파괴 API:** UI상에서 더 이상 쓸모없는 이미지 거부/삭제 시 실제 물리적 파일 삭제 연동으로 SSD 스토리지 낭비 억제.

### 🔵 Phase 4: 클라우드 (R2) 에셋 통제 매니저 신규 탭 부착
단순 업로더가 아닌 R2를 조율하는 자격을 획득함.
* **R2 동기화 관리 화면:** 버킷 내 `{project_name}/*` 리스트를 스캔해 조회할 수 있는 전용 탭 확장.
* **덮어쓰기(Replace) 기능 및 Cache 대응:** Kemi/MBTI 앱 코드 수정 없이 이미지 부분 변경(교체)을 위해, 동일 Key에 파일을 덮어쓰고 CDN Cache 회피 코드(ex: `url?v=timestamp`)가 즉시 툴링되도록 구조화.
