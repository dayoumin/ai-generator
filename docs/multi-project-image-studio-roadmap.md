# Multi-Project Image Studio Roadmap

## Goal

`AI_Generator`를 `Kemi` 전용 도구가 아니라 여러 프로젝트에서 공통으로 쓰는 이미지 스튜디오로 확장한다.

1. 프로젝트별 프롬프트 소스와 출력 경로를 분리한다.
2. 캐릭터/레퍼런스 자산을 기반으로 일관된 이미지를 생성한다.
3. 생성 엔진은 교체 가능하게 유지하고, 검수와 업로드 흐름은 공통으로 쓴다.

## Current Structure

현재 코드 기준 핵심 파일은 아래다.

- `app.py`
  - FastAPI 백엔드
  - 프롬프트 로드, 배치 생성, 크롭, manifest, R2 업로드 담당
- `index.html`
  - 스튜디오 UI
- `static/js/app.js`
  - 프로젝트 전환, 프롬프트 로드, 배치 제어, 갤러리 상태 관리
- `projects/*.json`
  - 프로젝트 설정 파일

이미 1차 기반은 추가됐다.

- `/api/projects`로 프로젝트 목록 조회 가능
- `project` 파라미터로 프롬프트 파일 조회 가능
- 결과물은 `outputs/{project}/...`로 분리 저장
- MBTI는 `projects/mbti.json`으로 연결됨

## Phase 1: Project Selector

목표는 "하나의 스튜디오에서 프로젝트를 바꿔도 흐름이 유지되는 상태"다.

완료 범위:

- 상단 프로젝트 셀렉터 추가
- `projects/*.json` 기반 프로젝트 목록 로드
- 프로젝트별 기본 프롬프트 파일 선택
- 프로젝트별 기본 스타일/비율 반영
- 프로젝트 전환 시 갤러리/로그/UI 상태 초기화
- 현재 프로젝트와 다른 배치 상태는 자동 복구하지 않음

남은 보완:

- 프로젝트별 로컬 설정 저장 키 분리
- 프로젝트별 최근 사용 프롬프트 파일 기억
- 프로젝트별 배치 이력 보존

## Phase 2: Reference Asset System

상황반응 같은 콘텐츠는 프롬프트만으로는 얼굴과 톤이 흔들린다. 따라서 기준 자산 세트를 먼저 둔다.

권장 자산 구조:

```text
assets/
  mbti/
    characters/
      haru/
        base/
          front.png
          closeup.png
        emotions/
          neutral.png
          joy.png
          awkward.png
          angry.png
        roles/
          friend.png
          parent.png
          coworker.png
          mentor.png
        props/
          phone.png
          laptop.png
          coffee.png
```

필요한 기능:

- 레퍼런스 자산 목록 조회 API
- 자산 업로드 API
- 생성 요청에 `referenceAssets` 전달
- 갤러리에서 어떤 레퍼런스를 썼는지 표시

## Phase 3: Character Builder

MBTI 상황반응은 CSV 하나로 끝내기보다 조합형 UI가 더 효율적이다.

필요한 입력:

- 캐릭터
- 감정 12종
- 역할 키트
- 상황 템플릿
- 출력 타입

생성 로직:

1. 캐릭터 기준본 선택
2. 감정/역할/상황 템플릿 조합
3. 공통 스타일 프롬프트 결합
4. 배치 생성
5. 크롭/검수/업로드

## Phase 4: Provider Abstraction

이미지 렌더링 엔진은 고정하지 않는다.

권장 역할 분리:

- `comfyui`
  - 로컬 기본 생성 엔진
- `api`
  - 일부 고품질 컷에 사용하는 외부 엔진
- `ollama`
  - 이미지 생성 본체가 아니라 프롬프트 보정, QC 보조용

추가 운용 모드:

- `codex-assisted`
  - 픽셀 렌더링은 외부 엔진이 담당
  - Codex는 프로젝트 설정, 프롬프트 구성, reference asset 구조화, 배치 실행 판단, 결과 검수와 수정 루프를 담당

권장 인터페이스:

```json
{
  "provider": "comfyui",
  "project": "mbti",
  "prompts": [],
  "referenceAssets": [],
  "generation": {
    "aspectRatio": "1:1",
    "steps": 20
  }
}
```

## Recommended MBTI Rollout

대량 자동화보다 소량 파일럿부터 시작한다.

1. `하루` 기준 캐릭터 확정
2. 감정 6종 생성
3. 역할 4종 생성
4. 상황반응 4개 생성
5. 앱 화면에 넣어서 레이아웃 검증
6. 괜찮으면 12감정과 20상황으로 확장

## Immediate Next Steps

다음 구현 단위는 아래 순서가 안전하다.

1. `Phase 1` 마감
   - 프로젝트별 설정 저장 분리
   - 최근 사용 파일 기억
2. `Phase 2` 착수
   - reference asset 폴더 규칙 추가
   - 업로드/목록 API 추가
   - UI에 reference 선택 섹션 추가
3. `MBTI` 파일럿
   - `하루` 기준 자산 세트 생성
   - 상황반응 프롬프트 4개 연결
