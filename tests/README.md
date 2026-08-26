# tests/

테스트 코드를 두는 곳입니다.

## 파일 이름 규칙

`test_{대상모듈}.py` — pytest가 `test_`로 시작하는 파일만 찾습니다.

| 파일 | 검사 대상 |
|---|---|
| `test_ocr_preprocess.py` | `src/ocr/preprocess.py` — 이미지 읽기·전처리 (한글 경로 버그 회귀 방지 포함) |
| `test_ocr_infer.py` | `src/ocr/infer.py` — 전처리 연결, 세로쓰기 글자 회전 처리 |
| `test_ocr_match.py` | `src/ocr/match.py` — 유사도 매칭의 정렬·필터 규칙 (긴 이름 안에 든 짧은 이름을 빼는 규칙 포함) |
| `test_ocr_price.py` | `src/ocr/price.py` — 메뉴판 숫자에서 가격을 읽어내는 규칙 |
| `test_cache.py` | `src/db/cache.py` — DB를 한 번만 읽는지, 조회 함수가 맞는 값을 주는지 |
| `test_narration.py` | `src/text_gen/narration.py` — spice_level→style 결정, 문장 3개 조합, TTS용 음식명 한글 표기 치환(`tts_text`) |
| `test_tts_infer.py` | `src/tts/infer.py` — 텍스트 통과·instruct 적용, 무음 제거 후처리 |
| `test_cart.py` | `src/cart/store.py` — 담기·빼기·비우기와 줄 구분(`food_id` + `menu_text`) |
| `test_pipeline.py` | `src/pipeline.py` — 블록들을 잇는 순서와 실패 시 fallback, 나레이션·이름 두 음성의 캐시 조회 |
| `test_api.py` | `K_Menu_Talk.py` — 엔드포인트별 응답과 업로드 검증(잘못된 타입·초과 크기·빈 파일·열리지 않는 이미지) |
| `test_api_integration.py` | `K_Menu_Talk.py` — 두 엔드포인트를 프론트와 같은 순서로 이어서 검사 |

각 파일 맨 위 설명(docstring)에 "무엇을 왜 검사하는지"가 적혀 있습니다.

## 실제 모델·DB를 쓰지 않습니다

OCR·TTS 모델도, Supabase도 부르지 않습니다. `unittest.mock`으로 가짜 값을 끼워넣어 **로직과 연결 방식만** 검사합니다. 그래서 GPU 없이, 인터넷 없이, 몇 초 만에 돌아갑니다.

## 무엇을 테스트하나

Spec의 **AC(Given-When-Then)** 를 그대로 테스트로 옮깁니다. AC 하나 = 테스트 함수 하나가 기본입니다.

```python
def test_ac01_설명():
    # GIVEN: 준비
    # WHEN: 실행
    # THEN: 검증
```

## 실행

```bash
python -m pytest                          # 전부
python -m pytest tests/test_ocr_match.py  # 파일 하나만
python -m pytest -v                       # 어떤 테스트가 돌았는지 보기
```

> Windows에서 `OSError: [WinError 127]`가 나면, paddle과 torch의 DLL 충돌입니다.
> 배포 진입점(`K_Menu_Talk.py`)에는 `import torch`를 맨 위에 둬서 막아뒀지만,
> pytest로 직접 실행하는 경로에는 아직 같은 조치가 없습니다(알려진 미해결 항목).

## 완료 기준

AC 테스트가 통과하기 전에는 "완료"라고 하지 않습니다. ([AGENTS.md](../AGENTS.md))
