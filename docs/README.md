# docs/

프로젝트 문서를 모아두는 곳입니다.

| 파일 | 내용 |
|---|---|
| `기획서.md` | 문제 정의·해결 방식·범위·성공 기준·일정 (현재 뼈대 상태 — 백엔드 완료 후 프론트 내용과 합쳐 정리 예정) |
| `specs/` | 기능별 Spec 문서 |
| [`../frontend/docs/`](../frontend/docs/) | 프론트 화면 흐름·영어 문구·API 클라이언트·배포 문서 |
| [`../mobile/README.md`](../mobile/README.md) | Flutter 앱 구조·실행 방법(시뮬레이터/실기기)·자주 겪는 문제 |

> 전체 파이프라인 흐름도는 루트 [`README.md`](../README.md)의 "시스템 아키텍처" 절에 Mermaid 다이어그램으로 들어있습니다(별도 이미지 파일 없음 — 텍스트라 수정이 쉽고 GitHub에서 바로 그림으로 보입니다).

## Spec 목록

| 파일 | 내용 |
|---|---|
| `specs/_example.md` | Spec 작성 형식 예시 |
| `specs/api-layer.md` | FastAPI 엔드포인트 계약 (`/api/analyze`, `/api/foods/{food_id}`) |
| `specs/db-cache.md` | 서버 시작 시 전체 데이터 메모리 캐싱 |
| `specs/flutter-mobile-app.md` | Flutter 앱 — 화면 3개, 서버 주소 전환, iOS 권한 설정 |
| `specs/ocr-candidate-results.md` | OCR 결과를 음식 후보 목록으로 돌려주는 계약 |
| `specs/ocr-finetuning.md` | 커스텀 딕셔너리·학습 데이터·1~3안 전환 기준 |
| `specs/ocr-preprocess-runtime.md` | 추론 경로에 OpenCV 전처리 연결 |
| `specs/streamlit-app.md` | HF Spaces 배포 진입점 `app.py` — 플랫폼 선정 근거·화면 구성 |
| `specs/text-generation.md` | 카테고리 6개 조합 + spice_level→style 결정 로직 |
| `specs/tts-finetuning.md` | TTS 파인튜닝 방식·목표 (실제 실험 결과는 [`eval/TTS_MODULE.md`](../eval/TTS_MODULE.md)) |

React/Vite 화면 상태·API 경계·응답 변환 기준은 프론트엔드 전용 문서인 [`frontend/docs/ux-ui-integration.md`](../frontend/docs/ux-ui-integration.md)에서 관리합니다.

## Spec 작성 규칙

기능을 구현하기 **전에** `specs/{기능명}.md`를 먼저 씁니다. 형식은 `specs/_example.md`를 따르고, 다섯 섹션(Why · Goal · What · How · AC)을 모두 채웁니다.

자세한 내용은 루트의 [AGENTS.md](../AGENTS.md)를 참고하세요.
