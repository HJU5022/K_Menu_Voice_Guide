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

React/Vite 단일 페이지에서 카메라 촬영 또는 이미지 업로드를 받아 서버가 인식한 음식 후보를 보여 주고, 선택한 음식의 여섯 상세 카테고리와 나레이션 텍스트·음성을 제공한다. TTS가 준비되지 않아 오디오 경로가 `null`로 와도(`tts_status: "not_ready"`) 상세 텍스트는 그대로 표시돼야 한다.

### 성공 기준

| 구분 | 완료 기준 |
|---|---|
| 이미지 입력 | 카메라 촬영과 파일 업로드 중 하나로 메뉴 이미지를 `image` 필드에 담아 전송할 수 있다. |
| 분석 상태 | `ocr_empty`, `not_a_menu`, `unsupported_food`, `candidates_found` 네 상태를 API 응답대로 분기한다. |
| 후보 선택 | 후보의 `name_kr`과 `score`를 표시하고 사용자가 하나를 선택할 수 있다. |
| 결과 정보 | `details`의 `DESCRIPTION`, `HOW_TO_EAT`, `INGREDIENT`, `ALLERGY`, `PRONUNCIATION`, `SPICY`를 표시한다. |
| 나레이션 | `narration_text`·`style`·`tts_status`를 안내하고, **오디오 두 갈래**(이름 `name_audio_path` / 설명 `narration_audio_path`)를 각각 재생한다. |
| 오류 처리 | OCR 실패, DB 미지원 음식, HTTP·네트워크 오류에서 재시도 또는 새 이미지 입력 행동을 제공한다. |

### Out of Scope

- Gradio UI
- 다국어 콘텐츠의 실제 번역·언어 전환 적용. 현재 언어 선택 UI는 화면 콘텐츠를 바꾸지 않는다.
- 사용자 계정, 결과 저장·공유, 결제·예약
- 지원 음식 목록을 프런트엔드에 **복제**하는 구현 — 목록은 `GET /api/foods`로 받아 쓴다(아래 "지원 음식 목록 처리")

> **2026-08-27 정정.** 이 절에 있던 세 항목이 그 뒤 전부 구현돼 범위 밖이 아니게 됐다 —
> ① "후보 박스는 데모용 위치 값" → 서버가 주는 `candidate.source`(원본 사진 기준 0~1 비율)로
> 그린다, ② "전체 음식 목록 엔드포인트가 없다" → `GET /api/foods`가 생겼다
> (`docs/specs/supported-foods.md`), ③ "브라우저에서 재생 가능한 오디오 URL이 없다" →
> `K_Menu_Talk.py`가 `/audio/{파일명}`으로 정적 서빙한다. 본문의 해당 절도 함께 고쳤다.

## What

### 구현된 사용자 흐름

1. 사용자는 랜딩에서 서비스 설명·이용 단계와 사진 사용 안내(`privacyNote`)를 보고 `Get started`를 누른다. **켜고 끄는 동의 토글은 없다** — 사진이 어떻게 다뤄지는지를 사실대로 알리고, 자세한 내용은 바닥글의 Privacy·Terms 창에 둔다.
2. 사용자는 카메라를 켜고 사진을 촬영하거나 이미지 파일을 업로드한다.
3. 프런트엔드는 `POST /api/analyze`에 multipart `image`를 전송하고 처리 상태를 보여 준다.
4. `candidates_found`이면 원본 이미지 위에 `source` 좌표로 번호 박스를 얹고, 후보를 `line_no` 순으로 늘어놓는다.
5. 사용자가 후보 하나를 선택하면 `GET /api/foods/{food_id}`로 상세 정보를 조회한다.
6. 결과 화면은 여섯 상세 정보 영역, 나레이션 텍스트, 두 가지 오디오(이름·설명) 재생을 표시한다.
7. OCR 실패·메뉴 아님·미지원 음식·서비스 오류에서는 오류 유형에 맞는 안내와 재시도 행동을 제공한다.

### 화면 상태

화면 상태는 일곱 개다(`frontend/client/src/pages/Home.tsx`의 `Screen`).

| 상태 | 진입 기준 | 화면 동작 | 사용자 행동 |
|---|---|---|---|
| `landing` | 최초 진입 | 서비스 소개·이용 단계·사진 사용 안내 | `Get started` |
| `camera` | `Get started` 또는 재시도 | 카메라·업로드 입력, 바닥글의 개인정보·약관 창 | 카메라 촬영 또는 파일 선택 |
| `processing` | API 요청 중 | 메뉴 읽기 진행 문구와 취소 버튼 | 분석 취소 |
| `candidates` | `status = candidates_found` | 원본 이미지 위 `source` 박스 · 후보 목록 · 장바구니 | 후보 선택, 담기, `Back`/`Start over` |
| `order` | 카트에 담긴 줄이 있을 때 `Order` | 주문 요약 — 종업원에게 보여주는 화면(어디에도 주문을 보내지 않는다) | 후보 목록으로 돌아가기 |
| `result` | 음식 상세 API 200 응답 | 상세 정보 카드·나레이션 원문·오디오 두 갈래 | 이전 후보로 이동 |
| `error` | OCR 실패·메뉴 아님·미지원 음식·HTTP 실패 | 오류 유형별 안내 | 재시도 또는 새 메뉴 촬영 |

