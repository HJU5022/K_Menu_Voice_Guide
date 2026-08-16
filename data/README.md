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

## 4. gTTS 학습 스크립트 실행

TTS 파인튜닝용 음성 데이터를 gTTS로 만듭니다.

```bash
# (실행 명령 채우기)
```

- 출력: `data/tts/`

## 폴더 구조

```
data/
├── raw/          # AI Hub 원본 (git 제외)
├── processed/    # 변환 결과 (git 제외)
└── tts/          # gTTS 생성 음성 (git 제외)
```
