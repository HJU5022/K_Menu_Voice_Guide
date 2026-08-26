# Spec — 백엔드 API 레이어 (FastAPI)

## Why

- **페르소나**: 백엔드(`src/pipeline.py`)와 별도로 만들어진 웹 프론트엔드(React 기반 시뮬레이션, "K-Menu Web Playground")를 붙이는 재훈·백호님, 그리고 향후 Flutter 앱.
- **상황**: 백엔드 로직(`analyze_image`, `create_tts_response`, `get_details`)은 이미 있지만, 파이썬 함수 호출로만 접근 가능하다. 프론트엔드는 별도 프로세스(브라우저/앱)에서 돌아가므로 HTTP로 호출해야 한다.
- **문제**: Gradio를 전제로 배포전략을 짰었는데(README 4장 배포 전략), 실제 프론트엔드는 Gradio 화면이 아니라 독립된 웹앱이라 Gradio의 기본 UI로는 계약이 맞지 않는다. HTTP API가 없어 프론트가 백엔드를 호출할 방법이 없다.
- **측정 지표**: 프론트가 이미지 하나로 후보 목록을 받고, 후보 하나로 상세정보+나레이션을 받는 왕복을 각각 성공적으로 마치는지 테스트로 검증한다.

## Goal

- **해결 목표**: 기존 `src/pipeline.py`의 `analyze_image()`, `create_tts_response()`, `src/text_gen/detail.py`의 `get_details()`를 HTTP로 노출한다.
- **성공 기준**:
  1. 이미지를 업로드하면 OCR 상태(`ocr_empty`/`not_a_menu`/`unsupported_food`/`candidates_found`)와 후보 목록을 JSON으로 받는다.
  2. `food_id`로 상세정보(6개 카테고리)와 나레이션 결과(텍스트·스타일·오디오 상태)를 JSON으로 받는다.
  3. 등록되지 않은 `food_id`는 404를 반환한다.
- **Out of Scope**: 프론트엔드 코드 자체, 인증/로그인, 주문·결제 기능, Flutter 클라이언트 코드, 배포(HF Spaces/Tailscale) 설정. 장바구니(`/api/cart`)는 별도 Spec(`docs/specs/cart.md`)에서 다룬다.

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
| EC-02 | 업로드된 파일이 이미지가 아니거나 손상됨 | **400**과 함께 "사진을 읽을 수 없습니다"를 반환한다. 한때는 파이프라인 예외를 그대로 500으로 흘려보냈는데(2026-08-26 이전), 500은 "서버 잘못"이라는 뜻이라 화면이 사용자 입력 문제와 서버 장애를 구별하지 못했다 — 실측으로 텍스트 파일·12MB 파일이 모두 500으로 나와 화면에 똑같이 "다시 찍으세요"가 떴다 |
| EC-03 | TTS 모델이 아직 준비 안 됨 (GPU 없음 등) | 기존 `tts_status: "not_ready"`를 그대로 응답에 담아 전달 — 이 레이어에서 예외로 바꾸지 않음 |
| EC-04 | OCR 결과 없음/미지원 음식 | `analyze_image()`가 이미 반환하는 `ocr_empty`/`unsupported_food` 상태를 그대로 전달 |
| EC-05 | 메뉴판이 아닌 사진 | 글자는 읽혔지만 가격 붙은 메뉴 줄이 하나도 없으면 `not_a_menu`. 얼굴·풍경을 찍어도 OCR이 잡음 글자를 만들어내 `ocr_empty`로는 안 잡히는데, 이쪽은 **다시 찍으면 해결되는** 상황이라 화면이 다른 안내를 띄워야 한다 |
| EC-06 | 음식에 등록된 썸네일이 없음 | `thumbnail_url`/`thumbnail_attribution`을 `null`로 반환 — 프론트는 이 경우 번호 아이콘으로 대체 표시 |
| EC-07 | 업로드 파일이 이미지가 아님 (`content-type`) | **400** "이미지 파일만 업로드할 수 있습니다." 가장 싼 검사라 파일을 읽기 전에 먼저 한다 |
| EC-08 | 업로드 본문이 0바이트 | **400** "빈 파일입니다." 업로드 중 취소·네트워크 끊김에서 실제로 나온다 |
| EC-09 | 업로드가 **10MB 초과** | **413** "사진이 너무 큽니다 (최대 10MB)." 상한 근거는 아래 How 참고 |
| EC-10 | 임시 파일 정리 | 성공·실패 어느 쪽이든 `finally`에서 지운다. 예전에는 `delete=False`로 만들고 지우지 않아 요청마다 Space 디스크에 쌓였다 |

