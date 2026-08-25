# UX/UI · React 프런트엔드 연동 Spec

> **문서 목적**: React/Vite 기반 K-Menu 프런트엔드가 메뉴 이미지 입력부터 음식 상세 안내까지 제공하는 사용자 경험과, 병합된 FastAPI API 계약을 정의한다. 이 문서는 `K_Menu_Talk.py`의 실제 HTTP 응답을 프런트엔드 표시 모델로 변환하는 기준이다.

## Why

- **페르소나**: 한국 음식과 한글 메뉴판에 익숙하지 않은 영어권 개별 관광객이다.
- **상황**: 사용자는 식당에서 메뉴판을 촬영하거나 업로드하고, 후보 음식 중 하나를 골라 재료·맵기·알레르기·먹는 법과 나레이션을 확인하려 한다.
- **문제**:
  1. 사용자는 한글 메뉴판에서 음식명을 바로 이해하기 어렵고, 단순 번역만으로는 재료·알레르기·먹는 법을 판단하기 어렵다.
  2. 카메라 권한 거부, OCR 실패, DB에 없는 음식, TTS 미준비처럼 현장에서 발생할 수 있는 상태를 이해하기 쉬운 화면으로 안내해야 한다.
  3. 백엔드의 실제 응답은 snake_case 필드와 중첩된 `details` 객체를 사용한다. 프런트엔드는 이 계약을 그대로 호출한 뒤 화면 친화적 모델로 변환해야 한다.
- **측정 지표**: 이미지 분석 성공률, 후보 선택 완료율, 상세 결과 화면 도달률, OCR·미지원 음식 오류에서의 재시도 비율을 측정한다.

## Goal

### 해결 목표

React/Vite 단일 페이지에서 카메라 촬영 또는 이미지 업로드를 받아 서버가 인식한 음식 후보를 보여 주고, 선택한 음식의 여섯 상세 카테고리와 나레이션 텍스트를 제공한다. TTS 생성이 준비되지 않았거나 브라우저용 오디오 URL이 없더라도 상세 텍스트는 표시돼야 한다.

### 성공 기준

| 구분 | 완료 기준 |
|---|---|
| 이미지 입력 | 카메라 촬영과 파일 업로드 중 하나로 메뉴 이미지를 `image` 필드에 담아 전송할 수 있다. |
| 분석 상태 | `ocr_empty`, `unsupported_food`, `candidates_found` 상태를 API 응답대로 분기한다. |
| 후보 선택 | 후보의 `name_kr`과 `score`를 표시하고 사용자가 하나를 선택할 수 있다. |
| 결과 정보 | `details`의 `DESCRIPTION`, `HOW_TO_EAT`, `INGREDIENT`, `ALLERGY`, `PRONUNCIATION`, `SPICY`를 표시한다. |
| 나레이션 | `narration_text`, `style`, `tts_status`를 결과 화면에서 의미 있게 안내한다. |
| 오류 처리 | OCR 실패, DB 미지원 음식, HTTP·네트워크 오류에서 재시도 또는 새 이미지 입력 행동을 제공한다. |

### Out of Scope

- Gradio UI
- 다국어 콘텐츠의 실제 번역·언어 전환 적용. 현재 언어 선택 UI는 화면 콘텐츠를 바꾸지 않는다.
- 사용자 계정, 결과 저장·공유, 주문·결제·예약
- 실제 OCR 좌표 기반 후보 박스. 현재 후보 박스는 데모용 위치 값이다.
- 지원 음식 목록을 프런트엔드에 복제하는 구현. 현재 API에는 전체 음식 목록 조회 엔드포인트가 없다.
- 브라우저에서 재생 가능한 TTS 오디오 엔드포인트. 현재 API의 `narration_audio_path`는 서버 임시 파일 경로다.

## What

### 구현된 사용자 흐름

1. 사용자는 개인정보 선택 배너에서 이미지 처리 동의를 확인한다.
2. 사용자는 카메라를 켜고 사진을 촬영하거나 이미지 파일을 업로드한다.
3. 프런트엔드는 `POST /api/analyze`에 multipart `image`를 전송하고 처리 상태를 보여 준다.
4. `candidates_found`이면 원본 이미지, 후보의 한글 음식명, 매칭 점수를 보여 준다.
5. 사용자가 후보 하나를 선택하면 `GET /api/foods/{food_id}`로 상세 정보를 조회한다.
6. 결과 화면은 여섯 상세 정보 영역, 나레이션 텍스트, TTS 상태를 표시한다.
7. OCR 실패·미지원 음식·서비스 오류에서는 오류 유형에 맞는 안내와 재시도 행동을 제공한다.

