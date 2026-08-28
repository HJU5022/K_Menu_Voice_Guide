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

import 'dart:io';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';

import '../api.dart';
import 'animated_gradient_back_button.dart';
import 'menu_photo_overlay.dart';
import 'detail_screen.dart';
import 'order_summary_screen.dart';
import 'settings_button.dart';
import 'spice_gauge.dart';
import 'stitch_bar.dart';

class CandidatesScreen extends StatefulWidget {
  const CandidatesScreen({super.key, required this.entries, this.photo});

  /// 사용자가 방금 찍은(또는 고른) 메뉴판 사진. 후보가 사진 어디에서 나왔는지
  /// 상자로 표시하는 데 쓴다. 없으면 그 영역을 통째로 생략한다.
  final File? photo;

  /// 촬영 화면이 넘겨준 메뉴 줄 목록 — **메뉴판에 인쇄된 순서 그대로**.
  ///
  /// 안내할 수 있는 후보([Candidate])만 들어온다. 등록되지 않은 줄은 서버가 아예
  /// 보내지 않는다 — 그 줄에 대해 아는 것이 사실상 없어서 원산지 표시나 가게 공지가
  /// 메뉴로 올라오고 엉뚱한 가격이 붙는 일이 있었다.
  ///
  /// 목록 자체는 이 화면에서 바뀌지 않는다 — 분석 결과를 다시 부를 이유가 없다.
  /// 바뀌는 건 장바구니뿐이라, State가 드는 것도 장바구니뿐이다.
  final List<CartAddable> entries;

  @override
  State<CandidatesScreen> createState() => _CandidatesScreenState();
}

class _CandidatesScreenState extends State<CandidatesScreen> {
  /// 후보 카드의 음식명 캐시 WAV를 한 번에 하나만 재생한다.
  final AudioPlayer _namePlayer = AudioPlayer();

  /// 서버가 돌려준 카트 전체 상태. 응답을 통째로 갈아끼운다 — 부분 갱신을
  /// 앱에서 짜맞추지 않는 게 이 API의 설계다(`docs/specs/cart.md`).
  CartState? _cart;

  /// 카트 요청이 실패했을 때만 채운다. 담긴 내용은 지우지 않는다(EC-06).
  String? _cartError;

  /// 하단 Order 버튼의 카트 변경 피드백을 식별하는 번호.
  ///
  /// 카트 모델 자체는 서버 응답으로 통째로 교체된다. 이 번호를 별도로 두면
  /// 서버/주문 기능에는 손대지 않고, `+`·`−`가 성공한 순간만 `_CartBar`에
  /// 전달할 수 있다.
  int _orderFeedbackVersion = 0;

  @override
  void initState() {
    super.initState();
    _runCartRequest(fetchCart);
  }

  @override
  void dispose() {
    _namePlayer.dispose();
    super.dispose();
  }

