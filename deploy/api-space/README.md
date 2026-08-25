---
title: K-Menu API
emoji: 🍲
colorFrom: red
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
---

# K-Menu API

한국 음식 메뉴판 사진을 분석해 음식 후보·상세 설명·음성 안내를 돌려주는 FastAPI 서버.

- 진입점: `K_Menu_Talk.py` (`/api/analyze`, `/api/foods/{id}`)
- 웹(Streamlit Space)과 모바일 앱이 이 API를 호출한다
- 배포 구조와 계약: `docs/specs/fastapi-space-deploy.md`, `docs/specs/api-layer.md`