### 화면 상태

| 상태 | 진입 기준 | 화면 동작 | 사용자 행동 |
|---|---|---|---|
| `camera` | 최초 진입 또는 재시도 | 카메라·업로드 입력, 동의, 개인정보·약관 안내 | 카메라 촬영 또는 파일 선택 |
| `processing` | API 요청 중 | 메뉴 읽기 진행 문구와 취소 버튼 | 분석 취소 |
| `candidates` | `status = candidates_found` | 원본 이미지·후보 목록·데모 OCR 박스 | 후보 음식 선택 또는 새 메뉴 촬영 |
| `result` | 음식 상세 API 200 응답 | 상세 정보 카드·나레이션·TTS 상태 | 이전 후보로 이동 |
| `error` | OCR 실패·미지원 음식·HTTP 실패 | 오류 유형별 안내 | 재시도 또는 새 메뉴 촬영 |

## How

### 실제 HTTP API 계약

| 사용자 행동 | 요청 | 실제 성공 응답 | 프런트엔드 처리 |
|---|---|---|---|
| 이미지 분석 | `POST /api/analyze` | `{ status, ocr_text, candidates }` | 상태 분기 후 후보를 화면 모델로 변환 |
| 음식 상세 조회 | `GET /api/foods/{food_id}` | `{ details, narration_text, style, tts_status, narration_audio_path, tts_latency_ms }` | 선택한 후보의 한글명을 유지하고, 중첩 `details`를 카드로 표시 |

`POST /api/analyze`는 `multipart/form-data`의 `image` 필드를 받는다.

```json
{
  "status": "candidates_found",
  "ocr_text": "비빔밥",
  "candidates": [
    {
      "food_id": 1,
      "name_kr": "비빔밥",
      "score": 95,
      "modifiers": {"spice": [], "ingredient": []}
    }
  ]
}
```

분석 상태는 다음처럼 처리한다.

| `status` | 후보 배열 | 프런트엔드 화면 |
|---|---|---|
| `candidates_found` | 하나 이상 | 후보 선택 화면 |
| `ocr_empty` | 빈 배열 | OCR 실패 화면 |
| `unsupported_food` | 빈 배열 | 미지원 음식 화면 |

`GET /api/foods/{food_id}` 응답의 음식명은 프런트엔드가 새로 기대하지 않는다. 결과 제목에는 후보 선택 단계에서 이미 받은 `name_kr`을 유지한다.

```json
{
  "details": {
    "DESCRIPTION": "...",
    "PRONUNCIATION": "...",
    "SPICY": "...",
    "INGREDIENT": "...",
    "HOW_TO_EAT": "...",
    "ALLERGY": "..."
  },
  "narration_text": "...",
  "style": "GUIDE",
  "tts_status": "not_ready",
  "narration_audio_path": null,
  "tts_latency_ms": 0.0
}
```

### 프런트엔드 변환 기준

| API 필드 | 화면 모델 또는 표시 |
|---|---|
| `candidates[].food_id` | `FoodCandidate.foodId` 및 상세 조회 경로 |
| `candidates[].name_kr` | 후보·결과 제목의 한글 음식명 |
| `candidates[].score` | 후보 목록의 매칭 점수 |
| `details.DESCRIPTION` | Description 카드 |
| `details.HOW_TO_EAT` | How to eat 카드 |
| `details.INGREDIENT` | Ingredients 카드 |
| `details.ALLERGY` | 강조된 Allergy notice 카드 |
| `details.PRONUNCIATION` | 결과 제목 아래 발음 안내 |
| `details.SPICY` | Spice level 배지 |
| `narration_text` | 음성 재생 불가 시에도 표시하는 텍스트 안내 |
| `tts_status` | `ok` 또는 `not_ready` 상태 안내 |
| `narration_audio_path` | 현재 서버 내부 임시 경로이므로 `<audio>`의 URL로 사용하지 않음 |

### 지원 음식 목록 처리

지원 음식의 단일 출처는 Supabase `foods` 테이블이다. 현재 FastAPI API는 OCR로 발견한 후보만 반환하고 전체 50개 음식 목록을 노출하지 않는다. 따라서 프런트엔드는 DB와 다른 `SUPPORTED_DISHES` 상수를 유지하지 않는다.

