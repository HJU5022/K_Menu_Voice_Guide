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

/// `MultipartFile.fromPath`는 타입을 지정하지 않으면
/// `application/octet-stream`으로 보낸다. 분석 서버는 `image/*`만 받으므로
/// 사진 확장자에 맞는 MIME 타입을 함께 보낸다.
http.MediaType _imageMediaType(File imageFile) {
  final extension = imageFile.path.split('.').last.toLowerCase();
  return switch (extension) {
    'png' => http.MediaType('image', 'png'),
    'gif' => http.MediaType('image', 'gif'),
    'webp' => http.MediaType('image', 'webp'),
    'heic' => http.MediaType('image', 'heic'),
    'heif' => http.MediaType('image', 'heif'),
    _ => http.MediaType('image', 'jpeg'),
  };
}

/// 후보가 사진의 어디에서 나왔는지 — 사진 위에 상자를 그리기 위한 값.
///
/// 좌표는 **업로드한 원본 사진 기준 0~1 비율**이다(px가 아니다). 화면이 사진을 어떤
/// 크기로 그리든 그대로 얹을 수 있게 서버가 비율로 바꿔서 준다.
class CandidateSource {
  CandidateSource({
    required this.text,
    required this.left,
    required this.top,
    required this.width,
    required this.height,
  });

  factory CandidateSource.fromJson(Map<String, dynamic> json) {
    return CandidateSource(
      text: json['text'] as String,
      left: (json['left'] as num).toDouble(),
      top: (json['top'] as num).toDouble(),
      width: (json['width'] as num).toDouble(),
      height: (json['height'] as num).toDouble(),
    );
  }

  /// OCR이 그 자리에서 **실제로 읽은 글자**. 음식명과 다를 수 있고, 그 차이 자체가
  /// "왜 이 후보가 나왔는지"를 설명한다.
  final String text;

  final double left;
  final double top;
  final double width;
  final double height;
}

/// 메뉴판 이름 앞에 붙어 있던 수식어 하나 (예: "꽁치김치찌개"의 `꽁치`).
///
/// 등록 음식은 50개뿐이라 "김치찌개"까지밖에 못 알아보는데, 메뉴판에는 그 앞에
/// 재료나 맵기가 붙어 있는 일이 많다. 그 한 마디가 있어야 여행자가 같은 이름의 두
/// 메뉴를 구분할 수 있다 — 실제 메뉴판에서 "쌈싸먹는 김치찌개"와 "쌈싸먹는
/// 꽁치김치찌개"가 나란히 있었고 **가격도 둘 다 7,000원**이었다.
///
/// 줄 단위 매칭 전에는 이 값이 97% 틀린 메뉴에 붙어서 화면에 그릴 수 없었다.
class Modifier {
  Modifier({required this.keyword, required this.keywordEn});

  factory Modifier.fromJson(Map<String, dynamic> json) {
    return Modifier(
      keyword: json['keyword'] as String,
      keywordEn: json['keyword_en'] as String?,
    );
  }

  /// 메뉴판에 인쇄된 한국어 그대로(`꽁치`).
  final String keyword;

  /// 영어 표기(`Saury`). 화면에 보여줄 사람은 한국어를 못 읽으므로 이쪽을 쓴다.
  final String? keywordEn;

  String get label => keywordEn ?? keyword;
}

/// 장바구니에 담을 수 있는 것 — 안내 가능한 후보이든, 이름·가격만 아는 줄이든.
///
/// 담기 요청이 서버에 보내는 값이 같아서 하나로 묶었다. 등록되지 않은 메뉴는
/// [foodId]가 null이고, 그때는 [menuText]가 유일한 신원이 된다.
abstract interface class CartAddable {
  int? get foodId;
  String get cartNameKr;
  String get cartNameEn;
  int? get priceKrw;
  String? get menuText;

  /// 이름 자리에 보여줄 글자 — [menuText]에서 가격만 뗀 것(서버의 `name_text`).
  ///
  /// 카드는 가격을 이미 따로 큰 글씨로 보여준다. 거기에 줄 글자를 그대로 쓰면
  /// "김치전/부추전 ₩7,000" 밑에 "₩7,000"이 또 붙어 같은 값이 두 번 보인다.
  /// 줄을 구분하는 신원은 [menuText]가 계속 맡는다 — 이건 표시 전용이다.
  String? get nameText;

  /// 사진에서 이 줄이 나온 자리. 사진 위 상자를 그리는 데 쓴다.
  CandidateSource? get source;

  /// 메뉴판에서 위에서부터 센 줄 번호. 목록을 메뉴판 순서로 늘어놓을 때 쓴다.
  ///
  /// 줄 위치를 못 잡은 후보는 번호가 없어서 [lineNoLast]가 대신 들어간다 —
  /// 그런 줄은 목록 맨 뒤로 간다.
  int get lineNo;

