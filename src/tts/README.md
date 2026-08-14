# src/tts/

**(내레이션 텍스트 + 스타일) ──▶ WAV**

내레이션 문장을 음성으로 만듭니다. `style`(GUIDE/CAUTION)에 따라 톤이 달라집니다.

## 파일

| 파일 | 역할 | 배포에 쓰임? |
|---|---|---|
| `finetune.py` | LoRA/PEFT 파인튜닝 | ✗ 학습 시에만 |
| `infer.py` | 추론 — **기본 경로(라이브 생성)** | ✓ |
| `pregenerate.py` | Plan B — 조합 30~60개 사전 생성·캐싱 | △ 조건부 |
| `perso_client.py` | Perso.ai API 호출 — 비교 평가용 | ✗ 평가 시에만 |

## 기본 경로 vs Plan B

**기본**은 요청이 올 때마다 `infer.py`로 그 자리에서 음성을 만듭니다(라이브 생성).

TTFB(첫 소리가 나오기까지 걸리는 시간)가 목표를 넘으면 **Plan B**로 바꿉니다. `pregenerate.py`로 나올 수 있는 조합 30~60개를 미리 다 만들어 저장해두고, 요청이 오면 꺼내 쓰기만 하는 방식입니다. 느린 대신 확실합니다.

전환 기준(TTFB 목표값)은 [`docs/specs/tts-finetuning.md`](../../docs/specs/tts-finetuning.md)에서 정합니다.

## Perso.ai는 왜 있나

우리 파인튜닝 모델이 상용 서비스 대비 어느 정도인지 재기 위한 **비교군**입니다. 같은 내레이션 텍스트를 양쪽에 넣고 MOS로 채점합니다. 결과는 `eval/`에 기록합니다.

## 관련 문서

- Spec: [`docs/specs/tts-finetuning.md`](../../docs/specs/tts-finetuning.md)
- 평가 결과: [`eval/model_comparison.md`](../../eval/model_comparison.md)
