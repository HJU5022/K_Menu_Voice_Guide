# Spec — OCR 파인튜닝

> **구현·배포 완료.** 다섯 섹션이 모두 채워져 있고, 아래 "구현 변경 이력"에 계획과 달라진 지점(export 경로 포기 → vendor 코드 직접 로딩)이 남아 있습니다. 실측 결과의 정본은 [`eval/model_comparison.md`](../../eval/model_comparison.md) 1절입니다.

## Why

- **페르소나**: 한국 음식에 익숙하지 않은 영어권 개별 외국인 관광객
- **상황**: 한국어로만 적힌 메뉴판을 촬영해 음식명을 인식시키려 한다.
- **문제**:
  1. 기본 PaddleOCR은 범용 한국어 인식 모델이라 메뉴판 특유의 서체·작은 글자·음식명 고유명사에 오인식이 잦다.
  2. 오인식된 글자로는 등록 음식명(RapidFuzz 매칭)과 제대로 이어지지 않아 다음 단계(텍스트·음성 안내)로 못 넘어간다.
- **측정 지표**: 기본 PaddleOCR 대비 한국어 음식명 인식률 +N%p (목표 수치는 Goal 참고)

## Goal

- **해결 목표**: 커스텀 딕셔너리로 파인튜닝한 PaddleOCR(mobile)로 메뉴판 음식명 인식률을 목표치까지 끌어올린다.
- **성공 기준**: `OCR_test_set_50`(별도 구성 테스트 50장) 기준 인식률 90% 이상
- **Out of Scope**: 손글씨 메뉴 인식, 실시간 동영상 OCR, 다국어 지원(영어권 메뉴판 외), paddleslim 양자화는 90% 인식률 확보 이후 배포 최적화 단계에서 별도로 진행(이 Spec의 AC 검증 대상 아님)

## What

**Happy Path**

1. AI Hub 데이터 → `prepare_dataset.py`로 PaddleOCR 학습 포맷(`rec_gt_train.txt`) 변환
2. 커스텀 딕셔너리 생성 (등록 음식명 50개 기준)
3. `finetune.py`로 학습
4. `infer.py`로 추론 → 한국어 글자 추출
5. `match.py`로 등록 음식명과 유사도 매칭

**Edge Cases** (최소 5개 + 처리 방식)

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | 메뉴판이 기울어져 촬영됨 | `preprocess.py`의 `_deskew`: Otsu 이진화 + `minAreaRect`로 회전각 추정 후 `warpAffine`으로 보정 |
| EC-02 | 조명이 어둡거나 반사됨 | `preprocess.py`의 `_enhance_contrast`: LAB 색공간에서 CLAHE 적용(`clipLimit=2.0`, `tileGridSize=8x8`) |
| EC-03 | 등록되지 않은 음식명이 인식됨 | `match.py`의 `name_score()`가 `MATCH_THRESHOLD`(현재 **85**) 미만 → 후보를 만들지 않음 → UI에 "미지원 안내" 표시 |
| EC-04 | 글자를 하나도 못 찾음 | OCR 결과 없음 → "조명·거리·각도 안내" 메시지와 함께 재촬영 요청 |
| EC-05 | 유사도가 비슷한 후보가 여러 개 | EC-03과 동일한 카드 UI 정책 재사용: 후보들을 번호+카드 목록으로 보여주고 사용자가 하나를 직접 선택 |

## How

**학습 방식 3안 — 전환 기준을 여기서 확정한다**

| 안 | 방식 | 선택 기준 |
|---|---|---|
| 1안 | 전체 학습 | 데이터 39,000장 규모로 대형 모델을 처음부터 학습시키면 과적합·학습 시간 부담 → 미선택 |
| 2안 | LoRA · QLoRA | PaddleOCR 인식 모델은 LoRA 적용 사례가 드물고, 이미 mobile 모델 자체가 경량이라 이득이 적음 → 미선택 |
| 3안 | mobile + 양자화(paddleslim) | **선택.** `korean_PP-OCRv5_mobile_rec` 사전학습 가중치로 전체 파인튜닝(현재 `finetune.py` 구현 상태) → 추론 시간·메모리 제약이 있는 Space 배포에 적합. *(2026-08-21 정정: 당시 전제였던 "HF Spaces **ZeroGPU**"는 폐기됐다 — ZeroGPU는 PyTorch 전용이라 PaddleOCR이 GPU를 쓸 수 없다. 실제 배포는 전용 GPU(T4 small) Docker Space다 — `docs/specs/fastapi-space-deploy.md`.)* 양자화는 파인튜닝 완료 후 순서대로 진행: ① 파인튜닝만으로 90% 인식률 확보 확인 → ② paddleslim으로 양자화 → ③ 양자화 후 재측정, 90% 밑으로 떨어지면 양자화 없는 mobile 가중치로 롤백 |

