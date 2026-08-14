# src/

실제 로직이 들어가는 곳입니다. 배포 진입점(`K_Menu_Talk.py`)은 여기 `pipeline.py`만 호출합니다.

## 블록 구성

| 폴더 | 역할 | 입력 → 출력 |
|---|---|---|
| `ocr/` | 메뉴판에서 음식 찾기 | 이미지 → 음식 후보 목록 |
| `text_gen/` | 설명 텍스트 만들기 | 음식 → 상세 텍스트 6개 + 내레이션 텍스트 1개 |
| `db/` | Supabase 데이터 접근 | 쿼리 → 레코드 |
| `tts/` | 음성 만들기 | 내레이션 텍스트 + 스타일 → WAV |

## pipeline.py 입출력 계약

블록끼리는 이 계약으로만 연결됩니다. 각 블록은 **자기 입출력만 지키면** 내부 구현을 자유롭게 바꿔도 됩니다.

```
입력:  { image_path, selected_food }
출력:  { detail_text(6개), narration_text, narration_audio_path, latency_ms }
```

## 작업 원칙

- 새 기능은 `docs/specs/{기능명}.md`를 먼저 쓰고 구현합니다.
- 블록 간 직접 import 대신 `pipeline.py`를 통해 연결합니다.
