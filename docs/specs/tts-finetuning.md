# Spec — TTS 파인튜닝

> **이 문서의 범위**: 내레이션 → TTS → 파이프라인으로 이어지는 **인터페이스 계약**과 그 계약이
> 바뀐 경위만 다룬다. 학습 차수·평가 수치·표기 방식 결정의 정본은 `eval/TTS_MODULE.md`,
> 서빙 경로(Plan B 캐시·별도 프로세스 실행)의 정본은 `src/tts/README.md`다. 같은 내용을
> 여기에 다시 적지 않고 가리키기만 한다.

## Why

- **페르소나**: 한글 메뉴판을 읽기 어려운 영어권 관광객
- **상황**: 음식 후보를 선택하고 영어 음성 안내를 재생하려는 순간
- **문제**: 화면에 보여줄 문장과 모델에 넘길 문장이 다르다(음식명 표기·발음 안내 문장). 여기에
  spice level에 따라 안내 톤도 갈린다. 이 차이를 DB 조회 결과에서 TTS까지 어긋나지 않게
  전달해야 한다.
- **측정 지표**: `get_narration()`이 화면용·TTS용 문장과 스타일을 함께 반환하고, 정상·예외 경로
  단위 테스트를 통과한다.

## Goal

- **해결 목표**: DB 조회 결과를 화면용과 TTS용으로 갈라 하나의 계약으로 제공하고, TTS가 이를
  검증해 실제 음성을 반환한다.
- **성공 기준**
  - spice level 1~3은 GUIDE, 4~5는 CAUTION과 해당 내레이션 문장을 반환한다.
  - `tts_text`는 음식명이 한글 표기로 치환되고 발음 안내가 음성 전용 문장으로 교체된 문장이다.
  - 유효한 TTS 입력은 `status="ok"`, 실제 WAV 경로, `latency_ms >= 0`을 반환한다.
- **Out of Scope**: OCR 이미지 입력, 상세 카드 6종 조합, UI 렌더링.
  - 이 Step 착수 시점의 Out of Scope(모델 로딩·WAV 생성·캐시·Perso.ai 호출·TTFB 측정)는
    **전부 해제됐다** — 경위는 아래 변경 이력.

## What

### Happy Path

1. `foods`에서 `food_id` 행을 조회한다 (`spice_level`, `name_en`, `name_kr`).
2. `spice_level`이 1~3이면 GUIDE, 4~5면 CAUTION으로 정한다.
3. `food_narration`에서 같은 `food_id`와 style의 `narration_text`를 조회한다.
4. `narration_text`를 그대로 화면용 `text`로 쓴다 — 다른 카테고리를 덧붙이지 않는다.
5. TTS용 문장은 같은 `text`에서 `name_en`을 단어 경계 기준으로 `name_kr`로 치환한 것이다
   → `tts_text`. 즉 둘은 음식명 표기만 다르다.
6. `{text, tts_text, style, name_kr}`을 반환한다.
7. `synthesize(text, style)`는 style에 맞는 instruct를 붙여 모델을 호출하고, 앞뒤 무음을 다듬은
   WAV 경로를 반환한다.
8. `create_tts_response(food_id)`는 사전 생성 캐시를 먼저 조회하고, 없으면 별도 프로세스로 라이브
   합성한 뒤 나레이션 음성과 이름 음성을 하나의 객체로 묶어 반환한다.

### Edge Cases

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | foods에 food_id가 없음 | `ValueError` |
| EC-02 | food_narration에 해당 style 문장이 없음 | `ValueError` |
| EC-03 | spice_level이 정수가 아님 | `ValueError` |
| EC-04 | narration_text가 빈 문자열 | `ValueError` |
| EC-05 | 해당 style의 `narration_text`가 없거나 공백만 있음 | `ValueError` |
| EC-07 | foods.name_kr이 비어 있음 | 치환하지 않고 로마자 원문을 그대로 씀 (예외 아님) |
| EC-08 | DB 호출 실패 | 예외를 숨기지 않고 호출자에게 전달 |
| EC-09 | TTS text가 빈 문자열 | `ValueError` |
| EC-10 | TTS style이 GUIDE/CAUTION이 아님 | `ValueError` |
| EC-11 | TTS 합성 실패(GPU 없음·워커 크래시·타임아웃) | 텍스트 응답은 유지하고 `tts_status="not_ready"` |

## How

