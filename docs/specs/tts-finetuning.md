# Why

- **페르소나**: 한글 메뉴판을 읽기 어려운 영어권 관광객
- **상황**: 음식 후보를 선택하고 영어 음성 안내를 재생하려는 순간
- **문제**: 최종 TTS 모델이 아직 정해지지 않았어도 DB의 문장과 GUIDE/CAUTION 조건을 다음 TTS 단계에 안정적으로 전달해야 한다.
- **측정 지표**: `get_narration()`이 문장과 스타일을 모두 반환하고, 정상·예외 경로 단위 테스트를 통과한다.

# Goal

- **해결 목표**: DB 조회 결과를 TTS가 바로 사용할 수 있는 `{text, style}` 계약으로 제공하고, TTS 스켈레톤이 이를 검증해 표준 결과를 반환한다.
- **성공 기준**: spice level 1~3은 GUIDE, 4~5는 CAUTION과 해당 내레이션 문장을 반환하며, 유효한 TTS 입력은 `audio_path=None`, `status="not_ready"`, `latency_ms>=0`을 반환한다.
- **Out of Scope**: XTTS/F5 모델 로딩, WAV 생성, 캐시, Perso.ai 호출, TTFB 측정.

# What

## Happy Path

1. `foods`에서 `food_id`의 `spice_level`을 조회한다.
2. 1~3은 GUIDE, 4~5는 CAUTION으로 결정한다.
3. `food_narration`에서 같은 `food_id`와 style의 `narration_text`를 조회한다.
4. `{ "text": narration_text, "tts_text": <음식명을 한글 표기로 바꾼 문장>, "style": style }`을 반환한다.
5. `synthesize(text, style)`는 실제 모델 없이 표준 TTS 결과 객체를 반환한다.
6. `create_tts_response(food_id)`는 내레이션 결과와 TTS 결과를 UI용 객체 하나로 묶어 반환한다.

## Edge Cases

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | foods에 food_id가 없음 | `ValueError` |
| EC-02 | food_narration에 해당 style 문장이 없음 | `ValueError` |
| EC-03 | spice_level이 숫자가 아님 | `ValueError` |
| EC-04 | narration_text가 빈 문자열 | `ValueError` |
| EC-05 | DB 호출 실패 | 예외를 숨기지 않고 호출자에게 전달 |
| EC-06 | TTS text가 빈 문자열 | `ValueError` |
| EC-07 | TTS style이 GUIDE/CAUTION이 아님 | `ValueError` |

# How

- 대상 파일: `src/text_gen/narration.py`
- 함수: `get_narration(food_id: int) -> dict[str, str]`
- 반환 키: `text`, `tts_text`, `style`
- style 규칙: `spice_level >= 4`이면 CAUTION, 그 외는 GUIDE
- TTS 대상 파일: `src/tts/infer.py`
- TTS 함수: `synthesize(text: str, style: str) -> dict[str, object]`
- TTS 반환 키: `audio_path` (`str | None`), `latency_ms` (`float`), `status` (`"not_ready"`)
- 실제 모델 연결은 다음 단계이며, 이 단계에서 audio_path는 항상 `None`이다.
- 파이프라인 대상 파일: `src/pipeline.py`
- 파이프라인 함수: `create_tts_response(food_id: int) -> dict[str, object]`
- 파이프라인 반환 키: `narration_text`, `style`, `narration_audio_path`, `tts_status`, `tts_latency_ms`
- OCR 이미지 입력, 상세 카드 6종 조합, UI 렌더링은 이 Step의 범위 밖이다.

# AC

**AC-01 · GUIDE 반환**
- GIVEN: spice_level=3 음식과 GUIDE 내레이션이 있다.
- WHEN: `get_narration(food_id)`를 호출한다.
- THEN: `{text: <GUIDE 문장>, style: "GUIDE"}`를 반환한다.

**AC-02 · CAUTION 반환**
- GIVEN: spice_level=4 음식과 CAUTION 내레이션이 있다.
- WHEN: `get_narration(food_id)`를 호출한다.
- THEN: `{text: <CAUTION 문장>, style: "CAUTION"}`를 반환한다.

**AC-03 · 음식 없음**
- GIVEN: foods 조회 결과가 비어 있다.
- WHEN: `get_narration(food_id)`를 호출한다.
- THEN: `ValueError`가 발생한다.

