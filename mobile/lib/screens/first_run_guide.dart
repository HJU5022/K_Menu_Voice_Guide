/// 첫 실행 사용 안내 — 촬영을 시작하기 전 네 단계만 짧게 보여준다.
///
/// Settings의 How it works는 지원 범위·가격 출처까지 설명하는 상세 문서다.
/// 이 파일의 중앙 모달은 "지금 무엇을 하면 되는가"만 알려 준다. 같은 내용을
/// 두 곳에 복제하지 않아, 정책 문구가 달라지는 일을 막는다.
library;

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 앱을 다시 열 때 안내를 자동으로 띄우지 않기 위한 기기 내 저장 키.
///
/// 계정·식별자·사진 정보는 저장하지 않는다. 사용자가 안내를 한 번 닫았다는
/// boolean 하나만 이 기기에 남긴다.
const String _firstRunGuideSeenKey = 'k_menu.first_run_guide_seen';

/// 첫 실행이면 중앙 안내 모달을 띄우고, 어떤 방식으로든 닫힌 뒤 완료를 저장한다.
///
/// Skip·바깥 탭·아래 스와이프·마지막 버튼 중 어느 경로로 닫혀도 완료된다.
/// 그래서 각 버튼마다 따로 저장하지 않고, 모달이 닫힌 뒤 한 번만
/// 저장해 세 종료 경로의 동작을 같게 유지한다.
Future<void> showFirstRunGuideIfNeeded(BuildContext context) async {
  final preferences = await SharedPreferences.getInstance();
  if (preferences.getBool(_firstRunGuideSeenKey) ?? false) return;
  if (!context.mounted) return;

  await showDialog<void>(
    context: context,
    barrierDismissible: true,
    builder: (context) => const _FirstRunGuideDialog(),
  );

  // 저장에 실패하면 호출자(CameraScreen)가 예외를 로그로 남긴다. 안내만 다시
  // 보일 수 있을 뿐, 카메라 촬영·서버 호출 같은 핵심 흐름에는 영향이 없다.
  await preferences.setBool(_firstRunGuideSeenKey, true);
}

class _FirstRunGuideDialog extends StatefulWidget {
  const _FirstRunGuideDialog();

  @override
  State<_FirstRunGuideDialog> createState() => _FirstRunGuideDialogState();
}

class _FirstRunGuideDialogState extends State<_FirstRunGuideDialog> {
  final PageController _pageController = PageController();
  int _pageIndex = 0;

  static const List<_GuidePage> _pages = [
    _GuidePage(
      icon: Icons.photo_camera_outlined,
      visualKind: _GuideVisualKind.menuFrame,
      eyebrow: 'STEP 1',
      title: 'Take a photo',
      body: 'Frame a Korean menu, then take a photo or choose one from your library.',
    ),
    _GuidePage(
      icon: Icons.checklist_rounded,
      visualKind: _GuideVisualKind.dishChoices,
      eyebrow: 'STEP 2',
      title: 'Choose a dish',
      body: 'The app reads the menu and shows the dishes it recognised.',
    ),
    _GuidePage(
      icon: Icons.menu_book_outlined,
      visualKind: _GuideVisualKind.foodGuide,
      eyebrow: 'STEP 3',
      title: 'Understand the dish',
      body: 'Check ingredients, allergies, pronunciation and spice level before you choose.',
    ),
    _GuidePage(
      icon: Icons.receipt_long_outlined,
      visualKind: _GuideVisualKind.orderReceipt,
      eyebrow: 'STEP 4',
      title: 'Show your order',
      body: 'Add dishes, then show the Korean order card to the restaurant staff.',
    ),
  ];

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  void _close() => Navigator.of(context).pop();

