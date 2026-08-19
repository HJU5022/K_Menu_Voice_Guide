# Spec — DB 메모리 캐싱

## Why

- **페르소나**: 메뉴판을 촬영해 결과를 기다리는 관광객, 그리고 배포 서버를 운영하는 팀.
- **상황**: `match.py`(후보 매칭), `narration.py`(나레이션), `detail.py`(상세정보)가 요청마다 각자 Supabase를 조회한다. 한 번의 "사진→상세정보" 왕복에서 `foods`·`food_details`·`food_narration` 테이블에 총 4~5회 쿼리가 나간다.
- **문제**: 등록 음식이 50개로 고정돼 있어 데이터 자체는 작은데도, 매 요청마다 네트워크 왕복이 반복돼 응답이 느려진다. 또 Supabase 무료 프로젝트는 7일간 요청이 없으면 자동 일시정지되는데(README 9절 위험 대응), 캐시가 없으면 이 위험이 그대로 남는다.
- **측정 지표**: 같은 프로세스 안에서 동일 데이터를 두 번 이상 조회할 때, DB 쿼리가 최초 1회만 나가는지 테스트로 검증한다.

## Goal

- **해결 목표**: 서버 프로세스가 살아있는 동안 `foods`·`food_details`·`food_narration`·`menu_modifiers` 4개 테이블을 최초 1회만 조회하고, 이후 조회는 메모리에서 처리한다.
- **성공 기준**:
  1. 같은 테이블을 두 번 이상 조회해도 실제 DB 쿼리는 1회만 발생한다.
  2. `match.py`·`narration.py`·`detail.py`의 기존 동작(입력→출력, 예외 메시지 포함)이 캐시 도입 전후로 동일하다.
- **Out of Scope**: 캐시 갱신(TTL, 수동 무효화) — 이번 MVP는 음식 데이터가 발표 전까지 거의 바뀌지 않는다고 가정하고, 서버 재시작 전까지는 갱신하지 않는다. 캐시 워밍업을 서버 시작 시점에 강제로 트리거하는 것(지금은 첫 호출 시점에 지연 로딩).

## What

**Happy Path**

1. 서버가 요청을 처음 받아 `cache.get_foods()`(또는 다른 getter)를 호출한다.
2. 캐시가 비어 있으므로 4개 테이블을 한 번에 Supabase에서 읽어 메모리에 저장한다.
3. 이후 호출은 메모리에 있는 값을 그대로 반환한다.
4. `match.py`·`narration.py`·`detail.py`는 이제 `src.db.supabase_client`가 아니라 `src.db.cache`를 통해서만 데이터를 가져온다.

**Edge Cases**

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | 존재하지 않는 `food_id` 조회 | `get_food()`는 `None`, `get_food_details()`는 빈 dict 반환 — 호출부(`narration.py`/`detail.py`)가 기존과 동일한 문구의 `ValueError`를 던짐 |
| EC-02 | 존재하지 않는 food_id+style 나레이션 조회 | `get_narration_text()`가 `None` 반환, `narration.py`가 기존과 동일한 문구의 `ValueError`를 던짐 |
| EC-03 | 같은 프로세스에서 여러 스레드/요청이 동시에 첫 호출을 함 | Out of Scope — 지금 배포 방식(단일 프로세스, 순차 요청 가정)에서는 경쟁 조건을 별도로 다루지 않음 |

## How

- 대상 파일: `src/db/cache.py` (신규 구현), `src/ocr/match.py`, `src/text_gen/narration.py`, `src/text_gen/detail.py` (Supabase 직접 호출 제거)
- `cache.py`는 모듈 전역 딕셔너리(`_cache`)에 4개 테이블을 통째로 담아두고, `get_foods()`/`get_food(food_id)`/`get_food_details(food_id, categories=None)`/`get_narration_text(food_id, style)`/`get_modifiers()` 5개 조회 함수를 제공한다.
- 첫 호출 때만 실제 쿼리가 나가는 지연 로딩(lazy loading) 방식 — `match.py`에 있던 `_modifiers_cache` 임시 캐시와 같은 패턴을 `cache.py`로 통합한다.
- 기존 함수들의 시그니처·반환값·예외 문구는 바꾸지 않는다 — 데이터를 어디서 가져오는지만 바뀐다.

## AC

**AC-01 · 중복 조회 시 쿼리 1회만 발생**
- GIVEN: 아직 캐시가 비어 있다.
- WHEN: `cache.get_foods()`를 두 번 호출한다.
- THEN: 실제 DB `foods` 테이블 쿼리는 1회만 발생한다.

**AC-02 · 존재하지 않는 음식 조회**
- GIVEN: 캐시에 `food_id=999`가 없다.
- WHEN: `cache.get_food(999)`를 호출한다.
- THEN: `None`을 반환한다.

**AC-03 · 카테고리 필터링**
- GIVEN: 한 음식에 여러 카테고리의 `food_details` 행이 있다.
- WHEN: `cache.get_food_details(food_id, categories=("ALLERGY",))`를 호출한다.
- THEN: `ALLERGY` 카테고리만 담긴 dict를 반환한다.

**AC-04 · 기존 동작 유지**
- GIVEN: `match.py`/`narration.py`/`detail.py`의 기존 테스트 케이스(정상 케이스·예외 케이스)들.
- WHEN: 캐시를 통해 데이터를 가져오도록 바뀐 코드로 같은 테스트를 실행한다.
- THEN: 입력→출력, 예외 메시지가 캐시 도입 전과 동일하다.