**학습 하이퍼파라미터 결정 경위** *(2026-08-21 정정: 실제로는 4차까지 진행됨. 아래 이전 표의 "1차"는 실제 3차, "2차"는 실제 4차)*

| 차수 | epoch | batch_size | 검증 정확도 | 기록 상태 |
|---|---|---|---|---|
| 1차 (스모크) | 3 | 1 | 86% | **기록 소실** — 체크포인트·로그·config 없음 |
| 2차 | 50 | 4 | 77% | **기록 소실** — 체크포인트·로그·config 없음 |
| 3차 | 10 | 4 | 90% 미만 | 문서 기록만 존재 (설정 파일·구체 수치 없음) |
| 4차 (최종 채택, 현재 배포본) | 20 | 8 (lr 0.001) | **90.98%** | 완비 — train.log · train_result.json · 설정 파일 3곳 일치 |

- **1·2차 소실 사유**: 로컬 ↔ 원격 환경 간 공유폴더 이동 중 폴더 오류로 값 분실. 이후 학습·측정 설정은 전부 저장소에 커밋하는 것으로 재발 방지 (1·2차의 정확도 수치는 담당자 기억 기준이며 원본 기록으로 확인 불가)
- **4차 학습 곡선 참고**: train.log상 ep1이 이미 acc 0.9093(이전 체크포인트 `pretrain_weight_path`에서 이어받음), ep4에 acc 0.0000 구간 후 복구, ep20 최종 0.9098(best) — 20에폭 학습 자체의 개선폭은 ep1 대비 +0.0005

- 학습 데이터 출처: AI Hub "관광 음식메뉴판 데이터" — 학습 39,000장(13개 지역 × 3,000), 검증 6,500장(13개 지역 × 500), 평가용 테스트 50장(`OCR_test_set_50`, 학습/검증과 별도 구성)
- 커스텀 딕셔너리 파일 경로/형식: `OCR_finetune_data/custom_dict.txt` — 한 줄에 문자 1개, 총 1,118자. 학습·검증 데이터에 등장한 문자 + 등록 음식명 문자의 합집합(`prepare_dataset.py`의 `build_dictionary`)
- **학습에만 필요한 패키지는 그때 따로 설치한다.** `requirements.txt`는 Dockerfile이 그대로
  설치하는 목록이라, 배포 서버가 쓰지 않는 것을 넣으면 이미지만 무거워진다. 학습·양자화를
  돌릴 환경에서 아래를 추가로 깐다(2026-08-27에 목록에서 분리함).

  ```bash
  pip install paddleslim albumentations albucore lmdb scikit-image
  ```

  `paddleslim`은 양자화(3안), 나머지는 학습 데이터 증강과 데이터 로더용이다. 추론 경로는
  이것들 없이 동작한다 — 없는 환경에서 실제 메뉴판으로 후보·가격까지 정상 인식됨을 확인했다.
- 매칭 임계값 (RapidFuzz score): `match.py`의 `MATCH_THRESHOLD = 85` (`name_score()` 기준, 2026-08-23 오탐 측정 후 65에서 상향 — `eval/measure_match_precision.py` 참고)

## AC (Given-When-Then)

**AC-01 · 정상 촬영된 메뉴판에서 등록 음식명 인식**
- GIVEN: 사용자가 조명이 양호하고 기울기가 크지 않은 메뉴판 사진을 촬영
- WHEN: 전처리 → 파인튜닝 OCR → `scan_menu_lines()` 파이프라인을 실행
- THEN: `OCR_test_set_50` 기준 90% 이상의 사진에서 등록 음식명과 정확히 매칭된다

**AC-02 · 기울어진 사진 보정**
- GIVEN: 메뉴판이 기울어져 촬영됨 (EC-01)
- WHEN: `preprocess_image`가 호출됨
- THEN: deskew로 각도가 보정된 이미지가 OCR에 전달되고, 보정 전 대비 인식률이 떨어지지 않는다

**AC-03 · 등록되지 않은 음식명 처리**
- GIVEN: OCR이 등록되지 않은 음식명 글자를 추출함 (EC-03)
- WHEN: `scan_menu_lines()`가 호출됨
- THEN: `name_score()`가 `MATCH_THRESHOLD`(현재 85) 미만이라 후보를 만들지 않고, UI에 "미지원 안내"가 표시된다

**AC-04 · 글자 인식 완전 실패**
- GIVEN: 조명·각도 문제로 OCR이 텍스트를 전혀 추출하지 못함 (EC-04)
- WHEN: 파이프라인이 빈 OCR 결과를 받음
- THEN: "조명·거리·각도 안내" 메시지와 함께 재촬영을 요청한다

## 구현 변경 이력 (2026-08-17)

### export 기능 버그로 인한 아키텍처 변경

