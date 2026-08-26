/// 주문 확인 화면 — 담은 메뉴를 종업원에게 보여주는 자리.
///
/// **어디에도 주문을 보내지 않는다.** 그래서 "주문이 접수되었습니다" 같은 문구를
/// 쓰지 않는다 — 실제로 접수되지 않았는데 접수된 것처럼 보이면 여행자가 자리에
/// 앉아 오지 않을 음식을 기다리게 된다(`docs/specs/cart.md`).
///
/// 그래서 이 화면만 **한글 이름을 크게** 둔다. 읽는 사람이 여행자가 아니라
/// 종업원이기 때문이다. 다른 화면은 전부 영문이 크고 한글이 보조다.
///
/// 카트는 그대로 남는다 — 보여주고 돌아와 수량을 고칠 수 있어야 한다(EC-08).
library;

import 'package:flutter/material.dart';

import '../api.dart';
import 'animated_gradient_back_button.dart';
import 'settings_button.dart';
import 'stitch_bar.dart';

class OrderSummaryScreen extends StatelessWidget {
  const OrderSummaryScreen({super.key, required this.cart});

  /// 후보 화면이 들고 있던 카트 상태를 그대로 받는다.
  ///
  /// 이 화면은 서버를 부르지 않는다. 여기서 다시 조회하면 보여주는 도중에
  /// 내용이 바뀔 수 있는데, 종업원에게 내미는 화면이 그러면 안 된다.
  final CartState cart;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Show this to the staff'),
        leading: const AnimatedGradientBackButton(),
        actions: const [SettingsButton()],
        // Penpot 04 보드와 동일한 시각적 리듬. 직원에게 보여줄 주문 데이터는 변경하지 않는다.
        bottom: const PreferredSize(
          preferredSize: Size.fromHeight(AppBarStitchBand.preferredHeight),
          child: AppBarStitchBand(),
        ),
      ),
      body: Column(
        children: [
          const _StaffNotice(),
          Expanded(
            // 주문 항목은 다른 본문과 분리된 종이 한 장처럼 보이게 한다.
            // 카트 데이터·수량·총계 계산은 기존과 완전히 같고, 이 위젯은 배경과
            // 구분선만 담당한다.
            child: _OrderTicket(cart: cart),
          ),
          _TotalBar(cart: cart),
        ],
      ),
    );
  }
}

/// 종업원에게 보여줄 음식 목록을 위한 주문서 모양의 컨테이너.
///
/// 아주 옅은 아이보리 종이, 얇은 테두리, 점선 구분선을 사용한다. 음식 이름과
/// 가격은 그대로 크게 유지해, 장식 때문에 실제 주문 내용을 읽기 어려워지지 않게 한다.
class _OrderTicket extends StatelessWidget {
  const _OrderTicket({required this.cart});

  final CartState cart;

  @override
  Widget build(BuildContext context) {
    const ticketBrown = Color(0xFF9D563D);
    const ticketBorder = Color(0xFFE6CEC1);

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: const Color(0xFFFFFCF7),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: ticketBorder),
          boxShadow: const [
            // 종이를 살짝 띄우되, 총계 바보다 눈에 띄지 않게 아주 약하게 둔다.
            BoxShadow(
              color: Color(0x12000000),
              blurRadius: 8,
              offset: Offset(0, 3),
            ),
          ],
        ),
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 13, 16, 7),
              child: Row(
                children: [
                  const Icon(
                    Icons.receipt_long_outlined,
                    size: 17,
                    color: ticketBrown,
                  ),
                  const SizedBox(width: 7),
                  const Text(
                    'ORDER TICKET',
                    style: TextStyle(
                      color: ticketBrown,
                      fontSize: 11,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 1.2,
                    ),
                  ),
                  const Spacer(),
                  Text(
                    '${cart.items.length} item${cart.items.length == 1 ? '' : 's'}',
                    style: const TextStyle(fontSize: 11, color: Colors.black45),
                  ),
                ],
              ),
            ),
            const _ReceiptDashedDivider(color: ticketBorder),
            Expanded(
              child: ListView.separated(
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 4,
                ),
                itemCount: cart.items.length,
                separatorBuilder: (context, index) =>
                    const _ReceiptDashedDivider(color: ticketBorder),
                itemBuilder: (context, index) =>
                    _OrderLine(line: cart.items[index]),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// 영수증의 절취선 같은 얇은 점선.
///
/// Flutter 기본 Divider는 실선뿐이라 CustomPainter로 짧은 선과 여백을 반복한다.
/// 장식 요소이므로 의미를 가진 텍스트나 탭 동작은 추가하지 않는다.
class _ReceiptDashedDivider extends StatelessWidget {
  const _ReceiptDashedDivider({required this.color});

  final Color color;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 12,
      width: double.infinity,
      child: CustomPaint(painter: _ReceiptDashPainter(color)),
    );
  }
}