**내레이션** — `src/text_gen/narration.py`

- 함수: `get_narration(food_id: int) -> dict[str, str]`
- 반환 키: `text`(화면용), `tts_text`(음성용), `style`, `name_kr`(이름 단독 음성용)
- style 규칙: `spice_level >= 4`이면 CAUTION, 그 외는 GUIDE
- 치환은 `tts_text`에만 적용한다 — 화면용 `text`는 로마자 원문을 유지한다(여행자가 소리 내어
  읽어야 하는 정보다).

**TTS** — `src/tts/infer.py`

- 함수: `synthesize(text: str, style: str) -> dict[str, object]`
- 반환 키: `audio_path`(`str`), `latency_ms`(`float`), `status`(`"ok"`)
- 성공하면 `"ok"`만 반환하고, 실패는 예외로 올린다. `"not_ready"`는 이 함수가 아니라 워커·파이프라인
  쪽 폴백(`src/tts/worker.py`, `src/pipeline.py`)이 붙이는 값이다.
- 받은 텍스트를 그대로 모델에 넘긴다 — 표기 치환을 여기서 또 하면 이중 처리가 된다.
- 상수는 이 모듈에 있다: `TTS_BASE_MODEL_ID`, `TTS_ADAPTER_REPO_ID`, `TTS_SPEAKER_NAME`,
  `LORA_SCALE`. 값의 근거는 모듈 헤더 주석과 `eval/TTS_MODULE.md`.

**파이프라인** — `src/pipeline.py`

- 함수: `create_tts_response(food_id: int) -> dict[str, object]`
- 반환 키: `narration_text`, `style`, `narration_audio_path`, `tts_status`, `tts_latency_ms`,
  `name_audio_path`, `name_tts_status`
- 캐시(`static/tts_cache/food_{id}_{STYLE}.wav`)를 먼저 조회하고, 미보유 조합만 라이브 합성으로
  폴백한다. 라이브 경로와 캐시 생성(`src/tts/pregenerate.py`)이 **같은 `tts_text`** 를 써야 같은
  음성이 나온다.

## AC (Given-When-Then)

**AC-01 · GUIDE 반환**
- GIVEN: spice_level=3 음식과 GUIDE 내레이션이 있다.
- WHEN: `get_narration(food_id)`를 호출한다.
- THEN: `style="GUIDE"`와 GUIDE 문장을 이어붙인 `text`를 반환한다.

**AC-02 · CAUTION 반환**
- GIVEN: spice_level=4 음식과 CAUTION 내레이션이 있다.
- WHEN: `get_narration(food_id)`를 호출한다.
- THEN: `style="CAUTION"`과 CAUTION 문장을 이어붙인 `text`를 반환한다.

**AC-03 · 음식 없음**
- GIVEN: foods 조회 결과가 비어 있다.
- WHEN: `get_narration(food_id)`를 호출한다.
- THEN: `ValueError`가 발생한다.

**AC-04 · 화면용/음성용 분리**
- GIVEN: `name_en`/`name_kr`이 있는 음식이 있다.
- WHEN: `get_narration(food_id)`를 호출한다.
- THEN: `tts_text`는 음식명이 한글 표기이고, `text`는 로마자 원문을 유지한다. 음식명을 되돌리면
  두 문자열이 정확히 같다. 치환은 단어 경계 기준이라 긴 이름 안쪽을 건드리지
  않는다.

**AC-05 · 폴백**
- GIVEN: PRONUNCIATION_TTS 행이 없거나 `name_kr`이 비어 있다.
- WHEN: `get_narration(food_id)`를 호출한다.
- THEN: 예외 없이 화면용 문장 또는 로마자 원문으로 폴백한다.

**AC-06 · TTS 정상 반환**
- GIVEN: 비어 있지 않은 text와 GUIDE 또는 CAUTION style이 있다.
- WHEN: `synthesize(text, style)`를 호출한다.
- THEN: `status="ok"`, 실제 WAV 경로, 0 이상 `latency_ms`를 반환하고, style에 맞는 instruct가
  모델에 전달된다.

**AC-07 · TTS 입력 검증**
- GIVEN: 빈 text 또는 지원하지 않는 style이 있다.
- WHEN: `synthesize(text, style)`를 호출한다.
- THEN: `ValueError`가 발생한다.