**AC-04 · TTS 스켈레톤 정상 반환**
- GIVEN: 비어 있지 않은 text와 GUIDE 또는 CAUTION style이 있다.
- WHEN: `synthesize(text, style)`를 호출한다.
- THEN: `audio_path=None`, `status="not_ready"`, 0 이상 `latency_ms`를 반환한다.

**AC-05 · TTS 입력 검증**
- GIVEN: 빈 text 또는 지원하지 않는 style이 있다.
- WHEN: `synthesize(text, style)`를 호출한다.
- THEN: `ValueError`가 발생한다.

**AC-06 · 파이프라인 연결**
- GIVEN: 음식 ID에 대한 `{text, style}`과 TTS 결과가 있다.
- WHEN: `create_tts_response(food_id)`를 호출한다.
- THEN: 내레이션 문장·style·audio path·TTS 상태·지연 시간을 하나의 객체로 반환한다.

## 구현 변경 이력 (2026-08-18)

### "Out of Scope"였던 실제 모델 연결을 진행함

이 문서 원래 Goal에는 "Out of Scope: XTTS/F5 모델 로딩, WAV 생성, 캐시, Perso.ai 호출, TTFB 측정"이라고 돼있었으나, 팀원(박민영님)이 이미 Qwen3-TTS 1.7B Base + LoRA 어댑터로 실제 파인튜닝을 완료해둔 상태라 그걸 기반으로 `infer.py`에 실제 모델 로딩·WAV 생성을 연결함.

- 모델: base `Qwen/Qwen3-TTS-12Hz-1.7B-Base` + LoRA 어댑터 `k-bite-team/k-menu-qwen3-tts-lora` (40 epoch, lr=2e-6)
- `synthesize()`의 반환 계약(`audio_path`, `latency_ms`, `status`)은 그대로 유지 — 다만 정상 동작 시 `status`는 `"not_ready"`가 아니라 `"ok"`, `audio_path`는 실제 임시 WAV 파일 경로가 됨
- Perso.ai 호출, TTFB 측정, 사전생성 캐시(Plan B)는 여전히 범위 밖

### 구현 변경 이력 (2026-08-21) — TTFB 실측 및 Plan B 전환

위에서 범위 밖이었던 TTFB 측정과 사전생성 캐시가 실제로 진행됨:

