/// ③ 상세 화면 — 고른 음식의 설명을 보여주고 내레이션 음성을 재생한다.
///
/// 하는 일
///   1. `GET /api/foods/{food_id}`를 호출한다.
///   2. details의 6개 카테고리를 카드로 표시한다.
///   3. narration_audio_path의 음성을 재생한다(audioplayers).
///
/// 카테고리 6개와 화면 제목은 프론트엔드와 통일한다
/// (`frontend/docs/content-style.md` 기준, app.py의 DETAIL_CARDS와 같은 순서):
///   DESCRIPTION / HOW_TO_EAT / INGREDIENT / ALLERGY / PRONUNCIATION / SPICY
///
/// TTS 실패는 화면 실패가 아니다 — tts_status가 "ok"가 아니거나
/// narration_audio_path가 null이면 **텍스트는 그대로 보여주고** 음성 영역만
/// 비활성으로 표시한다(`flutter-mobile-app.md` EC-05, 루트 README 9절
/// "TTS 생성 실패 → 상세 텍스트 우선 출력").
///
/// ── 이 파일을 읽는 데 필요한 개념 ──────────────────────────────────
///
/// initState — 화면이 처음 만들어질 때 딱 한 번 실행되는 함수
///   앞의 두 화면은 사용자가 버튼을 눌러야 서버를 불렀지만, 이 화면은 열리자마자
///   불러야 한다. 그 "열리자마자"에 해당하는 자리가 initState다.
///
/// dispose — 화면이 사라질 때 실행되는 함수
///   음성 재생기는 화면을 닫아도 저절로 멈추지 않는다. 뒤로 갔는데 소리가 계속
///   나는 것을 막으려면 여기서 직접 정리해야 한다.
///
/// 스트림(구독) — 계속 흘러오는 소식을 받는 것
///   음성은 재생 중에 상태가 계속 바뀐다(재생 중 → 끝남). 재생기가 그 변화를
///   흘려보내주면, 화면이 그걸 듣고 버튼 모양을 바꾼다.
library;

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';

import '../api.dart';

/// 화면에 보여줄 카테고리 순서와 제목.
///
/// 서버가 주는 details는 순서가 없는 묶음이라, 무엇을 어떤 순서로 보여줄지는
/// 화면이 정한다. 순서와 영어 제목은 웹앱(app.py의 DETAIL_CARDS)과 맞췄다 —
/// 같은 서비스인데 웹과 앱의 문구가 다르면 안 된다.
const List<({String key, String title, IconData icon})> _detailCards = [
  (key: 'DESCRIPTION', title: 'Description', icon: Icons.restaurant_menu),
  (key: 'HOW_TO_EAT', title: 'How to eat', icon: Icons.rice_bowl),
  (key: 'INGREDIENT', title: 'Ingredients', icon: Icons.egg_alt),
  (key: 'ALLERGY', title: 'Allergies & dietary needs', icon: Icons.warning_amber),
  (key: 'PRONUNCIATION', title: 'Pronunciation', icon: Icons.record_voice_over),
  (key: 'SPICY', title: 'Spice level', icon: Icons.local_fire_department),
];

class DetailScreen extends StatefulWidget {
  const DetailScreen({
    super.key,
    required this.foodId,
    required this.nameEn,
  });

  /// 후보 화면에서 넘겨받은 음식 번호. 이 번호로 서버에 다시 물어본다.
  final int foodId;

  /// 응답을 기다리는 동안 상단 제목에 미리 띄울 이름.
  ///
  /// 이미 후보 화면에서 알고 있는 값이라 굳이 로딩을 기다릴 이유가 없다.
  /// 제목이 비었다가 채워지면 화면이 덜컥거려 보인다.
  final String nameEn;

  @override
  State<DetailScreen> createState() => _DetailScreenState();
}

class _DetailScreenState extends State<DetailScreen> {
  /// 음성 재생기. 화면 하나당 하나만 두고, 화면이 사라질 때 정리한다.
  final AudioPlayer _player = AudioPlayer();

  FoodDetail? _food;
  String? _errorMessage;
  bool _isLoading = true;

  /// 지금 소리가 나고 있는지. 버튼 모양(▶ / ⏸)을 정하는 데 쓴다.
  bool _isPlaying = false;

  /// 음성 파일을 못 받았거나 재생에 실패했는지(EC-06).
  /// 서버가 TTS에 실패한 것(EC-05)과는 다른 상황이라 따로 둔다.
  bool _audioFailed = false;

  @override
  void initState() {
    super.initState();

    // 재생기가 알려주는 상태 변화를 듣는다. 사용자가 버튼을 눌러 멈췄든,
    // 음성이 끝까지 재생돼 저절로 멈췄든 여기로 들어온다.
    _player.onPlayerStateChanged.listen((state) {
      if (!mounted) return;
      setState(() => _isPlaying = state == PlayerState.playing);
    });

    _load();
  }

  @override
  void dispose() {
    // 화면을 떠날 때 재생기를 정리한다. 이걸 빠뜨리면 뒤로 갔는데도
    // 소리가 계속 나고, 재생기가 메모리에 남는다.
    _player.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final food = await fetchFood(widget.foodId);
      if (!mounted) return;
      setState(() => _food = food);

      // 텍스트를 먼저 화면에 올린 뒤에 음성을 시작한다. 순서를 바꾸면
      // 음성 준비가 느릴 때 글자까지 늦게 보인다.
      if (food.hasAudio) {
        _startAudio(food.audioUrl!);
      }
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _errorMessage = e.message);
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  /// 음성을 처음부터 재생한다.
  ///
  /// 화면에 들어오면 바로 들려주는 게 이 서비스의 목적(음성 가이드)에 맞다.
  /// 재생에 실패해도 예외를 밖으로 던지지 않는다 — 텍스트는 이미 화면에 있고,
  /// 음성 하나 때문에 화면 전체가 실패로 바뀌면 안 된다(EC-06).
  Future<void> _startAudio(String url) async {
    try {
      await _player.play(UrlSource(url));
    } catch (_) {
      if (!mounted) return;
      setState(() => _audioFailed = true);
    }
  }

