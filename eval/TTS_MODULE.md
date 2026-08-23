# K-Menu Voice Guide — TTS 모듈 (Qwen3-TTS 1.7B LoRA)

담당: TTS 파트
베이스 모델: `Qwen/Qwen3-TTS-12Hz-1.7B-Base`
최종 배포: [huggingface.co/k-bite-team/k-menu-qwen3-tts-lora](https://huggingface.co/k-bite-team/k-menu-qwen3-tts-lora)

---

## 1. 개요

기획서(SDD MVP v3)의 Qwen3-TTS는 최초 기술검증 단계에서 LoRA/PEFT 파인튜닝 공식 미지원으로 확인되어 후보에서 제외되었으나, 실제로는 검증된 비공식 커뮤니티 LoRA 패치([instavar/qwen3-tts-lora-finetuning](https://github.com/instavar/qwen3-tts-lora-finetuning))가 존재함을 확인하고, 이를 기반으로 파인튜닝을 재개하여 최종적으로 채택했다.

핵심 목표 두 가지:
1. 영어 문장 속 한국 음식명 발음 정확도 향상
2. GUIDE(안내)/CAUTION(경고) 스타일 톤 구분

---

## 2. 학습 환경 및 파이프라인

- 실행 환경: Google Colab (A100)
- 베이스 모델: `Qwen/Qwen3-TTS-12Hz-1.7B-Base`
- 파인튜닝 방식: LoRA (target modules: `q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj` — 어텐션+FFN 전체)
- 학습 데이터: 나레이션(실제 녹음) 50개 + 발음용 캐리어 문장(실제 녹음) 250개, 총 300개 원본 샘플
- 데이터 분할: 80/10/10 (food_id × style 기준 층화 분할)
- 오디오 스펙: 24kHz mono WAV로 통일 (코덱 파이프라인 요구사항)

### 공식/커뮤니티 스크립트에서 발견 및 패치한 버그 (총 6건)

| # | 버그 | 증상 | 조치 |
|---|---|---|---|
| 1 | `Accelerator`에 `project_dir` 누락 | tensorboard 로깅 시 `ValueError` | `project_dir=args.output_model_path` 추가 |
| 2 | `infer_lora_custom_voice.py`에 `main()` 호출 누락 | 추론 스크립트가 아무것도 안 하고 종료 | 파일 끝에 `main()` 호출 추가 |
| 3 | `torchao` 버전 비호환 | PEFT LoRA 적용 시 `ImportError` | `pip install -U torchao` |
| 4 | 기본 `attn_implementation=flash_attention_2` | flash-attn 미설치 환경에서 로드 실패 | `sdpa`로 고정 |
| 5 | 체크포인트 저장 시 모델 경로를 상대경로로 가정 | `config.json` 복사 시 `FileNotFoundError` | 베이스 모델을 로컬에 사전 다운로드 |
| 6 | `ref_audio` 스타일별 분리 시 `collate_fn`이 동일 길이 전제 | 배치 처리 중 `RuntimeError` (텐서 크기 불일치) | 전 샘플 `ref_audio`를 동일 클립으로 통일 |

---

## 3. 파인튜닝 차수별 실측값

원 계획(Qwen3-TTS Low/Mid 구간 기준선)이 아니라, 실제 스크리닝 결과 XTTS-v2·F5-TTS로 전환했던 기획서 v3 시점 이후 — 비공식 LoRA 경로 확인 후 Qwen3-TTS 자체를 재검증하여 아래와 같이 진행했다.

| 차수 | run_id | LR | rank | epoch | batch | min Val Loss (epoch) | final Val Loss (epoch) | 학습 시간 | 비고 |
|---|---|---|---|---|---|---|---|---|---|
| 1차 (베이스라인) | *(초기 10ep 실험)* | 2e-6 (기본값) | 16 | 10 | 4 | ~10.87 (ep9) | ~10.87 (ep9) | - | 최초 성공 학습 확인용 |
| 2차 (에폭 확장) | *(초기 40ep 실험)* | 2e-6 (기본값) | 16 | 40 | 4 | ~8.998 (ep39) | ~8.998 (ep39) | - | 낮은 LR로도 에폭 늘리면 개선됨을 확인, 그러나 여전히 완만한 하강 |
| 3차 | `lr5e-6_ep40` | 5e-6 | 16 | 40 | 4 | 8.8902 (ep33) | 8.9129 (ep39) | 1367.6초 | LR 2.5배 상향, **최종 안정적 하이퍼파라미터로 채택** |
| 4차 | `lr1e-5_ep40` | 1e-5 | 16 | 40 | 4 | 8.8808 (ep17) | 9.5494 (ep39) | 1371.3초 | 최저점은 3차보다 낮으나, 이후 발산(overfitting) — 최종 채택에서 제외 |
| 5차 | `lr2e-5_ep40` | 2e-5 | 16 | 40 | 4 | 8.8628 (ep9) | 10.2733 (ep39) | 1359.1초 | 공식 스크립트 원래 기본 LR, 가장 이른 최저점 후 가장 크게 발산 — 불안정성 확인, 채택 제외 |
| 6차 | `lr5e-6_r32_ep40` | 5e-6 | 32 | 40 | 4 | 8.8816 (ep21) | 9.1858 (ep39) | 1384.1초 | LoRA rank 2배 확장(용량 테스트), 최저점 개선 미미(0.01 미만) + 불안정성 증가 → **rank 확장 무효과 확인, rank=16 유지 결정** |
| 7차 | `lr5e-6_ep100` | 5e-6 | 16 | 100 | 4 | 8.8888 (ep32) | 10.3887 (ep99) | 3412.4초 | 3차 설정을 100에폭까지 연장. **epoch 25~40 구간은 8.89~8.92대 평탄(바닥), epoch 41부터 스파이크 없이 완만·지속적으로 상승(전형적 과적합 곡선)해 epoch 99에 10.39까지 도달.** 데이터셋 규모(348개, 오버샘플 포함) 자체가 성능 상한을 결정한다는 결론의 핵심 근거 |
| 8차 (최종) | `final_respelled_lr5e-6_ep40` | 5e-6 | 16 | 40 | 4 | 8.8875 (ep31) | 8.9122 (ep39) | 1414.9초 | 3차와 동일 하이퍼파라미터 + **리스펠링 21개 반영된 학습 텍스트**로 재학습. 최종 배포 버전 |

**하이퍼파라미터 탐색 결론**: LR·rank를 5개 조합으로 실험한 결과 최저 Val Loss는 8.86~8.89 범위에 공통적으로 수렴했으며(차이 0.03 이내), 100에폭까지 연장해도 동일 지점에서 벽에 부딪힘을 확인(7차). 이는 최적화(하이퍼파라미터) 문제가 아니라 학습 데이터 규모(348개, CAUTION 클래스 오버샘플링 포함)의 근본적 한계로 판단, 추가 탐색보다 데이터 품질 개선(리스펠링, 후술) 방향으로 전환했다.

> **참고**: 8차(최종) 체크포인트는 epoch 39를 사용 중이나, Val Loss 최저점은 epoch 31(8.8875)이었음 (차이 0.0247, 미미). 필요 시 `checkpoint-epoch-31`로 교체 검토 가능.

---

## 4. 발음 개선 — 음식명 리스펠링

### 시도했으나 실패한 접근

| 접근 | 결과 |
|---|---|
| IPA 발음기호를 텍스트에 직접 입력 | 모델이 IPA 기호를 일반 문자처럼 그대로 읽어버림 (부자연스러운 발화) |
| 영어 문장 중간에 한글 삽입 (`"...called 떡볶이 (tteokbokki)."`) | 결과가 부자연스럽게 나옴 (코드스위칭 미지원 또는 파인튜닝으로 한국어 능력 저하 추정) |
| 공식 phoneme/음소 입력 API | Qwen3-TTS 공식 문서([mintlify 문서](https://qwenlm-qwen3-tts.mintlify.app/)) 확인 결과 별도 음소 입력 채널 없음 (`generate_custom_voice`는 `text` 파라미터만 지원) |

### 채택한 방법: 영문 알파벳 리스펠링

음식명을 영어 알파벳만으로 다시 표기(예: `Tteokbokki` → `Duck-bok-kee`)하여, 모델이 이미 보유한 영어 읽기 능력을 통해 더 정확한 발음을 유도. 학습 완료된 어댑터(파인튜닝 전이 아닌, 이미 파인튜닝된 화자 목소리 기준)로 원본 표기 vs 리스펠링 표기를 각각 생성해 청취 비교하는 방식으로 전체 음식 스크리닝 진행.

**스크리닝 결과**: 전체 50개 음식 중 **21개는 리스펠링 필요, 29개는 원본 표기가 이미 적절**함을 확인.

| 원본 표기 | 리스펠링 |
|---|---|
| Tteokbokki | Duck-bok-kee |
| Bibimbap | Bee-bim-bahp |
| Nakji Bokkeum | Nahk-jee Boh-kum |
| Agujjim | Ah-goo-jim |
| Maeuntang | May-oon-tang |
| Bibim Naengmyeon | Bee-bim Nang-myun |
| Cheonggukjang | Chung-gook-jang |
| Doenjang Jjigae | Dwen-jang Jee-geh |
| Dongtae Jjigae | Dong-teh Jee-geh |
| Dubu Kimchi | Doo-boo Kim-chee |
| Jeyuk Bokkeum | Jeh-yook Bok-kum |
| Kimchi Bokkeumbap | Kim-chee Bok-kum-bap |
| Kimchi Jjigae | Kim-chee Jee-geh |
| Kongguksu | Kong-gook-soo |
| Mulhoe | Mul-hweh |
| Ojingeo Bokkeum | Oh-jing-uh Bok-kum |
| Sundae | Soon-deh |
| Sundubu Jjigae | Soon-doo-boo Jee-geh |
| Tteokgalbi | Duck-gal-bee |
| Tteokguk | Duck-gook |
| Yukhoe | Yook-hweh |

(나머지 29개는 원본 로마자 표기 그대로 사용 — Bulgogi, Samgyeopsal 등 청취 테스트로 원본이 이미 정확함을 확인)

**적용 방식**: 화면에 표시되는 텍스트(`narration_text`)는 원본 로마자 표기를 그대로 유지하고, TTS 입력 시에만 위 표를 적용해 치환한다. 8차(최종) 재학습부터는 이 치환된 텍스트를 학습 데이터 라벨에도 반영하여, 모델이 리스펠링 표기 자체를 정확히 발음하도록 직접 학습시켰다.

**한계**: 한국어 된소리(ㄸ,ㅃ,ㄲ,ㅆ,ㅉ)는 영어 알파벳 표기 체계에 대응 신호가 없어 완벽히 재현 불가능함을 확인(예: "Tteokbokki"의 "Tt"를 그대로 둬도 실제 된소리가 나지 않음). 근사치로 타협.

**추가 한계 (UTMOS 자동 평가로 확인, 6-2절 참고)**: 리스펠링은 발음 정확성을 높이지만 일부 음식에서 발화 자연스러움(UTMOS)이 오히려 하락하는 트레이드오프가 관찰됨. 아래 5개는 하락폭이 유난히 커서 표기 재검토 후보:

| 음식 | UTMOS 변화 |
|---|---|
| Doenjang Jjigae | -0.64 |
| Ojingeo Bokkeum | -0.60 |
| Dongtae Jjigae | -0.48 |
| Sundae | -0.39 |
| Bibim Naengmyeon | -0.30 |

---

## 5. 톤 구분 — GUIDE/CAUTION (`instruct` 파라미터)

### 배경 문제

학습 데이터의 CAUTION 클래스가 전체의 8%(50개 중 4개 음식)에 불과해, 하이퍼파라미터를 5개 조합으로 실험해도(3~7차, 4절 참고) 톤 구분 학습 자체가 근본적으로 개선되지 않았다.

### 해결: `instruct` 파라미터 발견 및 적용

Qwen3-TTS 공식 문서 조사 중 `generate_custom_voice()`에 자연어로 톤/감정을 직접 지시하는 `instruct` 파라미터가 있음을 확인. 사용 중이던 커뮤니티 추론 스크립트에는 이 파라미터가 연결돼 있지 않아 직접 패치(`infer_lora_custom_voice.py`, `run_lora_infer.sh`)하여 사용 가능하도록 했다.

**중요**: 이 방식은 **재학습 없이 기존 체크포인트에서 즉시 적용됨**을 확인 — 학습 데이터 부족 문제를 추론 시점 트릭으로 우회한 것이다.

### 확정된 instruct 문구

강도 단계별 비교 청취(약함→중간→강함→극단 4단계) 및 언어 비교(영어 vs 중국어, 영어가 더 명확함을 확인) 테스트를 거쳐 확정:

| 스타일 | instruct 문구 |
|---|---|
| GUIDE | `Speak in a calm, informative tone, like a knowledgeable guide explaining something interesting. Keep a natural, steady pace, not slow.` |
| CAUTION | `Say it in an urgent, warning tone, as if cautioning someone.` |

---

## 6. 기존 모델 대비 비교 평가

### 6-1. 정량 지표 (Val Loss, 8차 최종 기준)

| 지표 | 1차(베이스라인, LR 기본값 2e-6, 10ep) | 8차(최종) |
|---|---|---|
| Val Loss | ~10.87 | 8.9122 |
| 개선폭 | - | -1.96 (약 18% 감소) |

### 6-2. 1차 자동 평가 (UTMOS, library 기반 no-reference MOS 예측)

외부 평가자 확보 전, **자동 MOS 예측 모델([UTMOS22](https://github.com/tarepan/SpeechMOS), `utmos22_strong`)**로 예비 정량 평가를 진행했다. 사람 평가자 없이 오디오 자체의 자연스러움(naturalness)을 1~5점으로 예측하는 모델이며, 실제 오디오 76개(하이퍼파라미터 실험 12개 + 리스펠링 전/후 32개 + 원본유지 27개)에 대해 채점했다.

**평가 기준 (에폭·가중치 명시)**:

| 평가 대상 | 사용 체크포인트 | lora_scale |
|---|---|---|
| 하이퍼파라미터 실험 12개 (3~7차) | 각 run의 **마지막 에폭** 체크포인트 (3~6차: epoch 39 / 7차 `lr5e-6_ep100`: **epoch 99**, 발산 이후 지점이므로 해당 실험 점수는 최선 상태가 아님에 유의) | 0.3 |
| 리스펠링 전/후 32개, 원본유지 27개 (food_screen) | `lr5e-6_ep40` (3차) **checkpoint-epoch-39** — **8차(최종) 리스펠링 반영 재학습 이전 모델** | 0.3 |

> ⚠️ food_screen 평가는 리스펠링 텍스트가 학습에 반영되기 *전* 모델(3차) 기준이다. 즉 "베이스 모델의 일반화 능력만으로 리스펠링 텍스트를 얼마나 잘 읽는지"를 측정한 것이며, 실제 배포된 8차(최종) 모델은 리스펠링 텍스트로 추가 학습되었으므로 이 결과보다 더 나을 가능성이 있다. 8차 모델 기준 재평가는 TODO(7절).

| 구분 | n | 평균 UTMOS | min | max |
|---|---|---|---|---|
| 하이퍼파라미터 실험 12개 (3~7차 GUIDE/CAUTION) | 12 | 4.0124 | 3.7233 | 4.3066 |
| 리스펠링 적용 전 (16개 음식) | 16 | 3.9618 | 3.5018 | 4.3395 |
| 리스펠링 적용 후 (16개 음식) | 16 | 3.9224 | 3.1438 | 4.2347 |
| 리스펠링 불필요 판정 (27개 음식, 원본 유지) | 27 | 4.0659 | 3.3459 | 4.3316 |

**주요 발견 — 리스펠링 전/후 UTMOS는 평균 -0.0393 (16개 중 8개만 개선)**:

이는 리스펠링이 "틀렸다"는 뜻이 아니라, **UTMOS가 측정하는 축(발화의 일반적 자연스러움)과 리스펠링이 개선하려는 축(한국 음식명 발음의 정확성)이 서로 다르기 때문**으로 해석한다. UTMOS는 해당 단어가 무엇을 뜻하는지, "올바른" 목표 발음이 무엇인지 알지 못하며, 리스펠링 표기(하이픈으로 음절을 강제 분리하는 방식)가 일부 경우 발화를 더 정확하게 만드는 대신 약간의 유창함을 희생시키는 트레이드오프로 나타난 것으로 판단한다. (하락폭이 큰 5개 사례는 4절에 정리, 표기 재검토 후보로 남김)

> ⚠️ 하이퍼파라미터 실험 12개(설정당 GUIDE/CAUTION 각 1개, n=1) 비교는 표본이 매우 작아 참고용으로만 사용한다. 3절의 Val Loss 기반 결론(수십 에폭 전체 궤적 기준, 8개 실험)이 더 신뢰도 높은 근거다.

원본 데이터: `training_log.csv`와 동일 위치의 `utmos_results.csv` (Drive: `work/utmos_results.csv`)

### 6-3. 정성 평가 (팀 내부 청취, 비공식)

> ⚠️ 아래는 정식 MOS 평가가 아닌 팀 내부 청취 기준 판단이며, 정식 수치는 7절 TODO 참고.

- **발음**: 리스펠링 미적용 시 다수 음식명이 부정확하게 발화됨(예: Tteokbokki를 영어 단어처럼 읽음). 리스펠링 적용 후 21개 음식에서 확연한 개선 확인(청취 기준 — UTMOS 기준으로는 6-2절 참고, 자연스러움과는 다른 축의 평가임에 유의).
- **톤 구분**: `instruct` 미적용 시 GUIDE/CAUTION 간 청각적 차이 거의 없음. `instruct` 적용 후 CAUTION 발화에서 속도·긴장감 차이가 뚜렷하게 감지됨.
- **Perso.ai 비교**: 1차 결과 확보 완료 (6-4절 참고). 76개 문장 전체로 확대한 정식 재평가는 여전히 TODO(7절).

### 6-4. Perso.ai 비교 (1차, 2026-08-21)

`src/tts/perso_client.py`로 Perso.ai Speech API(voice cloning) 연동. 같은 나레이션 화자(`제발.zip` 나레이션 샘플 5개, 화자 본인 동의 확인; 공개용 문서 예시는 `docs/legal/tts-voice-consent/` 참고)로 Perso.ai 쪽 voice를 클로닝(`voice_id: psv-5fb5f0ee151cce710625a02fd6578184`)해서, 같은 문장을 우리 파인튜닝 모델(instruct-trained epoch-31)과 Perso.ai 양쪽에 넣어 UTMOS22로 채점.

| 스타일 | 문장 | 우리 모델 UTMOS | Perso.ai UTMOS | 비율 (기준 ≥85%) |
|---|---|---|---|---|
| GUIDE | "Bibimbap is a colorful bowl of warm rice topped with seasoned vegetables, meat, and a fried egg." | 4.2916 | 4.1135 | **104.3%** ✅ |
| CAUTION | "Careful, this one's spicy! Duck-bok-kee is chewy rice cakes simmered in a thick, spicy chili sauce." | 4.4408 | 4.1556 | **106.9%** ✅ |

**결론**: 두 스타일 모두 성공 기준(≥85%)을 크게 상회, 우리 모델이 Perso.ai보다 오히려 높게 채점됨(104~107%).

> ⚠️ **한계 — 이걸로 "이겼다"고 단정하지 말 것**: 스타일당 문장 1개(n=1)뿐이라 통계적으로 유의미하다고 보기 어렵다. 6-2절 기존 평가(76개)와 동일 규모로 확대 재평가가 필요하다(7절 TODO). 원본 오디오 4개(ours/perso × guide/caution)는 `eval/perso_comparison/`에 보관.

---

## 7. TODO (정식 평가 미완료 항목)

- [x] **1차 자동 평가 (library 기반 MOS)**: UTMOS22로 오디오 76개 채점 완료 (6-2절, 사용 체크포인트·lora_scale 명시)
- [ ] **8차(최종, 리스펠링 반영) 모델 기준 UTMOS 재평가**: 6-2절 food_screen 평가는 3차(리스펠링 학습 반영 전) 모델 기준이었음 — 8차 모델로 동일 76개 재채점 필요
- [x] **Perso.ai UTMOS 비교 (1차)**: 스타일당 1문장씩 비교 완료, 두 스타일 다 성공 기준(≥85%) 상회 (6-4절 참고)
- [ ] **Perso.ai UTMOS 비교 (정식, 76문장 확대)**: 6-4절은 n=1짜리 1차 결과일 뿐 — 6-2절과 동일한 76개 문장 세트로 재평가 필요
- [ ] **MOS 정식 평가 (사람 평가자)**: 외부 평가자 5명 확보, 블라인드 A/B(기본 모델 vs 파인튜닝 모델, 순서 랜덤화), 발음 정확도·자연스러움 각 1~5점 척도(ITU-T P.800 기준) — 기획서 AC5 요구사항(발음 0.4점 이상 향상, 스타일 구분률 85% 이상). 1차 자동 평가는 이를 대체하지 않음. **평가 절차: ① UTMOS 자동 채점 → ② 사용자(외부 평가자) 직접 청취 검증 순으로 진행**
- [ ] CAUTION 클래스 실제 녹음 추가 검토 (현재는 `instruct`로 우회, 데이터 자체 보강은 여전히 유효한 개선 방향)
- [ ] UTMOS 하락폭 큰 5개 음식(4절) 리스펠링 표기 재검토

---

## 8. 최종 산출물

- **모델**: [huggingface.co/k-bite-team/k-menu-qwen3-tts-lora](https://huggingface.co/k-bite-team/k-menu-qwen3-tts-lora) (LoRA 어댑터, `README.md` 포함)
- **학습 노트북**: `qwen3_tts_lora_final.ipynb` (환경설정→데이터빌드→학습→instruct 데모→업로드, 재실행 안전)
- **프로덕션 연결**: `src/tts/infer.py`의 `synthesize(text, style)` — `pipeline.py`가 실제로 호출하는 함수. 리스펠링(`apply_respelling`)·instruct(`INSTRUCT_MAP`)가 여기 직접 반영되어 있어 별도 통합 함수/파일이 필요 없음 (초기에 별도 `inference.py`로 만들었다가, 기존 `src/tts/infer.py`의 스피커 config/embedding/LoRA scale 로직과 중복·미연결 문제가 있어 통합함)
- **학습 로그**: `training_log.csv` (8개 실험, 에폭별 Val Loss 전체 기록)
- **1차 자동 평가 로그**: `utmos_results.csv` (오디오 76개 UTMOS 채점 결과)