미지원 음식 화면은 “현재 서버의 지원 음식 DB에서 이 메뉴를 매칭하지 못했다”는 사실과 새 메뉴 촬영 행동만 안내한다. 전체 목록을 표시하려면 후속 백엔드 작업으로 `GET /api/foods` 같은 읽기 전용 목록 엔드포인트를 추가하고, 프런트엔드는 그 응답을 사용해야 한다.

### TTS 재생 제한

FastAPI는 현재 `narration_audio_path`에 서버의 임시 WAV 파일 경로를 반환하지만 정적 파일 또는 다운로드 URL을 노출하지 않는다. 브라우저는 이 서버 파일 경로를 직접 재생할 수 없으므로, 프런트엔드는 텍스트 나레이션과 TTS 상태만 표시한다.

브라우저 재생을 지원하려면 후속 API에서 인증·만료 정책을 고려한 공개 오디오 URL 또는 스트리밍 엔드포인트를 제공해야 한다. 그때 `narration_audio_path` 대신 해당 URL을 `<audio>`에 연결한다.

### 환경·배포 제약

- `frontend/.env.example`에는 공개 가능한 `VITE_API_BASE_URL`만 기록한다.
- 실제 `frontend/.env`는 개발자 PC 또는 배포 환경에서만 생성하고 커밋하지 않는다.
- `VITE_*` 값은 브라우저 번들에 노출될 수 있으므로 API 키, Supabase 키, TTS 키, 비밀번호를 넣지 않는다.
- `node_modules/`, `dist/`, 로그, TypeScript 캐시는 `frontend/.gitignore`으로 제외한다.
- React 개발 서버와 FastAPI가 다른 origin에서 동작하면 백엔드는 CORS를 허용하거나, 개발 서버는 동등한 프록시 설정을 가져야 한다.

## AC (Given-When-Then)

**AC-01 · 후보 목록 반환**

- GIVEN: `POST /api/analyze`가 `candidates_found`와 후보 배열을 반환한다.
- WHEN: 프런트엔드가 응답을 수신한다.
- THEN: 각 후보의 `name_kr`과 `score`를 표시하고 사용자는 하나를 선택할 수 있다.

**AC-02 · OCR 실패 상태 전달**

- GIVEN: `POST /api/analyze`가 `status = ocr_empty`와 빈 후보 배열을 반환한다.
- WHEN: 프런트엔드가 응답을 수신한다.
- THEN: 서비스 오류가 아니라 OCR 실패 안내와 새 이미지 입력 행동을 표시한다.

**AC-03 · 미지원 음식 상태 전달**

- GIVEN: `POST /api/analyze`가 `status = unsupported_food`와 빈 후보 배열을 반환한다.
- WHEN: 프런트엔드가 응답을 수신한다.
- THEN: 하드코딩 목록 없이 DB 미지원 음식 안내와 새 이미지 입력 행동을 표시한다.

**AC-04 · 상세 정보 변환**

- GIVEN: 사용자가 후보를 선택하고 `GET /api/foods/{food_id}`가 200 응답을 반환한다.
- WHEN: 프런트엔드가 중첩 `details` 객체를 수신한다.
- THEN: 선택한 후보의 `name_kr`을 제목으로 유지하고 여섯 상세 카테고리와 `narration_text`를 표시한다.

**AC-05 · TTS 미준비 또는 웹 재생 불가**

- GIVEN: `tts_status = not_ready`이거나 `narration_audio_path`가 브라우저 URL이 아니다.
- WHEN: 결과 화면을 표시한다.
- THEN: 오디오 플레이어 오류를 만들지 않고 텍스트 나레이션과 상태 안내를 표시한다.

**AC-06 · 존재하지 않는 음식**

- GIVEN: `GET /api/foods/{food_id}`가 404를 반환한다.
- WHEN: 프런트엔드가 상세 조회 오류를 처리한다.
- THEN: 서비스 오류 안내와 재시도 행동을 표시한다.

## References

[1]: ../../K_Menu_Talk.py "FastAPI /api/analyze 및 /api/foods/{food_id} 구현"
[2]: ../../docs/specs/api-layer.md "백엔드 API 레이어 Spec"
[3]: ../../frontend/src/App.tsx "React 화면 상태, API 호출, 응답 변환"
[4]: ../../src/db/cache.py "foods 테이블을 지원 음식의 단일 출처로 사용하는 캐시 계층"
