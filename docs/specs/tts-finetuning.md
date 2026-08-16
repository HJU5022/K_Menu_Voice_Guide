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
