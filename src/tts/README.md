# src/tts/

**(내레이션 텍스트 + 스타일) ──▶ WAV**

내레이션 문장을 음성으로 만듭니다. `style`(GUIDE/CAUTION)에 따라 톤이 달라집니다.

## 파일

| 파일 | 역할 | 배포에 쓰임? |
|---|---|---|
| `finetune.py` | LoRA/PEFT 파인튜닝 | ✗ 학습 시에만 |
| `infer.py` | 추론 — **기본 경로(라이브 생성)** | ✓ |
| `worker.py` | `infer.py`를 별도 프로세스에서 실행하는 진입점 | ✓ |
| `pregenerate.py` | Plan B — 조합 30~60개 사전 생성·캐싱 | △ 조건부 |
| `perso_client.py` | Perso.ai API 호출 — 비교 평가용 | ✗ 평가 시에만 |

## 기본 경로 vs Plan B — **Plan B로 전환 결정 (2026-08-21)**

원래 **기본**은 요청이 올 때마다 `infer.py`로 그 자리에서 음성을 만드는 라이브 생성이었고, TTFB(첫 소리가 나오기까지 걸리는 시간)가 목표를 넘으면 **Plan B**(사전 생성 캐싱)로 바꾸기로 되어 있었습니다.

**전환 기준과 실측 (2026-08-21, 원격 RTX 3080 Ti)**:

| 항목 | 값 |
|---|---|
| TTFB 목표 | 5~7초 |
| 라이브 생성 실측 — 콜드(모델 로딩 포함) | 61.3초 |
| 라이브 생성 실측 — 워밍업 후(상주 워커) | 약 33초 |

상주 워커 전환(PR #45)으로 요청당 90~160초 → 33초까지 줄였지만 목표(5~7초)에는 구조적으로 미달 → **Plan B 전환 결정.**

**Plan B 동작 방식**: `pregenerate.py`가 등록 음식 전체(50개 × 스타일)의 음성을 미리 생성해 `static/tts_cache/food_{id}_{STYLE}.wav`로 저장하고, `src/pipeline.py`가 요청 시 이 캐시를 먼저 조회합니다(캐시 히트 시 1초 미만). 캐시에 없는 조합만 라이브 생성으로 폴백합니다.

```
# 배치 실행 (서비스와 같은 환경에서, 저장소 루트 기준 — 약 30분)
python -m src.tts.pregenerate            # 없는 조합만 생성 (이어하기 안전)
python -m src.tts.pregenerate --force    # 전부 다시 생성
```

배치는 각 항목의 생성 시간·음성 길이로 **RTF**(생성 시간 ÷ 음성 길이)도 같이 계산해 `eval/tts_pregen_log.csv`에 남깁니다.

## `infer.py` 실제 모델 연결 (2026-08-18)

`infer.py`가 실제 모델(Qwen3-TTS 1.7B Base + LoRA 어댑터 `k-bite-team/k-menu-qwen3-tts-lora`)을 호출하도록 연결됨. TTS 파트의 실제 학습 노트북에서 확인한 추론 코드(`generate_custom_voice` + 스피커 등록 방식)를 그대로 옮겨서 짰음 — 처음엔 다른 방식(`generate_voice_clone`)으로 추측해서 짰다가 노트북 확보 후 전면 재작성함. 자세한 경위는 `infer.py` 파일 상단 docstring과 `docs/specs/tts-finetuning.md`의 "구현 변경 이력" 참고.

**GPU 검증 완료 (2026-08-20)**: 원격 데스크톱(RTX 3080 Ti)에서 실제로 실행해 WAV 생성까지 확인됨. 다만 요청마다 별도 프로세스를 새로 띄워 모델을 처음부터 로딩하기 때문에 **요청당 90~160초**가 걸린다 — 상주 프로세스로 바꾸는 것은 후속 작업으로 남아있다(GPU 성능 문제가 아니므로 장비 업그레이드로는 해결되지 않음).

## 왜 별도 프로세스(`worker.py`)로 실행하나

이 서비스는 같은 프로세스에서 PaddleOCR(paddle)도 로드한다. `paddleocr → paddlex → modelscope` 임포트 체인이 내부적으로 torch를 끌어오는데, paddle이 먼저 네이티브 DLL을 잡아둔 상태에서 torch를 로드하면 Windows에서 `shm.dll` 로딩이 깨진다(`OSError: [WinError 127]`).

그래서 `src/pipeline.py`는 TTS 추론을 `python -m src.tts.worker`라는 **완전히 별도인 자식 프로세스**에서 실행한다. 그 프로세스는 paddle을 전혀 임포트하지 않으므로 torch가 깨끗하게 로드된다. 텍스트·스타일을 stdin으로 넘기고 결과 JSON 한 줄을 stdout으로 받는 구조다.

## 고유명사 발음 교정 (G2P 오버라이드)

기존 edge-tts 학습 데이터로 파인튜닝한 결과, 불고기·냉면 같은 고유명사 발음이 약하게 나오는 문제가 있었습니다. 이를 아래 방식으로 교정합니다.

1. edge-tts SSML `<phoneme>` 태그로 고유명사 발음을 발음사전(G2P)으로 오버라이드해서 음성을 다시 생성
2. 교정된 음성 + 정답 텍스트를 쌍으로 라벨링
3. **기존 edge-tts 학습 데이터는 전량 폐기**하고 이 교정 데이터로 완전히 교체
4. `finetune.py`로 재학습

이번 교정은 **고유명사 발음만** 대상입니다. GUIDE/CAUTION 톤 구분 문제는 범위 밖이며 별도로 다룹니다.

검증은 MOS 같은 정량 채점이 아니라, 재학습 후 몇 개를 직접 들어보고 사람이 판단하는 방식입니다.

## Perso.ai는 왜 있나

우리 파인튜닝 모델이 상용 서비스 대비 어느 정도인지 재기 위한 **비교군**입니다. 같은 내레이션 텍스트를 양쪽에 넣고 MOS로 채점합니다. 결과는 `eval/`에 기록합니다.

## 관련 문서

- Spec: [`docs/specs/tts-finetuning.md`](../../docs/specs/tts-finetuning.md)
- **실험 기록 상세**: [`eval/TTS_MODULE.md`](../../eval/TTS_MODULE.md) — 하이퍼파라미터 8차 실험, 리스펠링 21개 목록, instruct 문구, UTMOS 평가
- 평가 결과: [`eval/model_comparison.md`](../../eval/model_comparison.md)
