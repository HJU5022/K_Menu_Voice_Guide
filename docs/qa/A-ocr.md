# A. OCR·매칭

> **차터** — 메뉴판 이미지를 탐색한다 / 세로쓰기·저조도·흔들림·비메뉴판 이미지로 /
> **글자를 놓치거나 엉뚱한 음식으로 매칭되는 조건**을 찾기 위해

| | |
|---|---|
| 담당 | |
| 타임박스 | 60분 |
| 실시일 | |
| 대상 | 배포 서버 `POST /api/analyze` (커밋 `ff48749`) |

## 준비물

1. **메뉴판 사진 3장** — `demo_menus/` (`01_수식어_시연.jpg`, `02_같은음식_다른줄.jpg`, `03_실제메뉴판_유형.jpg`)
   > ⚠️ 이 폴더는 **저장소 밖**(`Main_1_projects/demo_menus/`)에 있다. 저장소만 clone한
   > 팀원은 같은 사진을 못 구해서 결과를 비교할 수 없다. **테스트 시작 전에 팀 채팅으로
   > 3장을 공유받을 것.**
2. **직접 찍은 사진 4장** — 세로쓰기 간판 / 어두운 조명 / 흔들린 사진 / 메뉴판이 아닌 사진(사람·풍경)
3. (선택) AI Hub "관광 음식메뉴판 데이터"(222) 검증셋 — 아래 품질 지표 재측정용. 없으면 그 표는 건너뛴다

## 실행 명령어

```bash
cd /Users/jeong-un/Documents/Projects/Main_1_projects
```

배포 서버에 사진 한 장 보내기 (응답 시간까지 같이 잼):

```bash
curl -s -w "\n[HTTP %{http_code}] %{time_total}s\n" -X POST https://hju5022-k-menu.hf.space/api/analyze -F "image=@demo_menus/01_수식어_시연.jpg"
```

응답에서 볼 것은 `status` 와 `candidates` 두 개다. `status` 는 네 가지만 나온다:

| status | 뜻 | 언제 나와야 정상인가 |
|---|---|---|
| `candidates_found` | 등록된 음식 후보를 찾음 | 정상 메뉴판 |
| `unsupported_food` | 메뉴 줄은 읽었는데 등록된 음식이 없음 | 우리가 모르는 음식만 있는 메뉴판 |
| `not_a_menu` | 메뉴판으로 안 보임 | 사람·풍경 사진 |
| `ocr_empty` | 글자를 하나도 못 읽음 | 완전히 뭉개진 사진 |

`unsupported_food` 와 `not_a_menu` 를 구별하는 게 이 설계의 핵심이다. 앞은 "다시 찍어도
소용없다", 뒤는 "다시 찍으면 된다"라서 사용자가 할 행동이 정반대다. **둘이 뒤바뀌어
나오면 결함이다.**

## 테스트 케이스

`판정` 칸: **P**(기대대로 동작) / **F**(다르게 동작) / **B**(못 돌림 — 서버 다운, 준비물 없음)

| ID | 입력 | 기대 결과 | 실측 결과 (status / 후보 / 응답시간) | 판정 | 심각도 |
|---|---|---|---|---|---|
| A-01 | `01_수식어_시연.jpg` | `candidates_found`, 수식어가 붙은 이름이 후보에 반영 | | | |
| A-02 | `02_같은음식_다른줄.jpg` | `candidates_found`, **같은 음식이 여러 줄에 있으면 줄마다 따로 후보로** 나옴 | | | |
| A-03 | `03_실제메뉴판_유형.jpg` | `candidates_found`, 가격이 이름과 올바르게 짝지어짐 | | | |
| A-04 | 세로쓰기 간판 사진 | 세로로 적힌 글자도 읽힘 (과거 실패했다가 고친 부분) | | | |
| A-05 | 어두운 조명 사진 | 후보가 나오거나, 못 읽으면 `ocr_empty` | | | |
| A-06 | 흔들린 사진 | 500이 아니라 정상 status 중 하나 | | | |
| A-07 | 사람·풍경 사진 | **`not_a_menu`** (`unsupported_food` 아님) | | | |
| A-08 | 등록 안 된 음식만 있는 메뉴판 | **`unsupported_food`** (`not_a_menu` 아님) | | | |
| A-09 | 같은 사진 2회 연속 요청 | 두 번 다 같은 후보 목록 | | | |

### 특히 노려볼 것 (알려진 약점)

- **중복 후보** — `갈비탕` 이 적힌 줄에서 `갈비` 와 `갈비탕` 이 둘 다 후보로 올라오는가?
- **짧은 이름 오탐** — 3글자 이름은 두 글자만 맞아도 점수가 높게 나온다.
  등록 안 된 3글자 음식이 적힌 메뉴판에서 엉뚱한 음식이 튀어나오는지 본다.
- **가격 오배치** — 가격이 음식명 *아래 줄*에 있는 메뉴판에서 짝이 어긋나는가?

## 품질 지표 (합불로 판정하지 않고 숫자만 적는다)

이전 기록은 `src/ocr/match.py` 주석의 실측표(메뉴판 100장, 임계값 85 기준)다.

| 지표 | 이전 기록 | 이번 실측 | 측정 방법 |
|---|---|---|---|
| 매칭 정밀도 | 84.9% | | `eval/measure_match_precision.py` |
| 매칭 재현율 | 86.9% | | 〃 |
| 오탐 건수 | 26 | | 〃 |
| 놓친 건수 | 22 | | 〃 |
| 응답시간 (배포, 1장) | — | | 위 curl 의 `time_total` 중앙값 (5회) |

> **주의 — `--source label` 로만 재면 회귀를 못 잡는다.** 라벨의 정답 글자를 그대로
> 넣는 모드라 OCR 오류가 통째로 배제된다. 매칭 로직만 볼 때 쓰는 모드다.

데이터셋이 있는 경우에만:

```bash
cd /Users/jeong-un/Documents/Projects/Main_1_projects/proj1-c
python eval/measure_match_precision.py --source ocr --labels <라벨폴더> --images <원천이미지폴더> --limit 100 --cache eval/.match_precision_ocr_cache.json
```

## 자동화 확인

```bash
cd /Users/jeong-un/Documents/Projects/Main_1_projects/proj1-c
python -m pytest tests/test_ocr_match.py tests/test_ocr_infer.py tests/test_ocr_preprocess.py tests/test_ocr_price.py -v
```

- [ ] 수동 실행 완료 (위 케이스 표를 채웠다) → 1점
- [ ] 자동화 통과 (위 pytest가 전부 통과) → +1점

## 발견한 결함

| # | 증상 | 재현 방법 | 심각도 | 비고 |
|---|---|---|---|---|
| | | | | |

> 실패한 케이스를 적지 않으면 이 문서를 만든 의미가 없다. 애매하면 일단 적는다.