class _ReceiptDashPainter extends CustomPainter {
  const _ReceiptDashPainter(this.color);

  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = 1;
    for (double x = 0; x < size.width; x += 7) {
      canvas.drawLine(
        Offset(x, size.height / 2),
        Offset(x + 3, size.height / 2),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _ReceiptDashPainter oldDelegate) =>
      oldDelegate.color != color;
}

/// 화면 맨 위 안내문 두 줄.
///
/// 한글은 **종업원이 읽는 문장**이라 크게, 영문은 여행자가 "내가 지금 뭘 보여주고
/// 있는지" 확인하는 줄이라 작게 둔다. 아래 메뉴 목록과 같은 규칙이다.
///
/// "주문이 접수되었습니다"류의 문구는 쓰지 않는다 — 이 화면은 어디에도 주문을
/// 보내지 않는다(`docs/specs/cart.md`). 여행자가 종업원에게 말을 거는 문장이라야
/// 실제로 일어나는 일과 화면이 어긋나지 않는다.
class _StaffNotice extends StatelessWidget {
  const _StaffNotice();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      // 앱 전체가 따뜻한 주황 계열이라 회색을 쓰면 이 띠만 따로 논다.
      // 테마에서 색을 받아오면 나중에 씨앗 색을 바꿔도 같이 따라온다.
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      padding: const EdgeInsets.all(16),
      child: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '이 메뉴로 주문할게요.',
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
          ),
          SizedBox(height: 6),
          Text(
            'This says "I would like to order these." Show this screen to the staff.',
            style: TextStyle(fontSize: 13, color: Colors.black54),
          ),
        ],
      ),
    );
  }
}

class _OrderLine extends StatelessWidget {
  const _OrderLine({required this.line});

  final CartLine line;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                // 종업원이 읽는 줄이라 가장 크게 둔다.
                //
                // 등록 이름(김치찌개)이 아니라 **그 가게 메뉴판에 인쇄된 글자**
                // (쌈싸먹는 꽁치김치찌개)를 쓴다. 종업원은 자기 메뉴판 표현으로
                // 봐야 무엇인지 바로 안다. 줄 정보가 없으면 등록 이름으로 돌아간다.
                //
                // 가격을 뗀 쪽을 먼저 쓴다 — 오른쪽에 값이 따로 있어서, 줄 글자를
                // 그대로 쓰면 "우성김치찌개 8,000" 옆에 "₩8,000"이 또 붙는다.
                Text(
                  line.nameText ?? line.menuText ?? line.nameKr,
                  style: const TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 2),
                // 여행자가 자기가 뭘 담았는지 확인하는 용도로 영문도 남긴다.
                Text(
                  line.nameEn,
                  style: const TextStyle(fontSize: 14, color: Colors.black54),
                ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                '× ${line.quantity}',
                style: const TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.bold,
                ),
              ),
              // 메뉴판에서 가격을 못 읽었으면 자리를 비운다.
              if (line.lineTotalDisplay != null)
                Text(
                  line.lineTotalDisplay!,
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              // 2개 이상일 때만 한 개 가격을 덧붙인다 — 1개면 소계와 같은 값이라
              // 같은 숫자를 두 번 적는 꼴이 된다.
              if (line.priceDisplay != null && line.quantity > 1)
                Text(
                  '${line.priceDisplay!} each',
                  style: const TextStyle(fontSize: 12, color: Colors.black45),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _TotalBar extends StatelessWidget {
  const _TotalBar({required this.cart});

  final CartState cart;

  @override
  Widget build(BuildContext context) {
    return Material(
      elevation: 8,
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // 총계가 실제보다 싸 보이는 상태를 말없이 두지 않는다.
              if (cart.hasUnpricedItems) ...[
                const Text(
                  'Some dishes had no price on the menu, so this total is partial.',
                  style: TextStyle(fontSize: 12, color: Colors.black54),
                ),
                const SizedBox(height: 8),
              ],
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text('Total', style: TextStyle(fontSize: 16)),
                  Text(
                    cart.totalDisplay,
                    style: const TextStyle(
                      fontSize: 24,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
