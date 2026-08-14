"""파이프라인 — ocr / text_gen / tts 블록을 입출력 계약대로 순서대로 연결한다.

입력:  {image_path, selected_food}
출력:  {detail_text(6개), narration_text, narration_audio_path, latency_ms}

K_Menu_Talk.py(배포 진입점)는 이 파일만 호출한다.
블록끼리 서로 직접 import 하지 않고, 연결은 전부 여기서 한다.
"""
