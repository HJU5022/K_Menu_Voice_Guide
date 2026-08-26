/// 지원 음식 목록 — 이 서비스가 안내할 수 있는 음식 전체를 보여준다.
///
/// 왜 필요한가: 사진을 찍어 분석이 끝나야만 지원 여부를 알 수 있으면, 실패했을 때
/// 그때까지 기다린 시간이 통째로 헛수고가 된다. 그리고 "Unsupported dish" 안내를
/// 받아도 *무엇이* 지원되는지 모르면 다시 시도할지 판단할 근거가 없다
/// (`docs/specs/supported-foods.md`).
///
/// 설정 화면 안에 목록을 그대로 깔지 않고 화면을 나눈 이유: 50개가 설정 본문을
/// 통째로 차지해서 다른 항목이 보이지 않았다. 설정은 한 줄씩 요약하는 자리고,
/// 긴 목록은 들어가서 보는 자리다.
///
/// 열 때마다 다시 불러온다 — 담당자가 그사이 DB에 음식을 추가했을 수 있다(EC-04).
library;

import 'package:flutter/material.dart';

import '../api.dart';
import 'animated_gradient_back_button.dart';
import 'stitch_bar.dart';

class SupportedFoodsScreen extends StatefulWidget {
  const SupportedFoodsScreen({super.key});

  @override
  State<SupportedFoodsScreen> createState() => _SupportedFoodsScreenState();
}

class _SupportedFoodsScreenState extends State<SupportedFoodsScreen> {
  /// 아직 못 받았으면 null. 빈 목록(`[]`)과 구분해야 한다 —
  /// 빈 목록은 "등록된 음식이 없음"이라는 정상 응답이다(EC-03).
  List<SupportedFood>? _foods;

  String? _errorMessage;
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final foods = await fetchSupportedFoods();
      if (!mounted) return;
      setState(() => _foods = foods);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _errorMessage = e.message);
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Supported dishes'),
        leading: const AnimatedGradientBackButton(),
        // Penpot 05 보드에만 적용한 장식이다. 지원 음식 목록을 가져오는 API 동작은 그대로다.
        bottom: const PreferredSize(
          preferredSize: Size.fromHeight(AppBarStitchBand.preferredHeight),
          child: AppBarStitchBand(),
        ),
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
            child: Text(
              _subtitle(),
              style: const TextStyle(color: Colors.black54),
            ),
          ),
          Expanded(child: _buildList()),
        ],
      ),
    );
  }

  String _subtitle() {
    // 기다리는 동안 개수를 0으로 보여주면 "지원 음식 없음"처럼 읽힌다(EC-02).
    if (_isLoading) return 'Loading…';
    if (_errorMessage != null) return "Couldn't load the list";
    return 'This guide covers ${_foods!.length} dishes.';
  }

  Widget _buildList() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    // 목록을 못 받아도 화면 자체는 살아 있어야 한다(EC-01).
    // 나갔다 들어오게 만들지 말고 이 자리에서 다시 시도하게 한다.
    if (_errorMessage != null) {
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(_errorMessage!, style: const TextStyle(color: Colors.black54)),
            const SizedBox(height: 12),
            OutlinedButton(onPressed: _load, child: const Text('Try again')),
          ],
        ),
      );
    }

    if (_foods!.isEmpty) {
      return const Padding(
        padding: EdgeInsets.symmetric(horizontal: 16),
        child: Text(
          'No dishes are registered yet.',
          style: TextStyle(color: Colors.black54),
        ),
      );
    }

    return ListView.separated(
      padding: const EdgeInsets.only(bottom: 16),
      itemCount: _foods!.length,
      separatorBuilder: (context, index) => const Divider(height: 1),
      itemBuilder: (context, index) {
        final food = _foods![index];
        // 여행자는 영문으로 찾고 메뉴판에서는 한글로 대조하므로 둘 다 보여준다.
        return ListTile(
          title: Text(food.nameEn),
          subtitle: Text(food.nameKr),
        );
      },
    );
  }
}
