/// 앱이 호출할 서버 주소.
///
/// 주소 문자열은 이 파일에만 둔다 — 화면이나 api.dart가 각자 주소를 갖고 있으면
/// 환경을 옮길 때마다 여러 파일을 찾아 고쳐야 하고, 하나를 빠뜨리면 일부 요청만
/// 옛 서버로 가는 형태로 조용히 깨진다.
///
/// 환경별 값:
///   시뮬레이터  http://localhost:8000
///   실제 기기    http://<맥 로컬 IP>:8000         폰이 맥과 같은 Wi-Fi일 때
///   시연        https://<...>.trycloudflare.com  cloudflared 터널
///   배포        https://hju5022-k-menu.hf.space  ← 커밋 기본값
///
/// **시뮬레이터는 맥 안에서 돌기 때문에 localhost로 서버에 닿는다.** 맥의 IP가
/// 바뀌어도 영향을 받지 않아 로컬 서버를 띄운 개발 중에는 이 값이 가장 안정적이다.
///
/// **로컬 서버로 되돌릴 때**는 맥의 LAN IP로 바꿔야 한다. 폰에게
/// localhost는 폰 자신이라 서버를 찾지 못한다. 주소는 아래로 확인한다.
///
///     ipconfig getifaddr en0
///
/// 이 값은 Wi-Fi를 옮기거나 공유기가 주소를 다시 할당하면 바뀐다. 앱이 갑자기
/// "Can't reach the server"를 띄우면 여기부터 확인한다. Wi-Fi가 끊겨 있으면
/// 위 명령이 아무것도 출력하지 않는다.
///
/// 서버는 반드시 `--host 0.0.0.0`으로 띄워야 한다. 기본값(127.0.0.1)이면 맥
/// 자신만 접속할 수 있어 실제 폰에서는 연결되지 않는다.
/// `--dart-define=API_BASE_URL=...`를 주면 그 주소를 우선 쓴다.
///
/// 기본값은 배포 Space라서 평소 빌드·배포 동작은 바뀌지 않는다. USB 디버깅 중에는
/// `http://127.0.0.1:8000`을 넣고 `adb reverse tcp:8000 tcp:8000`을 설정하면
/// 실제 Android 기기도 맥의 로컬 서버(사전 생성 TTS 캐시 포함)를 사용할 수 있다.
const String apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'https://hju5022-k-menu.hf.space',
);