**AC-08 · 파이프라인 연결**
- GIVEN: 음식 ID에 대한 내레이션과 사전 생성 캐시가 있다.
- WHEN: `create_tts_response(food_id)`를 호출한다.
- THEN: 라이브 합성 없이 캐시 음성을 쓰고, 문장·style·음성 경로·상태·지연 시간을 하나의 객체로
  반환한다.

**AC-09 · 합성 실패**
- GIVEN: 캐시가 없고 라이브 합성도 실패한다.
- WHEN: `create_tts_response(food_id)`를 호출한다.
- THEN: `narration_text`/`style`은 그대로 반환하고 `tts_status="not_ready"`만 남긴다.

> 대응 테스트: `tests/test_narration.py`, `tests/test_tts_infer.py`, `tests/test_pipeline.py`.

---

## 구현 변경 이력

### 2026-08-18 — "Out of Scope"였던 실제 모델 연결을 진행함

착수 시점 Goal에는 "Out of Scope: XTTS/F5 모델 로딩, WAV 생성, 캐시, Perso.ai 호출, TTFB 측정"이라고
적혀 있었고, `synthesize()`는 `audio_path=None` · `status="not_ready"`만 돌려주는 스켈레톤이었다.
팀원(박민영님)이 이미 Qwen3-TTS 1.7B Base + LoRA 어댑터로 파인튜닝을 완료해둔 상태라, 그걸 기반으로
`infer.py`에 실제 모델 로딩·WAV 생성을 연결했다.

- 모델: base `Qwen/Qwen3-TTS-12Hz-1.7B-Base` + LoRA 어댑터 `k-bite-team/k-menu-qwen3-tts-lora` (2026-10-20 개인 계정 `hajeongun/k-menu-qwen3-tts-lora`로 그대로 복사)
- `synthesize()`의 반환 **키**(`audio_path`, `latency_ms`, `status`)는 그대로 두고 **값**만 바뀌었다
  — 정상 동작 시 `status`는 `"ok"`, `audio_path`는 실제 WAV 경로다.
- 배포 체크포인트와 학습 차수별 하이퍼파라미터는 이후에도 여러 번 바뀌었다. 현재 값의 정본은
  `src/tts/infer.py` 헤더 주석과 `eval/TTS_MODULE.md` 3절이다 — 이 문서에 수치를 복사해두지 않는다.

### 2026-08-19 — 1차 구현은 추측이었고 틀렸음, 실제 학습 코드로 전면 재작성

처음엔 `finetuning/infer_lora_custom_voice.py`(커뮤니티 레포가 패치로 추가하는 파일)를 공개
저장소에서 못 찾아서, 공식 `qwen_tts` 소스 코드만 읽고 추측으로 구현했다(`generate_voice_clone` +
`VoiceClonePromptItem` 방식). 이후 박민영님이 실제 학습에 쓴 노트북을 받아 그 안의 실행 결과(패치
파일 `patches/0001-qwen3-tts-lora.patch`)에서 진짜 코드를 확인한 결과 **핵심 부분이 추측과 달랐다**:

- ~~`generate_voice_clone` + 참조 음성 임베딩 직접 주입~~ → **`generate_custom_voice` + "이름 있는
  스피커 등록" 방식이 맞았다.** 학습된 목소리를 `config.json`의 `talker_config.spk_id`에 이름→ID로
  등록해두고, `speaker_embedding.safetensors`의 `target_speaker_embedding` 텐서를 그 ID 위치의
  `core_model.talker.model.codec_embedding.weight`에 직접 덮어쓴다.
- LoRA는 `PeftModel`로 감싼 뒤 기본적으로 `merge_and_unload()`로 베이스에 합쳐진다(처음엔 안 합치고
  감싸기만 했다).
- LoRA scale은 `peft.tuners.lora.LoraLayer.set_scale()`로 적용한다(처음엔 `.scaling` 딕셔너리를 직접
  건드렸다 — 효과는 비슷하지만 정식 API가 따로 있었다).
- `infer.py`를 실제 코드 그대로 옮겨 전면 재작성했다. `_resolve_core_model` /
  `_apply_speaker_config` / `_apply_speaker_embedding` / `_set_lora_scale`이 패치 파일의 동명 함수를
  그대로 옮긴 것이다.

