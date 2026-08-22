/// 상단바 오른쪽의 설정 진입 버튼.
///
/// 촬영 화면에만 두었더니, 후보를 고르다가 "이 앱이 뭘 지원하지?"가 궁금해진
/// 순간에는 뒤로 나가야만 설정에 들어갈 수 있었다. 설정은 흐름 중 어디서든
/// 닿아야 하는 자리라 화면마다 같은 버튼을 둔다.
///
/// 위젯으로 빼둔 이유: 화면 네 곳에 같은 코드를 복사하면 아이콘이나 동작을 바꿀 때
/// 한 곳을 빠뜨리기 쉽다. 여기만 고치면 전부 같이 바뀐다.
///
/// 설정 화면 자신과 그 하위 화면(지원 음식·사용법·크레딧)에는 붙이지 않는다 —
/// 이미 설정 안이라 같은 곳으로 또 들어가는 버튼이 된다.
library;

import 'package:flutter/material.dart';

import 'settings_screen.dart';

class SettingsButton extends StatelessWidget {
  const SettingsButton({super.key});

  @override
  Widget build(BuildContext context) {
    return IconButton(
      onPressed: () => Navigator.push(
        context,
        MaterialPageRoute(builder: (context) => const SettingsScreen()),
      ),
      icon: const Icon(Icons.settings),
      tooltip: 'Settings',
    );
  }
}
