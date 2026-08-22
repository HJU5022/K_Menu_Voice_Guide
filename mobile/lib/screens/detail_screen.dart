/// ③ 상세 화면 — 고른 음식의 설명을 보여주고 내레이션 음성을 재생한다.
///
/// 하는 일
///   1. `GET /api/foods/{food_id}`를 호출한다.
///   2. details의 6개 카테고리를 카드로 표시한다.
///   3. narration_audio_path의 음성을 재생한다(audioplayers).
///
/// 카테고리 6개와 화면 제목은 프론트엔드와 통일한다
/// (`frontend/docs/content-style.md` 기준, app.py의 DETAIL_CARDS와 같은 순서):
///   DESCRIPTION / HOW_TO_EAT / INGREDIENT / ALLERGY / PRONUNCIATION / SPICY
///
/// 음성 URL 주의: 응답의 narration_audio_path는 `/audio/xxx.wav` 같은 상대
/// 경로다. 앞에 apiBaseUrl을 붙여야 재생된다.
///
/// TTS 실패는 화면 실패가 아니다 — tts_status가 "ok"가 아니거나
/// narration_audio_path가 null이면 **텍스트는 그대로 보여주고** 음성 영역만
/// 비활성으로 표시한다(`flutter-mobile-app.md` EC-05, 루트 README 9절
/// "TTS 생성 실패 → 상세 텍스트 우선 출력").
///
/// TODO(구현 예정)
///   - 상세 6개 카테고리 카드
///   - 재생/일시정지 버튼
///   - tts_status != "ok"일 때 음성 영역 비활성 처리 (EC-05)
///   - 음성 다운로드·재생 실패 시 텍스트 유지 + 재생 버튼만 오류 표시 (EC-06)

library;