  /// 후보에는 이름 음성 URL을 싣지 않으므로, 누른 항목 하나만 상세 API로 조회한다.
  /// 서버가 반환하는 name_audio_path는 파인튜닝 TTS의 사전 생성 캐시 WAV다.
  Future<void> _playCachedName(Candidate candidate) async {
    try {
      final food = await fetchFood(candidate.foodId);
      if (!food.hasNameAudio) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Voice guide is not ready yet.')),
          );
        }
        return;
      }
      await _namePlayer.play(UrlSource(food.nameAudioUrl!));
    } on ApiException {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Could not load the voice guide.')),
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Could not play the voice guide.')),
        );
      }
    }
  }

  Future<void> _runCartRequest(
    Future<CartState> Function() request, {
    bool animateOrderFeedback = false,
  }) async {
    try {
      final cart = await request();
      if (!mounted) return;
      setState(() {
        _cart = cart;
        _cartError = null;

        // 최초 fetchCart·Clear는 false로 들어오므로 화면 진입/초기화에는
        // 반응하지 않는다. 반면 `+`와 `−`는 서버가 성공 응답을 준 뒤 매번
        // 번호를 올려, 수량 변경마다 버튼이 한 번씩 반동하도록 한다.
        if (animateOrderFeedback) {
          _orderFeedbackVersion++;
        }
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _cartError = e.message);
    }
  }

  /// 이 후보가 지금 카트에 몇 개 담겨 있는지. 안 담겨 있으면 0.
  ///
  /// foodId만으로 찾으면 안 된다 — 물만두와 군만두는 foodId가 같아서, 하나를 담으면
  /// 다른 카드의 수량까지 같이 올라간 것처럼 보인다. 서버가 묶는 기준과 똑같이
  /// (foodId + 메뉴판 줄 글자)로 찾는다.
  int _quantityOf(CartAddable entry) {
    for (final line in _cart?.items ?? const <CartLine>[]) {
      if (line.lineKey == entry.lineKey) return line.quantity;
    }
    return 0;
  }

  /// 목록 위에 두는 한 줄 안내.
  ///
  /// 사진 위에 상자가 안 붙은 후보가 있으면 그 수를 밝힌다. 상자가 2개인데 카드가
  /// 6개면 "왜 4개는 표시가 없지?"가 되는데, 이름이 여러 글자 상자에 걸쳐 잘리면
  /// 서버가 위치를 특정하지 못해 생기는 정상 동작이다. 말없이 두면 앱이 뭔가
  /// 빠뜨린 것처럼 보인다.
  String _summaryLine(List<CartAddable> entries) {
    final dish = entries.length == 1 ? 'dish' : 'dishes';
    final found = 'We found ${entries.length} $dish.';
    if (widget.photo == null) return found;

    final unpinned = entries.where((e) => e.source == null).length;
    if (unpinned == 0) return '$found Each box shows what we read there.';

    final it = unpinned == 1 ? 'one' : '$unpinned';
    return '$found Each box shows what we read there — '
        'we could not pin $it to a spot on the photo.';
  }

  @override
  Widget build(BuildContext context) {
    final entries = widget.entries;
    return Scaffold(
      appBar: AppBar(
        // 자동 BackButton 대신 화살표 내부에만 색이 흐르는 공통 피드백을 쓴다.
        title: const Text('Which dish?'),
        leading: const AnimatedGradientBackButton(),
        actions: const [SettingsButton()],
        // Penpot 02 보드와 맞추는 공통 장식. 후보·카트 상태에는 영향을 주지 않는다.
        bottom: const PreferredSize(
          preferredSize: Size.fromHeight(AppBarStitchBand.preferredHeight),
          child: AppBarStitchBand(),
        ),
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (widget.photo != null) ...[
            const SizedBox(height: 8),
            MenuPhotoOverlay(photo: widget.photo!, entries: entries),
            const SizedBox(height: 4),
          ],
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
            child: Text(
              _summaryLine(entries),
              style: const TextStyle(fontSize: 15, color: Colors.black54),
            ),
          ),
          Expanded(
            child: ListView.separated(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              itemCount: entries.length,
              // separatorBuilder — 항목 사이마다 끼워 넣을 위젯.
              // 여기서는 간격만 준다.
              separatorBuilder: (context, index) => const SizedBox(height: 12),
              itemBuilder: (context, index) {
                final entry = entries[index];
                final candidate = entry as Candidate;
                void onChange(int delta) {
                  _runCartRequest(
                    () => changeCartItem(entry, quantityDelta: delta),
                    // 수량을 더하거나 뺀 요청이 서버에서 성공한 뒤에만 실행한다.
                    // 마지막 `−`로 버튼이 비활성화될 때도 같은 반동을 한 번 보인다.
                    animateOrderFeedback: true,
                  );
                }

                return _CandidateCard(
                  candidate: candidate,
                  index: index,
                  quantity: _quantityOf(entry),
                  // 카드는 "눌렸다"만 알리고, 무엇을 할지는 이 화면이 정한다.
                  onTap: () => _openDetail(context, entry),
                  onChangeQuantity: onChange,
                  onSpeak: () => _playCachedName(candidate),
                );
              },
            ),
          ),
          _CartBar(
            cart: _cart,
            errorMessage: _cartError,
            orderFeedbackVersion: _orderFeedbackVersion,
            onClear: () => _runCartRequest(clearCart),
            onOrder: () => Navigator.push(
              context,
              MaterialPageRoute(
                builder: (context) => OrderSummaryScreen(cart: _cart!),
              ),
            ),
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
        builder: (context) =>
            DetailScreen(foodId: candidate.foodId, nameEn: candidate.nameEn),
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
    required this.index,
    required this.quantity,
    required this.onTap,
    required this.onChangeQuantity,
    required this.onSpeak,
  });

  final Candidate candidate;

  /// 목록에서의 자리. 사진 위 상자의 번호·색과 맞추는 데 쓴다.
  final int index;

  /// 지금 카트에 담긴 개수. 0이면 아직 안 담긴 것이다.
  final int quantity;

  /// 카드가 눌렸을 때 실행할 동작. 카드는 무엇을 할지 모르고 알리기만 한다.
  final VoidCallback onTap;

  /// +/− 를 눌렀을 때. +1 또는 -1을 넘긴다.
  final void Function(int delta) onChangeQuantity;

  final Future<void> Function() onSpeak;

  @override
  Widget build(BuildContext context) {
    return Card(
      clipBehavior: Clip.antiAlias, // 사진 모서리를 카드 모양에 맞춰 둥글게 자른다
      margin: EdgeInsets.zero,
      // InkWell — 누를 수 있게 만들고, 누를 때 물결 효과를 준다.
      // "이건 누르는 것"이라는 신호를 사용자에게 준다.
      child: InkWell(
        onTap: onTap,
        // Stack으로 안내 칩을 카드 모서리에 독립 배치한다. 제목 행에 칩을 넣으면
        // 긴 음식명이 칩의 폭만큼 잘려 "Su / nd / ae"처럼 깨질 수 있다.
        child: Stack(
          children: [
            Padding(
              padding: const EdgeInsets.all(12),
              // Row — 자식들을 가로로 나란히 놓는다. (사진 | 글자 | 화살표)
              child: Row(
                children: [
                  // 사진 위 상자와 같은 번호·색. 어느 카드가 어느 자리인지 잇는다.
                  Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      CandidateBadge(index: index),
                      const SizedBox(height: 6),
                      _Thumbnail(candidate: candidate),
                    ],
                  ),
                  const SizedBox(width: 12),
                  // Expanded — 사진과 화살표를 뺀 나머지 가로 공간을 글자가 다 쓴다.
                  // 이게 없으면 이름이 길 때 화면 밖으로 삐져나간다.
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        // 사용자가 영어권이라 영어 이름을 크게, 한글은 보조로 둔다.
                        // 안내 칩은 Stack의 우측 상단에 독립 배치되어 이 텍스트 폭을 줄이지 않는다.
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
                        // 메뉴판에 실제로 인쇄된 글자. 등록 이름과 다를 때만 보여준다 —
                        // 같으면 같은 말을 두 번 적는 꼴이고, 다를 때가 정말 중요하다.
                        // "쌈싸먹는 꽁치김치찌개"가 왜 "김치찌개"로 나왔는지 여기서 보인다.
                        //
                        // 가격은 뺀 쪽을 쓴다 — 바로 아래에 값이 따로 있어서, 줄 글자를
                        // 그대로 쓰면 "황기갈비탕 15,000" 밑에 "₩15,000"이 또 붙는다.
                        if (candidate.nameText != null &&
                            candidate.nameText != candidate.nameKr) ...[
                          const SizedBox(height: 2),
                          Text(
                            'Menu: ${candidate.nameText}',
                            style: const TextStyle(
                              fontSize: 12,
                              color: Colors.black45,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ],
                        // 메뉴판 이름 앞에 붙어 있던 재료·맵기. 같은 "김치찌개" 두 개를
                        // 가르는 유일한 단서가 이것뿐일 때가 있다(꽁치김치찌개).
                        if (candidate.modifiers.isNotEmpty) ...[
                          const SizedBox(height: 6),
                          _ModifierBadges(modifiers: candidate.modifiers),
                        ],
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
                        // 맵기 눈금. 고를지 말지를 카드 단계에서 판단하게 해주는 값이라
                        // 상세로 들어가기 전에 보여준다(웹앱도 후보 카드에 그린다).
                        //
                        // 맵기가 등록되지 않은 음식은 서버가 null을 준다. 그때는 눈금을
                        // 통째로 뺀다 — 0칸으로 그리면 "안 맵다"고 잘못 알려주는 셈이다.
                        if (candidate.spiceLevel != null) ...[
                          const SizedBox(height: 6),
                          SpiceGauge(level: candidate.spiceLevel!, size: 14),
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
                  _SpeakButton(onPressed: onSpeak),
                  _QuantityStepper(
                    quantity: quantity,
                    onChange: onChangeQuantity,
                  ),
                ],
              ),
            ),
            // 카드의 실제 상세 이동은 바깥 InkWell 하나가 담당한다. 이 칩은 누를 수
            // 있는 영역을 하나 더 만들지 않고, "카드 본문을 누르면 상세를 본다"는
            // 시각적 단서만 제공한다. 카드 우측 끝에 고정해 본문 줄 수와 무관하다.
            const Positioned(
              top: 12,
              right: 12,
              child: IgnorePointer(child: _ViewGuideAffordance()),
            ),
          ],
        ),
      ),
    );
  }
}

/// 후보 카드 본문을 누르면 상세 가이드로 간다는 시각적 단서.
///
/// 이 위젯에는 onPressed를 두지 않는다. 실제 이동은 부모 카드의 InkWell 하나가
/// 담당해 기존 food_id 전달·상세 데이터 로딩 흐름을 바꾸지 않는다.
class _ViewGuideAffordance extends StatelessWidget {
  const _ViewGuideAffordance();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        // Penpot의 카드 안내 칩과 같은 옅은 살구색·브라운 조합.
        color: const Color(0xFFF3E1DB),
        borderRadius: BorderRadius.circular(12),
      ),
      child: const Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            'View guide',
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w700,
              color: Color(0xFFA4563C),
            ),
          ),
          SizedBox(width: 3),
          Icon(Icons.chevron_right_rounded, size: 15, color: Color(0xFFA4563C)),
        ],
      ),
    );
  }
}