- **TTFB 목표 확정**: 5~7초 (팀 합의, D5 체크포인트)
- **라이브 생성 실측** (원격 RTX 3080 Ti, 3회): 콜드(모델 로딩 포함) 61.3초 / 워밍업 후(상주 워커, PR #45) 약 33초 — 목표 대비 구조적 미달
- **판정**: 기획서 위험 대응("TTS 응답 지연이 목표치 초과 → 초과 시 사전 생성 캐싱으로 전환")에 따라 **Plan B 전환 결정**
- **구현**: `src/tts/pregenerate.py`(배치 생성 + RTF 로그) + `src/pipeline.py` 캐시 조회(`static/tts_cache/food_{id}_{STYLE}.wav`, 캐시 히트 시 1초 미만, 미보유 조합은 라이브 폴백). 상세는 `src/tts/README.md` 참고

### 1차 구현은 추측이었고 틀렸음 — 실제 학습 노트북 확보 후 전면 재작성함

처음엔 `finetuning/infer_lora_custom_voice.py`(커뮤니티 레포가 패치로 추가하는 파일)를 공개 저장소에서 못 찾아서, 공식 `qwen_tts` 소스 코드만 읽고 추측으로 구현했음(`generate_voice_clone` + `VoiceClonePromptItem` 방식). 이후 박민영님이 실제 학습에 쓴 노트북(`qwen3_tts_lora_finetune.ipynb`)을 받아 그 안의 실행 결과(패치 파일 `patches/0001-qwen3-tts-lora.patch`)에서 진짜 코드를 확인한 결과, **핵심 부분이 추측과 달랐음**:

- ~~`generate_voice_clone` + 참조 음성 임베딩 직접 주입~~ → **`generate_custom_voice` + "이름 있는 스피커 등록" 방식이 맞았음**. 학습된 목소리를 `config.json`의 `talker_config.spk_id`에 이름→ID로 등록해두고, `speaker_embedding.safetensors`의 `target_speaker_embedding` 텐서를 그 ID 위치의 `core_model.talker.model.codec_embedding.weight`에 직접 덮어쓰는 방식.
- LoRA는 `PeftModel`로 감싼 뒤 기본적으로 `merge_and_unload()`로 베이스에 합쳐짐 (처음엔 안 합치고 그냥 감싸기만 했었음).
- LoRA scale은 `peft.tuners.lora.LoraLayer.set_scale()`로 적용 (처음엔 `.scaling` 딕셔너리를 직접 건드렸었음 — 결과적으로 비슷한 효과지만 정식 API가 따로 있었음).
- `infer.py`를 이 실제 코드를 그대로 옮겨서 전면 재작성함 (`src/tts/infer.py`의 `_resolve_core_model`/`_apply_speaker_config`/`_apply_speaker_embedding`/`_set_lora_scale`이 패치 파일의 동명 함수를 그대로 옮긴 것).

### 검증 상태 — 아직 실행 확인 못 함

**로컬에 GPU가 없어서 이 구현을 실제로 돌려서 확인하지 못했다.** 단위 테스트(`tests/test_tts_infer.py`)는 모델 호출 부분을 가짜(mock)로 대체해서 입력 검증 로직·반환 형식만 확인한 것이고, 진짜 모델이 진짜 음성을 만들어내는지는 검증되지 않았다. 다만 로직 자체는 실제 학습에 쓰인 코드를 그대로 옮긴 것이라 이전보다 신뢰도가 훨씬 높음.

- **확인 필요한 값**: `speaker_name="speaker"`(노트북에서 커스텀 이름을 준 적이 없어 기본값이 계속 쓰였음), `LORA_SCALE`(노트북은 0.2/0.3/0.35/0.5를 다 뽑아서 귀로 비교하던 중이었고, 팀이 최종적으로 뭘 골랐는지 이 노트북만으로는 확인 안 됨. 2026-08-25에 GUIDE/CAUTION 톤 구분을 위해 0.3 -> **0.15**로 낮춤 — GPU 환경에서 톤 차이·음식명 발음 청취 확인 필요).
- **다음 할 일**: GPU 있는 환경(팀원 PC/Colab)에서 실제로 한번 실행해서 음성이 정상적으로 나오는지 확인.

### ⚠️ 보안 — 노트북 파일에 HF 토큰 평문 노출 발견

받은 노트북(`qwen3_tts_lora_finetune.ipynb`)에 Hugging Face 토큰이 평문으로 하드코딩된 셀이 있었음. 이 노트북은 절대 git에 커밋하지 말 것. 토큰은 이미 로컬 파일에 노출된 상태라 즉시 폐기(rotate) 권장.

### 구현 변경 이력 (2026-08-25) — 리스펠링 표를 DB 컬럼으로 옮기고 치환 위치를 바꿈

**바뀐 것**: TTS에 넘기는 문장에서 음식명을 영문 리스펠링 표기로 바꾼다(`Tteokbokki` →
`Duck-bok-kee`). 바뀐 건 표기 방식이 아니라 **값을 어디에 두고 누가 치환하는가**다. 값은
`src/tts/infer.py`의 파이썬 dict가 아니라 `foods.name_respell` 컬럼에 두고, 치환은
`src/text_gen/narration.py`가 한다.

**왜 DB 컬럼인가**: 표를 코드에 두면 음식이 늘 때마다 코드를 고쳐야 하고, DB의 음식 목록과
어긋나도 알아챌 방법이 없다. 컬럼으로 옮기면 행 하나가 매핑 하나가 되어 DB가 유일한 출처가
된다. 21개에만 값을 넣고 **29개는 NULL로 둔다** — NULL은 실패가 아니라 "원본 로마자 표기로
읽는다"는 뜻이고, 청취 스크리닝에서 원본이 이미 적절하다고 판정한 결과 그대로다
(`eval/TTS_MODULE.md` 4절). 값의 출처는 커밋 8176e66의 `RESPELL_MAP` 21개다.

**왜 narration.py인가**: `get_narration()`이 style을 정하려고 이미 `foods` 행을 조회하는데,
그 행에 `name_en`/`name_respell`이 같이 들어 있다. 반면 `infer.py`는 `food_id`를 받지 않고
(`worker.py`가 `{text, style}`만 넘긴다), paddle/torch 충돌을 피하려고 격리된 별도 프로세스라
DB 접근을 붙이면 그 격리 이유가 무너진다.

**계약 변경**: `get_narration()`이 `tts_text`를 추가로 돌려준다. `text`는 화면 표시용으로
원본 로마자 표기를 유지하고(여행자가 읽어야 한다), `tts_text`만 음식명이 리스펠링 표기로
바뀐다. `src/pipeline.py`와 `src/tts/pregenerate.py`가 `synthesize()`에 `tts_text`를 넘긴다 —
라이브 경로와 사전 생성 캐시가 같은 텍스트를 써야 같은 음성이 나온다.

**같이 삭제한 것**: `src/tts/infer.py`의 `RESPELL_MAP`·`_SORTED_RESPELL_NAMES`·
`apply_respelling()`(커밋 d862e11). 이제 `infer.py`는 받은 텍스트를 그대로 모델에 넘긴다 —
여기서 또 치환하면 이미 바뀐 이름을 두 번 처리하게 된다.

**⚠️ 이 선행 조건은 취소됐다**: 이 항목은 `foods.name_respell` 컬럼 추가 SQL을 실행 전제로
걸어뒀지만, 아래 "최종" 항목에서 표기를 한글로 바꾸면서 **그 SQL은 실행하지 않기로 했다**.
`cache.py`의 select에서도 `name_respell`을 뺐으므로 선행 DB 작업은 없다.

**함께 바뀐 값**: `LORA_SCALE` 0.3 → 0.15 (GUIDE/CAUTION 톤 구분 복구). 표기 방식과는 독립적인
결정이라 표기를 한글로 바꾼 뒤에도 0.15를 유지한다. 배경은 `src/tts/infer.py` 헤더 주석 참고.

**표기 방식은 그 뒤 한글로 확정됐다**: 같은 날 음식명을 한글로 적는 방식(`Tteokbokki` →
`떡볶이`, `foods.name_kr` 사용)을 넣었다 리스펠링으로 되돌렸다가, 다시 한글로 정했다. 경위와
근거는 아래 "최종" 항목에 적었다. 구조(치환은 narration.py가 하고 값은 DB에서 온다)는 이
항목에서 만든 것을 그대로 쓰므로, 그 뒤 바뀐 것은 표기 방식 하나뿐이다.

### 구현 변경 이력 (2026-08-25, 이어서) — 발음 안내 문장을 음성용으로 분리

**문제**: 음식명 치환을 켜면 TTS 문장이 `Duck-bok-kee is ... Duck-bok-kee is pronounced
"ddeok-bo-kki." ...`가 된다. `food_details`의 PRONUNCIATION은 화면에서 로마자 발음 표기를
알려주는 문장이라, 음식명이 리스펠링 표기로 바뀌면 **거의 같은 소리를 연달아 두 번** 읽는다.
50개 전부 해당된다(PRONUNCIATION 문장 형식이 전부 동일).

**해결**: `food_details`에 음성 전용 카테고리 `PRONUNCIATION_TTS`를 추가한다. 테이블 구조
(`food_id`/`category`/`detail_text`)를 그대로 쓰므로 컬럼 추가 없이 행 50개만 넣는다. 문장은
이름을 한 번만 말하는 형태(`Say it like this: Bibimbap.`)이고, 뜻 설명이 있던 17개는 그 절만
살려 뒤에 붙였다. 이름은 `foods.name_en`으로 적어둬서 표기 치환은 그대로 `narration.py`가
담당한다 — 리스펠링 표기를 이 행에 직접 적으면 출처가 둘로 갈린다.

**계약 변경**: `get_narration()`의 `tts_text`가 PRONUNCIATION 대신 PRONUNCIATION_TTS를 쓴다.
`text`(화면용)는 그대로 PRONUNCIATION이다. PRONUNCIATION_TTS 행이 없으면 화면용으로 폴백하므로
코드를 먼저 배포하고 DB 행을 나중에 넣어도 안내가 끊기지 않는다.

**DB 적용**: 이 50행은 2026-08-25에 Supabase SQL Editor로 이미 넣었다. `food_details_category_check`
제약이 카테고리 6종만 허용하고 있어서, 제약을 다시 만들어 `PRONUNCIATION_TTS`를 허용 값에 추가하는
작업이 선행됐다. 넣는 SQL은 저장소에 두지 않는다 — 일회성 데이터 주입이고 현재 값은 DB가 정본이다.

**배포 시 필수**: `python -m src.tts.pregenerate --force`로 캐시를 전량 재생성해야 한다.
`src/pipeline.py`의 `create_tts_response()`가 캐시를 먼저 조회하므로, 낡은 wav를 그대로 두면
코드를 바꿔도 사용자에게는 아무것도 바뀌지 않는다. 현재 `static/tts_cache`의 50개는 이번
변경 이전에 만들어진 것이라 **재생성 대상이다**.

### 구현 변경 이력 (2026-08-25, 최종) — TTS가 읽는 음식명을 한글 표기로 바꿈

**바뀐 것**: TTS에 넘기는 문장에서 음식명을 영문 리스펠링(`Duck-bok-kee`)이 아니라 **한글
표기**(`떡볶이`)로 바꾼다. 값은 이미 있는 `foods.name_kr`이고, 치환하는 코드
(`src/text_gen/narration.py`의 `_to_tts_text()`)와 계약(`text`/`tts_text` 분리)은 위 두 항목에서
만든 것을 그대로 쓴다 — 바뀐 것은 **어떤 표기로 바꾸느냐** 하나다. 화면용 `text`는 여전히
로마자 원문이다(여행자가 소리 내어 읽어야 하는 정보다).

**왜**: 리스펠링은 된소리(ㄸ, ㅃ, ㄲ, ㅆ, ㅉ)에 대응하는 알파벳 신호가 없어 근사치로 타협해야
했고, 리스펠링한 21개뿐 아니라 원본 표기가 적절하다고 판정했던 29개까지 발음이 부정확했다.
철자를 바꿔도 결과가 같다면 원인은 철자가 아니라 **모델이 그 이름을 영어 음운으로 읽는다는
것**이다. 한글로 적으면 읽는 음운 체계 자체가 한국어로 바뀐다.

**DB 작업 없음**: `name_kr`은 50행 전부 채워져 있고 `src/db/cache.py`가 예전부터 select하던
컬럼이다. 그래서 이번 변경에 실행할 SQL이 없고, 위 항목이 걸어둔 선행 조건
(`foods.name_respell` 컬럼 추가)은 **취소한다**. 2026-08-25 확인 기준 DB에 그 컬럼은 없고
(`column foods.name_respell does not exist`, 42703), `cache.py`의 select에서도 뺐다. 자세한
내용과 되돌리기용 `drop column if exists`는 `src/db/README.md`에 있다.

**PRONUNCIATION_TTS는 그대로 쓴다**: 화면용 PRONUNCIATION(`Tteokbokki is pronounced
"ddeok-bo-kki."`)을 음성에 그대로 넣으면 `떡볶이 is pronounced "ddeok-bo-kki."`가 되어 같은
이름을 한국어 발음으로 한 번, 영어 음운으로 읽히는 로마자로 한 번 연달아 읽는다. 이름을 한 번만
말하는 `Say it like this: 떡볶이.` 형태가 표기가 바뀐 뒤에도 그대로 유효하다. DB 행 50개는 이미
들어가 있다.

**⚠️ 아직 검증 안 됨 — 청취 확인이 남았다**: `eval/TTS_MODULE.md` 4절은 "영어 문장 중간에 한글
삽입"을 **실패한 접근**으로 기록해뒀다(`"...called 떡볶이 (tteokbokki)."` 형태에서 결과가
부자연스러웠음 — 코드스위칭 미지원 또는 파인튜닝에 따른 한국어 능력 저하로 추정). 지금 방식은
로마자를 괄호로 병기하지 않고 이름 자체를 한글로 대체한다는 점이 다르지만, 그 기록을 뒤집으려면
실제로 들어봐야 한다. 배포 체크포인트가 리스펠링된 영문 라벨로 학습됐다는 점도 같이 본다 —
한글 읽기는 어댑터가 아니라 베이스 모델의 한국어 능력에 기댄다. GPU 환경에서 50개를 확인하고,
결과에 따라 `eval/TTS_MODULE.md` 4절 기록을 갱신한다.

**배포 시 필수**: `python -m src.tts.pregenerate --force`로 캐시를 전량 재생성해야 한다.
`src/pipeline.py`가 캐시를 먼저 조회하므로, 낡은 wav를 그대로 두면 코드를 바꿔도 사용자에게는
아무것도 바뀌지 않는다.