  /// 재생 버튼을 눌렀을 때. 나고 있으면 멈추고, 멈춰 있으면 처음부터 다시 튼다.
  Future<void> _togglePlay() async {
    final food = _food;
    if (food == null || !food.hasAudio) return;

    if (_isPlaying) {
      await _player.pause();
    } else {
      await _startAudio(food.audioUrl!);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.nameEn)),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(),
            SizedBox(height: 16),
            Text('Getting the details…'),
          ],
        ),
      );
    }

    if (_errorMessage != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.wifi_off, size: 48, color: Colors.black38),
              const SizedBox(height: 12),
              const Text(
                "Can't reach the server",
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              Text(
                _errorMessage!,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.black54),
              ),
              const SizedBox(height: 16),
              // 서버가 잠깐 끊긴 경우가 많아, 화면을 나갔다 들어오지 않고
              // 그 자리에서 다시 시도할 수 있게 한다(EC-02).
              FilledButton.icon(
                onPressed: _load,
                icon: const Icon(Icons.refresh),
                label: const Text('Try again'),
              ),
            ],
          ),
        ),
      );
    }

    final food = _food;
    if (food == null) return const SizedBox.shrink();

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
      children: [
        _NameHeader(food: food),
        const SizedBox(height: 16),
        _AudioBar(
          food: food,
          isPlaying: _isPlaying,
          audioFailed: _audioFailed,
          onToggle: _togglePlay,
        ),
        const SizedBox(height: 20),
        // 6개 카테고리를 정해둔 순서대로 그린다.
        //
        // 서버가 특정 카테고리를 비워 보낼 수 있으므로 없는 것은 건너뛴다 —
        // 빈 카드가 있으면 정보가 누락된 것처럼 보인다.
        for (final card in _detailCards)
          if ((food.details[card.key] ?? '').trim().isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: _DetailCard(
                icon: card.icon,
                title: card.title,
                body: food.details[card.key]!,
              ),
            ),
      ],
    );
  }
}

/// 화면 맨 위의 이름 영역.
class _NameHeader extends StatelessWidget {
  const _NameHeader({required this.food});

  final FoodDetail food;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          food.nameEn,
          style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 4),
        Text(
          food.nameKr,
          style: const TextStyle(fontSize: 16, color: Colors.black54),
        ),
        const SizedBox(height: 8),
        _SpiceGauge(level: food.spiceLevel),
      ],
    );
  }
}

/// 맵기 눈금 — 불꽃 5칸 중 spice_level 만큼 채운다.
///
/// 웹앱(app.py 결과 화면)이 "🌶️" × level + "·" × (5 - level)로 그리던 것과 같은 규칙이다.
/// 상세 카드의 SPICY 텍스트가 설명이라면 이건 한눈에 보는 눈금이라, 둘 다 필요하다.
/// 아이콘은 SPICY 카드가 이미 쓰고 있는 것을 그대로 재사용한다.
class _SpiceGauge extends StatelessWidget {
  const _SpiceGauge({required this.level});

  final int level;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: List.generate(5, (index) {
        return Padding(
          padding: const EdgeInsets.only(right: 2),
          child: Icon(
            Icons.local_fire_department,
            size: 18,
            color: index < level ? Colors.deepOrange : Colors.black26,
          ),
        );
      }),
    );
  }
}

/// 음성 재생 영역.
///
/// 세 가지 상태를 구분해서 보여준다.
///   재생 가능   ▶ / ⏸ 버튼과 내레이션 문구
///   서버 TTS 실패  버튼을 비활성으로 두고 이유를 적는다 (EC-05)
///   재생 실패     같은 모양이되 문구만 다르다 (EC-06)
///
/// 어느 경우에도 아래 상세 텍스트는 그대로 보인다 — 음성은 덤이지 전부가 아니다.
class _AudioBar extends StatelessWidget {
  const _AudioBar({
    required this.food,
    required this.isPlaying,
    required this.audioFailed,
    required this.onToggle,
  });

  final FoodDetail food;
  final bool isPlaying;
  final bool audioFailed;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) {
    final bool usable = food.hasAudio && !audioFailed;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: usable
            ? Theme.of(context).colorScheme.primaryContainer
            : Colors.black12,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          IconButton.filled(
            // onPressed가 null이면 버튼이 자동으로 비활성된다.
            onPressed: usable ? onToggle : null,
            iconSize: 32,
            icon: Icon(isPlaying ? Icons.pause : Icons.play_arrow),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              usable
                  ? food.narrationText
                  : audioFailed
                      ? "We couldn't play the audio, but you can still read "
                          'everything below.'
                      : 'Audio is not ready for this dish yet. '
                          'The description below is complete.',
              style: TextStyle(
                fontSize: 13,
                color: usable ? Colors.black87 : Colors.black54,
              ),
              maxLines: 4,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}

/// 카테고리 하나를 보여주는 카드.
class _DetailCard extends StatelessWidget {
  const _DetailCard({
    required this.icon,
    required this.title,
    required this.body,
  });

  final IconData icon;
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, size: 18, color: Theme.of(context).colorScheme.primary),
                const SizedBox(width: 8),
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 0.3,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(body, style: const TextStyle(fontSize: 15, height: 1.45)),
          ],
        ),
      ),
    );
  }
}
