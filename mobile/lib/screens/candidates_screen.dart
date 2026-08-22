/// ② 후보 선택 화면 — 촬영 결과로 나온 음식 후보 중 하나를 고른다.
///
/// 하는 일
///   1. `POST /api/analyze`가 돌려준 candidates를 카드 목록으로 보여준다.
///   2. 사용자가 하나를 고르면 그 food_id를 들고 상세 화면으로 넘어간다.
///
/// 이 화면이 따로 있는 이유: 메뉴판 한 장에 음식이 여러 개 찍히는 게 정상이고,
/// OCR이 비슷한 이름을 여러 개 올릴 수도 있어서 서버가 단정하지 않고 후보를
/// 돌려준다(루트 README "여러 음식 인식 → 목록을 보여주고 하나를 선택").
/// 즉 서버는 판단을 사용자에게 넘기고, 그 판단을 받는 자리가 여기다.
///
/// 서버는 score(유사도) 내림차순으로 정렬해서 준다 — 앱에서 다시 정렬하지 않는다.
///
/// ── 이 파일을 읽는 데 필요한 개념 ──────────────────────────────────
///
/// 화면 이동(Navigator)
///   Flutter는 화면을 카드 쌓기처럼 다룬다.
///     Navigator.push  새 카드를 위에 얹는다 (앞으로 가기)
///     Navigator.pop   맨 위 카드를 치운다 (뒤로 가기)
///   push로 얹으면 상단 왼쪽 뒤로가기 버튼(←)이 자동으로 생긴다.
///
/// 왜 StatelessWidget인가
///   이 화면은 스스로 바뀌는 값이 없다. 목록은 촬영 화면에서 받아온 그대로
///   보여주기만 하고, 누르면 다음 화면으로 넘어갈 뿐이다. 그래서 State가 없는
///   가벼운 위젯으로 만든다.
library;

import 'package:flutter/material.dart';

import '../api.dart';
import 'detail_screen.dart';

class CandidatesScreen extends StatefulWidget {
  const CandidatesScreen({super.key, required this.candidates});

  /// 촬영 화면이 넘겨준 후보 목록.
  ///
  /// 목록 자체는 이 화면에서 바뀌지 않는다 — 분석 결과를 다시 부를 이유가 없다.
  /// 바뀌는 건 장바구니뿐이라, State가 드는 것도 장바구니뿐이다.
  final List<Candidate> candidates;

  @override
  State<CandidatesScreen> createState() => _CandidatesScreenState();
}

class _CandidatesScreenState extends State<CandidatesScreen> {
  /// 서버가 돌려준 카트 전체 상태. 응답을 통째로 갈아끼운다 — 부분 갱신을
  /// 앱에서 짜맞추지 않는 게 이 API의 설계다(`docs/specs/cart.md`).
  CartState? _cart;

  /// 카트 요청이 실패했을 때만 채운다. 담긴 내용은 지우지 않는다(EC-06).
  String? _cartError;

  @override
  void initState() {
    super.initState();
    _runCartRequest(fetchCart);
  }

  Future<void> _runCartRequest(Future<CartState> Function() request) async {
    try {
      final cart = await request();
      if (!mounted) return;
      setState(() {
        _cart = cart;
        _cartError = null;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _cartError = e.message);
    }
  }

  /// 이 후보가 지금 카트에 몇 개 담겨 있는지. 안 담겨 있으면 0.
  int _quantityOf(Candidate candidate) {
    for (final line in _cart?.items ?? const <CartLine>[]) {
      if (line.foodId == candidate.foodId) return line.quantity;
    }
    return 0;
  }

  @override
  Widget build(BuildContext context) {
    final candidates = widget.candidates;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Which dish?'),
        // 뒤로가기 버튼은 Navigator.push로 열린 화면에 자동으로 붙는다.
        // 따로 만들 필요가 없다.
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
            child: Text(
              candidates.length == 1
                  ? 'We found 1 dish on this menu.'
                  : 'We found ${candidates.length} dishes on this menu.',
              style: const TextStyle(fontSize: 15, color: Colors.black54),
            ),
          ),
          Expanded(
            child: ListView.separated(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              itemCount: candidates.length,
              // separatorBuilder — 항목 사이마다 끼워 넣을 위젯.
              // 여기서는 간격만 준다.
              separatorBuilder: (context, index) => const SizedBox(height: 12),
              itemBuilder: (context, index) {
                final candidate = candidates[index];
                return _CandidateCard(
                  candidate: candidate,
                  quantity: _quantityOf(candidate),
                  // 카드는 "눌렸다"만 알리고, 무엇을 할지는 이 화면이 정한다.
                  onTap: () => _openDetail(context, candidate),
                  onChangeQuantity: (delta) => _runCartRequest(
                    () => changeCartItem(candidate, quantityDelta: delta),
                  ),
                );
              },
            ),
          ),
          _CartBar(
            cart: _cart,
            errorMessage: _cartError,
            onClear: () => _runCartRequest(clearCart),
          ),
        ],
      ),
    );
  }

  /// 고른 음식의 상세 화면을 연다.
  ///
  /// 넘기는 것은 food_id와 이름뿐이다 — 상세 화면은 그 번호로 서버에 다시
  /// 물어보므로 후보 목록 전체를 들고 갈 이유가 없다. 이름을 같이 넘기는 것은
  /// 응답을 기다리는 동안 상단 제목을 비워두지 않기 위해서다.
  void _openDetail(BuildContext context, Candidate candidate) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => DetailScreen(
          foodId: candidate.foodId,
          nameEn: candidate.nameEn,
        ),
      ),
    );
  }
}

