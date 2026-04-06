# AI Generator - TODO 리스트
**목표:** 다중 프로젝트 이미지 생성/관리 Admin Studio (KEMI 일차, 확장 가능)

## 🔴 Phase 1: AI 생성 엔진 복구 및 검증 (우선 과제)

### 1.1 ComfyUI 워크플로우 수정
- [ ] **workflow_api.json 분해**: CheckpointLoaderSimple → UNETLoader + DualCLIPLoader + VAELoader
  - UNET: `z_image_turbo_bf16.safetensors` (Diffusion Only)
  - CLIP: `qwen_3_4b` (Text Encoder)
  - VAE: `ae.safetensors` (Encoder/Decoder)
- [ ] 필요 모델 다운로드 및 경로 검증 (`models/clip/`, `models/vae/`)
- [ ] 워크플로우 테스트 (ComfyUI 엔진 정상 로드 확인)

### 1.2 생성 파이프라인 안정화
- [ ] JSON 로더 및 Pillow 크롭 기능 검증 (최근 커밋: Phase 1-B)
- [ ] manifest 출력 검증
- [ ] 에러 핸들링 및 로깅 강화

---

## 🟡 Phase 2: 설정 기반 다중 프로젝트 라우팅 (Backend + Frontend)

### 2.1 프로젝트 설정 스키마 정의
- [ ] `projects/kemi.json` 스펙 정의 (프롬프트 경로, 규격, 스타일 등)
- [ ] `projects/mbti.json` 예시 작성
- [ ] 설정 검증 로직 구현

### 2.2 Backend (API 로직)
- [ ] 프로젝트 선택 기반 동적 경로 참조
- [ ] `outputs/{project_name}/` 구조 자동 생성
- [ ] 외부 절대경로(`promptsFile` 등) 직접 참조 로직

### 2.3 Frontend (UI)
- [ ] 프로젝트 선택기(Selector) 추가 (상단 콤보박스)
- [ ] 선택 시 갤러리/프롬프트 리스트 동적 리렌더링

---

## 🟢 Phase 3: 로컬 점검 및 메타데이터 관리

### 3.1 상태 메타 DB
- [ ] `outputs/{project_name}_state.json` 스키마 정의
  - 생성 기록, Approve/Reject 상태, 타임스탬프 등
- [ ] 상태 파일 읽기/쓰기 API 구현
- [ ] 메모리 ↔ 파일 동기화 로직

### 3.2 갤러리 점검 UX
- [ ] Approve/Reject 버튼 기능 연동
- [ ] 상태 파일에 자동 저장
- [ ] 삭제 시 로컬 물리 파일 제거

---

## 🔵 Phase 4: R2 에셋 통제 및 배포

### 4.1 R2 관리 탭
- [ ] R2 버킷 내 `{project_name}/*` 스캔 및 조회
- [ ] 덮어쓰기(Replace) 기능
- [ ] CDN Cache 회피 (`url?v=timestamp`)

### 4.2 배포 워크플로우
- [ ] 로컬 점검 완료 후 R2 일괄 업로드
- [ ] 배포 상태 추적 (시드/프롬프트 메타 포함)

---

## 📋 참고: 기존 완료 항목
- [x] 코드 구조화 (HTML/JS 분리, 이벤트 핸들러 정규화)
- [x] 중복 실행 방지 (포트 체크)
- [x] Phase 1-B: JSON 로더 + Pillow 크롭 + manifest

*최종 업데이트: 2026-04-06*
