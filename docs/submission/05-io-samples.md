# 05. 입력에 따른 생성 결과물

> 제출물 5번 — 음성·텍스트 입력에 따른 생성 결과물
>
> 이 문서의 텍스트·JSON은 **손으로 쓴 예시가 아니라 실제로 서버를 띄우고 받은 응답**이다
> (2026-08-26, 로컬 `K_Menu_Talk.py` + Supabase 실서비스 DB).

## 0. 가이드 항목과 이 프로젝트의 대응 관계

가이드는 "음성·텍스트 입력에 따른 생성 결과물"을 요구한다. 이 프로젝트의 입출력은 다음과 같다.

| 가이드가 말하는 것 | 이 프로젝트에서 | 비고 |
|---|---|---|
| 입력 | **메뉴판 사진** (+ 후보 목록에서 음식 선택) | 촬영 또는 업로드 |
| 조건 입력 | **음식의 `spice_level` (1~5)** | 사용자가 고르지 않는다. 음식 데이터가 정한다 |
| 텍스트 출력 | 카테고리 6개 상세 + 내레이션 텍스트 | 영어 |
| 음성 출력 | 내레이션 음성 + **음식 이름만 읽는 별도 음성** | GUIDE / CAUTION 두 스타일 |
| **음성 입력(STT)** | **없다** | 기획 초기 후보였으나 범위에서 제외했다. 근거는 [07. 발표자료 원고](07-presentation-outline.md) "무엇을 뺐는가" |

**"입력 조건에 따라 음성이 달라진다"(주제 유형 2)를 만족하는 지점**은 맵기 분기다 —
`spice_level ≥ 4`면 스타일이 `CAUTION`으로, 아니면 `GUIDE`로 자동 결정되고, 문장과 톤이 함께 바뀐다.

---

## 1. 입력 → 출력 사례

### 사례 A. 메뉴판 사진 한 장 → 후보 5개 (OCR 실행 결과)

**입력**: [`assets/sample-menu-synthetic.jpg`](assets/sample-menu-synthetic.jpg) — 6줄짜리 합성 메뉴판

**실제 응답** (`POST /api/analyze`):

```json
{
  "status": "candidates_found",
  "ocr_text": "메뉴 떡볶이 9,000 비빔밥 12,000 갈비탕 14,000 召大| 10,000 불고기 18,000 순두부찌개 10,000",
  "candidates": [
    { "food_id": 3,  "name_kr": "떡볶이",    "name_en": "Tteokbokki",     "score": 100, "price_krw": 9000  },
    { "food_id": 1,  "name_kr": "비빔밥",    "name_en": "Bibimbap",       "score": 100, "price_krw": 12000 },
    { "food_id": 7,  "name_kr": "갈비탕",    "name_en": "Galbitang",      "score": 100, "price_krw": 14000 },
    { "food_id": 2,  "name_kr": "불고기",    "name_en": "Bulgogi",        "score": 100, "price_krw": 18000 },
    { "food_id": 12, "name_kr": "순두부찌개", "name_en": "Sundubu Jjigae", "score": 100, "price_krw": 10000 }
  ]
}
```