/// 후보 하나를 보여주는 카드.
///
/// 이 파일 안에서만 쓰므로 이름 앞에 `_`를 붙여 비공개로 둔다.
/// 카드 한 장의 생김새가 제법 길어서, 목록 코드와 섞이지 않도록 분리했다.
class _CandidateCard extends StatelessWidget {
  const _CandidateCard({
    required this.candidate,
    required this.quantity,
    required this.onTap,
    required this.onChangeQuantity,
  });

  final Candidate candidate;

  /// 지금 카트에 담긴 개수. 0이면 아직 안 담긴 것이다.
  final int quantity;

  /// 카드가 눌렸을 때 실행할 동작. 카드는 무엇을 할지 모르고 알리기만 한다.
  final VoidCallback onTap;

  /// +/− 를 눌렀을 때. +1 또는 -1을 넘긴다.
  final void Function(int delta) onChangeQuantity;

  @override
  Widget build(BuildContext context) {
    return Card(
      clipBehavior: Clip.antiAlias, // 사진 모서리를 카드 모양에 맞춰 둥글게 자른다
      margin: EdgeInsets.zero,
      // InkWell — 누를 수 있게 만들고, 누를 때 물결 효과를 준다.
      // "이건 누르는 것"이라는 신호를 사용자에게 준다.
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(12),
          // Row — 자식들을 가로로 나란히 놓는다. (사진 | 글자 | 화살표)
          child: Row(
            children: [
              _Thumbnail(candidate: candidate),
              const SizedBox(width: 12),
              // Expanded — 사진과 화살표를 뺀 나머지 가로 공간을 글자가 다 쓴다.
              // 이게 없으면 이름이 길 때 화면 밖으로 삐져나간다.
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // 사용자가 영어권이라 영어 이름을 크게, 한글은 보조로 둔다.
                    Text(
                      candidate.nameEn,
                      style: const TextStyle(
                        fontSize: 17,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      candidate.nameKr,
                      style: const TextStyle(color: Colors.black54),
                    ),
                    // 가격은 있을 때만 보여준다. 서버가 못 읽었으면 자리를 비운다 —
                    // 없는 가격을 "가격 미상" 같은 문구로 채우면 화면만 시끄럽다.
                    if (candidate.hasPrice) ...[
                      const SizedBox(height: 6),
                      Text(
                        candidate.priceDisplay!,
                        style: TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                          color: Theme.of(context).colorScheme.primary,
                        ),
                      ),
                    ],
                    // 사진 출처 표기. 프로젝트가 외부 사진을 쓰면서 출처를 남기기로
                    // 한 항목이라, **사진을 보여주는 자리에는 반드시 함께 둔다.**
                    // 가격처럼 "있으면 좋은 것"이 아니라 지켜야 하는 조건이다.
                    if (candidate.hasThumbnail &&
                        candidate.thumbnailAttribution != null) ...[
                      const SizedBox(height: 6),
                      Text(
                        candidate.thumbnailAttribution!,
                        style: const TextStyle(
                          fontSize: 10,
                          color: Colors.black38,
                        ),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ],
                ),
              ),
              _QuantityStepper(quantity: quantity, onChange: onChangeQuantity),
            ],
          ),
        ),
      ),
    );
  }
}

