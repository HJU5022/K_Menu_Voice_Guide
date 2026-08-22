/// 앱의 시작점.
///
/// 하는 일은 두 가지뿐이다 — 앱 전체에 공통으로 적용할 것(제목·색)을 정하고,
/// 첫 화면을 지정한다. 실제 기능은 screens/ 아래 각 화면이 갖는다.
library;

import 'package:flutter/material.dart';

import 'screens/camera_screen.dart';

void main() {
  runApp(const KMenuApp());
}

class KMenuApp extends StatelessWidget {
  const KMenuApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'K-Menu',
      // 사용자가 영어권 관광객이라 화면 문구는 전부 영어로 쓴다
      // (frontend/docs/content-style.md의 기준을 따른다).
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFFD84315)),
        useMaterial3: true,
      ),
      home: const CameraScreen(),
      debugShowCheckedModeBanner: false,
    );
  }
}
