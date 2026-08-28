# Spec — Flutter 모바일 앱

## Why

- **페르소나**: 한국을 처음 방문한 영어권 관광객. 한국어를 읽지 못한다.
- **상황**: 식당에 앉아 한국어 메뉴판을 앞에 두고, 손에는 스마트폰이 있다.
- **문제**:
  1. 사용 장면 자체가 "식당에서 폰으로 메뉴판을 찍는" 것인데, 웹앱은 매번 브라우저를 열고 주소를 입력해 들어가야 한다.
  2. 카메라 촬영이 브라우저 파일 선택 흐름을 거쳐야 해서, 찍어서 바로 묻는 동작이 끊긴다.
  3. 홈 화면에 아이콘이 없어 재방문 경로가 남지 않는다.
- **측정 지표**: 사용자 지표는 현재 미측정. 이번 범위에서는 지표 개선이 아니라 **동일 기능을 네이티브 앱 형태로 제공할 수 있는지**를 확인한다.

**서버 응답 시간 실측** (2026-08-22, macOS·CPU, TTS 사전 생성 캐시가 채워진 상태)

| 요청 | 1회차 | 2회차 이후 |
|---|---|---|
| `POST /api/analyze` (OCR) | 10.0초 | **7.9초** |
| `GET /api/foods/{id}` | 1.9초 | **0.018초** |
| `/audio/*.wav` 다운로드 (876KB) | — | 0.011초 |

1회차가 느린 것은 모델·DB를 메모리에 올리기 때문이다. 화면 설계 시 **OCR 약 8초**를 기준으로 로딩 표시를 만든다 — 이 구간이 전체 대기의 대부분이다. 상세 조회는 캐시 히트라 사실상 즉시다(캐시가 없으면 33초이므로 `static/tts_cache/`가 채워져 있어야 한다).

## Goal

- **해결 목표**: 기존 백엔드(`K_Menu_Talk.py`)를 그대로 사용하면서, 촬영부터 음성 재생까지의 전 과정을 iOS·Android 앱 하나로 제공한다.
- **성공 기준**
  - 실제 iPhone 또는 Android 실기기에서 촬영 → 음식 후보 → 상세 6개 카테고리 → 내레이션 음성 재생까지 **중간 실패 없이 1회 완주**한다.
  - 후보·상세 화면의 음식명 스피커는 기기 기본 음성이 아니라 서버가 미리 생성해 둔 `name_audio_path` 캐시 WAV를 재생한다.
  - 서버 주소를 바꿀 때 **`lib/config.dart` 한 파일만** 수정하면 된다(개발·터널·배포 환경 전환).
  - 앱은 `src/` 로직을 복제하지 않는다 — OCR·매칭·텍스트·TTS는 전부 서버가 수행한다.
  - 처음 실행한 사용자는 촬영 화면 위에 4단계 사용 안내를 한 번 보고, 닫은 뒤에는 다음 실행부터 촬영 화면을 바로 사용한다.
- **Out of Scope**
  - 음성 질문 입력(STT) — 프로젝트에 STT 모듈 자체가 없다. 마이크를 쓰지 않는다.
  - App Store / Play Store 등록
  - 오프라인 동작, 로컬 캐싱, 로그인
  - 계정·서버에 첫 실행 여부 저장, 안내를 다시 띄우는 별도 설정 버튼

## What

**Happy Path**

1. 처음 실행한 사용자가 앱을 열면 촬영 화면 위 중앙에 사용 안내 모달이 뜬다.
   - 안내는 `Take a photo → Choose a dish → Understand the dish → Show your order` 네 장이다.
   - 각 장에는 긴 설명 대신 다음 화면에서 보게 될 메뉴판·후보 카드·음식 안내·주문서의 축약 그림을 함께 둔다.
   - 사용자는 좌우로 넘기며 볼 수 있고, `Skip`·아래 스와이프·마지막 `Start scanning`으로 닫을 수 있다.
   - 닫은 뒤에는 기기에 완료 여부를 저장해 다음 실행에서 자동으로 다시 띄우지 않는다. 상세한 제한사항은 Settings의 `How it works`에서 확인한다.
