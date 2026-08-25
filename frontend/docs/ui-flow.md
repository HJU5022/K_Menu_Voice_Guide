# UI Flow

## Why

한글 메뉴판이 낯선 영어권 관광객은 현재 단계와 다음 행동을 바로 이해해야 한다.

## Goal

첫 진입부터 음식 상세 화면 또는 재시도 가능한 오류 화면까지 한 흐름으로 연결한다.

**Out of Scope**: 로그인, 즐겨찾기, 주문·결제, 음성 질문.

## What

```text
서비스 소개(랜딩) — 무엇을 해주는지·이용 3단계·사진 사용 안내
→ Get started
→ 카메라 촬영 또는 메뉴 사진 업로드
→ 메뉴 읽는 중
→ 음식 후보와 원본 사진 대조
→ 음식 하나 선택
→ 음식 상세·오디오 안내
```

| 상황 | 보여 줄 화면·행동 |
|---|---|
| 카메라 권한 거부 | 권한 이유와 `Upload a menu photo` 대안 |
| 메뉴 글자를 읽지 못함 | 촬영 품질 안내와 `Scan another menu` |
| 미지원 음식 | 추측하지 않는 안내와 새 메뉴 스캔 |
| 연결 실패 | 쉬운 오류 문구와 `Try again` |
| 오디오 준비 실패 | 상세 텍스트를 유지하고 `Try audio again` |

## How

프론트는 `landing`, `camera`, `processing`, `candidates`, `order`, `result`, `error` 화면 상태를 사용한다. 첫 화면은 `landing`이고 `Get started`가 `camera`로 넘긴다. 분석을 시작하면 즉시 대기 화면을 보이고, 성공·실패 결과에 따라 다음 상태로 이동한다.

**화면마다 URL을 만들지 않는다.** 배포처인 Hugging Face static Space에는 SPA fallback이 없어서 `/landing` 같은 경로는 직접 접근·새로고침 한 번에 404가 된다. 화면 이동은 `Home.tsx`의 `Screen` 상태 하나로만 한다.

## AC (Given-When-Then)

- GIVEN: 사용자가 처음 접속했다. WHEN: 화면이 뜬다. THEN: 랜딩을 보여주고, `Get started`를 누르면 URL 변경 없이 촬영/업로드 화면으로 이동한다.
- GIVEN: 사용자가 메뉴 사진을 선택했다. WHEN: 분석이 시작된다. THEN: 대기 화면을 거쳐 후보 또는 오류 화면으로 이동한다.
- GIVEN: 후보가 있다. WHEN: 사용자가 후보를 선택한다. THEN: 해당 음식의 상세 화면을 표시한다.
- GIVEN: 오류 화면이다. WHEN: 사용자가 다시 스캔을 선택한다. THEN: 새 사진을 선택할 수 있는 화면으로 돌아간다.
