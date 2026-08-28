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
///
/// ── 이 파일을 읽는 데 필요한 개념 ──────────────────────────────────
///
/// StatefulWidget / State — 왜 클래스가 두 개인가
///   이 화면은 "분석 중인가", "결과가 뭔가" 같은 **바뀌는 값**을 갖는다.
///   Flutter는 이런 화면을 만들 때 클래스를 둘로 나눈다.
///     CameraScreen        겉껍데기. 바뀌지 않는 부분.
///     _CameraScreenState  실제 내용물. 바뀌는 값과 화면 그리는 코드가 여기 있다.
///   이름 앞의 `_`는 "이 파일 밖에서는 못 쓴다"는 표시다(비공개).
///
/// setState — "화면 다시 그려"
///   값을 그냥 바꾸면 화면은 그대로다. setState로 감싸야 Flutter가
///   "값이 바뀌었으니 build()를 다시 부르자"고 판단한다.
///
/// async / await — "기다렸다 받기"
///   서버 응답은 즉시 오지 않는다(OCR 약 8초). await는 "올 때까지 기다려"라는
///   뜻이고, 기다리는 동안 앱은 멈추지 않고 로딩 표시를 계속 그린다.
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../api.dart';
import '../config.dart';
import 'candidates_screen.dart';
import 'detail_screen.dart';
import 'first_run_guide.dart';
import 'paper_background.dart';
import 'settings_button.dart';
import 'stitch_bar.dart';
import 'supported_foods_screen.dart';

class CameraScreen extends StatefulWidget {
  const CameraScreen({super.key});

  // StatefulWidget은 짝이 되는 State 클래스를 만들어 돌려줘야 한다.
  // 이 줄은 형식이라 외울 필요 없이 그대로 쓴다.
  @override
  State<CameraScreen> createState() => _CameraScreenState();
}

class _CameraScreenState extends State<CameraScreen> {
  // ── 바뀌는 값 세 가지 ────────────────────────────────────────────
  // 이 값들이 바뀌면(setState를 거쳐) 아래 build()가 다시 불려 화면이 갱신된다.

  /// 서버 응답을 기다리는 중인지. true인 동안 버튼을 잠그고 로딩을 표시한다.
  ///
  /// OCR은 실측 약 8초(첫 요청 10초)가 걸린다. 이 표시가 없으면 사용자가
  /// 앱이 멈춘 줄 알고 나가버린다(EC-07).
  bool _isLoading = false;

  /// 서버에 아예 닿지 못했을 때의 안내. 성공하면 다시 null로 비운다.
  /// 타입 뒤의 `?`는 "값이 없을 수도 있다(null 가능)"는 뜻이다.
  String? _errorMessage;

  /// 마지막 분석 결과. 아직 한 번도 분석하지 않았으면 null.
  AnalyzeResult? _result;

