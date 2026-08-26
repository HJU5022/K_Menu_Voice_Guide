# docs/

프로젝트 문서를 모아두는 곳입니다.

| 파일 | 내용 |
|---|---|
| `기획서.md` | **왜 만들었고 무엇을 달성했는가** — 문제 정의·고객 여정·범위·성공 기준 대비 실측·모델 선택 근거·엔지니어링 판단·한계. 코드 구조와 실행 방법은 루트 `README.md`에 있다 |
| [`submission/`](submission/README.md) | **1차 프로젝트 제출물 8종** — 고객여정지도·구조도·노드 설명·입출력 결과물·모델 비교 실험·발표 원고·데모 대본. 색인은 `submission/README.md` |
| `specs/` | 기능별 Spec 문서 |
| `legal/` | 동의서·공개용 가림본 등 프로젝트 운영 문서 |
| [`content-style.md`](content-style.md) | 화면에 쓰는 영어 문구 기준 (웹·앱 공통) |
| [`../frontend/README.md`](../frontend/README.md) | React 웹 화면 구조·실행/빌드 방법·프론트 문서 읽는 순서 |
| [`../frontend/docs/`](../frontend/docs/README.md) | **웹 화면 스펙이 사는 곳** — 화면 흐름·화면별 스펙·API 호출 규칙·배포 절차 |
| [`../mobile/README.md`](../mobile/README.md) | Flutter 앱 구조·실행 방법(시뮬레이터/실기기)·자주 겪는 문제 |

> 전체 파이프라인 흐름도는 루트 [`README.md`](../README.md)의 "시스템 아키텍처" 절에 Mermaid 다이어그램으로 들어있습니다(별도 이미지 파일 없음 — 텍스트라 수정이 쉽고 GitHub에서 바로 그림으로 보입니다).

## Spec 목록

아래 표는 **백엔드·파이프라인·모바일 앱** 스펙입니다. **웹(React) 화면 스펙은 여기가 아니라 [`frontend/docs/`](../frontend/docs/README.md)에 있습니다** — 화면 문서는 화면 코드 바로 옆에 두고, 이 목록은 가리키기만 합니다(두 벌로 갈라져 서로 어긋나는 것을 막기 위해서). 화면이나 API 경계를 바꿀 때 갱신해야 하는 문서도 그쪽 표에 정리돼 있습니다.

| 파일 | 내용 |
|---|---|
| `specs/_example.md` | Spec 작성 형식 예시 |
| `specs/api-layer.md` | FastAPI 엔드포인트 계약 (`/api/analyze`, `/api/foods/{food_id}`) |
| `specs/cart.md` | 장바구니 — 담기·수량 조절·주문 요약 |
| `specs/db-cache.md` | 서버 시작 시 전체 데이터 메모리 캐싱 |
| `specs/error-logging.md` | 예외를 삼키지 않고 stdout에 남기는 규칙 (실제 사고 사례 포함) |
| `specs/fastapi-space-deploy.md` | API를 GPU Docker Space에 올리는 절차·제약 |
| `specs/flutter-mobile-app.md` | Flutter 앱 — 화면 3개, 서버 주소 전환, iOS 권한 설정 |
| `specs/ocr-candidate-results.md` | OCR 결과를 음식 후보 목록으로 돌려주는 계약 |
| `specs/ocr-finetuning.md` | 커스텀 딕셔너리·학습 데이터·1~3안 전환 기준 |
| `specs/ocr-preprocess-runtime.md` | 추론 경로에 OpenCV 전처리 연결 |
| `specs/sample-menu-images.md` | 처음 온 사람이 눌러볼 예시 메뉴판 사진 |
| `specs/supported-foods.md` | 지원 음식 50개 목록·선정 기준 |
| `specs/text-generation.md` | 카테고리 6개 조합 + spice_level→style 결정 로직 |
| `specs/tts-finetuning.md` | TTS 파인튜닝 방식·목표 (실제 실험 결과는 [`eval/TTS_MODULE.md`](../eval/TTS_MODULE.md)) |

## Spec 작성 규칙

기능을 구현하기 **전에** `specs/{기능명}.md`를 먼저 씁니다. 형식은 `specs/_example.md`를 따르고, 다섯 섹션(Why · Goal · What · How · AC)을 모두 채웁니다.

자세한 내용은 루트의 [AGENTS.md](../AGENTS.md)를 참고하세요.
