/// 맵기 눈금 — 불꽃 5칸 중 spice_level 만큼 채운다.
///
/// 웹앱이 "🌶️" × level + "·" × (5 - level)로 그리던 것과 같은 규칙이다.
/// 상세 화면의 SPICY 카드가 설명이라면 이건 한눈에 보는 눈금이라, 둘 다 필요하다.
///
/// 상세 화면(③)과 후보 카드(②) 두 곳에서 같은 눈금을 써야 해서, 상세 화면에만
/// 있던 것을 이 파일로 옮겨 공용으로 만들었다. 그리는 규칙은 그대로다.
library;

import 'package:flutter/material.dart';

class SpiceGauge extends StatelessWidget {
  const SpiceGauge({super.key, required this.level, this.size = 18});

  /// 채울 칸 수(1~5).
  final int level;

  /// 불꽃 하나의 크기. 상세 화면은 기본값(18)을 쓰고, 후보 카드는 글자가 작아서
  /// 더 작은 값을 넘긴다 — 웹앱도 상세 20 / 카드 13으로 카드 쪽을 줄여 그린다.
  final double size;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: List.generate(5, (index) {
        return Padding(
          padding: const EdgeInsets.only(right: 2),
          child: Icon(
            Icons.local_fire_department,
            size: size,
            color: index < level ? Colors.deepOrange : Colors.black26,
          ),
        );
      }),
    );
  }
}