2. 사용자가 촬영 화면에서 카메라로 메뉴판을 촬영한다(또는 사진첩에서 고른다).
3. 앱이 이미지를 `POST /api/analyze`로 보낸다.
4. 서버가 돌려준 음식 후보를 **음식 사진·영문명·한글명·가격** 카드로 보여주고, 사용자가 하나를 고른다.
   - 후보가 하나뿐이면 이 화면을 건너뛰고 바로 상세 화면으로 간다(EC-11).
   - 가격은 DB 값이 아니라 **그 메뉴판 사진에 실제로 적혀 있던 값**을 서버가 읽어준 것이다.
   - 사진이나 가격이 없는 후보는 그 자리를 비운다. 없는 값을 문구로 채우지 않는다.
   - 음식명 스피커를 누르면 앱이 해당 `food_id`의 상세를 조회하고, `name_audio_path`로 받은 캐시 WAV를 재생한다. 기기 기본 TTS는 사용하지 않는다.
5. 앱이 `GET /api/foods/{food_id}`를 호출한다.
6. 상세 6개 카테고리를 화면에 표시하고, `narration_audio_path`의 내레이션과 `name_audio_path`의 음식명 음성을 각각 재생한다.

**Edge Cases**

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | 카메라 권한 거부 | 안내 문구 + 사진첩 선택으로 대체 경로 제공 |
| EC-02 | 서버 연결 실패(주소 오류·서버 꺼짐·네트워크 없음) | "서버에 연결할 수 없습니다" + 재시도 버튼. 현재 `apiBaseUrl` 값을 함께 노출해 원인 파악을 돕는다 |
| EC-03 | OCR 결과 없음 (`status = "ocr_empty"`) | `docs/content-style.md`의 "예외 화면 문구" 표를 그대로 쓴다 — 조명·거리·각도 안내 후 재촬영 유도 |
| EC-04 | 등록되지 않은 음식 (`status = "unsupported_food"`) | 미지원 안내 + 재촬영. 읽힌 글자가 있으므로 EC-03과 다른 문구를 쓴다 |
| EC-05 | TTS 실패 (`tts_status != "ok"` 또는 `narration_audio_path`가 null) | **상세 텍스트를 먼저 보여준다.** 음성 영역만 비활성 표시 (음성이 없어도 상세 텍스트만으로 메뉴를 고를 수 있어야 한다) |
| EC-05a | 이름 음성 캐시 없음 (`name_tts_status != "ok"` 또는 `name_audio_path`가 null) | 후보·상세의 이름 스피커를 재생하지 않고, 텍스트·상세 조회·나레이션은 정상 유지한다 |
| EC-06 | 음성 파일 다운로드·재생 실패 | 텍스트는 유지하고 재생 버튼만 오류 표시 |
| EC-08 | 후보 카드의 음식 사진을 못 받음 | 회색 자리표시(접시 아이콘)로 대체. 오류를 사용자에게 알리지 않는다 — 이름과 가격만으로도 고를 수 있다 |
| EC-09 | 후보의 가격을 서버가 못 읽음 | 가격 자리를 비운다. "가격 미상" 같은 문구로 채우지 않는다 |
| EC-10 | 상세 화면에서 서버 호출 실패 | 화면 안에서 재시도 버튼을 제공한다. 뒤로 나갔다 들어오게 만들지 않는다 |
| EC-07 | 응답 지연(첫 요청 시 서버 모델 로딩) | 로딩 표시를 유지하고 사용자 입력을 막는다. 타임아웃은 두지 않는다 |
| EC-11 | 후보가 1개뿐 | 선택 화면을 건너뛰고 바로 상세 화면으로 간다 — 고를 것이 없다. 웹앱(`frontend/docs/web-app.md` EC-03)과 같은 동작 |
| EC-12 | 메뉴판이 아닌 사진 (`status = "not_a_menu"`) | EC-03·EC-04와 **다른 문구**로 안내하고 재촬영을 유도한다. 얼굴·풍경을 찍어도 OCR이 잡음 글자를 만들어내 `ocr_empty`로는 안 잡히는데, 이쪽은 다시 찍으면 해결되므로 "지원하지 않는 음식"이라고 하면 사용자가 포기한다 |

