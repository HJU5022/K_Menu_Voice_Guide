# FastAPI Space(HF Docker SDK, T4)용 이미지 — 결정 배경과 계약은
# docs/specs/fastapi-space-deploy.md 참고.
FROM python:3.11-slim

# opencv가 slim 이미지에서 요구하는 시스템 라이브러리 + soundfile이 쓰는 libsndfile,
# 그리고 build-essential(gcc). torch가 GPU 커널 일부를 실행 시점에 Triton으로 즉석
# 컴파일하는데 slim 이미지에는 C 컴파일러가 없어 "Failed to find C compiler"로 TTS가
# 죽는다(실측 2026-08-24). 개발 PC는 CPU 빌드 torch라 이 경로를 타지 않아 드러나지 않았다.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 libsndfile1 build-essential \
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

# TTS는 별도 가상환경에 둔다 — 한 환경에 합칠 수 없다.
# paddlepaddle-gpu는 nvidia-*-cu12 패키지를 정확한 버전으로 고정하는데(cublas 12.9.0.13 등),
# 요즘 torch도 같은 패키지를 다른 버전으로 고정한다. 둘을 함께 설치하면 pip이 충돌을 피해
# torch를 계속 낮추다 cu11 시절인 2.0.1까지 내려가고, 그 torch는 numpy 2.x와 호환되지 않아
# TTS 로딩이 통째로 깨진다(실측 2026-08-24). 워커는 paddle을 전혀 임포트하지 않으므로
# (src/tts/worker.py) 환경을 갈라두면 서로 간섭하지 않는다 — 맥·Windows의 .venv-tts와 같은 구조다.
RUN python -m venv /home/user/venv-tts \
    && /home/user/venv-tts/bin/pip install --no-cache-dir \
    torch qwen-tts peft transformers safetensors soundfile huggingface_hub numpy
ENV TTS_VENV_PYTHON=/home/user/venv-tts/bin/python

COPY --chown=user . .

EXPOSE 7860
CMD ["uvicorn", "K_Menu_Talk:app", "--host", "0.0.0.0", "--port", "7860"]
