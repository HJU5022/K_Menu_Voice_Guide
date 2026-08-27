# E. 파이프라인 E2E

> **차터** — 사진→음성 전 과정을 탐색한다 / 정상 3케이스 + 예외 5케이스로 /
> **중간에 끊기거나 무응답이 되는 지점**을 찾기 위해

| | |
|---|---|
| 담당 | |
| 타임박스 | 90분 |
| 실시일 | |
| 대상 | 배포 서버 전체 흐름 (커밋 `ff48749`) |

## 배경 — 실제 흐름은 두 번의 요청이다

한 번에 끝나지 않는다. **사용자가 중간에 음식을 고르는 단계가 있다.**

```
[1] 사진 업로드          POST /api/analyze        → 음식 후보 목록
        ↓  (사용자가 후보 중 하나를 고른다)
[2] 음식 상세 요청       GET /api/foods/{food_id} → 설명 텍스트 + 음성 파일
        ↓
[3] 음성 파일 재생        GET <narration_audio_path>
```

**A~D 영역이 각 조각을 보는 반면, 이 영역은 조각 사이의 이음매를 본다.**
개별 API가 다 정상인데 이어 붙이면 끊기는 경우가 실제로 가장 흔하다.
특히 **[1]에서 받은 `food_id` 를 [2]에 그대로 넣었을 때 통하는지**, **[2]가 준 음성 경로가
[3]에서 실제로 열리는지** 두 지점을 집중해서 본다.

## 실행 명령어

**전 과정을 한 번에 돌리는 스크립트** — 사진 한 장을 넣으면 음성 파일까지 받아온다:

```bash
cd /Users/jeong-un/Documents/Projects/Main_1_projects && python3 - <<'PY'
import json, time, urllib.request, subprocess
BASE = "https://hju5022-k-menu.hf.space"
IMAGE = "demo_menus/01_수식어_시연.jpg"   # ← 바꿔가며 테스트

t0 = time.time()
out = subprocess.run(["curl","-s","-X","POST",f"{BASE}/api/analyze","-F",f"image=@{IMAGE}"],
                     capture_output=True, text=True).stdout
step1 = time.time() - t0
r = json.loads(out)
print(f"[1] status={r['status']}  후보={len(r['candidates'])}개  {step1:.1f}초")
if not r["candidates"]:
    print("후보가 없어 여기서 종료"); raise SystemExit

fid = r["candidates"][0]["food_id"]
print(f"    고른 음식: food_id={fid}  {r['candidates'][0].get('name_en')}")

t1 = time.time()
d = json.load(urllib.request.urlopen(f"{BASE}/api/foods/{fid}"))
step2 = time.time() - t1
print(f"[2] tts_status={d['tts_status']}  {step2:.1f}초")
print(f"    텍스트: {d['narration_text'][:60]}...")

path = d.get("narration_audio_path")
if path:
    t2 = time.time()
    urllib.request.urlretrieve(BASE + path, "/tmp/e2e_narration.wav")
    print(f"[3] 음성 저장 완료 /tmp/e2e_narration.wav  {time.time()-t2:.1f}초")
else:
    print("[3] 음성 경로 없음 — 실패")

print(f"\n총 소요: {time.time()-t0:.1f}초")
PY
```

받은 음성 듣기:

```bash
afplay /tmp/e2e_narration.wav
```

## 테스트 케이스

| ID | 입력 | 기대 결과 | 실측 결과 (총 소요시간 포함) | 판정 | 심각도 |
|---|---|---|---|---|---|
| **정상 경로** | | | | | |
| E-01 | `01_수식어_시연.jpg` | 후보 → 상세 → 음성까지 끊김 없이 완주 | | | |
| E-02 | `02_같은음식_다른줄.jpg` | 후보 여러 개, 각각 골라도 전부 완주 | | | |
| E-03 | `03_실제메뉴판_유형.jpg` | 완주 + 가격이 후보에 함께 표시 | | | |
| **예외 경로** | | | | | |
| E-04 | 사람·풍경 사진 | `not_a_menu` 로 끝나고 **화면이 멈추지 않음** | | | |
| E-05 | 등록 안 된 음식만 있는 메뉴판 | `unsupported_food` 로 끝나고 안내가 나옴 | | | |
| E-06 | 완전히 뭉개진 사진 | `ocr_empty` (500 아님) | | | |
| E-07 | [1]의 `food_id` 를 [2]에 넣기 | **후보에서 받은 id가 그대로 통함** (404 나면 심각) | | | |
| E-08 | 음성 합성이 실패한 음식 | `tts_status` 가 실패여도 **설명 텍스트는 정상으로 옴** | | | |
| E-09 | 같은 사진으로 전 과정 2회 | 두 번째가 캐시 덕에 더 빠름 | | | |

### 특히 노려볼 것 — 이음매

- **`food_id` 불일치** — [1]이 준 id로 [2]를 부르면 404가 나는 경우. 조각별로는 정상인데 이어지지 않는 전형적 사례다
- **음성 경로 형식** — [2]가 준 경로가 서버 내부 파일 경로라서 브라우저에서 못 여는 경우
- **후보가 0개인데 화면이 다음 단계로 넘어가려 하는 경우**
- **첫 요청만 느린가, 매번 느린가** — 캐시가 실제로 동작하는지의 판단 근거

## 품질 지표

| 구간 | 이전 기록 | 이번 실측 (중앙값) | 측정 방법 |
|---|---|---|---|
| [1] 사진 → 후보 | 22.8초 (로컬 CPU, 2026-08-23) | | 위 스크립트 `[1]` |
| [2] 음식 → 텍스트+음성 | — | | 위 스크립트 `[2]` |
| [3] 음성 내려받기 | — | | 위 스크립트 `[3]` |
| **총 소요 (사진→음성)** | — | | 5회 실행 후 중앙값 |

> 이전 기록 22.8초는 **로컬 CPU 측정치**라 배포 서버 값과 직접 비교하면 안 된다.
> 이번 실측은 배포 서버 기준이므로 별개 숫자로 적는다.

완주율도 같이 적는다: **완주한 케이스 수 / 시도한 케이스 수 = ___ / 9**

## 자동화 확인

```bash
python -m pytest tests/test_api_integration.py tests/test_pipeline.py -v
```

- [ ] 수동 실행 완료 → 1점
- [ ] 자동화 통과 → +1점

## 발견한 결함

| # | 증상 | 어느 단계에서 끊겼나 ([1]/[2]/[3]) | 재현 방법 | 심각도 |
|---|---|---|---|---|
| | | | | |
