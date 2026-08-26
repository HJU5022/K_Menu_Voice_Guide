/// 공통 뒤로가기 버튼 — 화살표 자체에만 짧은 그라데이션 피드백을 준다.
///
/// Flutter 기본 AppBar의 자동 BackButton은 누를 때 원형 잉크(스플래시) 효과를
/// 낸다. K-Menu의 iOS 시연에서는 그 원형 배경보다 `<` 화살표 안에서 색이
/// 스쳐 지나가는 편이 Penpot의 가는 스티치·따뜻한 색 체계와 더 잘 맞는다.
///
/// 이 위젯은 경로 규칙을 바꾸지 않는다. 탭 후 320ms 동안만 시각 효과를 보여주고
/// `Navigator.maybePop`으로 기존의 자동 BackButton과 같은 이전 화면 이동을 한다.
/// 이전 화면은 새로 그려지므로, 화살표는 다시 기본색으로 보인다.
library;

import 'package:flutter/material.dart';

class AnimatedGradientBackButton extends StatefulWidget {
  const AnimatedGradientBackButton({super.key, this.baseColor});

  /// 사진 확대 화면처럼 AppBar의 기본 전경색이 흰색인 경우에만 넘긴다.
  /// 일반 화면은 현재 테마의 onSurface 색을 기본 화살표 색으로 사용한다.
  final Color? baseColor;

  @override
  State<AnimatedGradientBackButton> createState() =>
      _AnimatedGradientBackButtonState();
}

class _AnimatedGradientBackButtonState extends State<AnimatedGradientBackButton>
    with SingleTickerProviderStateMixin {
  // 처음의 180ms는 시뮬레이터에서 그라데이션을 인지하기에 너무 짧았다.
  // 320ms는 탭 반응으로는 여전히 짧지만, 색이 `<`를 지나가는 것을 볼 수 있는 길이다.
  static const _feedbackDuration = Duration(milliseconds: 320);

  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: _feedbackDuration,
  );

  bool _isLeaving = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _handlePressed() async {
    // 연속 탭으로 pop이 두 번 실행되는 것을 막는다. 이는 기존 BackButton의
    // 한 번 탭 = 한 번 뒤로가기 동작을 그대로 보장하기 위한 안전장치다.
    if (_isLeaving || !Navigator.canPop(context)) return;

    setState(() => _isLeaving = true);
    await _controller.forward(from: 0);
    if (!mounted) return;

    // 실제 화면 이동은 기존 자동 BackButton과 동일하게 현재 route만 pop한다.
    Navigator.maybePop(context);
  }

  @override
  Widget build(BuildContext context) {
    final baseColor = widget.baseColor ?? Theme.of(context).colorScheme.onSurface;

    return IconButton(
      tooltip: 'Back',
      // Material의 원형 상태 레이어를 투명하게 만들어, 컬러 변화가 원이 아니라
      // `<` 화살표 내부에만 나타나도록 한다. 터치 영역(최소 48px)은 유지된다.
      style: IconButton.styleFrom(overlayColor: Colors.transparent),
      onPressed: _isLeaving || !Navigator.canPop(context) ? null : _handlePressed,
      icon: AnimatedBuilder(
        animation: _controller,
        builder: (context, child) {
          // 넓은 브라운 → 골드 → 브라운 하이라이트가 화살표 안을 가로지른다.
          // 하이라이트 폭을 아이콘 폭의 약 30%로 넓혀, 작은 `<`에서도 색 이동이
          // 시뮬레이터에서 명확히 보이게 한다. t=0/1에서는 하이라이트가 아이콘 밖에 있다.
          final t = Curves.easeInOut.transform(_controller.value);
          return ShaderMask(
            blendMode: BlendMode.srcIn,
            shaderCallback: (bounds) => LinearGradient(
              begin: Alignment(-1.4 + (2.8 * t), 0),
              end: Alignment(.6 + (2.8 * t), 0),
              colors: [
                baseColor,
                baseColor,
                const Color(0xFFA4563C),
                const Color(0xFFCFA035),
                const Color(0xFFA4563C),
                baseColor,
                baseColor,
              ],
              stops: const [0, .2, .35, .5, .65, .8, 1],
            ).createShader(bounds),
            // iOS 화면에서 보이는 `<`와 같은 가는 chevron을 사용한다.
            child: Icon(
              Icons.arrow_back_ios_new_rounded,
              color: Colors.white,
              size: 28,
            ),
          );
        },
      ),
    );
  }
}
