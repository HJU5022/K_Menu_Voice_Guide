# src/

실제 로직이 들어가는 곳입니다. 배포 진입점(`K_Menu_Talk.py`)은 여기 `pipeline.py`만 호출합니다.

## 블록 구성

| 폴더 | 역할 | 입력 → 출력 |
|---|---|---|
| `ocr/` | 메뉴판에서 음식 찾기 | 이미지 → 음식 후보 목록 |
| `text_gen/` | 설명 텍스트 만들기 | 음식 → 상세 텍스트 6개 + 내레이션 텍스트 1개 |
| `db/` | Supabase 데이터 접근 | 쿼리 → 레코드 |
| `tts/` | 음성 만들기 | 내레이션 텍스트 + 스타일 → WAV |
| `cart/` | 장바구니 상태 | 메뉴 줄 + 수량 증감 → 카트 전체 상태 |

`cart/`만 `pipeline.py`를 거치지 않는다 — 파이프라인의 한 단계가 아니라 별도 상태 저장소라
`K_Menu_Talk.py`가 직접 부른다(`docs/specs/cart.md`).

## pipeline.py 입출력 계약

블록끼리는 이 계약으로만 연결됩니다. 각 블록은 **자기 입출력만 지키면** 내부 구현을 자유롭게 바꿔도 됩니다.

사용자가 후보 중 하나를 고르는 흐름이라, 함수가 두 개로 나뉘어 있습니다. 사진을 받는 시점에는 어떤 음식인지 아직 모르기 때문에, 후보만 먼저 돌려주고 **선택된 뒤에야** 무거운 TTS를 돌립니다.

| 함수 | 입력 | 출력 |
|---|---|---|
| `analyze_image(image_path)` | 메뉴판 이미지 경로 | `{ status, ocr_text, candidates[] }` |
| `create_tts_response(food_id)` | 선택된 음식 id | `{ narration_text, style, narration_audio_path, tts_status, tts_latency_ms, name_audio_path, name_tts_status }` |

`status`는 네 가지이고, 프론트가 이 값으로 어떤 화면을 보여줄지 정합니다.

| 값 | 뜻 |
|---|---|
| `candidates_found` | 후보를 찾음 |
| `ocr_empty` | 글자를 하나도 못 읽음 |
| `not_a_menu` | 글자는 읽혔지만 가격 붙은 메뉴 줄이 없음 — **다시 찍으면 해결된다** |
| `unsupported_food` | 메뉴 줄은 있으나 등록 음식과 매칭 실패 — 다시 찍어도 같다 |

음성은 두 갈래입니다 — `narration_audio_path`(설명 전체)와 `name_audio_path`(이름만). 화면이
이름 옆 스피커와 아래 재생바에 각각 겁니다.

> `run(image_path)`도 남아있습니다 — 사용자 선택 없이 1등 후보로 바로 끝까지 가는 초기 버전이며, 현재 API 경로에서는 쓰지 않습니다.

## 작업 원칙

- 새 기능은 `docs/specs/{기능명}.md`를 먼저 쓰고 구현합니다.
- 블록 간 직접 import 대신 `pipeline.py`를 통해 연결합니다.
