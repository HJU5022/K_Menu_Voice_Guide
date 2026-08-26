// 촬영 화면이 정상적으로 그려지는지 확인하는 기본 테스트.
//
// 서버를 부르지 않는다 — 화면을 만드는 것만으로는 API를 호출하지 않고,
// 버튼을 눌러야 비로소 호출한다. 그래서 서버가 꺼져 있어도 이 테스트는 돈다.

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:mobile/main.dart';

void main() {
  testWidgets('촬영 화면이 두 가지 사진 입력 경로를 보여준다', (WidgetTester tester) async {
    // 이 테스트는 촬영 화면 자체를 확인한다. 첫 실행 안내는 별도 테스트에서
    // 다루므로, 이미 본 상태로 만들어 화면을 가리지 않게 한다.
    SharedPreferences.setMockInitialValues({'k_menu.first_run_guide_seen': true});
    await tester.pumpWidget(const KMenuApp());

    expect(find.text('Point your camera at a Korean menu'), findsOneWidget);

    // 카메라와 사진첩 둘 다 있어야 한다. 사진첩은 카메라 권한을 거부당했을 때의
    // 대체 경로이자(EC-01), 카메라가 없는 iOS 시뮬레이터에서 쓰는 유일한 경로다.
    expect(find.text('Take a photo'), findsOneWidget);
    expect(find.text('Choose from library'), findsOneWidget);
  });

  testWidgets('첫 실행 안내는 닫은 뒤 자동으로 다시 나타나지 않는다',
      (WidgetTester tester) async {
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(const KMenuApp());
    await tester.pumpAndSettle();

    expect(find.text('A quick guide'), findsOneWidget);
    expect(find.text('Take a photo'), findsWidgets);

    await tester.tap(find.text('Skip'));
    await tester.pumpAndSettle();
    expect(find.text('A quick guide'), findsNothing);

    // 앱을 다시 만든 뒤에도 저장된 완료 상태 때문에 안내가 자동으로 열리지 않는다.
    await tester.pumpWidget(const KMenuApp());
    await tester.pumpAndSettle();
    expect(find.text('A quick guide'), findsNothing);
  });
}
