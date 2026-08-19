# Spec — 백엔드 API 레이어 (FastAPI)

## Why

- **페르소나**: 백엔드(`src/pipeline.py`)와 별도로 만들어진 웹 프론트엔드(React 기반 시뮬레이션, "K-Menu Web Playground")를 붙이는 재훈·백호님, 그리고 향후 Flutter 앱.
- **상황**: 백엔드 로직(`analyze_image`, `create_tts_response`, `get_details`)은 이미 있지만, 파이썬 함수 호출로만 접근 가능하다. 프론트엔드는 별도 프로세스(브라우저/앱)에서 돌아가므로 HTTP로 호출해야 한다.
- **문제**: Gradio를 전제로 배포전략을 짰었는데(README 8절), 실제 프론트엔드는 Gradio 화면이 아니라 독립된 웹앱이라 Gradio의 기본 UI로는 계약이 맞지 않는다. HTTP API가 없어 프론트가 백엔드를 호출할 방법이 없다.
- **측정 지표**: 프론트가 이미지 하나로 후보 목록을 받고, 후보 하나로 상세정보+나레이션을 받는 왕복을 각각 성공적으로 마치는지 테스트로 검증한다.

## Goal

- **해결 목표**: 기존 `src/pipeline.py`의 `analyze_image()`, `create_tts_response()`, `src/text_gen/detail.py`의 `get_details()`를 HTTP로 노출한다.
- **성공 기준**:
  1. 이미지를 업로드하면 OCR 상태(`ocr_empty`/`unsupported_food`/`candidates_found`)와 후보 목록을 JSON으로 받는다.
  2. `food_id`로 상세정보(6개 카테고리)와 나레이션 결과(텍스트·스타일·오디오 상태)를 JSON으로 받는다.
  3. 등록되지 않은 `food_id`는 404를 반환한다.
- **Out of Scope**: 프론트엔드 코드 자체, 인증/로그인, 장바구니·주문 기능, Flutter 클라이언트 코드, 대표이미지(`thumbnail_url`)·출처표시 필드(별도 Spec — `foods` 테이블 컬럼 추가가 선행돼야 함), 배포(HF Spaces/Tailscale) 설정.

## What

**Happy Path**

1. 프론트가 `POST /api/analyze`에 이미지 파일을 업로드한다.
2. 서버가 `analyze_image()`를 호출해 `status`, `ocr_text`, `candidates`를 반환한다.
3. 프론트가 후보 카드 중 하나를 사용자에게 선택받아 `food_id`를 얻는다.
4. 프론트가 `GET /api/foods/{food_id}`를 호출한다.
5. 서버가 `get_details()` + `create_tts_response()`를 호출해 상세 텍스트·나레이션 텍스트·스타일·TTS 상태를 반환한다.

**Edge Cases**

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | 존재하지 않는 `food_id` 조회 | `get_details()`의 `ValueError`를 잡아 404 반환 |
| EC-02 | 업로드된 파일이 이미지가 아니거나 손상됨 | `analyze_image()` 내부 `recognize()`가 던지는 예외를 그대로 전달(500) — 기존 파이프라인 동작과 동일, 여기서 새로 방어하지 않음 |
| EC-03 | TTS 모델이 아직 준비 안 됨 (GPU 없음 등) | 기존 `tts_status: "not_ready"`를 그대로 응답에 담아 전달 — 이 레이어에서 예외로 바꾸지 않음 |
| EC-04 | OCR 결과 없음/미지원 음식 | `analyze_image()`가 이미 반환하는 `ocr_empty`/`unsupported_food` 상태를 그대로 전달 |

## How

```
POST /api/analyze
요청: multipart/form-data, 필드 "image" (파일)

응답 200:
{
  "status": "ocr_empty" | "unsupported_food" | "candidates_found",
  "ocr_text": string,
  "candidates": [
    {"food_id": int, "name_kr": string, "score": int, "modifiers": {...}}
  ]
}
```

```
GET /api/foods/{food_id}

응답 200:
{
  "details": {"DESCRIPTION": string, "PRONUNCIATION": string, ...},
  "narration_text": string,
  "style": "GUIDE" | "CAUTION",
  "tts_status": "ok" | "not_ready",
  "narration_audio_path": string | null,
  "tts_latency_ms": number
}

응답 404: food_id가 존재하지 않음
```

- 대상 파일: `K_Menu_Talk.py` (README에 이미 "배포 진입점"으로 문서화된 파일 — Gradio 대신 FastAPI 앱을 둠)
- 업로드된 이미지는 임시 파일로 저장 후 기존 `analyze_image(image_path)`에 그대로 전달한다 (OCR 쪽 함수 시그니처를 바꾸지 않음).
- 응답 스키마는 Pydantic 모델로 고정한다 — FastAPI가 `/docs`에 자동으로 계약을 문서화하므로, 프론트엔드가 이 페이지를 보고 연동할 수 있다.

## AC

**AC-01 · 후보 목록 반환**
- GIVEN: `analyze_image()`가 `candidates_found` 상태와 후보 2개를 반환한다.
- WHEN: `POST /api/analyze`에 이미지를 업로드한다.
- THEN: 응답 200과 함께 동일한 `status`, `ocr_text`, `candidates`를 받는다.

**AC-02 · OCR 실패 상태 그대로 전달**
- GIVEN: `analyze_image()`가 `ocr_empty` 상태를 반환한다.
- WHEN: `POST /api/analyze`를 호출한다.
- THEN: 응답 200, `status`가 `ocr_empty`, `candidates`는 빈 배열이다.

**AC-03 · 상세정보 조회 성공**
- GIVEN: `food_id=1`에 대한 `get_details()`와 `create_tts_response()`가 정상 값을 반환한다.
- WHEN: `GET /api/foods/1`을 호출한다.
- THEN: 응답 200과 함께 6개 카테고리 상세정보와 나레이션 결과를 받는다.

**AC-04 · 존재하지 않는 음식**
- GIVEN: `get_details()`가 존재하지 않는 `food_id`에 대해 `ValueError`를 던진다.
- WHEN: `GET /api/foods/{food_id}`를 호출한다.
- THEN: 응답 404를 받는다.