**화면마다 URL을 만들지 않는다.** 배포처인 HF static Space에 SPA fallback이 없어
`/landing` 같은 경로는 새로고침 한 번에 404가 된다(`ui-flow.md`).

## How

### 실제 HTTP API 계약

| 사용자 행동 | 요청 | 실제 성공 응답 | 프런트엔드 처리 |
|---|---|---|---|
| 이미지 분석 | `POST /api/analyze` | `{ status, ocr_text, candidates }` | 상태 분기 후 후보를 화면 모델로 변환 |
| 지원 음식 목록 | `GET /api/foods` | `[{ food_id, name_kr, name_en }]` | 설정 창의 "Supported dishes" 목록(`docs/specs/supported-foods.md`) |
| 장바구니 | `GET`·`DELETE /api/cart`, `POST /api/cart/items` | `CartResponse`(카트 전체 상태) | 응답을 그대로 갈아끼운다. 계약은 `docs/specs/cart.md` |
| 음식 상세 조회 | `GET /api/foods/{food_id}` | `{ food_id, name_kr, name_en, spice_level, details, narration_text, style, tts_status, narration_audio_path, tts_latency_ms, name_audio_path, name_tts_status }` | 중첩 `details`를 카드로 표시하고, 두 오디오 경로 앞에 API 주소를 붙여 재생 |

`POST /api/analyze`는 `multipart/form-data`의 `image` 필드를 받는다.

```json
{
  "status": "candidates_found",
  "ocr_text": "비빔밥 12,000",
  "candidates": [
    {
      "food_id": 1,
      "name_kr": "비빔밥",
      "name_en": "Bibimbap",
      "score": 100,
      "modifiers": {"spice": [], "ingredient": []},
      "spice_level": 2,
      "line_no": 1,
      "menu_text": "비빔밥 12,000",
      "name_text": "비빔밥",
      "price_krw": 12000,
      "price_krw_display": "₩12,000",
      "thumbnail_url": "https://.../Bibimbap.jpg",
      "thumbnail_attribution": "Source: Wikimedia Commons, ...",
      "source": {"text": "비빔밥", "left": 0.11, "top": 0.24, "width": 0.28, "height": 0.05}
    }
  ]
}
```

후보는 **메뉴판 "줄" 단위**라 같은 `food_id`가 여러 번 올 수 있다 — 목록의 유일 키로 쓰지 말고
`menu_text`로 구분한다. 필드 정의의 정본은 `docs/specs/api-layer.md`다.

분석 상태는 다음처럼 처리한다.

| `status` | 후보 배열 | 프런트엔드 화면 |
|---|---|---|
| `candidates_found` | 하나 이상 | 후보 선택 화면 |
| `ocr_empty` | 빈 배열 | 글자를 못 읽음 — 촬영 품질 안내 |
| `not_a_menu` | 빈 배열 | 글자는 읽혔지만 가격 붙은 메뉴 줄이 없음. **다시 찍으면 해결되는** 상황이라 아래와 문구가 달라야 한다 |
| `unsupported_food` | 빈 배열 | 미지원 음식 — 다시 찍어도 결과가 같다 |

`GET /api/foods/{food_id}`는 음식명도 함께 돌려준다. 다만 결과 제목에는 **후보 선택 단계에서
받은 값**을 그대로 쓴다 — 상세 응답에 없는 메뉴판 글자·가격(`name_text`·`price_krw_display`)을
같은 자리에 함께 보여야 하므로, 선택 시점의 후보 객체를 들고 넘어가는 편이 단순하다.

```json
{
  "food_id": 1,
  "name_kr": "비빔밥",
  "name_en": "Bibimbap",
  "spice_level": 2,
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
  "tts_status": "ok",
  "narration_audio_path": "/audio/tmpn45xqico.wav",
  "tts_latency_ms": 1.8,
  "name_audio_path": "/audio/tmpm_m9lufr.wav",
  "name_tts_status": "ok"
}
```

`details`에는 음성 전용 `PRONUNCIATION_TTS`가 함께 올 수 있다 — **화면에는 그리지 않는다**
(`DETAIL_CARDS`에 없는 키는 무시한다).

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
| `candidates[].name_text` · `price_krw_display` | 후보·결과 화면의 메뉴판 글자와 가격 |
| `candidates[].source` | 원본 사진 위에 얹는 번호 박스(0~1 비율을 %로 변환) |
| `candidates[].line_no` | 목록 정렬 기준 — 메뉴판에 인쇄된 순서 |
| `narration_text` | 듣는 문장을 눈으로 따라갈 수 있게 화면에 함께 싣는다 |
| `tts_status` · `name_tts_status` | `ok`가 아니면 그 재생 수단만 비활성. 텍스트는 그대로 |
| `narration_audio_path` | `resolveAudioUrl()`로 API 주소를 앞에 붙여 아래 **가로 재생바**에 건다 |
| `name_audio_path` | 같은 방식으로 **이름 옆 스피커**에 건다. 하나를 재생하면 다른 하나는 멈춘다 |

