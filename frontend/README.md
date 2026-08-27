# K-Menu Frontend

영어권 관광객이 한국 메뉴판 사진을 촬영하거나 업로드하고, 인식한 음식 후보와 음식 안내를 보는 React + TypeScript 웹 화면입니다.

## 범위

- 카메라·사진 업로드, 분석 대기, 음식 후보 선택(장바구니 포함), 주문 요약, 음식 상세·오류 화면을 제공한다.
- API 주소는 `VITE_API_BASE_URL` 환경변수로만 받는다 (`client/src/lib/api.ts`).
- API 내부 구현·모델·비밀값은 이 프론트엔드 폴더의 범위가 아니다 — 백엔드는 `K_Menu_Talk.py`(FastAPI)를 그대로 호출한다.

## 실행과 빌드

```bash
pnpm install
pnpm run dev     # http://localhost:3000
pnpm run build
```

개발 환경에서 `frontend/.env`에 백엔드 주소를 설정한다.

```env
VITE_API_BASE_URL=http://localhost:8000
```

`VITE_` 값은 브라우저에 포함될 수 있으므로 토큰·비밀번호·개인 키를 넣지 않는다.

## 구조

```
frontend/
├── client/
│   ├── index.html          진입 HTML — main.tsx 하나만 부른다
│   ├── public/assets/      배경 이미지 (종이 질감·메뉴판·문)
│   └── src/
│       ├── main.tsx        React를 #root에 붙인다. 5줄짜리 시작점
│       ├── App.tsx         앱 껍데기 — 경로 배정(wouter)과 전역 장치(토스트·툴팁·오류 울타리)
│       ├── pages/
│       │   ├── Home.tsx      화면 상태 전부를 쥐고 있는 곳 (촬영·후보·상세·장바구니)
│       │   ├── Landing.tsx   첫 소개 화면. 껍데기는 Home이 씌운다
│       │   └── NotFound.tsx  없는 주소
│       ├── lib/
│       │   ├── api.ts        백엔드와 HTTP로 말하는 유일한 모듈
│       │   └── utils.ts      클래스 이름 합치기(cn) 한 개
│       ├── i18n.ts         화면 문구 영어·한국어 두 벌 (음식 설명은 여기 없다 — 서버가 준다)
│       ├── lang.tsx        고른 언어를 화면 전체가 함께 보게 하는 통로
│       ├── contexts/       테마(밝게·어둡게)
│       ├── components/
│       │   ├── ErrorBoundary.tsx  화면이 통째로 죽는 대신 안내를 띄운다
│       │   └── ui/               버튼·카드·토스트·툴팁 (shadcn 방식으로 파일째 들여온 것)
│       └── index.css       Tailwind와 디자인 토큰
├── space/deploy.sh         HF Static Space 배포 (빌드 + 통째로 덮어쓰기)
└── docs/                   화면 기준 문서 — 읽는 순서는 아래
```

두 파일만 기억하면 된다. **`pages/Home.tsx`가 화면 상태**를 전부 쥐고 있고,
**`lib/api.ts`가 백엔드 계약**이다. 나머지는 이 둘을 거드는 것들이다.

계산은 하지 않는다 — 후보를 고르는 것도 음성을 만드는 것도 서버가 한다. 화면은 받은 값을
그리기만 한다.

## 문서 읽는 순서

1. [docs/ux-ui-integration.md](docs/ux-ui-integration.md) — 현재 화면·API 경계의 기준
2. [docs/ui-flow.md](docs/ui-flow.md) — 전체 사용자 흐름
3. [docs/screen-spec.md](docs/screen-spec.md) — 화면별 요소·상태
4. [docs/api-client.md](docs/api-client.md) — API 호출 규칙
5. [../docs/content-style.md](../docs/content-style.md) — 영어 문구 기준 (웹·앱 공통이라 저장소 공통 문서에 있다)
6. [docs/deployment.md](docs/deployment.md) — 배포 절차

이 docs 폴더는 화면 재구현(마누스, Hanok Editorial 디자인) 이전에 작성된 원본 기준 문서다 — 정보 구조·문구 규칙은 여전히 유효하며, 실제 컴포넌트 구현은 `client/src/pages/Home.tsx`를 따른다.
