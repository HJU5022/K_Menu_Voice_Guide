/// 메뉴 이름을 **한국어로** 읽어주는 스피커.
///
/// ## 우리 TTS 모델과 다른 물건이다
///
/// 이 앱에는 소리를 내는 곳이 두 군데다.
///
///   나레이션  팀이 파인튜닝한 모델(Qwen3-TTS + LoRA)이 만든 **영어 설명**.
///             서버가 미리 만들어 wav로 내려준다.
///   이름 발음  **기기에 원래 있는 음성**이 읽는 한국어 이름. 여기가 그거다.
///
/// 우리 모델은 영어 설명을 읽도록 학습시킨 것이라 한국어 음식명을 한국어로
/// 발음하지 못한다. 그리고 등록 안 된 메뉴는 애초에 읽을 대본 자체가 없다.
/// 반면 기기 음성은 글자만 주면 무엇이든 읽고, 서버를 안 거치니 즉시 나온다.
///
/// 웹앱도 같은 구조다 — `frontend/src/App.tsx`가 브라우저 내장
/// `speechSynthesis`에 `lang: "ko-KR"`로 이름을 읽힌다. iOS에는 그에 해당하는
/// Flutter 기본 API가 없어서 flutter_tts(운영체제 음성을 부르는 얇은 껍데기)를 쓴다.
///
/// ## 무엇에 쓰나
///
/// 설명이 없는 메뉴에서 특히 값어치가 있다. 두루치기가 무엇인지는 못 알려줘도
/// **"두루치기"라고 소리 내주면 종업원에게 말할 수 있다.**
library;

import 'package:flutter_tts/flutter_tts.dart';

/// 앱 전체가 하나를 같이 쓴다. 여러 화면이 각자 만들면 서로 말을 끊지 못해
/// 두 목소리가 겹쳐 나온다.
final KoreanSpeaker koreanSpeaker = KoreanSpeaker();

class KoreanSpeaker {
  final FlutterTts _tts = FlutterTts();
  bool _ready = false;

  Future<void> _prepare() async {
    if (_ready) return;
    await _tts.setLanguage('ko-KR');
    // 메뉴 이름은 짧고 낯선 단어라 기본 속도로는 흘려듣기 쉽다. 조금 늦춘다.
    await _tts.setSpeechRate(0.45);
    _ready = true;
  }

  /// 한국어 글자를 소리 내어 읽는다.
  ///
  /// 이전 읽기를 끊고 새로 시작한다 — 카드를 연달아 누르면 목소리가 겹친다.
  /// 실패해도 예외를 올리지 않는다. 발음은 덤이라, 안 되더라도 화면이 멈추면 안 된다.
  Future<void> speak(String text) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty) return;
    try {
      await _prepare();
      await _tts.stop();
      await _tts.speak(trimmed);
    } catch (_) {
      // 기기에 한국어 음성이 없거나 TTS가 막혀 있는 경우다. 조용히 넘어간다.
    }
  }

  /// 화면을 떠날 때 부른다 — 안 멈추면 다음 화면에서도 계속 말한다.
  Future<void> stop() async {
    try {
      await _tts.stop();
    } catch (_) {}
  }
}
