/// 사용법 — 처음 켠 사람에게 이 앱이 무엇을 하는지 세 단계로 알려준다.
///
/// 촬영 화면만 보면 "메뉴판을 찍으면 뭐가 되는지"를 찍어보기 전엔 알 수 없다.
/// 여행자는 식당 앞에서 잠깐 확인하는 상황이라, 찍기 전에 읽을 자리가 필요하다.
///
/// 마지막 두 줄(지원 범위·가격 출처)은 안내가 아니라 **오해 방지**다. 등록된
/// 음식만 안내한다는 점과, 가격이 DB 값이 아니라 그 사진에서 읽은 값이라는 점은
/// 모르면 앱이 틀렸다고 오해하기 쉬운 지점이다.
library;

import 'package:flutter/material.dart';

import 'animated_gradient_back_button.dart';

class HowItWorksScreen extends StatelessWidget {
  const HowItWorksScreen({super.key});

  static const List<(IconData, String, String)> _steps = [
    (
      Icons.photo_camera_outlined,
      'Take a photo',
      'Point your camera at a Korean menu, or pick a photo you already took.',
    ),
    (
      Icons.checklist,
      'Pick a dish',
      'The app reads the menu and lists the dishes it recognised. Tap the one you want.',
    ),
    (
      Icons.volume_up_outlined,
      'Read and listen',
      'You get what it is, how to eat it, ingredients, allergies, pronunciation and spice level — with an English voice guide.',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('How it works'),
        leading: const AnimatedGradientBackButton(),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          for (final (index, step) in _steps.indexed) ...[
            _Step(number: index + 1, icon: step.$1, title: step.$2, body: step.$3),
            const SizedBox(height: 20),
          ],
          const Divider(),
          const SizedBox(height: 12),
          const _Note(
            'This guide covers a fixed set of registered dishes. '
            'If a dish is not registered, the app says so instead of guessing. '
            'See Supported dishes in Settings.',
          ),
          const SizedBox(height: 12),
          const _Note(
            'Prices come from the photo you took, not from a database. '
            'If a price is missing on the menu, the app leaves it blank.',
          ),
        ],
      ),
    );
  }
}

class _Step extends StatelessWidget {
  const _Step({
    required this.number,
    required this.icon,
    required this.title,
    required this.body,
  });

  final int number;
  final IconData icon;
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        CircleAvatar(
          radius: 18,
          backgroundColor: Theme.of(context).colorScheme.primaryContainer,
          child: Icon(icon, size: 20),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '$number. $title',
                style: const TextStyle(fontSize: 17, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 4),
              Text(body, style: const TextStyle(color: Colors.black54, height: 1.4)),
            ],
          ),
        ),
      ],
    );
  }
}

class _Note extends StatelessWidget {
  const _Note(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(fontSize: 13, color: Colors.black45, height: 1.4),
    );
  }
}