### 지원 음식 목록 처리

지원 음식의 단일 출처는 Supabase `foods` 테이블이다. 프런트엔드는 DB와 갈라질 수 있는
`SUPPORTED_DISHES` 같은 상수를 두지 않고, **설정 창이 열릴 때 `GET /api/foods`를 호출해** 받은
목록을 그대로 보여준다(`Home.tsx`의 `SupportedFoodsSection`).

- 응답이 배열인지 확인하고 쓴다. API 주소가 비어 있으면 요청이 같은 출처로 가고, 정적 파일
  서버는 없는 경로에 404가 아니라 `index.html`을 **200으로** 돌려준다 — 그것을 배열로 믿고
  `.map`을 부르면 설정 창만이 아니라 앱 전체가 흰 화면이 된다.
- 실패해도 설정 창의 나머지 항목은 그대로 동작해야 한다(`docs/specs/supported-foods.md` AC-04).

미지원 음식 화면은 “현재 서버의 지원 음식 DB에서 이 메뉴를 매칭하지 못했다”는 사실과 새 메뉴
촬영 행동만 안내한다. 전체 목록은 그 화면이 아니라 **설정 창**에서 확인한다.

### 오디오 재생 — 소리는 두 갈래다

`K_Menu_Talk.py`가 `static/audio`를 `/audio`로 정적 서빙하므로(`app.mount("/audio", ...)`),
응답의 경로는 **브라우저가 바로 재생할 수 있는 상대 URL**(`/audio/xxx.wav`)이다. 앞에
`VITE_API_BASE_URL`을 붙이는 일만 프런트가 한다(`lib/api.ts`의 `resolveAudioUrl()`).

- **이름 옆 스피커** ← `name_audio_path` (음식 이름만)
- **아래 가로 재생바** ← `narration_audio_path` (설명 전체)

둘을 나눠 둬야 이름 발음만 듣고 싶은 사람이 30초짜리 안내를 통째로 듣지 않는다. 하나를
재생하면 다른 하나는 멈춘다 — 겹쳐 나오면 둘 다 안 들린다. 자세한 화면 규칙은
`screen-spec.md`, 서버 계약은 `docs/specs/api-layer.md`.

`tts_status`가 `ok`가 아니거나 경로가 `null`이면 그 재생 수단만 감추고 **상세 텍스트와
나레이션 원문은 그대로 보여준다**(AC-05).

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

**AC-05 · TTS 미준비**

- GIVEN: `tts_status = not_ready`이고 `narration_audio_path`가 `null`이다.
- WHEN: 결과 화면을 표시한다.
- THEN: 오디오 플레이어 오류를 만들지 않고 텍스트 나레이션과 상태 안내를 표시한다. `name_tts_status`가 `ok`면 이름 스피커는 그대로 동작한다.

**AC-06 · 존재하지 않는 음식**

- GIVEN: `GET /api/foods/{food_id}`가 404를 반환한다.
- WHEN: 프런트엔드가 상세 조회 오류를 처리한다.
- THEN: 서비스 오류 안내와 재시도 행동을 표시한다.

**AC-07 · 오디오 재생**

- GIVEN: `tts_status = ok`이고 두 오디오 경로가 모두 `/audio/...`로 온다.
- WHEN: 사용자가 이름 옆 스피커와 가로 재생바를 차례로 누른다.
- THEN: 각각 이름 음성과 설명 음성이 재생되고, 하나를 재생하면 다른 하나는 멈춘다.

**AC-08 · 메뉴판이 아닌 사진**

- GIVEN: `POST /api/analyze`가 `status = not_a_menu`를 반환한다.
- WHEN: 프런트엔드가 응답을 수신한다.
- THEN: `ocr_empty`·`unsupported_food`와 **다른 문구**로 안내하고 새 촬영 행동을 제공한다.

## References

[1]: ../../K_Menu_Talk.py "FastAPI /api/analyze 및 /api/foods/{food_id} 구현"
[2]: ../../docs/specs/api-layer.md "백엔드 API 레이어 Spec"
[3]: ../client/src/pages/Home.tsx "React 화면 상태, API 호출, 응답 변환"
[5]: ../client/src/lib/api.ts "HTTP 계약과 타입 — Pydantic 응답 모델을 그대로 옮긴 곳"
[4]: ../../src/db/cache.py "foods 테이블을 지원 음식의 단일 출처로 사용하는 캐시 계층"
