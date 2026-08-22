/// 서버(`K_Menu_Talk.py`) 호출을 모아두는 곳.
///
/// 화면(screens/)은 http 패키지를 직접 쓰지 않고 이 파일의 함수만 부른다 —
/// 엔드포인트 경로나 응답 모양이 바뀌었을 때 고칠 곳을 한 군데로 묶기 위함이다.
///
/// 서버가 제공하는 것은 두 개뿐이다(`docs/specs/api-layer.md`):
///
///   POST /api/analyze          이미지(multipart, 필드명 "image") ──▶ 음식 후보 목록
///   GET  /api/foods/{food_id}  음식 id ──▶ 상세 6개 카테고리 + 내레이션 음성 경로
///
/// 주의: 응답의 `narration_audio_path`는 `/audio/xxx.wav` 형태의 상대 경로다.
/// 재생하려면 `apiBaseUrl`을 앞에 붙여 완전한 URL로 만들어야 한다.
///
/// TODO(구현 예정)
///   - Candidate      : food_id, name_kr, name_en, score, modifiers
///   - FoodDetail     : details(6개), narration_text, style,
///                      tts_status, narration_audio_path, tts_latency_ms
///   - analyze(File)  : POST /api/analyze
///   - fetchFood(int) : GET /api/foods/{food_id}
///
/// 실패 처리 기준(`docs/specs/flutter-mobile-app.md` EC-02·EC-05):
///   - 연결 실패는 예외를 던져 화면이 재시도 UI를 띄우게 한다.
///   - TTS 실패(`tts_status != "ok"`)는 예외가 아니다. 상세 텍스트는 그대로 쓰고
///     음성 영역만 비활성으로 표시한다.

library;