  @override
  void initState() {
    super.initState();

    // 첫 화면이 그려진 다음에만 하단 시트를 연다. initState 안에서 바로
    // showModalBottomSheet를 부르면 아직 Navigator가 준비되지 않은 시점이 있어
    // 예외가 날 수 있다. 이 화면은 앱의 진입점이므로 여기 한 곳에서만
    // 첫 실행 안내를 확인한다.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _showFirstRunGuide();
    });
  }

  /// 첫 실행일 때만 짧은 사용 안내를 연다.
  ///
  /// Settings의 How it works는 지원 범위·가격 출처 같은 상세 문서이고,
  /// 이 시트는 촬영을 시작하기 위한 네 단계 요약이다. 둘을 분리해 같은
  /// 문구가 두 곳에서 어긋나지 않게 한다(`flutter-mobile-app.md` EC-12).
  Future<void> _showFirstRunGuide() async {
    try {
      await showFirstRunGuideIfNeeded(context);
    } catch (error, stackTrace) {
      // 안내는 촬영·OCR과 무관한 보조 기능이다. 저장소 오류가 나더라도
      // 첫 화면을 막지 않고 다음 실행에 다시 보일 수 있게만 둔다.
      debugPrint('Unable to show first-run guide: $error\n$stackTrace');
    }
  }

  /// 사진을 고르고 서버에 보내는 전체 흐름.
  ///
  /// [source]로 카메라와 사진첩 중 어디서 가져올지 정한다. 두 경우의 처리가
  /// 완전히 같아서 함수를 하나로 두고 인자로만 구분한다.
  ///
  /// `Future<void>`는 "시간이 걸리는 작업이고, 끝나도 돌려줄 값은 없다"는 뜻이다.
  Future<void> _pickAndAnalyze(ImageSource source) async {
    final picked = await ImagePicker().pickImage(source: source);

    // 사용자가 촬영/선택을 취소한 경우다. 오류가 아니므로 조용히 돌아간다.
    if (picked == null) return;

    // 요청을 시작하면서 화면을 "로딩 중" 상태로 바꾼다.
    // 이전 결과와 오류는 지운다 — 새 사진을 넣었는데 옛 결과가 남아 있으면
    // 사용자가 그게 방금 찍은 것의 결과라고 오해한다.
    setState(() {
      _isLoading = true;
      _errorMessage = null;
      _result = null;
    });

    try {
      // 여기서 실제로 서버를 부른다. api.dart의 analyze() 함수다.
      final result = await analyze(File(picked.path));

      // await로 기다리는 사이에 사용자가 화면을 떠났을 수 있다. 그 상태에서
      // setState를 부르면 예외가 나므로 화면이 아직 살아있는지 먼저 확인한다.
      // mounted는 "이 화면이 아직 붙어 있나"를 알려주는 Flutter 기본 값이다.
      if (!mounted) return;
      setState(() => _result = result);

      // 후보를 찾았으면 곧바로 선택 화면으로 넘어간다.
      //
      // 이 화면에 목록을 그리지 않고 화면을 나누는 이유:
      // 카드에 사진·가격까지 들어가면 촬영 버튼이 위로 밀려 화면이 좁아진다.
      // 그리고 "찍는 일"과 "고르는 일"은 사용자에게도 별개의 단계다.
      //
      // Navigator.push — 새 화면을 위에 얹는다. 뒤로가기는 자동으로 생기고,
      // 뒤로 오면 이 화면이 그대로 남아 있어 다시 찍기가 편하다.
      if (result.isSuccess) {
        // 후보가 하나뿐이면 고를 것이 없으므로 선택 화면을 건너뛰고 바로 상세로
        // 간다. 웹앱(frontend/)도 같게 동작한다(`frontend/docs/web-app.md` EC-03).
        // 뒤로가기를 누르면 이 촬영 화면으로 돌아온다 — 중간에 아무것도 안 고른
        // 선택 화면이 끼어 있으면 한 번 더 눌러야 해서 오히려 번거롭다.
        // 새 메뉴판을 성공적으로 분석했으면 카트를 비운다 — 카트는 앱이 아니라
        // "지금 이 식당"에 묶인다. 안 그러면 A식당에서 담아둔 메뉴가 B식당
        // 메뉴판을 찍은 뒤에도 목록에 남는다(`cart.md` EC-09).
        //
        // 비우는 시점은 **분석 성공 하나뿐이다.** OCR 실패·미지원으로 되돌아온
        // 경우는 새 식당이 아니라 실패한 시도이므로 건드리지 않는다(EC-10) —
        // 흐리게 찍어 다시 찍는 흔한 흐름에서 담아둔 것을 잃지 않기 위해서다.
        // 그래서 이 호출이 isSuccess 안에 있다.
        try {
          await clearCart();
        } on ApiException {
          // 비우기에 실패해도 촬영 흐름을 막지 않는다. 이전 식당 메뉴가 남는 건
          // 불편하지만, 그것 때문에 안내를 아예 못 보게 하는 편이 더 나쁘다.
          // 서버에 닿지 못한 상황이면 다음 화면이 카트를 조회하면서 같은 오류를
          // 사용자에게 알린다(`cart.md` EC-06). 여기서 또 알릴 이유가 없다.
        }
        if (!mounted) return;

        final only = result.candidates.length == 1
            ? result.candidates.first
            : null;

        await Navigator.push(
          context,
          MaterialPageRoute(
            builder: (context) => only != null
                ? DetailScreen(foodId: only.foodId, nameEn: only.nameEn)
                : CandidatesScreen(
                    // 안내 가능한 후보와 이름·가격만 아는 줄을 메뉴판 순서로 합친 것.
                    entries: result.menuEntries,
                    // 후보가 사진 어디에서 나왔는지 보여주려면 원본 사진이 필요하다.
                    photo: File(picked.path),
                  ),
          ),
        );
      }
    } on ApiException catch (e) {
      // 서버에 닿지 못한 경우만 여기로 온다. api.dart가 그렇게 정해뒀다.
      // TTS 실패 같은 건 예외가 아니라 정상 응답 안의 상태값이다.
      if (!mounted) return;
      setState(() => _errorMessage = e.message);
    } finally {
      // finally는 성공하든 실패하든 반드시 실행된다.
      // 로딩 표시를 끄는 일은 어느 경우에도 빠뜨리면 안 되므로 여기 둔다.
      if (mounted) setState(() => _isLoading = false);
    }
  }

  /// 화면을 그리는 함수. 값이 바뀔 때마다 Flutter가 이걸 다시 부른다.
  @override
  Widget build(BuildContext context) {
    // Scaffold — 앱 화면의 기본 뼈대. 상단 바(appBar)와 본문(body) 자리를
    // 미리 잡아주고, 화면 크기·노치 같은 걸 알아서 처리해준다.
    return Scaffold(
      // 본문의 종이 배경을 상태바·상단바 아래까지 한 번에 그린다. AppBar에 배경을
      // 따로 칠하면 이음선이 생기므로, 투명한 상단바를 종이 위에 얹는다.
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: const Text('K-Menu'),
        backgroundColor: Colors.transparent,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        scrolledUnderElevation: 0,
        actionsPadding: EdgeInsets.zero,
        actions: const [SettingsButton()],
        // Penpot 01 보드의 상단 아래 스티치. 화면 기능이나 상태와는 무관한 공통 장식이다.
        bottom: const PreferredSize(
          preferredSize: Size.fromHeight(AppBarStitchBand.preferredHeight),
          child: AppBarStitchBand(),
        ),
      ),

      // Padding — 안쪽 여백. 글자가 화면 가장자리에 붙지 않게 한다.
      body: PaperBackground(
        child: Padding(
          // extendBodyBehindAppBar를 썼으므로, 본문만은 상태바·상단바 높이 아래에서
          // 시작시킨다. 배경은 뒤로 이어지되 내용이 제목과 겹치지 않는다.
          padding: EdgeInsets.fromLTRB(
            24,
            MediaQuery.paddingOf(context).top +
                kToolbarHeight +
                AppBarStitchBand.preferredHeight +
                24,
            24,
            24,
          ),
          // Column — 자식들을 세로로 차례차례 쌓는다. (가로로 쌓으려면 Row)
          child: Column(
            // 자식들의 가로 폭을 화면 끝까지 늘린다. 이게 없으면 버튼이
            // 글자 크기만큼만 작게 나온다.
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'Point your camera at a Korean menu',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
              ),
              // SizedBox — 높이만 가진 빈 상자. 위젯 사이 간격을 벌릴 때 쓴다.
              const SizedBox(height: 8),
              const Text(
                "We'll tell you what each dish is, how it tastes, "
                'and how spicy it gets.',
                style: TextStyle(fontSize: 14, color: Colors.black54),
              ),
              const SizedBox(height: 24),

              // FilledButton — 꽉 찬 색의 주요 버튼. 이 화면의 주 행동이다.
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

              // OutlinedButton — 테두리만 있는 보조 버튼. 대체 경로라 덜 강조한다.
              OutlinedButton.icon(
                onPressed: _isLoading
                    ? null
                    : () => _pickAndAnalyze(ImageSource.gallery),
                icon: const Icon(Icons.photo_library),
                label: const Text('Choose from library'),
              ),
              const SizedBox(height: 32),

              // Expanded — 남은 세로 공간을 전부 차지한다. 결과 목록이 길어져도
              // 이 영역 안에서만 스크롤되고 위쪽 버튼들은 자리를 지킨다.
              Expanded(child: _buildResultArea()),
            ],
          ),
        ),
      ),
    );
  }

  /// 화면 아래쪽에 상황에 맞는 내용을 보여준다.
  /// 로딩 > 오류 > 결과 순으로 확인한다 — 가장 급한 상태가 먼저다.
  ///
  /// build()에서 통째로 쓰지 않고 함수로 뺀 이유는, 경우가 다섯 가지나 돼서
  /// build() 안에 다 넣으면 화면 구조가 안 보이기 때문이다.
  Widget _buildResultArea() {
    if (_isLoading) {
      return const Center(
        child: Column(
          // 세로로 필요한 만큼만 차지한다. 이게 없으면 Column이 세로 전체를
          // 차지해서 가운데 정렬이 깨진다.
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(), // 빙글빙글 도는 표시
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
        body:
            '$_errorMessage\n\nMake sure the server is running '
            'and your phone is on the same Wi-Fi.\n$apiBaseUrl',
      );
    }

    // 지역 변수에 옮겨 담는다. _result는 null일 수 있는 타입이라 그대로 쓰면
    // Dart가 "null일 수도 있는데 왜 값처럼 쓰냐"고 막는다. 한 번 확인한
    // 지역 변수는 아래에서 안전하게 쓸 수 있다.
    final result = _result;
    if (result == null) {
      // 아직 아무것도 안 한 상태. 빈 자리로 둔다.
      return const SizedBox.shrink();
    }

    // 글자를 아예 못 읽은 경우 — 다시 찍는 방법을 알려준다(EC-03).
    if (result.isOcrEmpty) {
      return const _MessagePanel(
        icon: Icons.image_not_supported_outlined,
        title: "We couldn't read this photo",
        body:
            'Try brighter lighting, hold the menu straight, '
            'and move closer to the text.',
      );
    }

    // 메뉴판이 아닌 것을 찍은 경우 — 얼굴이나 풍경을 찍어도 OCR이 잡음 글자를
    // 만들어내서 위의 isOcrEmpty로는 안 잡힌다. 가격이 붙은 메뉴 줄이 하나도
    // 없다는 것이 "이건 메뉴판이 아니다"를 가르는 신호다(`src/pipeline.py`).
    // 아래 unsupported_food와 달리 **다시 찍으면 해결되는** 상황이라 재촬영을 권한다.
    if (result.isNotAMenu) {
      return const _MessagePanel(
        icon: Icons.no_photography_outlined,
        title: "We couldn't find a menu here",
        body:
            'Point the camera at a printed menu with prices, '
            'then take the photo again.',
      );
    }

    // 메뉴 줄은 읽혔지만 아는 음식이 없는 경우 — 위와 원인이 달라 문구도 다르다(EC-04).
    // 다시 찍어도 소용없는 상황이므로 재촬영을 권하지 않는다.
    if (result.isUnsupportedFood) {
      // OCR 원문은 보여주지 않는다. 메뉴판이 아닌 것을 찍거나 사진이 흐리면
      // 알아볼 수 없는 글자 덩어리가 화면을 채우는데, 사용자가 그걸로 할 수 있는
      // 일이 없고 파일 경로 같은 게 섞여 나오기도 한다(실기기 확인 중 확인됨).
      // 대신 지원 목록으로 보내준다 — "그럼 뭐가 되는데?"에 답해야 다음 행동이 나온다.
      return _MessagePanel(
        icon: Icons.search_off,
        title: 'Not in our guide yet',
        body:
            'We read this photo, but none of the dishes on it are among '
            'the 50 Korean dishes this guide covers.',
        actionLabel: 'See supported dishes',
        onAction: () => Navigator.push(
          context,
          MaterialPageRoute(builder: (context) => const SupportedFoodsScreen()),
        ),
      );
    }

    // 성공한 경우. 분석 직후에는 곧바로 후보 선택 화면으로 넘어가므로
    // 이 부분은 **거기서 뒤로 돌아왔을 때** 보인다.
    //
    // 빈 화면으로 두면 "방금 그 결과는 어디 갔지?"가 되므로, 결과가 남아
    // 있다는 것과 다시 열 수 있다는 것을 알려준다.
    return _LastPhotoResult(
      // 새 사진을 분석해 다른 결과 객체가 생겼을 때만 강조 효과를 처음부터
      // 재생한다. 화면이 단순히 다시 그려지는 경우에는 반복하지 않는다.
      key: ObjectKey(result),
      result: result,
    );
  }
}

