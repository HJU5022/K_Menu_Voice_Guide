/// 앱바 바로 아래에 붙는 공통 장식 바.
///
/// 이 위젯은 Penpot 01~05 보드에 있는 네 개의 짧은 색 선을 모바일에 옮긴
/// **시각적 장식**이다. 탭, 상태, 진행률을 표현하지 않으며 OCR·카트·주문·API
/// 요청 같은 기능 상태와 연결하지 않는다. 따라서 화면 기능을 바꾸지 않고도
/// 모든 주요 화면의 상단 인상을 일관되게 만들 수 있다.
library;

import 'package:flutter/material.dart';

/// Penpot의 AppBar 아래 스티치 장식.
///
/// Penpot 원본값은 64×5 선 네 개, 선 사이 14px, 모서리 3px이다.
/// 화면 폭이 넓어져도 선 묶음 자체는 중앙에 유지해, 원본 보드와 같은 리듬을
/// 만든다. [`preferredHeight`]는 AppBar의 `bottom`이 본문을 정확히 이 높이만큼
/// 아래로 밀도록 공개해 둔 값이다.
class AppBarStitchBand extends StatelessWidget {
  const AppBarStitchBand({super.key});

  /// AppBar `bottom` 영역의 전체 높이. 실제 색 선은 그 안에서 5px만 차지한다.
  static const double preferredHeight = 16;

  static const double _segmentWidth = 64;
  static const double _segmentHeight = 5;
  static const double _gap = 14;
  static const double _radius = 3;

  // Penpot 보드에서 사용하는 순서와 색을 그대로 보존한다.
  static const List<Color> _colors = [
    Color(0xFF2F6659),
    Color(0xFFCFA035),
    Color(0xFFDD6F52),
    Color(0xFF748F83),
  ];

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: preferredHeight,
      child: Center(
        child: Row(
          // 폭을 화면 전체로 늘리지 않는다. Penpot의 네 선 묶음처럼 가운데에 둔다.
          mainAxisSize: MainAxisSize.min,
          children: [
            for (var index = 0; index < _colors.length; index++) ...[
              if (index > 0) const SizedBox(width: _gap),
              DecoratedBox(
                decoration: BoxDecoration(
                  color: _colors[index],
                  borderRadius: BorderRadius.circular(_radius),
                ),
                child: const SizedBox(
                  width: _segmentWidth,
                  height: _segmentHeight,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
