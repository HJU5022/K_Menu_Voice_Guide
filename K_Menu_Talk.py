"""배포 진입점 — Gradio 화면을 띄우고 src/pipeline.py만 호출한다.

이 파일에는 화면(UI) 코드만 둔다. OCR·텍스트·TTS 로직은 전부 src/ 아래에 있고,
여기서는 pipeline.run()의 입출력만 다룬다.
"""
