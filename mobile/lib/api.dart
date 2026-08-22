/// 서버(`K_Menu_Talk.py`) 호출을 모아두는 곳.
///
/// 화면(screens/)은 http 패키지를 직접 쓰지 않고 이 파일의 함수만 부른다 —
/// 엔드포인트 경로나 응답 모양이 바뀌었을 때 고칠 곳을 한 군데로 묶기 위함이다.
///
/// 이 앱이 쓰는 엔드포인트는 세 개다(`docs/specs/api-layer.md`):
///
///   POST /api/analyze          이미지(multipart, 필드명 "image") ──▶ 음식 후보 목록
///   GET  /api/foods/{food_id}  음식 id ──▶ 상세 6개 카테고리 + 내레이션 음성 경로
///   GET  /api/foods            ──▶ 안내 가능한 음식 전체 목록 (설정 화면용)
///   GET/POST/DELETE /api/cart… 장바구니 (X-Cart-Id 헤더 필수)
///
/// ── 이 파일을 읽는 데 필요한 개념 ──────────────────────────────────
///
/// class(클래스) — 데이터의 모양을 정해두는 틀
///   서버가 보내주는 JSON은 그냥 글자 덩어리다. 그대로 쓰면 화면 코드에서
///   `json['candidates'][0]['name_en']` 처럼 매번 철자를 정확히 적어야 하고,
///   오타가 나도 실행하기 전까지 모른다. 클래스로 모양을 정해두면
///   `candidate.nameEn` 으로 쓸 수 있고, 오타는 작성하는 순간 빨간 줄로 잡힌다.
///
/// factory ...fromJson — JSON을 클래스로 옮겨 담는 규칙
///   "서버가 준 이 JSON에서 이 값을 꺼내 이 자리에 넣어라"를 적어둔 곳이다.
///   서버 응답 모양이 바뀌면 이 부분만 고치면 화면 코드는 안 건드려도 된다.
///
/// Future / async / await — 시간이 걸리는 작업
///   서버 응답은 즉시 오지 않는다(OCR 약 8초). Future는 "지금은 없지만
///   나중에 올 값"이라는 뜻이고, await는 "올 때까지 기다려"라는 뜻이다.
///
/// get(게터) — 계산해서 알려주는 값
///   저장된 값이 아니라 다른 값들로 그때그때 판단해 돌려주는 것.
///   예: hasAudio는 따로 저장하지 않고 tts_status와 URL을 보고 계산한다.
///   같은 판단을 화면마다 반복하지 않도록 여기 한 번만 적어둔다.
library;

import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:http/http.dart' as http;

import 'config.dart';

/// 서버를 부르지 못했거나 서버가 오류를 돌려줬을 때 던진다.
///
/// 화면은 이 예외를 잡아 재시도 UI를 띄운다(`flutter-mobile-app.md` EC-02).
/// TTS 실패는 여기 해당하지 않는다 — 그건 정상 응답 안의 상태값이라 예외가 아니다.
class ApiException implements Exception {
  ApiException(this.message);

  final String message;

  @override
  String toString() => message;
}

/// 서버가 응답 본문을 UTF-8로 보내지만 Content-Type에 charset을 명시하지 않는다.
/// 그 경우 http 패키지의 `response.body`는 latin1로 해석해서 한글이 깨진다
/// (name_kr이 "김치찌개" 대신 "ê¹ì¹ì°ê°"처럼 나온다).
/// 그래서 항상 바이트를 직접 UTF-8로 디코드한다.
Map<String, dynamic> _decodeJson(http.Response response) {
  return jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
}

/// OCR이 찾아낸 음식 후보 하나.
class Candidate {
  Candidate({
    required this.foodId,
    required this.nameKr,
    required this.nameEn,
    required this.score,
    required this.priceKrw,
    required this.priceDisplay,
    required this.thumbnailUrl,
    required this.thumbnailAttribution,
  });