**후보가 사진 어디에서 나왔는지** — 후보 화면 위쪽에 방금 찍은 사진을 두고, 후보가 읽힌 자리에 번호 상자를 얹는다. 상자와 카드 배지가 **같은 번호·같은 색**이라 눈으로 짝지을 수 있다. 목록만 보면 "왜 이게 나왔지?"를 확인할 방법이 없는데, 실제로 사진에 없는 음식이 후보로 뜬 적이 있어(`막국수` → `칼국수`) 판단 근거를 화면에 둔다. 좌표는 서버가 원본 사진 기준 0~1 비율로 준다(`candidate.source`). 번호는 두 자리로 적는다(`01`, `02` …).

**사진을 누르면 전체 화면으로 열려 확대·이동할 수 있다.** 목록 안의 사진은 작아서 번호 상자가 메뉴 글자를 덮는다 — 실기기에서 메뉴 24개짜리 메뉴판을 찍었을 때 상자가 이름을 거의 다 가려, 무엇을 읽었는지 확인하려던 목적 자체가 무너졌다. 목록 안에서 바로 확대하지 않는 이유는 사진이 스크롤 목록 안에 있어 끌기 동작이 목록 스크롤과 구분되지 않기 때문이다. 확대는 Flutter 기본 위젯 `InteractiveViewer`로 하고 외부 패키지를 쓰지 않는다.

**이름을 보여주는 자리에는 가격을 뺀 글자(`name_text`)를 쓴다.** 카드가 가격을 이미 따로 보여주므로, 줄 글자를 그대로 쓰면 "김치전/부추전 ₩7,000" 밑에 "₩7,000"이 또 붙는다. 줄을 구분하는 신원은 계속 `menu_text`다(`api-layer.md`).

**장바구니** — 후보 화면에서 메뉴를 담고 총계를 본다. 규칙은 `docs/specs/cart.md`를 따르며, 그중 앱에서 짚어둘 것은 **새 메뉴판을 성공적으로 분석하면 카트를 비운다**는 점이다(EC-09). 카트는 앱이 아니라 "지금 이 식당"에 묶이기 때문이다. 촬영이 실패해 되돌아온 경우는 새 식당이 아니므로 카트를 유지한다(EC-10).

**지원 음식 목록** — 촬영 화면 상단바의 톱니바퀴에서 설정 화면으로 들어가면 안내 가능한 음식 전체를 영문명·한글명으로 확인할 수 있다. 화면 구성과 예외 처리는 `docs/specs/supported-foods.md`를 따른다.

## How

**서버 계약** — 기존 `docs/specs/api-layer.md`를 그대로 따른다. 앱을 위해 서버를 바꾸지 않는다.

