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
| `vendor/ppocr/` | PaddleOCR 저장소의 내부 코드 일부(Apache-2.0)를 그대로 가져온 것. `infer.py`가 recognition 모델을 export 없이 직접 불러오는 데 씀 — 이유는 아래 "왜 vendor 코드가 있나" 참고. 직접 수정하지 말 것(원본 유지, 딱 한 줄만 우리가 안 쓰는 기능 때문에 지웠음: `data/imaug/__init__.py`의 `CopyPaste` import) |

## 흐름

```
이미지 → preprocess → infer(글자 추출) → match(음식명 확정) → 후보 목록
```

`match.py`의 `scan_menu_lines()`는 메뉴판을 줄 단위로 훑습니다. 이름이 닮은 정도로만
걸린 후보(메뉴판 `콩물국수` → 등록 `콩국수`)는 글자로 위치를 못 찾아 사진 상자와 가격을
잃는데, `_fill_missing_from_row()`가 그 줄에서 채웁니다. 가격은 줄에 값이 하나이고
후보도 하나일 때만 채웁니다 — 자세한 이유는 `docs/specs/ocr-candidate-results.md`의
EC-06 참고.

줄을 나누는 기준은 `infer.py`의 `group_boxes_into_row_groups()`이고, 같은 줄로 볼 세로
중심 허용 오차는 **상자 높이의 중앙값**에 겁니다. 작은 첨자(`(2인기준)`)가 줄을 먼저 열어도
그 메뉴의 가격 상자가 아래 줄로 밀려나지 않게 하려는 것입니다 — 밀려나면 그 자리에 옆 칸
메뉴의 가격이 붙습니다.

`prepare_dataset.py`와 `finetune.py`는 **학습할 때만** 씁니다. 배포 경로에는 들어가지 않습니다.

## 왜 vendor 코드가 있나

`infer.py`는 원래 계획대로면 PaddleOCR의 "export"(학습 체크포인트 → 배포용 정적 그래프 변환) 기능으로 만든 파일을 `PaddleOCR()` 고수준 API로 불러오는 단순한 코드였을 것입니다. 근데 이 모델 구조(`korean_PP-OCRv5_mobile_rec`, PPLCNetV3+MultiHead)에서 export 기능 자체가 PaddleOCR/PaddleX 양쪽 다, Paddle 여러 버전에서 재현되는 버그가 있어서(설정 파일만 만들어지고 실제 가중치 파일이 안 만들어짐) 이 경로를 포기하고, 원본 학습 체크포인트를 PaddleOCR 저장소의 내부 코드로 직접 불러오는 방식으로 바꿨습니다. 자세한 경위와 시도했던 것들은 `docs/specs/ocr-finetuning.md`의 "구현 변경 이력" 참고.

## 관련 문서

- Spec: [`docs/specs/ocr-finetuning.md`](../../docs/specs/ocr-finetuning.md)
- 데이터 준비: [`data/README.md`](../../data/README.md)
