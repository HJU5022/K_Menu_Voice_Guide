# tests/

테스트 코드를 두는 곳입니다.

## 파일 이름 규칙

`test_{대상모듈}.py` — pytest가 `test_`로 시작하는 파일만 찾습니다.

```
tests/
├── test_preprocess.py
├── test_match.py
├── test_narration.py
└── test_pipeline.py
```

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
pytest
pytest tests/test_match.py     # 파일 하나만
pytest -v                       # 어떤 테스트가 돌았는지 보기
```

## 완료 기준

AC 테스트가 통과하기 전에는 "완료"라고 하지 않습니다. ([AGENTS.md](../AGENTS.md))
