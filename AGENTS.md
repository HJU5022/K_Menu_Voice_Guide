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
- **서버**: FastAPI (`K_Menu_Talk.py`가 `/api/analyze`, `/api/foods/{id}`, `/api/cart` 노출)
- **웹 화면**: React + TypeScript (`frontend/`) — `K_Menu_Talk.py`를 HTTP로 호출하는 화면 전용 클라이언트다. 계산을 직접 하지 않고, API 주소는 `VITE_API_BASE_URL` 하나로만 받는다(`frontend/client/src/lib/api.ts`). 2026-08-23에 Streamlit으로 갈아탔다가 2026-08-25에 React로 되돌렸고, 2026-08-26에 Streamlit 진입점(`app.py`)을 저장소에서 제거했다
- **모바일 앱**: Flutter (최종 목표, `mobile/`). 같은 `K_Menu_Talk.py`를 HTTP로 호출한다 — 웹과 앱은 계약이 같은 두 개의 별도 클라이언트이지, 한쪽이 다른 쪽을 대체하지 않는다
- **배포**: Hugging Face Spaces를 **둘로 나눠** 쓴다. 계산(OCR·매칭·TTS)은 GPU Space 한 곳(`K_Menu_Talk.py`, Docker SDK, Nvidia T4 — 루트 `Dockerfile`, 배포 스크립트 `deploy/api-space/deploy.sh`)에 몰고, 웹은 그 API를 부르기만 하는 **무료 static Space**에 빌드 결과물(`pnpm run build`)만 올린다(`frontend/space/deploy.sh`). 웹에도 계산을 두면 GPU 비용이 두 배가 되기 때문이다. static SDK는 컨테이너 빌드 단계가 없어 배포가 몇 초에 끝난다(`docs/specs/fastapi-space-deploy.md`, `frontend/space/README.md`)

## Spec 먼저, 구현은 그다음

기능을 에이전트에게 시키기 전에 `docs/specs/{기능명}.md`에 Spec을 먼저 작성하세요. 형식은 `docs/specs/_example.md` 참고 — 다섯 섹션(Why · Goal · What · How · AC)이 다 있어야 에이전트에게 그대로 넘길 수 있습니다.

- **Why**: 페르소나·상황·문제·측정 지표
- **Goal**: 숫자로 된 성공 기준 + Out of Scope
- **What**: Happy Path + Edge Case
- **How**: API·데이터·제약 (에이전트가 임의 결정할 여지를 없앤다)
- **AC**: Given-When-Then 형식, 테스트 코드로 바로 옮길 수 있어야 함

**예외 — 웹 화면**: React 웹 화면의 스펙은 `docs/specs/`가 아니라 `frontend/docs/`에 둡니다(화면 흐름·화면별 스펙·API 호출 규칙·배포 절차). 화면 문서를 화면 코드 옆에 두기 위해서이며, 두 곳에 나눠 쓰면 서로 어긋납니다. 웹 화면 작업 전에는 `frontend/docs/README.md`의 표를 먼저 읽으세요.

## Out of Scope 원칙

에이전트는 Spec에 없는 기능을 임의로 추가하지 않습니다. "이왕이면"으로 범위를 넓히지 않습니다.

## 구현 원칙

- 이미 있는 코드·패턴을 우선 재사용합니다. 새로운 로직·알고리즘·추상화는 Spec에 명시되지 않았다면 임의로 만들지 않습니다.
- 구현 방식이 여러 개일 때는 가장 단순하고 기존 코드와 일관된 방법을 택합니다. "이게 더 나은 방식 같다"는 판단이 들어도 스스로 바꾸지 않고, 먼저 팀에 확인받습니다.
- Spec에 없는 결정(라이브러리 교체, 구조 변경 등)은 임의로 내리지 않습니다. 확신이 없으면 추측해서 구현하지 말고 질문합니다.

## Git 규칙

- `main` 브랜치에 직접 커밋·push하지 않습니다. 항상 새 브랜치(`feat/{작업내용}`, `fix/{내용}`, `docs/{내용}`)를 만들어 작업하고, PR로만 main에 합칩니다.
- 스택 PR을 만들지 않습니다 — 각 브랜치는 `origin/main`에서 새로 분기합니다. 이전 PR이 아직 merge되지 않았어도, 다음 작업은 옛 브랜치 위가 아니라 최신 `origin/main`에서 다시 딴다(그 사이 merge된 PR을 기다렸다가).
- `main` 브랜치에 force push(`--force`, `-f`)를 하지 않습니다.
- `git reset --hard`, `git clean -f` 등 되돌리기 힘든 명령은 임의로 실행하지 않고, 실행 전에 먼저 사용자에게 확인받습니다.
- 커밋 메시지에 AI 생성 흔적(`Co-Authored-By: Claude` 등)을 넣지 않습니다.
- PR 본문은 `.github/PULL_REQUEST_TEMPLATE.md`의 3섹션만 채웁니다: 변경 요약(2~3줄) / 리뷰 포인트(2~3개) / 체크리스트.

## 보안 원칙

- API 키·비밀번호·토큰을 코드에 직접 작성(하드코딩 포함)하지 않습니다. 항상 `.env`를 통해 불러옵니다.
- 새로 필요한 키가 생기면 `.env.example`에 값 없이 키 이름만 추가합니다.
- Secret Scan(GitHub Actions, `.github/workflows/secret-scan.yml`)이 **PR의 모든 커밋**과 **`main`으로의 push**를 검사합니다(브랜치 push마다 두 번 돌던 것을 2026-08-21에 정리). 머지 전 탐지 능력은 그대로입니다. 실패 시 커밋 히스토리에서 지워도 유출로 간주되므로, 애초에 키를 커밋하지 않는 것이 유일한 대응입니다.
- PR은 조원 1명 이상의 approve를 받은 뒤에만 merge합니다. merge 실행은 조장만 진행합니다.

## 로깅 원칙

- 예외를 잡을 때 그냥 버리지 않습니다(`except Exception: pass`). 무슨 예외였는지 `logging`으로 남깁니다 — 안 남기면 실패 원인이 배포 환경에서 재현 불가능해집니다(`docs/specs/error-logging.md`의 실제 사례 참고).
- 로그는 컨테이너 파일이 아니라 **stdout**으로 내보내, 셸 접근 없는 배포 환경(HF Spaces 등)의 로그 화면에서 바로 보이게 합니다.
- URL·토큰·키 등 자격증명을 로그에 평문으로 남기지 않습니다. 라이브러리가 알아서 찍는 로그(예: HTTP 클라이언트의 요청 URL)도 확인 대상입니다.

## 완료 기준

테스트(AC 기준) 통과 없이 "완료"라고 보고하지 않습니다.