## How

```
POST /api/analyze
요청: multipart/form-data, 필드 "image" (파일)

응답 200:
{
  "status": "ocr_empty" | "not_a_menu" | "unsupported_food" | "candidates_found",
  "ocr_text": string,
  "candidates": [
    {
      "food_id": int,
      "name_kr": string,
      "name_en": string,
      "score": int,
      "modifiers": {
        "spice":      [{"keyword": string, "keyword_en": string | null, "tier": 1..5}],
        "ingredient": [{"keyword": string, "keyword_en": string | null}]
      },
      "spice_level": 1 | 2 | 3 | 4 | 5 | null,
      "menu_text": string | null,
      "name_text": string | null,
      "thumbnail_url": string | null,
      "thumbnail_attribution": string | null
    }
  ]
}
```

**수식어는 영어와 함께 싣는다.** 화면이 보여주는 것은 `keyword_en` 쪽이다 — 이 서비스를
쓰는 사람은 한국어를 읽지 못한다. 같은 음식이 여러 줄 나올 때(`돼지김치찌개` /
`참치김치찌개`) 후보 이름은 둘 다 "Kimchi Jjigae"로 같으므로, 이 태그가 서로를 구분할
수 있는 유일한 수단이다. `spice_level`은 그 음식 자체의 맵기이며 후보 카드의 불꽃 눈금에
쓴다(수식어의 `tier`와는 별개 값이다).

**후보는 메뉴판 "줄" 단위다.** 같은 `food_id`가 여러 번 나올 수 있다 — 메뉴판에
"물만두"와 "군만두"가 둘 다 있으면 후보도 둘이고, 둘 다 `food_id`는 같다.
프론트는 `food_id`를 목록의 유일 키로 쓰면 안 되고, `menu_text`(그 줄에 인쇄된
글자 그대로)로 구분해야 한다. 순서는 메뉴판을 읽는 순서(위→아래)다.

**이름을 보여줄 자리에는 `name_text`를 쓴다.** `menu_text`에서 가격만 뗀 값이다
(`김치전/부추전 W7,000` → `김치전/부추전`). 화면은 가격을 이미 따로 보여주므로
줄 글자를 그대로 쓰면 같은 값이 두 번 보인다. 줄을 구분하는 기준은 계속
`menu_text`다 — `name_text`는 표시 전용이고, 뗄 것이 없으면 줄 글자와 같다.
**등록 음식과 매칭되지 않은 줄은 응답에 싣지 않는다**(2026-08-25 결정). 한때는
`unsupported_lines`로 이름·가격만 함께 보냈는데, 그 줄에 대해 아는 것이 OCR이 읽은
글자와 같은 줄에서 주운 숫자뿐이라 원산지 표시·가게 공지가 메뉴로 올라오고 엉뚱한
가격이 붙었다. 다만 서버는 그런 줄의 **개수를 보고 `not_a_menu`를 판정한다** —
메뉴 줄이 하나도 없으면 애초에 메뉴판이 아니다.

```
GET /api/foods/{food_id}

응답 200:
{
  "spice_level": 1 | 2 | 3 | 4 | 5,
  "details": {"DESCRIPTION": string, "PRONUNCIATION": string, ...},
  "narration_text": string,
  "style": "GUIDE" | "CAUTION",
  "tts_status": "ok" | "not_ready",
  "narration_audio_path": string | null,
  "tts_latency_ms": number,
  "name_audio_path": string | null,
  "name_tts_status": "ok" | "not_ready"
}

응답 404: food_id가 존재하지 않음
```

**소리가 두 갈래인 이유** (2026-08-26 추가). `narration_audio_path`는 설명 전체를,
`name_audio_path`는 **음식 이름만** 읽은 음성이다. 화면은 이름 옆 스피커에 뒤엣것을,
아래 재생바에 앞엣것을 건다. 한 파일로 두면 이름 발음만 듣고 싶은 사람이 30초짜리
안내를 통째로 듣게 되는데, 통짜 wav에서 이름 부분만 떼어낼 방법이 없어 처음부터
따로 만든다.

두 음성 모두 **읽는 값은 한글**이다(`foods.name_kr`). 화면에는 로마자(`Galbitang`)가
보이지만 모델에는 한글을 넘긴다 — 로마자를 주면 영어 음운으로 읽는다. 치환은
`src/text_gen/narration.py`가 한다.

