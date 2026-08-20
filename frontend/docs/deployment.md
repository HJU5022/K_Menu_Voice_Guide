# Frontend Deployment

## Why

개발 PC에서만 되는 설정이 아니라 실제 배포 환경에서도 같은 프론트 결과물을 실행해야 한다.

## Goal

빌드 전 환경변수를 확인하고, 정적 결과물 배포 후 핵심 화면을 점검한다.

## What

1. 배포 환경에 `VITE_API_BASE_URL`을 설정한다.
2. `npm run build`로 `dist/` 결과물을 생성한다.
3. 정적 웹 호스팅에 `dist/`를 배포한다.
4. 실제 HTTPS 주소에서 카메라·업로드·분석·오류 화면을 확인한다.

## How

```bash
npm install
npm run build
```

- API 주소는 빌드 전에 주입한다.
- `VITE_API_BASE_URL`은 브라우저에 공개되므로 비밀값을 넣지 않는다.
- 선택한 배포 서비스의 빌드 명령·출력 폴더·환경변수 등록 방법은 서비스가 확정되면 이 문서에 추가한다.

## AC (Given-When-Then)

- GIVEN: 의존성과 환경변수가 준비됐다. WHEN: `npm run build`를 실행한다. THEN: 오류 없이 `dist/`가 생성된다.
- GIVEN: HTTPS로 배포됐다. WHEN: 사용자가 카메라를 사용한다. THEN: 권한 요청 또는 업로드 대안이 정상적으로 보인다.