**여기서 실제로 일어난 실패를 그대로 남긴다** — 6줄 중 `김치찌개`가 **`召大|`로 오인식**되어
매칭에서 빠졌다(5/6). 화면에서도 그 줄만 박스가 없다([04. 캡처 ③](04-pipeline-nodes.md#③-후보-목록-화면)).

- 가격 6개는 전부 정확히 복원됐다 — 파인튜닝이 아니라 **base 인식기가 읽은 결과**다(하이브리드, 노드 3)
- 실측 소요: 첫 요청 73.9초 / 워밍업 후 22.4초 (이 머신의 PaddleOCR은 **CPU 빌드**)

### 사례 B. `food_id = 3` (떡볶이, spice_level 4) → **CAUTION**

**실제 응답** (`GET /api/foods/3`, 2026-08-26 로컬):

```json
{
  "food_id": 3, "name_kr": "떡볶이", "name_en": "Tteokbokki", "spice_level": 4,
  "details": {
    "DESCRIPTION": "Chewy rice cakes simmered in a thick, spicy-sweet chili paste sauce, a favorite Korean street food.",
    "SPICY": "Quite spicy — made with a generous amount of gochujang (chili paste). If you're sensitive to heat, ask for a milder version.",
    "INGREDIENT": "Rice cakes (tteok), fish cakes, gochujang, gochugaru (chili flakes), sugar, and scallions.",
    "HOW_TO_EAT": "Eat straight from the pan while hot, using a fork or toothpick for the rice cakes and fish cakes.",
    "ALLERGY": "Contains gluten (rice cake and fish cake) and soy. Not suitable for those avoiding spicy food.",
    "PRONUNCIATION": "Tteokbokki is pronounced \"ddeok-bo-kki.\"",
    "PRONUNCIATION_TTS": "Say it like this: Tteokbokki."
  },
  "narration_text": "Tteokbokki is chewy rice cakes simmered in a thick, spicy chili sauce, and it can be quite hot. If you're sensitive to spice, ask for a milder version or have a cold drink nearby. It's a beloved Korean street food worth trying carefully. Tteokbokki is pronounced \"ddeok-bo-kki.\" Contains gluten (rice cake and fish cake) and soy. Not suitable for those avoiding spicy food.",
  "style": "CAUTION",
  "tts_status": "ok",
  "narration_audio_path": "/audio/tmpn45xqico.wav",
  "tts_latency_ms": 4.91,
  "name_audio_path": "/audio/tmpm_m9lufr.wav",
  "name_tts_status": "ok"
}
```

**TTS에 실제로 들어가는 문장은 화면 문장과 다르다.** 음식명이 한글로 치환된다:

> `tts_text`: **"떡볶이** is chewy rice cakes simmered in a thick, spicy chili sauce, and it can be
> quite hot. … **Say it like this: 떡볶이.** Contains gluten…"

화면에는 로마자(`Tteokbokki`)를 그대로 남긴다 — 여행자가 소리 내어 읽어야 하는 정보이기 때문이다.
발음 안내도 화면용(`PRONUNCIATION`)과 음성용(`PRONUNCIATION_TTS`)이 다르다. 화면 문장을 그대로
읽히면 `떡볶이 is pronounced "ddeok-bo-kki."`가 되어 **같은 이름을 한국어 음운으로 한 번,
영어 음운으로 한 번 연달아 읽기** 때문이다.

- 🔊 내레이션: [`assets/audio/food_3_CAUTION.wav`](assets/audio/food_3_CAUTION.wav)
- 🔊 이름만: [`assets/audio/name_3.wav`](assets/audio/name_3.wav)

### 사례 C. `food_id = 1` (비빔밥, spice_level 2) → **GUIDE**

같은 파이프라인에 맵기만 다른 음식을 넣은 결과다.

```json
{
  "food_id": 1, "name_kr": "비빔밥", "name_en": "Bibimbap", "spice_level": 2,
  "narration_text": "Bibimbap is a colorful bowl of warm rice topped with seasoned vegetables, meat, and a fried egg. It's only mildly spicy, and mixing everything together with your spoon is part of the fun. A great choice if you want something wholesome and easy to enjoy. Bibimbap is pronounced \"bee-bim-bap.\" The name literally means \"mixed rice.\" Contains egg and soy. A vegetarian version without meat is often available on request.",
  "style": "GUIDE",
  "tts_status": "ok",
  "tts_latency_ms": 6.45,
  "name_tts_status": "ok"
}
```

- 🔊 내레이션: [`assets/audio/food_1_GUIDE.wav`](assets/audio/food_1_GUIDE.wav)
- 🔊 이름만: [`assets/audio/name_1.wav`](assets/audio/name_1.wav)

### 사례 D. 갈비탕 (spice_level 1) — 맵지 않은 음식의 문장

```
"Galbitang is a clear, mild soup made by slow-simmering beef short ribs until tender.
 It has almost no spice, just a light, savory broth. A gentle, nourishing choice if you
 want a break from spicy food. Galbitang is pronounced "gal-bi-tang." Beef-based.
 Generally free of major allergens, but check for added soy sauce."   → style: GUIDE
```

---

## 2. 조건 대비 — 같은 파이프라인, 다른 입력

| 항목 | 비빔밥 (사례 C) | 떡볶이 (사례 B) |
|---|---|---|
| 입력 조건 `spice_level` | 2 | **4** |
| 결정된 스타일 | `GUIDE` | **`CAUTION`** |
| 문장 톤 | "A great choice if you want something wholesome and easy to enjoy." | **"…it can be quite hot. If you're sensitive to spice, ask for a milder version or have a cold drink nearby."** |
| TTS `instruct` | *Speak in a calm, informative tone, like a knowledgeable guide…* | ***Say it in an urgent, warning tone, as if cautioning someone.*** |
| 화면 표시 | 불꽃 2/5 | 불꽃 4/5 + 알레르기 카드 강조 |
| 음성 파일 | [`food_1_GUIDE.wav`](assets/audio/food_1_GUIDE.wav) | [`food_3_CAUTION.wav`](assets/audio/food_3_CAUTION.wav) |

**문장과 톤이 함께 바뀐다.** 문장은 DB의 스타일별 템플릿에서, 톤은 TTS의 `instruct` 파라미터에서
갈린다. 사용자는 아무것도 고르지 않는다.

> **한 음식은 한 스타일만 갖는다.** 캐시 50개의 구성은 GUIDE 46개 · CAUTION 4개다 —
> `spice_level ≥ 4`인 음식이 4개(떡볶이·낙지볶음·아구찜·매운탕)뿐이기 때문이다. 그래서 A/B 비교는
> "같은 음식의 두 스타일"이 아니라 **"다른 음식, 다른 스타일"**로 들어야 한다.
> 같은 문장을 두 톤으로 들으려면 아래 Perso.ai 비교 오디오(3절)를 쓴다.

---

## 3. 상용 서비스 비교 청취 (Perso.ai)

같은 화자를 Perso.ai 쪽에 클로닝하고 **같은 문장**을 양쪽에 넣어 만든 오디오 4개다.

| 스타일 | 우리 모델 | Perso.ai | UTMOS (우리 / Perso) |
|---|---|---|---|
| GUIDE | [`ours_guide.wav`](../../eval/perso_comparison/ours_guide.wav) | [`perso_guide.wav`](../../eval/perso_comparison/perso_guide.wav) | 4.2916 / 4.1135 (**104.3%**) |
| CAUTION | [`ours_caution.wav`](../../eval/perso_comparison/ours_caution.wav) | [`perso_caution.wav`](../../eval/perso_comparison/perso_caution.wav) | 4.4408 / 4.1556 (**106.9%**) |

사용 문장:

- **GUIDE** — `Bibimbap is a colorful bowl of warm rice topped with seasoned vegetables, meat, and a fried egg.`
- **CAUTION** — `Careful, this one's spicy! Duck-bok-kee is chewy rice cakes simmered in a thick, spicy chili sauce.`

> ⚠️ 스타일당 문장 1개(n=1)라 통계적 유의성은 없다. CAUTION 문장은 **리스펠링 표기**(`Duck-bok-kee`)를
> 쓰고 있어 현행(한글 표기)과 다르다. 자세한 한계는 [08. 모델 비교 실험](08-model-experiments.md) 2-3절.

---

## 4. 베이스 모델 vs 파인튜닝 청취 샘플 — **없다**

파인튜닝 전 베이스 모델로 같은 문장을 생성해 나란히 들을 수 있는 오디오 쌍이 **저장소에 없다.**
발음 개선은 팀 내부 청취로만 판정했고(`eval/TTS_MODULE.md` 6-3), 그 오디오는 보존되지 않았다.

가이드가 "오디오 샘플을 발표 자료에 직접 들을 수 있게 포함"을 권하므로, 발표 전에 베이스 모델로
사례 B·C의 두 문장을 생성해 A/B로 넣는 것을 권한다(GPU 필요, 사람이 해야 하는 일).

---

## 5. ⚠️ 첨부한 오디오 4개는 교체 **이전** 파일이다

**서비스 캐시는 갱신됐고, 이 문서에 붙인 파일만 낡았다.** 둘을 구분해서 읽어야 한다.

| 대상 | 상태 |
|---|---|
| 서비스 캐시 `static/tts_cache` (100개) | ✅ **2026-08-27 교체 완료** — 배포 Space에서 한글 표기로 생성된 캐시로 갈아끼웠다. 구 파일은 `static/tts_cache_backup/`에 남아 있다 |
| 이 문서의 `assets/audio/` 4개 | ⚠️ **교체 전 파일** — 4개 모두 바이트 크기가 `tts_cache_backup/`의 구 파일과 정확히 같다 |

원래 문제는 이랬다. 음식명을 한글 표기로 바꾼 커밋이 `e457921`(**2026-08-25 22:12**)인데
당시 `static/tts_cache`의 내레이션 wav 50개는 **2026-08-25 03:05~03:13** 생성분이라 19시간
앞섰다(이름 음성 `name_*.wav`는 08-26 생성이라 전환 이후였다). `src/pipeline.py`가 캐시를
먼저 조회하므로, 캐시를 갱신하지 않으면 코드를 아무리 고쳐도 사용자에게 들리는 소리는
그대로다 — 그래서 배포 전 블로킹 항목이었고, 08-27에 해소했다.

남은 일은 **파일 복사 하나**다(GPU 불필요). 발표 자료에 붙일 소리와 서비스가 내는 소리를
맞춘다:

```bash
cp static/tts_cache/food_1_GUIDE.wav static/tts_cache/food_3_CAUTION.wav    static/tts_cache/name_1.wav static/tts_cache/name_3.wav    docs/submission/assets/audio/
```

[README 색인](README.md#사람이-해야-할-남은-일)의 3번 항목이다.

> `static/`은 `.gitignore` 대상이라 새 PC에는 캐시가 없다. 그때는
> `python -m src.tts.pregenerate`로 먼저 만든다(GPU 필요).