/// 마지막 성공 결과를 조용히 알려주는 1회성 완료 효과.
///
/// 계속 반복하면 "읽지 않은 알림"처럼 보이고 식사 중인 사용자에게 방해가 된다.
/// 그래서 외곽 원은 퍼지며 사라지고, 아이콘·문구·링크는 한 번만 부드럽게
/// 나타난 뒤 정지한다(`mobile-last-photo-result-motion.md` AC-01).
class _LastPhotoResult extends StatelessWidget {
  const _LastPhotoResult({super.key, required this.result});

  final AnalyzeResult result;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Center(
      child: TweenAnimationBuilder<double>(
        tween: Tween(begin: 0, end: 1),
        // 완료 상태를 알아채기에는 1.3초가 짧아, 한 번의 동작은 유지하면서
        // 2.2초 동안 천천히 보여 준다. easeInOut은 끝부분이 급하게 사라지는
        // 느낌을 막아 준다.
        duration: const Duration(milliseconds: 2200),
        curve: Curves.easeInOutCubic,
        builder: (context, progress, child) {
          // progress는 TweenAnimationBuilder가 항상 0~1 범위로 보장한다.
          // 원형 하이라이트는 처음에만 보였다가 자연스럽게 사라진다.
          final haloOpacity = (1 - progress) * 0.18;
          final iconScale = 0.88 + (0.12 * progress);
          final contentOpacity = Curves.easeOut.transform(progress);
          final contentOffset = 10 * (1 - contentOpacity);

          return Opacity(
            opacity: contentOpacity,
            child: Transform.translate(
              offset: Offset(0, contentOffset),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    height: 68,
                    width: 68,
                    child: Stack(
                      alignment: Alignment.center,
                      children: [
                        Transform.scale(
                          scale: 0.8 + (0.6 * progress),
                          child: DecoratedBox(
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: colorScheme.primary.withValues(
                                alpha: haloOpacity,
                              ),
                            ),
                            child: const SizedBox.expand(),
                          ),
                        ),
                        Transform.scale(
                          scale: iconScale,
                          child: DecoratedBox(
                            decoration: BoxDecoration(
                              color: colorScheme.primaryContainer,
                              shape: BoxShape.circle,
                            ),
                            child: Icon(
                              Icons.check_circle_outline,
                              size: 42,
                              color: colorScheme.primary,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    result.candidates.length == 1
                        ? 'Found 1 dish on your last photo'
                        : 'Found ${result.candidates.length} dishes on your last photo',
                    style: const TextStyle(color: Colors.black54),
                  ),
                  const SizedBox(height: 8),
                  TextButton.icon(
                    onPressed: () => Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (context) =>
                            CandidatesScreen(entries: result.menuEntries),
                      ),
                    ),
                    icon: const Icon(Icons.list),
                    label: const Text('See the dishes again'),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

/// 안내 문구를 보여주는 공통 틀. 오류·재촬영 안내가 같은 모양을 쓴다.
///
/// 같은 생김새를 세 군데에서 쓰기 때문에 위젯으로 빼뒀다. 문구만 바뀌고
/// 구조는 같으므로, 나중에 디자인을 고칠 때도 여기 한 곳만 고치면 된다.
/// 이 파일 안에서만 쓰므로 이름 앞에 `_`를 붙여 비공개로 둔다.
class _MessagePanel extends StatelessWidget {
  const _MessagePanel({
    required this.icon,
    required this.title,
    required this.body,
    this.actionLabel,
    this.onAction,
  });

  // final — 한 번 정해지면 안 바뀌는 값. 위젯이 받는 재료들이다.
  final IconData icon;
  final String title;
  final String body;

  /// 안내로 끝나지 않고 다음 행동이 있는 경우에만 준다(둘 다 있어야 그려진다).
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    // SingleChildScrollView — 작은 화면에서 안내가 잘리지 않도록 스크롤되게 한다.
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
          if (actionLabel != null && onAction != null) ...[
            const SizedBox(height: 16),
            OutlinedButton(onPressed: onAction, child: Text(actionLabel!)),
          ],
        ],
      ),
    );
  }
}
