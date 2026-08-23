# Spec — Streamlit 배포 진입점 (app.py)

## Why

- **페르소나**: 배포를 맡은 정운, 그리고 데모 링크로 접속하는 심사위원·외부 사용자.
- **상황**: 처음에는 "한 컨테이너에 한 앱"인 HF Spaces 제약 때문에 `app.py` 하나가 화면과 파이프라인을 **직접 연결**하는 단일 프로세스 구조로 만들었다(이 Spec의 이전 버전). 이후 GPU 실측(2026-08-23, RTX 3080 Ti)에서 OCR이 92상자 기준 **CPU 22.8초 → GPU 0.8초**로 확인돼, 계산은 GPU가 필수라는 것이 숫자로 굳었다.
- **문제**:
  1. 직접 연결 구조를 유지한 채 웹을 배포하면 **Streamlit Space에도 GPU**가 필요하다. 모바일 앱용 FastAPI Space(GPU)와 합쳐 GPU 비용이 두 배가 된다.
  2. 웹(Streamlit)과 앱(Flutter)이 각각 계산을 들고 있으면 같은 파이프라인이 두 곳에 뜬다 — 모델 로딩 메모리도, 콜드스타트도 두 배다.
- **결정(2026-08-23)**: 계산은 **FastAPI Space(GPU, `K_Menu_Talk.py`) 한 곳**에 몰고, `app.py`는 **무료 CPU Space에서 그 API를 HTTP로 호출하는 화면 전용 클라이언트**로 바꾼다. HTTP 계약은 `docs/specs/api-layer.md`에 이미 있는 것을 그대로 쓴다 — 모바일 앱(`mobile/lib/api.dart`)과 같은 계약이다.
- **측정 지표**: 사진 업로드부터 음성 재생까지의 사용자 흐름이 **FastAPI 호출만으로**(로컬 파이프라인 임포트 없이) 끝까지 완주하는지, 아래 AC로 검증한다.

## Goal

- **해결 목표**: `app.py`가 화면(업로드 → 후보 선택 → 결과)만 담당하고, 계산은 전부 `K_Menu_Talk.py`(FastAPI)의 HTTP API로 위임하는 배포 진입점을 만든다.
- **성공 기준**:
  1. `app.py`가 `src/` 아래 코드를 **전혀 임포트하지 않는다** — paddle·torch 없이 뜨므로 무료 CPU Space에서 돌 수 있다.
  2. API 주소는 환경변수 `API_BASE_URL`로 주입한다(기본값 `http://127.0.0.1:8000` — 로컬 개발). 모바일 앱의 `config.dart`와 같은 방식이다.
  3. 화면이 재실행돼도 `/api/foods/{id}`를 다시 부르지 않는다(TTS 재생성 방지 — 기존 성공 기준 유지).
  4. 카테고리 6개의 순서·영어 제목·예외 문구가 `docs/content-style.md` 기준을 지킨다(앱과 같은 문구를 쓴다).
- **Out of Scope**:
  - **디자인·CSS·테마** — 별도 작업이다. 이 Spec은 그 CSS가 붙을 **골격**까지만 다룬다.
  - `K_Menu_Talk.py` **수정** — 계약(`api-layer.md`)은 그대로 쓴다. 서버 쪽은 바꾸지 않는다.
  - HF Space 생성·하드웨어 설정·시크릿 등록, FastAPI Space용 Dockerfile, Flutter 클라이언트(`config.dart` 주소 변경 포함), 다국어.

## What

**Happy Path**

1. 사용자가 업로드 화면에서 메뉴 사진을 촬영(`st.camera_input`)하거나 업로드(`st.file_uploader`)한다.
2. 업로드된 바이트를 `POST {API_BASE_URL}/api/analyze`에 multipart(필드명 `image`)로 보낸다.
3. 응답 JSON을 `session_state["analysis"]`에 담고 후보 선택 화면으로 넘어간다.
4. 사용자가 후보 버튼 중 하나를 누른다.
5. `GET {API_BASE_URL}/api/foods/{food_id}`를 호출해 응답을 `session_state["guide"]`에 담고 결과 화면으로 넘어간다 — 이 한 응답에 상세·나레이션·맵기가 모두 들어 있다(`api-layer.md`의 `FoodDetailResponse`).
6. 결과 화면이 음식명·맵기 불꽃·오디오·카테고리 6개 카드를 보여준다. 오디오는 응답의 상대 경로(`/audio/...`) 앞에 `API_BASE_URL`을 붙인 URL로 재생한다.

**Edge Cases**

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | OCR 결과 없음 (`ocr_empty`) | 재촬영 안내 문구 + "Take a new photo" 버튼. 기존 React `ErrorPanel`의 영어 문구를 그대로 사용 |
| EC-02 | 등록되지 않은 음식 (`unsupported_food`) | 미지원 안내 + "Take a new photo" 버튼. 추측해서 결과를 만들지 않는다 |
| EC-03 | 후보가 1개뿐 | 선택 화면을 건너뛰고 바로 결과 화면으로 넘어간다 (고를 것이 없으므로) |
| EC-04 | TTS 실패 (`tts_status: "not_ready"`) | `narration_audio_path`가 `None` → 오디오 대신 경고 + 내레이션 텍스트를 화면에 출력. 상세 카드는 정상 표시 (README 9절 "TTS 생성 실패 \| 상세 텍스트 우선 출력") |
| EC-05 | 위젯 조작으로 스크립트가 재실행됨 | Streamlit은 상호작용마다 스크립트를 처음부터 다시 실행한다. 결과를 `session_state`에 담아두고 재사용해 TTS를 다시 부르지 않는다 (캐시 미스면 요청당 약 33초) |
| EC-06 | 특정 카테고리 텍스트가 비어 있음 | 해당 카드만 빈 내용으로 표시하고 화면 전체는 계속 그린다 (`details.get(category, "")`) |
| EC-07 | API 서버에 연결할 수 없음 (꺼져 있음·잠자기·네트워크 오류) 또는 5xx 응답 | "서비스에 연결할 수 없다"는 안내 문구와 "Try again" 버튼을 보여준다. 추측으로 결과를 만들지 않는다 |