캐시 파일명이 다르다 — 나레이션은 `static/tts_cache/food_{id}_{STYLE}.wav`,
이름은 `static/tts_cache/name_{id}.wav`. 둘 다 없으면 요청 시점에 생성한다.

- 대상 파일: `K_Menu_Talk.py` (README에 이미 "배포 진입점"으로 문서화된 파일 — Gradio 대신 FastAPI 앱을 둠)
- 업로드된 이미지는 임시 파일로 저장 후 기존 `analyze_image(image_path)`에 그대로 전달한다 (OCR 쪽 함수 시그니처를 바꾸지 않음).

- 응답 스키마는 Pydantic 모델로 고정한다 — FastAPI가 `/docs`에 자동으로 계약을 문서화하므로, 프론트엔드가 이 페이지를 보고 연동할 수 있다.

**업로드 검증 (`POST /api/analyze`)**

```
응답 400: {"detail": "이미지 파일만 업로드할 수 있습니다."}   content-type이 image/ 로 시작하지 않음
응답 400: {"detail": "빈 파일입니다."}                      본문 0바이트
응답 400: {"detail": "사진을 읽을 수 없습니다."}              저장은 됐으나 이미지로 열리지 않음
응답 413: {"detail": "사진이 너무 큽니다 (최대 10MB)."}       10MB 초과
```

검사 순서는 **싼 것부터**다 — content-type(헤더만 봄) → 크기(읽으면서 셈) → 0바이트 →
실제 디코드(가장 비쌈). 확장자만 바꾼 파일은 content-type으로 걸러지지 않으므로
**실제로 열리는지**가 마지막 판정이다.

상한을 10MB로 잡은 근거: 모바일 사진이 보통 2~5MB라 정상 사용을 막지 않는다.

크기는 **읽으면서 센다.** `await image.read()`로 통째로 읽은 뒤 크기를 재면 이미 메모리에
다 올라간 뒤라 상한의 의미가 없다 — 실측(2026-08-26)에서 12MB가 3.3초에 걸쳐 전량 수신된
뒤에야 실패했다. 1MB씩 끊어 쓰며 누적이 상한을 넘으면 그 자리에서 중단한다.

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

**AC-05 · 후보 썸네일·출처 전달**
- GIVEN: `foods` 테이블의 `thumbnail_url`·`thumbnail_attribution` 컬럼에 값이 있다.
- WHEN: `POST /api/analyze`가 그 음식을 후보로 반환한다.
- THEN: 후보 객체에 `thumbnail_url`과 `thumbnail_attribution`이 그대로 실려 있다. 값이 없는 음식은 두 필드 모두 `null`이다 (테스트: `tests/test_ocr_match.py`, `tests/test_cache.py`).

**AC-06 · 이미지가 아닌 업로드 거절**
- GIVEN: `content-type`이 `text/plain`인 파일이 있다.
- WHEN: `POST /api/analyze`에 업로드한다.
- THEN: 응답 400과 `detail: "이미지 파일만 업로드할 수 있습니다."`를 받는다. `analyze_image()`는 호출되지 않는다.

**AC-07 · 빈 파일 거절**
- GIVEN: 0바이트 파일이 `image/jpeg`로 올라온다.
- WHEN: `POST /api/analyze`에 업로드한다.
- THEN: 응답 400과 `detail: "빈 파일입니다."`를 받는다.

**AC-08 · 크기 상한 초과 거절**
- GIVEN: 10MB를 넘는 파일이 `image/jpeg`로 올라온다.
- WHEN: `POST /api/analyze`에 업로드한다.
- THEN: 응답 413과 `detail: "사진이 너무 큽니다 (최대 10MB)."`를 받는다. `analyze_image()`는 호출되지 않는다.

**AC-09 · 이미지로 열리지 않는 파일 거절**
- GIVEN: `content-type`은 `image/jpeg`지만 내용이 이미지가 아니라 `analyze_image()`가 `ValueError`를 던진다.
- WHEN: `POST /api/analyze`에 업로드한다.
- THEN: 응답 400과 `detail: "사진을 읽을 수 없습니다."`를 받는다 (500이 아니다).

**AC-10 · 임시 파일 정리**
- GIVEN: 업로드가 성공하든 실패하든 상관없다.
- WHEN: `POST /api/analyze` 처리가 끝난다.
- THEN: 그 요청이 만든 임시 파일이 디스크에 남아 있지 않다.