/// 파인튜닝 TTS가 미리 만든 음식명 캐시 WAV를 재생하는 버튼.
class _SpeakButton extends StatelessWidget {
  const _SpeakButton({required this.onPressed});

  final Future<void> Function() onPressed;

  @override
  Widget build(BuildContext context) {
    return IconButton(
      onPressed: onPressed,
      icon: const Icon(Icons.volume_up_outlined),
      tooltip: 'Hear the voice guide',
      visualDensity: VisualDensity.compact,
    );
  }
}

/// 수식어 배지들.
class _ModifierBadges extends StatelessWidget {
  const _ModifierBadges({required this.modifiers});

  final List<Modifier> modifiers;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Wrap(
      spacing: 6,
      runSpacing: 4,
      children: [
        for (final modifier in modifiers)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
            decoration: BoxDecoration(
              color: scheme.secondaryContainer,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Text(
              modifier.label,
              style: TextStyle(
                fontSize: 11,
                color: scheme.onSecondaryContainer,
              ),
            ),
          ),
      ],
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
/// 카트가 비어 있으면 Order·Clear 둘 다 비활성이다 — 빈 주문 확인 화면으로
/// 넘어가지 않게 하기 위함이다(EC-07).
class _CartBar extends StatefulWidget {
  const _CartBar({
    required this.cart,
    required this.errorMessage,
    required this.orderFeedbackVersion,
    required this.onClear,
    required this.onOrder,
  });

  /// 아직 못 받았으면 null. 그동안은 빈 카트와 같은 모양으로 둔다.
  final CartState? cart;

  final String? errorMessage;
  final int orderFeedbackVersion;
  final VoidCallback onClear;
  final VoidCallback onOrder;

  @override
  State<_CartBar> createState() => _CartBarState();
}

class _CartBarState extends State<_CartBar> {
  @override
  Widget build(BuildContext context) {
    final isEmpty = widget.cart?.isEmpty ?? true;

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
              if (widget.errorMessage != null) ...[
                Text(
                  widget.errorMessage!,
                  style: const TextStyle(fontSize: 12, color: Colors.redAccent),
                ),
                const SizedBox(height: 8),
              ],
              // 총계가 실제보다 싸 보이는 상태를 말없이 두지 않는다(EC-03).
              if (widget.cart?.hasUnpricedItems ?? false) ...[
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
                          isEmpty
                              ? 'Cart is empty'
                              : '${widget.cart!.itemCount} in cart',
                          style: const TextStyle(
                            fontSize: 13,
                            color: Colors.black54,
                          ),
                        ),
                        if (!isEmpty)
                          Text(
                            widget.cart!.totalDisplay,
                            style: const TextStyle(
                              fontSize: 20,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                      ],
                    ),
                  ),
                  TextButton(
                    onPressed: isEmpty ? null : widget.onClear,
                    child: const Text('Clear'),
                  ),
                  const SizedBox(width: 4),
                  _OrderBounceButton(
                    // 버전이 바뀌면 버튼만 새 상태로 교체한다. CartBar 전체의
                    // didUpdateWidget 중에 controller를 시작하지 않아도 되므로
                    // 카트 갱신과 애니메이션이 충돌하지 않는다.
                    key: ValueKey(widget.orderFeedbackVersion),
                    playOnMount: widget.orderFeedbackVersion > 0,
                    onPressed: isEmpty ? null : widget.onOrder,
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

/// 카트 수량 변경 뒤 Order 버튼에 주는 한 번의 반동.
///
/// 부모는 카트 변경 성공 시마다 [ValueKey]를 바꾼다. 따라서 이 위젯은 해당 순간에만
/// 새로 만들어지며, 최초 카트 조회(버전 0)에서는 움직이지 않는다. Flutter build 중
/// controller를 시작하면 렌더링 assertion이 날 수 있어, 첫 프레임 완료 후 시작한다.
class _OrderBounceButton extends StatefulWidget {
  const _OrderBounceButton({
    super.key,
    required this.playOnMount,
    required this.onPressed,
  });

  final bool playOnMount;
  final VoidCallback? onPressed;

  @override
  State<_OrderBounceButton> createState() => _OrderBounceButtonState();
}

class _OrderBounceButtonState extends State<_OrderBounceButton>
    with SingleTickerProviderStateMixin {
  // 수축 → 큰 반동 → 작은 반동 → 원래 크기. 520ms와 최대 1.16배는 iPhone
  // 시뮬레이터에서도 수량·활성화 텍스트 변화에 묻히지 않는 정도로 잡았다.
  static const _duration = Duration(milliseconds: 520);

  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: _duration,
  );

  late final Animation<double> _scale = TweenSequence<double>([
    TweenSequenceItem(
      tween: Tween(
        begin: 1.0,
        end: .88,
      ).chain(CurveTween(curve: Curves.easeInCubic)),
      weight: 16,
    ),
    TweenSequenceItem(
      tween: Tween(
        begin: .88,
        end: 1.16,
      ).chain(CurveTween(curve: Curves.easeOutBack)),
      weight: 42,
    ),
    TweenSequenceItem(
      tween: Tween(
        begin: 1.16,
        end: .96,
      ).chain(CurveTween(curve: Curves.easeOutBack)),
      weight: 25,
    ),
    TweenSequenceItem(
      tween: Tween(
        begin: .96,
        end: 1.0,
      ).chain(CurveTween(curve: Curves.easeOutCubic)),
      weight: 17,
    ),
  ]).animate(_controller);

  @override
  void initState() {
    super.initState();
    if (!widget.playOnMount) return;

    // ValueKey 교체로 만든 버튼의 첫 프레임이 보인 다음 시작한다. 이 순서라야
    // 새 활성 상태(색/disabled 여부)가 먼저 화면에 반영되고 Flutter build scope도
    // 안전하게 끝난다.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _controller.forward();
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ScaleTransition(
      scale: _scale,
      // 확대 중에도 버튼이 Row의 기준점에서 흔들리지 않게 중앙을 쓴다.
      alignment: Alignment.center,
      child: FilledButton(
        onPressed: widget.onPressed,
        child: const Text('Order'),
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
