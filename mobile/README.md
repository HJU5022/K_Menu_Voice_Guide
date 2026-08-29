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
│   ├── api.dart                   서버 호출 + 응답 파싱 (아래 표)
│   └── screens/
│       ├── camera_screen.dart          ① 메뉴판 촬영 (앱을 열면 처음 보이는 화면)
│       ├── candidates_screen.dart      ② 음식 후보 선택 + 장바구니
│       ├── detail_screen.dart          ③ 상세 6개 카테고리 + 음성 재생
│       ├── order_summary_screen.dart   주문 확인 — 종업원에게 보여주는 화면
│       ├── menu_photo_overlay.dart     찍은 사진 위에 후보 자리를 번호 상자로 표시
│       ├── first_run_guide.dart        첫 실행 4단계 안내 (한 번만 뜬다)
│       ├── settings_button.dart        촬영 화면 오른쪽 위 원형 설정 버튼
│       ├── settings_screen.dart        설정 — 안내 항목을 한 줄씩 모아둔 자리
│       ├── supported_foods_screen.dart   안내 가능한 음식 전체 목록
│       ├── how_it_works_screen.dart      사용법·지원 범위·가격 출처
│       ├── credits_screen.dart           사진·데이터 출처 모음
│       ├── spice_gauge.dart              맵기 불꽃 눈금 — 후보 카드와 상세가 같이 쓴다
│       ├── stitch_bar.dart               앱바 아래 공통 장식 바
│       └── animated_gradient_back_button.dart  공통 뒤로가기 버튼
├── ios/                           iOS 설정 (Info.plist에 카메라 권한·ATS)
├── android/                       Android 설정
└── pubspec.yaml                   패키지 목록
```

**주 흐름은 화면 3개**이고 서버 API와 1:1로 대응합니다. 나머지는 그 주위의 보조 화면과 공통 위젯입니다.

```
camera_screen      ──▶ POST /api/analyze       ──▶ candidates
candidates_screen  ──▶ 사용자가 하나 선택
detail_screen      ──▶ GET /api/foods/{id}     ──▶ details 6개 + 음성 URL 2개
```

`api.dart`가 부르는 곳은 여섯 군데입니다.

| 함수 | 요청 |
|---|---|
| `analyze()` | `POST /api/analyze` — 사진 → 후보 목록 |
| `fetchFood()` | `GET /api/foods/{id}` — 상세 + 나레이션·이름 음성 |
| `fetchSupportedFoods()` | `GET /api/foods` — 지원 음식 목록 (설정 화면) |
| `fetchCart()` / `changeCartItem()` / `clearCart()` | `/api/cart…` — 장바구니 (`X-Cart-Id` 헤더 필수) |

화면 사이에 넘기는 것은 매번 줄어듭니다 — 촬영→후보는 후보 목록 전체를, 후보→상세는 고른 `food_id` 하나만 넘깁니다. 상세 화면은 그 번호로 서버에 다시 물어보므로 목록을 들고 갈 이유가 없습니다.

후보 카드에는 음식 사진과 가격이 함께 표시됩니다. 가격은 DB 값이 아니라 **그 메뉴판 사진에 실제로 적혀 있던 값**을 서버가 읽어준 것이라, 못 읽은 후보는 가격 자리가 빕니다.

**사진을 보여주는 자리에는 출처(`thumbnail_attribution`)를 반드시 함께 표시합니다.** 외부 데이터셋 사진을 쓰면서 출처를 남기기로 한 프로젝트 조건이라, 화면을 고칠 때 이 부분이 빠지지 않도록 주의하세요.

상세 화면은 열리자마자 음성을 자동 재생하고, 화면을 떠날 때 재생기를 정리합니다. 정리를 빠뜨리면 뒤로 가도 소리가 계속 납니다.

**소리를 내는 곳은 모두 서버가 만든 캐시 WAV입니다.** 앱은 음성을 합성하지 않고 URL을 받아 재생만 합니다.

| | 내는 것 | 누가 만드나 |
|---|---|---|
| 나레이션 음성 | 음식의 영어 설명 | 우리가 파인튜닝한 모델. 서버가 `narration_audio_path` WAV로 내려준다 (`audioplayers`로 재생) |
| 이름 음성 | 음식 이름만 읽은 짧은 음성 | 같은 모델의 `name_audio_path` 캐시 WAV. 후보·상세 화면의 스피커가 재생한다 |

캐시 파일이 없거나 Space가 일시정지된 경우에는 텍스트는 정상 표시되지만 해당 음성은 재생할 수 없습니다. 앱은 기기 기본 TTS로 대체하지 않습니다.

## 실행 방법

### 1. 서버를 먼저 띄운다 (로컬 서버로 돌릴 때만)

기본값은 배포된 서버(`https://hju5022-k-menu.hf.space`)라, 평소에는 이 단계가 필요 없습니다. 맥에서 고친 서버 코드를 앱으로 확인하고 싶을 때만 띄웁니다. 저장소 루트에서:

```bash
uvicorn K_Menu_Talk:app --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0`이 필요합니다. 기본값(`127.0.0.1`)이면 맥 자신만 접속할 수 있어서 폰이 못 붙습니다.

### 2. 서버 주소를 확인한다

`lib/config.dart`의 `apiBaseUrl`이 실제 서버를 가리켜야 합니다.

| 어디서 돌리나 | 값 |
|---|---|
| **배포 서버** | `https://hju5022-k-menu.hf.space` ← 현재 기본값 |
| iOS 시뮬레이터 / Android 에뮬레이터 (로컬) | `http://localhost:8000` |
| 실제 아이폰 (로컬) | `http://<맥 로컬 IP>:8000` |

시뮬레이터는 맥 안에서 돌기 때문에 `localhost`로 서버에 닿고, 맥의 IP가 바뀌어도 영향을 받지 않습니다. 화면 작업 중에는 이 값이 가장 안정적입니다.

**로컬 서버로 되돌릴 때, 실제 아이폰이라면 맥의 LAN IP로 바꿔야 합니다.** 폰에게 `localhost`는 폰 자신이라 서버를 찾지 못합니다.

```bash
ipconfig getifaddr en0
```

이 값은 Wi-Fi를 옮기거나 공유기가 주소를 다시 할당하면 바뀌고, Wi-Fi가 끊기면 아무것도 출력되지 않습니다. 앱이 "Can't reach the server"를 띄우면 여기부터 확인하세요 — 화면에 현재 주소가 같이 표시됩니다.

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
| `audioplayers` | 서버가 만든 내레이션·이름 WAV 재생 |
| `shared_preferences` | 첫 실행 안내를 닫았는지 기기에 저장 |
| `cupertino_icons` | iOS 스타일 아이콘 |
