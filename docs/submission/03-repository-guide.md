# 03. 소스 코드 (GitHub Repository)

> 제출물 3번 — 소스 코드
>
> 코드 자체는 저장소에 있다. 이 문서는 **평가자가 저장소를 열었을 때 어디를 어떤 순서로 보면
> 되는지, 그리고 어떻게 직접 돌려보는지**를 정리한 안내다.

## 1. 저장소

| 항목 | 값 |
|---|---|
| URL | <https://github.com/aihuman-7th/proj1-c> |
| 기본 브랜치 | `main` |
| 팀 | KDT AI Human 7기 C조 (4명) |
| 라이선스·데이터 | AI Hub '관광 음식메뉴판 데이터' 활용, 음성 화자 동의서는 [`docs/legal/tts-voice-consent/`](../legal/tts-voice-consent/) |

**처음 보는 사람이 읽는 순서**

1. [`README.md`](../../README.md) — 무엇을 만들었고 코드가 어떻게 생겼는가
2. [`docs/기획서.md`](../기획서.md) — 왜 만들었고 무엇을 달성했는가 (문제 정의·측정·판단)
3. [`eval/model_comparison.md`](../../eval/model_comparison.md) — 모델을 왜 그것으로 골랐는가
4. [`docs/specs/`](../specs/) — 기능별 Spec (Why · Goal · What · How · AC)

## 2. 디렉토리 구조

```
proj1-c/
├── K_Menu_Talk.py          # API 진입점 (FastAPI). 화면을 갖지 않는다
├── Dockerfile              # GPU API Space용 이미지 (베이스 이미지를 digest로 고정)
├── requirements.txt        # 파이썬 의존성
├── .env.example            # 필요한 환경변수 이름만 (값 없음)
│
├── src/
│   ├── pipeline.py         # 세 블록을 조립하는 곳 — analyze_image() / create_tts_response()
│   ├── ocr/                # 전처리·검출·인식·가격파싱·매칭 (+ vendor/ppocr: PaddleOCR 학습 코드 사본)
│   ├── text_gen/           # 상세 6카테고리 조회 · 내레이션 조립 · 스타일 결정
│   ├── tts/                # TTS 추론·별도 워커 프로세스·사전 생성 배치·Perso 비교 클라이언트
│   ├── db/                 # Supabase 클라이언트 + 서버 메모리 캐시
│   └── cart/               # 장바구니 상태
│
├── frontend/               # React + TypeScript 웹 (Vite, pnpm) — 계산하지 않고 API만 호출
│   ├── client/src/         #   pages/Landing.tsx(소개) · pages/Home.tsx(전체 흐름) · lib/api.ts(HTTP 계약)
│   ├── docs/               #   화면 스펙이 사는 곳 (화면 문서는 화면 코드 옆에 둔다)
│   └── space/deploy.sh     #   무료 Static Space 배포
│
├── mobile/                 # Flutter 앱 (가산 항목) — 같은 API를 부르는 두 번째 클라이언트
├── deploy/api-space/       # GPU Docker Space 배포 스크립트
├── eval/                   # 모델 성능 측정 스크립트·결과·학습 로그·비교 오디오
├── tests/                  # pytest 242개
├── docs/                   # 기획서 · Spec · 법무 문서 · (이 폴더) 제출물
└── static/                 # .gitignore 대상 — TTS 캐시·생성 오디오 (저장소로 따라오지 않는다)
```

**저장소에 따라오지 않는 것**: `static/`(TTS 캐시 100개), `data/`(학습·테스트 데이터), `models/`,
`.env`. 새 컴퓨터에서는 비어 있으므로 아래 3절을 따른다.

## 3. 로컬에서 돌리는 법

### 3-1. 백엔드 API

```bash
pip install -r requirements.txt
```

`.env.example`을 `.env`로 복사하고 값을 채운다 (`SUPABASE_URL`, `SUPABASE_ANON_KEY` 등).
**키는 저장소에 커밋하지 않는다** — 모든 push는 GitHub Actions Secret Scan으로 검사된다.

```bash
python -m uvicorn K_Menu_Talk:app --host 127.0.0.1 --port 8000
```

- 최초 기동 시 PaddleOCR 모델을 내려받는다(캐시 후 재사용). 첫 `POST /api/analyze`는 모델 로드
  때문에 오래 걸린다 — **로컬 CPU 실측 73.9초**, 워밍업 후 22.4초.
- `GET http://127.0.0.1:8000/api/foods`가 50개를 돌려주면 DB 연결까지 정상이다.
- GPU가 없거나 TTS 모델이 준비되지 않으면 `tts_status: "not_ready"`로 내려가고, 나머지 응답은 정상이다.

### 3-2. 웹 화면

```bash
cd frontend && pnpm install && pnpm run dev
```

또는 이미 빌드된 결과물을 그대로 띄운다:

```bash
cd frontend/dist/public && python -m http.server 4173
```

브라우저에서 `http://127.0.0.1:4173/?api=http://127.0.0.1:8000`을 연다.
`?api=`는 **이 브라우저에만** 저장되는 임시 서버 주소 전환이다(재배포 없이 다른 서버를 보게 하는 장치).

### 3-3. TTS 캐시

`static/tts_cache`가 비어 있으면 매 요청 라이브 생성으로 폴백한다(느리다). GPU가 있으면:

