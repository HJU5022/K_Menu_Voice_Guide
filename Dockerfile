# FastAPI Space(HF Docker SDK, T4)용 이미지 — 결정 배경과 계약은
# docs/specs/fastapi-space-deploy.md 참고.
FROM python:3.11-slim

# opencv가 slim 이미지에서 요구하는 시스템 라이브러리
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# HF Spaces는 컨테이너를 uid 1000 비루트로 실행한다 — 앱과 캐시 경로(~/.cache,
# static/audio)가 이 사용자 소유가 아니면 모델 다운로드·음성 저장이 전부 실패한다.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH
WORKDIR /home/user/app

# requirements만 먼저 복사한다 — 코드가 바뀌어도 이 레이어(GPU 빌드 포함 수 GB)는
# 캐시돼 재빌드가 몇 분에서 몇 초로 준다.
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .

# TTS 워커를 서버와 같은 파이썬으로 돌린다(src/pipeline.py가 이 변수를 우선 읽는다).
# 별도 venv 기본값은 Windows/맥의 paddle·torch DLL 충돌 회피용이라 리눅스엔 불필요하다.
ENV TTS_VENV_PYTHON=python3

EXPOSE 7860
CMD ["uvicorn", "K_Menu_Talk:app", "--host", "0.0.0.0", "--port", "7860"]
