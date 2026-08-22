/// ① 촬영 화면 — 앱을 열면 처음 보이는 화면.
///
/// 하는 일
///   1. 카메라로 메뉴판을 촬영한다(또는 사진첩에서 고른다).
///   2. 찍은 이미지를 `POST /api/analyze`로 보낸다.
///   3. 결과를 화면에 보여준다.
///
/// 사진첩 선택도 함께 제공한다. 카메라 권한을 거부당했을 때의 대체 경로이고
/// (`flutter-mobile-app.md` EC-01), iOS 시뮬레이터에는 카메라가 아예 없어서
/// 개발 중에는 이 경로로만 화면을 확인할 수 있다.
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../api.dart';
import '../config.dart';

class CameraScreen extends StatefulWidget {
  const CameraScreen({super.key});

  @override
  State<CameraScreen> createState() => _CameraScreenState();
}

class _CameraScreenState extends State<CameraScreen> {
  /// 서버 응답을 기다리는 중인지. true인 동안 버튼을 잠그고 로딩을 표시한다.
  ///
  /// OCR은 실측 약 8초(첫 요청 10초)가 걸린다. 이 표시가 없으면 사용자가
  /// 앱이 멈춘 줄 알고 나가버린다(EC-07).
  bool _isLoading = false;

  /// 서버에 아예 닿지 못했을 때의 안내. 성공하면 다시 null로 비운다.
  String? _errorMessage;

  /// 마지막 분석 결과. 아직 한 번도 분석하지 않았으면 null.
  AnalyzeResult? _result;

  Future<void> _pickAndAnalyze(ImageSource source) async {
    final picked = await ImagePicker().pickImage(source: source);
    // 사용자가 촬영/선택을 취소한 경우다. 오류가 아니므로 조용히 돌아간다.
    if (picked == null) return;

    setState(() {
      _isLoading = true;
      _errorMessage = null;
      _result = null;
    });

    try {
      final result = await analyze(File(picked.path));
      // await로 기다리는 사이에 사용자가 화면을 떠났을 수 있다. 그 상태에서
      // setState를 부르면 예외가 나므로 화면이 아직 살아있는지 먼저 확인한다.
      if (!mounted) return;
      setState(() => _result = result);
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
      appBar: AppBar(title: const Text('K-Menu')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'Point your camera at a Korean menu',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            const Text(
              "We'll tell you what each dish is, how it tastes, "
              'and how spicy it gets.',
              style: TextStyle(fontSize: 14, color: Colors.black54),
            ),
            const SizedBox(height: 24),
            FilledButton.icon(
              // 로딩 중에는 onPressed를 null로 두면 버튼이 자동으로 비활성된다.
              // 사용자가 연달아 눌러 요청이 겹치는 것을 막는다.
              onPressed: _isLoading
                  ? null
                  : () => _pickAndAnalyze(ImageSource.camera),
              icon: const Icon(Icons.photo_camera),
              label: const Text('Take a photo'),
            ),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: _isLoading
                  ? null
                  : () => _pickAndAnalyze(ImageSource.gallery),
              icon: const Icon(Icons.photo_library),
              label: const Text('Choose from library'),
            ),
            const SizedBox(height: 32),
            Expanded(child: _buildResultArea()),
          ],
        ),
      ),
    );
  }

  /// 화면 아래쪽에 상황에 맞는 내용을 보여준다.
  /// 로딩 > 오류 > 결과 순으로 확인한다 — 가장 급한 상태가 먼저다.
  Widget _buildResultArea() {
    if (_isLoading) {
      return const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(),
            SizedBox(height: 16),
            Text('Reading the menu…'),
            SizedBox(height: 4),
            // 8초를 그냥 기다리게 하면 멈춘 것처럼 보인다. 얼마나 걸리는지
            // 미리 알려주면 같은 시간도 훨씬 짧게 느껴진다.
            Text(
              'This takes a few seconds',
              style: TextStyle(fontSize: 12, color: Colors.black45),
            ),
          ],
        ),
      );
    }

    if (_errorMessage != null) {
      // 서버에 못 닿은 경우다. 주소를 함께 보여줘야 원인(서버가 꺼져 있는지,
      // 주소가 틀렸는지)을 바로 짚을 수 있다(EC-02).
      return _MessagePanel(
        icon: Icons.wifi_off,
        title: "Can't reach the server",
        body: '$_errorMessage\n\nMake sure the server is running '
            'and your phone is on the same Wi-Fi.\n$apiBaseUrl',
      );
    }

    final result = _result;
    if (result == null) {
      return const SizedBox.shrink();
    }

    // 글자를 아예 못 읽은 경우 — 다시 찍는 방법을 알려준다(EC-03).
    if (result.isOcrEmpty) {
      return const _MessagePanel(
        icon: Icons.image_not_supported_outlined,
        title: "We couldn't read this photo",
        body: 'Try brighter lighting, hold the menu straight, '
            'and move closer to the text.',
      );
    }

    // 글자는 읽혔지만 아는 음식이 없는 경우 — 위와 원인이 달라 문구도 다르다(EC-04).
    if (result.isUnsupportedFood) {
      return _MessagePanel(
        icon: Icons.search_off,
        title: 'Not in our guide yet',
        body: 'We read the menu but none of these dishes are in our guide '
            'of 50 Korean foods.\n\nWhat we read:\n${result.ocrText}',
      );
    }

    // 성공. 다음 단계(후보 선택 화면)는 아직 없으므로 지금은 목록만 확인한다.
    return ListView.builder(
      itemCount: result.candidates.length,
      itemBuilder: (context, index) {
        final candidate = result.candidates[index];
        return ListTile(
          leading: CircleAvatar(child: Text('${index + 1}')),
          title: Text(candidate.nameEn),
          subtitle: Text(candidate.nameKr),
          trailing: Text('${candidate.score}'),
        );
      },
    );
  }
}

/// 안내 문구를 보여주는 공통 틀. 오류·재촬영 안내가 같은 모양을 쓴다.
class _MessagePanel extends StatelessWidget {
  const _MessagePanel({
    required this.icon,
    required this.title,
    required this.body,
  });

  final IconData icon;
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      child: Column(
        children: [
          Icon(icon, size: 48, color: Colors.black38),
          const SizedBox(height: 12),
          Text(
            title,
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 8),
          Text(
            body,
            style: const TextStyle(color: Colors.black54),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}