```bash
python -m src.tts.pregenerate
```

## 4. 테스트

```bash
python -m pytest tests -q
```

**실행 결과 (2026-08-27): 242 passed, 5 warnings in 76.06s** — 이 문서를 고치면서 실제로 돌린 값이다. (08-26 시점에는 237개였고, 그 뒤 OCR 후보 보정·가격 줄 허용오차 수정에 따라온 테스트가 더해졌다.)

| 파일 | 무엇을 지키는가 |
|---|---|
| `test_api.py` · `test_api_integration.py` | 엔드포인트 계약과 엣지 케이스(EC-01~EC-10) |
| `test_ocr_infer.py` · `test_ocr_match.py` · `test_ocr_preprocess.py` · `test_ocr_price.py` | OCR 인식·매칭·전처리·가격 파싱 |
| `test_narration.py` | 스타일 결정과 TTS용 텍스트 치환 |
| `test_tts_infer.py` · `test_pipeline.py` | TTS 호출 경로와 조립 |
| `test_cache.py` · `test_cart.py` | DB 메모리 캐시, 장바구니 |

## 5. 재현 가능성

| 항목 | 파일 | 비고 |
|---|---|---|
| 파이썬 의존성 | [`requirements.txt`](../../requirements.txt) | Paddle GPU 빌드는 PyPI에 없어 CUDA 버전별로 갈린다(주석에 근거 기록) |
| 컨테이너 | [`Dockerfile`](../../Dockerfile) | `python:3.11-slim`을 **digest로 고정** — 이름표만 쓰면 빌드가 조용히 바뀐다 |
| 환경변수 | [`.env.example`](../../.env.example) | 값 없이 키 이름만 |
| 배포 절차 | [`deploy/api-space/deploy.sh`](../../deploy/api-space/deploy.sh) · [`frontend/space/deploy.sh`](../../frontend/space/deploy.sh) | 커밋에 든 파일만 올린다 |
| CI | `.github/workflows/secret-scan.yml` | 모든 push에서 키 유출 검사 |

## 6. 파인튜닝 산출물이 어디 있나

| 산출물 | 위치 | 상태 |
|---|---|---|
| TTS LoRA 어댑터 | [`k-bite-team/k-menu-qwen3-tts-lora`](https://huggingface.co/k-bite-team/k-menu-qwen3-tts-lora) | 배포는 `checkpoint-epoch-31` (9차) |
| TTS 추론 코드 | [`src/tts/infer.py`](../../src/tts/infer.py) | `INSTRUCT_MAP` · `LORA_SCALE` · `_trim_silence()` |
| TTS 학습 노트북 | [`eval/qwen3_tts_lora_final.ipynb`](../../eval/qwen3_tts_lora_final.ipynb) | ⚠️ **8차 기준** — 배포본(9차) 재현 불가 |
| TTS 학습 로그 | [`eval/training_log.csv`](../../eval/training_log.csv) | ⚠️ **3~8차만** — 9차 미반영 |
| OCR 파인튜닝 | [`src/ocr/finetune.py`](../../src/ocr/finetune.py) · [`docs/specs/ocr-finetuning.md`](../specs/ocr-finetuning.md) | 커스텀 딕셔너리·학습 데이터 준비 포함 |
| OCR 학습 코드 사본 | `src/ocr/vendor/ppocr/` | PaddleOCR 학습 파이프라인 |
| 측정 스크립트 | [`eval/`](../../eval/) | `measure_ocr.py` · `measure_digits.py` · `measure_match_precision.py` |

## 7. 저장소 정리가 필요한 곳 (숨기지 않고 적는다)

| # | 항목 | 왜 문제인가 |
|---|---|---|
| 1 | `eval/mos_scores.csv`가 헤더만 있음 | 사람 MOS는 **한 건도 없다(0/5명)**. 오래 "평가자 2/5명 진행 중"이라고 적어왔으나 그 2명분 채점 원본이 저장소 어디에도 없다(2026-08-27 확인) — **5명을 새로 받는다.** 평가 설계와 자료는 별도 브랜치에서 준비 중이라 아직 main에 없다 |
| 2 | 9차 학습 로그·노트북 부재 | 배포 중인 체크포인트를 저장소만으로 재현할 수 없다 |
| 3 | `eval/tts_pregen_log.csv`·`utmos_results.csv` 부재 | RTF·UTMOS 원본이 각자 PC와 Colab Drive에만 있다 |
| 4 | ~~미추적 디렉토리 `output/`, `tmp/`~~ | **해소됨 (2026-08-27 확인)** — 두 디렉토리가 더 이상 작업 트리에 없다 |
| 5 | `docs/specs/sample-menu-images.md`가 "착수 전" | 사진 없이 들어온 방문자가 아무것도 못 하는 문제가 그대로다. 이번 제출물의 [합성 메뉴판](assets/sample-menu-synthetic.jpg)을 그대로 쓸 수 있다 |
| 6 | `assets/audio/`의 첨부 오디오 4개가 낡음 | 서비스 캐시(`static/tts_cache`)는 2026-08-27에 한글 표기본으로 교체됐으나, 제출물에 첨부한 4개는 그 이전 파일이다 — 복사만 하면 된다([05. 입출력 결과물](05-io-samples.md) 5절) |