```
POST /api/analyze
요청: multipart/form-data, 필드명 "image" (JPEG)
응답 200:
{
  "status": "candidates_found" | "not_a_menu" | "unsupported_food" | "ocr_empty",
  "ocr_text": string,
  "candidates": [
    { "food_id": int, "name_kr": string, "name_en": string,
      "score": int, "modifiers": object,
      "spice_level": int | null,               // 1~5. 카드의 불꽃 눈금
      "line_no": int | null,                   // 메뉴판 줄 번호 — 목록 정렬 기준
      "menu_text": string | null,              // 그 줄에 인쇄된 글자. 줄을 구분하는 신원
      "name_text": string | null,              // 위에서 가격만 뗀 것. 이름 자리에 쓴다
      "price_krw": int | null,                 // 사진에서 읽은 값 (DB 값 아님)
      "price_krw_display": string | null,      // 예 "₩8,000"
      "thumbnail_url": string | null,          // 완전한 URL
      "thumbnail_attribution": string | null,
      "source": object | null }                // 사진 속 이름 위치(원본 기준 0~1 비율)
  ]
}

status 네 값의 의미 (src/pipeline.py analyze_image):
  candidates_found  후보를 찾음 — candidates에 1개 이상
  not_a_menu        글자는 읽혔으나 가격 붙은 메뉴 줄이 하나도 없음 — 메뉴판이 아닌 사진.
                    **다시 찍으면 해결되는** 상황이라 unsupported_food와 문구가 달라야 한다
  unsupported_food  메뉴 줄은 있으나 등록된 50개 음식과 매칭 실패 — candidates 빈 배열
  ocr_empty         글자를 전혀 읽지 못함 — ocr_text·candidates 모두 빈 값
앱은 이 값으로 분기한다. 성공 값이 "ok"가 아님에 주의.

GET /api/foods/{food_id}
응답 200:
{
  "food_id": int,
  "name_kr": string, "name_en": string,
  "spice_level": 1 | 2 | 3 | 4 | 5,
  "details": { "DESCRIPTION": string, "HOW_TO_EAT": string,
               "INGREDIENT": string, "ALLERGY": string,
               "PRONUNCIATION": string, "SPICY": string },
  "narration_text": string,
  "style": "GUIDE" | "CAUTION",
  "tts_status": string,
  "narration_audio_path": string | null,
  "tts_latency_ms": float,
  "name_audio_path": string | null,            // 음식 이름만 읽은 음성 (서버 TTS)
  "name_tts_status": string
}
응답 404: 등록되지 않은 food_id

GET /api/foods                                  // 설정 화면의 지원 음식 목록
응답 200: [ { "food_id": int, "name_kr": string, "name_en": string } ]

GET / POST / DELETE  /api/cart…                 // 장바구니, X-Cart-Id 헤더 필수
```

`details`에는 음성 전용 `PRONUNCIATION_TTS`가 섞여 올 수 있다 — 아래 "상세 화면 카테고리
순서"에 없는 키는 그리지 않는다.

**중요** — `narration_audio_path`와 `name_audio_path`는 `/audio/xxx.wav` 형태의 **상대 경로**다. 앱은 여기에 `apiBaseUrl`을 앞에 붙여 완전한 URL로 만들어야 재생할 수 있다. 이 WAV는 HF Space가 사전 생성 캐시에서 제공하는 파인튜닝 TTS 결과이며, 앱은 음식 이름에 기기 기본 TTS를 쓰지 않는다.

**서버 주소 관리**

`lib/config.dart`의 `apiBaseUrl` 상수 한 곳에서만 관리한다. 다른 파일은 이 상수를 참조할 뿐 주소 문자열을 직접 갖지 않는다.

| 환경 | 값 | 비고 |
|---|---|---|
| 시뮬레이터 | `http://localhost:8000` | 시뮬레이터는 맥 안에서 돌아 맥의 IP 변동에 영향받지 않는다 |
| 실제 기기 | `http://<맥 로컬 IP>:8000` | 폰이 맥과 같은 Wi-Fi. `ipconfig getifaddr en0`으로 확인 |
| 시연 | `https://<...>.trycloudflare.com` | cloudflared 터널 |
| **배포** | `https://hju5022-k-menu.hf.space` | **현재 기본값.** 맥이 꺼져 있어도, 폰이 다른 망에 있어도 닿는다 |

**로컬 서버로 되돌릴 때는 LAN IP로 바꿔야 한다** — 폰에게 `localhost`는 폰 자신이라 서버를 찾지 못한다. 이 값은 Wi-Fi를 옮기거나 공유기가 주소를 다시 할당하면 바뀌고, Wi-Fi가 끊기면 아예 없어진다. 앱이 "Can't reach the server"를 띄우면 여기부터 확인한다(실제로 개발 중 한 번 발생했고, 화면이 주소를 함께 보여준 덕에 즉시 원인을 특정했다).

**패키지**

