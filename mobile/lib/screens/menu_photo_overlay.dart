/// 촬영한 메뉴판 사진 위에 후보가 나온 자리를 번호 상자로 표시한다.
///
/// 왜 필요한가: 후보 목록만 보면 "왜 이게 나왔지?"를 확인할 방법이 없다. 실제로
/// 사진에 없는 음식이 후보로 뜨는 일이 있었는데(`막국수` → `칼국수`), 그때 사용자가
/// 스스로 판단할 근거가 화면에 하나도 없었다. 사진 위에 상자를 얹고 **OCR이 그
/// 자리에서 실제로 읽은 글자**를 같이 보여주면, 틀린 후보를 바로 알아볼 수 있다.
///
/// 번호는 두 자리로 적는다(`01`, `02` …). 앱에서는 hover가 없으므로, 상자와
/// 카드를 **같은 색**으로 묶어 눈으로 짝지을 수 있게 했다.
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
    required this.entries,
    this.maxHeight = 260,
  });

  final File photo;

  /// 화면에 늘어놓는 메뉴 줄 전체(안내 가능한 것 + 그러지 못한 것).
  /// **순서가 번호와 색을 정하므로** 카드 목록과 같은 순서여야 한다.
  final List<CartAddable> entries;

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
        final aspectRatio = image.width / image.height;
        return Center(
          child: ConstrainedBox(
            constraints: BoxConstraints(maxHeight: maxHeight),
            // 목록 안의 사진은 작아서 번호 상자가 메뉴 글자를 덮는다(실측: 메뉴 24개짜리
            // 메뉴판에서 상자가 이름을 거의 다 가렸다). 눌러서 크게 볼 수 있게 한다.
            child: GestureDetector(
              onTap: () => _openFullScreen(context, aspectRatio),
              child: Stack(
                children: [
                  _PhotoWithMarkers(
                    photo: photo,
                    entries: entries,
                    aspectRatio: aspectRatio,
                  ),
                  const Positioned(right: 6, bottom: 6, child: _ZoomHint()),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  void _openFullScreen(BuildContext context, double aspectRatio) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => _FullScreenPhoto(
          photo: photo,
          entries: entries,
          aspectRatio: aspectRatio,
        ),
      ),
    );
  }

  static Future<ui.Image> _decode(File file) async {
    return decodeImageFromList(await file.readAsBytes());
  }
}

/// 사진 한 장과 그 위의 번호 상자. 목록 안과 전체 화면이 같은 그림을 써야
/// 번호·색이 어긋나지 않으므로 위젯 하나로 두고 양쪽에서 쓴다.
class _PhotoWithMarkers extends StatelessWidget {
  const _PhotoWithMarkers({
    required this.photo,
    required this.entries,
    required this.aspectRatio,
  });

  final File photo;
  final List<CartAddable> entries;
  final double aspectRatio;

  @override
  Widget build(BuildContext context) {
    return AspectRatio(
      aspectRatio: aspectRatio,
      child: Stack(
        fit: StackFit.expand,
        children: [
          Image.file(photo, fit: BoxFit.fill),
          // AspectRatio 덕분에 이 영역이 곧 사진 영역이라, 비율을 그대로 곱한다.
          LayoutBuilder(
            builder: (context, constraints) => Stack(
              children: [
                for (final (index, entry) in entries.indexed)
                  if (entry.source != null)
                    ..._sourceMarkers(
                      index: index,
                      source: entry.source!,
                      area: constraints.biggest,
                    ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// 사진을 눌러 크게 볼 수 있다는 표시. 사진 위에 얹으므로 어두운 반투명 바탕을 깐다.
class _ZoomHint extends StatelessWidget {
  const _ZoomHint();

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.black54,
        borderRadius: BorderRadius.circular(4),
      ),
      child: const Padding(
        padding: EdgeInsets.symmetric(horizontal: 6, vertical: 3),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.zoom_in, size: 14, color: Colors.white),
            SizedBox(width: 3),
            Text('Tap to zoom', style: TextStyle(fontSize: 11, color: Colors.white)),
          ],
        ),
      ),
    );
  }
}

/// 사진을 화면 가득 띄우고 손가락으로 확대·이동하게 하는 화면.
///
/// 목록 안에서 바로 확대하지 않는 이유: 사진이 스크롤 목록 안에 있어서, 손가락을
/// 끌면 사진을 옮기려는 것인지 목록을 넘기려는 것인지 구분되지 않는다. 화면을
/// 따로 열면 그 충돌이 없고, 볼 수 있는 넓이도 커진다.
///
/// [InteractiveViewer]는 Flutter 기본 위젯이라 따로 받아올 것이 없다.
class _FullScreenPhoto extends StatelessWidget {
  const _FullScreenPhoto({
    required this.photo,
    required this.entries,
    required this.aspectRatio,
  });

  final File photo;
  final List<CartAddable> entries;
  final double aspectRatio;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      // 사진을 보는 화면이라 배경을 어둡게 둔다 — 밝은 바탕이면 사진 가장자리가
      // 어디까지인지 알기 어렵다.
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: const Text('Pinch to zoom'),
      ),
      body: Center(
        child: InteractiveViewer(
          // 축소는 원래 크기까지만 — 더 줄이면 검은 화면에 사진이 떠 있는 꼴이 된다.
          minScale: 1,
          maxScale: 6,
          child: _PhotoWithMarkers(
            photo: photo,
            entries: entries,
            aspectRatio: aspectRatio,
          ),
        ),
      ),
    );
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
