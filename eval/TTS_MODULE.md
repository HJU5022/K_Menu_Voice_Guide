# K-Menu Voice Guide — TTS 모듈 (Qwen3-TTS 1.7B LoRA)

| 항목 | 값 |
|---|---|
| 담당 | 박민영 |
| 베이스 모델 | `Qwen/Qwen3-TTS-12Hz-1.7B-Base` |
| 배포 어댑터 | [huggingface.co/k-bite-team/k-menu-qwen3-tts-lora](https://huggingface.co/k-bite-team/k-menu-qwen3-tts-lora) (2026-10-20 개인 계정 `hajeongun/k-menu-qwen3-tts-lora`로 그대로 복사) |
| 최종 갱신 | 2026-08-28 — 9차 학습 로그를 `training_log.csv`에 복원(3절)하고, 현행 배포 설정의 UTMOS·WER 측정치를 6절에 실었다. 그 전 2026-08-27에 TTS 캐시를 한글 표기본으로 교체했고(7절), 2026-08-26에 배포 체크포인트 9차 · 음식명 표기 한글 전환 · `LORA_SCALE` 0.15를 반영했다 |

## 현재 배포 기준 (한눈에)

문서 전체가 실험 이력이라 길다. **지금 서비스가 실제로 쓰는 값만** 먼저 정리한다.

| 항목 | 현재 값 | 근거 |
|---|---|---|
| 체크포인트 | `instruct_trained_lr5e-6_ep40` / **checkpoint-epoch-31** (9차) | [3절](#3-파인튜닝-차수별-실측값) |
| 하이퍼파라미터 | lr 5e-6 · rank 16 · alpha 32 · 40 epoch · batch 4 | 3절 |
| `LORA_SCALE` | **0.15** (2026-08-25에 0.3에서 낮춤) | [src/tts/infer.py](../src/tts/infer.py) |
| 음식명 표기 | **한글** (`Tteokbokki` → `떡볶이`, `foods.name_kr`) | [4절](#4-발음-개선--음식명-표기) |
| 표기 치환 위치 | `src/text_gen/narration.py`의 `_to_tts_text()` — TTS 모듈이 아님 | 4절 |
| 톤 구분 | `instruct` 파라미터 — 9차부터 **학습에도 반영됨** | [5절](#5-톤-구분--guidecaution-instruct) |
| 서빙 경로 | Plan B(사전 생성 캐시) — `static/tts_cache/food_{id}_{STYLE}.wav` | [model_comparison.md](./model_comparison.md) 3절 |

> ⚠️ **이 문서의 정량 평가(6절)는 현재 배포 설정 기준이 아니다.** UTMOS 수치는 전부 3차 체크포인트 ·
> `LORA_SCALE` 0.3 · 영문 리스펠링 표기 시절에 측정한 값이다. 체크포인트·scale·표기가 모두 바뀌었으므로
> 재측정 대상이다 ([7절](#7-체크리스트) 참고).

---

## 1. 개요

기획서(SDD MVP v3)의 Qwen3-TTS는 최초 기술검증 단계에서 LoRA/PEFT 파인튜닝 공식 미지원으로 확인되어 후보에서 제외되었으나, 실제로는 검증된 비공식 커뮤니티 LoRA 패치([instavar/qwen3-tts-lora-finetuning](https://github.com/instavar/qwen3-tts-lora-finetuning))가 존재함을 확인하고, 이를 기반으로 파인튜닝을 재개하여 최종적으로 채택했다.

핵심 목표 두 가지:

1. 영어 문장 속 한국 음식명 발음 정확도 향상
2. GUIDE(안내)/CAUTION(경고) 스타일 톤 구분

---

## 2. 학습 환경 및 파이프라인

### 2-1. 설정

| 항목 | 값 |
|---|---|
| 실행 환경 | Google Colab (A100) |
| 베이스 모델 | `Qwen/Qwen3-TTS-12Hz-1.7B-Base` |
| 파인튜닝 방식 | LoRA — target modules `q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj` (어텐션 + FFN 전체) |
| 학습 데이터 | 나레이션(실제 녹음) 50개 + 발음용 캐리어 문장(실제 녹음) 250개 = **원본 300개** |
| 학습 샘플 수 | **348개** (CAUTION 클래스 오버샘플링 포함) |
| 데이터 분할 | 80 / 10 / 10 — `food_id` × `style` 기준 층화 분할 |
| 오디오 스펙 | 24kHz mono WAV로 통일 (코덱 파이프라인 요구사항) |

### 2-2. 공식·커뮤니티 스크립트에서 발견하고 패치한 버그 (6건)

| # | 위치 | 증상 | 조치 |
|:--:|---|---|---|
| 1 | `Accelerator`에 `project_dir` 누락 | tensorboard 로깅 시 `ValueError` | `project_dir=args.output_model_path` 추가 |
| 2 | `infer_lora_custom_voice.py`에 `main()` 호출 누락 | 추론 스크립트가 아무것도 안 하고 종료 | 파일 끝에 `main()` 호출 추가 |
| 3 | `torchao` 버전 비호환 | PEFT LoRA 적용 시 `ImportError` | `pip install -U torchao` |
| 4 | 기본값 `attn_implementation=flash_attention_2` | flash-attn 미설치 환경에서 로드 실패 | `sdpa`로 고정 |
| 5 | 체크포인트 저장 시 모델 경로를 상대경로로 가정 | `config.json` 복사 시 `FileNotFoundError` | 베이스 모델을 로컬에 사전 다운로드 |
| 6 | `ref_audio` 스타일별 분리 시 `collate_fn`이 동일 길이 전제 | 배치 처리 중 `RuntimeError` (텐서 크기 불일치) | 전 샘플 `ref_audio`를 동일 클립으로 통일 |

---

## 3. 파인튜닝 차수별 실측값

원 계획(Qwen3-TTS Low/Mid 구간 기준선)이 아니라, 실제 스크리닝 결과 XTTS-v2·F5-TTS로 전환했던 기획서 v3 시점 이후 — 비공식 LoRA 경로 확인 후 Qwen3-TTS 자체를 재검증하여 아래와 같이 진행했다.

**전 차수 공통 고정값**: batch 4 · LoRA alpha = rank × 2 · 학습 샘플 348개 · A100 1장

| 차수 | run_id | &nbsp;&nbsp;LR&nbsp;&nbsp; | rank | epoch | min Val Loss | final Val Loss | 학습 시간 |
|:--:|---|:------:|:--:|:--:|:--:|:--:|:--:|
| 1차 | *(초기 10ep 실험, 미로깅)* | 2e-6 | 16 | 10 | ~10.87 `ep9` | ~10.87 `ep9` | — |
| 2차 | *(초기 40ep 실험, 미로깅)* | 2e-6 | 16 | 40 | ~8.998 `ep39` | ~8.998 `ep39` | — |
| 3차 | `lr5e-6_ep40` | 5e-6 | 16 | 40 | **8.8902** `ep33` | 8.9129 `ep39` | 1,367.6s |
| 4차 | `lr1e-5_ep40` | 1e-5 | 16 | 40 | 8.8808 `ep17` | 9.5494 `ep39` | 1,371.3s |
| 5차 | `lr2e-5_ep40` | 2e-5 | 16 | 40 | 8.8628 `ep9` | 10.2733 `ep39` | 1,359.1s |
| 6차 | `lr5e-6_r32_ep40` | 5e-6 | **32** | 40 | 8.8816 `ep21` | 9.1858 `ep39` | 1,384.1s |
| 7차 | `lr5e-6_ep100` | 5e-6 | 16 | **100** | 8.8888 `ep32` | 10.3887 `ep99` | 3,412.4s |
| 8차 | `final_respelled_lr5e-6_ep40` | 5e-6 | 16 | 40 | 8.8875 `ep31` | 8.9122 `ep39` | 1,414.9s |
| **9차 (배포)** | `instruct_trained_lr5e-6_ep40` | 5e-6 | 16 | 40 | **8.8919** `ep31` | 8.9163 `ep39` | 1,399.2s |

### 근거

- **1차 (베이스라인)** — 최초 성공 학습 확인용. 기본 LR(2e-6) 그대로.
- **2차 (에폭 확장)** — 낮은 LR로도 에폭을 늘리면 개선됨을 확인. 다만 하강이 여전히 완만.
- **3차** — LR 2.5배 상향. **하이퍼파라미터 탐색의 기준선으로 채택**되어 이후 차수의 비교 대상이 됨.
- **4차** — 최저점은 3차보다 낮으나 이후 발산(overfitting). 채택 제외.
- **5차** — 공식 스크립트의 원래 기본 LR. 가장 이른 최저점 후 가장 크게 발산 — 불안정성 확인, 채택 제외.
- **6차** — LoRA rank 2배 확장(용량 테스트, alpha도 32→64). 최저점 개선이 0.01 미만인 데다 불안정성만 증가 → **rank 확장 무효과 확인, rank=16 유지 결정**.
- **7차** — 3차 설정을 100에폭까지 연장. **epoch 25~40 구간은 8.89~8.92대로 평탄(바닥)하고, epoch 41부터 스파이크 없이 완만·지속적으로 상승(전형적 과적합 곡선)해 epoch 99에 10.39 도달.** 데이터셋 규모가 성능 상한을 결정한다는 결론의 핵심 근거.
- **8차** — 3차와 동일 하이퍼파라미터 + **리스펠링 21개가 반영된 학습 텍스트**로 재학습. 2026-08-20까지의 배포 버전이었으나, 표기 방식이 한글로 바뀌면서(4절) 학습 라벨의 전제가 무너졌다.
- **9차 (현재 배포)** — 8차와 하이퍼파라미터는 같고, **학습 스크립트(`dataset.py` / `sft_12hz_lora.py`)를 고쳐 `instruct` 임베딩을 시퀀스 앞에 이어붙이도록 바꿔** instruct를 실제 학습에도 반영했다. 8차까지는 instruct가 추론 시점에만 걸려 학습/추론 조건이 어긋나 있었다(5절). 배포는 최저점인 `checkpoint-epoch-31`을 쓴다.

**하이퍼파라미터 탐색 결론**: LR·rank를 5개 조합으로 실험한 결과 최저 Val Loss는 8.86~8.89 범위에 공통 수렴했고(차이 0.03 이내), 100에폭까지 연장해도 같은 지점에서 벽에 부딪혔다(7차). 이는 최적화(하이퍼파라미터) 문제가 아니라 **학습 데이터 규모(348개)의 근본적 한계**로 판단해, 추가 탐색 대신 데이터 품질 개선(표기 방식, 4절) 방향으로 전환했다.

> **⚠️ 재현 상태 — 로그는 복원됐고, 노트북은 아직 없다.**
> `eval/training_log.csv`에 9차 40에폭이 들어왔다(2026-08-28). 학습에 쓴 Colab 작업 디렉토리의
> 원본 로그에서 복원한 것으로, 기존 3~8차 300행과 모든 열이 일치하는 상위집합이었다. 이로써
> 9차 수치의 출처가 [`src/tts/infer.py`](../src/tts/infer.py) 헤더 주석에서 에폭별 원본 로그로
> 바뀌었다(min 8.8919 `ep31`은 주석의 값과 일치). 1·2차는 로깅 이전이라 여전히 없다.
> 다만 `eval/qwen3_tts_lora_final.ipynb`는 **8차(`final_respelled_lr5e-6_ep40`) 기준 노트북**이라
> 배포 체크포인트를 재현하지 못한다 — instruct를 학습에 반영한 `dataset.py` / `sft_12hz_lora.py`
> 수정본이 빠져 있다(7절).

---

## 4. 발음 개선 — 음식명 표기

영어 문장 속 한국 음식명을 모델이 영어 음운으로 읽어버리는 문제를 어떻게 풀지에 대한 기록이다. **결론부터: 영문 리스펠링 → 한글 표기로 바뀌었다 (2026-08-25).**

### 4-1. 시도 이력

| 시도 | 결과 | 현재 상태 |
|---|---|:--:|
| IPA 발음기호를 텍스트에 직접 입력 | 모델이 IPA 기호를 일반 문자처럼 그대로 읽음 (부자연스러운 발화) | 폐기 |
| 공식 phoneme/음소 입력 API | Qwen3-TTS 공식 문서([mintlify](https://qwenlm-qwen3-tts.mintlify.app/)) 확인 결과 별도 음소 입력 채널 없음 — `generate_custom_voice`는 `text` 파라미터만 지원 | 경로 없음 |
| 영어 문장 중간에 한글 **병기** (`"...called 떡볶이 (tteokbokki)."`) | 부자연스러운 결과 (코드스위칭 미지원 또는 파인튜닝에 따른 한국어 능력 저하로 추정) | 폐기 |
| **영문 알파벳 리스펠링** (`Tteokbokki` → `Duck-bok-kee`) | 21개 음식에서 청취 개선 확인, 8차 학습 라벨에도 반영 | **폐기 (2026-08-25)** |
| **한글 표기 대체** (`Tteokbokki` → `떡볶이`) | 로마자 병기 없이 이름 자체를 한글로 교체 | **현행 · 청취 검증 대기** |

### 4-2. 리스펠링 (2026-08-25 폐기, 기록 보존)

음식명을 영어 알파벳만으로 다시 표기해, 모델이 이미 보유한 영어 읽기 능력으로 더 정확한 발음을 유도하는 방식이었다. 파인튜닝된 어댑터로 원본 표기 vs 리스펠링 표기를 각각 생성해 청취 비교하는 방식으로 전체 50개를 스크리닝했고, **21개는 리스펠링 필요 · 29개는 원본 표기가 이미 적절**로 판정했다.

<details>
<summary><strong>리스펠링 21개 전체 목록</strong> — 현재 코드에서는 쓰지 않음 (펼쳐 보기)</summary>

| 원본 표기 | 리스펠링 | 원본 표기 | 리스펠링 |
|---|---|---|---|
| Tteokbokki | Duck-bok-kee | Kimchi Bokkeumbap | Kim-chee Bok-kum-bap |
| Bibimbap | Bee-bim-bahp | Kimchi Jjigae | Kim-chee Jee-geh |
| Nakji Bokkeum | Nahk-jee Boh-kum | Kongguksu | Kong-gook-soo |
| Agujjim | Ah-goo-jim | Mulhoe | Mul-hweh |
| Maeuntang | May-oon-tang | Ojingeo Bokkeum | Oh-jing-uh Bok-kum |
| Bibim Naengmyeon | Bee-bim Nang-myun | Sundae | Soon-deh |
| Cheonggukjang | Chung-gook-jang | Sundubu Jjigae | Soon-doo-boo Jee-geh |
| Doenjang Jjigae | Dwen-jang Jee-geh | Tteokgalbi | Duck-gal-bee |
| Dongtae Jjigae | Dong-teh Jee-geh | Tteokguk | Duck-gook |
| Dubu Kimchi | Doo-boo Kim-chee | Yukhoe | Yook-hweh |
| Jeyuk Bokkeum | Jeh-yook Bok-kum | | |

나머지 29개는 원본 로마자 표기 그대로 사용했다(Bulgogi, Samgyeopsal 등 — 청취 테스트로 원본이 이미 정확하다고 판정).

</details>

**폐기 사유 (2026-08-25)**: 된소리(ㄸ, ㅃ, ㄲ, ㅆ, ㅉ)는 영어 알파벳 표기 체계에 대응 신호가 없어 근사치로만 타협 가능했다(예: `Tteokbokki`의 `Tt`를 그대로 둬도 실제 된소리가 나지 않음). 결정적으로 **리스펠링한 21개뿐 아니라, 원본 표기가 적절하다고 판정했던 29개까지 발음이 부정확했다.** 철자를 바꿔도 결과가 같다면 원인은 철자가 아니라 **모델이 그 이름을 영어 음운으로 읽는다는 것**이다.

부작용도 확인됐다 — 리스펠링은 발음 정확성을 높이는 대신 발화 자연스러움(UTMOS)을 일부 희생시켰다(6-2절). 하락폭이 컸던 5개:

| 음식 | UTMOS 변화 |
|---|:--:|
| Doenjang Jjigae | −0.64 |
| Ojingeo Bokkeum | −0.60 |
| Dongtae Jjigae | −0.48 |
| Sundae | −0.39 |
| Bibim Naengmyeon | −0.30 |

값 21개는 커밋 `8176e66`의 `RESPELL_MAP`에도 남아 있다. 코드(`RESPELL_MAP` · `_SORTED_RESPELL_NAMES` · `apply_respelling()`)는 커밋 `d862e11`에서 `src/tts/infer.py`에서 삭제됐다.

### 4-3. 현행 — 한글 표기 (2026-08-25 ~)

음식명을 한글로 적어 **모델이 읽는 음운 체계 자체를 한국어로 바꾼다.**

| 항목 | 내용 |
|---|---|
| 값의 출처 | `foods.name_kr` — 50행 전부 채워져 있고 `src/db/cache.py`가 예전부터 select하던 컬럼 (표기 전용 컬럼을 새로 두지 않음) |
| 치환 코드 | [`src/text_gen/narration.py`](../src/text_gen/narration.py)의 `_to_tts_text()` — 단어 경계(`\b`) 기준 매칭 (`Galbi`가 `Tteokgalbi` 안쪽을 파먹지 않도록) |
| 치환 범위 | `tts_text`에만 적용. 화면용 `text`는 로마자 원문 유지 — 여행자가 소리 내어 읽어야 하는 정보다 |
| TTS 모듈의 역할 | `src/tts/infer.py`는 받은 `tts_text`를 **그대로 모델에 넘긴다** — 여기서 또 치환하면 이중 처리가 된다 |
| 발음 안내 문장 | `food_details`의 `PRONUNCIATION_TTS` 카테고리 사용 (50행, 2026-08-25 DB 반영) |

**왜 `narration.py`인가**: `get_narration()`이 style을 정하려고 이미 `foods` 행을 조회하므로 `name_en` / `name_kr` 쌍이 손에 있다. 반면 `infer.py`는 `food_id`를 받지 않고(`worker.py`가 `{text, style}`만 넘긴다), paddle/torch 충돌을 피하려 격리된 별도 프로세스라 DB 접근을 붙이면 격리 이유가 무너진다.

**왜 `PRONUNCIATION_TTS`가 따로 필요한가**: 화면용 `PRONUNCIATION`을 음성에 그대로 넣으면 `떡볶이 is pronounced "ddeok-bo-kki."`가 되어, 같은 이름을 한국어 음운으로 한 번 · 영어 음운으로 읽히는 로마자로 한 번 연달아 읽는다. 이름을 한 번만 말하는 형태(`Say it like this: 떡볶이.`)로 갈아끼운다.

> **⚠️ 아직 청취 검증 전이다.** 4-1절이 "영어 문장 중간에 한글 병기"를 실패한 접근으로 기록해뒀다.
> 현행 방식은 로마자를 괄호로 병기하지 않고 **이름 자체를 한글로 대체**한다는 점이 다르지만, 그 기록을
> 뒤집으려면 실제로 들어봐야 한다. 배포 체크포인트(9차)가 **리스펠링된 영문 라벨로 학습됐다**는 점도
> 같이 본다 — 한글 읽기는 어댑터가 아니라 베이스 모델의 한국어 능력에 기댄다. `LORA_SCALE`을 0.15로
> 낮춘 것이 이 점에서는 오히려 유리하다. GPU 환경에서 50개 확인이 남아 있다(7절).

---

## 5. 톤 구분 — GUIDE/CAUTION (`instruct`)

### 배경 문제

학습 데이터의 CAUTION 클래스가 전체의 8%(50개 중 4개 음식)에 불과해, 하이퍼파라미터를 5개 조합으로 실험해도(3~7차) 톤 구분 학습 자체가 근본적으로 개선되지 않았다.

### 해결: `instruct` 파라미터

Qwen3-TTS 공식 문서 조사 중 `generate_custom_voice()`에 자연어로 톤·감정을 직접 지시하는 `instruct` 파라미터가 있음을 확인했다. 사용 중이던 커뮤니티 추론 스크립트에는 이 파라미터가 연결돼 있지 않아 직접 패치(`infer_lora_custom_voice.py`, `run_lora_infer.sh`)해 사용 가능하도록 했다.

### 확정된 instruct 문구

강도 4단계(약함 → 중간 → 강함 → 극단) 비교 청취 및 언어 비교(영어 vs 중국어 — 영어가 더 명확)를 거쳐 확정했다. 현재 값은 [`src/tts/infer.py`](../src/tts/infer.py)의 `INSTRUCT_MAP`에 있다.

| 스타일 | instruct 문구 |
|---|---|
| GUIDE | `Speak in a calm, informative tone, like a knowledgeable guide explaining something interesting. Keep a natural, steady pace, not slow.` |
| CAUTION | `Say it in an urgent, warning tone, as if cautioning someone.` |

### ⚠️ 정정 (2026-08-20) — "재학습 없이 적용된다"는 8차까지의 이야기였다

이 절은 원래 *"재학습 없이 기존 체크포인트에서 즉시 적용됨 — 학습 데이터 부족을 추론 시점 트릭으로 우회한 것"* 이라고 적혀 있었다. 확인 결과 **8차(epoch-39)까지의 체크포인트에만 해당하는 설명**이었다.

- 8차를 학습한 스크립트(`sft_12hz_lora.py`)에는 애초에 `instruct`를 받는 경로 자체가 없었다. 즉 당시 관찰된 톤 구분 효과는 파인튜닝이 아니라 **베이스 모델의 zero-shot instruct-following 능력**에서 나온 것이다.
- **9차(현재 배포, epoch-31)부터는 학습 스크립트를 고쳐 instruct를 실제 학습에도 반영했다.** 이제 학습 조건과 추론 조건이 일치한다(3절).

### `LORA_SCALE`과 톤 구분의 관계 (2026-08-25)

어댑터를 세게 걸수록 학습된 단일 화자 톤이 instruct를 눌러 두 스타일이 비슷하게 들린다. 그래서 톤 구분 복구를 위해 **`LORA_SCALE`을 0.3 → 0.15로 낮췄다.** 기존 0.2 / 0.3 / 0.35 / 0.5 청취 비교는 톤이 아니라 음질 기준이었다(1.0은 거의 항상 깨진 결과가 나온다 — 커뮤니티 가이드).

scale을 낮춰도 화자 음색은 유지된다 — 음색은 `speaker_embedding`을 `codec_embedding.weight`에 직접 덮어쓰는 방식이고, 그 주입은 `merge_and_unload()` **이후**라 scale이 곱해지는 LoRA 델타와 무관하다.

### 별개 이슈 — 발화 안정성 (2026-08-20)

실제 GPU 실행에서 발화 시작부에 최대 0.8초 무음, 문장 중간에 200~600ms 끊김이 확인됐다. **`LORA_SCALE`(0.2/0.3/0.4/0.5)이나 instruct 유무와 무관하게 재현**됐고(0.5에서는 327초짜리 폭주 생성까지 발생, 정상은 25~30초), `generate_custom_voice` 자체의 워밍업 특성으로 판단해 `infer.py`의 `_trim_silence()`로 생성 후 후처리한다. 톤 구분 문제와는 무관하다.

---

## 6. 평가

### 현재 배포 설정 측정 (2026-08-27/28) — 이 절의 정본

배포 캐시에 실려 있는 나레이션 50개를 **그대로** 채점했다. 이 wav들은 배포 Space가 생성해 둔 것을
받아온 파일이라(7절), 새로 만들지 않고도 **현재 배포 조건 그대로**를 잰다 — 9차 `checkpoint-epoch-31` ·
`LORA_SCALE` 0.15 · 한글 표기.

| 지표 | 값 |
|---|:--:|
| UTMOS 평균 | **4.0742** (중앙값 4.1522 · min 2.9482 · max 4.3349) |
| UTMOS — GUIDE / CAUTION | 4.0742 (n=46) / 4.0736 (n=4) — 스타일 간 차이 없음 |
| WER | **1.83%** |
| WER — 음식명 낱말 제외 (`wer_core`) | **1.21%** |
| 참조 음식명이 영어 ASR에 그대로 잡힌 비율 | 35/50 (0.70) |

- **측정**: `python -m eval.measure_tts_quality --score-cache` · 원본 [`eval/tts_quality/deployed.csv`](./tts_quality/deployed.csv)·`.json` · 오디오 합계 1,047.2초
- 맨 아래 항목은 품질 지표가 아니다. TTS 입력에서 음식명은 한글로 치환되어 **한국어 음운으로 읽히는 것이 의도한 동작**이라(4절), 영어 ASR이 그 낱말을 놓치는 것은 정상이다. 안내 문장 자체가 알아들리는지는 `wer_core`가 본다. 이름 발음의 정확성은 [`eval/verify_name_audio.py`](./verify_name_audio.py)가 한국어 ASR로 따로 본다.
- **재현 확인 (2026-08-28)**: 같은 명령을 다시 돌려 **50행 CSV와 요약 JSON이 바이트 단위로 동일**한 것을 확인했다 — UTMOS·WER은 물론 파일별 ASR 전사까지 전부 같다. 채점 모델과 ASR이 고정된 wav에 대해 결정론적이라 값이 흔들리지 않는다.

> ⚠️ **아래 6-1~6-4는 과거 설정 기준 기록이다.** 6-2의 UTMOS 수치는 모두 **3차 체크포인트 ·
> `LORA_SCALE` 0.3 · 영문 리스펠링 표기** 시절 측정치다. 인용할 때는 반드시 그 조건을 함께 적을 것.

### 6-1. Val Loss

| 지표 | 1차 (베이스라인, lr 2e-6, 10ep) | 9차 (현재 배포) |
|---|:--:|:--:|
| Val Loss | ~10.87 | **8.8919** |
| 개선폭 | — | **−1.98 (약 18% 감소)** |

참고: 8차 최종 Val Loss는 8.9122 `ep39`. 9차는 최저점인 `ep31`을 배포한다.

### 6-2. 자동 평가 — UTMOS (1차, no-reference MOS 예측)

외부 평가자 확보 전, 자동 MOS 예측 모델([UTMOS22](https://github.com/tarepan/SpeechMOS), `utmos22_strong`)로 예비 정량 평가를 진행했다. 사람 평가자 없이 오디오 자체의 자연스러움(naturalness)만 1~5점으로 예측하는 모델이며, 오디오 76개를 채점했다.

**측정 조건**

| 평가 대상 | n | 사용 체크포인트 | `lora_scale` |
|---|:--:|---|:--:|
| 하이퍼파라미터 실험 (3~7차) | 12 | 각 run의 **마지막 에폭** — 3~6차 `ep39` / 7차 `ep99` | 0.3 |
| 리스펠링 전·후 + 원본유지 (food_screen) | 64 | `lr5e-6_ep40` (**3차**) `checkpoint-epoch-39` | 0.3 |

7차의 `ep99`는 발산 이후 지점이므로 해당 실험 점수는 그 run의 최선 상태가 아니다.

**결과**

| 구분 | n | 평균 UTMOS | min | max |
|---|:--:|:--:|:--:|:--:|
| 하이퍼파라미터 실험 (3~7차 GUIDE/CAUTION) | 12 | 4.0124 | 3.7233 | 4.3066 |
| 리스펠링 적용 **전** (16개 음식) | 16 | 3.9618 | 3.5018 | 4.3395 |
| 리스펠링 적용 **후** (16개 음식) | 16 | 3.9224 | 3.1438 | 4.2347 |
| 리스펠링 불필요 판정 (27개 음식, 원본 유지) | 27 | 4.0659 | 3.3459 | 4.3316 |

**주요 발견 — 리스펠링 전/후 UTMOS 평균 −0.0393 (16개 중 8개만 개선)**

이는 리스펠링이 "틀렸다"는 뜻이 아니라, **UTMOS가 측정하는 축(발화의 일반적 자연스러움)과 리스펠링이 개선하려는 축(한국 음식명 발음의 정확성)이 서로 다르기 때문**으로 해석했다. UTMOS는 해당 단어가 무엇을 뜻하는지, "올바른" 목표 발음이 무엇인지 알지 못한다. 하이픈으로 음절을 강제 분리하는 표기가 발음을 더 정확하게 만드는 대신 약간의 유창함을 희생시키는 트레이드오프로 나타난 것으로 판단했다(하락폭 큰 5개는 4-2절).

> ⚠️ **이 평가의 한계 세 가지**
> 1. **food_screen 64개는 3차 체크포인트 기준**이다 — 리스펠링 텍스트가 학습에 반영되기 *전* 모델로,
>    "베이스 모델의 일반화 능력만으로 리스펠링 텍스트를 얼마나 잘 읽는지"를 측정한 것이다.
> 2. **하이퍼파라미터 실험 12개는 설정당 GUIDE/CAUTION 각 1개(n=1)** 라 표본이 매우 작다. 참고용으로만
>    쓰고, 3절의 Val Loss 기반 결론(수십 에폭 전체 궤적, 8개 run)을 더 신뢰한다.
> 3. **표기 방식이 한글로 바뀌면서 리스펠링 전/후 비교 자체가 현행과 무관해졌다.**

원본 데이터 `utmos_results.csv`는 **저장소에 없다** — 채점을 돌린 Colab Drive(`work/utmos_results.csv`)에만 있다.

### 6-3. 정성 평가 (팀 내부 청취, 비공식)

> ⚠️ 정식 MOS 평가가 아닌 팀 내부 청취 기준 판단이다. 정식 수치는 7절 참고.

| 항목 | 관찰 | 현행 유효성 |
|---|---|---|
| 발음 | 표기 교정 없이는 다수 음식명이 부정확하게 발화됨(예: Tteokbokki를 영어 단어처럼 읽음). 리스펠링 적용 후 21개에서 확연한 개선 확인 | ⚠️ **부분 무효** — 이후 29개도 부정확함이 드러나 한글 표기로 전환(4-2절). 한글 표기 청취 확인은 **미실시** |
| 톤 구분 | `instruct` 미적용 시 GUIDE/CAUTION 간 청각적 차이 거의 없음. 적용 후 CAUTION 발화에서 속도·긴장감 차이가 뚜렷하게 감지됨 | ✅ 유효. 단 `LORA_SCALE` 0.3에서 톤이 다시 눌리는 현상이 있어 0.15로 낮춤(5절) — **재확인 필요** |
| Perso.ai 비교 | 1차 결과 확보 완료 | 6-4절 참고 |

### 6-4. Perso.ai 비교 (1차, 2026-08-21)

[`src/tts/perso_client.py`](../src/tts/perso_client.py)로 Perso.ai Speech API(voice cloning)를 연동했다. 같은 나레이션 화자(나레이션 샘플 5개, 화자 본인 동의 확인 — 공개용 문서 예시는 [`docs/legal/tts-voice-consent/`](../docs/legal/tts-voice-consent/) 참고)로 Perso.ai 쪽 voice를 클로닝(`voice_id: psv-5fb5f0ee151cce710625a02fd6578184`)해서, 같은 문장을 우리 모델(**9차 instruct-trained `epoch-31`**)과 Perso.ai 양쪽에 넣고 UTMOS22로 채점했다.

| 스타일 | 우리 모델 | Perso.ai | 비율 (기준 ≥85%) |
|---|:--:|:--:|:--:|
| GUIDE | 4.2916 | 4.1135 | **104.3%** ✅ |
| CAUTION | 4.4408 | 4.1556 | **106.9%** ✅ |

사용 문장:

- **GUIDE** — `Bibimbap is a colorful bowl of warm rice topped with seasoned vegetables, meat, and a fried egg.`
- **CAUTION** — `Careful, this one's spicy! Duck-bok-kee is chewy rice cakes simmered in a thick, spicy chili sauce.`

**결론**: 두 스타일 모두 성공 기준(≥85%)을 크게 상회했고, 우리 모델이 오히려 높게 채점됐다(104~107%).

> ⚠️ **"이겼다"고 단정하지 말 것 — 한계 두 가지**
> 1. 스타일당 문장 1개(n=1)라 통계적으로 유의미하다고 보기 어렵다. 6-2절과 같은 76문장 규모로 확대 재평가가 필요하다(7절).
> 2. CAUTION 문장이 **리스펠링 표기(`Duck-bok-kee`)** 를 쓰고 있다. 현행은 한글 표기(`떡볶이`)이므로 재평가 시 문장 세트부터 갱신해야 한다.
>
> 원본 오디오 4개(ours/perso × guide/caution)는 [`eval/perso_comparison/`](./perso_comparison/)에 보관.

---

## 7. 체크리스트

### 완료

- [x] **하이퍼파라미터 탐색** — LR·rank 5개 조합 + 100에폭 연장으로 데이터 규모가 상한임을 확인 (3절, 근거 `eval/training_log.csv`)
- [x] **`instruct` 톤 구분 적용** — 문구 확정 및 `INSTRUCT_MAP` 반영 (5절)
- [x] **instruct를 학습에도 반영** — 9차 재학습으로 학습·추론 조건 일치 (3·5절)
- [x] **1차 자동 평가 (UTMOS22)** — 오디오 76개 채점 완료 (6-2절) · ⚠️ 3차 체크포인트 · scale 0.3 · 리스펠링 기준이라 **현행과 조건 불일치**
- [x] **Perso.ai UTMOS 비교 (1차)** — 스타일당 1문장, 두 스타일 다 기준(≥85%) 상회 (6-4절)
- [x] **음식명 표기 방식 전환 결정** — 리스펠링 폐기 → 한글 표기, 치환 위치를 `narration.py`로 이동 (4절)

### 배포 전 필수 (블로킹)

- [ ] **한글 표기 청취 검증 (50개)** — 4-1절이 "한글 병기"를 실패로 기록해뒀다. 현행 방식(이름 자체를 한글로 대체)은 조건이 다르지만, GPU 환경에서 직접 들어보기 전까지 확정이 아니다. 결과에 따라 4-3절을 갱신한다
- [ ] **`LORA_SCALE` 0.15 청취 확인** — 톤 구분이 실제로 복구됐는지, 음색·발화 안정성이 유지되는지 (5절)
- [x] **TTS 캐시를 한글 표기본으로 교체** (2026-08-27) — `src/pipeline.py`가 캐시를 먼저 조회하므로 낡은 wav를 두면 코드를 바꿔도 사용자에게는 아무것도 바뀌지 않는다. 다시 생성(`--force`)하는 대신 배포 Space `HJU5022/K_Menu`(커밋 `d91f637` 배포, 2026-08-26)에 이미 올라가 있던 한글 캐시 100개(나레이션 50 + 이름 50)를 받아 덮어썼다 — sha256 100/100 일치, 표본 3개를 Whisper large-v3로 전사해 이름이 한글로 읽히는 것 확인. 사람 청취 검증은 위 두 항목이 정본이다

### 평가 (미완료)

- [x] **현행 설정 기준 UTMOS 측정** (2026-08-27, 재현 확인 08-28) — 9차 `epoch-31` · `LORA_SCALE` 0.15 · **한글 표기** 조건의 배포 캐시 나레이션 **50개**를 채점했다. 결과는 6절 머리, 원본은 `eval/tts_quality/deployed.csv`. ⚠️ 단 6-2절의 76개 비교표를 현행 조건으로 다시 채운 것은 아니다 — 그 표의 뼈대인 리스펠링 전/후 비교는 표기 방식이 한글로 바뀌면서 현행과 무관해졌다(6-2절 한계 3)
- [ ] **Perso.ai UTMOS 비교 (정식, 76문장)** — 6-4절은 n=1 1차 결과일 뿐. 문장 세트도 한글 표기로 갱신해야 한다
- [ ] **MOS 정식 평가 (사람 평가자)** — 외부 평가자 5명, 블라인드 A/B(베이스 vs 파인튜닝, 순서 랜덤화), 발음 정확도·자연스러움 각 1~5점 척도(ITU-T P.800). 기획서 AC5 요구사항(발음 0.4점 이상 향상, 스타일 구분률 85% 이상). 자동 평가는 이를 대체하지 않는다
  - 진행 상황: **0/5명.** 오래 "평가자 2/5명"이라고 적어왔으나 그 채점 원본이 남아 있지 않다. 내부 예비 채점은 접고 **5명을 새로 받는다.** 사람 평가로 현재 가진 것은 외부 3명 참고 측정([`eval/user_test/`](./user_test/))뿐이다
  - 절차: ① UTMOS 자동 채점 → ② 외부 평가자 직접 청취 검증

### 기록·재현성 (미완료)

- [x] **9차 학습 로그를 `eval/training_log.csv`에 추가** — 2026-08-28 완료. 40에폭 전체가 들어왔다 (min 8.8919 `ep31` / final 8.9163 `ep39` / 1,399.2초)
- [ ] **9차 학습 노트북 확보** — `eval/qwen3_tts_lora_final.ipynb`는 8차(`final_respelled`) 기준이라 배포 체크포인트를 재현하지 못한다. instruct 학습을 반영한 `dataset.py` / `sft_12hz_lora.py` 수정본도 함께 남긴다

### 개선 후보 (선택)

- [ ] **CAUTION 클래스 실제 녹음 추가** — 현재는 `instruct`로 우회 중이나(5절), 8%라는 클래스 불균형 자체를 메우는 것은 여전히 유효한 방향
- [ ] **학습 데이터 규모 확대** — 348개가 성능 상한이라는 것이 7차의 결론(3절). 하이퍼파라미터로는 더 나아가지 못한다
- ~~UTMOS 하락폭 큰 5개 음식 리스펠링 표기 재검토~~ — **취소.** 리스펠링 방식 자체가 폐기되어 무효해졌다(4-2절)

---

## 8. 산출물

| 산출물 | 위치 | 비고 |
|---|---|---|
| **모델 (LoRA 어댑터)** | [k-bite-team/k-menu-qwen3-tts-lora](https://huggingface.co/k-bite-team/k-menu-qwen3-tts-lora) (2026-10-20 개인 계정 `hajeongun/k-menu-qwen3-tts-lora`로 그대로 복사) | `README.md` 포함. 배포는 `checkpoint-epoch-31` |
| **추론 코드** | [`src/tts/infer.py`](../src/tts/infer.py) | `synthesize(text, style)` — `pipeline.py`가 호출. `INSTRUCT_MAP` · `LORA_SCALE` · `_trim_silence()`가 여기 있다 |
| **표기 치환** | [`src/text_gen/narration.py`](../src/text_gen/narration.py) | `_to_tts_text()` — **TTS 모듈이 아니다.** 이유는 4-3절 |
| **사전 생성 (Plan B)** | [`src/tts/pregenerate.py`](../src/tts/pregenerate.py) | 배치 생성 + RTF 로그 |
| **학습 노트북** | [`eval/qwen3_tts_lora_final.ipynb`](./qwen3_tts_lora_final.ipynb) | ⚠️ **8차 기준** — 배포(9차) 재현 불가 |
| **학습 로그** | [`eval/training_log.csv`](./training_log.csv) | **3~9차 7개 run** (1·2차는 로깅 이전) |
| **Perso.ai 비교 오디오** | [`eval/perso_comparison/`](./perso_comparison/) | ours/perso × guide/caution 4개 |
| **UTMOS·WER 측정 (현행 배포)** | [`eval/tts_quality/deployed.csv`](./tts_quality/deployed.csv) | 배포 캐시 50개 채점 — 6절 머리의 근거. 스크립트는 [`eval/measure_tts_quality.py`](./measure_tts_quality.py) |
| **UTMOS 채점 원본 (과거 76개)** | `utmos_results.csv` | ⚠️ **저장소에 없다** — Colab Drive `work/utmos_results.csv` |
| **사람 평가 원본** | [`eval/user_test/`](./user_test/) | 외부 3명 참고 측정(2026-08-29). ⚠️ 정식 MOS(5명 블라인드 A/B) 원본은 **없다 — 미실시** |

> **초기에 만들었다가 통합한 것**: 별도 `inference.py`를 뒀다가, `src/tts/infer.py`의 스피커 config ·
> embedding · LoRA scale 로직과 중복되는 데다 파이프라인에 연결되지도 않아 `infer.py`로 합쳤다.

### 관련 문서

| 문서 | 내용 |
|---|---|
| [`docs/specs/tts-finetuning.md`](../docs/specs/tts-finetuning.md) | Spec + 구현 변경 이력 (표기 전환 · `PRONUNCIATION_TTS` · Plan B 전환의 1차 출처) |
| [`eval/model_comparison.md`](./model_comparison.md) | OCR · TTS 후보군 · Perso.ai · Plan B 판단 종합 |
| [`src/tts/README.md`](../src/tts/README.md) | 런타임 코드 구조, 별도 프로세스(`worker.py`)를 쓰는 이유 |
