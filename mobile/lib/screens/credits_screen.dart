/// 출처·크레딧 — 이 앱이 쓰는 사진과 데이터의 출처를 한곳에 모은다.
///
/// 후보 카드에도 사진마다 출처를 붙이고 있지만(카드에서 사라지면 안 되는 항목이다),
/// 그건 "지금 보고 있는 사진 한 장"의 표기다. 어떤 자료를 어떤 라이선스로 쓰고
/// 있는지 전체를 한 번에 확인할 자리가 따로 있어야 한다.
///
/// **여기 적힌 사진 출처는 손으로 관리한다.** 서버가 출처를 음식별로만 주고 전체
/// 목록으로는 주지 않기 때문이다. `foods` 테이블의 `thumbnail_attribution`을
/// 바꾸면 이 파일도 같이 고쳐야 한다 — 2026-08-22 기준 50개 중 43 + 7이다.
library;

import 'package:flutter/material.dart';

/// Wikimedia Commons에서 가져온 사진들의 표기. 나머지 43장은 아래 [_photoNote] 참고.
const List<String> _wikimediaCredits = [
  'CC0 1.0 — Lee Eunyoung',
  'CC0 1.0 — JeongHO Suh (Pixabay)',
  'CC BY 4.0 — Chacha PD',
  'CC BY 2.0 — Chloe Lim (Flickr)',
  'CC BY 2.0 — pcamp (Flickr)',
  'CC BY-SA 2.0 — Korea.net / KOCIS',
  'CC BY-SA 2.0 — stuart_spivack (Flickr)',
];

const String _photoNote =
    '43 of the 50 dish photos come from the AI Hub Tourism Menu Board Dataset (NIA). '
    'The remaining 7 come from Wikimedia Commons, credited individually below.';

/// 화면에 밝히는 기술 스택. 루트 README의 "기술 스택"과 맞춘다.
const List<(String, String)> _stack = [
  ('Menu text recognition', 'PaddleOCR, OpenCV'),
  ('Dish name matching', 'RapidFuzz'),
  ('English voice', 'Qwen3-TTS 1.7B Base with a LoRA adapter fine-tuned by the team'),
  ('Dish information', 'Written by the team, stored in Supabase'),
  ('Server / app', 'FastAPI, Flutter'),
];

class CreditsScreen extends StatelessWidget {
  const CreditsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Credits & sources')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const _Heading('Dish photos'),
          const SizedBox(height: 6),
          const Text(_photoNote, style: TextStyle(color: Colors.black54, height: 1.4)),
          const SizedBox(height: 14),
          for (final credit in _wikimediaCredits)
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Text(
                '• Wikimedia Commons, $credit',
                style: const TextStyle(fontSize: 13, color: Colors.black54),
              ),
            ),
          const SizedBox(height: 24),
          const _Heading('Dish information'),
          const SizedBox(height: 6),
          // 이 문장이 중요하다 — 설명이 AI가 지어낸 말이 아니라는 뜻이기 때문이다.
          const Text(
            'Every description, allergy note and voice script was written by the team '
            'in advance. Nothing on this app is generated on the fly.',
            style: TextStyle(color: Colors.black54, height: 1.4),
          ),
          const SizedBox(height: 24),
          const _Heading('Built with'),
          const SizedBox(height: 6),
          for (final (label, value) in _stack)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    label,
                    style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
                  ),
                  Text(
                    value,
                    style: const TextStyle(fontSize: 13, color: Colors.black54),
                  ),
                ],
              ),
            ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }
}

class _Heading extends StatelessWidget {
  const _Heading(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(fontSize: 17, fontWeight: FontWeight.bold),
    );
  }
}
