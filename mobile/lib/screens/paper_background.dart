/// K-Menu의 공통 종이 질감 배경.
///
/// 이미지 파일을 깔지 않고 코드로 그린다. 그래서 앱 용량이 늘지 않고, 홈 화면의
/// 상단바와 본문이 같은 바탕색을 써서 두 영역이 따로 떠 보이지 않는다.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';

class PaperPalette {
  const PaperPalette._();

  static const base = Color(0xFFFFFAF4);
  static const peachWash = Color(0xFFFFE0D4);
  static const sageWash = Color(0xFFDDE9DD);
}

/// 화면 모서리의 옅은 색 번짐과 아주 가는 섬유 결을 그린다.
class PaperBackground extends StatelessWidget {
  const PaperBackground({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return CustomPaint(painter: _PaperTexturePainter(), child: child);
  }
}

class _PaperTexturePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final bounds = Offset.zero & size;
    canvas.drawRect(bounds, Paint()..color = PaperPalette.base);

    // 모서리에만 머물게 하여 본문·사진의 가독성을 해치지 않는다.
    final peach = Paint()
      ..shader =
          RadialGradient(
            colors: [
              PaperPalette.peachWash.withValues(alpha: 0.72),
              Colors.transparent,
            ],
            stops: const [0, 1],
          ).createShader(
            Rect.fromCircle(
              center: const Offset(-18, 18),
              radius: size.width * 0.62,
            ),
          );
    canvas.drawRect(bounds, peach);

    final sage = Paint()
      ..shader =
          RadialGradient(
            colors: [
              PaperPalette.sageWash.withValues(alpha: 0.42),
              Colors.transparent,
            ],
            stops: const [0, 1],
          ).createShader(
            Rect.fromCircle(
              center: Offset(size.width + 22, size.height * 0.78),
              radius: size.width * 0.72,
            ),
          );
    canvas.drawRect(bounds, sage);

    final fibre = Paint()
      ..color = const Color(0xFF6D897B).withValues(alpha: 0.14)
      ..strokeWidth = 0.65
      ..strokeCap = StrokeCap.round;
    final random = math.Random(2042);
    final count = math.max(38, (size.width * size.height / 12000).round());
    for (var index = 0; index < count; index++) {
      final start = Offset(
        random.nextDouble() * size.width,
        random.nextDouble() * size.height,
      );
      final length = 5 + random.nextDouble() * 13;
      final angle = -0.9 + random.nextDouble() * 1.8;
      canvas.drawLine(
        start,
        start + Offset(math.cos(angle) * length, math.sin(angle) * length),
        fibre,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _PaperTexturePainter oldDelegate) => false;
}