/// 카드 오른쪽의 담기/빼기.
///
/// 아직 안 담긴 메뉴에는 `+`만 보여준다 — 0인데 `−`가 있으면 누를 수 있어 보이지만
/// 아무 일도 일어나지 않아서 고장처럼 읽힌다(EC-02).
class _QuantityStepper extends StatelessWidget {
  const _QuantityStepper({required this.quantity, required this.onChange});

  final int quantity;
  final void Function(int delta) onChange;

  @override
  Widget build(BuildContext context) {
    if (quantity == 0) {
      return IconButton(
        onPressed: () => onChange(1),
        icon: const Icon(Icons.add_circle_outline),
        tooltip: 'Add to cart',
      );
    }

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        IconButton(
          onPressed: () => onChange(-1),
          icon: const Icon(Icons.remove_circle_outline),
          visualDensity: VisualDensity.compact,
        ),
        Text(
          '$quantity',
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
        ),
        IconButton(
          onPressed: () => onChange(1),
          icon: const Icon(Icons.add_circle_outline),
          visualDensity: VisualDensity.compact,
        ),
      ],
    );
  }
}

/// 화면 아래에 붙어 있는 카트 요약.
///
/// 카트가 비어 있으면 Clear는 비활성이다(EC-07).
class _CartBar extends StatelessWidget {
  const _CartBar({
    required this.cart,
    required this.errorMessage,
    required this.onClear,
  });

  /// 아직 못 받았으면 null. 그동안은 빈 카트와 같은 모양으로 둔다.
  final CartState? cart;

  final String? errorMessage;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    final isEmpty = cart?.isEmpty ?? true;

    return Material(
      elevation: 8,
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (errorMessage != null) ...[
                Text(
                  errorMessage!,
                  style: const TextStyle(fontSize: 12, color: Colors.redAccent),
                ),
                const SizedBox(height: 8),
              ],
              // 총계가 실제보다 싸 보이는 상태를 말없이 두지 않는다(EC-03).
              if (cart?.hasUnpricedItems ?? false) ...[
                const Text(
                  'Some dishes had no price on the menu, so the total is partial.',
                  style: TextStyle(fontSize: 12, color: Colors.black54),
                ),
                const SizedBox(height: 8),
              ],
              Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          isEmpty ? 'Cart is empty' : '${cart!.itemCount} in cart',
                          style: const TextStyle(
                            fontSize: 13,
                            color: Colors.black54,
                          ),
                        ),
                        if (!isEmpty)
                          Text(
                            cart!.totalDisplay,
                            style: const TextStyle(
                              fontSize: 20,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                      ],
                    ),
                  ),
                  TextButton(
                    onPressed: isEmpty ? null : onClear,
                    child: const Text('Clear'),
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

/// 카드 왼쪽의 음식 사진.
///
/// 사진은 인터넷에서 받아오므로 실패할 수 있다. 실패해도 카드 전체가 깨지면
/// 안 되므로, 이 위젯 안에서 대체 그림으로 갈아끼운다.
class _Thumbnail extends StatelessWidget {
  const _Thumbnail({required this.candidate});

  final Candidate candidate;

  static const double _size = 64;

  @override
  Widget build(BuildContext context) {
    if (!candidate.hasThumbnail) {
      return const _ThumbnailPlaceholder(size: _size);
    }

    return ClipRRect(
      borderRadius: BorderRadius.circular(8),
      child: Image.network(
        candidate.thumbnailUrl!,
        width: _size,
        height: _size,
        fit: BoxFit.cover, // 비율을 유지하면서 정사각형을 꽉 채운다
        // 받아오는 동안 보여줄 것. 이게 없으면 사진 자리가 갑자기 나타나
        // 목록이 덜컥거린다.
        loadingBuilder: (context, child, progress) {
          if (progress == null) return child; // 다 받았으면 사진을 그대로
          return const _ThumbnailPlaceholder(size: _size, isLoading: true);
        },
        // 사진을 못 받았을 때. 오류를 사용자에게 보여줄 필요는 없다 —
        // 이름과 가격만으로도 고를 수 있으므로 조용히 대체 그림을 둔다.
        errorBuilder: (context, error, stackTrace) =>
            const _ThumbnailPlaceholder(size: _size),
      ),
    );
  }
}

/// 사진이 없거나 아직 못 받았을 때 자리를 대신 채우는 회색 상자.
class _ThumbnailPlaceholder extends StatelessWidget {
  const _ThumbnailPlaceholder({required this.size, this.isLoading = false});

  final double size;
  final bool isLoading;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: Colors.black12,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Center(
        child: isLoading
            ? const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : const Icon(Icons.restaurant, color: Colors.black26),
      ),
    );
  }
}
