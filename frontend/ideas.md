# K-menu Voice Guide 디자인 브레인스토밍

## Approach 1 — Hanok Editorial
**Very Brief Intro:** 따뜻한 크림 종이와 깊은 틸, 절제된 코랄을 사용하는 여행 매거진형 인터페이스다. 한식 메뉴를 해석하는 경험을 조용하고 신뢰감 있게 만든다.
**Probability:** 0.06

## Approach 2 — Market Signal
**Very Brief Intro:** 전통 시장의 가격표와 메뉴판에서 영감을 받은 고대비 정보 인터페이스다. 빠른 스캔과 후보 비교를 강조하고, 실용적인 리듬을 만든다.
**Probability:** 0.04

## Approach 3 — Neon Seoul Night
**Very Brief Intro:** 어두운 배경과 코랄·틸 발광 포인트를 활용하는 야간 여행 앱 방향이다. 카메라 스캔과 음성 안내를 미래적인 도구처럼 표현한다.
**Probability:** 0.02

# Chosen Direction — Hanok Editorial

## Design Movement
현대적인 에디토리얼 디자인과 한국 전통 종이 질감의 결합. 여행자가 메뉴를 해석하는 순간을 작은 문화 잡지의 한 페이지처럼 느끼게 한다.

## Core Principles
1. **읽기 쉬운 위계:** 종업원에게 보여줄 한국어 이름은 가장 크게, 영어 설명은 명료하게 보조한다.
2. **따뜻한 신뢰:** 크림 표면, 깊은 틸, 절제된 웜 섀도로 기본 상태를 차분하게 만든다.
3. **안전 정보의 분리:** 알레르기 정보는 코랄 경고 밴드와 별도 아이콘으로 즉시 식별한다.
4. **행동의 명료함:** 촬영, 업로드, 담기, 주문의 단계마다 하나의 주 행동만 둔다.

## Color Philosophy
크림은 종이 메뉴와 환대의 감각을, 딥 틸은 번역·안내의 신뢰를, 코랄은 식욕과 주의 환기를 상징한다. 색은 장식보다 상태와 행동의 의미를 전달하는 데 사용한다.

## Layout Paradigm
중앙 정렬 랜딩보다 **좌측 정보 리듬 + 우측 시각 앵커**를 기본으로 한다. 후보 화면은 데스크톱에서 메뉴 카드와 카트를 나란히 두고, 결과 화면은 큰 한국어 제목에서 6개 정보 카드로 내려가는 세로 편집 레이아웃을 사용한다.

## Signature Elements
- 메뉴판 모서리를 연상시키는 얇은 코랄 스캔 코너.
- 카드 상단의 작은 대문자 에디토리얼 라벨과 점선 구분선.
- 틸 잉크가 번진 듯한 미세한 종이 텍스처와 작은 코랄 스파크.

## Interaction Philosophy
인터랙션은 빠르고 정중해야 한다. 선택된 후보는 틸 아웃라인과 부드러운 표면 변화로 드러내며, 수량 스테퍼는 즉시 카트 전체 상태를 갱신한다. 카메라·업로드·주문 같은 중요한 행동은 누른 순간 명확한 피드백을 제공한다.

## Animation
페이지 진입 시 제목과 카드가 40ms 간격으로 짧게 올라온다. 버튼은 160ms 안에 눌림 피드백을 주고, 모달은 240ms 동안 0.96 스케일에서 등장한다. 장식 요소는 이동을 최소화하고, `prefers-reduced-motion` 환경에서는 비필수 모션을 제거한다.

## Typography System
헤드라인은 `DM Serif Display`를 사용해 메뉴와 매거진의 인상을 만든다. 본문과 UI는 `Manrope`를 사용해 작은 영어 라벨과 숫자를 또렷하게 유지한다. 한국어는 시스템 산세리프 폴백을 사용하고, 제목은 굵기보다 크기와 행간으로 위계를 만든다.

## Brand Essence
한국 메뉴를 읽기 어려운 여행자를 위한 차분하고 안전한 음식 안내 도구. **다정한, 명료한, 문화적인.**

## Brand Voice
헤드라인은 짧고 자신감 있게, CTA는 동사로 시작하며, 안전 문구는 단정하되 겁주지 않는다.

- “Scan a Korean menu.”
- “A clearer way to choose dinner.”

## Wordmark & Logo
워드마크는 하이픈을 중심으로 앞뒤의 글자 간격을 다르게 두고, 심볼은 말풍선 안에 놓인 한식 그릇의 곡선으로 구성한다. 텍스트를 로고 이미지에 억지로 넣지 않고, 생성된 심볼을 헤더와 파비콘에 사용한다.

## Signature Brand Color
**Deep Jeju Teal `#155E63`** — 음식 안내와 번역의 신뢰를 대표하는 고유 색상.

## Asset References
- Hero/menu visual: `/manus-storage/kmenu-menu-table_804752eb.jpg`
- Dish detail visual: `/manus-storage/kmenu-banchan-detail_68c7ee30.jpg`
- Paper texture: `/manus-storage/kmenu-paper-texture_52ea9638.jpg`
- Brand mark: `/manus-storage/kmenu-mark_ba19d191.png`

## Style Decisions

이번 패치에서는 한국 전통성이 은유에 머물지 않도록 오방색 띠를 주요 화면 전환부와 주문 요약 상단에 실제 장식으로 사용한다. 브랜드 심볼은 청·적 원형 링과 단순화한 태극 곡선으로 처리하고, 스캔 코너에는 코랄 포인트와 `MENU PLATE` 에디토리얼 라벨을 결합한다. 처리 화면에는 저채도 기와 곡선 패턴을 배경에만 배치하며, 본문 가독성을 위해 장식은 텍스트 뒤에 겹치지 않게 한다. 한글 음식명은 Noto Serif KR/Song Myung 계열로, 영문 헤드라인은 DM Serif Display로 분리한다. 알레르기 카드는 먹색 테두리와 단청 주홍색을 함께 사용해 안전 정보의 대비를 높인다.