## How

```
session_state 계약

"step"     : "upload" | "select" | "result"    # 현재 화면
"analysis" : POST /api/analyze 응답 JSON 그대로
             {status, ocr_text, candidates[], unsupported_lines[]}
"guide"    : GET /api/foods/{food_id} 응답 JSON 그대로
             {food_id, name_kr, name_en, spice_level,
              details: {CATEGORY: text, ...},
              narration_text, style,
              narration_audio_path, tts_status, tts_latency_ms}
```

- **대상 파일**: 저장소 루트 `app.py` (HF Spaces Streamlit SDK의 기본 진입점 이름).
- **화면 전용 원칙**: 이 파일은 화면 구성과 상태 전환, HTTP 호출만 둔다. `src/` 아래를 임포트하지 않는다 — 무료 CPU Space에서 뜨려면 paddle·torch가 로드되지 않아야 한다. (`import torch` 최상단 처방도 같이 사라진다 — paddle을 안 쓰므로 DLL 충돌 자체가 없다.)
- **HTTP 클라이언트**: `requests`(이미 `requirements.txt`에 있음)를 쓴다. 계약·필드명은 `api-layer.md`를 따르고 새 필드를 만들지 않는다.
- **오디오**: 응답의 `narration_audio_path`는 상대 경로(`/audio/...`)다. `st.audio()`에 `{API_BASE_URL}{narration_audio_path}` URL을 넘긴다.
- **카테고리 6개의 순서·영어 제목**과 **예외 화면 문구**는 `docs/content-style.md` 기준을 따른다. 새로 짓지 않는다.
- **후보의 `modifiers`** 는 화면에 표시하지 않는다 — 기존 React 화면도 받기만 하고 렌더링하지 않았으므로 동작을 맞춘다.
- **맵기 표시**: `spice_level`(1~5)만큼 불꽃을 채운다(README 3절). `get_food_info()`는 `spice_level`을 돌려주지 않으므로 `cache.get_food()`에서 읽는다.

## AC

**AC-01 · 후보 여러 개 → 선택 화면**
- GIVEN: `POST /api/analyze`가 `candidates_found`와 후보 2개를 반환한다.
- WHEN: 사용자가 업로드 화면에서 사진을 올린다.
- THEN: 후보 2개가 각각 버튼으로 표시되고, 결과 화면으로 자동 이동하지 않는다.

**AC-02 · 후보 1개 → 결과 화면 자동 이동**
- GIVEN: `POST /api/analyze`가 `candidates_found`와 후보 1개를 반환한다.
- WHEN: 사용자가 사진을 올린다.
- THEN: 선택 화면을 건너뛰고 결과 화면이 표시된다.

**AC-03 · OCR 실패 안내**
- GIVEN: `POST /api/analyze`가 `ocr_empty`를 반환한다.
- WHEN: 사용자가 사진을 올린다.
- THEN: 재촬영 안내 문구와 "Take a new photo" 버튼이 표시되고, 후보 목록·결과 화면은 표시되지 않는다.

**AC-04 · TTS 실패 시 텍스트 우선**
- GIVEN: `GET /api/foods/{id}`가 `tts_status: "not_ready"`, `narration_audio_path: null`을 반환한다.
- WHEN: 사용자가 후보를 선택한다.
- THEN: 오디오 플레이어 대신 경고와 내레이션 텍스트가 표시되고, 카테고리 6개 카드는 정상 표시된다.

**AC-05 · 재실행 시 API 재호출 없음**
- GIVEN: 결과 화면이 이미 표시돼 `session_state["guide"]`가 채워져 있다.
- WHEN: 사용자가 화면의 위젯을 조작해 스크립트가 재실행된다.
- THEN: `GET /api/foods/{id}`가 다시 호출되지 않고, 이미 받아둔 오디오와 텍스트가 그대로 표시된다.

**AC-06 · 처음으로 돌아가기**
- GIVEN: 결과 화면이 표시돼 있다.
- WHEN: 사용자가 "Take a new photo"를 누른다.
- THEN: 업로드 화면으로 돌아가고, `session_state`의 `analysis`·`guide`가 비워져 이전 결과가 남지 않는다.

**AC-07 · API 연결 실패 안내**
- GIVEN: `API_BASE_URL`에 응답하는 서버가 없다(연결 거부 또는 시간 초과).
- WHEN: 사용자가 사진을 올리거나 후보를 선택한다.
- THEN: 연결 실패 안내 문구와 "Try again" 버튼이 표시되고, 예외 스택이 화면에 그대로 노출되지 않는다.