**계획대로 안 된 부분**: `infer.py`는 원래 PaddleOCR의 "export"(체크포인트 → 배포용 정적 그래프 변환) 기능으로 변환한 파일을, `PaddleOCR()` 고수준 API로 불러오는 방식으로 구현할 계획이었음.

**발견한 문제**: `korean_PP-OCRv5_mobile_rec`(PPLCNetV3 backbone + MultiHead) 모델 구조에서 export 기능이 근본적으로 작동하지 않음. 시도한 조합 전부 동일 증상(설정 파일만 생성되고 실제 가중치 파일은 안 만들어지거나, 타입 에러로 크래시):

| Paddle 버전 | export 방식 | 결과 |
|---|---|---|
| 3.2.2 | PaddleX `main.py`, 기본(PIR) | `inference.yml`만 생성, 가중치 없음 |
| 3.2.2 | PaddleOCR `tools/export_model.py`, 기본(PIR) | 동일 |
| 3.2.2 | `export_with_pir=False`(legacy 강제) | `TypeError: multiply(): ... Value, but got Variable` 크래시 |
| 3.3.0 | 기본(PIR) | `inference.yml`만 생성, 가중치 없음 |
| 3.3.0 | `export_with_pir=False` | 동일 크래시 |

**근거**: 원본 체크포인트(`.pdparams`)는 export 없이 PaddleOCR 저장소 내부 코드(`ppocr.modeling`, `ppocr.postprocess` 등, dynamic graph 방식)로 직접 불러오면 정상 작동함을 확인함 (검증 이미지 `SL_val_000000.jpg`, 정답 "생맥주", 99.99% 신뢰도로 정확히 인식).

**결정**: export 경로를 포기하고, 위 방식(원본 체크포인트 직접 로딩)으로 배포 경로도 그대로 구현. PaddleOCR 저장소의 필요한 내부 코드(`ppocr/` 폴더, Apache-2.0)를 `src/ocr/vendor/ppocr/`로 가져와 사용. Detection은 기존 계획대로 파인튜닝 안 한 PaddleOCR 기본 모델(가벼운 mobile 버전, `PP-OCRv5_mobile_det`) 그대로 사용.

**HF Hub 업로드물 변경**: 원래 계획한 "export된 배포용 파일" 대신, 원본 체크포인트(`best_accuracy.pdparams`) + 커스텀 딕셔너리(`dict.txt`) 두 파일만 그대로 업로드함 (`k-bite-team/K_Bite_OCR`, 팀 Organization으로 이전됨; 2026-10-20 개인 계정 `hajeongun/K_Bite_OCR`로 그대로 복사).


**AC-01 재검증 완료 (2026-08-17)**: detection 모델을 mobile 버전으로 바꾼 뒤 `OCR_test_set_50`(match_count>=1인 36장) 재측정 결과 35/36(97.22%) — 기존 수치와 동일, 영향 없음 확인됨.
- *(2026-08-21 단서)* 이 측정은 세로쓰기 회전 보정(PR #32) **이전** 수치이며, 당시 측정 스크립트가 커밋되지 않아 판정 기준을 재확인할 수 없음.

**신규 실측 (2026-08-21, `eval/measure_ocr.py` — 커밋된 스크립트로 재현 가능)**: 세로쓰기 회전 보정 등 후처리 반영 후 동일 테스트셋 재측정.

| 지표 | 기존 | 신규 (08-21) | 재측정 (08-28) | 비고 |
|---|---|---|---|---|
| 매칭 정확도 (올바른 음식 후보 노출) | 97.22% | **91.67%** | **91.67%** | 매칭 대상 36장(전체 50장) 기준. 차이는 매칭 규칙 한계 2건 + 오독 1건, 기존 수치는 판정 기준 확인 불가 |
| 라벨 완전일치 (글자 단위) | 42.94% | 66.67% | **72.32%** | 08-21은 세로쓰기 회전 보정 효과, 08-28은 그 뒤 들어간 줄 단위 매칭 개선이 더해진 값 |

**base 비교 완료 (2026-08-28)**: 같은 코드·같은 detection 박스로 인식 모델만 바꿔 측정한 결과, PaddleOCR 기본 인식기(`PP-OCRv6_medium_rec`)는 매칭 **0.0%**(0/36)였다. 한글을 한자·영문으로 읽어 음식명이 하나도 걸리지 않는다. 결과 원본은 `eval/measure_ocr_base.json`, 정리는 `eval/model_comparison.md` 1절.

- 이 0%는 "기성 OCR을 그대로 쓸 수 있나"의 답이다. **파인튜닝 직전 체크포인트(`korean_PP-OCRv5_mobile_rec` 원본 가중치)와의 비교는 아직 미측정** — `measure_ocr.py --rec local`로 재야 한다
- 측정 중 `eval/measure_ocr.py`의 `--rec paddle-base` 경로가 옮겨진 `preprocess_image`를 부르다 죽는 버그를 발견해 함께 고쳤다
