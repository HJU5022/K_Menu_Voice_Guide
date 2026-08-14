# src/text_gen/

**음식 ──▶ 상세 텍스트 6개 + 내레이션 텍스트 1개**

선택된 음식의 설명을 DB에서 조회해 화면용 카드와 음성용 문장으로 만듭니다.

## 파일

| 파일 | 역할 |
|---|---|
| `detail.py` | `food_details` 6개 카테고리 조회·카드 조합 |
| `narration.py` | `spice_level` → `style`(GUIDE/CAUTION) 자동 결정 + `narration_text` 조회 |

## 흐름

```
음식 ┬→ detail.py    → 상세 텍스트 6개 (화면 표시용)
     └→ narration.py → 내레이션 텍스트 1개 + style (TTS 입력용)
```

`narration.py`가 정한 `style`은 `src/tts/`로 그대로 넘어가 목소리 톤을 결정합니다.

## 주의

텍스트를 **생성(generate)하지 않습니다.** 이미 Supabase에 들어있는 문장을 조회해서 조합할 뿐입니다. 새 문장을 만들어내는 로직이 필요해지면 Spec부터 다시 씁니다.

## 관련 문서

- Spec: [`docs/specs/text-generation.md`](../../docs/specs/text-generation.md)
- 데이터 접근: [`src/db/README.md`](../db/README.md)