  factory Candidate.fromJson(Map<String, dynamic> json) {
    return Candidate(
      foodId: json['food_id'] as int,
      nameKr: json['name_kr'] as String,
      nameEn: json['name_en'] as String,
      score: json['score'] as int,
      // 아래 셋은 서버가 못 채울 수 있어 null이 올 수 있다.
      // `as String?`의 `?`가 "없을 수도 있다"는 표시다.
      priceKrw: json['price_krw'] as int?,
      priceDisplay: json['price_krw_display'] as String?,
      thumbnailUrl: json['thumbnail_url'] as String?,
      thumbnailAttribution: json['thumbnail_attribution'] as String?,
    );
  }

  final int foodId;
  final String nameKr;
  final String nameEn;

  /// OCR 문자열과의 유사도(0~100). 서버가 이 값 내림차순으로 정렬해서 주므로
  /// 앱에서 다시 정렬하지 않는다.
  final int score;

  /// 메뉴판 사진에서 이 음식 근처에 적혀 있던 가격을 서버가 읽어 "₩8,000"
  /// 형태로 만들어준 값. DB 값이 아니라 **그 사진에 실제로 적힌 가격**이다.
  ///
  /// 이름이 메뉴판 다른 문구에 걸려서 잡혔거나 근처에 숫자가 없으면 null이다.
  /// 그때 화면은 가격 자리를 비워둔다 — 없는 가격을 지어내면 안 된다.
  final String? priceDisplay;

  /// 위 값의 계산용 원본(원 단위 정수). 장바구니에 담을 때 서버로 실어 보낸다 —
  /// 사진마다 값이 달라서 서버가 food_id로 되찾아올 수 있는 값이 아니다.
  final int? priceKrw;

  /// 음식 대표 사진 주소. 서버가 완전한 URL로 준다(apiBaseUrl을 붙이지 않는다).
  final String? thumbnailUrl;

  /// 사진 출처 표기. 프로젝트가 외부 사진을 쓰면서 출처를 남기기로 한 항목이라,
  /// 사진을 보여주는 자리에서는 이 값도 함께 보여준다.
  final String? thumbnailAttribution;

  /// 가격을 아는 후보인지. 화면에서 가격 자리를 그릴지 판단할 때 쓴다.
  bool get hasPrice => priceDisplay != null;

  /// 사진을 보여줄 수 있는지.
  bool get hasThumbnail => thumbnailUrl != null;
}

/// `POST /api/analyze`의 응답.
class AnalyzeResult {
  AnalyzeResult({
    required this.status,
    required this.ocrText,
    required this.candidates,
  });

  factory AnalyzeResult.fromJson(Map<String, dynamic> json) {
    final rawCandidates = json['candidates'] as List<dynamic>;
    return AnalyzeResult(
      status: json['status'] as String,
      ocrText: json['ocr_text'] as String,
      candidates: rawCandidates
          .map((item) => Candidate.fromJson(item as Map<String, dynamic>))
          .toList(),
    );
  }

  /// 서버가 돌려주는 값은 세 가지다(`src/pipeline.py`의 analyze_image).
  /// 성공 값이 "ok"가 아니라 "candidates_found"임에 주의한다.
  ///
  ///   candidates_found  후보를 찾음 — candidates에 1개 이상
  ///   unsupported_food  글자는 읽었으나 등록된 50개 음식과 매칭 실패
  ///   ocr_empty         글자를 전혀 읽지 못함
  final String status;

  /// OCR이 읽어낸 원문. 실패 안내를 만들 때 참고용으로 쓴다.
  final String ocrText;

  final List<Candidate> candidates;

  bool get isSuccess => status == 'candidates_found' && candidates.isNotEmpty;

  /// 글자는 읽혔지만 등록된 음식이 없는 경우. 안내 문구가 ocrEmpty와 달라야 해서
  /// 따로 구분한다(EC-03 vs EC-04).
  bool get isUnsupportedFood => status == 'unsupported_food';

  bool get isOcrEmpty => status == 'ocr_empty';
}