| 패키지 | 용도 |
|---|---|
| `image_picker` | 카메라 촬영 / 사진첩 선택 |
| `http` | API 호출 |
| `audioplayers` | 서버가 만든 내레이션·이름 WAV 재생 |
| `flutter_tts` | **기기에 깔린 음성**으로 한국어 메뉴 이름 읽기 (`lib/korean_speaker.dart`) — 우리 TTS와 별개다. 우리 모델은 영어 설명을 읽도록 학습돼 한국어 이름을 발음하지 못하고, 등록 안 된 메뉴는 읽을 대본 자체가 없다 |
| `shared_preferences` | 첫 실행 안내를 닫았는지 기기에 boolean으로 저장 |

**iOS 필수 설정** — `ios/Runner/Info.plist`

| 키 | 없을 때 |
|---|---|
| `NSCameraUsageDescription` | 촬영 시도 시 앱이 즉시 종료된다 |
| `NSPhotoLibraryUsageDescription` | 사진첩 열 때 종료된다 |
| `NSAppTransportSecurity` → `NSAllowsArbitraryLoads` | `http://` 요청이 전부 차단된다 |

`NSAllowsArbitraryLoads`는 암호화되지 않은 통신을 허용하는 보안 완화다. 개발·시연 단계의 `http` 로컬 서버 때문에 필요하며, 서버가 `https`로 옮겨가면 제거한다.

**상세 화면 카테고리 순서**

서버가 주는 `details`는 순서가 없는 묶음이라, 무엇을 어떤 순서로 보여줄지는 앱이 정한다. 순서와 영어 제목은 웹앱(`frontend/client/src/pages/Home.tsx`의 `DETAIL_CARDS`)과 맞춘다 — 같은 서비스인데 웹과 앱의 문구가 다르면 안 된다.

```
DESCRIPTION / HOW_TO_EAT / INGREDIENT / ALLERGY / PRONUNCIATION / SPICY
```

서버가 특정 카테고리를 비워 보내면 그 카드는 건너뛴다. 빈 카드가 있으면 정보가 누락된 것처럼 보인다.

**음성 재생**

상세 화면에 들어오면 자동으로 재생을 시작한다 — 음성 가이드가 이 서비스의 목적이다. 재생 버튼은 재생기의 상태 변화를 받아 모양이 바뀐다(▶ ↔ ⏸). 사용자가 눌러 멈춘 경우와 끝까지 재생돼 멈춘 경우가 같은 통로로 들어온다.

화면을 떠날 때 재생기를 반드시 정리한다. 그러지 않으면 뒤로 가도 소리가 계속 난다.

**줄 번호가 없는 후보는 목록 맨 뒤로 보낸다** (2026-08-27). 서버는 메뉴판에서 줄 위치를
잡지 못한 후보에 `line_no`를 null로 준다. 앱은 이걸 0으로 바꿔 정렬해서 그런 후보가 목록
맨 앞에 왔는데, 같은 후보는 `source`(좌표)도 없어 사진 위에 상자를 그리지 못한다. 그래서
목록은 01·02부터 시작하는데 사진의 상자는 03부터 시작해, 두 번호가 어긋난 것처럼 보였다.
웹앱(`frontend/client/src/pages/Home.tsx`)이 이미 `line_no ?? Number.MAX_SAFE_INTEGER`로
맨 뒤에 보내고 있어 앱도 같은 순서로 맞춘다 — 상자를 못 그리는 후보가 뒤에 모이면 앞쪽
번호는 사진과 그대로 맞아떨어진다.

**맵기 눈금을 후보 카드에도 그린다** (2026-08-27). 서버는 후보마다 `spice_level`(1~5, 없으면
null)을 실어 보내는데(`K_Menu_Talk.py`의 `Candidate`), 앱은 이 값을 아예 읽지 않아 버리고
상세 화면에서만 맵기를 보여줬다. 매운 것을 못 먹는 사람은 어느 후보를 열어볼지 고르는
단계에서 이 정보가 필요하다. 웹앱이 후보 카드에 불꽃 5칸으로 그리고 있어 앱도 맞춘다.

