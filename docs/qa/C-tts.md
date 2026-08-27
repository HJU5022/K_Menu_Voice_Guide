# C. TTS 음성

> **차터** — 생성 음성을 탐색한다 / 한국어 음식명이 섞인 영어 문장으로 /
> **발음 깨짐·끊김·부자연스러움**을 찾기 위해

| | |
|---|---|
| 담당 | |
| 타임박스 | 45분 |
| 실시일 | |
| 대상 | 배포 서버 `GET /api/foods/{food_id}` 응답의 음성 파일 (커밋 `ff48749`) |

## 배경 — 음성이 두 개다

응답에는 음성 경로가 **두 개** 들어 있다. 둘을 헷갈리면 엉뚱한 걸 평가하게 된다.

| 필드 | 무엇 | 상태 필드 |
|---|---|---|
| `narration_audio_path` | 음식 설명 전체를 읽은 긴 음성 | `tts_status` |
| `name_audio_path` | **음식 이름만** 읽은 짧은 음성 (화면의 스피커 버튼용) | `name_tts_status` |

또 하나 알아둘 것: **화면에 보이는 글자와 음성으로 읽는 글자가 다르다.**
화면은 로마자(`Bibimbap`)를 그대로 두고, TTS에 넘길 때만 한글(`비빔밥`)로 바꾼다.
로마자를 그대로 읽히면 모델이 영어 음운으로 읽어서 발음이 뭉개지기 때문이다.

**그래서 이 영역의 핵심 확인 사항은 "한국어 음식명이 한국어답게 읽히는가"다.**

`tts_status` 가 `not_ready` 여도 **텍스트 응답은 정상으로 와야 한다** — 음성 합성이 실패해도
설명 글자까지 막지 않는 설계다. 텍스트까지 안 오면 그건 별개의 결함이다.

## 실행 명령어

응답에서 음성 관련 필드만 뽑기:

```bash
curl -s https://hju5022-k-menu.hf.space/api/foods/1 | python3 -c "import json,sys; d=json.load(sys.stdin); print({k:d[k] for k in ('name_en','name_kr','style','tts_status','name_tts_status','tts_latency_ms','narration_audio_path','name_audio_path')})"
```

음성 파일 내려받아 듣기 (경로는 위 응답의 `narration_audio_path` 값):

```bash
curl -s -o /tmp/narration_1.wav "https://hju5022-k-menu.hf.space<narration_audio_path 값>" && afplay /tmp/narration_1.wav
```

**청취 평가용 샘플 10개 한 번에 받기** (매운 음식과 안 매운 음식을 섞을 것):

```bash
mkdir -p /tmp/tts_samples && for i in 1 2 3 4 5 6 7 8 9 10; do curl -s "https://hju5022-k-menu.hf.space/api/foods/$i" | python3 -c "
import json,sys,urllib.request
d=json.load(sys.stdin); p=d.get('narration_audio_path')
print(d['food_id'], d['name_en'], d['tts_status'], p)
if p: urllib.request.urlretrieve('https://hju5022-k-menu.hf.space'+p, f'/tmp/tts_samples/{d[\"food_id\"]}_{d[\"name_en\"]}.wav')
"; done && ls -la /tmp/tts_samples/
```

## 테스트 케이스

| ID | 확인할 것 | 기대 결과 | 실측 결과 | 판정 | 심각도 |
|---|---|---|---|---|---|
| C-01 | `tts_status` | 전 음식에서 **`ok`** (실패 시 `not_ready`) | | | |
| C-02 | `name_tts_status` | 전 음식에서 **`ok`** | | | |
| C-03 | 음성 파일 실제 재생 | 소리가 나고 중간에 끊기지 않음 | | | |
| C-04 | 나레이션 음성 길이 | 텍스트 분량에 맞는 길이 (너무 짧으면 잘린 것) | | | |
| C-05 | **한국어 음식명 발음** | 음식 이름이 **한국어 발음으로** 읽힘 (영어식으로 읽으면 결함) | | | |
| C-06 | 이름 전용 음성 | 이름만 짧게 읽고, 나레이션과 동시에 재생되지 않음 | | | |
| C-07 | `tts_latency_ms` 값 | 1ms 안팎이면 캐시, 수백~수천ms면 그 자리에서 합성한 것 — 어느 쪽인지 기록 | | | |
| C-08 | CAUTION 스타일 음식 | GUIDE 음식과 톤이 구별됨 | | | |
| C-09 | 음성 파일 URL 직접 열기 | 404 없이 파일이 내려옴 | | | |

