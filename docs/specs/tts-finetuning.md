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
4. `{ "text": narration_text, "style": style }`을 반환한다.
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
- 반환 키: `text`, `style`
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

### 1차 구현은 추측이었고 틀렸음 — 실제 학습 노트북 확보 후 전면 재작성함

처음엔 `finetuning/infer_lora_custom_voice.py`(커뮤니티 레포가 패치로 추가하는 파일)를 공개 저장소에서 못 찾아서, 공식 `qwen_tts` 소스 코드만 읽고 추측으로 구현했음(`generate_voice_clone` + `VoiceClonePromptItem` 방식). 이후 박민영님이 실제 학습에 쓴 노트북(`qwen3_tts_lora_finetune.ipynb`)을 받아 그 안의 실행 결과(패치 파일 `patches/0001-qwen3-tts-lora.patch`)에서 진짜 코드를 확인한 결과, **핵심 부분이 추측과 달랐음**:

- ~~`generate_voice_clone` + 참조 음성 임베딩 직접 주입~~ → **`generate_custom_voice` + "이름 있는 스피커 등록" 방식이 맞았음**. 학습된 목소리를 `config.json`의 `talker_config.spk_id`에 이름→ID로 등록해두고, `speaker_embedding.safetensors`의 `target_speaker_embedding` 텐서를 그 ID 위치의 `core_model.talker.model.codec_embedding.weight`에 직접 덮어쓰는 방식.
- LoRA는 `PeftModel`로 감싼 뒤 기본적으로 `merge_and_unload()`로 베이스에 합쳐짐 (처음엔 안 합치고 그냥 감싸기만 했었음).
- LoRA scale은 `peft.tuners.lora.LoraLayer.set_scale()`로 적용 (처음엔 `.scaling` 딕셔너리를 직접 건드렸었음 — 결과적으로 비슷한 효과지만 정식 API가 따로 있었음).
- `infer.py`를 이 실제 코드를 그대로 옮겨서 전면 재작성함 (`src/tts/infer.py`의 `_resolve_core_model`/`_apply_speaker_config`/`_apply_speaker_embedding`/`_set_lora_scale`이 패치 파일의 동명 함수를 그대로 옮긴 것).

### 검증 상태 — 아직 실행 확인 못 함

**로컬에 GPU가 없어서 이 구현을 실제로 돌려서 확인하지 못했다.** 단위 테스트(`tests/test_tts_infer.py`)는 모델 호출 부분을 가짜(mock)로 대체해서 입력 검증 로직·반환 형식만 확인한 것이고, 진짜 모델이 진짜 음성을 만들어내는지는 검증되지 않았다. 다만 로직 자체는 실제 학습에 쓰인 코드를 그대로 옮긴 것이라 이전보다 신뢰도가 훨씬 높음.

- **확인 필요한 값**: `speaker_name="speaker"`(노트북에서 커스텀 이름을 준 적이 없어 기본값이 계속 쓰였음), `LORA_SCALE=0.3`(노트북은 0.2/0.3/0.35/0.5를 다 뽑아서 귀로 비교하던 중이었고, 팀이 최종적으로 뭘 골랐는지 이 노트북만으로는 확인 안 됨) — 팀 확정값 확인 후 상수 갱신 필요.
- **다음 할 일**: GPU 있는 환경(팀원 PC/Colab)에서 실제로 한번 실행해서 음성이 정상적으로 나오는지 확인.

### ⚠️ 보안 — 노트북 파일에 HF 토큰 평문 노출 발견

받은 노트북(`qwen3_tts_lora_finetune.ipynb`)에 Hugging Face 토큰이 평문으로 하드코딩된 셀이 있었음. 이 노트북은 절대 git에 커밋하지 말 것. 토큰은 이미 로컬 파일에 노출된 상태라 즉시 폐기(rotate) 권장.