/// `GET /api/foods`의 한 줄 — 설정 화면의 "지원 음식" 목록에 쓴다.
///
/// 상세 화면이 쓰는 [FoodDetail]과 달리 이름만 있다. 이 화면의 질문은 "무엇을
/// 지원하나"이지 "무엇을 먹을까"가 아니라서, 서버가 사진·맵기·가격을 싣지 않는다
/// (`docs/specs/supported-foods.md`).
class SupportedFood {
  SupportedFood({
    required this.foodId,
    required this.nameKr,
    required this.nameEn,
  });

  factory SupportedFood.fromJson(Map<String, dynamic> json) {
    return SupportedFood(
      foodId: json['food_id'] as int,
      nameKr: json['name_kr'] as String,
      nameEn: json['name_en'] as String,
    );
  }

  final int foodId;
  final String nameKr;
  final String nameEn;
}

/// `GET /api/foods/{food_id}`의 응답.
class FoodDetail {
  FoodDetail({
    required this.foodId,
    required this.nameKr,
    required this.nameEn,
    required this.spiceLevel,
    required this.details,
    required this.narrationText,
    required this.style,
    required this.ttsStatus,
    required this.audioUrl,
  });

  factory FoodDetail.fromJson(Map<String, dynamic> json) {
    final rawDetails = json['details'] as Map<String, dynamic>;
    // 서버는 "/audio/xxx.wav" 같은 상대 경로를 준다. 재생하려면 서버 주소를
    // 앞에 붙여 완전한 URL로 만들어야 하는데, 그 조립을 화면마다 반복하지 않도록
    // 여기서 한 번만 한다.
    final relativePath = json['narration_audio_path'] as String?;
    return FoodDetail(
      foodId: json['food_id'] as int,
      nameKr: json['name_kr'] as String,
      nameEn: json['name_en'] as String,
      spiceLevel: json['spice_level'] as int,
      details: rawDetails.map((key, value) => MapEntry(key, value as String)),
      narrationText: json['narration_text'] as String,
      style: json['style'] as String,
      ttsStatus: json['tts_status'] as String,
      audioUrl: relativePath == null ? null : '$apiBaseUrl$relativePath',
    );
  }

  final int foodId;
  final String nameKr;
  final String nameEn;

  /// 맵기 1~5. 상세 카드의 SPICY 텍스트가 설명이라면, 이 값은 한눈에 보는 눈금이다.
  final int spiceLevel;

  /// 카테고리 6개. 키는 DESCRIPTION / HOW_TO_EAT / INGREDIENT / ALLERGY /
  /// PRONUNCIATION / SPICY 이며, 화면에 보여줄 순서와 제목은 화면 쪽에서 정한다
  /// (`frontend/docs/content-style.md`의 문구 기준을 따른다).
  final Map<String, String> details;

  final String narrationText;

  /// 맵기 4단계 이상이면 CAUTION, 아니면 GUIDE. 서버가 정해서 준다.
  final String style;

  final String ttsStatus;

  /// 재생 가능한 완전한 URL. TTS가 실패했으면 null이다.
  final String? audioUrl;

  /// 음성을 재생할 수 있는 상태인지.
  ///
  /// false여도 화면 전체를 실패로 처리하면 안 된다 — 상세 텍스트는 그대로
  /// 보여주고 음성 영역만 비활성으로 표시한다(EC-05).
  bool get hasAudio => ttsStatus == 'ok' && audioUrl != null;
}

