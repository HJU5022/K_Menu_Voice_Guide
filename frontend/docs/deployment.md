# Frontend Deployment

## Why

개발 PC에서만 되는 설정이 아니라 실제 배포 환경에서도 같은 프론트 결과물을 실행해야 한다.

## Goal

빌드 전 환경변수를 확인하고, 정적 결과물 배포 후 핵심 화면을 점검한다.

## What

배포처는 **Hugging Face의 무료 static Space**로 정해졌다(`hajeongun/K_Menu_react`). 계산은 전부
GPU API Space가 하고 여기에는 빌드 결과물만 올린다 — 화면 쪽에도 계산을 두면 GPU 비용이 두 배가
되기 때문이다. static SDK는 컨테이너 빌드 단계가 없어 배포가 몇 초에 끝난다.

1. 빌드할 때 `VITE_API_BASE_URL`에 API Space 주소를 넣는다.
2. `pnpm run build`가 `frontend/dist/public/`에 정적 파일을 만든다.
3. 그 폴더의 내용과 Space 설정 `README.md`를 대상 Space에 통째로 덮어쓴다.
4. 배포된 HTTPS 주소에서 촬영·업로드·분석·오류 화면을 확인한다.

## How

**보통은 스크립트 하나면 된다.** 빌드와 업로드를 같이 한다.

```bash
frontend/space/deploy.sh
```

```bash
frontend/space/deploy.sh hajeongun/K_Menu_react https://다른-api-주소
```

인자는 `[Space ID] [API 주소]`이고 기본값은 `hajeongun/K_Menu_react` · `https://hajeongun-k-menu.hf.space`다.

> 2026-08-27 이전에는 기본값이 `HJU5022/K_Menu_Web`이었는데 **그 이름의 Space는 없다.**
> 인자 없이 실행하면 존재하지 않는 곳으로 올리려다 실패했다. 실제 서비스 중인 웹은
> `K_Menu_react` 한 곳이다.
처음 한 번은 HF 로그인이 필요하다(토큰은 write 권한, git이 물으면 비밀번호 자리에 넣는다).

손으로 빌드만 할 때:

```bash
cd frontend && pnpm install && pnpm run build
```

- **서버 주소는 빌드 시점에 JS 안에 박힌다**(Vite의 `VITE_` 규칙). Space에 환경변수를 넣어도
  바뀌지 않으므로, 주소를 바꾸려면 **다시 빌드해야 한다.**
- 출력 폴더는 `frontend/dist/public`이다(`vite.config.ts`의 `build.outDir`). `dist/`가 아니다.
- 패키지 매니저는 **pnpm**이다(`package.json`의 `packageManager`). `wouter` 패치가
  `pnpm.patchedDependencies`에 걸려 있어 npm으로 설치하면 그 패치가 적용되지 않는다.
- `VITE_API_BASE_URL`은 브라우저에 그대로 실리므로 비밀값을 넣지 않는다.
- 배포는 대상 Space를 **통째로 덮어쓴다**(`git push --force`). 소스는 GitHub에 있고 Space에는
  산출물만 둔다 — 되돌릴 일이 생기면 그 시점 소스를 다시 빌드해 올린다.
- 배경 이미지는 Git LFS로 올린다. HF가 일반 git으로 올라오는 바이너리를 거부하기 때문이며,
  `deploy.sh`가 `.gitattributes`를 먼저 써서 처리한다.
- 확인 주소는 일반 Space와 도메인이 다르다 — 가운데에 `.static`이 들어간다
  (`https://hajeongun-k-menu-react.static.hf.space`).

**재배포 없이 다른 서버를 보게 하는 장치**: 주소창에 `?api=https://...`를 붙이면 그 주소를 대신
쓰고 브라우저에 기억한다(`?api=`만 붙이면 원래 주소로 복귀). 시연 중 API Space가 죽었을 때 개인
GPU 터널로 옮기는 용도다. **이 브라우저에서만** 적용되고, https 페이지는 http 주소를 부를 수
없으므로 넘기는 주소도 https여야 한다.

**화면마다 URL을 만들지 않는다** — static Space에는 SPA fallback이 없어 `/landing` 같은 경로는
새로고침 한 번에 404가 된다(`ui-flow.md`).

## AC (Given-When-Then)

- GIVEN: 의존성과 `VITE_API_BASE_URL`이 준비됐다. WHEN: `pnpm run build`를 실행한다. THEN: 오류 없이 `frontend/dist/public/index.html`이 생성된다.
- GIVEN: `frontend/space/deploy.sh`를 실행했다. WHEN: `https://<space>.static.hf.space`를 연다. THEN: 소개 화면이 뜨고, 사진을 올리면 빌드에 박아 넣은 API 주소로 요청이 나간다.
- GIVEN: HTTPS로 배포됐다. WHEN: 사용자가 카메라를 사용한다. THEN: 권한 요청 또는 업로드 대안이 정상적으로 보인다.
- GIVEN: 배포된 화면이다. WHEN: 주소 끝에 `?api=https://다른-서버`를 붙인다. THEN: 재배포 없이 그 서버를 호출하고, 기본값이 아님을 화면이 알린다.