  /// 장바구니에서 이 줄을 가리키는 신원. 서버가 묶는 기준과 같아야 한다.
  String get lineKey;
}

/// OCR이 찾아낸 음식 후보 하나.
class Candidate implements CartAddable {
  Candidate({
    required this.foodId,
    required this.nameKr,
    required this.nameEn,
    required this.score,
    required this.priceKrw,
    required this.priceDisplay,
    required this.thumbnailUrl,
    required this.thumbnailAttribution,
    required this.menuText,
    required this.nameText,
    required this.source,
    required this.rawLineNo,
    required this.spiceLevel,
    required this.spiceModifiers,
    required this.ingredientModifiers,
  });

  static List<Modifier> _modifiers(Map<String, dynamic> json, String key) {
    final raw = (json['modifiers'] as Map<String, dynamic>?)?[key] as List<dynamic>?;
    return (raw ?? const [])
        .map((item) => Modifier.fromJson(item as Map<String, dynamic>))
        .toList();
  }

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
      menuText: json['menu_text'] as String?,
      nameText: json['name_text'] as String?,
      // 이름이 두 상자에 걸쳐 잘리면 위치를 특정할 수 없어 서버가 null을 준다.
      source: json['source'] == null
          ? null
          : CandidateSource.fromJson(json['source'] as Map<String, dynamic>),
      rawLineNo: json['line_no'] as int?,
      // 등록되지 않은 맵기는 서버가 null로 준다(`K_Menu_Talk.py`의 Candidate).
      spiceLevel: json['spice_level'] as int?,
      spiceModifiers: _modifiers(json, 'spice'),
      ingredientModifiers: _modifiers(json, 'ingredient'),
    );
  }

  @override
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
  @override
  final int? priceKrw;

  /// 음식 대표 사진 주소. 서버가 완전한 URL로 준다(apiBaseUrl을 붙이지 않는다).
  final String? thumbnailUrl;

  /// 사진 출처 표기. 프로젝트가 외부 사진을 쓰면서 출처를 남기기로 한 항목이라,
  /// 사진을 보여주는 자리에서는 이 값도 함께 보여준다.
  final String? thumbnailAttribution;

  /// 메뉴판의 그 줄에 인쇄된 글자 그대로(예: "쌈싸먹는 꽁치김치찌개").
  ///
  /// 서버가 메뉴판을 줄 단위로 매칭하므로 **같은 foodId가 여러 번 올 수 있다** —
  /// "물만두"와 "군만두"는 둘 다 만두다. 목록에서 후보를 구분하는 건 이 값이지
  /// foodId가 아니다. 좌표 없이 매칭된 경우에는 null이다.
  @override
  final String? menuText;

  /// 위 글자에서 가격만 뗀 것. 카드가 가격을 따로 보여주는 자리에 쓴다.
  @override
  final String? nameText;

  /// 사진에서 이 후보가 나온 자리. 위치를 특정 못 했으면 null이다.
  @override
  final CandidateSource? source;

  /// 서버가 준 줄 번호. 옛 응답에는 없어 null일 수 있다.
  final int? rawLineNo;

  /// 이 음식의 맵기(1~5). 후보 카드의 불꽃 눈금에 쓴다.
  ///
  /// DB에 맵기가 등록되지 않은 음식이면 서버가 null을 주고, 그때는 눈금을 아예
  /// 그리지 않는다 — 모르는 값을 0칸으로 그리면 "안 맵다"는 거짓말이 된다.
  final int? spiceLevel;

  /// 이 줄에 붙어 있던 맵기 수식어(`매운` → Hot).
  final List<Modifier> spiceModifiers;

  /// 이 줄에 붙어 있던 재료 수식어(`꽁치` → Saury).
  final List<Modifier> ingredientModifiers;

  /// 화면에 배지로 그릴 수식어. 맵기를 앞에 둔다 — 못 먹는 사람에게 더 급한 정보다.
  List<Modifier> get modifiers => [...spiceModifiers, ...ingredientModifiers];

  /// 줄 번호를 못 받은 후보를 목록 맨 뒤로 보내는 대체 값.
  ///
  /// 정렬에만 쓰는 값이라 "가장 큰 줄 번호"이기만 하면 되고, 실제 메뉴판 줄 수와는
  /// 상관없다. 웹앱이 같은 자리에서 쓰는 Number.MAX_SAFE_INTEGER와 같은 역할이다.
  static const int lineNoLast = 1 << 62;

  /// 줄 번호가 없으면 [lineNoLast]로 미뤄 **목록 맨 뒤**에 놓는다.
  ///
  /// 예전에는 0을 넣어 맨 앞으로 보냈는데, 줄 위치를 못 잡은 후보는 사진 위에 상자도
  /// 못 그린다. 그래서 목록은 01·02부터 시작하는데 사진의 상자는 03부터 시작해,
  /// 번호가 서로 어긋난 것처럼 보였다. 웹앱(`frontend/client/src/pages/Home.tsx`)이
  /// 이미 맨 뒤로 보내고 있어 앱도 같은 순서로 맞춘다.
  @override
  int get lineNo => rawLineNo ?? lineNoLast;

  @override
  String get cartNameKr => nameKr;

  @override
  String get cartNameEn => nameEn;

  /// 장바구니에서 이 후보를 가리키는 신원. 서버의 묶는 기준과 같아야 한다.
  @override
  String get lineKey => '$foodId|${menuText ?? ''}';

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
  ///   unsupported_food  메뉴 줄은 읽었으나 등록된 음식과 매칭 실패
  ///   not_a_menu        글자는 읽혔지만 가격 붙은 메뉴 줄이 하나도 없음
  ///   ocr_empty         글자를 전혀 읽지 못함
  final String status;

  /// OCR이 읽어낸 원문. 실패 안내를 만들 때 참고용으로 쓴다.
  final String ocrText;

  final List<Candidate> candidates;

  /// 화면에 늘어놓을 메뉴 줄 — 메뉴판에 인쇄된 순서 그대로.
  ///
  /// **안내할 수 있는 후보만 올린다.** 한때는 등록되지 않은 줄도 이름·가격만 실어
  /// 보여줬는데, 그 줄에 대해 아는 것이 사실상 없어서(이름은 OCR이 읽은 글자,
  /// 가격은 같은 줄에서 주운 숫자) 원산지 표시나 가게 공지가 메뉴로 올라오고
  /// 엉뚱한 가격이 붙는 일이 생겼다. 믿을 수 있는 것만 보여준다.
  List<CartAddable> get menuEntries {
    final entries = <CartAddable>[...candidates];
    entries.sort((a, b) => a.lineNo.compareTo(b.lineNo));
    return entries;
  }

  /// 안내할 수 있는 후보가 하나라도 있으면 성공이다.
  bool get isSuccess => candidates.isNotEmpty;

  /// 메뉴 줄은 읽혔지만 등록된 음식이 없는 경우. 안내 문구가 ocrEmpty와 달라야 해서
  /// 따로 구분한다(EC-03 vs EC-04). 다시 찍어도 결과가 같다.
  bool get isUnsupportedFood => status == 'unsupported_food';

  /// 메뉴판이 아닌 사진. 얼굴·풍경을 찍어도 OCR이 잡음 글자를 만들어내므로
  /// isOcrEmpty로는 안 잡힌다. 이쪽은 다시 찍으면 해결된다.
  bool get isNotAMenu => status == 'not_a_menu';

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
  /// (`docs/content-style.md`의 문구 기준을 따른다).
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
  request.files.add(
    await http.MultipartFile.fromPath(
      'image',
      imageFile.path,
      contentType: _imageMediaType(imageFile),
    ),
  );

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
    required this.menuText,
    required this.nameText,
  });

  factory CartLine.fromJson(Map<String, dynamic> json) {
    return CartLine(
      foodId: json['food_id'] as int,
      nameKr: json['name_kr'] as String,
      nameEn: json['name_en'] as String,
      quantity: json['quantity'] as int,
      priceDisplay: json['price_krw_display'] as String?,
      lineTotalDisplay: json['line_total_display'] as String?,
      menuText: json['menu_text'] as String?,
      nameText: json['name_text'] as String?,
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

  /// 메뉴판에 인쇄된 그 줄 글자. 주문 확인 화면이 종업원에게 보여줄 때
  /// 등록 이름("김치찌개")보다 이쪽("쌈싸먹는 꽁치김치찌개")이 정확하다.
  ///
  /// 줄을 구분하는 신원이기도 해서(lineKey) 표시용으로 바꾸지 않는다.
  final String? menuText;

  /// 위 글자에서 가격만 뗀 것. 화면이 가격을 따로 보여주므로 이름 자리에 쓴다.
  /// 옛 서버는 안 준다 — 그때는 [menuText]로 돌아간다.
  final String? nameText;

  /// 장바구니에서 이 줄을 가리키는 신원. [Candidate.lineKey]와 같은 규칙이다.
  String get lineKey => '$foodId|${menuText ?? ''}';
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
  CartAddable item, {
  required int quantityDelta,
}) {
  return _cartRequest(
    () => http.post(
      Uri.parse('$apiBaseUrl/api/cart/items'),
      headers: {'X-Cart-Id': cartId, 'Content-Type': 'application/json'},
      body: jsonEncode({
        'food_id': item.foodId,
        'name_kr': item.cartNameKr,
        'name_en': item.cartNameEn,
        'price_krw': item.priceKrw,
        // 서버가 줄을 구분하는 기준. 안 보내면 물만두와 군만두가 한 줄로 합쳐진다.
        'menu_text': item.menuText,
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
