# B. 음식 데이터·나레이션

> **차터** — 음식 설명 텍스트를 탐색한다 / DB에 등록된 음식 전체로 /
> **사실오류·빠진 항목·어색한 영어**를 찾기 위해

| | |
|---|---|
| 담당 | |
| 타임박스 | 60분 |
| 실시일 | |
| 대상 | 배포 서버 `GET /api/foods`, `GET /api/foods/{food_id}` (커밋 `ff48749`) |

## 배경 — 무엇을 보는 영역인가

이 영역은 **음성이 아니라 글자**를 본다. 음성 품질은 C영역이다.

나레이션 텍스트는 새로 생성하지 않는다. DB에 이미 완성된 문장 3개를 순서대로 이어붙일 뿐이다:

```
food_narration.narration_text  →  food_details.PRONUNCIATION  →  food_details.ALLERGY
```

그래서 **여기서 나오는 결함은 대부분 "DB 행이 비었다" 아니면 "문장 내용이 틀렸다"** 둘 중 하나다.
코드 버그보다 데이터 문제가 많은 영역이라, 눈으로 읽는 게 유일한 검증 방법이다.

`food_details` 카테고리는 6개다: DESCRIPTION · PRONUNCIATION · INGREDIENT · HOW_TO_EAT · (맵기) · ALLERGY

## 실행 명령어

등록된 음식 전체 목록:

```bash
curl -s https://hju5022-k-menu.hf.space/api/foods | python3 -m json.tool
```

음식 개수 세기:

```bash
curl -s https://hju5022-k-menu.hf.space/api/foods | python3 -c "import json,sys; print(len(json.load(sys.stdin)))"
```

음식 하나의 상세 + 나레이션:

```bash
curl -s https://hju5022-k-menu.hf.space/api/foods/1 | python3 -m json.tool
```

**전체 음식의 나레이션 텍스트를 한 파일로 뽑기** (읽으면서 검수하기 위함):

```bash
curl -s https://hju5022-k-menu.hf.space/api/foods | python3 -c "
import json, sys, urllib.request
for f in json.load(sys.stdin):
    d = json.load(urllib.request.urlopen(f'https://hju5022-k-menu.hf.space/api/foods/{f[\"food_id\"]}'))
    print(f'--- [{f[\"food_id\"]}] {d[\"name_en\"]} / {d[\"name_kr\"]} (spice={d[\"spice_level\"]}, style={d[\"style\"]})')
    print(d['narration_text']); print()
" > docs/qa/_narration_dump.txt && wc -l docs/qa/_narration_dump.txt
```

> `_narration_dump.txt` 는 검수용 임시 파일이다. **커밋하지 말 것** (앞의 `_` 가 그 표시다).

## 테스트 케이스

`판정` 칸: **P** / **F** / **B**(못 돌림)

| ID | 확인할 것 | 기대 결과 | 실측 결과 | 판정 | 심각도 |
|---|---|---|---|---|---|
| B-01 | `GET /api/foods` 응답 | 음식 목록이 **영문명 순**으로 정렬되어 옴 | | | |
| B-02 | 음식 개수 | 문서에 적힌 개수(50)와 일치 | | | |
| B-03 | 상세 응답 필드 | `name_kr`·`name_en`·`spice_level`·`details`·`narration_text`·`style` 이 전부 있음 | | | |
| B-04 | 나레이션 구성 | 모든 음식에서 **발음 안내 문장과 알레르기 문장이 빠짐없이** 포함 | | | |
| B-05 | `spice_level` 1~3 인 음식 | `style` 이 **GUIDE** | | | |
| B-06 | `spice_level` 4~5 인 음식 | `style` 이 **CAUTION** | | | |
| B-07 | 없는 food_id (`/api/foods/99999`) | **404** (500 아님) | | | |
| B-08 | 음수·문자 food_id (`/api/foods/-1`, `/api/foods/abc`) | 404 또는 422 (500 아님) | | | |
| B-09 | 전체 음식 텍스트 눈으로 읽기 | 사실오류·오탈자·빈 문장 없음 | | | |

### 특히 노려볼 것

- **매운맛 경고가 빠진 매운 음식** — `spice_level` 4~5인데 문장에 경고 표현이 없는 경우
- **알레르기 누락** — 땅콩·계란·우유·갑각류가 들어가는데 알레르기 문장에 언급이 없는 경우.
  **이건 실제로 사람이 다칠 수 있는 항목이라 발견되면 무조건 High다.**
- **발음 안내가 이름과 안 맞는 경우** — 다른 음식의 발음 문장이 붙어 있진 않은지
- **영어가 어색한 문장** — 원어민이 안 쓰는 표현, 문법 오류. 외국인 관광객이 대상이라 실제 문제다

## 품질 지표

| 지표 | 이전 기록 | 이번 실측 | 측정 방법 |
|---|---|---|---|
| 나레이션 완성 음식 수 | — | / 전체 | B-04 결과 집계 |
| 사실오류 건수 | — | | B-09 눈검수 |
| 영어 어색함 건수 | — | | B-09 눈검수 |
| 알레르기 누락 건수 | — | | B-09 눈검수 |

## 자동화 확인

```bash
cd /Users/jeong-un/Documents/Projects/Main_1_projects/proj1-c && python -m pytest tests/test_narration.py -v
```

- [ ] 수동 실행 완료 → 1점
- [ ] 자동화 통과 → +1점

## 발견한 결함

| # | 증상 | 재현 방법 (food_id 포함) | 심각도 | 비고 |
|---|---|---|---|---|
| | | | | |
