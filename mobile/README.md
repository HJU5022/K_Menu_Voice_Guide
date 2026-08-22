# mobile/ — Flutter 모바일 앱

K-Menu를 iOS·Android 앱으로 제공하는 클라이언트입니다.

**이 앱은 계산을 하지 않습니다.** OCR·음식 매칭·텍스트 조회·TTS는 전부 서버(`K_Menu_Talk.py`)가 수행하고, 앱은 사진을 보내고 결과를 받아 보여주는 역할만 합니다. `src/` 아래 로직을 복제하지 않습니다.

기능 명세는 [`docs/specs/flutter-mobile-app.md`](../docs/specs/flutter-mobile-app.md)에 있습니다.

## 구조

```
mobile/
├── lib/
│   ├── main.dart                  앱 시작점 + 화면 전환
│   ├── config.dart                서버 주소 — 환경이 바뀌면 여기만 고친다
│   ├── api.dart                   서버 호출 2개 + 응답 파싱
│   └── screens/
│       ├── camera_screen.dart     ① 메뉴판 촬영
│       ├── candidates_screen.dart ② 음식 후보 선택
│       └── detail_screen.dart     ③ 상세 6개 카테고리 + 음성 재생
├── ios/                           iOS 설정 (Info.plist에 카메라 권한·ATS)
├── android/                       Android 설정
└── pubspec.yaml                   패키지 목록
```

화면 3개는 서버 API와 1:1로 대응합니다.

```
camera_screen      ──▶ POST /api/analyze       ──▶ candidates
candidates_screen  ──▶ 사용자가 하나 선택
detail_screen      ──▶ GET /api/foods/{id}     ──▶ details 6개 + 음성 URL
```

## 실행 방법

### 1. 서버를 먼저 띄운다

앱만 켜면 아무것도 안 됩니다. 저장소 루트에서:

```bash
uvicorn K_Menu_Talk:app --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0`이 필요합니다. 기본값(`127.0.0.1`)이면 맥 자신만 접속할 수 있어서 폰이 못 붙습니다.

### 2. 서버 주소를 확인한다

`lib/config.dart`의 `apiBaseUrl`이 실제 서버를 가리켜야 합니다. 맥 로컬 IP는:

```bash
ipconfig getifaddr en0
```

이 값이 바뀌면(Wi-Fi 변경, 공유기 재할당) 앱이 서버를 못 찾습니다. 그때 `config.dart` 한 줄만 고치면 됩니다.

### 3. 앱을 실행한다

**iOS 시뮬레이터** — 화면 작업용. 빠르지만 **카메라가 없어서** 촬영은 시연할 수 없습니다.

```bash
open -a Simulator
```
```bash
cd mobile && flutter run
```

**실제 iPhone** — 카메라가 필요할 때, 그리고 최종 시연용. USB로 맥에 연결한 뒤:

```bash
cd mobile && flutter run
```

무료 Apple ID로 서명하면 설치되지만 **7일 뒤 만료**되므로 다시 설치해야 합니다.

**Android 에뮬레이터** — Android Studio에서 기기를 하나 만들어 실행한 뒤 같은 명령을 씁니다.

### 실행 중 단축키

`flutter run`이 끝나면 터미널이 켜져 있는 상태로 유지됩니다.

| 키 | 동작 |
|---|---|
| `r` | Hot reload — 코드 수정이 1초 안에 화면에 반영 |
| `R` | Hot restart — 앱을 처음부터 다시 시작 |
| `q` | 종료 |

## 자주 겪는 문제

| 증상 | 원인·해결 |
|---|---|
| 촬영 누르자마자 앱이 꺼진다 | `ios/Runner/Info.plist`에 `NSCameraUsageDescription`이 없다 |
| 모든 요청이 실패한다 | iOS가 `http://`를 차단한다. `Info.plist`의 `NSAppTransportSecurity` → `NSAllowsArbitraryLoads` 확인 |
| 서버에 연결 안 됨 | ① 서버가 켜져 있는지 ② `--host 0.0.0.0`로 띄웠는지 ③ 폰과 맥이 같은 Wi-Fi인지 ④ `config.dart`의 IP가 맞는지 |
| 첫 요청이 아주 오래 걸린다 | 서버가 그때 OCR 모델을 메모리에 올린다. 두 번째부터 빨라진다 |
| 음성이 안 나온다 | 응답의 `tts_status`를 확인. `ok`가 아니면 서버 쪽 TTS 문제이며, 텍스트는 정상 표시되어야 한다 |

## 패키지

| 패키지 | 용도 |
|---|---|
| `image_picker` | 카메라 촬영 / 사진첩 선택 |
| `http` | API 호출 |
| `audioplayers` | 내레이션 WAV 재생 |
