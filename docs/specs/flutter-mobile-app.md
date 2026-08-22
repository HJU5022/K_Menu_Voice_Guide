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
  - 실제 iPhone에서 촬영 → 음식 후보 → 상세 6개 카테고리 → 내레이션 음성 재생까지 **중간 실패 없이 1회 완주**한다.
  - 서버 주소를 바꿀 때 **`lib/config.dart` 한 파일만** 수정하면 된다(개발·터널·배포 환경 전환).
  - 앱은 `src/` 로직을 복제하지 않는다 — OCR·매칭·텍스트·TTS는 전부 서버가 수행한다.
- **Out of Scope**
  - 음성 질문 입력(STT) — 프로젝트에 STT 모듈 자체가 없다. 마이크를 쓰지 않는다.
  - App Store / Play Store 등록
  - 오프라인 동작, 로컬 캐싱, 로그인
  - Android 실기기 검증 (에뮬레이터까지만)
  - 디자인 완성도 — 기능 동작이 우선

## What

**Happy Path**

1. 사용자가 앱을 열면 촬영 화면이 뜬다.
2. 카메라로 메뉴판을 촬영한다(또는 사진첩에서 고른다).
3. 앱이 이미지를 `POST /api/analyze`로 보낸다.
4. 서버가 돌려준 음식 후보 목록을 카드로 보여주고, 사용자가 하나를 고른다.
5. 앱이 `GET /api/foods/{food_id}`를 호출한다.
6. 상세 6개 카테고리를 화면에 표시하고, `narration_audio_path`의 음성을 재생한다.

**Edge Cases**

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | 카메라 권한 거부 | 안내 문구 + 사진첩 선택으로 대체 경로 제공 |
| EC-02 | 서버 연결 실패(주소 오류·서버 꺼짐·네트워크 없음) | "서버에 연결할 수 없습니다" + 재시도 버튼. 현재 `apiBaseUrl` 값을 함께 노출해 원인 파악을 돕는다 |
| EC-03 | OCR 결과 없음 (`status = "ocr_empty"`) | 루트 README 9절 기준 문구 사용 — 조명·거리·각도 안내 후 재촬영 유도 |
| EC-04 | 등록되지 않은 음식 (`status = "unsupported_food"`) | 미지원 안내 + 재촬영. 읽힌 글자가 있으므로 EC-03과 다른 문구를 쓴다 |
| EC-05 | TTS 실패 (`tts_status != "ok"` 또는 `narration_audio_path`가 null) | **상세 텍스트를 먼저 보여준다.** 음성 영역만 비활성 표시 (루트 README 9절 "TTS 생성 실패 → 상세 텍스트 우선 출력") |
| EC-06 | 음성 파일 다운로드·재생 실패 | 텍스트는 유지하고 재생 버튼만 오류 표시 |
| EC-07 | 응답 지연(첫 요청 시 서버 모델 로딩) | 로딩 표시를 유지하고 사용자 입력을 막는다. 타임아웃은 두지 않는다 |

## How

**서버 계약** — 기존 `docs/specs/api-layer.md`를 그대로 따른다. 앱을 위해 서버를 바꾸지 않는다.

```
POST /api/analyze
요청: multipart/form-data, 필드명 "image" (JPEG)
응답 200:
{
  "status": "candidates_found" | "unsupported_food" | "ocr_empty",
  "ocr_text": string,
  "candidates": [
    { "food_id": int, "name_kr": string, "name_en": string,
      "score": int, "modifiers": object }
  ]
}

status 세 값의 의미 (src/pipeline.py analyze_image):
  candidates_found  후보를 찾음 — candidates에 1개 이상
  unsupported_food  글자는 읽었으나 등록된 50개 음식과 매칭 실패 — candidates 빈 배열
  ocr_empty         글자를 전혀 읽지 못함 — ocr_text·candidates 모두 빈 값
앱은 이 값으로 분기한다. 성공 값이 "ok"가 아님에 주의.

GET /api/foods/{food_id}
응답 200:
{
  "food_id": int,
  "name_kr": string, "name_en": string,
  "details": { "DESCRIPTION": string, "HOW_TO_EAT": string,
               "INGREDIENT": string, "ALLERGY": string,
               "PRONUNCIATION": string, "SPICY": string },
  "narration_text": string,
  "style": "GUIDE" | "CAUTION",
  "tts_status": string,
  "narration_audio_path": string | null,
  "tts_latency_ms": float
}
응답 404: 등록되지 않은 food_id
```

**중요** — `narration_audio_path`는 `/audio/xxx.wav` 형태의 **상대 경로**다. 앱은 여기에 `apiBaseUrl`을 앞에 붙여 완전한 URL로 만들어야 재생할 수 있다.

**서버 주소 관리**

`lib/config.dart`의 `apiBaseUrl` 상수 한 곳에서만 관리한다. 다른 파일은 이 상수를 참조할 뿐 주소 문자열을 직접 갖지 않는다.

| 환경 | 값 | 비고 |
|---|---|---|
| 개발 | `http://<맥 로컬 IP>:8000` | 맥에서 uvicorn 실행 + 폰이 같은 Wi-Fi. IP는 공유기 재할당 시 바뀐다 |
| 시연 | `https://<...>.trycloudflare.com` | cloudflared 터널 |
| 배포 | `https://<...>.hf.space` | 미확정 |

**패키지**

| 패키지 | 용도 |
|---|---|
| `image_picker` | 카메라 촬영 / 사진첩 선택 |
| `http` | API 호출 |
| `audioplayers` | 내레이션 WAV 재생 |

**iOS 필수 설정** — `ios/Runner/Info.plist`

| 키 | 없을 때 |
|---|---|
| `NSCameraUsageDescription` | 촬영 시도 시 앱이 즉시 종료된다 |
| `NSPhotoLibraryUsageDescription` | 사진첩 열 때 종료된다 |
| `NSAppTransportSecurity` → `NSAllowsArbitraryLoads` | `http://` 요청이 전부 차단된다 |

`NSAllowsArbitraryLoads`는 암호화되지 않은 통신을 허용하는 보안 완화다. 개발·시연 단계의 `http` 로컬 서버 때문에 필요하며, 서버가 `https`로 옮겨가면 제거한다.

**제약**

- `src/` 아래 로직은 앱을 위해 수정하지 않는다. 앱이 필요로 하는 변경이 생기면 별도 Spec으로 분리한다.
- 앱은 Supabase에 직접 접근하지 않는다. 모든 데이터는 서버를 거친다(anon key를 앱에 넣지 않기 위함).

## AC (Given-When-Then)

**AC-01 · 촬영에서 후보까지**
- GIVEN: 서버가 실행 중이고 `apiBaseUrl`이 올바르게 설정되어 있다
- WHEN: 사용자가 등록된 음식이 적힌 메뉴판을 촬영한다
- THEN: `POST /api/analyze` 응답의 `candidates`가 화면에 목록으로 표시되고, 각 항목에 `name_en`이 보인다

**AC-02 · 상세와 음성**
- GIVEN: 후보 목록에서 항목 하나가 선택되었다
- WHEN: 앱이 `GET /api/foods/{food_id}`를 호출한다
- THEN: 6개 카테고리 텍스트가 화면에 표시되고, `tts_status`가 `ok`이면 내레이션 음성이 재생된다

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
