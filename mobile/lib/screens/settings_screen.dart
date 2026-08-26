/// 설정 화면 — 앱 정보와 안내 항목을 한 줄씩 모아둔 자리.
///
/// 설정 화면은 **요약하는 자리**다. 긴 내용은 여기 깔지 않고 눌러서 들어가게 한다.
/// 지원 음식 50개를 이 화면 본문에 그대로 두었더니 다른 항목이 아예 보이지 않아
/// [SupportedFoodsScreen]으로 분리했다.
///
/// 서버 주소를 노출하는 이유: 시연·개발 중 `apiBaseUrl`이 맥 IP와 어긋나 앱이
/// 서버를 못 찾는 일이 반복됐다. 터미널을 보지 않고 폰에서 바로 확인할 수 있으면
/// 원인을 훨씬 빨리 좁힌다.
library;

import 'package:flutter/material.dart';

import '../api.dart';
import 'animated_gradient_back_button.dart';
import '../config.dart';
import 'credits_screen.dart';
import 'how_it_works_screen.dart';
import 'supported_foods_screen.dart';

/// 화면에 표시할 앱 버전. `mobile/pubspec.yaml`의 `version`과 맞춰야 한다.
///
/// 빌드 시점에 자동으로 읽어오려면 package_info_plus 의존성이 필요한데, 값 하나
/// 때문에 패키지를 더하지 않았다. pubspec을 올릴 때 이 줄도 같이 올린다.
const String _appVersion = '1.0.0';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  /// 지원 음식 개수. 못 받았으면 null.
  int? _dishCount;

  /// 서버에 닿지 못했을 때의 이유. 닿았으면 null.
  String? _connectionError;

  bool _isChecking = true;

  @override
  void initState() {
    super.initState();
    _check();
  }

  /// 요청 한 번으로 두 가지를 동시에 안다 — 서버에 닿는지, 음식이 몇 개인지.
  /// 같은 걸 두 번 물을 이유가 없어 목록 요청 하나로 연결 확인까지 겸한다.
  Future<void> _check() async {
    setState(() {
      _isChecking = true;
      _connectionError = null;
    });

    try {
      final foods = await fetchSupportedFoods();
      if (!mounted) return;
      setState(() => _dishCount = foods.length);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _connectionError = e.message);
    } finally {
      if (mounted) setState(() => _isChecking = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Settings'),
        leading: const AnimatedGradientBackButton(),
      ),
      body: ListView(
        children: [
          const _AppHeader(),
          const _SectionTitle('Guide'),
          ListTile(
            leading: const Icon(Icons.help_outline),
            title: const Text('How it works'),
            subtitle: const Text('Three steps, and what this app does not do'),
            trailing: const Icon(Icons.chevron_right, color: Colors.black38),
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (context) => const HowItWorksScreen()),
            ),
          ),
          ListTile(
            leading: const Icon(Icons.restaurant_menu),
            title: const Text('Supported dishes'),
            subtitle: const Text('Dishes this guide can explain'),
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                // 개수를 못 받았을 때 0을 쓰면 "지원 음식 없음"으로 읽힌다.
                Text(
                  _isChecking ? '…' : (_dishCount?.toString() ?? '—'),
                  style: const TextStyle(fontSize: 16, color: Colors.black54),
                ),
                const Icon(Icons.chevron_right, color: Colors.black38),
              ],
            ),
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(
                builder: (context) => const SupportedFoodsScreen(),
              ),
            ),
          ),
          ListTile(
            leading: const Icon(Icons.copyright_outlined),
            title: const Text('Credits & sources'),
            subtitle: const Text('Where the photos and information come from'),
            trailing: const Icon(Icons.chevron_right, color: Colors.black38),
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (context) => const CreditsScreen()),
            ),
          ),
          const _SectionTitle('Connection'),
          _ConnectionTile(
            isChecking: _isChecking,
            errorMessage: _connectionError,
            onRetry: _check,
          ),
          const _SectionTitle('Legal'),
          ListTile(
            leading: const Icon(Icons.description_outlined),
            title: const Text('Open source licenses'),
            trailing: const Icon(Icons.chevron_right, color: Colors.black38),
            // Flutter가 기본으로 만들어주는 화면이다. 직접 만들 이유가 없다.
            onTap: () => showLicensePage(
              context: context,
              applicationName: 'K-Menu Voice Guide',
              applicationVersion: _appVersion,
            ),
          ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }
}

/// 화면 맨 위의 앱 이름·버전·한 줄 소개.
class _AppHeader extends StatelessWidget {
  const _AppHeader();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 20, 16, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'K-Menu Voice Guide',
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 4),
          const Text(
            'Photograph a Korean menu and hear what each dish is.',
            style: TextStyle(fontSize: 14, color: Colors.black54),
          ),
          const SizedBox(height: 8),
          Text(
            'Version $_appVersion',
            style: const TextStyle(fontSize: 12, color: Colors.black38),
          ),
        ],
      ),
    );
  }
}

/// 항목 묶음의 제목. 목록이 길어졌을 때 눈이 쉬는 자리가 된다.
class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 20, 16, 4),
      child: Text(
        text.toUpperCase(),
        style: const TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.bold,
          color: Colors.black45,
          letterSpacing: 0.6,
        ),
      ),
    );
  }
}

/// 서버 연결 상태 한 줄.
///
/// 주소를 항상 보여주고, 닿았는지 여부만 오른쪽에 표시한다. 못 닿았을 때는
/// 이 자리에서 바로 다시 시도할 수 있게 한다 — 화면을 나갔다 들어오게 만들면
/// 원인을 좁히는 동안 같은 동작을 계속 반복해야 한다.
class _ConnectionTile extends StatelessWidget {
  const _ConnectionTile({
    required this.isChecking,
    required this.errorMessage,
    required this.onRetry,
  });

  final bool isChecking;
  final String? errorMessage;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final isConnected = !isChecking && errorMessage == null;

    return ListTile(
      leading: const Icon(Icons.dns_outlined),
      title: const Text('Server'),
      subtitle: Text(apiBaseUrl),
      trailing: isChecking
          ? const SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : isConnected
          ? const Icon(Icons.check_circle, color: Colors.green)
          : TextButton(onPressed: onRetry, child: const Text('Retry')),
    );
  }
}
