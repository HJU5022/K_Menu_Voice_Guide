# Spec — 텍스트 생성

> 뼈대만 잡아둔 상태입니다. 형식은 [`_example.md`](./_example.md)를 따르고, 다섯 섹션을 모두 채운 뒤 구현에 들어갑니다.

## Why

- **페르소나**:
- **상황**:
- **문제**:
- **측정 지표**:

## Goal

- **해결 목표**:
- **성공 기준**:
- **Out of Scope**:

## What

**Happy Path**

1. 선택된 음식 → `food_details`에서 6개 카테고리 조회
2. 카테고리 6개를 카드 형태로 조합 → 상세 텍스트 출력
3. 해당 음식의 `spice_level` 조회
4. `spice_level` → `style`(GUIDE / CAUTION) 자동 결정
5. `food_narration`에서 결정된 style에 맞는 `narration_text` 조회

**카테고리 6개**

| # | 카테고리 | 설명 |
|---|---|---|
| 1 | | |
| 2 | | |
| 3 | | |
| 4 | | |
| 5 | | |
| 6 | | |

**Edge Cases** (최소 5개 + 처리 방식)

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | 6개 카테고리 중 일부가 비어 있음 | |
| EC-02 | `spice_level`이 NULL | |
| EC-03 | 해당 style의 `narration_text`가 없음 | |
| EC-04 | 등록되지 않은 음식 | |
| EC-05 | | |

## How

**spice_level → style 결정 로직**

| spice_level | style |
|---|---|
| | GUIDE |
| | CAUTION |

- 경계값(몇 단계부터 CAUTION인지)을 여기서 확정한다.
- 참조 테이블: `foods`, `food_details`, `food_narration`

## AC (Given-When-Then)

**AC-01 ·**
- GIVEN:
- WHEN:
- THEN:
