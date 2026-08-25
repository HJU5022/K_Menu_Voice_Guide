# FastAPI Space(HF Docker SDK, T4)용 이미지 — 결정 배경과 계약은
# docs/specs/fastapi-space-deploy.md 참고.
# 이미지를 **숫자(digest)로 못 박는다.** `python:3.11-slim`은 고정된 이미지가 아니라
# "그때그때 최신"을 가리키는 이름표라, 도커 쪽에서 그 이름표를 옮겨 달면 우리 빌드도
# 조용히 다른 환경으로 바뀐다. 2026-08-25에 실제로 그 일이 났다 — 데비안이 통째로 올라가며
# 캐시가 전부 무효가 됐고, 그 바람에 2.9GB짜리 paddlepaddle-gpu를 다시 받다가 실패했다.
# 코드를 한 줄도 안 바꿨는데 어제 되던 빌드가 오늘 깨지는 상황을 막는다.
# 값은 마지막으로 배포에 성공한 이미지다. 올릴 때는 의도적으로, 한 번에 하나씩.
FROM python:3.11-slim@sha256:9c900dea9e8fb7e16277c179b555cc72d29a352dbc33cff48ad5a0412fd5bfc7

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
# paddlepaddle-gpu 한 개가 **2.9GB**이고 중국 CDN(paddle-whl.cdn.bcebos.com)에서 받는다.
# 기본 시간 제한(15초)으로는 중간에 한 번만 느려져도 통째로 끊긴다 — 실제로 1.3GB에서
# ReadTimeout으로 빌드가 실패했다(2026-08-25). 넉넉히 기다리고, 끊기면 다시 시도한다.
RUN pip install --no-cache-dir --default-timeout=300 --retries 10 -r requirements.txt

# TTS는 별도 가상환경에 둔다 — 한 환경에 합칠 수 없다.
# paddlepaddle-gpu는 nvidia-*-cu12 패키지를 정확한 버전으로 고정하는데(cublas 12.9.0.13 등),
# 요즘 torch도 같은 패키지를 다른 버전으로 고정한다. 둘을 함께 설치하면 pip이 충돌을 피해
# torch를 계속 낮추다 cu11 시절인 2.0.1까지 내려가고, 그 torch는 numpy 2.x와 호환되지 않아
# TTS 로딩이 통째로 깨진다(실측 2026-08-24). 워커는 paddle을 전혀 임포트하지 않으므로
# (src/tts/worker.py) 환경을 갈라두면 서로 간섭하지 않는다 — 맥·Windows의 .venv-tts와 같은 구조다.
#
# **torch와 torchaudio는 버전을 못 박는다.** 둘은 같은 버전 번호끼리만 맞물린다 —
# qwen-tts가 torchaudio를 끌어오는데, 버전을 안 적어두면 빌드하는 날의 최신을 각각
# 집어와 짝이 깨진다. 실제로 2026-08-26 빌드가 torch 2.13.0 + torchaudio 2.11.0을
# 설치했고, 같은 어긋남을 Windows에서 겪었을 때는 qwen_tts 임포트가
# `OSError: [WinError 127]`로 죽어 TTS가 통째로 멈췄다(로딩 실패라 캐시가 있으면
# 증상이 안 보인다 — 실시간 생성만 조용히 죽는다).
# 값은 그 Windows GPU에서 실제로 음성 생성까지 확인한 조합이다.
RUN python -m venv /home/user/venv-tts \
    && /home/user/venv-tts/bin/pip install --no-cache-dir --default-timeout=300 --retries 10 \
    "torch==2.6.0" "torchaudio==2.6.0" qwen-tts peft transformers safetensors soundfile huggingface_hub numpy
ENV TTS_VENV_PYTHON=/home/user/venv-tts/bin/python

COPY --chown=user . .

EXPOSE 7860
CMD ["uvicorn", "K_Menu_Talk:app", "--host", "0.0.0.0", "--port", "7860"]
