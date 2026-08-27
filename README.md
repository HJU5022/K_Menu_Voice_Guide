# K-Menu Voice Guide

영어권 관광객이 한국어 메뉴판을 촬영하면, 음식의 발음·맵기·재료·먹는 법·알레르기까지
영어 텍스트와 음성으로 설명해주는 멀티모달 한국 음식 가이드.

| | |
|---|---|
| 웹 | <https://hju5022-k-menu-react.static.hf.space> |
| API | <https://hju5022-k-menu.hf.space> (`GET /api/foods`로 살아있는지 확인) |
| 프로젝트 | KDT AI Human 7기 1차 프로젝트 · 팀 C |

> **이 문서는 저장소를 어떻게 실행·검증·배포하는가**를 다룬다.
> 왜 만들었고 무엇을 달성했는가(문제 정의·성공 기준 대비 실측·모델 선택 근거·엔지니어링
> 판단·한계)는 [`docs/기획서.md`](docs/기획서.md)에 있다.

### 팀원

| 이름 | GitHub | 역할 |
|---|---|---|
| 하정운(조장) | [@HJU5022](https://github.com/HJU5022) | PM · OCR 파인튜닝 · 파이프라인 통합 · DB · 배포 |
| 박민영 | [@pastar20250101-creator](https://github.com/pastar20250101-creator) | TTS 파인튜닝 · 하이퍼파라미터 실험 · UX/UI |
| 배재훈 | [@Bae-JaeHun](https://github.com/Bae-JaeHun) | 데이터 구축 (프로젝트 참여 종료) |
| 차백호 | [@cosohotmas](https://github.com/cosohotmas) | TTS 추론 |

---

## 저장소 구조

폴더가 무슨 일을 하는지만 적는다. **파일 단위 설명은 각 폴더의 README에 있다** — 같은 내용을
두 군데 적으면 한쪽만 고쳤을 때 조용히 갈라지기 때문이다.

```
proj1-c/
├── K_Menu_Talk.py        API 진입점 (FastAPI). 화면을 갖지 않고 엔드포인트 6개만 노출한다
├── Dockerfile            API를 올리는 GPU Docker Space용 이미지
├── requirements.txt      API·OCR·TTS가 쓰는 파이썬 패키지
│
├── src/                  실제 로직 → src/README.md
│   ├── ocr/                이미지 ──▶ 음식 후보 목록
│   ├── text_gen/           음식 ──▶ 상세 텍스트 6개 + 내레이션 텍스트 1개
│   ├── db/                 Supabase 읽기 전용 접근 + 메모리 캐시
│   ├── tts/                내레이션 텍스트 + 스타일 ──▶ WAV
│   ├── cart/               장바구니 (파이프라인 단계가 아니라 별도 상태 저장소)
│   └── pipeline.py         위 블록들을 입출력 계약대로 연결
│
├── frontend/             React + TypeScript 웹 화면 → frontend/README.md
├── mobile/               Flutter 모바일 앱 (iOS·Android) → mobile/README.md
│
├── tests/                pytest — 모델·DB를 부르지 않고 로직만 검사 → tests/README.md
├── eval/                 모델 성능 측정과 그 원본 기록 → eval/README.md
├── docs/                 기획서 · Spec · 문구 기준 · 운영 문서 → docs/README.md
├── deploy/api-space/     API Space 배포 스크립트와 Space 설정
├── data/                 데이터 받는 법·변환법만 (파일 자체는 git 제외) → data/README.md
└── models/               HF Hub 모델 ID 기록 → models/README.md
```

git에 따라오지 않지만 실행하면 생기는 폴더가 셋 있다.

| 폴더 | 무엇 | 없으면 |
|---|---|---|
| `static/tts_cache/` | 사전 생성 음성 100개 (나레이션 50 + 이름 50) | 요청마다 라이브 생성으로 넘어가 음식당 수십 초가 걸린다 |
| `static/audio/` | 라이브 생성한 wav — `/audio/{파일명}`으로 서빙 | 서버가 알아서 만든다 |
| `logs/` | `tts_worker.log` 등 실행 로그 | 서버가 알아서 만든다 |

---

## 실행하기

### 준비물

- Python 3.11
- Node.js + [pnpm](https://pnpm.io) (웹 화면을 볼 때만)
- Flutter SDK (모바일 앱을 볼 때만)
- GPU는 **없어도 된다.** OCR은 CPU에서도 돌고(느릴 뿐), TTS는 사전 생성 캐시를 읽는다.

### 1. 파이썬 환경

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. TTS는 별도 환경에 깐다

`paddle`(OCR)과 `torch`(TTS)를 한 프로세스에 함께 올릴 수 없어서, TTS는 자식 프로세스로
분리해 돌린다(`src/tts/worker.py`). 그 자식이 쓸 환경을 따로 만든다.

```bash
python -m venv .venv-tts
.venv-tts/bin/pip install "torch==2.6.0" "torchaudio==2.6.0" qwen-tts peft transformers safetensors soundfile huggingface_hub numpy
```

`torch`와 `torchaudio`는 **버전을 못 박아야 한다.** 둘은 같은 버전끼리만 맞물리는데, 버전을
안 적으면 그날의 최신을 각각 집어와 짝이 깨진다. 실제로 어긋났을 때 `qwen_tts` 임포트가
`OSError: [WinError 127]`로 죽어 TTS가 통째로 멈췄다. 로딩 실패라 **캐시가 있으면 증상이
안 보인다** — 라이브 생성만 조용히 죽는다.

### 3. 환경변수

`.env.example`을 `.env`로 복사한 뒤 값을 채운다. 필요한 키의 설명은 그 파일 안에 다 적혀 있다.

```bash
cp .env.example .env
```

macOS·Linux에서는 **`TTS_VENV_PYTHON`을 반드시 채워야 한다.** 기본값이 Windows 구조
(`.venv-tts/Scripts/python.exe`)라, 비워두면 위에서 만든 환경을 못 찾는다.

```env
TTS_VENV_PYTHON=.venv-tts/bin/python
```

### 4. API 서버 띄우기

```bash
uvicorn K_Menu_Talk:app --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0`은 실제 휴대폰에서 붙을 때 필요하다. 기본값(`127.0.0.1`)이면 이 컴퓨터
자신만 접속할 수 있다.

```bash
curl http://localhost:8000/api/foods
```

지원 음식 50개가 JSON으로 나오면 DB 연결까지 정상이다. 서버 기동 후 **첫 요청**만
Supabase를 한 번에 읽느라 2.5초쯤 걸리고, 그 뒤로는 메모리 캐시라 사라진다.

엔드포인트는 6개다. 요청·응답 계약은 [`docs/specs/api-layer.md`](docs/specs/api-layer.md)가 정본이다.

| 메서드 | 경로 | 하는 일 |
|---|---|---|
| `POST` | `/api/analyze` | 메뉴판 사진 ──▶ 음식 후보 목록 |
| `GET` | `/api/foods` | 안내 가능한 음식 50개 목록 |
| `GET` | `/api/foods/{food_id}` | 상세 텍스트 6개 + 내레이션 텍스트·음성 |
| `GET` | `/api/cart` | 장바구니 조회 |
| `POST` | `/api/cart/items` | 담기·수량 조절 |
| `DELETE` | `/api/cart` | 비우기 |

### 5. 음성 캐시 만들기

캐시는 git에 올라가지 않으므로 **새 컴퓨터에서는 비어 있다.** 채우지 않으면 요청마다
라이브 생성으로 넘어간다.

```bash
python -m src.tts.pregenerate
```

음식 50개의 나레이션 음성과 이름 음성을 미리 만들어 `static/tts_cache/`에 넣는다.
나레이션 문장이 바뀐 뒤라면 `--force`를 붙여 다시 만들어야 한다 — 파일이 이미 있으면
건너뛰기 때문이다.

### 6. 웹 화면

```bash
cd frontend
pnpm install
pnpm run dev
```

`frontend/.env`에 백엔드 주소를 넣는다. `VITE_` 값은 브라우저에 그대로 실리므로 토큰·비밀번호를
넣지 않는다.

```env
VITE_API_BASE_URL=http://localhost:8000
```

### 7. 모바일 앱

```bash
cd mobile
flutter run
```

서버 주소는 `mobile/lib/config.dart` 한 곳에서 바꾼다(기본값은 배포 서버). 시뮬레이터·에뮬레이터는
`http://localhost:8000`, 실제 휴대폰은 `http://<이 컴퓨터의 LAN IP>:8000`이다 — 폰에게
`localhost`는 폰 자신이라 서버를 못 찾는다. 자세한 것은 [`mobile/README.md`](mobile/README.md).

---

## 테스트

```bash
python -m pytest
```

OCR·TTS 모델도 Supabase도 부르지 않는다. `unittest.mock`으로 가짜 값을 끼워넣어 **로직과 연결
방식만** 검사하므로 GPU 없이, 인터넷 없이 몇 초 만에 돈다. 무엇을 왜 검사하는지는
[`tests/README.md`](tests/README.md).

모델 성능은 테스트가 아니라 `eval/`에서 잰다. 실제 사진과 GPU가 필요한 것과 없이도 되는 것이
갈리므로 [`eval/README.md`](eval/README.md)를 먼저 볼 것.

---

## 배포

Hugging Face Space를 **둘로 나눠** 쓴다.

| | Space | 무엇이 올라가나 | 왜 |
|---|---|---|---|
| API | `HJU5022/K_Menu` (Docker, T4 GPU) | 저장소 전체 | 계산(OCR·매칭·TTS)을 한 곳에 몬다 |
| 웹 | `HJU5022/K_Menu_react` (Static, 무료) | `pnpm run build` 결과물만 | 화면 쪽에도 계산을 두면 GPU 비용이 두 배가 된다 |

API Space에 전용 GPU가 필요한 이유는 ZeroGPU가 PyTorch 전용이라 PaddleOCR이 GPU를 못 쓰기
때문이다. OCR 실측이 92상자 기준 **CPU 22.8초 → GPU 0.8초**로 나와, 계산은 GPU에 있어야
한다는 것이 숫자로 굳었다.

```bash
deploy/api-space/deploy.sh                                  # main을 API Space에
frontend/space/deploy.sh HJU5022/K_Menu_react               # 웹 빌드 결과물을 Static Space에
```

두 스크립트 모두 **대상 Space를 통째로 덮어쓴다(`--force`).** 소스는 GitHub에 있고 Space에는
산출물만 두므로, 되돌릴 일이 생기면 그 시점 소스를 다시 올리면 된다.

웹은 서버 주소가 **빌드 시점에 JS 안에 박힌다**(Vite의 `VITE_` 규칙). 그래서 주소를 바꾸려면
다시 빌드해야 한다 — Space에 환경변수를 넣는 것으로는 바뀌지 않는다. 절차와 제약은
[`docs/specs/fastapi-space-deploy.md`](docs/specs/fastapi-space-deploy.md)와
[`frontend/docs/deployment.md`](frontend/docs/deployment.md).

---

## 데이터와 모델

- **음식 데이터**는 Supabase 테이블 4개에 있다. 무엇이 어느 테이블에 있고 왜 캐싱하는지는
  [`src/db/README.md`](src/db/README.md). 런타임은 읽기 전용 anon key만 쓰고 RLS로 `SELECT`만 열려 있다.
- **설명 문장은 LLM이 만들지 않는다.** 팀이 미리 써서 DB에 넣어둔 문장을 조회해 조합할 뿐이다 —
  알레르기·재료에서 환각이 나오면 안전 문제가 되기 때문이다.
- **OCR 학습 데이터**를 받아 변환하는 법은 [`data/README.md`](data/README.md). 데이터 파일 자체는
  git에 올리지 않는다.
- **파인튜닝한 모델**의 HF Hub ID는 [`models/README.md`](models/README.md).

---

## 문서 지도

| 무엇이 궁금한가 | 어디를 보나 |
|---|---|
| 왜 만들었나, 목표를 달성했나 | [`docs/기획서.md`](docs/기획서.md) |
| 기능별 Spec (API·OCR·TTS·장바구니·배포) | [`docs/README.md`](docs/README.md) |
| 웹 화면 흐름·화면별 스펙 | [`frontend/docs/README.md`](frontend/docs/README.md) |
| 화면에 쓰는 영어 문구 기준 (웹·앱 공통) | [`docs/content-style.md`](docs/content-style.md) |
| 모델을 왜 이걸 골랐나, 실측값 | [`eval/README.md`](eval/README.md) |
| 에이전트·기여 규칙 (브랜치·PR·보안) | [`AGENTS.md`](AGENTS.md) |

---

## 기여 규칙 요약

- `main`에 직접 커밋·push하지 않는다. `feat/{내용}`·`fix/{내용}` 브랜치를 만들고 PR로만 합친다.
- 기능을 만들기 전에 `docs/specs/{기능명}.md`를 먼저 쓴다.
- API 키·토큰을 코드에 넣지 않는다. `.env`로만 불러오고, `.env.example`에는 키 이름만 적는다.
- AC 테스트가 통과하기 전에는 "완료"라고 하지 않는다.

전문은 [`AGENTS.md`](AGENTS.md)에 있다.
