# models/

> ⚠️ **모델 파일(가중치)은 git에 올리지 않습니다.** 용량이 크기 때문에 Hugging Face Hub에 올리고, 여기에는 **모델 ID만** 기록합니다.

## 체크포인트 목록

| 용도 | HF Hub 모델 ID | 베이스 모델 | 비고 |
|---|---|---|---|
| OCR (파인튜닝) | [`HJU5022/K_Bite_OCR`](https://huggingface.co/HJU5022/K_Bite_OCR) | korean_PP-OCRv5_mobile_rec | **export(배포용 정적 변환) 없이 원본 체크포인트(`best_accuracy.pdparams`) + `dict.txt` 그대로 업로드함 — 이유는 `docs/specs/ocr-finetuning.md`의 "구현 변경 이력" 참고** |
| TTS (파인튜닝) | | | LoRA/PEFT |

## 불러오는 곳

- OCR: `src/ocr/infer.py` (원본 체크포인트를 `src/ocr/vendor/ppocr/`로 직접 로드 — 아래 참고)
- TTS: `src/tts/infer.py`

## 기록할 때 같이 남길 것

새 체크포인트를 올리면 위 표에 한 줄 추가하고, 아래도 같이 적어주세요.

- 학습에 쓴 안 (1안 전체학습 / 2안 LoRA·QLoRA / 3안 mobile+양자화)
- 학습 데이터 버전
- 평가 결과 → `eval/model_comparison.md`에 기록
