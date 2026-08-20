# AGENTS.md

AI 코딩 에이전트(Claude Code, Codex, Cursor 등)가 이 저장소에서 작업할 때 따르는 공통 지침입니다. 어떤 도구를 쓰든 이 문서를 기준으로 합니다.

## 프로젝트 개요

외국인 사용자가 한국 음식 메뉴판 이미지를 OCR로 인식하고, 음식 정보와 매운맛 안내를 텍스트와 음성으로 제공받을 수 있는 서비스입니다.

## 기술 스택

- **언어**: Python
- **OCR**: PaddleOCR, OpenCV
- **음식명 유사도 매칭**: RapidFuzz
- **TTS**: Qwen3-TTS-12Hz-1.7B-Base + PEFT(LoRA) 파인튜닝 (어댑터: `k-bite-team/k-menu-qwen3-tts-lora`)
- **데이터베이스**: Supabase
- **서버**: FastAPI (`K_Menu_Talk.py`가 `/api/analyze`, `/api/foods/{id}` 노출)
- **배포 형태**: Flutter 앱 (최종 목표). 기능 동결 전까지는 React 웹앱으로 체크포인트 데모

## Spec 먼저, 구현은 그다음

기능을 에이전트에게 시키기 전에 `docs/specs/{기능명}.md`에 Spec을 먼저 작성하세요. 형식은 `docs/specs/_example.md` 참고 — 다섯 섹션(Why · Goal · What · How · AC)이 다 있어야 에이전트에게 그대로 넘길 수 있습니다.

- **Why**: 페르소나·상황·문제·측정 지표
- **Goal**: 숫자로 된 성공 기준 + Out of Scope
- **What**: Happy Path + Edge Case
- **How**: API·데이터·제약 (에이전트가 임의 결정할 여지를 없앤다)
- **AC**: Given-When-Then 형식, 테스트 코드로 바로 옮길 수 있어야 함

## Out of Scope 원칙

에이전트는 Spec에 없는 기능을 임의로 추가하지 않습니다. "이왕이면"으로 범위를 넓히지 않습니다.

## 완료 기준

테스트(AC 기준) 통과 없이 "완료"라고 보고하지 않습니다.
