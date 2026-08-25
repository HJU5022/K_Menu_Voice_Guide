# Spec — FastAPI Space 배포 (Dockerfile)

## Why

- **페르소나**: 배포를 맡은 정운, 그리고 이 API를 부르는 두 클라이언트 — 웹(static Space의 React, `frontend/`)과 모바일 앱(`mobile/lib/api.dart`).
- **상황**: 배포 구조를 확정했다(2026-08-23) — 계산은 **FastAPI Space(GPU) 한 곳**에 몰고, 웹은 무료 CPU Space에서, 앱은 `config.dart` 주소만 바꿔 같은 API를 부른다. GPU 실측(RTX 3080 Ti)에서 OCR이 92상자 기준 CPU 22.8초 → GPU 0.8초로 확인돼 계산은 GPU가 필수다.
- **문제**:
  1. HF Spaces에 FastAPI 전용 SDK가 없다 — **Docker Space**로 올려야 하는데 저장소에 Dockerfile이 없다.
  2. TTS 워커(`src/tts/worker.py`)는 Windows/맥의 paddle·torch DLL 충돌 때문에 **별도 가상환경의 파이썬**(`_TTS_PYTHON`, 기본값 `.venv-tts/Scripts/python.exe`)으로 뜨게 되어 있다. 리눅스 컨테이너에는 이 충돌이 없지만, 기본값이 Windows 경로라 그대로는 워커가 시작조차 못 한다.
- **측정 지표**: Space에 올린 컨테이너에서 `/api/analyze`와 `/api/foods/{id}`가 GPU로 정상 응답하는지, 아래 AC로 검증한다.

## Goal

- **해결 목표**: 저장소 루트의 `Dockerfile`(+`.dockerignore`) 하나로 `K_Menu_Talk.py`가 HF Docker Space(T4 small)에서 뜨게 한다.
- **성공 기준**:
  1. `src/`와 `K_Menu_Talk.py`를 **한 줄도 수정하지 않는다** — 환경 차이는 전부 Dockerfile의 환경변수로 흡수한다.
  2. 컨테이너 안에서 paddle이 GPU를 잡는다 (`paddle.device.get_device()` → `gpu:0`).
  3. TTS 워커가 서버와 같은 파이썬으로 떠서 음성을 생성한다 (`tts_status: "ok"`).
  4. 비밀값(Supabase 키)이 이미지에 들어가지 않는다 — Space **Secrets**로만 주입한다.
- **Out of Scope**:
  - **웹 Space 배포** — 웹은 빌드 결과물만 올리는 무료 static Space라 이 Dockerfile과 무관하다. 화면 쪽은 `frontend/docs/web-app.md`와 `frontend/space/README.md`가 다룬다.
  - HF Space 생성·하드웨어 선택·Secrets 등록의 **수행 절차 자체** (이 Spec은 무엇이 필요한지만 명시한다).
  - 모바일 `config.dart` 주소 변경, 모델 가중치 사전 캐싱(빌드타임 다운로드) 최적화, CI/CD.

## What

**Happy Path**

1. Space(Docker SDK, T4 small)에 저장소를 푸시하면 Dockerfile로 이미지가 빌드된다.
2. 컨테이너가 뜨고 uvicorn이 7860 포트에서 `K_Menu_Talk:app`을 서빙한다.
3. 첫 부팅 때 모델을 허브에서 내려받는다 — OCR 기본 2종(PaddleX), 파인튜닝 OCR(`k-bite-team/K_Bite_OCR`), TTS(`Qwen/Qwen3-TTS-12Hz-1.7B-Base` + `k-bite-team/k-menu-qwen3-tts-lora`).
4. 웹·앱이 `/api/analyze` → `/api/foods/{id}`를 호출해 결과와 음성 URL(`/audio/...`)을 받는다.

**Edge Cases**

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | Space Secrets에 Supabase 키가 등록 안 됨 | 음식 DB를 읽는 API가 5xx로 실패한다. Dockerfile은 관여하지 않는다 — 필요한 Secrets 목록을 How에 명시하고, Space 생성 시 등록한다 |
| EC-02 | 잠자기에서 깨어나는 중(콜드스타트) | 빌드·모델 로딩이 끝날 때까지 응답하지 못한다. 시연 전에 미리 켜서 요청 한 번으로 웜업한다(운영 절차, 코드 아님) |
| EC-03 | Space 재시작으로 모델 캐시 소실 | 허브에서 다시 내려받는다 — 부팅이 느려질 뿐 실패가 아니다. 영구 스토리지는 쓰지 않는다 |
| EC-04 | TTS LoRA 저장소가 비공개로 전환됨 | 다운로드 401 → TTS만 `not_ready`로 내려앉는다(기존 텍스트 우선 동작). 이 경우 `HF_TOKEN`을 Secrets에 추가한다 |
| EC-05 | 저장소에 LFS 없는 바이너리(jpg·png·wav)가 있으면 Space 푸시가 거절된다 | `pre-receive hook declined` + "Please use xet to store binary files". 배포용으로는 히스토리 없는 스냅샷 커밋을 만들고 `mobile/`·`eval/`을 제외해서 푸시한다 |

## How

