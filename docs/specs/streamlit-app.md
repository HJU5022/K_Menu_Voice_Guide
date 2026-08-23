# Spec — Streamlit 배포 진입점 (app.py)

## Why

- **페르소나**: 배포를 맡은 정운, 그리고 데모 링크로 접속하는 심사위원·외부 사용자.
- **상황**: 지금은 원격 데스크톱(RTX 3080 Ti)에서 백엔드(FastAPI `:8000`)와 프론트(Vite `:5173`) **두 프로세스**를 띄우고 cloudflared 임시 튜널로 링크를 만든다. 튜널 주소는 켤 때마다 바뀌고, PC를 끄면 서비스가 죽는다.
- **문제**:
  1. Hugging Face Spaces는 **한 컨테이너에 한 앱**이 기본이라, "FastAPI + 별도 React 정적 호스팅 + 빌드타임 `VITE_API_BASE_URL` 주입" 구조를 그대로 옮길 수 없다.
  2. 배포 플랫폼 조사 결과(2026-08-21) 선택지가 좁혀졌다 — **ZeroGPU는 PyTorch 전용 메커니즘이라 PaddleOCR이 GPU를 쓸 수 없고**, Streamlit Community Cloud는 RAM 약 1GB라 `paddlepaddle`+PaddleOCR이 들어가지 않는다. OCR·TTS를 모두 GPU로 돌리려면 **HF Spaces 전용 GPU(T4 small)** 가 필요하고, 팀은 SDK로 Streamlit을 택했다.
  3. 두 프로세스 구조 때문에 CORS 설정, 프론트 `.env` 위치 함정, 튜널 주소 재빌드 등 배포 실수가 반복돼 왔다.
- **측정 지표**: 사진 업로드부터 음성 재생까지의 사용자 흐름이 **단일 프로세스에서** 끝까지 완주하는지, 아래 AC로 검증한다.

## Goal

- **해결 목표**: `app.py` 하나가 화면(업로드 → 후보 선택 → 결과)과 파이프라인 호출을 모두 담당해, HTTP 계약 없이 동작하는 배포 진입점을 만든다.
- **성공 기준**:
  1. `streamlit run app.py` 하나로 서비스 전체가 뜬다 (백엔드·프론트 분리 실행 불필요).
  2. `src/` 아래 코드(`pipeline`·`text_gen`·`db`·`ocr`·`tts`)를 **한 줄도 수정하지 않고** 재사용한다.
  3. 화면이 재실행돼도 TTS가 다시 생성되지 않는다.
  4. 카테고리 6개의 순서·영어 제목·예외 문구가 `docs/content-style.md` 기준을 지킨다(앱과 같은 문구를 쓴다).
- **Out of Scope**:
  - **디자인·CSS·테마** — 별도 작업이다. 이 Spec은 그 CSS가 붙을 **골격**까지만 다룬다.
  - `K_Menu_Talk.py` **삭제** — 모바일 앱이 쓰는 API 진입점이라 남긴다. (React 웹앱 `frontend/`는 2026-08-23에 제거했다 — 웹 화면은 이 Streamlit 하나다.)
  - **배포 전 이식성 수정 3건**(별도 작업): ① `.gitignore`가 `static/`을 통째로 제외해 사전 생성 TTS 캐시가 저장소에 없음 ② `src/pipeline.py`의 `_TTS_PYTHON` 기본값이 Windows 전용 경로 ③ `requirements.txt`에 `paddlepaddle` 미기재·버전 핀 없음.
  - HF Space 생성·하드웨어 설정·시크릿 등록, Flutter 클라이언트, 다국어.

## What

**Happy Path**

1. 사용자가 업로드 화면에서 메뉴 사진을 촬영(`st.camera_input`)하거나 업로드(`st.file_uploader`)한다.
2. 업로드된 바이트를 임시 파일로 저장하고 `analyze_image(path)`를 호출한다.
3. 결과를 `session_state["analysis"]`에 담고 후보 선택 화면으로 넘어간다.
4. 사용자가 후보 버튼 중 하나를 누른다.
5. `create_tts_response(food_id)` + `get_details(food_id)` + `get_food_info(food_id)`를 호출해 `session_state["guide"]`에 담고 결과 화면으로 넘어간다.
6. 결과 화면이 음식명·맵기 불꽃·오디오·카테고리 6개 카드를 보여준다.

