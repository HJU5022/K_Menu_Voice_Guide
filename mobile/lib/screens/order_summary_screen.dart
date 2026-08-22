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
      appBar: AppBar(title: const Text('Show this to the staff')),
      body: Column(
        children: [
          Expanded(
            child: ListView.separated(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              itemCount: cart.items.length,
              separatorBuilder: (context, index) => const Divider(height: 1),
              itemBuilder: (context, index) => _OrderLine(line: cart.items[index]),
            ),
          ),
          _TotalBar(cart: cart),
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
                Text(
                  line.nameKr,
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
                  style: const TextStyle(fontSize: 14, color: Colors.black54),
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