- **대상 파일**: 저장소 루트 `Dockerfile`, `.dockerignore`. 그 외 파일은 만들지도 고치지도 않는다.
- **HF Docker Space 규칙**: 컨테이너는 **uid 1000 비루트**로 실행되고, 웹서버는 **7860 포트**를 서빙해야 한다. Space 저장소 README 메타데이터에 `sdk: docker`, `app_port: 7860`을 넣는다(Space 생성 단계).
- **베이스 이미지**: `python:3.11-slim` — 로컬 개발 환경과 같은 3.11. GPU 라이브러리는 `requirements.txt`의 `paddlepaddle-gpu`(cu129)가 pip으로 함께 끌어오므로 CUDA 베이스 이미지가 필요 없다.
- **시스템 패키지**: `libgl1`, `libglib2.0-0`, `libgomp1`(opencv), `libsndfile1`(soundfile), `build-essential`.
- **TTS는 별도 가상환경(`/home/user/venv-tts`)에 둔다.** `ENV TTS_VENV_PYTHON`이 그 파이썬을 가리키면 `src/pipeline.py`(31행)가 그것으로 워커를 띄우므로 코드 수정이 필요 없다. 아래 두 함정이 실측으로 확인됐다(2026-08-24, T4 Space).
  - **한 환경에 합칠 수 없다.** `paddlepaddle-gpu`가 `nvidia-*-cu12` 패키지를 정확한 버전으로 고정하는데(cublas 12.9.0.13 등) 최신 torch도 같은 패키지를 다른 버전으로 고정한다. 함께 설치하면 pip이 충돌을 피해 torch를 계속 낮추다 cu11 시절인 **2.0.1**까지 내려가고, 그 torch는 numpy 2.x와 호환되지 않아 TTS가 로딩 단계에서 죽는다. 워커는 paddle을 임포트하지 않으므로(`src/tts/worker.py`) 환경을 가르면 해결된다 — 맥·Windows의 `.venv-tts`와 같은 구조다.
  - **torch와 torchaudio는 버전을 못 박아야 한다** (2026-08-26 추가). 둘은 같은 버전 번호끼리만 맞물리는데, `qwen-tts`가 `torchaudio`를 끌어오므로 값을 적어두지 않으면 빌드하는 날의 최신을 각각 집어와 짝이 깨진다. 실제로 2026-08-26 빌드가 **torch 2.13.0 + torchaudio 2.11.0**을 설치했다. 같은 어긋남을 Windows에서 겪었을 때는 `qwen_tts` 임포트가 `OSError: [WinError 127]`로 죽어 TTS가 통째로 멈췄다. **캐시가 있으면 증상이 안 보이고 실시간 생성만 조용히 죽는 종류**라 더 위험하다 — 캐시 히트만 확인하고 "TTS 정상"이라고 판단하면 안 된다. 지금 값(`torch==2.6.0`, `torchaudio==2.6.0`)은 Windows GPU에서 음성 생성까지 확인한 조합이다.
  - **C 컴파일러가 있어야 한다.** torch가 GPU 커널 일부를 실행 시점에 Triton으로 즉석 컴파일하는데, slim 이미지에는 컴파일러가 없어 `RuntimeError: Failed to find C compiler`로 워커가 죽는다. 개발 PC(Windows)는 CPU 빌드 torch라 이 경로를 타지 않아 드러나지 않는다.
- **진단 방법**: 워커의 stderr는 컨테이너 안 `logs/tts_worker.log`에만 남아 Space 로그 화면에서 보이지 않는다. 원인을 볼 때는 파이프를 거치지 않고 `TTS_VENV_PYTHON`으로 `src.tts.infer.synthesize`를 직접 실행해 종료 코드와 stderr를 확인하는 편이 빠르다.
- **Space Secrets**(이미지·저장소에 넣지 않는다): `SUPABASE_URL`, `SUPABASE_ANON_KEY`. TTS LoRA 저장소가 비공개면 `HF_TOKEN` 추가(EC-04).
- **`.dockerignore`**: `.env`(비밀값 — 반드시), `.venv*`, `mobile/`, `docs/`, `tests/`, `logs/`, `static/audio`, git 메타 — 빌드 컨텍스트와 이미지에서 제외한다.
- **사전 생성 TTS 캐시(`static/tts_cache`)는 이미지에 넣는다.** 없으면 요청마다 라이브 생성이라 음식 하나에 60초 이상 걸린다(T4 실측 2026-08-24). 캐시가 있으면 0.8초로 끝난다 — `src/pipeline.py`의 `_load_cached_audio`가 그 파일을 먼저 찾기 때문이다. **파일은 두 종류, 모두 100개다**(2026-08-26): 나레이션 `food_{id}_{STYLE}.wav` 50개와 이름만 읽은 `name_{id}.wav` 50개. 저장소에는 `.gitignore`가 `static/`을 막고 있으므로, 배포용 스냅샷에서 `git add -f static/tts_cache`로 포함시키고 `.gitattributes`에 `*.wav filter=lfs …`를 넣어 LFS로 올린다(EC-05).

## AC

**AC-01 · GPU 인식**
- GIVEN: T4 Space에서 컨테이너가 부팅을 마쳤다.
- WHEN: 컨테이너 안에서 `paddle.device.get_device()`를 확인한다.
- THEN: `gpu:0`이다.

**AC-02 · 분석 API 정상 응답**
- GIVEN: Secrets가 등록돼 있고 Space가 깨어 있다.
- WHEN: 메뉴판 사진을 `POST /api/analyze`로 보낸다.
- THEN: 응답 200과 `status: candidates_found`, 후보 목록을 받는다.

**AC-03 · TTS 생성**
- GIVEN: Space가 깨어 있다.
- WHEN: `GET /api/foods/{food_id}`를 호출한다.
- THEN: `tts_status: "ok"`이고 `narration_audio_path`의 `/audio/...` URL에서 음성이 재생된다.

**AC-04 · 이미지에 비밀값 없음**
- GIVEN: Dockerfile로 이미지를 빌드했다.
- WHEN: 이미지 파일시스템에서 `.env`를 찾는다.
- THEN: 존재하지 않는다 (`.dockerignore`가 제외).
