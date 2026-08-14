"""TTS 추론 — 배포에서 실제로 쓰이는 쪽. 기본은 라이브 생성.

(내레이션 텍스트 + style) → WAV
TTFB가 목표를 넘으면 pregenerate.py의 사전 생성 캐시로 전환한다.
"""