**Edge Cases**

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | OCR 결과 없음 (`ocr_empty`) | 재촬영 안내 문구 + "Take a new photo" 버튼. 기존 React `ErrorPanel`의 영어 문구를 그대로 사용 |
| EC-02 | 등록되지 않은 음식 (`unsupported_food`) | 미지원 안내 + "Take a new photo" 버튼. 추측해서 결과를 만들지 않는다 |
| EC-03 | 후보가 1개뿐 | 선택 화면을 건너뛰고 바로 결과 화면으로 넘어간다 (고를 것이 없으므로) |
| EC-04 | TTS 실패 (`tts_status: "not_ready"`) | `narration_audio_path`가 `None` → 오디오 대신 경고 + 내레이션 텍스트를 화면에 출력. 상세 카드는 정상 표시 (README 9절 "TTS 생성 실패 \| 상세 텍스트 우선 출력") |
| EC-05 | 위젯 조작으로 스크립트가 재실행됨 | Streamlit은 상호작용마다 스크립트를 처음부터 다시 실행한다. 결과를 `session_state`에 담아두고 재사용해 TTS를 다시 부르지 않는다 (캐시 미스면 요청당 약 33초) |
| EC-06 | 특정 카테고리 텍스트가 비어 있음 | 해당 카드만 빈 내용으로 표시하고 화면 전체는 계속 그린다 (`details.get(category, "")`). 음식의 상세정보가 **전혀** 없으면 `get_details()`가 `ValueError`를 던진다 — 기존 동작 그대로 |

## How

```
session_state 계약

"step"     : "upload" | "select" | "result"    # 현재 화면
"analysis" : analyze_image()의 반환값 그대로
             {status, ocr_text, candidates[]}
"guide"    : {food_id, name_kr, name_en,       # get_food_info()
              spice_level,                     # cache.get_food()
              details: {CATEGORY: text, ...},  # get_details()
              narration_text, style,           # create_tts_response()
              narration_audio_path, tts_status, tts_latency_ms}
```

- **대상 파일**: 저장소 루트 `app.py` (HF Spaces Streamlit SDK의 기본 진입점 이름).
- **`src/` 무수정 원칙**: 이 파일은 화면 구성과 상태 전환만 둔다. OCR·텍스트·TTS 로직은 `src/` 아래에 그대로 둔다 — `K_Menu_Talk.py`가 요청/응답 변환만 뒀던 것과 같은 원칙.
- **`import torch`를 최상단에** 둔다. `src.pipeline`이 쓰는 `paddleocr`을 import하면 내부적으로 `paddlex → modelscope` 체인이 torch를 끌어오는데, 그 시점에 paddle이 로드해둔 네이티브 DLL과 얽혀 torch의 `shm.dll` 로딩이 깨진다(Windows, `OSError: [WinError 127]`). `K_Menu_Talk.py`와 같은 이유·같은 처방.
- **오디오**: `st.audio()`가 로컬 파일 경로를 직접 받으므로, `K_Menu_Talk.py`의 `_publish_audio()`(임시 wav를 `static/audio`로 옮기고 URL로 노출)가 필요 없다.
- **카테고리 6개의 순서·영어 제목**과 **예외 화면 문구**는 `docs/content-style.md` 기준을 따른다. 새로 짓지 않는다.
- **후보의 `modifiers`** 는 화면에 표시하지 않는다 — 기존 React 화면도 받기만 하고 렌더링하지 않았으므로 동작을 맞춘다.
- **맵기 표시**: `spice_level`(1~5)만큼 불꽃을 채운다(README 3절). `get_food_info()`는 `spice_level`을 돌려주지 않으므로 `cache.get_food()`에서 읽는다.

## AC

**AC-01 · 후보 여러 개 → 선택 화면**
- GIVEN: `analyze_image()`가 `candidates_found`와 후보 2개를 반환한다.
- WHEN: 사용자가 업로드 화면에서 사진을 올린다.
- THEN: 후보 2개가 각각 버튼으로 표시되고, 결과 화면으로 자동 이동하지 않는다.

**AC-02 · 후보 1개 → 결과 화면 자동 이동**
- GIVEN: `analyze_image()`가 `candidates_found`와 후보 1개를 반환한다.
- WHEN: 사용자가 사진을 올린다.
- THEN: 선택 화면을 건너뛰고 결과 화면이 표시된다.

**AC-03 · OCR 실패 안내**
- GIVEN: `analyze_image()`가 `ocr_empty`를 반환한다.
- WHEN: 사용자가 사진을 올린다.
- THEN: 재촬영 안내 문구와 "Take a new photo" 버튼이 표시되고, 후보 목록·결과 화면은 표시되지 않는다.

**AC-04 · TTS 실패 시 텍스트 우선**
- GIVEN: `create_tts_response()`가 `tts_status: "not_ready"`, `narration_audio_path: None`을 반환한다.
- WHEN: 사용자가 후보를 선택한다.
- THEN: 오디오 플레이어 대신 경고와 내레이션 텍스트가 표시되고, 카테고리 6개 카드는 정상 표시된다.

**AC-05 · 재실행 시 TTS 재호출 없음**
- GIVEN: 결과 화면이 이미 표시돼 `session_state["guide"]`가 채워져 있다.
- WHEN: 사용자가 화면의 위젯을 조작해 스크립트가 재실행된다.
- THEN: `create_tts_response()`가 다시 호출되지 않고, 이미 만들어진 오디오와 텍스트가 그대로 표시된다.

**AC-06 · 처음으로 돌아가기**
- GIVEN: 결과 화면이 표시돼 있다.
- WHEN: 사용자가 "Take a new photo"를 누른다.
- THEN: 업로드 화면으로 돌아가고, `session_state`의 `analysis`·`guide`가 비워져 이전 결과가 남지 않는다.
