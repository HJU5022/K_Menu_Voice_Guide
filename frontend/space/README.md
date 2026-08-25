---
title: K-Menu Voice Guide
emoji: 🍲
colorFrom: red
colorTo: yellow
sdk: static
app_file: index.html
pinned: false
---

# K-Menu Voice Guide (웹)

한국 음식 메뉴판 사진을 올리면 영어 설명과 음성 안내를 보여주는 React 화면.

- 계산은 하지 않는다 — 빌드 시 `VITE_API_BASE_URL`에 박아 넣은 FastAPI Space를 HTTP로 호출한다
- 이 Space에 올라오는 것은 `pnpm run build` 결과물(정적 파일)뿐이다. 소스는 GitHub `aihuman-7th/proj1-c`의 `frontend/`에 있다
- 배포 방법: 같은 저장소 `frontend/space/deploy.sh`

## 왜 static SDK인가

이전에는 Streamlit 화면을 `sdk: docker`로 올렸다. React는 빌드 결과가 `index.html` +
JS/CSS 파일뿐이라 실행할 서버가 없다. `static`은 그 파일들을 그대로 서빙하므로 컨테이너
빌드 단계가 사라지고, 배포가 몇 초로 끝난다.