**검증 상태**: 작성 시점엔 로컬에 GPU가 없어 실행 확인을 못 했고 단위 테스트는 모델 호출을 mock으로
대체한 것뿐이었다. 2026-08-20에 실제 GPU로 처음 돌려 정상 생성을 확인했고, 그때 발화 시작부 무음·문장
중간 끊김이 드러나 `_trim_silence()` 후처리를 넣었다(경위: `src/tts/infer.py` 헤더).

### 2026-08-19 — 보안: 학습 노트북의 HF 토큰

전달받은 학습 노트북에 Hugging Face 토큰이 평문으로 하드코딩된 셀이 있었다. **토큰 폐기(rotate)가
필요하다** — 이미 로컬 파일에 노출된 상태였다.

현재 상태(2026-08-26 확인): 저장소의 `eval/qwen3_tts_lora_final.ipynb`는 토큰을 `HF_TOKEN` 참조로
바꾼 뒤 커밋된 것이고, 저장소 전체에 `hf_` 평문 패턴은 남아 있지 않다. 노트북을 새로 받거나 갱신할
때는 커밋 전에 토큰 셀을 반드시 확인한다.

### 2026-08-21 — TTFB 실측 및 Plan B 전환

범위 밖이던 TTFB 측정과 사전 생성 캐시를 실제로 진행했다.

