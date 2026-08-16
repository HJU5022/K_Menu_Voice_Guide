# src/ocr/

**이미지 ──▶ 음식 후보 목록**

메뉴판 사진에서 한국어 글자를 뽑아내고, 등록된 음식명 50개 중 무엇인지 맞춥니다.

## 파일

| 파일 | 역할 |
|---|---|
| `preprocess.py` | OpenCV로 회전·대비·크기 보정 |
| `prepare_dataset.py` | AI Hub 라벨 → PaddleOCR 학습 포맷 + 커스텀 딕셔너리 생성 |
| `finetune.py` | 학습 (1안 전체학습 / 2안 LoRA·QLoRA / 3안 mobile+양자화) |
| `infer.py` | 추론 — 파인튜닝 모델로 한국어 글자 추출 |
| `match.py` | RapidFuzz로 등록 음식명 50개와 유사도 매칭 |

## 흐름

```
이미지 → preprocess → infer(글자 추출) → match(음식명 확정) → 후보 목록
```

`prepare_dataset.py`와 `finetune.py`는 **학습할 때만** 씁니다. 배포 경로에는 들어가지 않습니다.

## 관련 문서

- Spec: [`docs/specs/ocr-finetuning.md`](../../docs/specs/ocr-finetuning.md)
- 데이터 준비: [`data/README.md`](../../data/README.md)