/// 메뉴판 사진을 보내 음식 후보를 받는다.
///
/// 첫 요청은 서버가 OCR 모델을 메모리에 올리느라 오래 걸린다(실측 10초, 이후 약 8초).
/// 호출하는 화면은 그동안 로딩 표시를 유지해야 한다(EC-07).
Future<AnalyzeResult> analyze(File imageFile) async {
  final request = http.MultipartRequest(
    'POST',
    Uri.parse('$apiBaseUrl/api/analyze'),
  );
  // 필드명 "image"는 서버가 정한 이름이라 바꾸면 안 된다
  // (K_Menu_Talk.py의 `image: UploadFile = File(...)`).
  request.files.add(await http.MultipartFile.fromPath('image', imageFile.path));

  final http.Response response;
  try {
    response = await http.Response.fromStream(await request.send());
  } on SocketException {
    throw ApiException('서버에 연결할 수 없습니다.\n주소: $apiBaseUrl');
  }

  if (response.statusCode != 200) {
    throw ApiException('사진 분석에 실패했습니다. (HTTP ${response.statusCode})');
  }
  return AnalyzeResult.fromJson(_decodeJson(response));
}

/// 음식 하나의 상세 텍스트와 내레이션 음성을 받는다.
///
/// 사전 생성 캐시가 있으면 사실상 즉시 돌아오지만(실측 0.018초), 캐시에 없는
/// 조합이면 서버가 그 자리에서 음성을 만드느라 30초 이상 걸릴 수 있다.
Future<FoodDetail> fetchFood(int foodId) async {
  final http.Response response;
  try {
    response = await http.get(Uri.parse('$apiBaseUrl/api/foods/$foodId'));
  } on SocketException {
    throw ApiException('서버에 연결할 수 없습니다.\n주소: $apiBaseUrl');
  }

  if (response.statusCode == 404) {
    throw ApiException('등록되지 않은 음식입니다. (food_id: $foodId)');
  }
  if (response.statusCode != 200) {
    throw ApiException('음식 정보를 불러오지 못했습니다. (HTTP ${response.statusCode})');
  }
  return FoodDetail.fromJson(_decodeJson(response));
}

/// 안내할 수 있는 음식 전체를 받는다.
///
/// 서버가 영문명 오름차순으로 정렬해서 주므로 앱에서 다시 정렬하지 않는다.
/// 빈 배열은 오류가 아니라 "아직 등록된 음식이 없음"이다 — 호출하는 화면이 그대로
/// 알린다(`supported-foods.md` EC-03).
Future<List<SupportedFood>> fetchSupportedFoods() async {
  final http.Response response;
  try {
    response = await http.get(Uri.parse('$apiBaseUrl/api/foods'));
  } on SocketException {
    throw ApiException('서버에 연결할 수 없습니다.\n주소: $apiBaseUrl');
  }

  if (response.statusCode != 200) {
    throw ApiException('지원 음식 목록을 불러오지 못했습니다. (HTTP ${response.statusCode})');
  }
  // 이 응답만 최상위가 객체가 아니라 배열이라 _decodeJson()을 쓸 수 없다.
  final rawFoods = jsonDecode(utf8.decode(response.bodyBytes)) as List<dynamic>;
  return rawFoods
      .map((item) => SupportedFood.fromJson(item as Map<String, dynamic>))
      .toList();
}

/// 장바구니에 담긴 한 줄.
class CartLine {
  CartLine({
    required this.foodId,
    required this.nameKr,
    required this.nameEn,
    required this.quantity,
    required this.priceDisplay,
    required this.lineTotalDisplay,
  });

  factory CartLine.fromJson(Map<String, dynamic> json) {
    return CartLine(
      foodId: json['food_id'] as int,
      nameKr: json['name_kr'] as String,
      nameEn: json['name_en'] as String,
      quantity: json['quantity'] as int,
      priceDisplay: json['price_krw_display'] as String?,
      lineTotalDisplay: json['line_total_display'] as String?,
    );
  }

  final int foodId;
  final String nameKr;
  final String nameEn;
  final int quantity;

  /// 한 개 가격. 메뉴판에서 못 읽었으면 null이다.
  final String? priceDisplay;

  /// 이 줄의 소계(한 개 가격 × 수량). 마찬가지로 못 읽었으면 null이다.
  final String? lineTotalDisplay;
}