- **TTFB 목표 확정**: 5~7초 (팀 합의, D5 체크포인트)
- **라이브 생성 실측** (원격 RTX 3080 Ti, 3회): 콜드(모델 로딩 포함) 61.3초 / 워밍업 후(상주 워커,
  PR #45) 약 33초 — 목표 대비 구조적 미달
- **판정**: 기획서 위험 대응("TTS 응답 지연이 목표치 초과 → 초과 시 사전 생성 캐싱으로 전환")에 따라
  **Plan B 전환 결정**
- **구현**: `src/tts/pregenerate.py`(배치 생성 + RTF 로그) + `src/pipeline.py` 캐시 조회. 상세 수치와
  판단 근거는 `eval/model_comparison.md` 3절, 서빙 구조는 `src/tts/README.md`.

### 2026-08-25 — 화면용/음성용 텍스트 분리와 발음 안내 문장 추가

음식명 치환을 넣으면 TTS 문장이 같은 이름을 연달아 두 번 읽는 문제가 생겼다 — `food_details`의
PRONUNCIATION은 화면에서 로마자 발음 표기를 알려주는 문장이라, 음식명이 치환되면 거의 같은 소리를
반복하게 된다(50개 전부 해당).

- **계약 변경**: `get_narration()`이 `tts_text`를 추가로 돌려준다. `text`는 화면 표시용으로 원본
  로마자 표기를 유지하고, `tts_text`만 치환한다.
- **치환 위치**: `src/text_gen/narration.py`. `get_narration()`이 style을 정하려고 이미 `foods` 행을
  조회하므로 이름 쌍이 손에 있다. 반면 `infer.py`는 `food_id`를 받지 않고(`worker.py`가
  `{text, style}`만 넘긴다), paddle/torch 충돌을 피하려 격리된 별도 프로세스라 DB 접근을 붙이면 격리
  이유가 무너진다.
- **음성 전용 발음 문장**: `food_details`에 `PRONUNCIATION_TTS` 카테고리를 추가했다. 테이블 구조
  (`food_id`/`category`/`detail_text`)를 그대로 쓰므로 컬럼 추가 없이 행 50개만 넣는다. 문장은 이름을
  한 번만 말하는 형태(`Say it like this: Bibimbap.`)이고, 뜻 설명이 있던 17개는 그 절만 살려 뒤에
  붙였다. 행이 없으면 화면용으로 폴백하므로 코드를 먼저 배포하고 DB 행을 나중에 넣어도 안내가 끊기지
  않는다.
- **DB 적용**: 50행은 2026-08-25에 Supabase SQL Editor로 이미 넣었다. `food_details_category_check`
  제약이 카테고리 6종만 허용하고 있어 제약을 다시 만들어 허용 값에 추가하는 작업이 선행됐다. 넣는
  SQL은 저장소에 두지 않는다 — 일회성 데이터 주입이고 현재 값은 DB가 정본이다.
- **같이 삭제한 것**: `src/tts/infer.py`의 표기 치환 코드(커밋 `d862e11`). 이제 `infer.py`는 받은
  텍스트를 그대로 넘긴다.

### 2026-08-25 (최종) — TTS가 읽는 음식명을 한글 표기로 확정

표기 방식은 하루 사이에 영문 리스펠링(`Tteokbokki` → `Duck-bok-kee`) → 한글 → 리스펠링을 오간 끝에
**한글 표기**(`Tteokbokki` → `떡볶이`)로 정해졌다. 위 항목에서 만든 구조(치환은 `narration.py`가 하고
값은 DB에서 온다)는 그대로 두고, **바뀐 것은 어떤 표기로 바꾸느냐 하나**다.

- **왜**: 리스펠링은 된소리(ㄸ, ㅃ, ㄲ, ㅆ, ㅉ)에 대응하는 알파벳 신호가 없어 근사치로 타협해야 했고,
  리스펠링한 21개뿐 아니라 원본 표기가 적절하다고 판정했던 29개까지 발음이 부정확했다. 철자를 바꿔도
  결과가 같다면 원인은 철자가 아니라 **모델이 그 이름을 영어 음운으로 읽는다는 것**이다. 한글로 적으면
  읽는 음운 체계 자체가 한국어로 바뀐다. 시도 이력과 폐기 근거(UTMOS 하락 포함)의 정본은
  `eval/TTS_MODULE.md` 4절이다.
- **DB 작업 없음**: 값은 이미 있는 `foods.name_kr`이고 50행 전부 채워져 있으며 `src/db/cache.py`가
  예전부터 select하던 컬럼이다.
- **취소된 선행 조건**: 리스펠링 시절 계획했던 `foods.name_respell` 컬럼 추가 SQL은 **실행하지 않는다.**
  2026-08-25 확인 기준 DB에 그 컬럼은 없고(`column foods.name_respell does not exist`, 42703),
  `cache.py`의 select에서도 뺐다. 되돌리기용 `drop column if exists`는 `src/db/README.md`에 있다.
- **`PRONUNCIATION_TTS`는 그대로 유효**: 이름을 한 번만 말하는 형태(`Say it like this: 떡볶이.`)라
  표기가 바뀌어도 전제가 유지된다.
- **함께 바뀐 값**: `LORA_SCALE` 0.3 → 0.15 (GUIDE/CAUTION 톤 구분 복구). 표기 방식과는 독립적인
  결정이라 한글 전환 후에도 0.15를 유지한다. 배경은 `src/tts/infer.py` 헤더 주석.

## 남은 작업

- **한글 표기 청취 검증 (50개)** — `eval/TTS_MODULE.md` 4-1절은 "영어 문장 중간에 한글 **병기**"를
  실패한 접근으로 기록해뒀다(`"...called 떡볶이 (tteokbokki)."` 형태). 현행 방식은 로마자를 병기하지
  않고 이름 자체를 한글로 대체한다는 점이 다르지만, 그 기록을 뒤집으려면 실제로 들어봐야 한다. 배포
  체크포인트가 리스펠링된 영문 라벨로 학습됐다는 점도 같이 본다 — 한글 읽기는 어댑터가 아니라 베이스
  모델의 한국어 능력에 기댄다.
- **`LORA_SCALE` 0.15 청취 확인** — 톤 구분이 실제로 복구됐는지, 음색·발화 안정성이 유지되는지.
- ~~**캐시 전량 재생성**~~ — 2026-08-27 해결. `create_tts_response()`가 캐시를 먼저 조회하므로 낡은
  wav를 두면 코드를 바꿔도 사용자에게는 아무것도 바뀌지 않는데, 그 낡은 파일을 교체했다. 다시
  생성(`--force`)하는 대신 **배포 Space에 이미 올라가 있던 한글 캐시를 받아 덮어썼다** —
  `HJU5022/K_Menu`(커밋 `d91f637` 배포, 2026-08-26 06:27)의 `static/tts_cache` 100개를
  `hf download HJU5022/K_Menu --repo-type space --include "static/tts_cache/*"`로 받아 sha256
  100/100 일치 확인. 표본 3개(`food_1`·`food_2`·`food_23`)를 Whisper large-v3로 전사해 이름을 각각
  "비빔밥"·"불고기"·"낙지볶음"으로 읽는 것까지 확인했다 — 다만 이건 기계 전사이고, 사람 청취 검증은
  위 항목이 정본이다.

> 평가·재현성 쪽 남은 항목(현행 설정 기준 UTMOS 재측정, MOS 정식 평가, 9차 학습 노트북 확보)은
> `eval/TTS_MODULE.md` 7절이 정본이다.