### ⚠️ 반드시 확인할 것 — 배포된 음성이 낡았을 가능성

미리 만들어둔 음성 캐시가 **한글 이름 치환을 적용하기 전에 생성된 것일 수 있다.**
그러면 코드는 최신인데 음성만 옛날 것이라, C-05가 조용히 실패한다.

**판정 방법: 귀로 듣는 것이 유일하다. HTTP 응답으로는 알 수 없다.**

파일 시각(`Last-Modified`)이나 해시로 판정하려 하지 말 것. 서버는 캐시 파일을 그대로
주지 않고 **요청할 때마다 임시 파일로 복사해서** 내보낸다. 그래서 받은 파일의 시각은
언제나 "방금"이고, 이름도 매번 달라진다. 낡은 캐시든 새 음성이든 겉으로는 똑같아 보인다.

대신 두 신호를 조합해서 판정한다:

| 신호 | 확인 방법 | 뜻 |
|---|---|---|
| 캐시에서 나왔나 | `tts_latency_ms` 가 1ms 안팎으로 매우 작음 | 미리 만들어둔 파일을 쓴 것 |
| 한국어로 읽나 | 음성을 직접 들어봄 | 이름이 영어식으로 들리면 낡은 캐시 |

**둘 다 해당하면(캐시에서 나왔는데 이름이 영어식으로 들린다) 낡은 캐시가 확정이다.**

낡았다고 판정되면 → 재생성이 필요하다. **재생성은 GPU 데스크톱에서만 되므로,
발견 즉시 팀에 알리고 아래 결함표에 적을 것.** 이 영역에서 혼자 해결하려 하지 말 것.

## 청취 평가 (합불이 아니라 점수로)

빈 파일이 이미 준비돼 있다: `eval/mos_scores.csv` — 헤더만 있고 **데이터는 0행이다.**
여기를 채우는 게 이 영역의 산출물이다.

컬럼: `model, sample_id, narration_text, rater, pronunciation, naturalness, note`

두 축을 1~5점으로 따로 준다.

| 점수 | pronunciation (발음이 정확한가) | naturalness (사람 같은가) |
|---|---|---|
| 5 | 전부 알아들을 수 있음 | 사람이 읽은 것과 구별 안 됨 |
| 4 | 거의 정확, 한두 군데 어색 | 약간 기계 같지만 자연스러움 |
| 3 | 알아들을 수는 있음 | 기계 티가 남 |
| 2 | 몇 군데 못 알아들음 | 듣기 불편함 |
| 1 | 무슨 말인지 모르겠음 | 참고 듣기 어려움 |

| 지표 | 이전 기록 | 이번 실측 | 비고 |
|---|---|---|---|
| pronunciation 평균 | 없음 (0행) | | 샘플 10개 |
| naturalness 평균 | 없음 (0행) | | 샘플 10개 |
| 평가자 수 | — | n = | |

> **"MOS"라고 부르지 말 것.** 정식 MOS는 청취자 10~20명이 필요한데 우리는 팀원 몇 명이다.
> 문서에는 **"팀 내부 청취 평가 (n=?)"** 로 적고 표본 수를 반드시 밝힌다.
> 표본 수를 숨기고 "MOS 4.2점"이라고 쓰면 나중에 과장했다는 지적을 받는다.

## 자동화 확인

```bash
cd /Users/jeong-un/Documents/Projects/Main_1_projects/proj1-c && python -m pytest tests/test_tts_infer.py tests/test_cache.py -v
```

- [ ] 수동 실행 완료 → 1점
- [ ] 자동화 통과 → +1점

## 발견한 결함

| # | 증상 | 재현 방법 (food_id 포함) | 심각도 | 비고 |
|---|---|---|---|---|
| | | | | |
