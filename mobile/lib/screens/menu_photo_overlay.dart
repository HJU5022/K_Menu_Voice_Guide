/// 촬영한 메뉴판 사진 위에 후보가 나온 자리를 번호 상자로 표시한다.
///
/// 왜 필요한가: 후보 목록만 보면 "왜 이게 나왔지?"를 확인할 방법이 없다. 실제로
/// 사진에 없는 음식이 후보로 뜨는 일이 있었는데(`막국수` → `칼국수`), 그때 사용자가
/// 스스로 판단할 근거가 화면에 하나도 없었다. 사진 위에 상자를 얹고 **OCR이 그
/// 자리에서 실제로 읽은 글자**를 같이 보여주면, 틀린 후보를 바로 알아볼 수 있다.
///
/// 웹앱(`frontend/src/App.tsx`)이 같은 방식을 쓰고 있어 번호 규칙(`01`, `02` …)을
/// 맞췄다. 앱에서는 hover가 없으므로, 상자와 카드를 **같은 색**으로 묶어 눈으로
/// 짝지을 수 있게 했다.
///
/// 좌표는 서버가 원본 사진 기준 0~1 비율로 준다(`CandidateSource`). 그래서 사진을
/// 어떤 크기로 그리든 비율만 곱하면 자리가 맞는다 — 다만 그리는 영역이 사진과
/// **정확히 같은 비율**이어야 해서, AspectRatio로 그 조건을 만든다.
library;

import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import '../api.dart';

/// 후보 번호에 돌려 쓰는 색. 사진 위에서도 구분되도록 진한 색만 골랐다.
///
/// 후보가 6개를 넘으면 색이 반복된다. 번호가 같이 붙어 있어 헷갈리지 않고,
/// 색을 더 늘리면 서로 비슷해져서 오히려 구분이 어려워진다.
const List<Color> _paletteColors = [
  Color(0xFFD32F2F), // red
  Color(0xFF1976D2), // blue
  Color(0xFF388E3C), // green
  Color(0xFFF57C00), // orange
  Color(0xFF7B1FA2), // purple
  Color(0xFF0097A7), // cyan
];

/// 목록에서 index번째 후보의 색. 사진 상자와 카드 배지가 같은 값을 써야 짝지어진다.
Color candidateColor(int index) => _paletteColors[index % _paletteColors.length];

/// 후보 번호 표기. 웹앱과 같게 두 자리로 채운다(`01`, `02` …).
String candidateLabel(int index) => (index + 1).toString().padLeft(2, '0');

class MenuPhotoOverlay extends StatelessWidget {
  const MenuPhotoOverlay({
    super.key,
    required this.photo,
    required this.candidates,
    this.maxHeight = 260,
  });

  final File photo;

  /// 후보 목록. **순서가 번호와 색을 정하므로** 카드 목록과 같은 순서여야 한다.
  final List<Candidate> candidates;

  final double maxHeight;

  @override
  Widget build(BuildContext context) {
    // 사진의 가로세로 비를 알아야 상자 자리가 맞는다. 파일을 한 번 디코드해서 얻는다.
    return FutureBuilder<ui.Image>(
      future: _decode(photo),
      builder: (context, snapshot) {
        final image = snapshot.data;
        if (image == null) {
          // 디코드 전에는 자리만 잡아둔다. 목록이 위아래로 덜컥이지 않게 하기 위함.
          return SizedBox(height: maxHeight, child: const Center(child: CircularProgressIndicator()));
        }
        return Center(
          child: ConstrainedBox(
            constraints: BoxConstraints(maxHeight: maxHeight),
            child: AspectRatio(
              aspectRatio: image.width / image.height,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  Image.file(photo, fit: BoxFit.fill),
                  // AspectRatio 덕분에 이 영역이 곧 사진 영역이라, 비율을 그대로 곱한다.
                  LayoutBuilder(
                    builder: (context, constraints) => Stack(
                      children: [
                        for (final (index, candidate) in candidates.indexed)
                          if (candidate.source != null)
                            ..._sourceMarkers(
                              index: index,
                              source: candidate.source!,
                              area: constraints.biggest,
                            ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  static Future<ui.Image> _decode(File file) async {
    return decodeImageFromList(await file.readAsBytes());
  }
}

/// 상자 하나가 만드는 위젯 두 개 — 테두리와, 그 밖에 붙는 번호 배지.
///
/// 배지를 상자 **안**에 두면 읽어낸 글자의 첫 자를 가린다(실제로 "01"이 "김"을
/// 덮었다). 상자가 글자에 딱 맞게 그려지기 때문이다. 그래서 위쪽 바깥에 두고,
/// 사진 맨 위라 자리가 없으면 아래쪽 바깥으로 내린다.
const double _badgeHeight = 14;

List<Widget> _sourceMarkers({
  required int index,
  required CandidateSource source,
  required Size area,
}) {
  final color = candidateColor(index);
  final left = source.left * area.width;
  final top = source.top * area.height;
  final width = source.width * area.width;
  final height = source.height * area.height;

  final above = top - _badgeHeight - 1;
  final badgeTop = above >= 0 ? above : top + height + 1;

  return [
    Positioned(
      left: left,
      top: top,
      width: width,
      height: height,
      child: DecoratedBox(
        decoration: BoxDecoration(
          border: Border.all(color: color, width: 2),
          // 글자가 비치도록 아주 옅게만 채운다. 진하게 채우면 무엇을 읽었는지 못 본다.
          color: color.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(3),
        ),
      ),
    ),
    Positioned(
      left: left,
      top: badgeTop,
      height: _badgeHeight,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 4),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(3),
        ),
        child: Text(
          candidateLabel(index),
          style: const TextStyle(
            color: Colors.white,
            fontSize: 9,
            fontWeight: FontWeight.bold,
            height: 1.1,
          ),
        ),
      ),
    ),
  ];
}

/// 카드 왼쪽에 붙는 번호 배지 — 사진 위 상자와 같은 색·같은 번호.
class CandidateBadge extends StatelessWidget {
  const CandidateBadge({super.key, required this.index});

  final int index;

  @override
  Widget build(BuildContext context) {
    final color = candidateColor(index);
    return Container(
      width: 24,
      height: 24,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        candidateLabel(index),
        style: const TextStyle(
          color: Colors.white,
          fontSize: 11,
          fontWeight: FontWeight.bold,
        ),
      ),
    );
  }
}