  void _goToNextPage() {
    if (_pageIndex == _pages.length - 1) {
      _close();
      return;
    }
    _pageController.nextPage(
      duration: const Duration(milliseconds: 260),
      curve: Curves.easeOutCubic,
    );
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    // 화면 아래에 붙이면 사용 안내가 화면 하단 기능처럼 보인다. 화면 중앙에
    // 독립된 모달로 두고, 시각 카드를 넣어 화면의 68%만 쓰면서도 비어 보이지
    // 않게 한다. Dialog의 shape은 네 모서리 모두에 적용된다.
    final height = MediaQuery.sizeOf(context).height * 0.68;

    return Dialog(
      insetPadding: const EdgeInsets.symmetric(horizontal: 24, vertical: 48),
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      clipBehavior: Clip.antiAlias,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
      child: GestureDetector(
        // PageView는 가로 드래그만 받으므로, 빠른 아래 드래그는 모달 종료로
        // 안전하게 분리할 수 있다. 버튼을 찾지 않아도 한 손으로 닫을 수 있다.
        onVerticalDragEnd: (details) {
          if ((details.primaryVelocity ?? 0) > 450) _close();
        },
        child: SizedBox(
          height: height,
          child: Column(
            children: [
              const SizedBox(height: 10),
              Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: Colors.black26,
                  borderRadius: BorderRadius.circular(99),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(24, 12, 12, 0),
                child: Row(
                  children: [
                    const Expanded(
                      child: Text(
                        'A quick guide',
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                    TextButton(onPressed: _close, child: const Text('Skip')),
                  ],
                ),
              ),
              Expanded(
                child: PageView.builder(
                  controller: _pageController,
                  itemCount: _pages.length,
                  onPageChanged: (index) => setState(() => _pageIndex = index),
                  itemBuilder: (context, index) =>
                      _GuidePageView(page: _pages[index]),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
                child: Column(
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        for (var index = 0; index < _pages.length; index++)
                          AnimatedContainer(
                            duration: const Duration(milliseconds: 180),
                            margin: const EdgeInsets.symmetric(horizontal: 4),
                            width: index == _pageIndex ? 22 : 7,
                            height: 7,
                            decoration: BoxDecoration(
                              color: index == _pageIndex
                                  ? colorScheme.primary
                                  : colorScheme.primary.withValues(alpha: 0.18),
                              borderRadius: BorderRadius.circular(99),
                            ),
                          ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    Text(
                      _pageIndex == _pages.length - 1
                          ? 'Ready when you are'
                          : 'Swipe for the next step',
                      style: const TextStyle(
                        fontSize: 12,
                        color: Colors.black45,
                      ),
                    ),
                    const SizedBox(height: 12),
                    FilledButton(
                      onPressed: _goToNextPage,
                      child: Text(
                        _pageIndex == _pages.length - 1
                            ? 'Start scanning'
                            : 'Next',
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _GuidePageView extends StatelessWidget {
  const _GuidePageView({required this.page});

  final _GuidePage page;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    // 중앙 모달의 높이는 화면 높이에 비례한다. 가로 화면·글자 확대처럼
    // 안내 본문이 좁아지는 경우에는 이 안만 스크롤하게 해 RenderFlex overflow를
    // 피한다. PageView의 좌우 넘김과 세로 스크롤은 서로 다른 방향이라 공존한다.
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(32, 24, 32, 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _GuideVisual(kind: page.visualKind, icon: page.icon),
          const SizedBox(height: 24),
          Text(
            page.eyebrow,
            style: TextStyle(
              color: colorScheme.primary,
              fontSize: 12,
              fontWeight: FontWeight.bold,
              letterSpacing: 0.8,
            ),
          ),
          const SizedBox(height: 12),
          Text(
            page.title,
            style: const TextStyle(fontSize: 30, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 12),
          Text(
            page.body,
            style: const TextStyle(
              fontSize: 17,
              height: 1.45,
              color: Colors.black54,
            ),
          ),
        ],
      ),
    );
  }
}

class _GuidePage {
  const _GuidePage({
    required this.icon,
    required this.visualKind,
    required this.eyebrow,
    required this.title,
    required this.body,
  });

  final IconData icon;
  final _GuideVisualKind visualKind;
  final String eyebrow;
  final String title;
  final String body;
}

/// 글만 길게 읽히지 않도록, 실제 다음 화면의 핵심 정보 구조를 축약해 그린다.
/// 서버 결과나 사용자가 찍은 사진을 여기서 불러오지 않는다. 첫 실행에는 그런
/// 데이터가 없고, 이 위젯은 사용 흐름을 미리 알려 주는 정적 안내여야 한다.
class _GuideVisual extends StatelessWidget {
  const _GuideVisual({required this.kind, required this.icon});

  final _GuideVisualKind kind;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final accent = colors.primary;

    return Semantics(
      label: switch (kind) {
        _GuideVisualKind.menuFrame => 'Menu photo illustration',
        _GuideVisualKind.dishChoices => 'Dish choices illustration',
        _GuideVisualKind.foodGuide => 'Food guide illustration',
        _GuideVisualKind.orderReceipt => 'Order receipt illustration',
      },
      child: Container(
        height: 132,
        width: double.infinity,
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: colors.primaryContainer.withValues(alpha: 0.56),
          borderRadius: BorderRadius.circular(22),
        ),
        child: switch (kind) {
          _GuideVisualKind.menuFrame => _MenuFrameVisual(
            accent: accent,
            icon: icon,
          ),
          _GuideVisualKind.dishChoices => _DishChoicesVisual(accent: accent),
          _GuideVisualKind.foodGuide => _FoodGuideVisual(accent: accent),
          _GuideVisualKind.orderReceipt => _OrderReceiptVisual(accent: accent),
        },
      ),
    );
  }
}

class _MenuFrameVisual extends StatelessWidget {
  const _MenuFrameVisual({required this.accent, required this.icon});

  final Color accent;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.88),
        border: Border.all(color: accent.withValues(alpha: 0.38), width: 2),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Stack(
        children: [
          Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  'KOREAN MENU',
                  style: TextStyle(
                    fontSize: 10,
                    color: accent,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 7),
                _VisualLine(width: 112, color: Colors.black45),
                const SizedBox(height: 5),
                _VisualLine(width: 88, color: Colors.black38),
                const SizedBox(height: 5),
                _VisualLine(width: 100, color: Colors.black38),
              ],
            ),
          ),
          Positioned(
            right: 8,
            bottom: 8,
            child: DecoratedBox(
              decoration: BoxDecoration(color: accent, shape: BoxShape.circle),
              child: Padding(
                padding: const EdgeInsets.all(6),
                child: Icon(icon, size: 16, color: Colors.white),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _DishChoicesVisual extends StatelessWidget {
  const _DishChoicesVisual({required this.accent});

  final Color accent;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '3 dishes found',
          style: TextStyle(
            fontSize: 11,
            color: accent,
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(height: 8),
        for (final dish in ['Sundae', 'Bibimbap', 'Bulgogi']) ...[
          Expanded(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 9),
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.88),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Row(
                children: [
                  Container(
                    width: 18,
                    height: 18,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: accent,
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: const Icon(
                      Icons.check,
                      size: 12,
                      color: Colors.white,
                    ),
                  ),
                  const SizedBox(width: 7),
                  Text(
                    dish,
                    style: const TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const Spacer(),
                  Icon(Icons.add_circle_outline, size: 16, color: accent),
                ],
              ),
            ),
          ),
          if (dish != 'Bulgogi') const SizedBox(height: 5),
        ],
      ],
    );
  }
}

class _FoodGuideVisual extends StatelessWidget {
  const _FoodGuideVisual({required this.accent});

  final Color accent;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Container(
              width: 38,
              height: 38,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Text('🍲', style: TextStyle(fontSize: 20)),
            ),
            const SizedBox(width: 9),
            const Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Sundae',
                    style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                  ),
                  Text(
                    '순대 · Mild',
                    style: TextStyle(fontSize: 11, color: Colors.black54),
                  ),
                ],
              ),
            ),
            Icon(Icons.volume_up_outlined, color: accent, size: 20),
          ],
        ),
        const SizedBox(height: 10),
        Expanded(
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
            decoration: BoxDecoration(
              color: const Color(0xFFFFF4D6),
              borderRadius: BorderRadius.circular(10),
            ),
            child: const Row(
              children: [
                Icon(
                  Icons.warning_amber_rounded,
                  size: 17,
                  color: Color(0xFF9C5C26),
                ),
                SizedBox(width: 7),
                Expanded(
                  child: Text(
                    'Check allergies before ordering',
                    style: TextStyle(fontSize: 11, color: Color(0xFF6E492D)),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _OrderReceiptVisual extends StatelessWidget {
  const _OrderReceiptVisual({required this.accent});

  final Color accent;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.9),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'YOUR ORDER',
              style: TextStyle(
                fontSize: 10,
                color: accent,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 6),
            const _ReceiptLine(name: '순대국밥', price: '₩8,000'),
            const Divider(height: 12),
            const _ReceiptLine(name: '비빔밥', price: '₩10,000'),
            const Spacer(),
            Row(
              children: [
                const Text(
                  'Total',
                  style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold),
                ),
                const Spacer(),
                Text(
                  '₩18,000',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                    color: accent,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _ReceiptLine extends StatelessWidget {
  const _ReceiptLine({required this.name, required this.price});

  final String name;
  final String price;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Text(name, style: const TextStyle(fontSize: 11)),
        const Spacer(),
        Text(
          price,
          style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600),
        ),
      ],
    );
  }
}

class _VisualLine extends StatelessWidget {
  const _VisualLine({required this.width, required this.color});

  final double width;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width,
      height: 5,
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.2),
        borderRadius: BorderRadius.circular(99),
      ),
    );
  }
}

enum _GuideVisualKind { menuFrame, dishChoices, foodGuide, orderReceipt }