- 상세 화면에만 있던 눈금 위젯을 `lib/screens/spice_gauge.dart`로 옮겨 두 화면이 같은 것을
  쓴다. 그리는 규칙(불꽃 5칸, 채운 칸 수 = `spice_level`)은 그대로다.
- 카드는 글자가 작아 불꽃 크기만 줄인다(상세 18 / 카드 14). 웹앱도 같은 이유로 상세 20 /
  카드 13으로 카드 쪽을 줄여 그린다.
- `spice_level`이 null이면 눈금을 통째로 뺀다. 0칸으로 그리면 "안 맵다"고 잘못 알려주는
  셈이라, 가격이 없을 때 자리를 비우는 것과 같은 원칙이다.

**제약**

- `src/` 아래 로직은 앱을 위해 수정하지 않는다. 앱이 필요로 하는 변경이 생기면 별도 Spec으로 분리한다.
- 앱은 Supabase에 직접 접근하지 않는다. 모든 데이터는 서버를 거친다(anon key를 앱에 넣지 않기 위함).
- **음식 사진을 보여주는 자리에는 `thumbnail_attribution`을 반드시 함께 표시한다.** 외부 데이터셋 사진을 쓰면서 출처를 남기기로 한 프로젝트 조건이므로, 가격처럼 "있으면 좋은 것"이 아니라 지켜야 하는 항목이다.

## AC (Given-When-Then)

**AC-01 · 촬영에서 후보까지**
- GIVEN: 서버가 실행 중이고 `apiBaseUrl`이 올바르게 설정되어 있다
- WHEN: 사용자가 등록된 음식이 적힌 메뉴판을 촬영한다
- THEN: 후보 선택 화면으로 자동 전환되고, 각 후보가 음식 사진·`name_en`·`name_kr`·가격 카드로 표시된다. 사진이나 가격이 없는 후보는 그 자리만 비고 카드 자체는 정상 표시된다

**AC-02 · 상세와 음성**
- GIVEN: 후보 목록에서 항목 하나가 선택되었다
- WHEN: 앱이 `GET /api/foods/{food_id}`를 호출한다
- THEN: 6개 카테고리 텍스트가 정해진 순서로 표시되고, `tts_status`가 `ok`이면 내레이션 음성이 자동 재생되며 버튼이 일시정지 모양으로 바뀐다

**AC-02a · 캐시된 음식명 음성**
- GIVEN: 서버가 `name_tts_status: "ok"` 및 `name_audio_path`를 반환한다
- WHEN: 사용자가 후보 카드 또는 상세 화면의 음식명 스피커를 누른다
- THEN: 앱은 `apiBaseUrl`을 붙인 캐시 WAV를 재생하며, 기기 기본 TTS를 호출하지 않는다

**AC-06 · 사진 출처 표시**
- GIVEN: 후보에 `thumbnail_url`과 `thumbnail_attribution`이 있다
- WHEN: 후보 선택 화면이 그려진다
- THEN: 사진과 함께 출처 문구가 카드에 표시된다 (사진만 보이고 출처가 빠지는 경우가 없어야 한다)


**AC-03 · TTS 실패 시 텍스트 우선**
- GIVEN: 서버가 `tts_status`를 `ok`가 아닌 값으로, `narration_audio_path`를 null로 응답한다
- WHEN: 상세 화면이 그려진다
- THEN: 6개 카테고리 텍스트는 정상 표시되고, 음성 영역만 비활성으로 표시된다 (화면 전체가 실패하지 않는다)

**AC-04 · 서버 연결 실패**
- GIVEN: 서버가 꺼져 있거나 `apiBaseUrl`이 잘못되었다
- WHEN: 사용자가 촬영을 마친다
- THEN: 앱이 종료되지 않고 오류 안내와 재시도 버튼을 보여준다

**AC-05 · 환경 전환**
- GIVEN: 서버를 로컬에서 터널 주소로 옮겼다
- WHEN: `lib/config.dart`의 `apiBaseUrl` 한 줄만 수정한다
- THEN: 다른 파일 수정 없이 앱이 새 서버를 호출한다
