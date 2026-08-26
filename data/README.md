# data/

학습·평가에 쓰는 데이터를 두는 곳입니다.

> ⚠️ **데이터 파일 자체는 git에 올리지 않습니다.** 이 README에 "어디서 받아서 어떻게 변환하는지"만 적고, 실제 파일은 각자 로컬에 받습니다. (`.gitignore` 확인)

## 1. AI Hub 데이터 신청

- 신청 링크: (URL 채우기)
- 신청 후 승인까지 걸리는 시간: (채우기)
- 받은 파일을 둘 경로: `data/raw/`

## 2. OCR 학습 라벨 변환 (`rec_gt_train.txt`)

AI Hub 라벨 형식 → PaddleOCR 학습 포맷으로 바꿔야 합니다.

```bash
python -m src.ocr.prepare_dataset
```

PaddleOCR가 요구하는 형식:

```
이미지경로<TAB>정답텍스트
```

- 입력: (AI Hub 원본 라벨 경로)
- 출력: `data/processed/rec_gt_train.txt`

## 3. 커스텀 딕셔너리 파일 생성

등록 음식명 50개에 쓰인 글자만 모은 사전입니다. 인식 후보 글자를 줄여서 정확도를 올리는 용도입니다.

```bash
python -m src.ocr.prepare_dataset
```

- 출력: `data/processed/korean_menu_dict.txt`
- 형식: 한 줄에 글자 하나

## 4. TTS 학습 음성 데이터 (팀원 실제 녹음)

TTS 파인튜닝용 음성은 합성이 아니라 **팀원이 직접 녹음**한 것입니다.

- 구성: 나레이션 50개 + 발음용 캐리어 문장 250개 = 원본 300개
  (CAUTION 클래스 오버샘플링을 적용한 최종 학습셋은 348개)
- 오디오 스펙: 24kHz mono WAV로 통일 (코덱 파이프라인 요구사항)
- 데이터 분할: 80/10/10 (food_id × style 기준 층화 분할)
- 라벨 텍스트: 8차(최종) 학습부터는 리스펠링을 반영한 텍스트를 사용 — [`eval/TTS_MODULE.md`](../eval/TTS_MODULE.md) 4절
- 둘 경로: `data/tts/`

> 🔒 녹음 파일은 개인 음성이므로 **공개 저장소에 올리지 않습니다.** 팀 내부 비공개 저장소/Drive에서 받아 `data/tts/`에 둡니다.
> 음성 사용 동의서 보관 원칙은 [`docs/legal/tts-voice-consent/`](../docs/legal/tts-voice-consent/) 참고.

## 폴더 구조

```
data/
├── raw/          # AI Hub 원본 (git 제외)
├── processed/    # 변환 결과 (git 제외)
└── tts/          # 팀원 녹음 음성 (git 제외)
```
