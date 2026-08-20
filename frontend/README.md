# K-Menu Frontend

영어권 관광객이 한국 메뉴판 사진을 촬영하거나 업로드하고, 인식한 음식 후보와 음식 안내를 보는 React + TypeScript 웹 화면입니다.

## 범위

- 카메라·사진 업로드, 분석 대기, 음식 후보 선택, 음식 상세·오류 화면을 제공한다.
- API 주소는 `VITE_API_BASE_URL` 환경변수로만 받는다.
- API 내부 구현·모델·비밀값은 이 프론트엔드 폴더의 범위가 아니다.

## 실행과 빌드

```bash
npm install
npm run dev
npm run build
```

개발 환경에서만 `frontend/.env`에 공개 가능한 API 주소를 설정한다.

```env
VITE_API_BASE_URL=https://api.example.com
```

`VITE_` 값은 브라우저에 포함될 수 있으므로 토큰·비밀번호·개인 키를 넣지 않는다.

## 문서 읽는 순서

1. [docs/ux-ui-integration.md](docs/ux-ui-integration.md) — 현재 화면·API 경계의 기준
2. [docs/ui-flow.md](docs/ui-flow.md) — 전체 사용자 흐름
3. [docs/screen-spec.md](docs/screen-spec.md) — 화면별 요소·상태
4. [docs/api-client.md](docs/api-client.md) — API 호출 규칙
5. [docs/content-style.md](docs/content-style.md) — 영어 문구 기준
6. [docs/deployment.md](docs/deployment.md) — 배포 절차
7. [src/README.md](src/README.md) — 소스 파일 역할·주석 원칙
