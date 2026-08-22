/// 앱의 시작점.
///
/// 하는 일은 두 가지뿐이다 — 앱 전체에 공통으로 적용할 것(제목·색)을 정하고,
/// 첫 화면을 지정한다. 실제 기능은 screens/ 아래 각 화면이 갖는다.
///
/// ── Flutter 기본 개념 ──────────────────────────────────────────────
/// Flutter에서 화면에 보이는 모든 것은 Widget(위젯)이다. 글자도, 버튼도,
/// 여백도 전부 위젯이고, 이것들을 레고처럼 조립해서 화면을 만든다.
///
/// 위젯에는 두 종류가 있다.
///   StatelessWidget  한 번 그려지면 스스로 바뀌지 않는 위젯. 이 파일이 그렇다.
///   StatefulWidget   내부 값이 바뀌면 다시 그려지는 위젯. 촬영 화면이 그렇다.
library;

import 'package:flutter/material.dart';

import 'screens/camera_screen.dart';

/// 앱이 실행되면 운영체제가 제일 먼저 부르는 함수.
///
/// runApp()에 위젯 하나를 넘기면 그게 화면 전체의 뿌리가 된다.
void main() {
  runApp(const KMenuApp());
}

/// 앱 전체를 감싸는 껍데기.
///
/// 스스로 바뀔 일이 없으므로(제목·색·첫 화면은 고정) StatelessWidget을 쓴다.
class KMenuApp extends StatelessWidget {
  // const 생성자 — 값이 절대 안 바뀌는 위젯이라는 표시다. Flutter가 이걸 보고
  // "다시 그릴 필요 없음"으로 판단해 성능을 아낀다.
  // super.key는 Flutter가 위젯을 구분할 때 쓰는 이름표로, 관례적으로 넣어둔다.
  const KMenuApp({super.key});

  /// build()는 "이 위젯을 화면에 어떻게 그릴지" 돌려주는 함수다.
  /// Flutter가 화면을 그려야 할 때마다 이 함수를 부른다.
  @override
  Widget build(BuildContext context) {
    // MaterialApp은 앱 전체에 공통으로 필요한 것(화면 이동 기능, 테마, 제목)을
    // 한꺼번에 제공하는 위젯이다. Flutter 앱은 보통 이걸 최상단에 둔다.
    return MaterialApp(
      title: 'K-Menu',

      // theme — 앱 전체의 색을 정한다. 화면마다 색을 따로 지정하지 않아도
      // 여기서 정한 색이 버튼·앱바 등에 자동으로 적용된다.
      theme: ThemeData(
        // 씨앗 색 하나만 주면 Flutter가 그 색과 어울리는 색 조합을 만들어준다.
        // 0xFFD84315는 진한 주황빛 — 음식 앱에 맞는 따뜻한 톤으로 골랐다.
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFFD84315)),
        useMaterial3: true,
      ),

      // home — 앱을 열었을 때 처음 보이는 화면.
      home: const CameraScreen(),

      // 개발 중에만 화면 오른쪽 위에 뜨는 빨간 "DEBUG" 띠를 없앤다.
      // 시연 영상에 그 띠가 찍히면 지저분해 보인다.
      debugShowCheckedModeBanner: false,
    );
  }
}