/// 카트 전체 상태.
///
/// 담기·빼기·비우기 어느 요청이든 이 모양이 통째로 돌아온다 — 앱이 부분 갱신을
/// 짜맞추지 않게 서버가 그렇게 정했다(`docs/specs/cart.md`).
class CartState {
  CartState({
    required this.items,
    required this.itemCount,
    required this.totalDisplay,
    required this.hasUnpricedItems,
  });

  factory CartState.fromJson(Map<String, dynamic> json) {
    final rawItems = json['items'] as List<dynamic>;
    return CartState(
      items: rawItems
          .map((item) => CartLine.fromJson(item as Map<String, dynamic>))
          .toList(),
      itemCount: json['item_count'] as int,
      totalDisplay: json['total_krw_display'] as String,
      hasUnpricedItems: json['has_unpriced_items'] as bool,
    );
  }

  final List<CartLine> items;

  /// 줄 수가 아니라 수량의 합이다.
  final int itemCount;

  final String totalDisplay;

  /// 가격을 못 읽은 메뉴가 담겨 있는지. true면 총계가 실제보다 싸 보이므로
  /// 화면이 그 사실을 함께 알려야 한다(EC-03).
  final bool hasUnpricedItems;

  bool get isEmpty => items.isEmpty;
}

/// 이 앱 실행 동안 쓰는 카트 ID.
///
/// 로그인이 없는 서비스라 계정 대신 쓰는 최소 식별자다. 웹은 localStorage에
/// 보관하지만 여기서는 앱을 켤 때 한 번 만들어 메모리에만 둔다 — 서버도 카트를
/// 메모리에만 들고 있어 재시작하면 사라지고, 영속 저장은 Spec의 Out of Scope다.
/// 앱을 껐다 켜면 카트가 비는데, 서버 재시작과 같은 수준의 동작이다.
final String cartId = _newCartId();

String _newCartId() {
  final random = Random();
  return List.generate(
    4,
    (_) => random.nextInt(1 << 32).toRadixString(16).padLeft(8, '0'),
  ).join();
}

/// 카트 요청 세 가지가 응답을 다루는 방식이 같아서 한 군데로 묶었다.
Future<CartState> _cartRequest(Future<http.Response> Function() send) async {
  final http.Response response;
  try {
    response = await send();
  } on SocketException {
    throw ApiException('서버에 연결할 수 없습니다.\n주소: $apiBaseUrl');
  }

  if (response.statusCode != 200) {
    throw ApiException('장바구니를 갱신하지 못했습니다. (HTTP ${response.statusCode})');
  }
  return CartState.fromJson(_decodeJson(response));
}

/// 지금 카트 상태를 받는다. 처음 보는 카트 ID면 서버가 빈 카트를 준다(EC-05).
Future<CartState> fetchCart() {
  return _cartRequest(
    () => http.get(
      Uri.parse('$apiBaseUrl/api/cart'),
      headers: {'X-Cart-Id': cartId},
    ),
  );
}

/// 음식 하나의 수량을 [quantityDelta]만큼 더하거나 뺀다(+1 / -1).
///
/// 가격을 같이 보내는 이유: 이 값은 DB가 아니라 **그 메뉴판 사진에서 읽은 값**이라
/// 서버가 food_id만으로 되찾아올 수 없다.
Future<CartState> changeCartItem(
  Candidate candidate, {
  required int quantityDelta,
}) {
  return _cartRequest(
    () => http.post(
      Uri.parse('$apiBaseUrl/api/cart/items'),
      headers: {'X-Cart-Id': cartId, 'Content-Type': 'application/json'},
      body: jsonEncode({
        'food_id': candidate.foodId,
        'name_kr': candidate.nameKr,
        'name_en': candidate.nameEn,
        'price_krw': candidate.priceKrw,
        'quantity_delta': quantityDelta,
      }),
    ),
  );
}

/// 카트를 비운다.
Future<CartState> clearCart() {
  return _cartRequest(
    () => http.delete(
      Uri.parse('$apiBaseUrl/api/cart'),
      headers: {'X-Cart-Id': cartId},
    ),
  );
}
